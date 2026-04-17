from flask import Flask
from config import Config
from model import db, Receta, MateriaPrima

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    # Ver qué insumos tiene la receta base del Cafe Expreso (id_variante=NULL)
    from sqlalchemy import text
    res = db.session.execute(text("""
        SELECT r.id_receta, mp.nombre, mp.tamanio, r.cantidad
        FROM Recetas r
        JOIN Materia_prima mp ON mp.id_materia = r.id_materia
        WHERE r.id_producto = (SELECT id_producto FROM Producto WHERE nombre = 'Cafe Expreso')
          AND r.id_variante IS NULL
          AND r.estado = 1
    """)).fetchall()
    for r in res:
        print(f"Receta #{r[0]} | {r[1]} | tamaño: {r[2]} | cantidad: {r[3]}")
