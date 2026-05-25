from datetime import timedelta
from flask import Flask, redirect, render_template, session, url_for
from sqlalchemy.exc import OperationalError
from werkzeug.routing import BuildError

from config import Config
from db_init import asegurar_base_de_datos, inicializar_db
from model import  db

from app.login.routes import authBp, endpointDashboardRol, usuarioAutenticado
from app.usuarios.routes import usuariosBp
from app.cliente.routes import clientesBp
from app.sucursales.routes import sucursalesBp 
from app.alimento.routes import alimentosBp
from app.bebida.routes import bebidasBp
from app.combos.routes import combosBp
from app.venta_linea.routes import inicioBp
from app.pedidos.routes import pedidosBp

from flask import current_app
from itsdangerous import URLSafeSerializer

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

_ENGINES_TECNICOS: dict[str, object] = {}

try:
    asegurar_base_de_datos()
except Exception as exc:
    raise RuntimeError(f"No fue posible crear/verificar la base de datos: {exc}") from exc

db.init_app(app)
app.register_blueprint(authBp)
app.register_blueprint(usuariosBp)
app.register_blueprint(pedidosBp)
app.register_blueprint(clientesBp)
app.register_blueprint(sucursalesBp)
app.register_blueprint(alimentosBp)
app.register_blueprint(bebidasBp)
app.register_blueprint(combosBp)
app.register_blueprint(inicioBp)

try:
    with app.app_context():
        inicializar_db()
except OperationalError as exc:
    raise RuntimeError(
        f"No fue posible inicializar MySQL: {exc}"
    ) from exc


@app.context_processor
def utilidadesTemplate():
    def safe_url_for(endpoint: str, **values):
        try:
            return url_for(endpoint, **values)
        except BuildError:
            return "#"

    return {"safe_url_for": safe_url_for}

def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

@app.context_processor
def inject_serializer():
    return dict(serializer=get_serializer())

@app.teardown_request
def liberar_sesion_db(_exc):
    try:
        db.session.remove()
    except Exception:
        pass

@app.after_request
def add_header(response):
    if response.content_type == "text/html; charset=utf-8":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    if usuarioAutenticado():
        if session.get("usuarioRol") != "Cliente":
            endpointRol = endpointDashboardRol(session.get("usuarioRol", "Operador"))
            return redirect(url_for(endpointRol))
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, port=8080)