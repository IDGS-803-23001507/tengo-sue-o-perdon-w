from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from app.auditoria import registrar_auditoria
from forms import RegistroProduccionForm
from model import (
    Cliente,
    DetalleProduccion,
    Empleado,
    Producto,
    Receta,
    SolicitudProduccion,
    Usuario,
    db,
)

produccion_bp = Blueprint("produccion", __name__, url_prefix="/produccion")


def _nombre_operador(usuario: Usuario | None) -> str:
    if not usuario:
        return "Usuario desconocido"
    if usuario.empleado:
        return usuario.empleado.nombre
    if usuario.cliente:
        return usuario.cliente.nombre
    return usuario.correo or f"Usuario #{usuario.id}"


def _obtener_historial_reciente() -> list[DetalleProduccion]:
    ayer = (datetime.utcnow() - timedelta(days=1)).date()

    return (
        DetalleProduccion.query
        .join(SolicitudProduccion, DetalleProduccion.id_solicitud == SolicitudProduccion.id_solicitud)
        .outerjoin(Usuario, SolicitudProduccion.id_usuario == Usuario.id)
        .outerjoin(Empleado, Usuario.id == Empleado.usuarioId)
        .outerjoin(Cliente, Usuario.id == Cliente.usuarioId)
        .join(Producto, DetalleProduccion.id_producto == Producto.id_producto)
        .filter(
            SolicitudProduccion.estado == "finalizado",
            func.date(SolicitudProduccion.fecha) >= ayer,
        )
        .order_by(SolicitudProduccion.fecha.desc(), DetalleProduccion.id_detalle.desc())
        .limit(120)
        .all()
    )


@produccion_bp.route("/", methods=["GET", "POST"], endpoint="index")
def index():
    form = RegistroProduccionForm()
    productos = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()
    form.set_productos(productos)

    if form.validate_on_submit():
        usuario_id = session.get("usuarioId")
        if not usuario_id:
            flash("Tu sesión no es válida. Inicia sesión nuevamente.", "danger")
            return redirect(url_for("auth.iniciarSesion"))

        try:
            Receta.validar_activa_para_produccion(form.id_producto.data)

            solicitud = SolicitudProduccion(
                id_usuario=usuario_id,
                estado="pendiente",
            )
            db.session.add(solicitud)
            db.session.flush()

            detalle = DetalleProduccion(
                id_solicitud=solicitud.id_solicitud,
                id_producto=form.id_producto.data,
                cantidad=form.cantidad.data,
            )
            db.session.add(detalle)
            db.session.flush()

            db.session.execute(
                text("CALL sp_finalizar_solicitud_produccion(:id_solicitud)"),
                {"id_solicitud": solicitud.id_solicitud},
            )

            registrar_auditoria(
                accion="Registro de Producción",
                modulo="Producción",
                detalles={
                    "id_solicitud": solicitud.id_solicitud,
                    "id_producto": form.id_producto.data,
                    "cantidad": form.cantidad.data,
                    "id_operador": usuario_id,
                },
                commit=False,
            )

            db.session.commit()
            flash("Producción registrada y stock actualizado correctamente.", "success")
            return redirect(url_for("produccion.index"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except SQLAlchemyError as exc:
            db.session.rollback()
            mensaje = str(getattr(exc, "orig", exc))
            flash(f"No se pudo registrar la producción: {mensaje}", "danger")

    if request.method == "POST":
        for errores_campo in form.errors.values():
            if errores_campo:
                flash(errores_campo[0], "danger")
                break

    historial = _obtener_historial_reciente()

    return render_template(
        "produccion/produccion.html",
        form=form,
        historial=historial,
        nombre_operador=_nombre_operador,
        active_page="produccion",
    )


@produccion_bp.route("/insumos", methods=["GET"], endpoint="insumos")
def obtener_insumos_requeridos():
    id_producto = request.args.get("id_producto", type=int)
    cantidad = request.args.get("cantidad", type=int, default=1)

    if not id_producto or cantidad <= 0:
        return jsonify({"ok": False, "message": "Producto o cantidad inválidos.", "insumos": []}), 400

    recetas = (
        Receta.query
        .filter_by(id_producto=id_producto, estado=True)
        .order_by(Receta.id_receta.asc())
        .all()
    )

    if not recetas:
        return jsonify({"ok": False, "message": "El producto no tiene receta activa.", "insumos": []}), 404

    insumos = []
    inventario_suficiente = True

    for receta in recetas:
        materia = receta.materiaPrima
        if not materia:
            continue

        requerido = (Decimal(str(receta.cantidad)) * Decimal(str(cantidad))).quantize(Decimal("0.01"))
        disponible = Decimal(str(materia.stock_actual or 0)).quantize(Decimal("0.01"))
        suficiente = disponible >= requerido

        if not suficiente:
            inventario_suficiente = False

        unidad = ""
        if materia.unidad:
            unidad = materia.unidad.abreviacion or materia.unidad.nombre or ""

        insumos.append(
            {
                "id_materia": materia.id_materia,
                "materia": materia.nombre,
                "unidad": unidad,
                "requerido": float(requerido),
                "disponible": float(disponible),
                "suficiente": suficiente,
            }
        )

    return jsonify(
        {
            "ok": True,
            "message": "ok",
            "insumos": insumos,
            "inventario_suficiente": inventario_suficiente,
        }
    )
