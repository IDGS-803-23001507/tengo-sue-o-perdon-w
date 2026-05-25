from flask import ( Blueprint, render_template, request, redirect, url_for, flash, session)
from model import Productoo, db, DetallePedidoo, Pedidoo
from model import Cliente, Usuario
from functools import wraps

def requiereRol(rolRequerido: str):
    def decorador(funcionVista):
        @wraps(funcionVista)
        def envuelta(*args, **kwargs):
            if not session.get("inicioSesion"):
                return redirect(url_for("auth.iniciarSesion"))
            rolSesion = session.get("usuarioRol")
            equivalencias = {
                "Cliente": {"Cliente"},
                }
            rolesPermitidos = equivalencias.get(rolRequerido, {rolRequerido})
            if rolSesion not in rolesPermitidos:
                flash("porfavor de iniciar sesion.", "danger")
                return redirect(url_for("dashboard_operador"))
            return funcionVista(*args, **kwargs)
        return envuelta
    return decorador

pedidosBp = Blueprint("pedidos", __name__,url_prefix="/pedidos")

@pedidosBp.route("/", methods=["GET"])
def index():
    productos = Productoo.query.filter(
        Productoo.estatus == True
    ).all()

    return render_template(
        "venta_linea/ordenar.html",
        productos=productos
    )
    
@pedidosBp.route("/mis-pedidos")
def mis_pedidos():

    usuario_id = session.get("usuarioId")

    usuario = Usuario.query.get(usuario_id)

    cliente = usuario.cliente

    pedidosDB = Pedidoo.query.filter_by(
        idCliente=cliente.id
    ).order_by(
        Pedidoo.fecha.desc()
    ).all()
    pedidos = []
    
    for pedido in pedidosDB:
        detallesDB = DetallePedidoo.query.filter_by(
            idPedido=pedido.idPedido
        ).all()
        
        detalles = []

        for detalle in detallesDB:
            producto = Productoo.query.get(
                detalle.idProducto
            )

            detalles.append({
                "nombre_producto": producto.nombre,
                "cantidad": detalle.cantidad,
                "precio_unitario": float(
                    detalle.precio
                )
            })
            
        pedidos.append({
            "id_pedido": pedido.idPedido,
            "fecha": pedido.fecha,
            "estado": pedido.estado,
            "total": float(pedido.total),
            "notas": pedido.notas,
            "detalles": detalles

        })

    return render_template( "venta_linea/mis_pedidos.html", pedidos=pedidos)

@pedidosBp.route("/agregar-carrito", methods=["POST"])
def agregar_carrito():
    idProducto = request.form.get(
        "idProducto",
        type=int
    )
    cantidad = request.form.get(
        "cantidad",
        type=int
    )

    if not idProducto or cantidad < 1:
        flash(
            "Datos inválidos.",
            "danger"
        )

        return redirect(
            url_for("pedidos.index")
        )

    producto = Productoo.query.get_or_404(
        idProducto
    )

    carrito = session.get(
        "carrito",
        []
    )

    productoExistente = next(
        (
            item for item in carrito
            if item["idProducto"] == idProducto
        ),
        None
    )
    if productoExistente:
        productoExistente["cantidad"] += cantidad

    else:

        carrito.append({
            "idProducto": producto.idProducto,
            "nombre": producto.nombre,
            "precio": float(producto.precio),
            "cantidad": cantidad,
            "foto": producto.foto

        })
    session["carrito"] = carrito
    session.modified = True
    
    return redirect(
        url_for("pedidos.index")
    )

@pedidosBp.route("/eliminar-carrito", methods=["POST"])
def eliminar_carrito():

    index = request.form.get("index", type=int)
    carrito = session.get(
        "carrito", 
        [])

    if (
        index is not None
        and 0 <= index < len(carrito)
    ):
        carrito.pop(index)
        session["carrito"] = carrito
        session.modified = True

    return redirect(
        url_for("pedidos.index")
    )

@pedidosBp.route("/vaciar-carrito", methods=["POST"])
def vaciar_carrito():
    session.pop("carrito",None)
   
    return redirect(
        url_for("pedidos.index")
    )

@pedidosBp.route("/finalizar", methods=["POST"])
@requiereRol("Cliente")
def finalizar():

    carrito = session.get(
        "carrito",
        []
    )

    if not carrito:
        flash(
            "El carrito está vacío.",
            "danger"
        )

        return redirect(
            url_for("pedidos.index")
        )
        
    try:
        notas = request.form.get(
            "notas"
        )
        
        total = sum(
            item["precio"] * item["cantidad"]
            for item in carrito
        )

        usuario_id = session.get("usuarioId")

        usuario = Usuario.query.get(usuario_id)

        cliente = usuario.cliente

        pedido = Pedidoo(
        idCliente=cliente.id,
        total=total,
        notas=notas,
        estado="Pendiente"
    )
        db.session.add(pedido)
        db.session.flush()
        
        for item in carrito:

            detalle = DetallePedidoo(
                idPedido=pedido.idPedido,
                idProducto=item["idProducto"],
                cantidad=item["cantidad"],
                precio=item["precio"]
            )
            db.session.add(detalle)
        db.session.commit()
        
        session.pop(
            "carrito",
            None)

        flash(
            "Pedido realizado correctamente.",
            "success"
        )

        return redirect(
            url_for("pedidos.index")
        )

    except Exception as e:
        db.session.rollback()
        print(e)

        flash(
            "Error al procesar el pedido.",
            "danger")
        
        return redirect(
            url_for("pedidos.index"))