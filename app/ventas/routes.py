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
from model import Cliente, DetalleVenta, Producto, Venta, Usuario, db

from itsdangerous import URLSafeSerializer
from flask import current_app

ventasBp = Blueprint("ventas", __name__)

def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

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

    fecha_filtro = request.args.get('fecha') or request.args.get('creado_en')
    
    if not fecha_filtro:
        fecha_filtro = datetime.now().strftime('%Y-%m-%d')

    query = text("""
        SELECT * FROM ventas 
        WHERE DATE(creado_en) = :f 
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
    query_productos = text("""
        SELECT p.*, 
        CASE 
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE WHEN (COALESCE(p.stock, 0) - COALESCE(p.stock_reservado, 0)) > 0 THEN 1 ELSE 0 END
            WHEN EXISTS (
                SELECT 1 FROM Recetas r 
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia 
                WHERE r.id_producto = p.id_producto AND r.estado = 1 AND mp.stock_actual < r.cantidad
            ) THEN 0 ELSE 1 
        END as disponible_stock
        FROM Producto p WHERE p.estatus = 1
    """)
    productos = db.session.execute(query_productos).fetchall()

    # Mapa: id_producto -> lista de insumos para tooltip en el POS
    insumos_por_producto = {}
    from model import Receta, MateriaPrima
    recetas_activas = (
        Receta.query
        .filter_by(estado=True)
        .join(MateriaPrima, Receta.id_materia == MateriaPrima.id_materia)
        .all()
    )
    for receta in recetas_activas:
        mp = receta.materiaPrima
        if mp:
            label = mp.nombre
            if mp.tamanio:
                label += f" ({mp.tamanio})"
            insumos_por_producto.setdefault(receta.id_producto, []).append(label)
    
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
                
                return redirect(url_for("ventas.pagar_venta_gestion", token=get_serializer().dumps(id_venta_actual)))
                
            except Exception as e:
                db.session.rollback()
                error_str = str(e)
                error_texto = error_str.lower()

                if "faltan insumos:" in error_texto:
                    error_msg = str(e.orig).split("'")[1] if hasattr(e, 'orig') and "'" in str(e.orig) else str(e)
                    flash(error_msg, "danger")
                elif "stock insuficiente" in error_texto and "insumo" in error_texto:
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
        insumos_por_producto=insumos_por_producto,
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
    
    query_productos = text("""
        SELECT p.*, 
        CASE 
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE WHEN (COALESCE(p.stock, 0) - COALESCE(p.stock_reservado, 0)) > 0 THEN 1 ELSE 0 END
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
            flash(f"¡{nombre} añadido con éxito!", "success")
            return redirect(url_for("ventas.venta_online"))
        
        if "terminar" in request.form:
            
            usuario = Usuario.query.get(session.get("usuarioId"))

            if usuario and not usuario.verificado:
                session["verificacion_email"] = usuario.correo
                flash("Debes verificar tu correo para completar la compra", "warning")
                return redirect(url_for("auth.verificarCorreo"))
     
            carrito = session.get("carrito", [])
            if not carrito:
                flash("Carrito vacío", "warning")
                return redirect(url_for("ventas.venta_online"))
                
            total_unidades = sum(item.get("cantidad", 1) for item in carrito)
            if total_unidades > 15:
                flash("Para pedidos mayores a 15 unidades, por favor contactar a la sucursal.", "warning")
                return redirect(url_for("ventas.venta_online"))

            hora_recogida_raw = request.form.get("hora_recogida")

            try:
                hora_pedido = datetime.strptime(hora_recogida_raw, '%Y-%m-%dT%H:%M')
                ahora = datetime.now()

                if hora_pedido.date() != ahora.date():
                    flash("Los pedidos online solo se pueden realizar para el día de hoy.", "danger")
                    return redirect(url_for("ventas.venta_online"))

                if hora_pedido.hour >= 23:
                    flash("Lo sentimos, la sucursal está por cerrar. Elige una hora más temprana.", "warning")
                    return redirect(url_for("ventas.venta_online"))

                if hora_pedido < (ahora + timedelta(minutes=15)):
                    flash("Para preparar tu pedido con calidad, requerimos al menos 15 minutos de anticipación.", "danger")
                    return redirect(url_for("ventas.venta_online"))

            except ValueError:
                flash("El formato de fecha y hora no es correcto.", "danger")
                return redirect(url_for("ventas.venta_online"))
                
            # Lógica de Validación de Stock Agrupada
            try:
                from collections import defaultdict
                cantidades_por_producto = defaultdict(int)
                for item in carrito:
                    cantidades_por_producto[item["id_producto"]] += item["cantidad"]
                
                consumo_materia = defaultdict(float)

                for p_id, q in cantidades_por_producto.items():
                    query_prod = text("""
                        SELECT tipo_preparacion, stock 
                        FROM Producto 
                        WHERE id_producto = :pid AND estatus = 1
                    """)
                    prod_info = db.session.execute(query_prod, {"pid": p_id}).fetchone()
                    if not prod_info:
                        flash("Uno o más productos en el carrito ya no están disponibles. Por favor, actualiza tu orden.", "danger")
                        return redirect(url_for("ventas.venta_online"))
                    
                    tipo, stock_actual = prod_info
                    
                    if tipo == "stock":
                        if int(stock_actual or 0) < q:
                            flash("Stock insuficiente del producto para completar la venta. Ajuste las cantidades.", "warning")
                            return redirect(url_for("ventas.venta_online"))
                    else:
                        query_receta = text("""
                            SELECT id_materia, cantidad 
                            FROM Recetas 
                            WHERE id_producto = :pid AND estado = 1
                        """)
                        recetas = db.session.execute(query_receta, {"pid": p_id}).fetchall()
                        if not recetas:
                            flash("Un producto no tiene receta activa y no puede ser preparado. Contacte a la sucursal.", "danger")
                            return redirect(url_for("ventas.venta_online"))
                            
                        for r_materia, r_cantidad in recetas:
                            consumo_materia[r_materia] += float(r_cantidad * q)
                
                for m_id, q_req in consumo_materia.items():
                    query_mp = text("SELECT stock_actual FROM Materia_prima WHERE id_materia = :mid")
                    mp_info = db.session.execute(query_mp, {"mid": m_id}).fetchone()
                    if not mp_info or float(mp_info[0] or 0) < q_req:
                        flash("No hay suficiente stock de insumos para procesar la orden completa a la vez.", "warning")
                        return redirect(url_for("ventas.venta_online"))

            except Exception as e:
                print(f"Error calculado stock pre-pedido: {e}")
                flash("Ocurrió un error calculando el stock. Intenta de nuevo.", "danger")
                return redirect(url_for("ventas.venta_online"))
            
            u_id = session.get("usuarioId")
            c_id = session.get("clienteId")

            if u_id is None:
                flash("Tu sesión ha expirado. Por favor, vuelve a ingresar.", "danger")
                return redirect(url_for("auth.iniciarSesion"))

            if c_id is None:
                cliente = Cliente.query.filter_by(usuarioId=u_id).first()
                if cliente:
                    c_id = cliente.id
                    session["clienteId"] = c_id
                else:
                    nombreBase = (session.get("usuarioNombre") or session.get("usuarioCorreo") or "Cliente").split("@")[0].strip() or "Cliente"
                    cliente = Cliente(
                        usuarioId=u_id,
                        nombre=nombreBase,
                        apellidoPaterno="Pendiente",
                        apellidoMaterno="",
                        telefono="",
                        alias="",
                    )
                    db.session.add(cliente)
                    db.session.commit()
                    c_id = cliente.id
                    session["clienteId"] = c_id

       
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
                
                # Limpiamos carrito y la marca de edición
                session.pop("carrito", None)
                session.pop("editando_pedido_id", None)
                
                msg = "¡Pedido actualizado con éxito!" if id_pedido_editando else "¡Pedido confirmado! Te esperamos a la hora indicada."
                flash(msg, "success")
                return redirect(url_for("pedidos.mis_pedidos") if id_pedido_editando else url_for("ventas.venta_online"))

            except exc.IntegrityError:
                db.session.rollback()
                flash("Hubo un problema con tu cuenta de usuario. Contacta a soporte.", "danger")
            except exc.InternalError as e:
                db.session.rollback()
                error_msg = str(e.orig).split("'")[1] if "'" in str(e.orig) else "No hay stock suficiente para procesar la orden."
                flash(f"Aviso: {error_msg}", "warning")
            except Exception as e:
                db.session.rollback()
                flash("Lo sentimos, no pudimos procesar tu pedido en este momento.", "danger")
            
            return redirect(url_for("ventas.venta_online"))

    return render_template("ventas/online.html", form=form, lista_productos=productos)

@ventasBp.route("/reporte", methods=["GET"])
def generar_reporte():

    fecha_filtro = request.args.get('fecha') or request.args.get('creado_en')
    if not fecha_filtro:
        fecha_filtro = datetime.now().strftime('%Y-%m-%d')

    query = text("""
        SELECT v.id_venta, v.creado_en, v.metodo_pago, v.total, v.id_usuario
        FROM ventas v
        WHERE DATE(v.creado_en) = :f
    """)
    
    ventas = db.session.execute(query, {"f": fecha_filtro}).fetchall()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Folio', 'Fecha/Hora', 'Metodo Pago', 'Total', 'Atendio'])
    
    total_acumulado = 0
    for v in ventas:
        cw.writerow([f"UC-{v.id_venta}", v.creado_en, v.metodo_pago, v.total, f"Usuario #{v.id_usuario}"])
        total_acumulado += v.total
    
    cw.writerow([])
    cw.writerow(['', '', 'TOTAL DEL DIA:', total_acumulado])

   
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=Reporte_{fecha_filtro}.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output

@ventasBp.route("/<token>/pagar", methods=["GET", "POST"])
def pagar_venta_gestion(token): 
    
    try:
        idVenta = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("ventas.venta_fisica"))

    form = PagoForm()
    
    if request.method == "GET":
        try:
            
            result = db.session.execute(
                text("SELECT total FROM ventas WHERE id_venta = :id"), 
                {"id": idVenta}
            ).fetchone()
            
            if not result:
                flash("La venta no existe", "warning")
                return redirect(url_for("ventas.venta_fisica"))
            
            return render_template("ventas/pagar.html", 
                                 form=form, 
                                 idVenta=idVenta, 
                                 total=result[0])
        except Exception as e:
            print(f"Error GET pagar: {e}")
            return redirect(url_for("ventas.venta_fisica"))

    metodo = request.form.get("metodo_pago")
    
    try:
        db.session.execute(
            text("CALL pagar_venta(:id, :met)"), 
            {"id": idVenta, "met": metodo}
        )
        db.session.commit()
        
        flash(f"¡Venta #{idVenta} pagada con éxito!", "success")
        return redirect(url_for("ventas.ticket", token=get_serializer().dumps(idVenta)))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al procesar el pago: {str(e)}", "danger")
        return redirect(url_for("ventas.venta_fisica"))
    
@ventasBp.route("/ticket/<token>", methods=["GET", "POST"], endpoint="ticket")
def ticket(token):
    
    try:
        idVenta = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("ventas.venta_fisica"))
    
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
    return render_template("ventas/ticket.html", ticket=resultado)


