from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from model import DetalleVenta, Producto, Venta, db

ventasBp = Blueprint("ventas", __name__, url_prefix="/ventas")


@ventasBp.route("/tienda", methods=["GET"], endpoint="tienda_cliente")
def tiendaCliente():
	if not session.get("inicioSesion"):
		return redirect(url_for("auth.iniciarSesion"))

	if session.get("usuarioRol") not in {"Cliente", "Cajero"}:
		return redirect(url_for("index"))

	productos = Producto.query.filter_by(estatus=True).order_by(Producto.nombre.asc()).all()
	return render_template("venta_linea/catalogo_productos.html", productos=productos)


@ventasBp.route("/comprar", methods=["POST"], endpoint="comprar_producto")
def comprarProducto():
	if not session.get("inicioSesion"):
		return redirect(url_for("auth.iniciarSesion"))

	if session.get("usuarioRol") not in {"Cliente", "Cajero"}:
		return redirect(url_for("index"))

	productoId = request.form.get("productoId", type=int)
	cantidad = request.form.get("cantidad", type=int, default=1)

	if not productoId or not cantidad or cantidad <= 0:
		flash("Selecciona un producto y una cantidad válida.", "danger")
		return redirect(url_for("ventas.tienda_cliente"))

	producto = Producto.query.get(productoId)
	if not producto or not producto.estatus:
		flash("El producto no está disponible.", "danger")
		return redirect(url_for("ventas.tienda_cliente"))

	if producto.stockActual < cantidad:
		flash("No hay stock suficiente para completar la compra.", "danger")
		return redirect(url_for("ventas.tienda_cliente"))

	precioUnitario = Decimal(str(producto.precio))
	subtotal = (precioUnitario * Decimal(cantidad)).quantize(Decimal("0.01"))
	costoUnitario = (precioUnitario * Decimal("0.58")).quantize(Decimal("0.01"))
	utilidadBruta = ((precioUnitario - costoUnitario) * Decimal(cantidad)).quantize(Decimal("0.01"))

	venta = Venta(
		usuarioId=session.get("usuarioId"),
		total=subtotal,
		utilidadBruta=utilidadBruta,
		confirmada=True,
		origen="ONLINE",
	)
	db.session.add(venta)
	db.session.flush()

	detalle = DetalleVenta(
		ventaId=venta.id_venta,
		productoId=producto.id_producto,
		cantidad=cantidad,
		precioUnitario=precioUnitario,
		costoUnitario=costoUnitario,
		subtotal=subtotal,
	)
	db.session.add(detalle)

	producto.stockActual -= cantidad
	db.session.commit()

	flash("Compra realizada correctamente.", "success")
	return redirect(url_for("ventas.tienda_cliente"))