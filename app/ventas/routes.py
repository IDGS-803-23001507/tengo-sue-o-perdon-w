from functools import wraps
from forms import VentaForm, PagoForm
from sqlalchemy import text, exc, inspect
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


def _stock_reservado_expr() -> str:
    """Devuelve una expresion SQL segura para stock reservado segun el esquema actual."""
    columnas = {c["name"] for c in inspect(db.engine).get_columns("Producto")}
    return "COALESCE(p.stock_reservado, 0)" if "stock_reservado" in columnas else "0"

def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

@ventasBp.route("/tienda", methods=["GET"], endpoint="tienda_cliente")
def tiendaCliente():
    if not session.get("inicioSesion"):
        return redirect(url_for("auth.iniciarSesion"))

    if session.get("usuarioRol") != "Cliente":
        return redirect(url_for("index"))

    stock_reservado_expr = _stock_reservado_expr()
    query_productos = text(f"""
        SELECT p.*, 
        CASE 
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE 
                    WHEN (COALESCE(p.stock, 0) - {stock_reservado_expr}) > 0 THEN 1 
                    WHEN EXISTS (SELECT 1 FROM Recetas r WHERE r.id_producto = p.id_producto AND r.estado = 1) 
                         AND NOT EXISTS (
                             SELECT 1 FROM Recetas r
                             JOIN Materia_prima mp ON r.id_materia = mp.id_materia
                             WHERE r.id_producto = p.id_producto AND r.estado = 1
                               AND mp.stock_actual < r.cantidad
                         ) THEN 1
                    ELSE 0 
                END
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
    stock_reservado_expr = _stock_reservado_expr()
    # Query base: para productos de tipo stock o sin variantes
    query_productos = text(f"""
        SELECT p.*,
        CASE
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE 
                    WHEN (COALESCE(p.stock, 0) - {stock_reservado_expr}) > 0 THEN 1 
                    WHEN EXISTS (SELECT 1 FROM Recetas r WHERE r.id_producto = p.id_producto AND r.estado = 1) 
                         AND NOT EXISTS (
                             SELECT 1 FROM Recetas r
                             JOIN Materia_prima mp ON r.id_materia = mp.id_materia
                             WHERE r.id_producto = p.id_producto AND r.estado = 1
                               AND mp.stock_actual < r.cantidad
                         ) THEN 1
                    ELSE 0 
                END
            WHEN EXISTS (
                SELECT 1 FROM Recetas r
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia
                WHERE r.id_producto = p.id_producto AND r.estado = 1
                  AND mp.stock_actual < r.cantidad
            ) THEN 0 ELSE 1
        END as disponible_stock
        FROM Producto p WHERE p.estatus = 1
    """)
    productos_raw = db.session.execute(query_productos).fetchall()

    # Mapa: id_producto -> lista de insumos para tooltip en el POS
    insumos_por_producto = {}
    # Mapa: id_producto -> lista de variantes {id, nombre, precio_extra}
    variantes_por_producto = {}

    from model import Receta, MateriaPrima, VarianteReceta
    recetas_activas = (
        Receta.query
        .filter_by(estado=True)
        .join(MateriaPrima, Receta.id_materia == MateriaPrima.id_materia)
        .all()
    )
    # Mapa: id_variante -> lista de (stock_actual, cantidad_necesaria)
    stock_por_variante: dict[int, list[tuple]] = {}
    stock_receta_base: dict[int, list[tuple]] = {}
    # Mapa: id_producto -> nombre del tamaño de la receta base (ej. "Mediano")
    nombre_base_producto: dict[int, str] = {}
    
    for receta in recetas_activas:
        mp = receta.materiaPrima
        if mp:
            label = mp.nombre
            if label not in insumos_por_producto.setdefault(receta.id_producto, []):
                insumos_por_producto[receta.id_producto].append(label)
            
            if receta.id_variante is not None:
                # Excluir insumos tipo "contenedor" (vasos, tazas) del chequeo de stock:
                # si tiene tamaño (ej. "12oz") es un vaso/recipiente, no un insumo líquido/sólido
                if not mp.tamanio:
                    stock_por_variante.setdefault(receta.id_variante, []).append(
                        (float(mp.stock_actual or 0), float(receta.cantidad))
                    )
            else:
                if not mp.tamanio:
                    stock_receta_base.setdefault(receta.id_producto, []).append(
                        (float(mp.stock_actual or 0), float(receta.cantidad))
                    )
                # Si el insumo tiene tamaño definido, usarlo como nombre de la variante base
                if mp.tamanio and receta.id_producto not in nombre_base_producto:
                    nombre_base_producto[receta.id_producto] = mp.tamanio

    variantes = VarianteReceta.query.filter_by(estado=True).order_by(
        VarianteReceta.id_producto.asc(), VarianteReceta.id_variante.asc()
    ).all()
    for v in variantes:
        insumos_variante = stock_por_variante.get(v.id_variante, [])
        # Una variante está disponible si TODOS sus insumos tienen stock suficiente
        variante_ok = all(stock >= cantidad for stock, cantidad in insumos_variante) if insumos_variante else True
        variantes_por_producto.setdefault(v.id_producto, []).append({
            "id": v.id_variante,
            "nombre": v.nombre,
            "precio_extra": float(v.precio_extra) if v.precio_extra else 0,
            "disponible": variante_ok,
        })
        
    for id_producto, insumos_base in stock_receta_base.items():
        if id_producto in variantes_por_producto:
            # El producto tiene variantes extra. Agregar la receta base como opción
            # El nombre será el tamaño del insumo (ej. "Mediano") o "Regular" si no hay tamaño
            base_ok = all(stock >= cant for stock, cant in insumos_base) if insumos_base else True
            nombre_base = nombre_base_producto.get(id_producto, "Regular")
            # Buscar el precio_venta del producto para la receta base
            from model import Producto as ProductoModel
            prod_obj = ProductoModel.query.get(id_producto)
            precio_base_val = float(prod_obj.precio_venta) if (prod_obj and prod_obj.precio_venta) else 0
            variantes_por_producto[id_producto].insert(0, {
                "id": "",
                "nombre": nombre_base,
                "precio_extra": precio_base_val,
                "disponible": base_ok,
            })

    # Sobreescribir disponible_stock para productos con variantes usando lógica Python pura
    productos_con_disponibilidad = []
    for prod in productos_raw:
        prod_dict = dict(prod._mapping)
        variantes_prod = variantes_por_producto.get(prod_dict["id_producto"], [])
        if variantes_prod:
            # Disponible si al menos UNA variante tiene insumos
            prod_dict["disponible_stock"] = 1 if any(v["disponible"] for v in variantes_prod) else 0
            # Si el precio del producto es 0 o nulo, usar el precio mínimo de sus variantes
            precios_variantes = [v["precio_extra"] for v in variantes_prod if v.get("precio_extra", 0) > 0]
            if precios_variantes and not prod_dict.get("precio_venta"):
                prod_dict["precio_venta"] = min(precios_variantes)
        productos_con_disponibilidad.append(prod_dict)

    # Convertir a objetos con acceso por atributo
    from types import SimpleNamespace
    productos = [SimpleNamespace(**d) for d in productos_con_disponibilidad]
    
    if request.method == "POST":
        
        if "agregar" in request.form:
            p_id = request.form.get("producto_id", type=int)
            prod = Producto.query.get(p_id)
            if prod:
                carrito = session.get("carrito", [])
                
                # Determinamos la variante si la hay

                id_variante = request.form.get("variante_id", type=int)  # None si no hay variantes
                nombre_variante = request.form.get("variante_nombre", "").strip()
                precio_variante = request.form.get("variante_precio", 0.0, type=float)

                # Si viene precio de variante calculado (absoluto), usarlo; si no, el precio base del producto
                precio_final = precio_variante if precio_variante > 0 else float(prod.precio_venta or 0)

                carrito.append({
                    "id_producto": p_id,
                    "nombre": prod.nombre + (f" ({nombre_variante})" if nombre_variante else ""),
                    "precio": precio_final,
                    "cantidad": 1,
                    "id_variante": id_variante,
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
                costo_total_carrito = 0.0
                
                for item in carrito:
                    result = db.session.execute(
                        text("CALL crear_venta_general(:u, :c, :tipo, :p, :can, :v_id, :var_id)"),
                        {
                            "u": session.get("usuarioId"),
                            "c": None,
                            "tipo": "fisica",
                            "p": item["id_producto"],
                            "can": item["cantidad"],
                            "v_id": id_venta_actual,
                            "var_id": item.get("id_variante"),
                        }
                    )
                    row = result.fetchone()
                    if row:
                        id_venta_actual = row[0]
                        
                    # Extraemos el costo vivo del producto para desplazar el 35% del Store Procedure
                    prod = Producto.query.get(item["id_producto"])
                    if prod:
                        costo_total_carrito += float(prod.costo_unitario()) * int(item["cantidad"])

                if id_venta_actual > 0:
                    venta = Venta.query.get(id_venta_actual)
                    if venta:
                        utilidad_real = float(venta.total) - costo_total_carrito
                        venta.utilidadBruta = utilidad_real

                db.session.commit()
                
                session["carrito"] = [] 
                session.pop("carrito", None) 
                session.modified = True 
                
                return redirect(url_for("ventas.pagar_venta_gestion", idVenta=id_venta_actual))
                
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
        variantes_por_producto=variantes_por_producto,
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
    stock_reservado_expr = _stock_reservado_expr()
    
    # Consulta de productos con validación de stock en tiempo real
    query_productos = text(f"""
        SELECT p.*,
        CASE
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE 
                    WHEN (COALESCE(p.stock, 0) - {stock_reservado_expr}) > 0 THEN 1 
                    WHEN EXISTS (SELECT 1 FROM Recetas r WHERE r.id_producto = p.id_producto AND r.estado = 1) 
                         AND NOT EXISTS (
                             SELECT 1 FROM Recetas r
                             JOIN Materia_prima mp ON r.id_materia = mp.id_materia
                             WHERE r.id_producto = p.id_producto AND r.estado = 1
                               AND mp.stock_actual < r.cantidad
                         ) THEN 1
                    ELSE 0 
                END
            WHEN EXISTS (
                SELECT 1 FROM Recetas r
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia
                WHERE r.id_producto = p.id_producto AND r.estado = 1
                  AND mp.stock_actual < r.cantidad
            ) THEN 0 ELSE 1
        END as disponible_stock
        FROM Producto p WHERE p.estatus = 1
    """)
    productos_raw = db.session.execute(query_productos).fetchall()

    from model import Receta, MateriaPrima, VarianteReceta
    recetas_activas = (
        Receta.query
        .filter_by(estado=True)
        .join(MateriaPrima, Receta.id_materia == MateriaPrima.id_materia)
        .all()
    )
    stock_por_variante: dict[int, list[tuple]] = {}
    stock_receta_base: dict[int, list[tuple]] = {}
    nombre_base_producto_online: dict[int, str] = {}
    
    for receta in recetas_activas:
        mp = receta.materiaPrima
        if mp:
            if receta.id_variante is not None:
                stock_por_variante.setdefault(receta.id_variante, []).append(
                    (float(mp.stock_actual or 0), float(receta.cantidad))
                )
            else:
                stock_receta_base.setdefault(receta.id_producto, []).append(
                    (float(mp.stock_actual or 0), float(receta.cantidad))
                )
                if mp.tamanio and receta.id_producto not in nombre_base_producto_online:
                    nombre_base_producto_online[receta.id_producto] = mp.tamanio

    variantes_por_producto_online = {}
    variantes = VarianteReceta.query.filter_by(estado=True).order_by(
        VarianteReceta.id_producto.asc(), VarianteReceta.id_variante.asc()
    ).all()
    
    for v in variantes:
        insumos_variante = stock_por_variante.get(v.id_variante, [])
        variante_ok = all(stock >= cantidad for stock, cantidad in insumos_variante) if insumos_variante else True
        variantes_por_producto_online.setdefault(v.id_producto, []).append({
            "id": v.id_variante,
            "nombre": v.nombre,
            "precio_extra": float(v.precio_extra) if v.precio_extra else 0,
            "disponible": variante_ok,
        })
        
    for id_producto, insumos_base in stock_receta_base.items():
        if id_producto in variantes_por_producto_online:
            base_ok = all(stock >= cant for stock, cant in insumos_base) if insumos_base else True
            nombre_base = nombre_base_producto_online.get(id_producto, "Regular")
            from model import Producto as ProductoModel
            prod_obj = ProductoModel.query.get(id_producto)
            precio_base_val = float(prod_obj.precio_venta) if (prod_obj and prod_obj.precio_venta) else 0
            variantes_por_producto_online[id_producto].insert(0, {
                "id": "",
                "nombre": nombre_base,
                "precio_extra": precio_base_val,
                "disponible": base_ok,
            })

    productos_con_disponibilidad = []
    for prod in productos_raw:
        prod_dict = dict(prod._mapping)
        variantes_prod = variantes_por_producto_online.get(prod_dict["id_producto"], [])
        if variantes_prod:
            prod_dict["disponible_stock"] = 1 if any(v["disponible"] for v in variantes_prod) else 0
            # Si el precio del producto es 0 o nulo, usar el precio mínimo de sus variantes
            precios_variantes = [v["precio_extra"] for v in variantes_prod if v.get("precio_extra", 0) > 0]
            if precios_variantes and not prod_dict.get("precio_venta"):
                prod_dict["precio_venta"] = min(precios_variantes)
        productos_con_disponibilidad.append(prod_dict)

    from types import SimpleNamespace
    productos = [SimpleNamespace(**d) for d in productos_con_disponibilidad]

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
            
            id_variante = request.form.get("variante_id", type=int)
            nombre_variante = request.form.get("variante_nombre", "").strip()
            precio_variante = request.form.get("variante_precio", 0.0, type=float)
            
            # Si viene precio de variante (absoluto calculado), usarlo; si no, el precio base
            precio_final = precio_variante if precio_variante > 0 else precio
            nombre_display = f"{nombre} ({nombre_variante})" if nombre_variante else nombre
            
            carrito = session.get("carrito", [])
            carrito.append({
                "id_producto": int(prod_id),
                "cantidad": cant,
                "nombre": nombre_display,
                "precio": precio_final,
                "id_variante": id_variante,
            })
            session["carrito"] = carrito
            session.modified = True
            flash(f"¡{nombre} añadido!", "success")
            return redirect(url_for("ventas.venta_online"))
        
        # --- FINALIZAR PEDIDO (VALIDACIÓN Y REGISTRO PREVIO) ---
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
                
            # Lógica de Validación de Stock Agrupada
            try:
                from collections import defaultdict
                consumo_materia = defaultdict(float)
                consumo_stock_directo = defaultdict(int)

                for item in carrito:
                    p_id = item["id_producto"]
                    q = item["cantidad"]
                    v_id = item.get("id_variante")
                    
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
                        consumo_stock_directo[p_id] += q
                        if int(stock_actual or 0) < consumo_stock_directo[p_id]:
                            # Falta stock físico. Verificamos si tiene receta para descontar insumos en su lugar.
                            query_receta = text("""
                                SELECT id_materia, cantidad 
                                FROM Recetas 
                                WHERE id_producto = :pid AND (id_variante = :vid OR id_variante IS NULL) AND estado = 1
                            """)
                            recetas = db.session.execute(query_receta, {"pid": p_id, "vid": v_id}).fetchall()
                            if not recetas:
                                flash(f"Stock físico insuficiente y no tiene receta para preparar el producto '{p_nombre}'.", "warning")
                                return redirect(url_for("ventas.venta_online"))
                                
                            # Si sí tiene receta, agregamos el faltante a consumo de materia prima
                            faltante = consumo_stock_directo[p_id] - int(stock_actual or 0)
                            for r_materia, r_cantidad in recetas:
                                consumo_materia[r_materia] += float(r_cantidad * faltante)
                            
                            # Ajustamos el consumo directo de stock al máximo disponible
                            consumo_stock_directo[p_id] = int(stock_actual or 0)
                    else:
                        if v_id is None:
                            query_receta = text("""
                                SELECT id_materia, cantidad 
                                FROM Recetas 
                                WHERE id_producto = :pid AND id_variante IS NULL AND estado = 1
                            """)
                        else:
                            query_receta = text("""
                                SELECT id_materia, cantidad 
                                FROM Recetas 
                                WHERE id_producto = :pid AND id_variante = :vid AND estado = 1
                            """)
                            
                        recetas = db.session.execute(query_receta, {"pid": p_id, "vid": v_id}).fetchall()
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
                costo_total_carrito = 0.0

                for item in carrito:
                    result = db.session.execute(
                        text("CALL crear_venta_online(:u, :c, :h, :n, :p, :can, :v_ex, :var_id)"),
                        {
                            "u": u_id, "c": c_id,
                            "h": hora_recogida_raw,
                            "n": request.form.get("notas", ""),
                            "p": item["id_producto"], "can": item["cantidad"],
                            "v_ex": id_venta_tracker,
                            "var_id": item.get("id_variante"),
                        }
                    ).fetchone()
                    
                    if result:
                        id_venta_tracker = result[0]
                        
                    # Extraemos el costo computado real
                    prod = Producto.query.get(item["id_producto"])
                    if prod:
                        costo_total_carrito += float(prod.costo_unitario()) * int(item["cantidad"])
                        
                # Sobreescribimos el 35% por default de MySQL
                if id_venta_tracker > 0:
                    venta = Venta.query.get(id_venta_tracker)
                    if venta:
                        utilidad_real = float(venta.total) - costo_total_carrito
                        venta.utilidadBruta = utilidad_real
                
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
                flash(f"No pudimos procesar tu pedido. Error: {str(e)}", "danger")
            
            return redirect(url_for("ventas.venta_online"))

    # Construir variantes_por_producto para el template online
    from model import VarianteReceta as VR
    variantes_por_producto_online = {}
    for v in VR.query.filter_by(estado=True).order_by(VR.id_variante.asc()).all():
        variantes_por_producto_online.setdefault(v.id_producto, []).append({
            "id": v.id_variante,
            "nombre": v.nombre,
            "precio_extra": float(v.precio_extra) if v.precio_extra else 0,
        })

    return render_template(
        "ventas/online.html",
        form=form,
        lista_productos=productos,
        variantes_por_producto=variantes_por_producto_online,
    )

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


