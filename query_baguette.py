from flask import Flask
from config import Config
from model import db, Producto, Receta, MateriaPrima

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    prods = Producto.query.filter(Producto.nombre.ilike("%bagu%")).all()
    for p in prods:
        print(f"Producto: {p.nombre}")
        recetas = Receta.query.filter_by(id_producto=p.id_producto).all()
        for r in recetas:
            mp = MateriaPrima.query.get(r.id_materia)
            print(f" - Insumo: {mp.nombre} | Cantidad en Receta: {r.cantidad} {mp.unidad.abreviacion if mp.unidad else ''} | Costo Global MP: ${mp.costo_promedio}")
