from flask import Blueprint, render_template, request
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

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        categoria = request.form.get('categoria', '').strip()
        precio_venta = request.form.get('precio_venta')
        descripcion = request.form.get('descripcion')
        imagen_base64 = request.form.get('imageBase64') or None

        if not nombre or not categoria or not precio_venta:
            return render_template(
                'productos/nuevo_producto.html',
                mostrar_modal=False,
                error="Todos los campos son obligatorios"
            )
        if imagen_base64 and len(imagen_base64) > 2_000_000:
            return render_template('productos/nuevo_producto.html',
                                    mostrar_modal=False,
                                    error="La imagen es demasiado grande"
    )

        try:
            precio_venta = float(precio_venta)
        except ValueError:
            return render_template(
                'productos/nuevo_producto.html',
                mostrar_modal=False,
                error="El precio debe ser un número válido"
            )

        nuevo_producto = Producto(
            nombre=nombre,
            categoria=categoria.lower(), 
            precio_venta=precio_venta,
            imagen=imagen_base64,
            descripcion = descripcion
        )

        db.session.add(nuevo_producto)
        db.session.commit()

        return render_template(
            'productos/nuevo_producto.html',
            mostrar_modal=True
        )

    return render_template(
        'productos/nuevo_producto.html',
        mostrar_modal=False
    )


@producto_bp.route('/editar_producto/<int:id>', methods=['GET', 'POST'])
def editar_producto(id):
    producto = Producto.query.get_or_404(id)

    if request.method == 'POST':
        producto.nombre = request.form.get('nombre')
        producto.categoria = request.form.get('categoria')
        producto.precio_venta = request.form.get('precio_venta')
        producto.descripcion = request.form.get('descripcion')
        estatus_form = request.form.get('estatus')
        producto.estatus = True if estatus_form == '1' else False
        db.session.commit()
        
        return render_template('productos/editar_producto.html', mostrar_modal=True, producto=producto)
    
    return render_template('productos/editar_producto.html', mostrar_modal=False, producto=producto)

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


