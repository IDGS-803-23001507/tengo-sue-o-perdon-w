
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from model import db, Producto, Venta, DetalleVenta
from sqlalchemy import func
from datetime import datetime, timedelta
import forms
from decimal import Decimal
from xhtml2pdf import pisa
import io

utilidad_bp = Blueprint('utilidad', __name__)

@utilidad_bp.route('/utilidad')
def index():
    return redirect(url_for('utilidad.dashboard'))


@utilidad_bp.route('/utilidad/dashboard')
def dashboard():
   
    try:
      
        hoy = datetime.now().date()
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        inicio_mes = hoy.replace(day=1)

        ventas_hoy = Venta.query.filter(
            func.date(Venta.fecha) == hoy
        ).all()
        total_ventas_hoy = sum(float(v.total) for v in ventas_hoy) if ventas_hoy else 0
        
        costo_ventas_hoy = 0.0
        for venta in ventas_hoy:
            for detalle in venta.detalles:
                producto = Producto.query.get(detalle.id_producto)
                if producto:
                    costo_unitario = float(producto.costo_unitario())
                    costo_ventas_hoy += costo_unitario * detalle.cantidad
        
        utilidad_hoy = total_ventas_hoy - costo_ventas_hoy
        margen_hoy = (utilidad_hoy / total_ventas_hoy * 100) if total_ventas_hoy > 0 else 0
        
        ventas_semana = Venta.query.filter(
            func.date(Venta.fecha) >= inicio_semana
        ).all()
        total_ventas_semana = sum(float(v.total) for v in ventas_semana) if ventas_semana else 0

        ventas_mes = Venta.query.filter(
            func.date(Venta.fecha) >= inicio_mes
        ).all()
        total_ventas_mes = sum(float(v.total) for v in ventas_mes) if ventas_mes else 0

        productos = Producto.query.filter_by(estatus=True).all()
        
        productos_rentabilidad = []
        for producto in productos:
            if producto.precio_venta and producto.precio_venta > 0:
                productos_rentabilidad.append(producto.to_dict_rentabilidad())
        
        productos_rentabilidad.sort(key=lambda x: x['porcentaje'], reverse=True)
        top_rentables = productos_rentabilidad[:5]
        menos_rentables = productos_rentabilidad[-5:] if len(productos_rentabilidad) > 5 else []

    except Exception as e:
        flash(f'Error al conectar con la base de datos: {e}', 'error')
        total_ventas_hoy = costo_ventas_hoy = utilidad_hoy = margen_hoy = 0
        total_ventas_semana = total_ventas_mes = 0
        top_rentables = menos_rentables = []
    
    return render_template('utilidad/utilidad.html',
                          total_ventas_hoy=total_ventas_hoy,
                          costo_ventas_hoy=costo_ventas_hoy,
                          utilidad_hoy=utilidad_hoy,
                          margen_hoy=margen_hoy,
                          total_ventas_semana=total_ventas_semana,
                          total_ventas_mes=total_ventas_mes,
                          top_rentables=top_rentables,
                          menos_rentables=menos_rentables)


@utilidad_bp.route('/utilidad/reporte', methods=['GET', 'POST'])
def reporte():

    form = forms.FechasReporteForm(request.form)
    
    if not form.fecha_inicio.data:
        form.fecha_inicio.data = datetime.now().date() - timedelta(days=30)
    if not form.fecha_fin.data:
        form.fecha_fin.data = datetime.now().date()
    
    ventas = []
    resumen = {
        'total_ventas': 0,
        'total_costos': 0,
        'utilidad_bruta': 0,
        'margen_promedio': 0,
        'num_transacciones': 0,
        'productos_vendidos': 0
    }
    productos_detalle = {}
    
    if request.method == 'POST' and form.validate():
        fecha_inicio = form.fecha_inicio.data
        fecha_fin = form.fecha_fin.data
        
        ventas_query = Venta.query.filter(
            func.date(Venta.fecha) >= fecha_inicio,
            func.date(Venta.fecha) <= fecha_fin
        ).order_by(Venta.fecha.desc()).all()
        
        resumen['num_transacciones'] = len(ventas_query)
        
        for venta in ventas_query:
            costo_venta = 0.0
            productos_vendidos = []
            
            for detalle in venta.detalles:
                producto = Producto.query.get(detalle.id_producto)
                if producto:
                    costo_unitario = float(producto.costo_unitario())
                    costo_detalle = costo_unitario * detalle.cantidad
                    costo_venta += costo_detalle
                    
                    subtotal = float(detalle.cantidad) * float(producto.precio_venta or 0)
                    
                    productos_vendidos.append({
                        'nombre': producto.nombre,
                        'cantidad': float(detalle.cantidad),
                        'precio': float(producto.precio_venta) if producto.precio_venta else 0,
                        'subtotal': subtotal,
                        'costo': costo_detalle,
                        'utilidad': subtotal - costo_detalle
                    })

                    nombre_producto = producto.nombre
                    if nombre_producto not in productos_detalle:
                        productos_detalle[nombre_producto] = {
                            'cantidad': 0,
                            'ventas': 0,
                            'costo': 0,
                            'utilidad': 0
                        }
                    productos_detalle[nombre_producto]['cantidad'] += float(detalle.cantidad)
                    productos_detalle[nombre_producto]['ventas'] += subtotal
                    productos_detalle[nombre_producto]['costo'] += costo_detalle
                    productos_detalle[nombre_producto]['utilidad'] += subtotal - costo_detalle
                    
                    resumen['productos_vendidos'] += float(detalle.cantidad)
            
            ventas.append({
                'id': venta.id_venta,
                'fecha': venta.fecha.strftime('%d/%m/%Y %H:%M'),
                'total': float(venta.total),
                'costo': costo_venta,
                'utilidad': float(venta.total) - costo_venta,
                'metodo_pago': venta.metodo_pago,
                'productos': productos_vendidos
            })
            
            resumen['total_ventas'] += float(venta.total)
            resumen['total_costos'] += costo_venta
        
        resumen['utilidad_bruta'] = resumen['total_ventas'] - resumen['total_costos']
        if resumen['total_ventas'] > 0:
            resumen['margen_promedio'] = (resumen['utilidad_bruta'] / resumen['total_ventas']) * 100
        
        lista_productos = []
        for nombre, datos in productos_detalle.items():
            datos['nombre'] = nombre
            if datos['ventas'] > 0:
                datos['margen'] = (datos['utilidad'] / datos['ventas']) * 100
            else:
                datos['margen'] = 0
            lista_productos.append(datos)
        
        lista_productos.sort(key=lambda x: x['utilidad'], reverse=True)
        
        return render_template('utilidad/reporteUtilidad.html',
                              form=form,
                              ventas=ventas,
                              resumen=resumen,
                              productos_detalle=lista_productos,
                              fecha_inicio=fecha_inicio.strftime('%d/%m/%Y'),
                              fecha_fin=fecha_fin.strftime('%d/%m/%Y'))
    
    return render_template('utilidad/reporteUtilidad.html', form=form, ventas=[], resumen={}, productos_detalle=[])


@utilidad_bp.route('/utilidad/producto/<int:producto_id>')
def producto_detalle(producto_id):

    producto = Producto.query.get_or_404(producto_id)
    
    datos = producto.to_dict_rentabilidad()
    ventas_detalle = DetalleVenta.query.filter_by(id_producto=producto_id).all()
    total_vendido = sum(d.cantidad for d in ventas_detalle)
    total_ingresos = sum(float(d.subtotal) for d in ventas_detalle)
    
    total_costos = 0
    for detalle in ventas_detalle:
        producto_venta = Producto.query.get(detalle.id_producto)
        if producto_venta:
            costo_unitario = float(producto_venta.costo_unitario())
            total_costos += costo_unitario * detalle.cantidad
    
    return render_template('utilidad/productoDetalle.html',
                          producto=producto,
                          costo=datos['costo'],
                          margen=datos['margen'],
                          porcentaje=datos['porcentaje'],
                          total_vendido=float(total_vendido),
                          total_ingresos=float(total_ingresos),
                          total_costos=float(total_costos))

@utilidad_bp.route('/utilidad/reporte/pdf', methods=['POST'])
def reporte_pdf():

    form = forms.FechasReporteForm(request.form)

    if not form.validate():
        flash('Fechas inválidas para generar el PDF', 'error')
        return redirect(url_for('utilidad.reporte'))

    fecha_inicio = form.fecha_inicio.data
    fecha_fin    = form.fecha_fin.data

    ventas_query = Venta.query.filter(
        func.date(Venta.fecha) >= fecha_inicio,
        func.date(Venta.fecha) <= fecha_fin
    ).order_by(Venta.fecha.desc()).all()

    resumen = {
        'total_ventas': 0, 'total_costos': 0,
        'utilidad_bruta': 0, 'margen_promedio': 0,
        'num_transacciones': len(ventas_query),
        'productos_vendidos': 0
    }
    productos_detalle = {}
    ventas = []

    for venta in ventas_query:
        costo_venta = 0.0
        for detalle in venta.detalles:
            producto = Producto.query.get(detalle.id_producto)
            if producto:
                costo_unitario  = float(producto.costo_unitario())
                costo_detalle   = costo_unitario * detalle.cantidad
                
                costo_venta    += costo_detalle
                nombre_producto = producto.nombre
                
                subtotal = float(detalle.cantidad) * float(producto.precio_venta or 0)
                
                if nombre_producto not in productos_detalle:
                    productos_detalle[nombre_producto] = {
                        'cantidad': 0, 'ventas': 0, 'costo': 0, 'utilidad': 0
                    }
                
                productos_detalle[nombre_producto]['cantidad']  += float(detalle.cantidad)
                productos_detalle[nombre_producto]['ventas']    += subtotal
                productos_detalle[nombre_producto]['costo']     += costo_detalle
                productos_detalle[nombre_producto]['utilidad']  += subtotal - costo_detalle
                resumen['productos_vendidos'] += float(detalle.cantidad)

        ventas.append({
            'id':          venta.id_venta,
            'fecha':       venta.fecha.strftime('%d/%m/%Y %H:%M'),
            'total':       float(venta.total),
            'costo':       costo_venta,
            'utilidad':    float(venta.total) - costo_venta,
            'metodo_pago': venta.metodo_pago,
        })
        resumen['total_ventas']  += float(venta.total)
        resumen['total_costos']  += costo_venta

    resumen['utilidad_bruta'] = resumen['total_ventas'] - resumen['total_costos']
    if resumen['total_ventas'] > 0:
        resumen['margen_promedio'] = (resumen['utilidad_bruta'] / resumen['total_ventas']) * 100

    lista_productos = []
    for nombre, datos in productos_detalle.items():
        datos['nombre']  = nombre
        datos['margen']  = (datos['utilidad'] / datos['ventas'] * 100) if datos['ventas'] > 0 else 0
        lista_productos.append(datos)
    lista_productos.sort(key=lambda x: x['utilidad'], reverse=True)

    html_content = render_template(
        'utilidad/reporteUtilidad_pdf.html',
        ventas=ventas,
        resumen=resumen,
        productos_detalle=lista_productos,
        fecha_inicio=fecha_inicio.strftime('%d/%m/%Y'),
        fecha_fin=fecha_fin.strftime('%d/%m/%Y'),
        generado=datetime.now().strftime('%d/%m/%Y %H:%M')
    )

    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)
    pdf_buffer.seek(0)

    nombre_archivo = f"reporte_utilidad_{fecha_inicio}_{fecha_fin}.pdf"
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type']        = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}'
    return response