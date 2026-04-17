from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime

from model import db, PedidoProveedor, PedidoProveedorDetalle, Proveedores, MateriaPrima
from forms import PedidoProveedorForm, DesactivarForm
from model import EstadoPedidoProveedor

pedidoProv_bp = Blueprint('pedido_proveedor', __name__, url_prefix='/pedidos-proveedor')

@pedidoProv_bp.route('/', methods=['GET'])
def listar_pedidos():

    pedidos = PedidoProveedor.query.order_by(
        PedidoProveedor.fecha_solicitud.desc()
    ).all()

    form = DesactivarForm()
    
    return render_template(
        'pedido_proveedor/listar.html',
        pedidos=pedidos,
        active_page='pedido_proveedor',
        form=form
    )
    
@pedidoProv_bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo_pedido():

    form = PedidoProveedorForm()

    proveedores = Proveedores.query.all()
    materias = MateriaPrima.query.filter_by(estatus=True).all()

    form.id_proveedor.choices = [
        (p.id, p.nombre) for p in proveedores
    ]

    print(form.detalles.data)
    for d in form.detalles:
        d.id_materia.choices = [
            (m.id_materia, m.nombre) for m in materias
        ]

    if form.validate_on_submit():
        try:

            pedido = PedidoProveedor(
                id_proveedor=form.id_proveedor.data,
                id_usuario=session.get("usuarioId"),
                estado=EstadoPedidoProveedor.PENDIENTE,
                notas=form.notas.data
            )

            for d in form.detalles.data:
                detalle = PedidoProveedorDetalle(
                    id_materia=d["id_materia"],
                    cantidad_solicitada=d["cantidad_solicitada"],
                    costo_unitario_est=d.get("costo_unitario_est")
                )
                pedido.detalles.append(detalle)

            db.session.add(pedido)
            db.session.commit()

            flash("Pedido creado correctamente", "success")
            return redirect(url_for('pedido_proveedor.listar_pedidos'))

        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")

    return render_template(
        'pedido_proveedor/nuevo.html',
        form=form,
        materias=materias
    )
    
@pedidoProv_bp.route('/<int:id>', methods=['GET'])
def ver_pedido(id):

    pedido = PedidoProveedor.query.get_or_404(id)

    return render_template(
        'pedido_proveedor/detalle.html',
        pedido=pedido
    )
    
@pedidoProv_bp.route('/<int:id>/cancelar', methods=['POST'])
def cancelar_pedido(id):

    pedido = PedidoProveedor.query.get_or_404(id)

    if pedido.estado != EstadoPedidoProveedor.PENDIENTE:
        flash("No se puede cancelar este pedido", "warning")
        return redirect(url_for('pedido_proveedor.listar_pedidos'))

    try:
        pedido.estado = EstadoPedidoProveedor.CANCELADO
        db.session.commit()

        flash("Pedido cancelado", "success")

    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for('pedido_proveedor.listar_pedidos'))

@pedidoProv_bp.route('/<int:id>/generar-compra', methods=['GET'])
def generar_compra(id):

    pedido = PedidoProveedor.query.get_or_404(id)

    if pedido.estado != EstadoPedidoProveedor.PENDIENTE:
        flash("Este pedido no se puede procesar", "warning")
        return redirect(url_for('pedido_proveedor.listar_pedidos'))

    return redirect(url_for('compras.nueva_compra', pedido_id=id))