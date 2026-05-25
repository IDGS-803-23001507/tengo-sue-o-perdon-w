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

from forms import ComboForm, DesactivarForm
from model import (
    Productoo,
    Combo,
    DetalleCombo,
    TipoProducto,
    db
)

combosBp = Blueprint(
    "combos",
    __name__,
    url_prefix="/combos"
)

def requiereRol(rolRequerido: str):

    def decorador(funcionVista):

        @wraps(funcionVista)
        def envuelta(*args, **kwargs):

            from flask import session

            if not session.get("inicioSesion"):
                return redirect(
                    url_for("auth.iniciarSesion")
                )

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

                return redirect(
                    url_for("dashboard_operador")
                )

            return funcionVista(*args, **kwargs)

        return envuelta

    return decorador

@combosBp.route("/", methods=["GET"], endpoint="index")
@requiereRol("Gerente")
def index():

    form = DesactivarForm()

    terminoBusqueda = request.args.get(
        "q",
        ""
    ).strip()

    estado = request.args.get(
        "estado",
        "activos"
    )


    consulta = Productoo.query.filter(
        Productoo.tipo == TipoProducto.COMBO
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

        combos = consulta.order_by(
            Productoo.nombre
        ).all()

    elif estado == "inactivos":

        combos = consulta.filter(
            Productoo.estatus == False
        ).order_by(
            Productoo.nombre
        ).all()

    else:

        combos = consulta.filter(
            Productoo.estatus == True
        ).order_by(
            Productoo.nombre
        ).all()

    return render_template(
        "combos/combos.html",
        combos=combos,
        terminoBusqueda=terminoBusqueda,
        estado=estado,
        active_page="combos",
        form=form
    )

@combosBp.route(
    "/nuevo",
    methods=["GET"],
    endpoint="nuevo"
)
@requiereRol("Gerente")
def nuevo():

    form = ComboForm()

    productos = Productoo.query.filter(
        Productoo.tipo.in_([
            TipoProducto.ALIMENTO,
            TipoProducto.BEBIDA
        ]),
        Productoo.estatus == True
    ).all()

    return render_template(
        "combos/nuevo_combo.html",
        form=form,
        productos=productos,
        active_page="combos"
    )

@combosBp.route(
    "/crear",
    methods=["GET", "POST"],
    endpoint="crear"
)
@requiereRol("Gerente")
def crear():

    form = ComboForm()

    productos = Productoo.query.filter(
        Productoo.tipo.in_([
            TipoProducto.ALIMENTO,
            TipoProducto.BEBIDA
        ]),
        Productoo.estatus == True
    ).all()

    if form.validate_on_submit():

        try:

            nombre = form.nombre.data.strip()
            comboExistente = Productoo.query.filter_by(
                nombre=nombre
            ).first()

            if comboExistente:

                flash(
                    "Ya existe un combo con ese nombre.",
                    "danger"
                )

                return render_template(
                    "combos/nuevo_combo.html",
                    form=form,
                    productos=productos
                )

            rutaImagen = None

            if form.foto.data:

                archivo = form.foto.data

                nombreSeguro = secure_filename(
                    archivo.filename
                )

                extension = os.path.splitext(
                    nombreSeguro
                )[1]

                nombreFinal = (
                    f"{uuid4().hex}{extension}"
                )

                carpetaUploads = os.path.join(
                    current_app.root_path,
                    "static/uploads/combos"
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

                rutaImagen = (
                    f"/static/uploads/combos/{nombreFinal}"
                )

            producto = Productoo(
                nombre=nombre,
                descripcion=form.descripcion.data.strip(),
                foto=rutaImagen,
                precio=form.precio.data,
                tipo=TipoProducto.COMBO,
                estatus=1
            )

            db.session.add(producto)
            db.session.flush()

            combo = Combo(
                idProducto=producto.idProducto
            )

            db.session.add(combo)
            db.session.flush()

            idsProductos = request.form.getlist(
                "idProducto[]"
            )

            cantidades = request.form.getlist(
                "cantidad[]"
            )

            for idProducto, cantidad in zip(
                idsProductos,
                cantidades
            ):

                detalle = DetalleCombo(
                    idCombo=combo.idCombo,
                    idProducto=int(idProducto),
                    cantidad=int(cantidad)
                )
                
                db.session.add(detalle)
            db.session.commit()
            flash("Combo creado correctamente.",
                "success")
            return redirect(
                url_for("combos.index")
            )
        except Exception as e:
            db.session.rollback()
            flash(
                "Error al crear el combo.",
                "danger"
            )
            print(e)
    return render_template(
        "combos/nuevo_combo.html",
        form=form,
        productos=productos,
        active_page="combos"
    )
    
@combosBp.route(
    "/<int:idProducto>/editar",
    methods=["GET"],
    endpoint="editar"
)
@requiereRol("Gerente")
def editar(idProducto):

    comboProducto = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.COMBO
    ).first_or_404()

    combo = Combo.query.filter_by(
        idProducto=idProducto
    ).first()

    detalles = DetalleCombo.query.filter_by(
        idCombo=combo.idCombo
    ).all()

    productos = Productoo.query.filter(
        Productoo.tipo.in_([
            TipoProducto.ALIMENTO,
            TipoProducto.BEBIDA
        ]),
        Productoo.estatus == True
    ).all()

    form = ComboForm(obj=comboProducto)

    return render_template(
        "combos/editar_combo.html",
        form=form,
        combo=comboProducto,
        detalles=detalles,
        productos=productos,
        active_page="combos"
    )

@combosBp.route(
    "/<int:idProducto>/actualizar",
    methods=["POST"],
    endpoint="actualizar"
)
@requiereRol("Gerente")
def actualizar(idProducto):

    comboProducto = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.COMBO
    ).first_or_404()

    combo = Combo.query.filter_by(
        idProducto=idProducto
    ).first()

    productos = Productoo.query.filter(
        Productoo.tipo.in_([
            TipoProducto.ALIMENTO,
            TipoProducto.BEBIDA
        ]),
        Productoo.estatus == True
    ).all()
    form = ComboForm()
    if form.validate_on_submit():

        try:

            comboProducto.nombre = (
                form.nombre.data.strip()
            )

            comboProducto.descripcion = (
                form.descripcion.data.strip()
            )

            comboProducto.precio = (
                form.precio.data
            )

            comboProducto.estatus = (
                1
            )

            if form.foto.data:

                archivo = form.foto.data

                nombreSeguro = secure_filename(
                    archivo.filename
                )

                extension = os.path.splitext(
                    nombreSeguro
                )[1]

                nombreFinal = (
                    f"{uuid4().hex}{extension}"
                )

                carpetaUploads = os.path.join(
                    current_app.root_path,
                    "static/uploads/combos"
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
                comboProducto.foto = (
                    f"/static/uploads/combos/{nombreFinal}"
                )

            DetalleCombo.query.filter_by(
                idCombo=combo.idCombo
            ).delete()

            idsProductos = request.form.getlist(
                "idProducto[]"
            )

            cantidades = request.form.getlist(
                "cantidad[]"
            )

            for idProd, cantidad in zip(
                idsProductos,
                cantidades
            ):

                detalle = DetalleCombo(
                    idCombo=combo.idCombo,
                    idProducto=int(idProd),
                    cantidad=int(cantidad)
                )

                db.session.add(detalle)
            db.session.commit()

            flash(
                "Combo actualizado correctamente.",
                "success"
            )

            return redirect(
                url_for("combos.index")
            )

        except Exception as e:
            db.session.rollback()
            flash(
                "Error al actualizar el combo.",
                "danger"
            )
            print(e)

    detalles = DetalleCombo.query.filter_by(
        idCombo=combo.idCombo
    ).all()

    return render_template(
        "combos/editar_combo.html",
        form=form,
        combo=comboProducto,
        detalles=detalles,
        productos=productos,
        active_page="combos"
    )

@combosBp.route("/<int:idProducto>/desactivar", methods=["POST"], endpoint="desactivar")
@requiereRol("Gerente")
def desactivar(idProducto):
    combo = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.COMBO
    ).first_or_404()

    form = DesactivarForm()

    if form.validate_on_submit():
        combo.estatus = False
        db.session.commit()

        flash("Combo desactivado correctamente.", "success")

    return redirect(
        url_for("combos.index")
    )

@combosBp.route( "/<int:idProducto>/reactivar", methods=["POST"], endpoint="reactivar")
@requiereRol("Gerente")
def reactivar(idProducto):
    combo = Productoo.query.filter(
        Productoo.idProducto == idProducto,
        Productoo.tipo == TipoProducto.COMBO
    ).first_or_404()

    form = DesactivarForm()
    if form.validate_on_submit():
        combo.estatus = True
        db.session.commit()
        flash(
            "Combo reactivado correctamente.",
            "success"
        )

    return redirect(
        url_for("combos.index")
    )