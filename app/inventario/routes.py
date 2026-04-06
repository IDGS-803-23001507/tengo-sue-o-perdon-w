from flask import Blueprint, flash, render_template, request
from sqlalchemy.exc import SQLAlchemyError

from forms import MateriaPrimaForm
from model import db, MateriaPrima, UnidadMedida 

inventario_bp = Blueprint('inventario', __name__)

@inventario_bp.route('/materias_primas')
def materias_primas():
    busqueda = request.args.get('q')
    
    if busqueda:
        insumos = MateriaPrima.query.filter(MateriaPrima.nombre.like(f'%{busqueda}%')).all()
    else:
        insumos = MateriaPrima.query.all()
    
    return render_template('inventario/materia_prima.html', insumos=insumos, busqueda=busqueda)

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

@inventario_bp.route('/editar-materia/<int:id>', methods=['GET', 'POST'])
def editar_materia(id):
    insumo = MateriaPrima.query.get_or_404(id)
    unidades_db = UnidadMedida.query.all()
    form = MateriaPrimaForm(obj=insumo)
    form.set_unidades(unidades_db)

    if request.method == 'GET':
        form.estatus.data = '1' if insumo.estatus else '0'

    if form.validate_on_submit():
        try:
            insumo.nombre = (form.nombre_insumo.data or '').strip()
            insumo.descripcion = (form.descripcion.data or '').strip() or None
            insumo.unidad_medida = form.unidad_medida.data
            insumo.stock_minimo = form.stock_minimo.data
            insumo.estatus = True if form.estatus.data == '1' else False
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