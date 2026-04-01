from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

from model import RegistroSesion, Usuario, db

authBp = Blueprint("auth", __name__)

hashContrasenaSimulada = generate_password_hash("urban-coffee-dummy-password")


def asegurarEsquemaUsuarios() -> None:
    inspector = inspect(db.engine)
    columnas = {columna["name"] for columna in inspector.get_columns("usuarios")}

    sentenciasMigracion = []

    if "nombre" not in columnas:
        sentenciasMigracion.append("ALTER TABLE usuarios ADD COLUMN nombre VARCHAR(120) NOT NULL DEFAULT 'Sin nombre'")

    if "estado" not in columnas:
        sentenciasMigracion.append("ALTER TABLE usuarios ADD COLUMN estado VARCHAR(20) NOT NULL DEFAULT 'Activo'")

    for sentencia in sentenciasMigracion:
        db.session.execute(text(sentencia))

    if sentenciasMigracion:
        db.session.commit()


def sembrarUsuariosBase() -> None:
    gerente = Usuario.query.filter_by(correo="gerente@urbancoffee.com").first()
    operador = Usuario.query.filter_by(correo="operador@urbancoffee.com").first()

    if not gerente:
        gerente = Usuario(correo="gerente@urbancoffee.com", nombre="Administrador", rol="Gerente", estado="Activo")
        gerente.establecerContrasena("Gerente#2026")
        db.session.add(gerente)
    else:
        gerente.nombre = gerente.nombre or "Administrador"
        gerente.estado = gerente.estado or "Activo"

    if not operador:
        operador = Usuario(correo="operador@urbancoffee.com", nombre="Operador", rol="Operador", estado="Activo")
        operador.establecerContrasena("Operador#2026")
        db.session.add(operador)
    else:
        operador.nombre = operador.nombre or "Operador"
        operador.estado = operador.estado or "Activo"

    db.session.commit()


def iniciarModuloAuth(app) -> None:
    with app.app_context():
        db.create_all()
        asegurarEsquemaUsuarios()
        sembrarUsuariosBase()


def usuarioAutenticado() -> bool:
    return bool(session.get("inicioSesion") and session.get("usuarioId"))


def endpointDashboardRol(rol: str) -> str:
    mapaRoles = {
        "Gerente": "dashboard_gerente",
        "Operador": "dashboard_operador",
    }
    return mapaRoles.get(rol, "dashboard_operador")


@authBp.route("/login", methods=["GET", "POST"], endpoint="iniciarSesion")
def iniciarSesion():
	if request.method == "POST":
		correo = request.form.get("correo", "").strip().lower()
		contrasena = request.form.get("contrasena", "")

		errorGenerico = "Usuario o contraseña incorrectos"
		usuario = Usuario.query.filter_by(correo=correo).first()

		if not usuario:
			check_password_hash(hashContrasenaSimulada, contrasena)
			flash(errorGenerico, "danger")
			return render_template("login.html")

		if usuario.estado != "Activo":
			check_password_hash(hashContrasenaSimulada, contrasena)
			flash(errorGenerico, "danger")
			return render_template("login.html")

		if usuario.estaBloqueada():
			db.session.commit()
			flash("Cuenta bloqueada temporalmente.", "warning")
			return render_template("login.html")

		if not usuario.validarContrasena(contrasena):
			usuario.registrarIntentoFallido(maxIntentos=4, minutosBloqueo=15)
			db.session.commit()

			if usuario.cuentaBloqueada:
				flash("Cuenta bloqueada temporalmente por múltiples intentos fallidos.", "warning")
			else:
				flash(errorGenerico, "danger")

			return render_template("login/login.html")

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
		session["usuarioCorreo"] = usuario.correo
		session["usuarioRol"] = usuario.rol
		session["registroSesionId"] = registroSesion.id
		session["tokenSesion"] = tokenSesion

		return redirect(url_for(endpointDashboardRol(usuario.rol)))

	return render_template("login/login.html")


@authBp.route("/register", methods=["GET", "POST"], endpoint="registrarUsuario")
def registrarUsuario():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")

        if not nombre or not correo or not contrasena:
            flash("Completa todos los campos requeridos.", "danger")
            return render_template("register.html")

        existe = Usuario.query.filter_by(correo=correo).first()
        if existe:
            flash("El correo ya está registrado.", "danger")
            return render_template("register.html")

        usuario = Usuario(nombre=nombre, correo=correo, rol="Operador", estado="Activo")
        usuario.establecerContrasena(contrasena)
        usuario.resetearSeguridad()

        db.session.add(usuario)
        db.session.commit()

        flash("Registro completado. Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("auth.iniciarSesion"))

    return render_template("login/registrar_cliente.html")


@authBp.route("/forgot-password", endpoint="recuperarContrasena")
def recuperarContrasena():
    flash("Recuperación de contraseña pendiente de implementación.", "info")
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