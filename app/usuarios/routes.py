from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_

from forms import  CrearEmpleadoForm, EmpleadoActualizarForm, DesactivarForm
from model import Rol, Usuario, Empleado, db

usuariosBp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


def hayOtroGerenteActivo(idUsuarioActual: int) -> bool:
    return (
        Usuario.query.join(Rol, Usuario.rolId == Rol.id)
        .filter(
            Usuario.id != idUsuarioActual,
            Rol.nombre == "Gerente",
            Usuario.estado == "Activo",
        )
        .first()
        is not None
    )


def requiereRol(rolRequerido: str):
    def decorador(funcionVista):
        @wraps(funcionVista)
        def envuelta(*args, **kwargs):
            if not session.get("inicioSesion"):
                return redirect(url_for("auth.iniciarSesion"))

            if session.get("usuarioRol") != rolRequerido:
                flash("No tienes permisos para acceder a este módulo.", "danger")
                return redirect(url_for("dashboard_operador"))

            return funcionVista(*args, **kwargs)

        return envuelta

    return decorador


@usuariosBp.route("/", methods=["GET"], endpoint="index")
@requiereRol("Gerente")
def index():
    
    form = DesactivarForm()
    terminoBusqueda = request.args.get("q", "").strip()
    estado = request.args.get('estado', 'activos')

    consultaUsuarios = Usuario.query.join(Rol, Usuario.rolId == Rol.id)\
                                 .join(Empleado, Usuario.id == Empleado.usuarioId)\
                                 .filter(
    Rol.nombre.in_(["Operador", "Gerente"])
)
    if terminoBusqueda:
        patronBusqueda = f"%{terminoBusqueda}%"
        consultaUsuarios = consultaUsuarios.filter(
            or_(
                Empleado.username.ilike(patronBusqueda),
                Usuario.correo.ilike(patronBusqueda),
                Rol.nombre.ilike(patronBusqueda),
                Usuario.estado.ilike(patronBusqueda),
            )
        )

    if estado == 'todos':
        listaUsuarios = consultaUsuarios.order_by(Empleado.username).all()
    elif estado == 'inactivos':
        listaUsuarios = consultaUsuarios.filter(Usuario.estado == 'Inactivo').order_by(Empleado.username).all()
    else:
        listaUsuarios = consultaUsuarios.filter(Usuario.estado == 'Activo').order_by(Empleado.username).all()

    return render_template(
        "usuarios/usuarios.html",
        usuarios=listaUsuarios,
        terminoBusqueda=terminoBusqueda,
        active_page = 'usuarios',
        form = form,
        estado=estado
    )


@usuariosBp.route("/nuevo", methods=["GET"], endpoint="nuevo")
@requiereRol("Gerente")
def nuevo():
    form = CrearEmpleadoForm()
    return render_template("usuarios/nuevo_usuario.html", active_page = 'usuarios', form=form)


@usuariosBp.route("/crear", methods=["GET", "POST"], endpoint="crear")
@requiereRol("Gerente")
def crear():
    form = CrearEmpleadoForm()

    if form.validate_on_submit():
        try:
            correo = form.correo.data.strip().lower()
            username = form.username.data.strip().lower()
            nombre = form.nombre.data.strip()
            rol = form.rol.data.strip()
            contrasena = form.contrasenaTemporal.data

            rolRegistro = Rol.query.filter_by(nombre=rol).first()
            if not rolRegistro:
                flash("El rol seleccionado no existe.", "danger")
                return render_template("usuarios/nuevo_usuario.html", form=form)

            if Usuario.query.filter_by(correo=correo).first():
                flash("El correo ya está registrado.", "danger")
                return render_template("usuarios/nuevo_usuario.html", form=form)
            
            if Empleado.query.filter_by(username=username).first():
                flash("El usuario ya está registrado.", "danger")
                return render_template("usuarios/nuevo_usuario.html", form=form)

            usuario = Usuario(
                correo=correo,
                rolId=rolRegistro.id,
                estado="Activo"
            )

            usuario.establecerContrasena(contrasena)
            usuario.resetearSeguridad()

            db.session.add(usuario)
            db.session.flush() 

            empleado = Empleado(
                usuarioId=usuario.id,
                username=username,
                nombre=nombre
            )

            db.session.add(empleado)
            db.session.commit()

            flash("Empleado creado correctamente.", "success")
            return redirect(url_for("usuarios.index"))

        except Exception as e:
            db.session.rollback()
            flash("Error al crear el empleado.", "danger")
            print(e)

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template("usuarios/nuevo_usuario.html", active_page='usuarios', form=form)

@usuariosBp.route("/<int:idUsuario>/editar", methods=["GET"], endpoint="editar")
@requiereRol("Gerente")
def editar(idUsuario: int):
    usuario = Usuario.query.get_or_404(idUsuario)
    form = EmpleadoActualizarForm(obj=usuario)
    return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)


@usuariosBp.route("/<int:idUsuario>/actualizar", methods=["POST"], endpoint="actualizar")
@requiereRol("Gerente")
def actualizar(idUsuario: int):
    
    usuario = Usuario.query.get_or_404(idUsuario)
    form = EmpleadoActualizarForm()

    if not form.validate_on_submit():
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    correo = form.correo.data.strip().lower()
    username = form.username.data.strip().lower()
    nombre = form.nombre.data.strip()
    rol = form.rol.data.strip()
    contrasenaTemporal = (form.contrasenaTemporal.data or "")

    rolRegistro = Rol.query.filter_by(nombre=rol).first()
    if not rolRegistro:
        flash("El rol seleccionado no existe.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    correoRepetido = Usuario.query.filter(
        Usuario.correo == correo,
        Usuario.id != idUsuario
    ).first()

    if correoRepetido:
        flash("El correo ya está registrado por otro usuario.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    usuarioRepetido = Empleado.query.filter(
        Empleado.username == username,
        Empleado.usuarioId != idUsuario
    ).first()

    if usuarioRepetido:
        flash("El usuario ya está registrado por otra cuenta.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    usuario.correo = correo
    usuario.rolId = rolRegistro.id

    if contrasenaTemporal:
        usuario.establecerContrasena(contrasenaTemporal)
        usuario.resetearSeguridad()


    if usuario.empleado:
        usuario.empleado.username = username
        usuario.empleado.nombre = nombre

    db.session.commit()

    flash("Usuario actualizado correctamente.", "success")
    return redirect(url_for("usuarios.index"))


@usuariosBp.route("/<int:idUsuario>/desactivar", methods=["POST"], endpoint="desactivar")
@requiereRol("Gerente")
def desactivar(idUsuario: int):
    usuario = Usuario.query.get_or_404(idUsuario)
    form = DesactivarForm()

    if usuario.id == session.get("usuarioId"):
        flash("No puedes desactivar tu propia cuenta.", "danger")
        return redirect(url_for("usuarios.index"))

    if usuario.rol == "Gerente" and not hayOtroGerenteActivo(idUsuario):
        flash("Debe existir al menos un Gerente activo en el sistema.", "danger")
        return redirect(url_for("usuarios.index"))

    if form.validate_on_submit():
        usuario.estado = "Inactivo"
        usuario.resetearSeguridad()
        db.session.commit()
        flash("Usuario desactivado correctamente.", "success")
    
    return redirect(url_for("usuarios.index"))

@usuariosBp.route("/<int:idUsuario>/reactivar", methods=["POST"] )
@requiereRol("Gerente")
def reactivar(idUsuario: int):
    usuario = Usuario.query.get_or_404(idUsuario)
    form = DesactivarForm()

    if form.validate_on_submit():
        usuario.estado = "Activo"
        db.session.commit()
        flash("Usuario reactivado correctamente.", "success")
        
    return redirect(url_for("usuarios.index"))