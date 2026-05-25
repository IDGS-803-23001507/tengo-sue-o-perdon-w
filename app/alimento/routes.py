from functools import wraps
import os
from uuid import uuid4

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    current_app
)

from werkzeug.utils import secure_filename
from sqlalchemy import or_

from forms import AlimentoForm, DesactivarForm
from model import Productoo, Alimento, TipoProducto, db


alimentosBp = Blueprint(
    "alimentos",
    __name__,
    url_prefix="/alimentos"
)

def requiereRol(rolRequerido: str):

    def decorador(funcionVista):

        @wraps(funcionVista)
        def envuelta(*args, **kwargs):

            from flask import session

            if not session.get("inicioSesion"):
                return redirect(url_for("auth.iniciarSesion"))

            rolSesion = session.get("usuarioRol")

            equivalencias = {
                "Gerente": {
                    "Gerente",
                    "Gerente de Tienda",
                    "Admin General",
                    "Admin General (TI)"
                }
            }

            rolesPermitidos = equivalencias.get(
                rolRequerido,
                {rolRequerido}
            )

            if rolSesion not in rolesPermitidos:
                flash(
                    "No tienes permisos para acceder.",
                    "danger"
                )
                return redirect(url_for("dashboard_operador"))

            return funcionVista(*args, **kwargs)

        return envuelta

    return decorador


@alimentosBp.route("/", methods=["GET"], endpoint="index")
@requiereRol("Gerente")
def index():

    form = DesactivarForm()

    terminoBusqueda = request.args.get("q", "").strip()
    estado = request.args.get("estado", "activos")

    consulta = Productoo.query.filter(
        Productoo.tipo == TipoProducto.ALIMENTO
    )

    if terminoBusqueda:

        patron = f"%{terminoBusqueda}%"

        consulta = consulta.filter(
            or_(
                Productoo.nombre.ilike(patron),
                Productoo.descripcion.ilike(patron)
            )
        )

    if estado == "todos":
        alimentos = consulta.order_by(Productoo.nombre).all()

    elif estado == "inactivos":
        alimentos = consulta.filter(
            Productoo.estatus == False
        ).order_by(Productoo.nombre).all()

    else:
        alimentos = consulta.filter(
            Productoo.estatus == True
        ).order_by(Productoo.nombre).all()

    return render_template(
        "alimentos/alimentos.html",
        alimentos=alimentos,
        terminoBusqueda=terminoBusqueda,
        estado=estado,
        active_page="alimentos",
        form=form
    )


@alimentosBp.route("/nuevo", methods=["GET"], endpoint="nuevo")
@requiereRol("Gerente")
def nuevo():

    form = AlimentoForm()

    return render_template(
        "alimentos/nuevo_alimento.html",
        form=form,
        active_page="alimentos"
    )

@alimentosBp.route(
    "/crear",
    methods=["GET", "POST"],
    endpoint="crear"
)
@requiereRol("Gerente")
def crear():

    form = AlimentoForm()

    if form.validate_on_submit():

        try:

            nombre = form.nombre.data.strip()

            alimentoExistente = Productoo.query.filter_by(
                nombre=nombre
            ).first()

            if alimentoExistente:

                flash(
                    "Ya existe un alimento con ese nombre.",
                    "danger"
                )

                return render_template(
                    "alimentos/nuevo_alimento.html",
                    form=form
                )

            rutaImagen = None

            if form.foto.data:

                archivo = form.foto.data

                nombreSeguro = secure_filename(archivo.filename)

                extension = os.path.splitext(
                    nombreSeguro
                )[1]

                nombreFinal = f"{uuid4().hex}{extension}"

                carpetaUploads = os.path.join(
                    current_app.root_path,
                    "static/uploads/alimentos"
                )

                os.makedirs(carpetaUploads, exist_ok=True)

                rutaCompleta = os.path.join(
                    carpetaUploads,
                    nombreFinal
                )

                archivo.save(rutaCompleta)

                rutaImagen = (
                    f"/static/uploads/alimentos/{nombreFinal}"
                )

            producto = Productoo(
                nombre=nombre,
                descripcion=form.descripcion.data.strip(),
                foto=rutaImagen,
                precio=form.precio.data,
                tipo=TipoProducto.ALIMENTO,
                estatus=1
            )

            db.session.add(producto)
            db.session.flush()
            alimento = Alimento(
                idProducto=producto.idProducto
            )

            db.session.add(alimento)

            db.session.commit()

            flash(
                "Alimento creado correctamente.",
                "success"
            )

            return redirect(url_for("alimentos.index"))

        except Exception as e:

            db.session.rollback()

            flash(
                "Error al crear el alimento.",
                "danger"
            )

            print(e)

    if request.method == "POST":

        for erroresCampo in form.errors.values():

            if erroresCampo:

                flash(
                    erroresCampo[0],
                    "danger"
                )

                break

    return render_template(
        "alimentos/nuevo_alimento.html",
        form=form,
        active_page="alimentos"
    )
    
@alimentosBp.route( "/<int:idProducto>/editar", methods=["GET"], endpoint="editar")
@requiereRol("Gerente")
def editar(idProducto):

    alimento = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.ALIMENTO
    ).first_or_404()

    form = AlimentoForm(obj=alimento)

    return render_template(
        "alimentos/editar_alimento.html",
        form=form,
        alimento=alimento,
        active_page="alimentos"
    )

@alimentosBp.route("/<int:idProducto>/actualizar", methods=["POST"], endpoint="actualizar")
@requiereRol("Gerente")
def actualizar(idProducto):

    alimento = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.ALIMENTO
    ).first_or_404()

    form = AlimentoForm()

    if form.validate_on_submit():

        try:

            nombre = form.nombre.data.strip()

            alimentoExistente = Productoo.query.filter(
                Productoo.nombre == nombre,
                Productoo.idProducto != idProducto
            ).first()

            if alimentoExistente:

                flash(
                    "Ya existe un alimento con ese nombre.",
                    "danger"
                )

                return render_template(
                    "alimentos/editar_alimento.html",
                    form=form,
                    alimento=alimento
                )
                
            if form.foto.data:

                archivo = form.foto.data

                nombreSeguro = secure_filename(
                    archivo.filename
                )

                extension = os.path.splitext(
                    nombreSeguro
                )[1]

                nombreFinal = f"{uuid4().hex}{extension}"

                carpetaUploads = os.path.join(
                    current_app.root_path,
                    "static/uploads/alimentos"
                )

                os.makedirs(
                    carpetaUploads,
                    exist_ok=True
                )

                rutaCompleta = os.path.join(
                    carpetaUploads,
                    nombreFinal
                )

                archivo.save(rutaCompleta)

                alimento.foto = (
                    f"/static/uploads/alimentos/{nombreFinal}"
                )
                
            alimento.nombre = nombre

            alimento.descripcion = (
                form.descripcion.data.strip()
            )

            alimento.precio = form.precio.data
            alimento.estatus = 1

            db.session.commit()

            flash(
                "Alimento actualizado correctamente.",
                "success"
            )

            return redirect(
                url_for("alimentos.index")
            )

        except Exception as e:

            db.session.rollback()

            flash(
                "Error al actualizar el alimento.",
                "danger"
            )

            print(e)

    if request.method == "POST":

        for erroresCampo in form.errors.values():

            if erroresCampo:

                flash(
                    erroresCampo[0],
                    "danger"
                )

                break

    return render_template(
        "alimentos/editar_alimento.html",
        form=form,
        alimento=alimento,
        active_page="alimentos"
    )

@alimentosBp.route("/<int:idProducto>/desactivar", methods=["POST"], endpoint="desactivar")
@requiereRol("Gerente")
def desactivar(idProducto):

    alimento = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.ALIMENTO
    ).first_or_404()

    form = DesactivarForm()

    if form.validate_on_submit():

        alimento.estatus = False

        db.session.commit()

        flash(
            "Alimento desactivado correctamente.",
            "success"
        )

    return redirect(
        url_for("alimentos.index")
    )


@alimentosBp.route("/<int:idProducto>/reactivar", methods=["POST"], endpoint="reactivar")
@requiereRol("Gerente")
def reactivar(idProducto):

    alimento = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.ALIMENTO
    ).first_or_404()

    form = DesactivarForm()

    if form.validate_on_submit():

        alimento.estatus = True

        db.session.commit()

        flash(
            "Alimento reactivado correctamente.",
            "success"
        )

    return redirect(
        url_for("alimentos.index")
    )