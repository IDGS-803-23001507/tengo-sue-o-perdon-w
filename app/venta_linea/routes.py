from flask import Blueprint, render_template
from model import Productoo

inicioBp = Blueprint('inicio', __name__)

@inicioBp.route("/productos")
def productos():

    productos = Productoo.query.filter(
        Productoo.estatus == True
    ).order_by(
        Productoo.tipo
    ).all()

    return render_template(
        "venta_linea/catalogo_productos.html",
        productos=productos
    )