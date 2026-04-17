from flask import Blueprint, flash, render_template, request, url_for, redirect
from sqlalchemy.exc import SQLAlchemyError

from forms import MateriaPrimaForm, DesactivarForm
from model import db, MateriaPrima, UnidadMedida 

from itsdangerous import URLSafeSerializer
from flask import current_app

inventario_bp = Blueprint('inventario', __name__)

def get_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"])

@inventario_bp.route('/materias_primas')
def materias_primas():
    form = DesactivarForm()
    busqueda = request.args.get('q')
    
    if busqueda:
        insumos = MateriaPrima.query.filter(MateriaPrima.nombre.like(f'%{busqueda}%')).all()
    else:
        insumos = MateriaPrima.query.all()
    
    return render_template('inventario/materia_prima.html', form=form, insumos=insumos, busqueda=busqueda)

@inventario_bp.route('/nueva-materia', methods=['GET', 'POST'])
def nueva_materia():
    unidades_db = UnidadMedida.query.all()
    form = MateriaPrimaForm()
    form.set_unidades(unidades_db)
    
    if form.validate_on_submit():
        try:
            nuevo_insumo = MateriaPrima(
                nombre=(form.nombre_insumo.data or "").strip(),
                descripcion=(form.descripcion.data or "").strip() or None,
                tamanio=(form.tamanio.data or "").strip() or None,
                unidad_medida=form.unidad_medida.data,
                stock_minimo=form.stock_minimo.data,
                stock_actual=0.0,
            )

            db.session.add(nuevo_insumo)
            db.session.commit()

            return render_template('inventario/nueva_materia.html', mostrar_modal=True, form=form)
        except SQLAlchemyError:
            db.session.rollback()
            flash('No se pudo guardar la materia prima. Inténtalo de nuevo.', 'danger')

    if request.method == 'POST':
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break

    return render_template('inventario/nueva_materia.html', mostrar_modal=False, form=form)

@inventario_bp.route('/editar-materia/<token>', methods=['GET', 'POST'])
def editar_materia(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("inventario.materias_primas"))
    
    insumo = MateriaPrima.query.get_or_404(id)
    unidades_db = UnidadMedida.query.all()
    form = MateriaPrimaForm(obj=insumo)
    form.set_unidades(unidades_db)

    if request.method == 'GET':
        form.nombre_insumo.data = insumo.nombre
        form.tamanio.data = insumo.tamanio or ''

    if form.validate_on_submit():
        try:
            insumo.nombre = (form.nombre_insumo.data or '').strip()
            insumo.descripcion = (form.descripcion.data or '').strip() or None
            insumo.tamanio = (form.tamanio.data or '').strip() or None
            insumo.unidad_medida = form.unidad_medida.data
            insumo.stock_minimo = form.stock_minimo.data
            db.session.commit()

            return render_template('inventario/editar_materia.html', mostrar_modal=True, insumo=insumo, form=form)
        except SQLAlchemyError:
            db.session.rollback()
            flash('No se pudo actualizar la materia prima.', 'danger')

    if request.method == 'POST':
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], 'danger')
                break

    return render_template('inventario/editar_materia.html', mostrar_modal=False, insumo=insumo, form=form)


@inventario_bp.route('/materia-prima/desactivar/<token>', methods=['POST'])
def desactivar_materia(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("inventario.materias_primas"))
 
    insumo = MateriaPrima.query.get_or_404(id)
    form = DesactivarForm()

    if form.validate_on_submit():
        try:
            insumo.estatus = False  
            db.session.commit()
            flash(f'La materia prima "{insumo.nombre}" ha sido desactivada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al desactivar la materia prima: {str(e)}', 'danger')
    else:
        flash('Solicitud de seguridad inválida.', 'danger')

    return redirect(url_for('inventario.materias_primas'))


@inventario_bp.route('/materia-prima/reactivar/<token>', methods=['POST'])
def reactivar_materia(token):
    
    try:
        id = get_serializer().loads(token)
    except Exception:
        return redirect(url_for("inventario.materias_primas"))
    
    insumo = MateriaPrima.query.get_or_404(id)
    form = DesactivarForm()

    if form.validate_on_submit():
        try:
            insumo.estatus = True  
            db.session.commit()
            flash(f'La materia prima "{insumo.nombre}" ha sido reactivada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al reactivar la materia prima: {str(e)}', 'danger')
    else:
        flash('Solicitud de seguridad inválida.', 'danger')

    return redirect(url_for('inventario.materias_primas'))