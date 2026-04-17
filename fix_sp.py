from flask import Flask
from config import Config
from model import db
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    with open("sp_cambiar_estado_pedido.sql", "r") as f:
        sp_def = f.read()

    # Fix 1: The validation check for "no active recipe" (LEFT JOIN Recetas without variant condition)
    old_check = """                            LEFT JOIN Recetas r\n                                ON r.id_producto = p.id_producto\n                               AND r.estado = 1\n                            WHERE dv.id_venta = v_id_venta\n                              AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'\n                            GROUP BY dv.id_producto\n                            HAVING COUNT(r.id_receta) = 0"""
    new_check = """                            LEFT JOIN Recetas r\n                                ON r.id_producto = p.id_producto\n                               AND r.estado = 1\n                               AND (dv.id_variante IS NULL AND r.id_variante IS NULL OR r.id_variante = dv.id_variante)\n                            WHERE dv.id_venta = v_id_venta\n                              AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'\n                            GROUP BY dv.id_producto\n                            HAVING COUNT(r.id_receta) = 0"""
    print("Fix 1 found?", old_check in sp_def)
    sp_def = sp_def.replace(old_check, new_check)

    # Fix 2: The reversal on cancellation (fallback case when no inventario_movimientos record exists)
    old_reversal = """                            JOIN Recetas r\n                                ON r.id_producto = p.id_producto\n                               AND r.estado = 1\n                            WHERE dv.id_venta = v_id_venta\n                              AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'\n                            GROUP BY r.id_materia"""
    new_reversal = """                            JOIN Recetas r\n                                ON r.id_producto = p.id_producto\n                               AND r.estado = 1\n                               AND (dv.id_variante IS NULL AND r.id_variante IS NULL OR r.id_variante = dv.id_variante)\n                            WHERE dv.id_venta = v_id_venta\n                              AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'\n                            GROUP BY r.id_materia"""
    print("Fix 2 found?", old_reversal in sp_def)
    sp_def = sp_def.replace(old_reversal, new_reversal)

    occurrences_after = sp_def.count("dv.id_variante IS NULL AND r.id_variante IS NULL OR r.id_variante = dv.id_variante")
    print(f"Occurrences after fix: {occurrences_after}")

    # Recreate the SP
    db.session.execute(text("DROP PROCEDURE IF EXISTS sp_cambiar_estado_pedido"))
    db.session.commit()
    db.session.execute(text(sp_def))
    db.session.commit()
    print("sp_cambiar_estado_pedido RECREATED with all fixes")

