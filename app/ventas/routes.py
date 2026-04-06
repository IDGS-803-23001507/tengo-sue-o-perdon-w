from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.auditoria import registrar_auditoria
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

	if int(producto.stock or 0) < cantidad:
		flash("No hay stock suficiente para completar la compra.", "danger")
		return redirect(url_for("ventas.tienda_cliente"))

	precioUnitario = Decimal(str(producto.precio_venta or 0))
	subtotal = (precioUnitario * Decimal(cantidad)).quantize(Decimal("0.01"))
	costoUnitario = (precioUnitario * Decimal("0.58")).quantize(Decimal("0.01"))
	utilidadBruta = ((precioUnitario - costoUnitario) * Decimal(cantidad)).quantize(Decimal("0.01"))

	venta = Venta(
		id_usuario=session.get("usuarioId"),
		total=subtotal,
		utilidadBruta=utilidadBruta,
		confirmada=True,
		origen="ONLINE",
		tipo_venta="Mostrador",
		metodo_pago="Efectivo",
	)
	db.session.add(venta)
	db.session.flush()

	detalle = DetalleVenta(
		id_venta=venta.id_venta,
		id_producto=producto.id_producto,
		cantidad=cantidad,
		precio_unitario=precioUnitario,
		descuento=Decimal("0.00"),
	)
	db.session.add(detalle)

	producto.stock = int(producto.stock or 0) - int(cantidad)

	registrar_auditoria(
		accion="Venta Confirmada",
		modulo="Ventas",
		detalles={"id_venta": venta.id_venta, "id_producto": producto.id_producto, "cantidad": cantidad, "total": str(subtotal)},
		commit=False,
	)
	db.session.commit()

	flash("Compra realizada correctamente.", "success")
	return redirect(url_for("ventas.tienda_cliente"))


@ventasBp.route("/cancelar/<int:id_venta>", methods=["POST"], endpoint="cancelar_venta")
def cancelarVenta(id_venta: int):
	if not session.get("inicioSesion"):
		return redirect(url_for("auth.iniciarSesion"))

	if session.get("usuarioRol") not in {"Cajero", "Gerente", "Gerente de Tienda", "Admin General (TI)", "Admin General"}:
		flash("No tienes permisos para cancelar ventas.", "danger")
		return redirect(url_for("index"))

	venta = Venta.query.get_or_404(id_venta)

	if not venta.confirmada:
		flash("La venta ya estaba cancelada.", "info")
		return redirect(url_for("ventas.tienda_cliente"))

	try:
		for detalle in venta.detalles:
			producto = Producto.query.get(detalle.id_producto)
			if producto:
				producto.stock = int(producto.stock or 0) + int(detalle.cantidad or 0)

		venta.confirmada = False

		registrar_auditoria(
			accion="Cancelación de Venta",
			modulo="Ventas",
			detalles={"id_venta": venta.id_venta, "total": str(venta.total)},
			commit=False,
		)

		db.session.commit()
		flash("Venta cancelada correctamente.", "success")
	except SQLAlchemyError:
		db.session.rollback()
		flash("No se pudo cancelar la venta.", "danger")

	return redirect(url_for("ventas.tienda_cliente"))