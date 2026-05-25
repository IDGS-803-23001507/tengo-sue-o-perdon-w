from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_

import os
from werkzeug.utils import secure_filename
from forms import SucursalForm, DesactivarForm
from model import Sucursal, db

sucursalesBp = Blueprint(
    "sucursales",
    __name__,
    url_prefix="/sucursales"
)

@sucursalesBp.route("/", methods=["GET"], endpoint="index")
def index():

    form = DesactivarForm()

    terminoBusqueda = request.args.get("q", "").strip()
    estado = request.args.get("estado", "activas")

    consulta = Sucursal.query

    if terminoBusqueda:

        patron = f"%{terminoBusqueda}%"

        consulta = consulta.filter(
            or_(
                Sucursal.nombre.ilike(patron),
                Sucursal.ciudad.ilike(patron),
                Sucursal.colonia.ilike(patron),
                Sucursal.cp.ilike(patron)
            )
        )

    if estado == "inactivas":

        consulta = consulta.filter(
            Sucursal.estatus == False
        )

    elif estado == "todas":

        pass

    else:

        consulta = consulta.filter(
            Sucursal.estatus == True
        )

    sucursales = consulta.order_by(
        Sucursal.nombre
    ).all()

    return render_template(
        "sucursales/sucursales.html",
        sucursales=sucursales,
        terminoBusqueda=terminoBusqueda,
        estado=estado,
        form=form,
        active_page="sucursales"
    )


@sucursalesBp.route("/nuevo", methods=["GET"], endpoint="nuevo")
def nuevo():

    form = SucursalForm()

    return render_template(
        "sucursales/nueva_sucursal.html",
        form=form,
        active_page="sucursales"
    )


@sucursalesBp.route(
    "/crear",
    methods=["GET", "POST"],
    endpoint="crear"
)

def crear():
    form = SucursalForm()
    if form.validate_on_submit():

        try:
            nombreSucursal = form.nombre.data.strip()
            sucursalExistente = Sucursal.query.filter_by(
                nombre=nombreSucursal
            ).first()
            if sucursalExistente:

                flash(
                    "Ya existe una sucursal con ese nombre.",
                    "danger"
                )

                return render_template(
                    "sucursales/nueva_sucursal.html",
                    form=form,
                    active_page="sucursales"
                )
                
            archivo = form.foto.data
            rutaImagen = None

            if archivo:

                nombreSeguro = secure_filename(
                    archivo.filename
                )

                carpetaUploads = os.path.join(
                    "app",
                    "static",
                    "uploads",
                    "sucursales"
                )
                os.makedirs(
                    carpetaUploads,
                    exist_ok=True
                )

                rutaCompleta = os.path.join(
                    carpetaUploads,
                    nombreSeguro
                )
                
                archivo.save(rutaCompleta)
                rutaImagen = (
                    f"/static/uploads/sucursales/{nombreSeguro}"
                )

            nuevaSucursal = Sucursal(
                nombre=nombreSucursal,
                foto=rutaImagen,
                ciudad=form.ciudad.data.strip(),
                calle=form.calle.data.strip(),
                colonia=form.colonia.data.strip(),
                numInt=form.numInt.data.strip(),
                cp=form.cp.data.strip(),
                estatus=True
            )
            db.session.add(nuevaSucursal)
            db.session.commit()

            flash(
                "Sucursal registrada correctamente.",
                "success"
            )

            return redirect(
                url_for("sucursales.index")
            )

        except Exception as e:
            db.session.rollback()
            print(e)
            flash(
                "Error al registrar la sucursal.",
                "danger"
            )

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(
                    erroresCampo[0],
                    "danger"
                )
                break


    return render_template(
        "sucursales/nueva_sucursal.html",
        form=form,
        active_page="sucursales"
    )

@sucursalesBp.route("/<int:id>/editar", methods=["GET"], endpoint="editar")
def editar(id):

    sucursal = Sucursal.query.get_or_404(id)

    form = SucursalForm(obj=sucursal)

    return render_template(
        "sucursales/editar_sucursal.html",
        sucursal=sucursal,
        form=form,
        active_page="sucursales"
    )


@sucursalesBp.route("/<int:id>/actualizar", methods=["POST"], endpoint="actualizar")
def actualizar(id):

    sucursal = Sucursal.query.get_or_404(id)

    form = SucursalForm()

    if not form.validate_on_submit():

        for erroresCampo in form.errors.values():

            if erroresCampo:

                flash(
                    erroresCampo[0],
                    "danger"
                )

                break

        return render_template(
            "sucursales/editar_sucursal.html",
            sucursal=sucursal,
            form=form
        )

    sucursalRepetida = Sucursal.query.filter(
        Sucursal.nombre == form.nombre.data.strip(),
        Sucursal.idSucursal != id
    ).first()

    if sucursalRepetida:

        flash(
            "Ya existe otra sucursal con ese nombre.",
            "danger"
        )

        return render_template(
            "sucursales/editar_sucursal.html",
            sucursal=sucursal,
            form=form
        )

    sucursal.nombre = form.nombre.data.strip()
    sucursal.foto = form.foto.data
    sucursal.ciudad = form.ciudad.data.strip()
    sucursal.calle = form.calle.data.strip()
    sucursal.colonia = form.colonia.data.strip()
    sucursal.numInt = form.numInt.data.strip()
    sucursal.cp = form.cp.data.strip()

    db.session.commit()

    flash(
        "Sucursal actualizada correctamente.",
        "success"
    )

    return redirect(
        url_for("sucursales.index")
    )


@sucursalesBp.route("/<int:id>/desactivar", methods=["POST"], endpoint="desactivar")
def desactivar(id):

    sucursal = Sucursal.query.get_or_404(id)

    form = DesactivarForm()

    if form.validate_on_submit():

        sucursal.estatus = False

        db.session.commit()

        flash(
            "Sucursal desactivada correctamente.",
            "success"
        )

    return redirect(
        url_for("sucursales.index")
    )

@sucursalesBp.route("/<int:id>/reactivar", methods=["POST"], endpoint="reactivar")
def reactivar(id):

    sucursal = Sucursal.query.get_or_404(id)

    form = DesactivarForm()

    if form.validate_on_submit():

        sucursal.estatus = True

        db.session.commit()

        flash(
            "Sucursal reactivada correctamente.",
            "success"
        )

    return redirect(
        url_for("sucursales.index")
    )