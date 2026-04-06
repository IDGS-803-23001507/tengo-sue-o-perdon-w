from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from forms import ProductoTerminadoEditarForm, ProductoTerminadoForm
from model import Producto, db

producto_bp = Blueprint("producto_terminado", __name__, url_prefix="/producto-terminado")


@producto_bp.route("/catalogo", endpoint="index")
def index():
    busqueda = (request.args.get("q") or "").strip()

    query = Producto.query
    if busqueda:
        query = query.filter(Producto.nombre.ilike(f"%{busqueda}%"))

    productos = query.order_by(Producto.nombre.asc()).all()
    return render_template(
        "producto_terminado/index.html",
        productos=productos,
        busqueda=busqueda,
        active_page="producto_terminado",
    )


@producto_bp.route("/nuevo-producto", methods=["GET", "POST"], endpoint="nuevo_producto")
def nuevo_producto():
    form = ProductoTerminadoForm()

    if form.validate_on_submit():
        try:
            nuevo = Producto(
                nombre=form.nombre.data.strip(),
                categoria=form.categoria.data,
                precio_venta=form.precio_venta.data,
                descripcion="",
            )

            db.session.add(nuevo)
            db.session.commit()

            flash("Producto registrado. Ahora captura su receta.", "success")
            return redirect(url_for("recetas.nueva", producto=nuevo.id_producto))
        except SQLAlchemyError:
            db.session.rollback()
            flash("No se pudo guardar el producto. Verifica los datos e inténtalo de nuevo.", "danger")

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "producto_terminado/nuevo_producto.html",
        form=form,
        mostrar_modal=False,
        active_page="producto_terminado",
    )


@producto_bp.route("/editar-producto/<int:id>", methods=["GET", "POST"], endpoint="editar_producto")
def editar_producto(id: int):
    producto = Producto.query.get_or_404(id)
    form = ProductoTerminadoEditarForm(obj=producto)
    if request.method == "GET":
        form.estatus.data = "1" if producto.estatus else "0"

    if form.validate_on_submit():
        try:
            producto.nombre = form.nombre.data.strip()
            producto.categoria = form.categoria.data
            producto.precio_venta = form.precio_venta.data
            producto.estatus = True if form.estatus.data == "1" else False
            db.session.commit()

            return render_template(
                "producto_terminado/editar_producto.html",
                form=form,
                mostrar_modal=True,
                producto=producto,
                active_page="producto_terminado",
            )
        except SQLAlchemyError:
            db.session.rollback()
            flash("No se pudo actualizar el producto. Inténtalo nuevamente.", "danger")

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "producto_terminado/editar_producto.html",
        form=form,
        mostrar_modal=False,
        producto=producto,
        active_page="producto_terminado",
    )
