from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from forms import AgregarDetalleSolicitudForm
from model import DetalleProduccion, Producto, SolicitudProduccion, db

solicitud_bp = Blueprint("solicitud", __name__, url_prefix="/solicitud")


@solicitud_bp.route("/", endpoint="index")
def index():
    solicitudes = SolicitudProduccion.query.order_by(SolicitudProduccion.fecha.desc()).all()
    return render_template("solicitud/solicitud.html", solicitudes=solicitudes, active_page="solicitudes")


@solicitud_bp.route("/crear", methods=["GET", "POST"], endpoint="crear_solicitud")
def crear_solicitud():
    productos_disponibles = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()
    form = AgregarDetalleSolicitudForm()
    form.set_productos(productos_disponibles)

    if form.validate_on_submit():
        id_usuario = session.get("usuarioId")
        if not id_usuario:
            flash("Tu sesión no es válida. Inicia sesión nuevamente.", "danger")
            return redirect(url_for("auth.iniciarSesion"))

        try:
            nueva_solicitud = SolicitudProduccion(id_usuario=id_usuario)
            db.session.add(nueva_solicitud)
            db.session.flush()

            primer_detalle = DetalleProduccion(
                id_solicitud=nueva_solicitud.id_solicitud,
                id_producto=form.id_producto.data,
                cantidad=form.cantidad.data,
            )
            db.session.add(primer_detalle)
            db.session.commit()

            return redirect(url_for("solicitud.detalles_solicitud", id=nueva_solicitud.id_solicitud, creado=1))
        except SQLAlchemyError:
            db.session.rollback()
            flash("No se pudo crear la solicitud. Inténtalo nuevamente.", "danger")

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "solicitud/nueva_solicitud.html",
        form=form,
        active_page="solicitudes",
    )


@solicitud_bp.route("/<int:id>/detalles", methods=["GET", "POST"], endpoint="detalles_solicitud")
def detalles_solicitud(id: int):
    solicitud = SolicitudProduccion.query.get_or_404(id)
    productos_disponibles = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()
    tipo_modal = ""
    if request.args.get("creado") == "1":
        tipo_modal = "creado"
    elif request.args.get("agregado") == "1":
        tipo_modal = "agregado"

    mostrar_modal = bool(tipo_modal)
    form = AgregarDetalleSolicitudForm()
    form.set_productos(productos_disponibles)

    if form.validate_on_submit():
        id_producto = form.id_producto.data
        cantidad = form.cantidad.data

        try:
            nuevo_detalle = DetalleProduccion(
                id_solicitud=solicitud.id_solicitud,
                id_producto=id_producto,
                cantidad=cantidad,
            )
            db.session.add(nuevo_detalle)
            db.session.commit()

            return redirect(url_for("solicitud.detalles_solicitud", id=solicitud.id_solicitud, agregado=1))
        except SQLAlchemyError:
            db.session.rollback()
            flash("No se pudo agregar el producto a la solicitud.", "danger")

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "solicitud/detalles.html",
        solicitud=solicitud,
        form=form,
        mostrar_modal=mostrar_modal,
        tipo_modal=tipo_modal,
        active_page="solicitudes",
    )


@solicitud_bp.route("/<int:id>/finalizar", methods=["POST"], endpoint="finalizar_solicitud")
def finalizar_solicitud(id: int):
    solicitud = SolicitudProduccion.query.get_or_404(id)

    if not solicitud.detalles:
        flash("Agrega al menos un producto antes de finalizar la solicitud.", "danger")
        return redirect(url_for("solicitud.detalles_solicitud", id=solicitud.id_solicitud))

    try:
        solicitud.estado = "finalizado"
        db.session.commit()
        return redirect(url_for("solicitud.index"))
    except SQLAlchemyError:
        db.session.rollback()
        flash("No se pudo finalizar la solicitud. Inténtalo nuevamente.", "danger")
        return redirect(url_for("solicitud.detalles_solicitud", id=solicitud.id_solicitud))
