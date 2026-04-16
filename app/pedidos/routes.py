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
    
    pedidos = db.session.execute(query, {"cliente": session.get("clienteId")}).fetchall()
    
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
            SELECT dv.cantidad, prod.nombre as nombre_producto
            FROM detalle_venta dv
            JOIN Producto prod ON dv.id_producto = prod.id_producto
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
        detalle_lower = detalle.lower()

        if "no se puede aceptar" in detalle_lower and "stock insuficiente" in detalle_lower:
            flash("No se pudo aceptar el pedido: inventario insuficiente para cubrir la preparación.", "danger")
        elif "stock insuficiente" in detalle_lower:
            flash("Inventario insuficiente para realizar este cambio de estado.", "danger")
        elif "transición inválida" in detalle_lower:
            flash("Cambio de estado inválido: el pedido solo puede avanzar al siguiente estado lógico.", "warning")
        elif "pedido no encontrado" in detalle_lower:
            flash("El pedido ya no existe o fue actualizado por otro usuario.", "warning")
        else:
            flash(detalle if detalle else "No fue posible cambiar el estado del pedido.", "warning")

        return redirect(url_for("pedidos.index"))

    if estado_normalizado == 'entregado' and venta:
        return redirect(url_for("ventas.pagar_venta_gestion", idVenta=venta.id_venta))

    return redirect(url_for("pedidos.index"))