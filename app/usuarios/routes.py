from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_

from forms import UsuarioActualizarForm, UsuarioCrearForm
from model import Rol, Usuario, db

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
    terminoBusqueda = request.args.get("q", "").strip()

    consultaUsuarios = Usuario.query.join(Rol, Usuario.rolId == Rol.id)
    if terminoBusqueda:
        patronBusqueda = f"%{terminoBusqueda}%"
        consultaUsuarios = consultaUsuarios.filter(
            or_(
                Usuario.nombre.ilike(patronBusqueda),
                Usuario.usuario.ilike(patronBusqueda),
                Usuario.correo.ilike(patronBusqueda),
                Rol.nombre.ilike(patronBusqueda),
                Usuario.estado.ilike(patronBusqueda),
            )
        )

    listaUsuarios = consultaUsuarios.order_by(Usuario.creadoEn.desc()).all()
    return render_template(
        "usuarios/usuarios.html",
        usuarios=listaUsuarios,
        terminoBusqueda=terminoBusqueda,
    )


@usuariosBp.route("/nuevo", methods=["GET"], endpoint="nuevo")
@requiereRol("Gerente")
def nuevo():
    form = UsuarioCrearForm()
    return render_template("usuarios/nuevo_usuario.html", form=form)


@usuariosBp.route("/crear", methods=["POST"], endpoint="crear")
@requiereRol("Gerente")
def crear():
    form = UsuarioCrearForm()
    if not form.validate_on_submit():
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break
        return render_template("usuarios/nuevo_usuario.html", form=form)

    nombre = form.nombre.data.strip()
    usuarioLogin = form.usuario.data.strip().lower()
    correo = form.correo.data.strip().lower()
    rol = form.rol.data.strip()
    contrasenaTemporal = form.contrasenaTemporal.data
    estado = form.estado.data.strip()
    rolRegistro = Rol.query.filter_by(nombre=rol).first()

    if not rolRegistro:
        flash("El rol seleccionado no existe.", "danger")
        return render_template("usuarios/nuevo_usuario.html", form=form)

    existeUsuario = Usuario.query.filter_by(usuario=usuarioLogin).first()
    if existeUsuario:
        flash("El usuario ya está registrado.", "danger")
        return render_template("usuarios/nuevo_usuario.html", form=form)

    existe = Usuario.query.filter_by(correo=correo).first()
    if existe:
        flash("El correo ya está registrado.", "danger")
        return render_template("usuarios/nuevo_usuario.html", form=form)

    usuario = Usuario(nombre=nombre, usuario=usuarioLogin, correo=correo, rolId=rolRegistro.id, estado=estado)

    usuario.establecerContrasena(contrasenaTemporal)
    usuario.resetearSeguridad()

    db.session.add(usuario)
    db.session.commit()

    flash("Usuario creado correctamente.", "success")
    return redirect(url_for("usuarios.index"))


@usuariosBp.route("/<int:idUsuario>/editar", methods=["GET"], endpoint="editar")
@requiereRol("Gerente")
def editar(idUsuario: int):
    usuario = Usuario.query.get_or_404(idUsuario)
    form = UsuarioActualizarForm(obj=usuario)
    return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)


@usuariosBp.route("/<int:idUsuario>/actualizar", methods=["POST"], endpoint="actualizar")
@requiereRol("Gerente")
def actualizar(idUsuario: int):
    usuario = Usuario.query.get_or_404(idUsuario)

    form = UsuarioActualizarForm()
    if not form.validate_on_submit():
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    nombre = form.nombre.data.strip()
    usuarioLogin = form.usuario.data.strip().lower()
    correo = form.correo.data.strip().lower()
    rol = form.rol.data.strip()
    estado = form.estado.data.strip()
    contrasenaTemporal = (form.contrasenaTemporal.data or "")
    rolRegistro = Rol.query.filter_by(nombre=rol).first()

    if not rolRegistro:
        flash("El rol seleccionado no existe.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    usuarioRepetido = Usuario.query.filter(Usuario.usuario == usuarioLogin, Usuario.id != idUsuario).first()
    if usuarioRepetido:
        flash("El usuario ya está registrado por otra cuenta.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    correoRepetido = Usuario.query.filter(Usuario.correo == correo, Usuario.id != idUsuario).first()
    if correoRepetido:
        flash("El correo ya está registrado por otro usuario.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    perderaPrivilegiosGerente = usuario.rol == "Gerente" and (rol != "Gerente" or estado != "Activo")
    if perderaPrivilegiosGerente and not hayOtroGerenteActivo(idUsuario):
        flash("Debe existir al menos un Gerente activo en el sistema.", "danger")
        return render_template("usuarios/editar_usuario.html", usuario=usuario, form=form)

    usuario.nombre = nombre
    usuario.usuario = usuarioLogin
    usuario.correo = correo
    usuario.rolId = rolRegistro.id
    usuario.estado = estado

    if contrasenaTemporal:
        usuario.establecerContrasena(contrasenaTemporal)
        usuario.resetearSeguridad()

    db.session.commit()
    flash("Usuario actualizado correctamente.", "success")
    return redirect(url_for("usuarios.index"))


@usuariosBp.route("/<int:idUsuario>/desactivar", methods=["POST"], endpoint="desactivar")
@requiereRol("Gerente")
def desactivar(idUsuario: int):
    usuario = Usuario.query.get_or_404(idUsuario)

    if usuario.id == session.get("usuarioId"):
        flash("No puedes desactivar tu propia cuenta.", "danger")
        return redirect(url_for("usuarios.index"))

    if usuario.rol == "Gerente" and not hayOtroGerenteActivo(idUsuario):
        flash("Debe existir al menos un Gerente activo en el sistema.", "danger")
        return redirect(url_for("usuarios.index"))

    usuario.estado = "Inactivo"
    usuario.resetearSeguridad()
    db.session.commit()

    flash("Usuario desactivado correctamente.", "success")
    return redirect(url_for("usuarios.index"))