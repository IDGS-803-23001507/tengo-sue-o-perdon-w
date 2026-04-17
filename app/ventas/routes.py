from functools import wraps
from forms import VentaForm, PagoForm
from sqlalchemy import text, exc
from datetime import datetime, timedelta
from decimal import Decimal
import csv
from io import StringIO
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, make_response
from sqlalchemy.exc import SQLAlchemyError

from app.auditoria import registrar_auditoria
from model import Cliente, DetalleVenta, Producto, Venta, db

ventasBp = Blueprint("ventas", __name__)

@ventasBp.route("/tienda", methods=["GET"], endpoint="tienda_cliente")
def tiendaCliente():
    if not session.get("inicioSesion"):
        return redirect(url_for("auth.iniciarSesion"))

    if session.get("usuarioRol") != "Cliente":
        return redirect(url_for("index"))

    query_productos = text("""
        SELECT p.*, 
        CASE 
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE WHEN COALESCE(p.stock, 0) > 0 THEN 1 ELSE 0 END
            WHEN EXISTS (
                SELECT 1 FROM Recetas r 
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia 
                WHERE r.id_producto = p.id_producto AND r.estado = 1 AND mp.stock_actual < r.cantidad
            ) THEN 0 ELSE 1 
        END as disponible_stock
        FROM Producto p WHERE p.estatus = 1
        ORDER BY p.nombre ASC
    """)
    productos = db.session.execute(query_productos).fetchall()
    return render_template("venta_linea/catalogo_productos.html", productos=productos)


@ventasBp.route("/ventas", methods=["GET"])
def ventas():
    # 1. Obtener la fecha del filtro o la de hoy
    fecha_filtro = request.args.get('fecha') or request.args.get('creado_en')
    if not fecha_filtro:
        fecha_filtro = datetime.now().strftime('%Y-%m-%d')

    # 2. CONSULTA CORREGIDA: Filtramos estrictamente por estado 'Pagado'
    # Usamos LOWER para evitar problemas si en la DB dice 'PAGADO' o 'pagado'
    query = text("""
        SELECT * FROM ventas 
        WHERE DATE(creado_en) = :f 
          AND LOWER(estado) = 'pagado'
        ORDER BY creado_en DESC
    """)
    
    ventas = db.session.execute(query, {"f": fecha_filtro}).fetchall()


    total_efectivo = sum(v.total for v in ventas if v.metodo_pago == 'Efectivo')
    total_tarjeta = sum(v.total for v in ventas if v.metodo_pago == 'Tarjeta')
    
    total_dia = total_efectivo + total_tarjeta
    num_transacciones = len(ventas)

    return render_template(
        "ventas/ventas.html", 
        ventas=ventas, 
        fecha_actual=fecha_filtro,
        total_efectivo=total_efectivo,
        total_tarjeta=total_tarjeta,
        total_dia=total_dia,
        transacciones=num_transacciones
    )
    
    
@ventasBp.route("/fisica", methods=["GET", "POST"])
def venta_fisica():
    form = VentaForm()
    productos = Producto.query.filter_by(estatus=True).all()
    
    if request.method == "POST":
        
        if "agregar" in request.form:
            p_id = request.form.get("producto_id", type=int)
            prod = Producto.query.get(p_id)
            if prod:
                if prod.tipo_preparacion == "stock" and int(prod.stock or 0) <= 0:
                    session["modal_solicitud_produccion"] = {
                        "id_producto": prod.id_producto,
                        "nombre": prod.nombre,
                    }
                    session.modified = True
                    return redirect(url_for("ventas.venta_fisica"))

                carrito = session.get("carrito", [])

                if prod.tipo_preparacion == "stock":
                    cantidad_actual_en_carrito = sum(
                        item.get("cantidad", 0)
                        for item in carrito
                        if item.get("id_producto") == p_id
                    )

                    if cantidad_actual_en_carrito >= int(prod.stock or 0):
                        session["modal_solicitud_produccion"] = {
                            "id_producto": prod.id_producto,
                            "nombre": prod.nombre,
                        }
                        session.modified = True
                        return redirect(url_for("ventas.venta_fisica"))

                carrito.append({
                    "id_producto": p_id,
                    "nombre": prod.nombre,
                    "precio": float(prod.precio_venta),
                    "cantidad": 1
                })
                session["carrito"] = carrito
                session.modified = True
            return redirect(url_for("ventas.venta_fisica"))

        
        if "quitar" in request.form:
            idx = request.form.get("item_index", type=int)
            carrito = session.get("carrito", [])
            if 0 <= idx < len(carrito):
                carrito.pop(idx)
                session["carrito"] = carrito
                session.modified = True
            return redirect(url_for("ventas.venta_fisica"))

        if "terminar" in request.form:
            carrito = session.get("carrito", [])
            if not carrito: 
                return redirect(url_for("ventas.venta_fisica"))
            
            try:
                id_venta_actual = 0
                for item in carrito:
                    result = db.session.execute(
                        text("CALL crear_venta_general(:u, :c, :tipo, :p, :can, :v_id)"),
                        {
                            "u": session.get("usuarioId"),
                            "c": None,
                            "tipo": "fisica",
                            "p": item["id_producto"],
                            "can": item["cantidad"],
                            "v_id": id_venta_actual
                        }
                    )
                    row = result.fetchone()
                    if row:
                        id_venta_actual = row[0]

                db.session.commit()
                
                session["carrito"] = [] 
                session.pop("carrito", None) 
                session.modified = True 
                
                return redirect(url_for("ventas.pagar_venta_gestion", idVenta=id_venta_actual))
                
            except Exception as e:
                db.session.rollback()
                error_str = str(e)
                error_texto = error_str.lower()

                if "stock insuficiente" in error_texto and "insumo" in error_texto:
                    flash("No hay suficiente stock de insumos para completar la venta.", "danger")
                elif "stock insuficiente" in error_texto:
                    flash("No hay suficiente stock del producto para completar la venta.", "danger")
                elif "producto sin receta activa" in error_texto:
                    flash("El producto no tiene receta activa. Revisa el módulo de recetas.", "danger")
                elif "producto no disponible" in error_texto:
                    flash("El producto ya no está disponible para la venta.", "danger")
                else:
                    flash("Ocurrió un error al procesar la venta.", "danger")

                return redirect(url_for("ventas.venta_fisica"))

    carrito = session.get("carrito", [])
    total = sum(item['precio'] * item['cantidad'] for item in carrito)
    modal_solicitud = session.pop("modal_solicitud_produccion", None)
    return render_template(
        "ventas/fisica.html",
        form=form,
        productos=productos,
        carrito=carrito,
        total=total,
        modal_solicitud=modal_solicitud,
    )


@ventasBp.route("/fisica/solicitar-produccion", methods=["POST"], endpoint="solicitar_produccion_desde_pos")
def solicitar_produccion_desde_pos():
    id_producto = request.form.get("producto_id", type=int)
    if not id_producto:
        flash("Producto inválido para generar solicitud.", "danger")
        return redirect(url_for("ventas.venta_fisica"))

    producto = Producto.query.filter_by(id_producto=id_producto, estatus=True).first()
    if not producto:
        flash("El producto ya no está disponible.", "danger")
        return redirect(url_for("ventas.venta_fisica"))

    if producto.tipo_preparacion != "stock":
        flash("Solo los productos de tipo stock se envían a solicitud de producción.", "danger")
        return redirect(url_for("ventas.venta_fisica"))

    flash(
        f"Te redirigimos a Nueva Solicitud para registrar manualmente la producción de {producto.nombre}.",
        "info",
    )
    return redirect(url_for("solicitud.crear_solicitud", producto=producto.id_producto))

@ventasBp.route("/online", methods=["GET", "POST"])
def venta_online():
    if not session.get("inicioSesion"):
        return redirect(url_for("auth.iniciarSesion"))
        
    form = VentaForm()
    
    # Consulta de productos con validación de stock en tiempo real
    query_productos = text("""
        SELECT p.*, 
        CASE 
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE WHEN COALESCE(p.stock, 0) > 0 THEN 1 ELSE 0 END
            WHEN EXISTS (
                SELECT 1 FROM Recetas r 
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia 
                WHERE r.id_producto = p.id_producto AND r.estado = 1 AND mp.stock_actual < r.cantidad
            ) THEN 0 ELSE 1 
        END as disponible_stock
        FROM Producto p WHERE p.estatus = 1
    """)
    productos = db.session.execute(query_productos).fetchall()

    if request.method == "POST":
        # --- LÓGICA DEL CARRITO ---
        if "quitar" in request.form:
            index = request.form.get("item_index", type=int)
            carrito = session.get("carrito", [])
            if 0 <= index < len(carrito):
                eliminado = carrito.pop(index)
                session["carrito"] = carrito
                session.modified = True
                flash(f"Se quitó {eliminado['nombre']} del pedido", "info")
            return redirect(url_for("ventas.venta_online"))

        if "agregar" in request.form:
            prod_id = request.form.get("producto")
            cant = request.form.get("cantidad", type=int, default=1)
            nombre = request.form.get("nombre_prod")
            prod_actual = next((p for p in productos if str(p.id_producto) == prod_id), None)
            
            if prod_actual and prod_actual.disponible_stock == 0:
                flash(f"Lo sentimos, {nombre} se ha agotado.", "danger")
                return redirect(url_for("ventas.venta_online"))

            precio = float(prod_actual.precio_venta) if prod_actual else 0
            carrito = session.get("carrito", [])
            carrito.append({
                "id_producto": int(prod_id), 
                "cantidad": cant, 
                "nombre": nombre,
                "precio": precio 
            })
            session["carrito"] = carrito
            session.modified = True
            flash(f"¡{nombre} añadido!", "success")
            return redirect(url_for("ventas.venta_online"))
        
        # --- FINALIZAR PEDIDO (VALIDACIÓN Y REGISTRO PREVIO) ---
        if "terminar" in request.form:
            carrito = session.get("carrito", [])
            if not carrito:
                flash("Carrito vacío", "warning")
                return redirect(url_for("ventas.venta_online"))

            hora_recogida_raw = request.form.get("hora_recogida")

            try:
                hora_pedido = datetime.strptime(hora_recogida_raw, '%Y-%m-%dT%H:%M')
                ahora = datetime.now()

                # Validaciones de horario de Urban Coffee
                if hora_pedido.date() != ahora.date():
                    flash("Los pedidos online son solo para hoy.", "danger")
                    return redirect(url_for("ventas.venta_online"))

                if hora_pedido.hour >= 23:
                    flash("La sucursal cierra a las 11 PM. Elige una hora más temprana.", "warning")
                    return redirect(url_for("ventas.venta_online"))

                if hora_pedido < (ahora + timedelta(hours=1)):
                    flash("Requerimos al menos 1 hora de anticipación.", "danger")
                    return redirect(url_for("ventas.venta_online"))

            except ValueError:
                flash("Formato de fecha incorrecto.", "danger")
                return redirect(url_for("ventas.venta_online"))
            
            u_id = session.get("usuarioId")
            c_id = session.get("clienteId")

            # --- PROCESO DE INSERCIÓN "PENDIENTE DE PAGO" ---
            id_venta_tracker = 0 
            id_pedido_editando = session.get("editando_pedido_id")

            if id_pedido_editando:
                res_venta = db.session.execute(
                    text("SELECT id_venta FROM pedidos WHERE id_pedido = :id"),
                    {"id": id_pedido_editando}
                ).fetchone()
                if res_venta:
                    id_venta_tracker = res_venta[0]

            try:
                # Se llama al Procedure para validar insumos y crear registro
                # NOTA: La venta se crea pero con metodo_pago = NULL (No contable aún)
                for item in carrito:
                    result = db.session.execute(
                        text("CALL crear_venta_online(:u, :c, :h, :n, :p, :can, :v_ex)"),
                        {
                            "u": u_id, "c": c_id, 
                            "h": hora_recogida_raw, 
                            "n": request.form.get("notas", ""),
                            "p": item["id_producto"], "can": item["cantidad"], 
                            "v_ex": id_venta_tracker
                        }
                    ).fetchone()
                    
                    if result:
                        id_venta_tracker = result[0]
                
                db.session.commit()
                
                session.pop("carrito", None)
                session.pop("editando_pedido_id", None)
                
                flash("¡Pedido confirmado! Paga al recoger en sucursal.", "success")
                return redirect(url_for("pedidos.mis_pedidos"))

            except exc.InternalError as e:
                db.session.rollback()
                # Si el trigger o procedure de SQL lanza error por falta de materia prima
                error_msg = str(e.orig).split("'")[1] if "'" in str(e.orig) else "Sin stock suficiente."
                flash(f"Aviso: {error_msg}", "warning")
            except Exception as e:
                db.session.rollback()
                flash("No pudimos procesar tu pedido.", "danger")
            
            return redirect(url_for("ventas.venta_online"))

    return render_template("ventas/online.html", form=form, lista_productos=productos)
@ventasBp.route("/reporte", methods=["GET"])
def generar_reporte():
    # Obtenemos la fecha del filtro o la de hoy por defecto
    fecha_filtro = request.args.get('fecha') or datetime.now().strftime('%Y-%m-%d')

    # MODIFICACIÓN: Filtramos estrictamente por v.estado = 'Pagado'
    # Esto excluye pedidos pendientes, cancelados o carritos abandonados.
    query = text("""
        SELECT v.id_venta, v.creado_en, v.metodo_pago, v.total, v.id_usuario, v.estado
        FROM ventas v
        WHERE DATE(v.creado_en) = :f
          AND LOWER(v.estado) = 'pagado'
    """)
    
    ventas = db.session.execute(query, {"f": fecha_filtro}).fetchall()

    si = StringIO()
    cw = csv.writer(si)
    # Encabezados del CSV
    cw.writerow(['Folio', 'Fecha/Hora', 'Metodo Pago', 'Estado', 'Total', 'Atendio'])
    
    total_acumulado = 0
    for v in ventas:
        # Escribimos cada fila de venta pagada
        cw.writerow([
            f"UC-{v.id_venta}", 
            v.creado_en, 
            v.metodo_pago or 'N/A', 
            v.estado,
            v.total, 
            f"Usuario #{v.id_usuario}"
        ])
        total_acumulado += v.total
    
    # Fila de total al final del reporte
    cw.writerow([])
    cw.writerow(['', '', '', 'TOTAL DEL DIA:', total_acumulado])

    # Generamos la respuesta para descargar el archivo
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=Reporte_Ventas_{fecha_filtro}.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output

@ventasBp.route("/<int:idVenta>/pagar", methods=["GET", "POST"])
def pagar_venta_gestion(idVenta): 
    form = PagoForm()
    
    if request.method == "POST":
        metodo = request.form.get("metodo_pago")
        # Aseguramos que si el campo está vacío, sea "0"
        monto_recibido = request.form.get("pago_recibido", 0)
        cambio = request.form.get("cambio_calculado", 0)
        tarjeta = request.form.get("num_tarjeta", "")[-4:]
        
        try:
            db.session.execute(text("CALL pagar_venta(:id, :met)"), {"id": idVenta, "met": metodo})
            db.session.commit()
            
            # IMPORTANTE: Enviamos los valores tal cual al ticket
            return redirect(url_for("ventas.ticket", 
                                    idVenta=idVenta, 
                                    pago=monto_recibido, 
                                    cambio=cambio, 
                                    term=tarjeta))
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}" # Para debug breve

    result = db.session.execute(text("SELECT total FROM ventas WHERE id_venta = :id"), {"id": idVenta}).fetchone()
    return render_template("ventas/pagar.html", form=form, idVenta=idVenta, total=result[0])
@ventasBp.route("/ticket/<int:idVenta>", methods=["GET", "POST"], endpoint="ticket")
def ticket(idVenta):
    # Usamos type=float para que Flask convierta la URL directamente
    pago = request.args.get('pago', default=0.0, type=float)
    cambio = request.args.get('cambio', default=0.0, type=float)
    terminacion = request.args.get('term', "")

    query = text("""
        SELECT 
            v.id_venta, v.creado_en, v.metodo_pago, v.total,
            COALESCE(c.nombre, 'Venta Mostrador') AS cliente_nombre,
            p.nombre AS producto,
            dv.cantidad,
            (dv.cantidad * dv.precio_unitario) AS subtotal
        FROM ventas v
        JOIN detalle_venta dv ON v.id_venta = dv.id_venta
        JOIN Producto p ON dv.id_producto = p.id_producto
        LEFT JOIN clientes c ON v.id_cliente = c.id
        WHERE v.id_venta = :idVenta
    """)
    
    resultado = db.session.execute(query, {"idVenta": idVenta}).fetchall()
    
    return render_template("ventas/ticket.html", 
                           ticket=resultado, 
                           pago=pago, 
                           cambio=cambio, 
                           term=terminacion)

#####################################################################################
