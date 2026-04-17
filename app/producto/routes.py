from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text, inspect
from forms import ProductoTerminadoForm, ProductoTerminadoEditarForm, DesactivarForm
from model import db, Producto, Receta
from app.food_cost_service import recalcular_precio_producto

from itsdangerous import URLSafeSerializer
from flask import current_app

producto_bp = Blueprint('producto', __name__)


def _stock_reservado_expr() -> str:
    """Devuelve una expresion SQL segura para stock reservado segun el esquema actual."""
    columnas = {c["name"] for c in inspect(db.engine).get_columns("Producto")}
    return "COALESCE(p.stock_reservado, 0)" if "stock_reservado" in columnas else "0"

def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

@producto_bp.route('/catalogo')
def producto_index():
    busqueda = request.args.get('q')
    categoria = request.args.get('categoria')
    filtro_stock = (request.args.get('stock') or 'todos').strip().lower()
    
    form = DesactivarForm()
    
    query = Producto.query
    
    if busqueda:
        query = query.filter(Producto.nombre.ilike(f'%{busqueda}%'))
        
    if categoria and categoria != 'todos':
        query = query.filter(Producto.categoria == categoria)

    if filtro_stock == 'con_stock':
        query = query.filter(
            Producto.tipo_preparacion == 'stock',
            Producto.stock > 0,
        )
    elif filtro_stock == 'sin_stock':
        query = query.filter(
            Producto.tipo_preparacion == 'stock',
            Producto.stock <= 0,
        )
        
    productos = query.all()    
        
    mostrar_stock = any(p.tipo_preparacion == 'stock' for p in productos)
        
    return render_template('productos/productos.html', active_page = 'producto', 
                           form = form, productos=productos, busqueda=busqueda, 
                           mostrar_stock=mostrar_stock, categoria_actual=categoria,
                           stock_actual=filtro_stock)


@producto_bp.route('/nuevo_producto', methods=['GET', 'POST'])
def nuevo_producto():
    form = ProductoTerminadoForm()

    if form.validate_on_submit():
        imagen_base64 = (form.imageBase64.data or '').strip() or None

        if imagen_base64 and len(imagen_base64) > 2_000_000:
            flash('La imagen es demasiado grande', 'danger')
            return render_template('productos/nuevo_producto.html', mostrar_modal=False, form=form)

        precio = float(form.precio_venta.data) if form.precio_venta.data else None
        target_fc = float(form.target_food_cost.data) if form.target_food_cost.data else 0.30

        nuevo_producto = Producto(
            nombre=form.nombre.data.strip(),
            categoria=form.categoria.data.lower(),
            precio_venta=precio,
            tipo_preparacion=form.tipo_preparacion.data,
            imagen=imagen_base64,
            descripcion=form.descripcion.data,
            estado_producto='borrador',
            target_food_cost=target_fc,
        )

        db.session.add(nuevo_producto)
        db.session.commit()

        pendientes = set(session.get('productos_pendientes_receta', []))
        pendientes.add(nuevo_producto.id_producto)
        session['productos_pendientes_receta'] = list(pendientes)

        flash('Producto registrado en borrador. Ahora captura su receta para activarlo.', 'success')
        return redirect(url_for('recetas.nueva', producto=nuevo_producto.id_producto, nuevo_producto=1))

    if request.method == 'POST':
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break

    return render_template('productos/nuevo_producto.html', mostrar_modal=False, form=form)


@producto_bp.route('/productos/<int:id_producto>/descartar_pendiente', methods=['GET'])
def descartar_producto_pendiente(id_producto):
    
    pendientes = set(session.get('productos_pendientes_receta', []))
    if id_producto not in pendientes:
        return redirect(url_for('producto.producto_index'))

    producto = Producto.query.get_or_404(id_producto)
    tiene_receta_activa = Receta.query.filter_by(id_producto=id_producto, estado=True).first() is not None

    if tiene_receta_activa:
        pendientes.discard(id_producto)
        session['productos_pendientes_receta'] = list(pendientes)
        flash('El producto ya tiene receta asociada y no se descartó.', 'info')
        return redirect(url_for('producto.producto_index'))

    try:
        Receta.query.filter_by(id_producto=id_producto).delete(synchronize_session=False)
        db.session.delete(producto)
        db.session.commit()

        pendientes.discard(id_producto)
        session['productos_pendientes_receta'] = list(pendientes)
        flash('Producto descartado porque no se registró receta.', 'info')

    except Exception:
        db.session.rollback()
        flash('No se pudo descartar el producto pendiente.', 'danger')

    return redirect(url_for('producto.producto_index'))


@producto_bp.route('/editar_producto/<token>', methods=['GET', 'POST'])
def editar_producto(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("producto.producto_index"))
    
    producto = Producto.query.get_or_404(id)
    form = ProductoTerminadoEditarForm(obj=producto)

    if form.validate_on_submit():
        old_target = producto.target_food_cost
        
        producto.nombre = form.nombre.data.strip()
        producto.categoria = form.categoria.data
        producto.tipo_preparacion = form.tipo_preparacion.data
        producto.descripcion = form.descripcion.data
        
        new_target = float(form.target_food_cost.data) if form.target_food_cost.data else 0.30
        producto.target_food_cost = new_target
        
        # Decision: If the target changed, we ignore any manual price input and force a recalculation
        if float(old_target) != float(new_target):
            recalcular_precio_producto(producto, commit=False)
            flash('Food Cost re-calculado y actualizado.', 'info')
        else:
            # If the user manually edited the price and target did NOT change, respect manual price
            if form.precio_venta.data is not None:
                producto.precio_venta = float(form.precio_venta.data)
                
        db.session.commit()
        
        return render_template('productos/editar_producto.html', mostrar_modal=True, producto=producto, form=form)

    if request.method == 'POST':
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break
    
    return render_template('productos/editar_producto.html', mostrar_modal=False, producto=producto, form=form)

@producto_bp.route('/productos/<token>')
def detalle_producto(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("producto.producto_index"))
    
    producto = db.get_or_404(Producto, id)

    return render_template(
        'productos/detalles_producto.html',
        producto=producto
    )

@producto_bp.route('/catalogo_venta')
def producto_venta():
    busqueda = (request.args.get('q') or '').strip()
    categoria = (request.args.get('categoria') or 'todos').strip()
    stock_reservado_expr = _stock_reservado_expr()

    query_productos = text(f"""
        SELECT p.*, 
        CASE 
            WHEN COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock' THEN
                CASE WHEN (COALESCE(p.stock, 0) - {stock_reservado_expr}) > 0 THEN 1 ELSE 0 END
            WHEN EXISTS (
                SELECT 1 FROM Recetas r 
                JOIN Materia_prima mp ON r.id_materia = mp.id_materia 
                WHERE r.id_producto = p.id_producto AND r.estado = 1 AND mp.stock_actual < r.cantidad
            ) THEN 0 ELSE 1 
        END as disponible_stock
        FROM Producto p
        WHERE p.estatus = 1
          AND (:busqueda = '' OR p.nombre LIKE :busqueda_like)
          AND (:categoria = 'todos' OR p.categoria = :categoria)
        ORDER BY p.nombre ASC
    """)

    productos_raw = db.session.execute(
        query_productos,
        {
            'busqueda': busqueda,
            'busqueda_like': f"%{busqueda}%",
            'categoria': categoria,
        },
    ).fetchall()
    
    from model import Receta, MateriaPrima, VarianteReceta
    recetas_activas = (
        Receta.query
        .filter_by(estado=True)
        .join(MateriaPrima, Receta.id_materia == MateriaPrima.id_materia)
        .all()
    )
    stock_por_variante = {}
    stock_receta_base = {}
    for receta in recetas_activas:
        mp = receta.materiaPrima
        if mp:
            if receta.id_variante is not None:
                stock_por_variante.setdefault(receta.id_variante, []).append((float(mp.stock_actual or 0), float(receta.cantidad)))
            else:
                stock_receta_base.setdefault(receta.id_producto, []).append((float(mp.stock_actual or 0), float(receta.cantidad)))

    variantes_por_producto_online = {}
    variantes = VarianteReceta.query.filter_by(estado=True).all()
    for v in variantes:
        insumos_variante = stock_por_variante.get(v.id_variante, [])
        variante_ok = all(s >= c for s, c in insumos_variante) if insumos_variante else True
        variantes_por_producto_online.setdefault(v.id_producto, []).append({"disponible": variante_ok})
        
    for id_producto, insumos_base in stock_receta_base.items():
        if id_producto in variantes_por_producto_online:
            base_ok = all(s >= c for s, c in insumos_base) if insumos_base else True
            variantes_por_producto_online[id_producto].append({"disponible": base_ok})

    productos_con_disponibilidad = []
    for prod in productos_raw:
        prod_dict = dict(prod._mapping)
        variantes_prod = variantes_por_producto_online.get(prod_dict["id_producto"], [])
        if variantes_prod:
            prod_dict["disponible_stock"] = 1 if any(v["disponible"] for v in variantes_prod) else 0
        productos_con_disponibilidad.append(prod_dict)

    from types import SimpleNamespace
    productos = [SimpleNamespace(**d) for d in productos_con_disponibilidad]

    return render_template('venta_linea/catalogo_productos.html', productos=productos, busqueda=busqueda, categoria_actual=categoria)

@producto_bp.route('/productos/desactivar/<token>', methods=['POST'])
def desactivar_producto(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("producto.producto_index"))
    
    producto = db.get_or_404(Producto, id)
    form = DesactivarForm()

    if form.validate_on_submit():
        try:
            producto.estatus = False

            recetas = Receta.query.filter_by(id_producto=producto.id_producto).all()
            for receta in recetas:
                receta.estado = False

            db.session.commit()
            flash(f'Producto {producto.nombre} y sus recetas desactivados.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error al desactivar el producto: {str(e)}', 'error')
    else:
        flash('Solicitud inválida.', 'error')

    return redirect(url_for('producto.producto_index'))

@producto_bp.route('/productos/reactivar/<token>', methods=['POST'])
def reactivar_producto(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("producto.producto_index"))
    
    producto = db.get_or_404(Producto, id)
    form = DesactivarForm()

    if form.validate_on_submit():
        try:
            producto.estatus = True
            
            recetas = Receta.query.filter_by(id_producto=producto.id_producto).all()
            for receta in recetas:
                receta.estado = True

            db.session.commit()
            flash(f'Producto {producto.nombre} y sus recetas reactivados.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error al reactivar el producto: {str(e)}', 'error')
    else:
        flash('Solicitud inválida.', 'error')

    return redirect(url_for('producto.producto_index'))