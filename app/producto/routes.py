from flask import Blueprint, flash, redirect, render_template, request, url_for
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
    busqueda = request.args.get('q')
    categoria = request.args.get('categoria')
    
    query = Producto.query
    
    if busqueda:
        query = query.filter(Producto.nombre.ilike(f'%{busqueda}%'))
        
    if categoria and categoria != 'todos':
        query = query.filter(Producto.categoria == categoria)
        
    productos = query.all()    
        
    return render_template('venta_linea/catalogo_productos.html', productos=productos, busqueda=busqueda, categoria_actual=categoria)


