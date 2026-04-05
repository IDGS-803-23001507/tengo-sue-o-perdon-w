from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from model import db, Compra, convertir, DetalleCompra, Proveedores, MateriaPrima, UnidadMedida
from sqlalchemy import func
from datetime import datetime
from decimal import Decimal
import forms

compras_bp = Blueprint('compras', __name__)

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

    proveedores = Proveedores.query.filter_by(estado=True).all()
    form.set_proveedores(proveedores)

    if form.validate_on_submit():
        print(form.errors)
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

            for i in range(len(materias_ids)):

                if materias_ids[i] and cantidades[i] and costos[i]:

                    materia_id     = int(materias_ids[i])
                    cantidad       = Decimal(cantidades[i])
                    costo_unitario = Decimal(costos[i])
                    unidad_id      = int(unidades_ids[i]) if unidades_ids[i] else None


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

                    materia.stock_actual += cantidad_convertida

            db.session.commit()

            flash('Compra registrada exitosamente', 'success')
            return redirect(url_for('compras.detalle_compra', id=compra.id_compra))

        except Exception as e:
            db.session.rollback()
            print("ERROR REAL:", e)
            raise 

    materias_primas = MateriaPrima.query.all()
    unidades        = UnidadMedida.query.all()

    return render_template('compras/nueva_compra.html', active_page = 'compras', form=form, proveedores=proveedores, materias_primas=materias_primas, unidades=unidades, datetime=datetime)


@compras_bp.route('/compras/detalle/<int:id>')
def detalle_compra(id):
    compra = Compra.query.get_or_404(id)
    return render_template('compras/detalle_compra.html', compra=compra)


@compras_bp.route('/compras/obtener_materia/<int:materia_id>')
def obtener_materia(materia_id):

    materia = MateriaPrima.query.get_or_404(materia_id)

    return jsonify({ 'id': materia.id_materia, 'nombre': materia.nombre, 
                    'unidad_id': materia.unidad_medida, 
                    'unidad_nombre': materia.unidad.abreviacion if materia.unidad else 'ud', 
                    'stock_actual': float(materia.stock_actual or 0)})