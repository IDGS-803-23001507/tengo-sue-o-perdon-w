from flask import Blueprint, flash, redirect, render_template, session, url_for
from functools import wraps
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from model import db

pedidosBp = Blueprint("pedidos", __name__, url_prefix="/pedidos")

def requiereRol(rolRequerido: str):
    def decorador(funcionVista):
        @wraps(funcionVista)
        def envuelta(*args, **kwargs):
            if not session.get("inicioSesion"):
                return redirect(url_for("auth.iniciarSesion"))

            if session.get("usuarioRol") != rolRequerido:
                flash("No tienes permisos.", "danger")
                return redirect(url_for("dashboard_operador"))

            return funcionVista(*args, **kwargs)
        return envuelta
    return decorador

@pedidosBp.route("/mis-pedidos", methods=["GET"], endpoint="mis_pedidos")
def mis_pedidos():
    
    query = text("""
        SELECT p.*, v.codigo_recogida, v.total 
        FROM pedidos p
        JOIN ventas v ON p.id_venta = v.id_venta
        WHERE v.id_cliente = :cliente
        ORDER BY p.hora_solicitud DESC
    """)
    result = db.session.execute(query, {"cliente": session.get("clienteId")})
    # Convertimos a lista de diccionarios para poder agregarle la clave 'detalles'
    pedidos = [dict(row._mapping) for row in result]
    
    # 2. Obtener los productos para cada pedido
    for p in pedidos:
        query_detalles = text("""
            SELECT dv.cantidad, prod.nombre as nombre_producto
            FROM detalle_venta dv
            JOIN Producto prod ON dv.id_producto = prod.id_producto
            WHERE dv.id_venta = :id_venta
        """)
        detalles_result = db.session.execute(query_detalles, {"id_venta": p['id_venta']})
        p['detalles'] = [dict(row._mapping) for row in detalles_result]
    
    return render_template("venta_linea/mis_pedidos.html", pedidos=pedidos)

@pedidosBp.route("/", methods=["GET"], endpoint="index")
def index():

    query_pedidos = text("""
        SELECT 
            p.id_pedido, 
            p.id_venta, 
            p.hora_recogida, 
            p.estado, 
            p.notas, 
            v.codigo_recogida,
            v.total,
            c.nombre AS nombre_cliente
        FROM pedidos p
        JOIN ventas v ON p.id_venta = v.id_venta
        LEFT JOIN clientes c ON v.id_cliente = c.id
        WHERE LOWER(p.estado) IN ('pendiente', 'aceptado', 'preparando')
        ORDER BY p.hora_recogida ASC
    """)
    
    result = db.session.execute(query_pedidos)
    pedidos = [dict(row._mapping) for row in result]

    for p in pedidos:
        query_detalles = text("""
            SELECT dv.cantidad, 
                   COALESCE(CONCAT(prod.nombre, ' (', vr.nombre, ')'), prod.nombre) as nombre_producto
            FROM detalle_venta dv
            JOIN Producto prod ON dv.id_producto = prod.id_producto
            LEFT JOIN variante_receta vr ON dv.id_variante = vr.id_variante
            WHERE dv.id_venta = :id_venta
        """)
        detalles_result = db.session.execute(query_detalles, {"id_venta": p['id_venta']})
  
        p['detalles'] = [dict(row._mapping) for row in detalles_result]
    
    return render_template("venta_linea/pedidos.html", pedidos=pedidos, active_page="pedidos")


@pedidosBp.route("/<int:idPedido>/estado/<string:estado>", methods=["POST"])
def cambiar_estado(idPedido, estado):
    estado_normalizado = (estado or "").strip().lower()
    estados_validos = {"pendiente", "aceptado", "preparando", "entregado", "cancelado", "rechazado"}

    if estado_normalizado not in estados_validos:
        flash("Estado de pedido inválido.", "danger")
        return redirect(url_for("pedidos.index"))

    try:
        query_venta = text("SELECT id_venta FROM pedidos WHERE id_pedido = :id")
        venta = db.session.execute(query_venta, {"id": idPedido}).fetchone()

        db.session.execute(
            text("CALL sp_cambiar_estado_pedido(:id_pedido, :nuevo_estado, :id_usuario, :motivo)"),
            {
                "id_pedido": idPedido,
                "nuevo_estado": estado_normalizado,
                "id_usuario": session.get("usuarioId"),
                "motivo": "cambio desde panel operativo",
            },
        )
        db.session.commit()

    except SQLAlchemyError as e:
        db.session.rollback()
        detalle = str(getattr(e, "orig", e))
        flash(detalle if detalle else "No fue posible cambiar el estado del pedido.", "warning")
        return redirect(url_for("pedidos.index"))

    if estado_normalizado == 'entregado' and venta:
        return redirect(url_for("ventas.pagar_venta_gestion", idVenta=venta.id_venta))

    return redirect(url_for("pedidos.index"))
    
MINUTOS_LIMITE_CAMBIO = 10


MINUTOS_LIMITE_CAMBIO = 10

@pedidosBp.route("/cancelar/<int:idPedido>", methods=["POST"])
def cancelar_pedido(idPedido):
    
    query_verificar = text("""
        SELECT p.id_pedido, p.hora_solicitud, p.estado 
        FROM pedidos p
        JOIN ventas v ON p.id_venta = v.id_venta
        WHERE p.id_pedido = :id AND v.id_cliente = :clienteId
    """)
    pedido = db.session.execute(query_verificar, {
        "id": idPedido, 
        "clienteId": session.get("clienteId")
    }).fetchone()

    if not pedido:
        flash("Pedido no encontrado.", "danger")
        return redirect(url_for("pedidos.mis_pedidos"))

    
    tiempo_transcurrido = datetime.now() - pedido.hora_solicitud
    if tiempo_transcurrido > timedelta(minutes=MINUTOS_LIMITE_CAMBIO):
        flash(f"No puedes cancelar el pedido después de {MINUTOS_LIMITE_CAMBIO} minutos.", "warning")
        return redirect(url_for("pedidos.mis_pedidos"))

    
    if pedido.estado.lower() != 'pendiente':
        flash("Solo se pueden cancelar pedidos en estado 'Pendiente'.", "warning")
        return redirect(url_for("pedidos.mis_pedidos"))

    
    query_cancelar = text("UPDATE pedidos SET estado = 'cancelado' WHERE id_pedido = :id")
    db.session.execute(query_cancelar, {"id": idPedido})
    db.session.commit()

    flash("Pedido cancelado exitosamente.", "success")
    return redirect(url_for("pedidos.mis_pedidos"))


@pedidosBp.route("/editar/<int:idPedido>")
def editar_pedido(idPedido):

    if not session.get("inicioSesion"):
        return redirect(url_for("auth.iniciarSesion"))

    
    c_id = session.get("clienteId")
    print(f"\n--- INTENTO DE EDICIÓN ---")
    print(f"Pedido a buscar: {idPedido}")
    print(f"ID Cliente en sesión: {c_id}")
    # ------------------------------

    # 2. Query simplificada (Quitamos el JOIN con ventas para ver si ese es el bloqueo)
    # Solo buscamos los detalles que pertenecen a ese pedido
    query_detalles = text("""
        SELECT dv.id_producto, dv.cantidad, p.nombre, p.precio_venta 
        FROM detalle_venta dv
        JOIN Producto p ON dv.id_producto = p.id_producto
        JOIN pedidos pe ON dv.id_venta = pe.id_venta
        WHERE pe.id_pedido = :id
    """)
    
    detalles = db.session.execute(query_detalles, {"id": idPedido}).fetchall()

    # 3. Verificamos qué encontró
    if not detalles:
        print("ERROR: No se encontraron productos para este pedido en la DB.")
        flash("No se encontraron productos en este pedido.", "danger")
        return redirect(url_for("pedidos.mis_pedidos"))

    print(f"ÉXITO: Se encontraron {len(detalles)} productos.")

    # 4. Cargar carrito
    session["carrito"] = []
    for d in detalles:
        session["carrito"].append({
            "id_producto": d.id_producto,
            "nombre": d.nombre,
            "precio": float(d.precio_venta),
            "cantidad": d.cantidad
        })
    
    session["editando_pedido_id"] = idPedido
    session.modified = True

    print("Redirigiendo a /online...")
    return redirect(url_for("ventas.venta_online", _external=True))
