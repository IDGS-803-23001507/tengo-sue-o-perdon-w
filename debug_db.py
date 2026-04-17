from flask import Flask
from config import Config
from model import db, Producto, MateriaPrima, Receta

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    productos_borrador = Producto.query.filter_by(estado_producto='borrador').all()
    for p in productos_borrador:
        print(f"Producto: {p.nombre}")
        costo_total = 0
        for r in p.recetas:
            if r.estado:
                costo = r.materiaPrima.costo_promedio or 0
                cant = r.cantidad or 0
                print(f" - Receta: {r.id_materia} -> {r.materiaPrima.nombre}, costo: {costo}, cantidad: {cant}")
                costo_total += costo * cant
        print(f" Costo Unitario calculado por db: {p.costo_unitario()} - vs script: {costo_total}")
