from flask import Blueprint, render_template, request
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
    
    if request.method == 'POST':
        nombre = request.form.get('nombre_insumo')
        descripcion = request.form.get('descripcion')
        unidad_medida = request.form.get('unidad_medida') 
        stock_minimo = request.form.get('stock_minimo')

        nuevo_insumo = MateriaPrima(
            nombre=nombre,
            descripcion=descripcion,
            unidad_medida=unidad_medida, 
            stock_minimo=stock_minimo,
            stock_actual=0.0 
        )

        db.session.add(nuevo_insumo)
        db.session.commit()
        
        return render_template('inventario/nueva_materia.html', mostrar_modal=True, unidades=unidades_db)
    
    return render_template('inventario/nueva_materia.html', mostrar_modal=False, unidades=unidades_db)

@inventario_bp.route('/editar-materia/<int:id>', methods=['GET', 'POST'])
def editar_materia(id):
    insumo = MateriaPrima.query.get_or_404(id)
    unidades_db = UnidadMedida.query.all() 

    if request.method == 'POST':
        insumo.nombre = request.form.get('nombre_insumo')
        insumo.descripcion = request.form.get('descripcion')
        insumo.unidad_medida = request.form.get('unidad_medida')
        insumo.stock_minimo = request.form.get('stock_minimo')
        estatus_form = request.form.get('estatus')
        insumo.estatus = True if estatus_form == '1' else False
        db.session.commit()
        
        return render_template('inventario/editar_materia.html', mostrar_modal=True, insumo=insumo, unidades=unidades_db)
    
    return render_template('inventario/editar_materia.html', mostrar_modal=False, insumo=insumo, unidades=unidades_db)