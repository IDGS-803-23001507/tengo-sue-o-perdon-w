from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from forms import AgregarDetalleSolicitudForm
from model import DetalleProduccion, Producto, SolicitudProduccion, db

solicitud_bp = Blueprint("solicitud", __name__, url_prefix="/solicitud")


@solicitud_bp.route("/", endpoint="index")
def index():
    solicitudes = SolicitudProduccion.query.order_by(SolicitudProduccion.fecha.desc()).all()
    return render_template("solicitud/solicitud.html", solicitudes=solicitudes, active_page="solicitudes")


@solicitud_bp.route("/crear", endpoint="crear_solicitud")
def crear_solicitud():
    id_usuario = session.get("usuarioId") or 1

    nueva_solicitud = SolicitudProduccion(id_usuario=id_usuario)
    db.session.add(nueva_solicitud)
    db.session.commit()

    return redirect(url_for("solicitud.detalles_solicitud", id=nueva_solicitud.id_solicitud))


@solicitud_bp.route("/<int:id>/detalles", methods=["GET", "POST"], endpoint="detalles_solicitud")
def detalles_solicitud(id: int):
    solicitud = SolicitudProduccion.query.get_or_404(id)
    productos_disponibles = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()
    form = AgregarDetalleSolicitudForm()
    form.set_productos(productos_disponibles)

    if form.validate_on_submit():
        id_producto = form.id_producto.data
        cantidad = form.cantidad.data

        nuevo_detalle = DetalleProduccion(
            id_solicitud=solicitud.id_solicitud,
            id_producto=id_producto,
            cantidad=cantidad,
        )
        db.session.add(nuevo_detalle)
        db.session.commit()

        flash("Producto agregado a la solicitud.", "success")
        return redirect(url_for("solicitud.detalles_solicitud", id=solicitud.id_solicitud))

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "solicitud/detalles.html",
        solicitud=solicitud,
        form=form,
        active_page="solicitudes",
    )
