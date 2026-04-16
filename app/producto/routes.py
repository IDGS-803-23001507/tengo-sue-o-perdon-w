from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from forms import ProductoTerminadoForm, ProductoTerminadoEditarForm, DesactivarForm
from model import db, Producto, Receta

from itsdangerous import URLSafeSerializer
from flask import current_app

producto_bp = Blueprint('producto', __name__)

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

        nuevo_producto = Producto(
            nombre=form.nombre.data.strip(),
            categoria=form.categoria.data.lower(),
            precio_venta=float(form.precio_venta.data),
            tipo_preparacion=form.tipo_preparacion.data,
            imagen=imagen_base64,
            descripcion=form.descripcion.data,
        )

        db.session.add(nuevo_producto)
        db.session.commit()

        pendientes = set(session.get('productos_pendientes_receta', []))
        pendientes.add(nuevo_producto.id_producto)
        session['productos_pendientes_receta'] = list(pendientes)

        flash('Producto registrado. Ahora captura su receta.', 'success')
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
        producto.nombre = form.nombre.data.strip()
        producto.categoria = form.categoria.data
        producto.precio_venta = float(form.precio_venta.data)
        producto.tipo_preparacion = form.tipo_preparacion.data
        producto.descripcion = form.descripcion.data
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
        FROM Producto p
        WHERE p.estatus = 1
          AND (:busqueda = '' OR p.nombre LIKE :busqueda_like)
          AND (:categoria = 'todos' OR p.categoria = :categoria)
        ORDER BY p.nombre ASC
    """)

    productos = db.session.execute(
        query_productos,
        {
            'busqueda': busqueda,
            'busqueda_like': f"%{busqueda}%",
            'categoria': categoria,
        },
    ).fetchall()

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