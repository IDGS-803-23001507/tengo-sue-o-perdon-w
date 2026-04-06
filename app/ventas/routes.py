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
from model import DetalleVenta, Producto, Venta, db

ventasBp = Blueprint("ventas", __name__)

@ventasBp.route("/tienda", methods=["GET"], endpoint="tienda_cliente")
def tiendaCliente():
	if not session.get("inicioSesion"):
		return redirect(url_for("auth.iniciarSesion"))

	if session.get("usuarioRol") != "Cliente":
		return redirect(url_for("index"))

	productos = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()
	return render_template("venta_linea/catalogo_productos.html", productos=productos)


@ventasBp.route("/ventas", methods=["GET"])
def ventas():

    fecha_filtro = request.args.get('creado_en')
    
    if not fecha_filtro:
        fecha_filtro = datetime.now().strftime('%Y-%m-%d')

    query = text("""
        SELECT * FROM Ventas 
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
    productos = Producto.query.filter_by(estatus=True).all()
    
    if request.method == "POST":
        
        if "agregar" in request.form:
            p_id = request.form.get("producto_id", type=int)
            prod = Producto.query.get(p_id)
            if prod:
                carrito = session.get("carrito", [])
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
                flash(f"Error: {str(e)}", "danger")
                return redirect(url_for("ventas.venta_fisica"))

    carrito = session.get("carrito", [])
    total = sum(item['precio'] * item['cantidad'] for item in carrito)
    return render_template("ventas/fisica.html", form=form, productos=productos, carrito=carrito, total=total)

@ventasBp.route("/online", methods=["GET", "POST"])
def venta_online():
     
    form = VentaForm()
    
    query_productos = text("""
        SELECT p.*, 
        CASE 
            WHEN EXISTS (
                SELECT 1 FROM Recetas r 
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia 
                WHERE r.id_producto = p.id_producto AND mp.stock_actual < r.cantidad
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
            carrito = session.get("carrito", [])
            if not carrito:
                flash("Carrito vacío", "warning")
                return redirect(url_for("ventas.venta_online"))

            hora_recogida_raw = request.form.get("hora_recogida")
            
            try:
                hora_pedido = datetime.strptime(hora_recogida_raw, '%Y-%m-%dT%H:%M')
                ahora = datetime.now()
         
                if hora_pedido.hour >= 24 or (hora_pedido.hour >= 23 and hora_pedido.minute > 59):
                    flash("Lo sentimos, la sucursal va a cerrar o ya está cerrada. Te sugerimos realizar tu pedido para el día de mañana.", "warning")
                    return redirect(url_for("ventas.venta_online"))


                if hora_pedido < (ahora + timedelta(minutes=25)):
                    flash("Requerimos al menos 30 minutos de anticipación para preparar tus productos con calidad.", "danger")
                    return redirect(url_for("ventas.venta_online"))

            except ValueError:
                flash("Formato de hora inválido.", "danger")
                return redirect(url_for("ventas.venta_online"))

            try:
                hora_pedido = datetime.strptime(hora_recogida_raw, '%Y-%m-%dT%H:%M')
                ahora = datetime.now()
                
                if hora_pedido.date() != ahora.date():
                    flash("Los pedidos online solo se pueden realizar para el día de hoy.", "danger")
                    return redirect(url_for("ventas.venta_online"))

                if hora_pedido < (ahora + timedelta(hours=2)):
                    flash("Para preparar tu pedido con calidad, requerimos al menos 1 hora de anticipación.", "danger")
                    return redirect(url_for("ventas.venta_online"))

            except ValueError:
                flash("El formato de fecha y hora no es correcto.", "danger")
                return redirect(url_for("ventas.venta_online"))
            
   
            u_id = session.get("usuarioId")
            c_id = session.get("clienteId")

            if u_id is None:
                flash("Tu sesión ha expirado. Por favor, vuelve a ingresar.", "danger")
                return redirect(url_for("auth.iniciarSesion"))

            id_venta_tracker = 0 
            
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
                session.pop("carrito", None)
                flash("¡Pedido confirmado! Te esperamos a la hora indicada.", "success")
                return redirect(url_for("ventas.venta_online"))

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
    fecha_filtro = request.args.get('creado_en')
    if not fecha_filtro:
        fecha_filtro = datetime.now().strftime('%Y-%m-%d')

    query = text("""
        SELECT v.id_venta, v.creado_en, v.metodo_pago, v.total, u.nombre as usuario
        FROM Ventas v
        JOIN Usuarios u ON v.id_usuario = u.id 
        WHERE DATE(v.creado_en) = :f
    """)
    
    ventas = db.session.execute(query, {"f": fecha_filtro}).fetchall()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Folio', 'Fecha/Hora', 'Metodo Pago', 'Total', 'Atendio']) # Encabezados
    
    total_acumulado = 0
    for v in ventas:
        cw.writerow([f"UC-{v.id_venta}", v.fecha, v.metodo_pago, v.total, v.usuario])
        total_acumulado += v.total
    
    cw.writerow([])
    cw.writerow(['', '', 'TOTAL DEL DIA:', total_acumulado])

   
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=Reporte_{fecha_filtro}.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output

@ventasBp.route("/<int:idVenta>/pagar", methods=["GET", "POST"])
def pagar_venta_gestion(idVenta): 
    
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
        return redirect(url_for("ventas.ticket", idVenta=idVenta))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al procesar el pago: {str(e)}", "danger")
        return redirect(url_for("ventas.venta_fisica"))
    
@ventasBp.route("/ticket/<int:idVenta>", methods=["GET", "POST"], endpoint="ticket")
def ticket(idVenta):
    query = text("""
        SELECT 
            v.id_venta, v.creado_en, v.metodo_pago, v.total,
            c.nombre AS cliente,
            p.nombre AS producto,
            dv.cantidad,
            (dv.cantidad * dv.precio_unitario) AS subtotal
        FROM Ventas v
        JOIN Detalle_venta dv ON v.id_venta = dv.id_venta
        JOIN Producto p ON dv.id_producto = p.id_producto
        LEFT JOIN Clientes c ON v.id_cliente = c.id
        WHERE v.id_venta = :idVenta
    """)
    
    resultado = db.session.execute(query, {"idVenta": idVenta}).fetchall()

    return render_template("ventas/ticket.html", ticket=resultado)

#####################################################################################
