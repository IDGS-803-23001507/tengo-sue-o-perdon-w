from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from werkzeug.routing import BuildError

from config import Config
from db_init import asegurar_base_de_datos, inicializar_db
from model import Compra, DetalleCompra, DetalleVenta, MateriaPrima, Producto, RegistroSesion, Venta, db
from app.auditoria import obtener_logs_auditoria

from app.login.routes import authBp, endpointDashboardRol, usuarioAutenticado
from app.usuarios.routes import usuariosBp
from app.inventario.routes import inventario_bp
from app.producto.routes import producto_bp
from app.producto_terminado.routes import producto_bp as producto_terminado_bp
from app.proveedores.routes import proveedor_bp
from app.merma.routes import merma_bp
from app.compras.routes import compras_bp
from app.cliente.routes import clientesBp
from app.solicitud.routes import solicitud_bp
from app.recetas.routes import recetas_bp
from app.utilidad.routes import utilidad_bp
from app.produccion.routes import produccion_bp
    
#Integracion decosas de michelle
from app.ventas.routes import ventasBp
from app.pedidos.routes import pedidosBp

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

try:
    asegurar_base_de_datos()
except Exception as exc:
    raise RuntimeError(f"No fue posible crear/verificar la base de datos: {exc}") from exc

db.init_app(app)
app.register_blueprint(authBp)
app.register_blueprint(usuariosBp)
app.register_blueprint(inventario_bp)
app.register_blueprint(producto_bp)
app.register_blueprint(producto_terminado_bp)
app.register_blueprint(proveedor_bp)
app.register_blueprint(merma_bp)
app.register_blueprint(compras_bp)
app.register_blueprint(clientesBp)
app.register_blueprint(solicitud_bp)
app.register_blueprint(recetas_bp)
app.register_blueprint(utilidad_bp)
app.register_blueprint(produccion_bp)

#Cosas de michelle
app.register_blueprint(ventasBp)
app.register_blueprint(pedidosBp)

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
    hoy = datetime.now()
    fechaHoy = hoy.date()

    inicioPeriodo = fechaHoy - timedelta(days=periodoDias - 1)
    finPeriodo = fechaHoy
    inicioPeriodoAnterior = inicioPeriodo - timedelta(days=periodoDias)
    finPeriodoAnterior = inicioPeriodo - timedelta(days=1)
    inicioSemanaMovil = fechaHoy - timedelta(days=6)

    def calcular_mediana(valores: list[float]) -> float:
        if not valores:
            return 0.0
        valores_ordenados = sorted(valores)
        mitad = len(valores_ordenados) // 2
        if len(valores_ordenados) % 2 == 0:
            return (valores_ordenados[mitad - 1] + valores_ordenados[mitad]) / 2
        return valores_ordenados[mitad]

    totalVentasDia = Decimal("0.00")
    totalVentasPeriodo = Decimal("0.00")
    totalVentasPeriodoAnterior = Decimal("0.00")
    totalGastosDia = Decimal("0.00")
    totalGastosPeriodo = Decimal("0.00")
    totalGastosPeriodoAnterior = Decimal("0.00")
    utilidadBrutaDia = Decimal("0.00")
    utilidadBrutaPeriodo = Decimal("0.00")
    utilidadBrutaPeriodoAnterior = Decimal("0.00")
    totalVentasSemana = Decimal("0.00")
    numeroTicketsDia = 0
    numeroTicketsSemana = 0
    ticketPromedioSemanal = Decimal("0.00")
    margenUtilidadBrutaPct = Decimal("0.00")
    puntoEquilibrioPeriodo = None

    if puedeVerFinanzas:
        totalVentasDia = db.session.query(func.coalesce(func.sum(Venta.total), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) == fechaHoy,
        ).scalar() or Decimal("0.00")

        totalVentasPeriodo = db.session.query(func.coalesce(func.sum(Venta.total), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) >= inicioPeriodo,
            func.date(Venta.fecha) <= finPeriodo,
        ).scalar() or Decimal("0.00")

        totalVentasPeriodoAnterior = db.session.query(func.coalesce(func.sum(Venta.total), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) >= inicioPeriodoAnterior,
            func.date(Venta.fecha) <= finPeriodoAnterior,
        ).scalar() or Decimal("0.00")

        totalVentasSemana = db.session.query(func.coalesce(func.sum(Venta.total), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) >= inicioSemanaMovil,
            func.date(Venta.fecha) <= fechaHoy,
        ).scalar() or Decimal("0.00")

        utilidadBrutaDia = db.session.query(func.coalesce(func.sum(Venta.utilidadBruta), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) == fechaHoy,
        ).scalar() or Decimal("0.00")

        utilidadBrutaPeriodo = db.session.query(func.coalesce(func.sum(Venta.utilidadBruta), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) >= inicioPeriodo,
            func.date(Venta.fecha) <= finPeriodo,
        ).scalar() or Decimal("0.00")

        utilidadBrutaPeriodoAnterior = db.session.query(func.coalesce(func.sum(Venta.utilidadBruta), 0)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) >= inicioPeriodoAnterior,
            func.date(Venta.fecha) <= finPeriodoAnterior,
        ).scalar() or Decimal("0.00")

        numeroTicketsDia = db.session.query(func.count(Venta.id_venta)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) == fechaHoy,
        ).scalar() or 0

        numeroTicketsSemana = db.session.query(func.count(Venta.id_venta)).filter(
            Venta.estatus.is_(True),
            func.date(Venta.fecha) >= inicioSemanaMovil,
            func.date(Venta.fecha) <= fechaHoy,
        ).scalar() or 0

        totalGastosDia = db.session.query(
            func.coalesce(func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario), 0)
        ).join(
            Compra, Compra.id_compra == DetalleCompra.id_compra
        ).filter(
            func.date(Compra.fecha) == fechaHoy,
        ).scalar() or Decimal("0.00")

        totalGastosPeriodo = db.session.query(
            func.coalesce(func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario), 0)
        ).join(
            Compra, Compra.id_compra == DetalleCompra.id_compra
        ).filter(
            func.date(Compra.fecha) >= inicioPeriodo,
            func.date(Compra.fecha) <= finPeriodo,
        ).scalar() or Decimal("0.00")

        totalGastosPeriodoAnterior = db.session.query(
            func.coalesce(func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario), 0)
        ).join(
            Compra, Compra.id_compra == DetalleCompra.id_compra
        ).filter(
            func.date(Compra.fecha) >= inicioPeriodoAnterior,
            func.date(Compra.fecha) <= finPeriodoAnterior,
        ).scalar() or Decimal("0.00")

        ticketPromedioSemanal = (totalVentasSemana / numeroTicketsSemana) if numeroTicketsSemana else Decimal("0.00")
        margenUtilidadBrutaPct = ((utilidadBrutaPeriodo / totalVentasPeriodo) * 100) if totalVentasPeriodo else Decimal("0.00")
        indiceContribucion = (utilidadBrutaPeriodo / totalVentasPeriodo) if totalVentasPeriodo else Decimal("0.00")
        if indiceContribucion > 0:
            puntoEquilibrioPeriodo = totalGastosPeriodo / indiceContribucion

    ventasPeriodo = db.session.query(
        func.date(Venta.fecha).label("fecha"),
        func.coalesce(func.sum(Venta.total), 0).label("monto"),
    ).filter(
        Venta.estatus.is_(True),
        func.date(Venta.fecha) >= inicioPeriodo,
        func.date(Venta.fecha) <= finPeriodo,
    ).group_by(
        func.date(Venta.fecha)
    ).all()

    ventasPeriodoAnterior = db.session.query(
        func.date(Venta.fecha).label("fecha"),
        func.coalesce(func.sum(Venta.total), 0).label("monto"),
    ).filter(
        Venta.estatus.is_(True),
        func.date(Venta.fecha) >= inicioPeriodoAnterior,
        func.date(Venta.fecha) <= finPeriodoAnterior,
    ).group_by(
        func.date(Venta.fecha)
    ).all()

    gastosPeriodo = []
    gastosPeriodoAnterior = []
    if puedeVerFinanzas:
        gastosPeriodo = db.session.query(
            func.date(Compra.fecha).label("fecha"),
            func.coalesce(func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario), 0).label("monto"),
        ).join(
            Compra, Compra.id_compra == DetalleCompra.id_compra
        ).filter(
            func.date(Compra.fecha) >= inicioPeriodo,
            func.date(Compra.fecha) <= finPeriodo,
        ).group_by(
            func.date(Compra.fecha)
        ).all()

        gastosPeriodoAnterior = db.session.query(
            func.date(Compra.fecha).label("fecha"),
            func.coalesce(func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario), 0).label("monto"),
        ).join(
            Compra, Compra.id_compra == DetalleCompra.id_compra
        ).filter(
            func.date(Compra.fecha) >= inicioPeriodoAnterior,
            func.date(Compra.fecha) <= finPeriodoAnterior,
        ).group_by(
            func.date(Compra.fecha)
        ).all()

    mapaVentas = {str(fila.fecha): float(fila.monto or 0) for fila in ventasPeriodo}
    mapaVentasPeriodoAnterior = {str(fila.fecha): float(fila.monto or 0) for fila in ventasPeriodoAnterior}
    mapaGastos = {str(fila.fecha): float(fila.monto or 0) for fila in gastosPeriodo}
    mapaGastosPeriodoAnterior = {str(fila.fecha): float(fila.monto or 0) for fila in gastosPeriodoAnterior}
    etiquetas = []
    puntosIngresos = []
    puntosIngresosPeriodoAnterior = []
    puntosGastos = []
    puntosGastosPeriodoAnterior = []
    puntosEbitda = []
    puntosEbitdaPeriodoAnterior = []

    for paso in range(periodoDias):
        fecha = inicioPeriodo + timedelta(days=paso)
        clave = fecha.isoformat()
        etiquetas.append(fecha.strftime("%d/%m"))
        ingreso_actual = round(mapaVentas.get(clave, 0.0), 2)
        gasto_actual = round(mapaGastos.get(clave, 0.0), 2)
        puntosIngresos.append(ingreso_actual)
        puntosGastos.append(gasto_actual)
        puntosEbitda.append(round(ingreso_actual - gasto_actual, 2))

        fecha_anterior = inicioPeriodoAnterior + timedelta(days=paso)
        clave_anterior = fecha_anterior.isoformat()
        ingreso_anterior = round(mapaVentasPeriodoAnterior.get(clave_anterior, 0.0), 2)
        gasto_anterior = round(mapaGastosPeriodoAnterior.get(clave_anterior, 0.0), 2)
        puntosIngresosPeriodoAnterior.append(ingreso_anterior)
        puntosGastosPeriodoAnterior.append(gasto_anterior)
        puntosEbitdaPeriodoAnterior.append(round(ingreso_anterior - gasto_anterior, 2))

    productosVentasPeriodo = db.session.query(
        Producto.id_producto,
        Producto.nombre,
        func.coalesce(func.sum(DetalleVenta.cantidad), 0).label("cantidad"),
    ).join(
        DetalleVenta, DetalleVenta.id_producto == Producto.id_producto
    ).join(
        Venta, Venta.id_venta == DetalleVenta.id_venta
    ).filter(
        Venta.estatus.is_(True),
        func.date(Venta.fecha) >= inicioPeriodo,
        func.date(Venta.fecha) <= finPeriodo,
    ).group_by(
        Producto.id_producto,
        Producto.nombre,
    ).order_by(
        func.sum(DetalleVenta.cantidad).desc()
    ).all()

    rentabilidadProductos = []
    for item in productosVentasPeriodo:
        producto = Producto.query.get(item.id_producto)
        if not producto:
            continue

        cantidad = Decimal(str(item.cantidad or 0))
        costo_producto = Decimal(str(producto.costo_unitario() or 0))
        precio_venta = Decimal(str(producto.precio_venta or 0))
        margen_contribucion = precio_venta - costo_producto
        rentabilidad_total = cantidad * margen_contribucion

        rentabilidadProductos.append({
            "id_producto": item.id_producto,
            "nombre": item.nombre,
            "cantidad": float(cantidad),
            "costo_producto": float(costo_producto),
            "margen_contribucion": float(margen_contribucion),
            "rentabilidad_total": float(rentabilidad_total),
        })

    mediana_cantidad = calcular_mediana([item["cantidad"] for item in rentabilidadProductos])
    mediana_rentabilidad = calcular_mediana([item["rentabilidad_total"] for item in rentabilidadProductos])

    for item in rentabilidadProductos:
        es_alta_venta = item["cantidad"] >= mediana_cantidad
        es_alta_ganancia = item["rentabilidad_total"] >= mediana_rentabilidad

        if es_alta_venta and es_alta_ganancia:
            item["categoria_menu"] = "Plato Estrella"
            item["categoria_color"] = "bg-emerald-100 text-emerald-700 border-emerald-200"
        elif (not es_alta_venta) and (not es_alta_ganancia):
            item["categoria_menu"] = "Perro"
            item["categoria_color"] = "bg-rose-100 text-rose-700 border-rose-200"
        elif es_alta_venta and (not es_alta_ganancia):
            item["categoria_menu"] = "Caballo"
            item["categoria_color"] = "bg-amber-100 text-amber-700 border-amber-200"
        else:
            item["categoria_menu"] = "Puzzle"
            item["categoria_color"] = "bg-blue-100 text-blue-700 border-blue-200"

    topProductos = sorted(
        rentabilidadProductos,
        key=lambda item: item["rentabilidad_total"],
        reverse=True,
    )[:10]

    ultimasOperaciones = Venta.query.filter_by(estatus=True).order_by(Venta.fecha.desc()).limit(7).all()
    materiasActivas = MateriaPrima.query.filter(
        MateriaPrima.estatus.is_(True),
    ).order_by(MateriaPrima.nombre.asc()).all()

    alertasInsumos = []
    for materia in materiasActivas:
        stock_actual = Decimal(str(materia.stock_actual or 0))
        stock_minimo = Decimal(str(materia.stock_minimo or 0))
        faltante = max(stock_minimo - stock_actual, Decimal("0"))

        if stock_minimo > 0 and stock_actual <= stock_minimo:
            prioridad = "Urgente"
            prioridad_orden = 1
            prioridad_color = "bg-red-100 text-red-700 border-red-200"
        elif stock_minimo > 0 and stock_actual <= (stock_minimo * Decimal("1.25")):
            prioridad = "Próximo"
            prioridad_orden = 2
            prioridad_color = "bg-amber-100 text-amber-700 border-amber-200"
        else:
            prioridad = "Stock OK"
            prioridad_orden = 3
            prioridad_color = "bg-emerald-100 text-emerald-700 border-emerald-200"

        alertasInsumos.append({
            "id_materia": materia.id_materia,
            "nombre": materia.nombre,
            "unidad": materia.unidad.abreviacion if materia.unidad else "u",
            "stock_actual": float(stock_actual),
            "stock_minimo": float(stock_minimo),
            "faltante": float(faltante),
            "prioridad": prioridad,
            "prioridad_orden": prioridad_orden,
            "prioridad_color": prioridad_color,
        })

    alertasInsumos.sort(key=lambda item: (item["prioridad_orden"], -item["faltante"], item["nombre"]))

    ticketPromedioDia = (totalVentasDia / numeroTicketsDia) if numeroTicketsDia else Decimal("0.00")
    ebitdaDia = totalVentasDia - totalGastosDia
    ebitdaPeriodo = totalVentasPeriodo - totalGastosPeriodo
    ebitdaPeriodoAnterior = totalVentasPeriodoAnterior - totalGastosPeriodoAnterior

    variacionVentasPct = 0.0
    if totalVentasPeriodoAnterior > 0:
        variacionVentasPct = float(((totalVentasPeriodo - totalVentasPeriodoAnterior) / totalVentasPeriodoAnterior) * 100)
    elif totalVentasPeriodo > 0:
        variacionVentasPct = 100.0

    variacionEbitdaPct = 0.0
    if ebitdaPeriodoAnterior > 0:
        variacionEbitdaPct = float(((ebitdaPeriodo - ebitdaPeriodoAnterior) / ebitdaPeriodoAnterior) * 100)
    elif ebitdaPeriodo > 0:
        variacionEbitdaPct = 100.0

    return {
        "periodoSeleccionado": periodoDias,
        "totalVentasDia": float(totalVentasDia),
        "totalVentasPeriodo": float(totalVentasPeriodo),
        "totalVentasPeriodoAnterior": float(totalVentasPeriodoAnterior),
        "totalGastosDia": float(totalGastosDia),
        "totalGastosPeriodo": float(totalGastosPeriodo),
        "totalGastosPeriodoAnterior": float(totalGastosPeriodoAnterior),
        "utilidadBrutaDia": float(utilidadBrutaDia),
        "utilidadBrutaPeriodo": float(utilidadBrutaPeriodo),
        "utilidadBrutaPeriodoAnterior": float(utilidadBrutaPeriodoAnterior),
        "utilidadNetaDia": float(ebitdaDia),
        "utilidadNetaPeriodo": float(ebitdaPeriodo),
        "ebitdaDia": float(ebitdaDia),
        "ebitdaPeriodo": float(ebitdaPeriodo),
        "ebitdaPeriodoAnterior": float(ebitdaPeriodoAnterior),
        "ticketPromedioDia": float(ticketPromedioDia),
        "ticketPromedioSemanal": float(ticketPromedioSemanal),
        "margenUtilidadBrutaPct": float(margenUtilidadBrutaPct),
        "puntoEquilibrioPeriodo": float(puntoEquilibrioPeriodo) if puntoEquilibrioPeriodo is not None else None,
        "numeroTicketsDia": int(numeroTicketsDia),
        "numeroTicketsSemana": int(numeroTicketsSemana),
        "etiquetasGrafica": etiquetas,
        "puntosGrafica": puntosIngresos,
        "puntosGraficaPeriodoAnterior": puntosIngresosPeriodoAnterior,
        "puntosGraficaGastos": puntosGastos,
        "puntosGraficaGastosPeriodoAnterior": puntosGastosPeriodoAnterior,
        "puntosGraficaEbitda": puntosEbitda,
        "puntosGraficaEbitdaPeriodoAnterior": puntosEbitdaPeriodoAnterior,
        "variacionVentasPct": variacionVentasPct,
        "variacionEbitdaPct": variacionEbitdaPct,
        "topProductos": topProductos,
        "ultimasOperaciones": ultimasOperaciones,
        "alertasInsumos": alertasInsumos,
        "puedeVerFinanzas": puedeVerFinanzas,
    }


@app.before_request
def requerirLogin():
    def normalizarRol(rol: str) -> str:
        mapa = {
            "Admin General (TI)": "admin_ti",
            "Admin General": "admin_ti",
            "Gerente de Tienda": "gerente_tienda",
            "Gerente": "gerente_tienda",
            "Cajero": "cajero",
            "Barista": "barista",
            "Operador": "barista",
            "Cliente": "cliente",
        }
        return mapa.get((rol or "").strip(), "desconocido")

    def moduloDesdeEndpoint(endpoint: str | None) -> str | None:
        if not endpoint:
            return None
        if endpoint in {"dashboard_gerente", "dashboard_operador"}:
            return "dashboard"

        prefijo = endpoint.split(".", 1)[0] if "." in endpoint else endpoint
        mapa = {
            "auth": "autenticacion",
            "usuarios": "usuarios",
            "producto": "productos",
            "producto_terminado": "productos",
            "recetas": "recetas",
            "solicitud": "produccion",
            "produccion": "produccion",
            "proveedor": "proveedores",
            "compras": "compras",
            "ventas": "ventas",
        }
        return mapa.get(prefijo)

    def accionDesdeRequest(endpoint: str | None, method: str) -> str:
        metodo = (method or "GET").upper()
        if metodo == "GET":
            return "R"
        if metodo in {"PUT", "PATCH"}:
            return "U"
        if metodo == "DELETE":
            return "D"

        ep = (endpoint or "").lower()
        if any(token in ep for token in ["eliminar", "borrar", "desactivar", "delete"]):
            return "D"
        if any(token in ep for token in ["actualizar", "editar", "modificar", "finalizar", "reactivar"]):
            return "U"
        if any(token in ep for token in ["crear", "nuevo", "nueva", "registrar", "comprar"]):
            return "C"
        return "C"

    def accionesPermitidas(rolCanonico: str, modulo: str) -> set[str]:
        matriz = {
            "admin_ti": {
                "autenticacion": {"C", "R", "U", "D"},
                "usuarios": {"C", "R", "U", "D"},
                "dashboard": {"R"},
                "productos": {"C", "R", "U", "D"},
                "recetas": {"C", "R", "U", "D"},
                "produccion": {"C", "R", "U", "D"},
                "proveedores": {"C", "R", "U", "D"},
                "compras": {"C", "R", "U", "D"},
                "ventas": {"C", "R", "U", "D"},
            },
            "gerente_tienda": {
                "autenticacion": {"C", "R", "U", "D"},
                "usuarios": {"C", "R", "U", "D"},
                "dashboard": {"C", "R", "U", "D"},
                "productos": {"C", "R", "U", "D"},
                "recetas": {"C", "R", "U", "D"},
                "produccion": {"C", "R", "U", "D"},
                "proveedores": {"C", "R", "U", "D"},
                "compras": {"C", "R", "U", "D"},
                "ventas": {"C", "R", "U", "D"},
            },
            "cajero": {
                "autenticacion": {"R"},
                "usuarios": set(),
                "dashboard": set(),
                "productos": {"R"},
                "recetas": set(),
                "produccion": set(),
                "proveedores": set(),
                "compras": set(),
                "ventas": {"C", "R", "U"},
            },
            "barista": {
                "autenticacion": {"R"},
                "usuarios": set(),
                "dashboard": set(),
                "productos": {"R"},
                "recetas": {"R"},
                "produccion": {"C", "R", "U"},
                "proveedores": set(),
                "compras": set(),
                "ventas": set(),
            },
        }
        return matriz.get(rolCanonico, {}).get(modulo, set())

    def permitido(rolCanonico: str, modulo: str, accion: str) -> bool:
        return accion in accionesPermitidas(rolCanonico, modulo)

    endpointsPublicos = {
        "auth.iniciarSesion",
        "auth.registrarUsuario",
        "auth.recuperarContrasena",
        "auth.resetearContrasena",
        "auth.verificarCorreo",
        "auth.reenviarCodigo",
        "auth.iniciarVerificacion",
        "auth.cerrarSesion",
        "producto.producto_venta",
        "clientes.detalle_cliente",
        "ventas.venta_online",
        "ventas.pagar_venta_gestion",
        "index",
        "static",
    }

    if request.endpoint in endpointsPublicos:
        return None

    if not usuarioAutenticado():
        return redirect(url_for("auth.iniciarSesion"))

    registroSesionId = session.get("registroSesionId")
    tokenSesion = session.get("tokenSesion")
    usuarioId = session.get("usuarioId")

    if not registroSesionId or not tokenSesion or not usuarioId:
        session.clear()
        return redirect(url_for("auth.iniciarSesion"))

    sesionActiva = RegistroSesion.query.filter_by(
        id=registroSesionId,
        tokenSesion=tokenSesion,
        usuarioId=usuarioId,
        activa=True,
    ).first()

    if not sesionActiva:
        session.clear()
        flash("Tu sesión no es válida o expiró. Inicia sesión nuevamente.", "danger")
        return redirect(url_for("auth.iniciarSesion"))

    if request.endpoint not in endpointsPublicos:
       modulo = moduloDesdeEndpoint(request.endpoint)
    if modulo:
        accion = accionDesdeRequest(request.endpoint, request.method)
        rolCanonico = normalizarRol(session.get("usuarioRol", ""))
        if not permitido(rolCanonico, modulo, accion):
            acciones = accionesPermitidas(rolCanonico, modulo)
            nombres = {"R": "leer", "C": "crear", "U": "actualizar", "D": "eliminar"}

            if not acciones:
                flash("No tienes permisos para este módulo.", "danger")
            elif acciones == {"R"}:
                flash("Solo tienes permiso para leer en este módulo.", "warning")
            else:
                permitidas_txt = ", ".join(nombres[a] for a in ["R", "C", "U", "D"] if a in acciones)
                flash(f"No tienes permiso para esta acción. Tus permisos aquí son: {permitidas_txt}.", "warning")
            return redirect(url_for("index"))

    if session.get("usuarioRol") == "Cliente":
        endpointsCliente = {
            "ventas.tienda_cliente",
            "ventas.comprar_producto",
            "auth.verificarCorreo",
            "auth.cerrarSesion",
            "auth.iniciarVerificacion",
            "auth.reenviarCodigo",
            "clientes.detalle_cliente",
            "clientes.editar_cliente",
            "clientes.desactivar_cliente",
            "pedidos.mis_pedidos",
            "ventas.venta_online",
            "ventas.pagar_venta_gestion",
            "index",
            "static",
        }
       
        if request.endpoint not in endpointsPublicos and request.endpoint not in endpointsCliente:
            return redirect(url_for("ventas.tienda_cliente"))

    return None

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


@app.route("/dashboard/gerente")
def dashboard_gerente():
    if session.get("usuarioRol") not in {"Gerente", "Gerente de Tienda", "Admin General (TI)", "Admin General"}:
        abort(403)
    periodo = request.args.get("periodo", "7")
    periodoDias = int(periodo) if periodo in {"7", "15", "30"} else 7
    contexto = construirContextoDashboard(periodoDias=periodoDias, puedeVerFinanzas=True)
    contexto["active_page"] = "dashboard"
    return render_template("dashboard/dashboard.html", **contexto)


@app.route("/dashboard/operador")
def dashboard_operador():
    if session.get("usuarioRol") not in {
        "Gerente",
        "Gerente de Tienda",
        "Admin General (TI)",
        "Admin General",
        "Operador",
        "Cajero",
        "Barista",
    }:
        abort(403)
    periodo = request.args.get("periodo", "7")
    periodoDias = int(periodo) if periodo in {"7", "15", "30"} else 7
    contexto = construirContextoDashboard(periodoDias=periodoDias, puedeVerFinanzas=False)
    contexto["active_page"] = "dashboard"
    return render_template("dashboard/dashboard.html", **contexto)


@app.route("/dashboard/auditoria")
def dashboard_auditoria():
    if session.get("usuarioRol") not in {"Admin General (TI)", "Admin General"}:
        abort(403)

    logs = obtener_logs_auditoria(limit=300)
    return render_template("dashboard/auditoria.html", logs=logs, active_page="dashboard")

if __name__ == "__main__":
    app.run(debug=True, port=8080)