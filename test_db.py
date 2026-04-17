from flask import Flask
from config import Config
from model import db, MateriaPrima

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    for mp in MateriaPrima.query.filter(MateriaPrima.nombre.in_(["Harina de Trigo", "Levadura"])).all():
        print(f"MP: {mp.nombre} | Stock: {mp.stock_actual} | CostoProm: {mp.costo_promedio}")
