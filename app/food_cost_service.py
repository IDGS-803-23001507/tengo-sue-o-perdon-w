"""
Servicio centralizado de Food Cost.

Contiene la lógica de negocio para:
  - Recalcular el precio de un producto a partir de su receta (Evento A).
  - Propagar recálculos en cascada cuando cambia el costo de una materia prima (Evento B).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from model import Producto, Receta, db

if TYPE_CHECKING:
    pass


def recalcular_precio_producto(producto: Producto, commit: bool = True) -> None:
    """Evento A: Calcula el precio_venta con food cost y cambia estado a 'activo'.

    Se invoca después de guardar/editar la receta de un producto.
    Solo recalcula si el producto tiene al menos una receta activa.
    """
    tiene_receta_activa = Receta.query.filter_by(
        id_producto=producto.id_producto,
        estado=True,
    ).first()

    if not tiene_receta_activa:
        return

    # Recalcular precio base del producto (basado solo en la receta base id_variante=None)
    precio_calculado = producto.calcular_precio_food_cost()

    if precio_calculado > 0:
        producto.precio_venta = precio_calculado
        producto.estado_producto = "activo"
    # Si el costo es 0 (sin receta base o costo_promedio=0), NO sobreescribimos el precio existente

    # Recalcular precio de las variantes activas
    from model import VarianteReceta
    variantes = VarianteReceta.query.filter_by(id_producto=producto.id_producto, estado=True).all()
    for var in variantes:
        precio_var_calc = var.calcular_precio_food_cost()
        # Solo actualizamos si el cálculo produce un precio real (> 0).
        # Si costo_promedio es 0 (sin compras registradas), conservamos el precio anterior.
        if precio_var_calc > 0:
            var.precio_extra = precio_var_calc

    # Si el producto no tiene receta base pero sí tiene variantes con precios,
    # usar el precio mínimo de variante como precio_venta del producto (para la tarjeta del POS)
    if not (precio_calculado > 0):
        precios_variantes = [
            var.precio_extra for var in variantes
            if var.precio_extra and var.precio_extra > 0
        ]
        if precios_variantes:
            producto.precio_venta = min(precios_variantes)
            producto.estado_producto = "activo"

    if commit:
        db.session.commit()


def recalcular_productos_por_materia(id_materia: int, commit: bool = True) -> list[int]:
    """Evento B (Cascada): Recalcula precios de todos los productos que usen esta materia prima.

    Se invoca cuando cambia el costo_promedio de una MateriaPrima (ej. al registrar compra).
    Retorna lista de IDs de productos actualizados.
    """
    # Buscar productos únicos que usen esta materia prima en recetas activas
    recetas_afectadas = (
        Receta.query
        .filter_by(id_materia=id_materia, estado=True)
        .all()
    )

    ids_productos = list({r.id_producto for r in recetas_afectadas})

    if not ids_productos:
        return []

    ids_actualizados = []
    for id_producto in ids_productos:
        producto = Producto.query.get(id_producto)
        if not producto:
            continue

        precio_anterior = producto.precio_venta
        estado_anterior = producto.estado_producto
        
        # Unificar la lógica invocando el método de evaluación general (sin commit individual)
        recalcular_precio_producto(producto, commit=False)

        # Si el precio mutó o destrabamos el producto de borrador a activo, marcar el cambio
        if producto.precio_venta != precio_anterior or producto.estado_producto != estado_anterior:
            ids_actualizados.append(id_producto)

    if commit and ids_actualizados:
        db.session.commit()

    return ids_actualizados
