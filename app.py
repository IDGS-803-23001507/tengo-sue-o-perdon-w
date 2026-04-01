from datetime import timedelta

from flask import Flask, abort, redirect, render_template, request, session, url_for
from sqlalchemy.exc import OperationalError

from config import Config
from model import db

from app.login.routes import authBp, endpointDashboardRol, iniciarModuloAuth, usuarioAutenticado
from app.usuarios.routes import usuariosBp
from app.inventario.routes import inventario_bp
from app.producto.routes import producto_bp

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

db.init_app(app)
app.register_blueprint(authBp)
app.register_blueprint(usuariosBp)
app.register_blueprint(inventario_bp)
app.register_blueprint(producto_bp)

try:
    iniciarModuloAuth(app)
except OperationalError as exc:
    raise RuntimeError(
        "No fue posible conectar a MySQL."
    ) from exc


@app.before_request
def requerirLogin():
    endpointsPublicos = {"auth.iniciarSesion", "auth.registrarUsuario", "auth.recuperarContrasena", "producto.producto_venta","home", "index", "static"}

    if request.endpoint in endpointsPublicos:
        return None

    if not usuarioAutenticado():
        return redirect(url_for("auth.iniciarSesion"))

    return None


@app.route("/",)
def home():
    return render_template("index.html")

@app.route("/cambio")
def index():
    if usuarioAutenticado():
        endpointRol = endpointDashboardRol(session.get("usuarioRol", "Operador"))
        return redirect(url_for(endpointRol))
    return redirect(url_for("auth.iniciarSesion"))


@app.route("/dashboard/gerente")
def dashboard_gerente():
    if session.get("usuarioRol") != "Gerente":
        abort(403)
    return render_template("dashboard/dashboard.html")


@app.route("/dashboard/operador")
def dashboard_operador():
    if session.get("usuarioRol") not in {"Gerente", "Operador"}:
        abort(403)
    return render_template("dashboard/dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)