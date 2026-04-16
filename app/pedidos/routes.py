from flask import Blueprint, flash, redirect, render_template, session, url_for
from functools import wraps
from sqlalchemy import text
from datetime import datetime, timedelta
from flask import request

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
    # 1. Obtener los pedidos del cliente
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
            c.nombre AS nombre_cliente
        FROM pedidos p
        JOIN ventas v ON p.id_venta = v.id_venta
        LEFT JOIN clientes c ON v.id_cliente = c.id
        WHERE LOWER(p.estado) IN ('pendiente', 'aceptado', 'preparando', 'listo', 'enviado')
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

    query_pedido = text("SELECT id_venta, estado FROM pedidos WHERE id_pedido = :id")
    pedido = db.session.execute(query_pedido, {"id": idPedido}).fetchone()
    
    if not pedido:
        flash("Pedido no encontrado", "danger")
        return redirect(url_for("pedidos.index"))
        
    id_venta = pedido.id_venta
    estado_actual = str(pedido.estado).lower()
    estado_nuevo = estado.lower()
    
    # Bloqueo de Reversa Irreversible
    if estado_actual in ['enviado', 'entregado'] and estado_nuevo in ['cancelado', 'rechazado']:
        flash("No puedes rechazar o cancelar un pedido que ya fue enviado o entregado.", "danger")
        return redirect(url_for("pedidos.index"))

    query_update = text("""
        UPDATE pedidos
        SET estado = :estado
        WHERE id_pedido = :id
    """)
    db.session.execute(query_update, {"estado": estado, "id": idPedido})

    # --- Lógica de inventario según transición de estado ---
    query_detalles = text("SELECT id_producto, cantidad FROM detalle_venta WHERE id_venta = :id_venta")
    detalles = db.session.execute(query_detalles, {"id_venta": id_venta}).fetchall()

    if estado_nuevo in ['cancelado', 'rechazado'] and estado_actual not in ['cancelado', 'rechazado']:
        # Liberar reservas y restaurar insumos
        for id_producto, cantidad in detalles:
            prod_info = db.session.execute(
                text("SELECT tipo_preparacion FROM Producto WHERE id_producto = :pid"),
                {"pid": id_producto}
            ).fetchone()
            if prod_info:
                if prod_info[0] == "stock":
                    # Solo liberar la reserva; el stock real nunca se tocó
                    db.session.execute(
                        text("UPDATE Producto SET stock_reservado = GREATEST(0, stock_reservado - :cant) WHERE id_producto = :pid"),
                        {"cant": cantidad, "pid": id_producto}
                    )
                else:
                    # materia_prima: devolver insumos que sí se descontaron
                    recetas = db.session.execute(
                        text("SELECT id_materia, cantidad FROM Recetas WHERE id_producto = :pid AND estado = 1"),
                        {"pid": id_producto}
                    ).fetchall()
                    for id_materia, c_receta in recetas:
                        db.session.execute(
                            text("UPDATE Materia_prima SET stock_actual = stock_actual + :total WHERE id_materia = :mid"),
                            {"total": c_receta * cantidad, "mid": id_materia}
                        )

    elif estado_nuevo == 'entregado' and estado_actual not in ['entregado', 'cancelado', 'rechazado']:
        # Descontar stock real y limpiar reserva para productos tipo stock
        for id_producto, cantidad in detalles:
            prod_info = db.session.execute(
                text("SELECT tipo_preparacion FROM Producto WHERE id_producto = :pid"),
                {"pid": id_producto}
            ).fetchone()
            if prod_info and prod_info[0] == "stock":
                db.session.execute(
                    text("""
                        UPDATE Producto
                        SET stock          = GREATEST(0, stock - :cant),
                            stock_reservado = GREATEST(0, stock_reservado - :cant)
                        WHERE id_producto = :pid
                    """),
                    {"cant": cantidad, "pid": id_producto}
                )

    db.session.commit()

    if estado_nuevo == 'entregado' and id_venta:
        return redirect(url_for("ventas.pagar_venta_gestion", idVenta=id_venta))

    flash(f"Estado actualizado a {estado}.", "success")
    return redirect(url_for("pedidos.index"))

@pedidosBp.route("/cancelar/<int:idPedido>", methods=["POST"])
def cancelar_pedido(idPedido):
    # 1. Verificar que el pedido existe y pertenece al cliente
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

    # 2. Verificar tiempo transcurrido
    tiempo_transcurrido = datetime.now() - pedido.hora_solicitud
    if tiempo_transcurrido > timedelta(minutes=MINUTOS_LIMITE_CAMBIO):
        flash(f"No puedes cancelar el pedido después de {MINUTOS_LIMITE_CAMBIO} minutos.", "warning")
        return redirect(url_for("pedidos.mis_pedidos"))

    # 3. Verificar estado (No se puede cancelar si ya se está preparando o entregó)
    if pedido.estado.lower() != 'pendiente':
        flash("Solo se pueden cancelar pedidos en estado 'Pendiente'.", "warning")
        return redirect(url_for("pedidos.mis_pedidos"))

    # 4. Ejecutar cancelación (Cambiamos el estado a 'Cancelado')
    query_cancelar = text("UPDATE pedidos SET estado = 'Cancelado' WHERE id_pedido = :id")
    db.session.execute(query_cancelar, {"id": idPedido})
    
    # 4. Liberar reserva / restaurar insumos según tipo de producto
    query_detalles = text("SELECT id_producto, cantidad FROM detalle_venta WHERE id_venta = :id_venta")
    detalles = db.session.execute(query_detalles, {"id_venta": pedido.id_venta}).fetchall()
    for id_producto, cantidad in detalles:
        prod_info = db.session.execute(
            text("SELECT tipo_preparacion FROM Producto WHERE id_producto = :pid"),
            {"pid": id_producto}
        ).fetchone()
        if prod_info:
            if prod_info[0] == "stock":
                # Solo liberar la reserva; el stock real nunca se tocó
                db.session.execute(
                    text("UPDATE Producto SET stock_reservado = GREATEST(0, stock_reservado - :cant) WHERE id_producto = :pid"),
                    {"cant": cantidad, "pid": id_producto}
                )
            else:
                # materia_prima: devolver los insumos descontados
                recetas = db.session.execute(
                    text("SELECT id_materia, cantidad FROM Recetas WHERE id_producto = :pid AND estado = 1"),
                    {"pid": id_producto}
                ).fetchall()
                for id_materia, c_receta in recetas:
                    db.session.execute(
                        text("UPDATE Materia_prima SET stock_actual = stock_actual + :total WHERE id_materia = :mid"),
                        {"total": c_receta * cantidad, "mid": id_materia}
                    )
    
    db.session.commit()

    flash("Pedido cancelado exitosamente.", "success")
    return redirect(url_for("pedidos.mis_pedidos"))


@pedidosBp.route("/editar/<int:idPedido>")
def editar_pedido(idPedido):
    # 1. Seguridad básica
    if not session.get("inicioSesion"):
        return redirect(url_for("auth.iniciarSesion"))

    # --- DIAGNÓSTICO DE CONSOLA ---
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

    # 5. Forzamos la redirección manual por si url_for tiene conflicto de nombres
    print("Redirigiendo a /online...")
    # Usamos el nombre exacto del endpoint que definiste en ventasBp
    return redirect("/online")