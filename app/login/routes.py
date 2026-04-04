from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib
import ssl
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from forms import LoginForm, RecuperarContrasenaForm, RegistroUsuarioForm, ResetearContrasenaForm
from model import RegistroSesion, Rol, Usuario, db

authBp = Blueprint("auth", __name__)

hashContrasenaSimulada = generate_password_hash("urban-coffee-dummy-password")


def serializadorRecuperacion() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def enviarCorreoRecuperacion(destinatario: str, enlace: str) -> None:
    smtpHost = current_app.config.get("SMTP_HOST", "")
    smtpPort = int(current_app.config.get("SMTP_PORT", 587))
    smtpUser = current_app.config.get("SMTP_USER", "")
    smtpPassword = current_app.config.get("SMTP_PASSWORD", "")
    smtpFrom = current_app.config.get("SMTP_FROM", "")
    usarTls = bool(current_app.config.get("SMTP_USE_TLS", True))
    usarSsl = bool(current_app.config.get("SMTP_USE_SSL", False))

    if not smtpHost or not smtpFrom:
        raise RuntimeError("Configuración SMTP incompleta: define SMTP_HOST y SMTP_FROM")

    mensaje = EmailMessage()
    mensaje["Subject"] = "Urban Coffee - Recuperación de contraseña"
    mensaje["From"] = smtpFrom
    mensaje["To"] = destinatario
    mensaje.set_content(
        (
            "Hola,\n\n"
            "Recibimos una solicitud para restablecer tu contraseña en Urban Coffee.\n"
            "Usa el siguiente enlace (válido por 30 minutos):\n\n"
            f"{enlace}\n\n"
            "Si no solicitaste este cambio, puedes ignorar este correo.\n"
        )
    )

    contextoSsl = ssl.create_default_context()

    if usarSsl:
        with smtplib.SMTP_SSL(smtpHost, smtpPort, timeout=15, context=contextoSsl) as servidor:
            if smtpUser and smtpPassword:
                servidor.login(smtpUser, smtpPassword)
            servidor.send_message(mensaje)
        return

    with smtplib.SMTP(smtpHost, smtpPort, timeout=15) as servidor:
        if usarTls:
            servidor.starttls(context=contextoSsl)
        if smtpUser and smtpPassword:
            servidor.login(smtpUser, smtpPassword)
        servidor.send_message(mensaje)


def usuarioAutenticado() -> bool:
    return bool(session.get("inicioSesion") and session.get("usuarioId"))


def endpointDashboardRol(rol: str) -> str:
    mapaRoles = {
        "Gerente": "dashboard_gerente",
        "Operador": "dashboard_operador",
        "Cliente": "ventas.tienda_cliente",
    }
    return mapaRoles.get(rol, "dashboard_operador")


@authBp.route("/login", methods=["GET", "POST"], endpoint="iniciarSesion")
def iniciarSesion():
    form = LoginForm()
    if form.validate_on_submit():
        identificador = form.correo.data.strip().lower()
        contrasena = form.contrasena.data

        errorGenerico = "Usuario o contraseña incorrectos"
        usuario = Usuario.query.filter(
            (Usuario.correo == identificador) | (Usuario.usuario == identificador)
        ).first()

        if not usuario:
            check_password_hash(hashContrasenaSimulada, contrasena)
            flash(errorGenerico, "danger")
            return render_template("login/login.html", form=form)

        if usuario.estado != "Activo":
            check_password_hash(hashContrasenaSimulada, contrasena)
            flash(errorGenerico, "danger")
            return render_template("login/login.html", form=form)

        if usuario.estaBloqueada():
            db.session.commit()
            flash("Cuenta bloqueada temporalmente.", "warning")
            return render_template("login/login.html", form=form)

        if not usuario.validarContrasena(contrasena):
            usuario.registrarIntentoFallido(maxIntentos=3, minutosBloqueo=15)
            db.session.commit()

            if usuario.cuentaBloqueada:
                flash("Cuenta bloqueada temporalmente por múltiples intentos fallidos.", "warning")
            else:
                flash(errorGenerico, "danger")

            return render_template("login/login.html", form=form)

        usuario.resetearSeguridad()

        tokenSesion = str(uuid4())
        registroSesion = RegistroSesion(
            usuarioId=usuario.id,
            tokenSesion=tokenSesion,
            direccionIp=request.headers.get("X-Forwarded-For", request.remote_addr),
            agenteUsuario=(request.user_agent.string or "")[:255],
        )
        db.session.add(registroSesion)
        db.session.commit()

        session.clear()
        session.permanent = True
        session["inicioSesion"] = True
        session["usuarioId"] = usuario.id
        session["usuarioNombre"] = usuario.nombre
        session["usuarioCorreo"] = usuario.correo
        session["usuarioLogin"] = usuario.usuario
        session["usuarioRol"] = usuario.rol
        session["registroSesionId"] = registroSesion.id
        session["tokenSesion"] = tokenSesion

        return redirect(url_for(endpointDashboardRol(usuario.rol)))

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template("login/login.html", form=form)


@authBp.route("/register", methods=["GET", "POST"], endpoint="registrarUsuario")
def registrarUsuario():
    form = RegistroUsuarioForm()
    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        correo = form.correo.data.strip().lower()
        contrasena = form.contrasena.data

        existe = Usuario.query.filter_by(correo=correo).first()
        if existe:
            flash("El correo ya está registrado.", "danger")
            return render_template("login/registrar_cliente.html", form=form)

        usuarioSugerido = correo.split("@")[0]
        consecutivo = 0
        usuarioGenerado = usuarioSugerido
        while Usuario.query.filter_by(usuario=usuarioGenerado).first():
            consecutivo += 1
            usuarioGenerado = f"{usuarioSugerido}{consecutivo}"

        rolCliente = Rol.query.filter_by(nombre="Cliente").first()
        if not rolCliente:
            flash("No existe el rol Cliente. Contacta al administrador.", "danger")
            return render_template("login/registrar_cliente.html", form=form)

        usuario = Usuario(nombre=nombre, usuario=usuarioGenerado, correo=correo, rolId=rolCliente.id, estado="Activo")
        usuario.establecerContrasena(contrasena)
        usuario.resetearSeguridad()

        db.session.add(usuario)
        db.session.commit()

        flash("Registro completado. Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("auth.iniciarSesion"))

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template("login/registrar_cliente.html", form=form)


@authBp.route("/forgot-password", methods=["GET", "POST"], endpoint="recuperarContrasena")
def recuperarContrasena():
    form = RecuperarContrasenaForm()
    if request.method == "GET":
        return render_template("login/forgot_password.html", form=form)

    if not form.validate_on_submit():
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break
        return render_template("login/forgot_password.html", form=form)

    correo = form.correo.data.strip().lower()

    usuario = Usuario.query.filter_by(correo=correo).first()

    if usuario:
        token = serializadorRecuperacion().dumps({"uid": usuario.id})
        enlace = url_for("auth.resetearContrasena", token=token, _external=True)

        try:
            enviarCorreoRecuperacion(destinatario=usuario.correo, enlace=enlace)
        except Exception as exc:
            current_app.logger.exception("Error al enviar correo de recuperación: %s", exc)
            if current_app.debug:
                flash("SMTP no disponible. Enlace temporal (solo desarrollo):", "warning")
                flash(enlace, "info")
                return render_template("login/forgot_password.html", form=form)

            flash("No se pudo enviar el correo de recuperación en este momento.", "danger")
            return render_template("login/forgot_password.html", form=form)

    flash("Si el correo existe, recibirás instrucciones para recuperar tu contraseña.", "info")
    return render_template("login/forgot_password.html", form=form)


@authBp.route("/reset-password/<token>", methods=["GET", "POST"], endpoint="resetearContrasena")
def resetearContrasena(token: str):
    form = ResetearContrasenaForm()

    try:
        datos = serializadorRecuperacion().loads(token, max_age=1800)
    except SignatureExpired:
        flash("El enlace expiró. Solicita uno nuevo.", "danger")
        return redirect(url_for("auth.recuperarContrasena"))
    except BadSignature:
        flash("El enlace no es válido.", "danger")
        return redirect(url_for("auth.recuperarContrasena"))

    usuario = Usuario.query.get(datos.get("uid"))
    if not usuario:
        flash("No se encontró la cuenta para restablecer.", "danger")
        return redirect(url_for("auth.recuperarContrasena"))

    if request.method == "GET":
        return render_template("login/reset_password.html", form=form)

    if not form.validate_on_submit():
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break
        return render_template("login/reset_password.html", form=form)

    nuevaContrasena = form.contrasena.data

    usuario.establecerContrasena(nuevaContrasena)
    usuario.resetearSeguridad()
    db.session.commit()

    flash("Contraseña actualizada correctamente. Inicia sesión.", "success")
    return redirect(url_for("auth.iniciarSesion"))


@authBp.route("/logout", endpoint="cerrarSesion")
def cerrarSesion():
    registroSesionId = session.get("registroSesionId")
    tokenSesion = session.get("tokenSesion")

    if registroSesionId and tokenSesion:
        registroSesion = RegistroSesion.query.filter_by(id=registroSesionId, tokenSesion=tokenSesion, activa=True).first()
        if registroSesion:
            registroSesion.activa = False
            registroSesion.fechaFin = datetime.now(timezone.utc)
            db.session.commit()

    session.clear()
    return redirect(url_for("auth.iniciarSesion"))