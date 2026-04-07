from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import text
from forms import ProductoTerminadoForm, ProductoTerminadoEditarForm
from model import db, Producto

producto_bp = Blueprint('producto', __name__)

@producto_bp.route('/catalogo')
def producto_index():
    busqueda = request.args.get('q')
    categoria = request.args.get('categoria')
    
    query = Producto.query
    
    if busqueda:
        query = query.filter(Producto.nombre.ilike(f'%{busqueda}%'))
        
    if categoria and categoria != 'todos':
        query = query.filter(Producto.categoria == categoria)
        
    productos = query.all()    
        
    return render_template('productos/productos.html', productos=productos, busqueda=busqueda, categoria_actual=categoria)


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

        flash('Producto registrado. Ahora captura su receta.', 'success')
        return redirect(url_for('recetas.nueva', producto=nuevo_producto.id_producto))

    if request.method == 'POST':
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break

    return render_template('productos/nuevo_producto.html', mostrar_modal=False, form=form)


@producto_bp.route('/editar_producto/<int:id>', methods=['GET', 'POST'])
def editar_producto(id):
    producto = Producto.query.get_or_404(id)
    form = ProductoTerminadoEditarForm(obj=producto)

    if request.method == 'GET':
        form.estatus.data = '1' if producto.estatus else '0'

    if form.validate_on_submit():
        producto.nombre = form.nombre.data.strip()
        producto.categoria = form.categoria.data
        producto.precio_venta = float(form.precio_venta.data)
        producto.tipo_preparacion = form.tipo_preparacion.data
        producto.descripcion = form.descripcion.data
        producto.estatus = form.estatus.data == '1'
        db.session.commit()
        
        return render_template('productos/editar_producto.html', mostrar_modal=True, producto=producto, form=form)

    if request.method == 'POST':
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break
    
    return render_template('productos/editar_producto.html', mostrar_modal=False, producto=producto, form=form)

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


