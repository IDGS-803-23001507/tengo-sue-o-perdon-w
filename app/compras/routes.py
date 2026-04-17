from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.auditoria import registrar_auditoria
from app.food_cost_service import recalcular_productos_por_materia
from model import db, Compra, convertir, DetalleCompra, Proveedores, MateriaPrima, UnidadMedida
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
import forms

from itsdangerous import URLSafeSerializer
from flask import current_app

compras_bp = Blueprint('compras', __name__)

def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

@compras_bp.route('/compras')
def compras():
    return redirect(url_for('compras.listar_compras'))


@compras_bp.route('/compras/listar')
def listar_compras():

    filtro_form = forms.FiltroComprasForm(request.args)

    proveedores = Proveedores.query.filter_by(estado=True).all()
    filtro_form.set_proveedores(proveedores)

    query = Compra.query

    if filtro_form.fecha_inicio.data:
        query = query.filter(func.date(Compra.fecha) >= filtro_form.fecha_inicio.data)

    if filtro_form.fecha_fin.data:
        query = query.filter(func.date(Compra.fecha) <= filtro_form.fecha_fin.data)

    if filtro_form.id_proveedor.data and filtro_form.id_proveedor.data != 0:
        query = query.filter(Compra.id_proveedor == filtro_form.id_proveedor.data)

    compras_list = query.order_by(Compra.fecha.desc()).all()

    return render_template( 'compras/compras.html', active_page = 'compras',compras=compras_list, filtro_form=filtro_form)


@compras_bp.route('/compras/nueva', methods=['GET', 'POST'])
def nueva_compra():

    form = forms.CompraForm()
    compra_token = session.get("compra_form_token")
    if request.method == "GET" or not compra_token:
        compra_token = uuid4().hex
        session["compra_form_token"] = compra_token

    proveedores = Proveedores.query.filter_by(estado=True).all()
    form.set_proveedores(proveedores)

    if form.validate_on_submit():
        token_form = (request.form.get("compra_token") or "").strip()
        token_sesion = (session.get("compra_form_token") or "").strip()

        if not token_form or token_form != token_sesion:
            flash("La compra ya fue enviada o el formulario expiró. Intenta nuevamente.", "warning")
            return redirect(url_for('compras.nueva_compra'))

        session.pop("compra_form_token", None)

        try:
            compra = Compra(
                id_proveedor=form.id_proveedor.data,
                fecha=form.fecha.data
            )
            db.session.add(compra)
            db.session.flush()

            materias_ids = request.form.getlist('materia_id[]')
            cantidades   = request.form.getlist('cantidad[]')
            costos       = request.form.getlist('costo_unitario[]')
            unidades_ids = request.form.getlist('unidad_id[]')

            if not any(m for m in materias_ids if m):
                raise ValueError('Debe agregar al menos un insumo a la compra')

            insumos_vistos = set()
            materias_afectadas = set()

            for i in range(len(materias_ids)):

                if materias_ids[i] and cantidades[i] and costos[i]:

                    materia_id     = int(materias_ids[i])
                    cantidad       = Decimal(cantidades[i])
                    costo_unitario = Decimal(costos[i])
                    unidad_id      = int(unidades_ids[i]) if unidades_ids[i] else None

                    if cantidad <= 0 or costo_unitario <= 0:
                        raise ValueError("Cantidad y costo unitario deben ser mayores a cero")

                    clave_insumo = (materia_id, unidad_id)
                    if clave_insumo in insumos_vistos:
                        raise ValueError("No repitas el mismo insumo con la misma unidad en una compra")
                    insumos_vistos.add(clave_insumo)


                    materia = MateriaPrima.query.get(materia_id)
                    if not materia:
                        raise ValueError("Materia prima no encontrada")

                    unidad_compra = UnidadMedida.query.get(unidad_id)
                    if not unidad_compra:
                        raise ValueError("Unidad de medida no válida")
                    
                    try:
                        cantidad_convertida = convertir(
                            cantidad,
                            unidad_compra,
                            materia.unidad
                        )
                        
                    except ValueError as e:
                        raise ValueError(f"Error en unidades: {str(e)}")
                    
                    detalle = DetalleCompra(
                        id_compra=compra.id_compra,
                        id_materia=materia_id,
                        cantidad=cantidad,
                        unidad=unidad_id,
                        costo_unitario=costo_unitario
                    )
                    db.session.add(detalle)

                    materia = MateriaPrima.query.get(materia_id)
                    if not materia:
                        raise ValueError("Materia prima no encontrada")

                    # --- Actualizar costo promedio de la materia prima ---
                    # IMPORTANT: Do this BEFORE updating stock_actual to avoid math corruption
                    costo_por_unidad_base = (costo_unitario * cantidad) / cantidad_convertida if cantidad_convertida > 0 else costo_unitario
                    materia.actualizar_costo_promedio(float(costo_por_unidad_base), float(cantidad_convertida))
                    materias_afectadas.add(materia_id)

                    materia.stock_actual += cantidad_convertida

                    registrar_auditoria(
                        accion="Cambio de Costo de Materia Prima",
                        modulo="Inventario",
                        detalles={
                            "id_materia": materia_id,
                            "id_compra": compra.id_compra,
                            "costo_unitario": str(costo_unitario),
                            "cantidad": str(cantidad),
                            "unidad": unidad_compra.abreviacion if unidad_compra else None,
                        },
                        commit=False,
                    )

            db.session.commit()

            # --- Evento B (Cascada): Recalcular precios de productos afectados ---
            for id_mat in materias_afectadas:
                recalcular_productos_por_materia(id_mat)

            flash('Compra registrada exitosamente', 'success')
            return redirect(url_for('compras.detalle_compra',  token=get_serializer().dumps(compra.id_compra)))

        except (ValueError, SQLAlchemyError) as e:
            db.session.rollback()
            flash(str(e) if str(e) else "No se pudo registrar la compra", 'danger')

            compra_token = uuid4().hex
            session["compra_form_token"] = compra_token

    materias_primas = MateriaPrima.query.all()
    unidades        = UnidadMedida.query.all()

    if request.method == 'POST' and not form.validate_on_submit():
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break

    return render_template(
        'compras/nueva_compra.html',
        active_page='compras',
        form=form,
        proveedores=proveedores,
        materias_primas=materias_primas,
        unidades=unidades,
        datetime=datetime,
        compra_token=compra_token,
    )


@compras_bp.route('/compras/detalle/<token>')
def detalle_compra(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("compras.listar_compras"))

    compra = Compra.query.get_or_404(id)
    return render_template('compras/detalle_compra.html', compra=compra)


@compras_bp.route('/compras/cancelar/<token>', methods=['POST'])
def cancelar_compra(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("compras.listar_compras"))
    
    compra = Compra.query.get_or_404(id)

    try:
        for detalle in compra.detalles:
            materia = MateriaPrima.query.get(detalle.id_materia)
            if not materia:
                continue

            unidad_detalle = detalle.unidad_medida
            unidad_materia = materia.unidad
            cantidad_revertir = convertir(Decimal(str(detalle.cantidad)), unidad_detalle, unidad_materia)

            stock_actual = Decimal(str(materia.stock_actual or 0))
            materia.stock_actual = max(stock_actual - Decimal(str(cantidad_revertir)), Decimal('0'))

        registrar_auditoria(
            accion='Cancelación de Compra',
            modulo='Compras',
            detalles={'id_compra': compra.id_compra, 'id_proveedor': compra.id_proveedor},
            commit=False,
        )

        db.session.delete(compra)
        db.session.commit()
        flash('Compra cancelada correctamente.', 'success')
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        flash('No se pudo cancelar la compra.', 'danger')

    return redirect(url_for('compras.listar_compras'))


@compras_bp.route('/compras/obtener_materia/<int:materia_id>')
def obtener_materia(materia_id):

    materia = MateriaPrima.query.get_or_404(materia_id)
    
    ultimo_costo = 0
    ultimo_detalle = DetalleCompra.query.filter_by(id_materia=materia_id).order_by(DetalleCompra.id_detalle_compra.desc()).first()
    if ultimo_detalle:
        ultimo_costo = float(ultimo_detalle.costo_unitario)

    return jsonify({ 'id': materia.id_materia, 'nombre': materia.nombre, 
                    'unidad_id': materia.unidad_medida, 
                    'unidad_nombre': materia.unidad.abreviacion if materia.unidad else 'ud', 
                    'stock_actual': float(materia.stock_actual or 0),
                    'ultimo_costo': ultimo_costo})