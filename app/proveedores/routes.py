from flask import render_template, request, redirect, url_for, flash, Blueprint
from model import db, Proveedores
from sqlalchemy.exc import DataError, IntegrityError
from forms import ProveedorForm, DesactivarForm

from itsdangerous import URLSafeSerializer
from flask import current_app

proveedor_bp = Blueprint('proveedor', __name__)


def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

@proveedor_bp.route('/proveedores')
def proveedores():
    busqueda = request.args.get('busqueda', '')
    estado = request.args.get('estado', 'activos')

    query = Proveedores.query

    if busqueda:
        query = query.filter(
            db.or_(
                Proveedores.nombre.ilike(f'%{busqueda}%'),
                Proveedores.rfc.ilike(f'%{busqueda}%')
            )
        )

    if estado == 'todos':
        proveedores_list = query.order_by(Proveedores.nombre).all()
    elif estado == 'inactivos':
        proveedores_list = query.filter(Proveedores.estado == False).order_by(Proveedores.nombre).all()
    else: 
        proveedores_list = query.filter(Proveedores.estado == True).order_by(Proveedores.nombre).all()

    form = DesactivarForm()

    return render_template(
        'proveedores/proveedores.html',
        proveedores=proveedores_list,
        busqueda=busqueda,
        estado=estado,
        active_page = 'proveedores',
        form=form
    )

@proveedor_bp.route('/proveedores/nuevo', methods=['GET', 'POST'])
def nuevo_proveedor():
    
    form = ProveedorForm()

    if form.validate_on_submit():
        existente = Proveedores.query.filter_by(rfc=form.rfc.data.upper()).first()
        if existente:
            flash(f'Ya existe un proveedor con el RFC {form.rfc.data}', 'error')
        else:
            try:
                proveedor = Proveedores(
                    nombre=form.nombre.data,
                    rfc=form.rfc.data.upper(),
                    telefono=form.telefono.data or None,
                    email=form.email.data or None,
                    colonia = form.colonia.data,
                    calle = form.calle.data,
                    num_exterior = form.num_exterior.data
                )
                
                db.session.add(proveedor)
                db.session.commit()
                
                flash(f'Proveedor {proveedor.nombre} registrado exitosamente', 'success')
                return redirect(url_for('proveedor.proveedores'))
            
            except IntegrityError:
                db.session.rollback()
                flash('Error: No se pudo registrar el proveedor. Verifica los datos.', 'error')
            except DataError:
                db.session.rollback()
                flash('Error: Uno o más campos exceden la longitud permitida.', 'error')

    return render_template('proveedores/nuevo_proveedor.html', form=form)


@proveedor_bp.route('/proveedores/detalle/<token>')
def detalle_proveedor(token):

    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("proveedor.proveedores"))
    
    proveedor = db.get_or_404(Proveedores, id)
    return render_template('proveedores/detalle_proveedor.html', proveedor=proveedor)


@proveedor_bp.route('/proveedores/modificar/<token>', methods=['GET', 'POST'])
def modificar_proveedor(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("proveedor.proveedores"))

    proveedor = db.get_or_404(Proveedores, id)
    form = ProveedorForm(obj=proveedor)

    if form.validate_on_submit():
        existente = Proveedores.query.filter(
            Proveedores.rfc == form.rfc.data.upper(),
            Proveedores.id != id
        ).first()

        if existente:
            flash(f'Ya existe otro proveedor con el RFC {form.rfc.data}', 'error')
        else:
            try:
                proveedor.nombre    = form.nombre.data
                proveedor.rfc       = form.rfc.data.upper()
                proveedor.telefono  = form.telefono.data or None
                proveedor.email     = form.email.data or None
                proveedor.colonia   = form.colonia.data
                proveedor.calle     = form.calle.data or None
                proveedor.num_exterior   = form.num_exterior.data
                
                db.session.commit()
                flash(f'Proveedor {proveedor.nombre} actualizado exitosamente', 'success')
                return redirect(url_for('proveedor.proveedores'))
            
            except IntegrityError:
                db.session.rollback()
                flash('Error: No se pudo actualizar el proveedor.', 'error')
            except DataError:
                db.session.rollback()
                flash('Error: Uno o más campos exceden la longitud permitida.', 'error')

    return render_template('proveedores/modificar_proveedor.html', form=form, proveedor=proveedor)


@proveedor_bp.route('/proveedores/eliminar/<token>', methods=['POST'])
def eliminar_proveedor(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("proveedor.proveedores"))
    
    proveedor = db.get_or_404(Proveedores, id)
    form = DesactivarForm()

    if form.validate_on_submit():
        try:
            proveedor.estado = False
            db.session.commit()
            flash(f'Proveedor {proveedor.nombre} desactivado exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al desactivar el proveedor: {str(e)}', 'error')
    else:
        flash('Solicitud inválida.', 'error')

    return redirect(url_for('proveedor.proveedores'))
    

@proveedor_bp.route('/proveedores/reactivar/<token>', methods=['POST'])
def reactivar_proveedor(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("proveedor.proveedores"))
    
    proveedor = db.get_or_404(Proveedores, id)
    form = DesactivarForm()

    if form.validate_on_submit():
        try:
            proveedor.estado = True
            db.session.commit()
            flash(f'Proveedor {proveedor.nombre} reactivado exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al reactivar el proveedor: {str(e)}', 'error')
    else:
        flash('Solicitud inválida.', 'error')

    return redirect(url_for('proveedor.proveedores'))