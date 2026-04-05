from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from model import DetalleProduccion, Producto, SolicitudProduccion, db

solicitud_bp = Blueprint("solicitud", __name__, url_prefix="/solicitud")


@solicitud_bp.route("/", endpoint="index")
def index():
    solicitudes = SolicitudProduccion.query.order_by(SolicitudProduccion.fecha.desc()).all()
    return render_template("solicitud/solicitud.html", solicitudes=solicitudes, active_page="solicitudes")


@solicitud_bp.route("/crear", endpoint="crear_solicitud")
def crear_solicitud():
    # Integrado con sesión. Si no hay sesión, usa un usuario temporal.
    id_usuario = session.get("usuarioId") or 1

    nueva_solicitud = SolicitudProduccion(id_usuario=id_usuario)
    db.session.add(nueva_solicitud)
    db.session.commit()

    return redirect(url_for("solicitud.detalles_solicitud", id=nueva_solicitud.id_solicitud))


@solicitud_bp.route("/<int:id>/detalles", methods=["GET", "POST"], endpoint="detalles_solicitud")
def detalles_solicitud(id: int):
    solicitud = SolicitudProduccion.query.get_or_404(id)
    productos_disponibles = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()

    if request.method == "POST":
        id_producto = request.form.get("id_producto", type=int)
        cantidad = request.form.get("cantidad", type=int)

        if not id_producto or not cantidad or cantidad <= 0:
            flash("Selecciona un producto y una cantidad válida.", "danger")
            return redirect(url_for("solicitud.detalles_solicitud", id=solicitud.id_solicitud))

        nuevo_detalle = DetalleProduccion(
            id_solicitud=solicitud.id_solicitud,
            id_producto=id_producto,
            cantidad=cantidad,
        )
        db.session.add(nuevo_detalle)
        db.session.commit()

        flash("Producto agregado a la solicitud.", "success")
        return redirect(url_for("solicitud.detalles_solicitud", id=solicitud.id_solicitud))

    return render_template(
        "solicitud/detalles.html",
        solicitud=solicitud,
        productos=productos_disponibles,
        active_page="solicitudes",
    )
