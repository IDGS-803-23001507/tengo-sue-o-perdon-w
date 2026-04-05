from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Flask, abort, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from werkzeug.routing import BuildError

from config import Config
from db_init import inicializar_db
from model import DetalleVenta, MateriaPrima, Producto, Venta, db

from app.login.routes import authBp, endpointDashboardRol, usuarioAutenticado
from app.usuarios.routes import usuariosBp
from app.inventario.routes import inventario_bp
from app.producto.routes import producto_bp
from app.proveedores.routes import proveedor_bp
from app.merma.routes import merma_bp
from app.compras.routes import compras_bp
from app.ventas.routes import ventasBp
from app.cliente.routes import clientesBp

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
app.register_blueprint(proveedor_bp)
app.register_blueprint(merma_bp)
app.register_blueprint(compras_bp)
app.register_blueprint(ventasBp)
app.register_blueprint(clientesBp)

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


def construirContextoDashboard(periodoDias: int, puedeVerFinanzas: bool) -> dict:
    hoy = datetime.now(timezone.utc)
    inicioHoy = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
    finHoy = inicioHoy + timedelta(days=1)

    inicioPeriodo = (inicioHoy - timedelta(days=periodoDias - 1)).date()
    finPeriodo = inicioHoy.date()

    totalVentasDia = Decimal("0.00")
    utilidadBrutaDia = Decimal("0.00")
    numeroTicketsDia = 0

    if puedeVerFinanzas:
        totalVentasDia = db.session.query(func.coalesce(func.sum(Venta.total), 0)).filter(
            Venta.confirmada.is_(True),
            Venta.fecha >= inicioHoy,
            Venta.fecha < finHoy,
        ).scalar() or Decimal("0.00")

        utilidadBrutaDia = db.session.query(func.coalesce(func.sum(Venta.utilidadBruta), 0)).filter(
            Venta.confirmada.is_(True),
            Venta.fecha >= inicioHoy,
            Venta.fecha < finHoy,
        ).scalar() or Decimal("0.00")

        numeroTicketsDia = db.session.query(func.count(Venta.id)).filter(
            Venta.confirmada.is_(True),
            Venta.fecha >= inicioHoy,
            Venta.fecha < finHoy,
        ).scalar() or 0

    ventasPeriodo = db.session.query(
        func.date(Venta.fecha).label("fecha"),
        func.coalesce(func.sum(Venta.total), 0).label("monto"),
    ).filter(
        Venta.confirmada.is_(True),
        func.date(Venta.fecha) >= inicioPeriodo,
        func.date(Venta.fecha) <= finPeriodo,
    ).group_by(
        func.date(Venta.fecha)
    ).all()

    mapaVentas = {str(fila.fecha): float(fila.monto or 0) for fila in ventasPeriodo}
    etiquetas = []
    puntos = []

    for paso in range(periodoDias):
        fecha = inicioPeriodo + timedelta(days=paso)
        clave = fecha.isoformat()
        etiquetas.append(fecha.strftime("%d/%m"))
        puntos.append(round(mapaVentas.get(clave, 0.0), 2))

    topProductos = db.session.query(
        Producto.nombre,
        func.coalesce(func.sum(DetalleVenta.cantidad), 0).label("cantidad"),
    ).join(
        DetalleVenta, DetalleVenta.id_producto == Producto.id_producto
    ).join(
        Venta, Venta.id == DetalleVenta.id_venta
    ).filter(
        Venta.confirmada.is_(True),
        func.date(Venta.fecha) >= inicioPeriodo,
        func.date(Venta.fecha) <= finPeriodo,
    ).group_by(
        Producto.id_producto,
        Producto.nombre,
    ).order_by(
        func.sum(DetalleVenta.cantidad).desc()
    ).limit(5).all()

    ultimasOperaciones = Venta.query.filter_by(confirmada=True).order_by(Venta.fecha.desc()).limit(7).all()
    alertasInsumos = MateriaPrima.query.filter(
        MateriaPrima.estatus.is_(True),
        MateriaPrima.stock_actual <= MateriaPrima.stock_minimo,
    ).order_by(MateriaPrima.stock_actual.asc()).all()

    return {
        "periodoSeleccionado": periodoDias,
        "totalVentasDia": float(totalVentasDia),
        "utilidadBrutaDia": float(utilidadBrutaDia),
        "numeroTicketsDia": int(numeroTicketsDia),
        "etiquetasGrafica": etiquetas,
        "puntosGrafica": puntos,
        "topProductos": topProductos,
        "ultimasOperaciones": ultimasOperaciones,
        "alertasInsumos": alertasInsumos,
        "puedeVerFinanzas": puedeVerFinanzas,
    }


@app.before_request
def requerirLogin():
    endpointsPublicos = {
        "auth.iniciarSesion",
        "auth.registrarUsuario",
        "auth.recuperarContrasena",
        "auth.resetearContrasena",
        "producto.producto_venta",
        "clientes.detalle_cliente",
        "index",
        "static",
    }

    if request.endpoint in endpointsPublicos:
        return None

    if not usuarioAutenticado():
        return redirect(url_for("auth.iniciarSesion"))

    if session.get("usuarioRol") == "Cliente":
        endpointsCliente = {
            "ventas.tienda_cliente",
            "ventas.comprar_producto",
            "auth.cerrarSesion",
            "clientes.detalle_cliente",
            "clientes.editar_cliente",
            "clientes.desactivar_cliente",
            "index",
            "static",
        }
        if request.endpoint not in endpointsPublicos and request.endpoint not in endpointsCliente:
            return redirect(url_for("ventas.tienda_cliente"))

    return None


@app.route("/")
def index():
    if usuarioAutenticado():
        if session.get("usuarioRol") != "Cliente":
            endpointRol = endpointDashboardRol(session.get("usuarioRol", "Operador"))
            return redirect(url_for(endpointRol))
    return render_template("index.html")


@app.route("/dashboard/gerente")
def dashboard_gerente():
    if session.get("usuarioRol") != "Gerente":
        abort(403)
    periodo = request.args.get("periodo", "7")
    periodoDias = int(periodo) if periodo in {"7", "15", "30"} else 7
    contexto = construirContextoDashboard(periodoDias=periodoDias, puedeVerFinanzas=True)
    return render_template("dashboard/dashboard.html", **contexto)


@app.route("/dashboard/operador")
def dashboard_operador():
    if session.get("usuarioRol") not in {"Gerente", "Operador"}:
        abort(403)
    periodo = request.args.get("periodo", "7")
    periodoDias = int(periodo) if periodo in {"7", "15", "30"} else 7
    contexto = construirContextoDashboard(periodoDias=periodoDias, puedeVerFinanzas=False)
    return render_template("dashboard/dashboard.html", **contexto)

if __name__ == "__main__":
    app.run(debug=True, port=8080)