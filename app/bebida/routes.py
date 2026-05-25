from functools import wraps
import os
from uuid import uuid4

from flask import (Blueprint, flash, redirect, render_template, request,url_for, current_app)

from werkzeug.utils import secure_filename
from sqlalchemy import or_

from forms import BebidaForm, DesactivarForm
from model import Productoo, Bebida, TipoProducto, db


bebidasBp = Blueprint(
    "bebidas",
    __name__,
    url_prefix="/bebidas"
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


@bebidasBp.route("/", methods=["GET"], endpoint="index")
@requiereRol("Gerente")
def index():

    form = DesactivarForm()

    terminoBusqueda = request.args.get("q", "").strip()
    estado = request.args.get("estado", "activos")

    consulta = Productoo.query.filter(
        Productoo.tipo == TipoProducto.BEBIDA
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
        bebidas = consulta.order_by(Productoo.nombre).all()

    elif estado == "inactivos":
        bebidas = consulta.filter(
            Productoo.estatus == False
        ).order_by(Productoo.nombre).all()

    else:
        bebidas = consulta.filter(
            Productoo.estatus == True
        ).order_by(Productoo.nombre).all()

    return render_template(
        "bebidas/bebidas.html",
        bebidas=bebidas,
        terminoBusqueda=terminoBusqueda,
        estado=estado,
        active_page="bebidas",
        form=form
    )


@bebidasBp.route("/nuevo", methods=["GET"], endpoint="nuevo")
@requiereRol("Gerente")
def nuevo():

    form = BebidaForm()

    return render_template(
        "bebidas/nueva_bebida.html",
        form=form,
        active_page="bebidas"
    )

@bebidasBp.route("/crear", methods=["GET", "POST"], endpoint="crear" )
@requiereRol("Gerente")
def crear():

    form = BebidaForm()

    if form.validate_on_submit():

        try:
            nombre = form.nombre.data.strip()
            bebidaExistente = Productoo.query.filter_by(
                nombre=nombre
            ).first()

            if bebidaExistente:

                flash(
                    "Ya existe una bebida con ese nombre.",
                    "danger"
                )

                return render_template(
                    "bebidas/nueva_bebida.html",
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
                    "static/uploads/bebidas"
                )

                os.makedirs(carpetaUploads, exist_ok=True)

                rutaCompleta = os.path.join(
                    carpetaUploads,
                    nombreFinal
                )

                archivo.save(rutaCompleta)

                rutaImagen = (
                    f"/static/uploads/bebidas/{nombreFinal}"
                )

            producto = Productoo(
                nombre=nombre,
                descripcion=form.descripcion.data.strip(),
                foto=rutaImagen,
                precio=form.precio.data,
                tipo=TipoProducto.BEBIDA,
                estatus=1
            )

            db.session.add(producto)
            db.session.flush()

            alimento = Bebida(
                idProducto=producto.idProducto
            )

            db.session.add(alimento)

            db.session.commit()

            flash(
                "Bebidas creado correctamente.",
                "success"
            )

            return redirect(url_for("bebidas.index"))

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
        "bebidas/nueva_bebida.html",
        form=form,
        active_page="bebidas"
    )
@bebidasBp.route( "/<int:idProducto>/editar", methods=["GET"], endpoint="editar")
@requiereRol("Gerente")
def editar(idProducto):

    bebida = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.BEBIDA
    ).first_or_404()

    form = BebidaForm(obj=bebida)

    return render_template(
        "bebidas/editar_bebida.html",
        form=form,
        bebida=bebida,
        active_page="bebidas"
    )

@bebidasBp.route("/<int:idProducto>/actualizar", methods=["POST"], endpoint="actualizar")
@requiereRol("Gerente")
def actualizar(idProducto):

    bebida = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.BEBIDA
    ).first_or_404()

    form = BebidaForm()

    if form.validate_on_submit():

        try:

            nombre = form.nombre.data.strip()

            bebidaExistente = Productoo.query.filter(
                Productoo.nombre == nombre,
                Productoo.idProducto != idProducto
            ).first()

            if bebidaExistente:

                flash(
                    "Ya existe una bebida con ese nombre.",
                    "danger"
                )

                return render_template(
                    "bebidas/editar_bebida.html",
                    form=form,
                    bebida=bebida
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
                    "static/uploads/bebidas"
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

                bebida.foto = (
                    f"/static/uploads/bebidas/{nombreFinal}"
                )
                
            bebida.nombre = nombre

            bebida.descripcion = (
                form.descripcion.data.strip()
            )
            bebida.precio = form.precio.data
            bebida.estatus = 1
            db.session.commit()

            flash(
                "Bebida actualizada correctamente.",
                "success"
            )
            return redirect(
                url_for("bebidas.index")
            )

        except Exception as e:
            db.session.rollback()
            flash(
                "Error al actualizar la bebida.",
                "danger"
            )
            print(e)

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(
                    erroresCampo[0],
                    "danger")
                break

    return render_template(
        "bebidas/editar_bebida.html",
        form=form,
        bebida=bebida,
        active_page="alimentos"
    )

@bebidasBp.route("/<int:idProducto>/desactivar", methods=["POST"], endpoint="desactivar")
@requiereRol("Gerente")
def desactivar(idProducto):

    bebida = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.BEBIDA
    ).first_or_404()

    form = DesactivarForm()

    if form.validate_on_submit():

        bebida.estatus = False

        db.session.commit()

        flash(
            "Bebida desactivada correctamente.",
            "success"
        )
    return redirect(
        url_for("bebidas.index")
    )


@bebidasBp.route("/<int:idProducto>/reactivar", methods=["POST"], endpoint="reactivar")
@requiereRol("Gerente")
def reactivar(idProducto):

    bebida = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.BEBIDA
    ).first_or_404()

    form = DesactivarForm()
    if form.validate_on_submit():
        bebida.estatus = True
        db.session.commit()

        flash(
            "Bebida reactivada correctamente.",
            "success"
        )

    return redirect(
        url_for("bebidas.index")
    )