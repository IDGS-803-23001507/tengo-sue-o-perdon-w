from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib
import ssl
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from forms import LoginForm, RecuperarContrasenaForm, ClienteForm, ResetearContrasenaForm
from app.auditoria import registrar_auditoria
from model import RegistroSesion, Rol, Usuario, Cliente, Empleado, db

import random
from datetime import timedelta

authBp = Blueprint("auth", __name__)

hashContrasenaSimulada = generate_password_hash("urban-coffee-dummy-password")

codigos_verificacion = {}

def generar_codigo():
    return str(random.randint(100000, 999999))

def generar_codigo_con_expiracion():
    codigo = generar_codigo()
    expira = datetime.now() + timedelta(minutes=5)
    return codigo, expira

def enviar_codigo_verificacion(destinatario: str, codigo: str):
    smtpHost = current_app.config.get("SMTP_HOST", "")
    smtpPort = int(current_app.config.get("SMTP_PORT", 587))
    smtpUser = current_app.config.get("SMTP_USER", "")
    smtpPassword = current_app.config.get("SMTP_PASSWORD", "")
    smtpFrom = current_app.config.get("SMTP_FROM", "")

    mensaje = EmailMessage()
    mensaje["Subject"] = "Código de verificación - Urban Coffee"
    mensaje["From"] = smtpFrom
    mensaje["To"] = destinatario
    mensaje.set_content(f"Tu código de verificación es: {codigo}")

    contexto = ssl.create_default_context()

    with smtplib.SMTP(smtpHost, smtpPort) as servidor:
        servidor.starttls(context=contexto)
        if smtpUser and smtpPassword:
            servidor.login(smtpUser, smtpPassword)
        servidor.send_message(mensaje)

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
        "Admin General (TI)": "dashboard_gerente",
        "Admin General": "dashboard_gerente",
        "Gerente de Tienda": "dashboard_gerente",
        "Gerente": "dashboard_gerente",
        "Cajero": "ventas.tienda_cliente",
        "Barista": "solicitud.index",
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
        
        usuario = Usuario.query.outerjoin(Empleado).filter(
        (Usuario.correo == identificador) | (Empleado.username == identificador)
        ).first()

        if not usuario:
            check_password_hash(hashContrasenaSimulada, contrasena)
            registrar_auditoria(
                accion="Login Fallido",
                modulo="Autenticación",
                detalles={"motivo": "usuario_no_encontrado", "identificador": identificador},
                usuario_id=None,
                commit=True,
            )
            flash(errorGenerico, "danger")
            return render_template("login/login.html", form=form)

        if usuario.estado != "Activo":
            check_password_hash(hashContrasenaSimulada, contrasena)
            registrar_auditoria(
                accion="Login Fallido",
                modulo="Autenticación",
                detalles={"motivo": "usuario_inactivo"},
                usuario_id=usuario.id,
                commit=True,
            )
            flash(errorGenerico, "danger")
            return render_template("login/login.html", form=form)

        if usuario.estaBloqueada():
            registrar_auditoria(
                accion="Login Fallido",
                modulo="Autenticación",
                detalles={"motivo": "cuenta_bloqueada"},
                usuario_id=usuario.id,
                commit=False,
            )
            db.session.commit()
            flash("Cuenta bloqueada temporalmente.", "warning")
            return render_template("login/login.html", form=form)

        if not usuario.validarContrasena(contrasena):
            usuario.registrarIntentoFallido(maxIntentos=3, minutosBloqueo=15)

            motivo = "credenciales_invalidas"
            if usuario.cuentaBloqueada:
                motivo = "cuenta_bloqueada_por_intentos"
                registrar_auditoria(
                    accion="Cuenta Bloqueada",
                    modulo="Usuarios",
                    detalles={"motivo": "intentos_fallidos", "intentos": usuario.intentosFallidos},
                    usuario_id=usuario.id,
                    commit=False,
                )

            registrar_auditoria(
                accion="Login Fallido",
                modulo="Autenticación",
                detalles={"motivo": motivo, "intentos": usuario.intentosFallidos},
                usuario_id=usuario.id,
                commit=False,
            )

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

        registrar_auditoria(
            accion="Login Exitoso",
            modulo="Autenticación",
            detalles={"motivo": "credenciales_validas"},
            usuario_id=usuario.id,
            commit=False,
        )
        db.session.commit()

        session.clear()
        session.permanent = True
        session["inicioSesion"] = True
        session["usuarioId"] = usuario.id

        rolNombre = usuario.rol
        if rolNombre == "Cliente":
            clienteRegistro = usuario.cliente or Cliente.query.filter_by(usuarioId=usuario.id).first()
            if not clienteRegistro:
                nombreBase = (usuario.correo or "Cliente").split("@")[0].strip() or "Cliente"
                clienteRegistro = Cliente(
                    usuarioId=usuario.id,
                    nombre=nombreBase,
                    apellidoPaterno="Pendiente",
                    apellidoMaterno="",
                    telefono="",
                    alias="",
                )
                db.session.add(clienteRegistro)
                db.session.commit()
            session["usuarioNombre"] = (
                clienteRegistro.nombre
                if clienteRegistro
                else (usuario.empleado.nombre if usuario.empleado else usuario.correo)
            )
            session["usuarioLogin"] = usuario.correo
            session["clienteId"] = clienteRegistro.id if clienteRegistro else None
        else:
            session["usuarioNombre"] = (
                usuario.empleado.nombre
                if usuario.empleado
                else (usuario.cliente.nombre if usuario.cliente else usuario.correo)
            )
            session["usuarioLogin"] = (
                usuario.empleado.username if usuario.empleado else usuario.correo
            )
            session.pop("clienteId", None)

        session["usuarioCorreo"] = usuario.correo
        session["usuarioRol"] = rolNombre
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
    
    form = ClienteForm()

    if form.validate_on_submit():
   
        try:
            nombre = form.nombre.data.strip()
            apellidoPaterno = form.apellidoPaterno.data.strip()
            apellidoMaterno = (form.apellidoMaterno.data or "").strip()
            telefono = (form.telefono.data or "").strip()
            alias = (form.alias.data or "").strip()

            correo = form.correo.data.strip().lower()
            contrasena = form.contrasena.data

            if Usuario.query.filter_by(correo=correo).first():
                flash("El correo ya está registrado.", "danger")
                return render_template("login/registrar_cliente.html", form=form)

            rolCliente = Rol.query.filter_by(nombre="Cliente").first()
            if not rolCliente:
                flash("No existe el rol Cliente.", "danger")
                return render_template("login/registrar_cliente.html", form=form)

            usuario = Usuario(
                correo=correo,
                rolId=rolCliente.id,
                estado="Activo"
            )

            usuario.establecerContrasena(contrasena)
            usuario.resetearSeguridad()

            db.session.add(usuario)
            db.session.flush()  

            cliente = Cliente(
                usuarioId=usuario.id,
                nombre=nombre,
                apellidoPaterno=apellidoPaterno,
                apellidoMaterno=apellidoMaterno,
                telefono=telefono,
                alias=alias,
            )

            db.session.add(cliente)
            db.session.commit()

            codigo, expira = generar_codigo_con_expiracion()

            codigos_verificacion[correo] = {
                "codigo": codigo,
                "expira": expira,
                "intentos": 0,
                "max_intentos": 3
            }

            enviar_codigo_verificacion(correo, codigo)
            flash("Registro completado. Revisa tu correo para verificar tu cuenta.", "info")

            session["verificacion_email"] = correo
            return redirect(url_for("auth.verificarCorreo"))

        except Exception as e:
            db.session.rollback()
            flash("Ocurrió un error al registrar el usuario.", "danger")
            print(e)

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

@authBp.route("/verificar-correo", methods=["GET", "POST"])
def verificarCorreo():
    
    print("ENDPOINT:", request.endpoint)
    
    email = session.get("verificacion_email")

    print(email)
    
    if not email:
        flash("Sesión de verificación inválida", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    if request.method == "POST":
        codigo_ingresado = request.form.get("codigo")

        data = codigos_verificacion.get(email)

        if not data:
            flash("Código no válido o expirado", "danger")
            return redirect(url_for("auth.iniciarSesion"))

        if datetime.now() > data["expira"]:
            del codigos_verificacion[email]
            flash("Código expirado", "danger")
            return redirect(url_for("auth.registrarUsuario"))

        if data["intentos"] >= data["max_intentos"]:
            del codigos_verificacion[email]
            flash("Demasiados intentos", "danger")
            return redirect(url_for("auth.registrarUsuario"))

        if data["codigo"] != codigo_ingresado:
            data["intentos"] += 1
            flash("Código incorrecto", "danger")
            return render_template("login/verificar.html", email=email)

        usuario = Usuario.query.filter_by(correo=email).first()
        if usuario:
            usuario.verificado = True
            db.session.commit()

        codigos_verificacion.pop(email, None)

        flash("Cuenta verificada correctamente", "success")

        session.pop("verificacion_email", None)
            
        return redirect(url_for("auth.iniciarSesion"))

    return render_template("login/verificar.html", email=email)

@authBp.route("/reenviar-codigo", methods=["GET"])
def reenviarCodigo():
    email = session.get("verificacion_email")

    if not email:
        usuario_id = session.get("usuarioId")
        usuario = Usuario.query.get(usuario_id)

        if usuario:
            email = usuario.correo
            session["verificacion_email"] = email

    if not email:
        flash("No se pudo determinar el correo", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    codigo, expira = generar_codigo_con_expiracion()

    codigos_verificacion[email] = {
        "codigo": codigo,
        "expira": expira,
        "intentos": 0,
        "max_intentos": 3
    }

    enviar_codigo_verificacion(email, codigo)

    flash("Nuevo código enviado", "info")
    return redirect(url_for("auth.verificarCorreo"))

@authBp.route("/iniciar-verificacion", methods=["GET", "POST"])
def iniciarVerificacion():
    usuario_id = session.get("usuarioId")

    print("hola")
    
    usuario = Usuario.query.get(usuario_id)

    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    session["verificacion_email"] = usuario.correo

    return redirect(url_for("auth.verificarCorreo"))