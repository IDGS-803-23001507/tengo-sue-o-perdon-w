from decimal import Decimal
import json

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import or_, text
from sqlalchemy.exc import SQLAlchemyError

from app.usuarios.routes import requiereRol
from app.auditoria import registrar_auditoria
from forms import RecetaForm, RecetaLoteForm
from model import MateriaPrima, Producto, Receta, db

recetas_bp = Blueprint("recetas", __name__, url_prefix="/recetas")


def _cargar_formulario_receta(form: RecetaForm) -> None:
    productos = Producto.query.order_by(Producto.estatus.desc(), Producto.nombre.asc()).all()
    materias = MateriaPrima.query.filter_by(estatus=True).order_by(MateriaPrima.nombre.asc()).all()
    form.set_productos(productos)
    form.set_materias(materias)


def _cargar_formulario_receta_lote(form: RecetaLoteForm):
    productos = Producto.query.order_by(Producto.estatus.desc(), Producto.nombre.asc()).all()
    materias = MateriaPrima.query.filter_by(estatus=True).order_by(MateriaPrima.nombre.asc()).all()
    form.set_productos(productos)
    return materias, productos


def _asegurar_tabla_detalle_receta() -> None:
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS receta_detalle (
                id_producto INT PRIMARY KEY,
                tamano_vaso VARCHAR(20) NULL,
                actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                CONSTRAINT fk_receta_detalle_producto
                    FOREIGN KEY (id_producto) REFERENCES Producto(id_producto)
                    ON DELETE CASCADE
            )
            """
        )
    )


def _obtener_tamano_vaso_producto(id_producto: int) -> str:
    fila = db.session.execute(
        text("SELECT tamano_vaso FROM receta_detalle WHERE id_producto = :id_producto"),
        {"id_producto": id_producto},
    ).fetchone()
    return (fila[0] if fila and fila[0] else "")


def _guardar_tamano_vaso_producto(id_producto: int, tamano_vaso: str | None) -> None:
    db.session.execute(
        text(
            """
            INSERT INTO receta_detalle (id_producto, tamano_vaso)
            VALUES (:id_producto, :tamano_vaso)
            ON DUPLICATE KEY UPDATE tamano_vaso = VALUES(tamano_vaso)
            """
        ),
        {
            "id_producto": id_producto,
            "tamano_vaso": tamano_vaso,
        },
    )


@recetas_bp.route("/", methods=["GET"], endpoint="index")
def recetas():
    busqueda = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "todos").strip().lower()

    query = Receta.query.join(Producto, Receta.id_producto == Producto.id_producto).join(
        MateriaPrima, Receta.id_materia == MateriaPrima.id_materia
    )

    if busqueda:
        patron = f"%{busqueda}%"
        query = query.filter(
            or_(
                Producto.nombre.ilike(patron),
                MateriaPrima.nombre.ilike(patron),
            )
        )

    if estado == "activas":
        query = query.filter(Receta.estado.is_(True))
    elif estado == "inactivas":
        query = query.filter(Receta.estado.is_(False))

    recetas_db = query.order_by(Producto.nombre.asc(), MateriaPrima.nombre.asc()).all()

    recetas_agrupadas = []
    agrupadas_por_producto = {}
    for receta in recetas_db:
        id_producto = receta.id_producto
        if id_producto not in agrupadas_por_producto:
            agrupadas_por_producto[id_producto] = {
                "id_producto": id_producto,
                "producto_nombre": receta.producto.nombre if receta.producto else "-",
                "estado": True,
                "insumos": [],
            }
            recetas_agrupadas.append(agrupadas_por_producto[id_producto])

        grupo = agrupadas_por_producto[id_producto]
        grupo["insumos"].append(
            {
                "id_receta": receta.id_receta,
                "nombre_materia": receta.nombre_materia or "-",
                "cantidad": receta.cantidad,
                "unidad_materia": receta.unidad_materia or "Sin unidad",
                "estado": receta.estado,
            }
        )
        grupo["estado"] = bool(grupo["estado"] and receta.estado)

    return render_template(
        "recetas/recetas.html",
        recetas=recetas_agrupadas,
        busqueda=busqueda,
        estado_actual=estado,
        active_page="recetas",
    )


@recetas_bp.route("/nueva", methods=["GET", "POST"], endpoint="nueva")
@requiereRol("Gerente")
def nueva_receta():
    form = RecetaLoteForm()
    materias, productos = _cargar_formulario_receta_lote(form)
    productos_meta = {
        producto.id_producto: {
            "categoria": (producto.categoria or "").lower(),
        }
        for producto in productos
    }
    insumos_precargados = []
    cancel_url = url_for("recetas.index")
    modo_edicion = False

    _asegurar_tabla_detalle_receta()

    if request.method == "GET":
        modo_edicion = request.args.get("editar") == "1"
        producto_preseleccionado = request.args.get("producto", type=int)
        if producto_preseleccionado:
            ids_validos = {pid for pid, _ in (form.id_producto.choices or [])}
            if producto_preseleccionado in ids_validos:
                form.id_producto.data = producto_preseleccionado
                recetas_producto = (
                    Receta.query.filter_by(id_producto=producto_preseleccionado, estado=True)
                    .order_by(Receta.id_receta.asc())
                    .all()
                )

                if not recetas_producto:
                    recetas_producto = (
                        Receta.query.filter_by(id_producto=producto_preseleccionado)
                        .order_by(Receta.id_receta.asc())
                        .all()
                    )

                ids_materias_receta = {receta.id_materia for receta in recetas_producto}
                ids_materias_actuales = {materia.id_materia for materia in materias}
                ids_faltantes = ids_materias_receta - ids_materias_actuales

                if ids_faltantes:
                    materias_faltantes = (
                        MateriaPrima.query.filter(MateriaPrima.id_materia.in_(ids_faltantes))
                        .order_by(MateriaPrima.nombre.asc())
                        .all()
                    )
                    materias.extend(materias_faltantes)

                insumos_precargados = [
                    {
                        "id_materia": receta.id_materia,
                        "cantidad": float(receta.cantidad),
                    }
                    for receta in recetas_producto
                ]

                form.tamano_vaso.data = _obtener_tamano_vaso_producto(producto_preseleccionado)

            es_nuevo_producto = request.args.get("nuevo_producto") == "1"
            pendientes = set(session.get("productos_pendientes_receta", []))
            if es_nuevo_producto and producto_preseleccionado in pendientes:
                cancel_url = url_for("producto.descartar_producto_pendiente", id_producto=producto_preseleccionado)

    if form.validate_on_submit():
        try:
            modo_edicion = request.form.get("modo_edicion") == "1"
            id_producto = form.id_producto.data
            producto = Producto.query.get(id_producto)
            if not producto:
                raise ValueError("El producto indicado no existe.")

            receta_existente = Receta.query.filter_by(id_producto=id_producto, estado=True).first()
            if receta_existente and not modo_edicion:
                raise ValueError(
                    "Este producto ya tiene receta registrada. Usa la opción Editar para modificarla."
                )

            tamano_vaso = (form.tamano_vaso.data or "").strip().lower()
            if (producto.categoria or "").lower() == "bebidas":
                if tamano_vaso not in {"chico", "mediano", "grande"}:
                    raise ValueError("Selecciona el tamaño de vaso para recetas de bebidas.")
            else:
                tamano_vaso = ""

            try:
                insumos_raw = json.loads(form.insumos_json.data or "[]")
            except json.JSONDecodeError:
                raise ValueError("La captura de insumos es inválida.")

            if not isinstance(insumos_raw, list) or not insumos_raw:
                raise ValueError("No se puede registrar una receta sin insumos.")

            insumos_payload = []
            ids_vistos = set()

            for item in insumos_raw:
                id_materia = int((item or {}).get("id_materia") or 0)
                cantidad = Decimal(str((item or {}).get("cantidad") or 0))

                if id_materia <= 0:
                    raise ValueError("Selecciona un insumo válido en cada renglón.")

                if id_materia in ids_vistos:
                    raise ValueError("No se puede repetir el mismo insumo en la receta.")
                ids_vistos.add(id_materia)

                if cantidad <= 0:
                    raise ValueError("La cantidad de cada insumo debe ser mayor a cero.")

                insumos_payload.append({
                    "id_materia": id_materia,
                    "cantidad": cantidad
                })

            Receta.reemplazar_receta_producto(
                id_producto=id_producto,
                insumos=insumos_payload
            )

            _guardar_tamano_vaso_producto(id_producto=id_producto, tamano_vaso=tamano_vaso or None)

            registrar_auditoria(
                accion="Creación/Actualización de Receta",
                modulo="Recetas",
                detalles={
                    "id_producto": id_producto,
                    "tamano_vaso": tamano_vaso or None,
                    "insumos": [
                        {
                            "id_materia": i["id_materia"],
                            "cantidad": str(i["cantidad"])
                        }
                        for i in insumos_payload
                    ]
                },
                commit=False,
            )

            pendientes = set(session.get("productos_pendientes_receta", []))
            if id_producto in pendientes:
                pendientes.discard(id_producto)
                session["productos_pendientes_receta"] = list(pendientes)

            db.session.commit()

            form_limpio = RecetaLoteForm()
            materias, productos = _cargar_formulario_receta_lote(form_limpio)
            productos_meta = {
                producto.id_producto: {
                    "categoria": (producto.categoria or "").lower(),
                }
                for producto in productos
            }

            return render_template(
                "recetas/nueva_receta.html",
                form=form_limpio,
                materias=materias,
                productos_meta=productos_meta,
                insumos_precargados=[],
                modo_edicion=False,
                cancel_url=url_for("recetas.index"),
                mostrar_modal=True,
                active_page="recetas",
            )

        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

        except SQLAlchemyError:
            db.session.rollback()
            flash("No se pudo guardar la receta.", "danger")

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "recetas/nueva_receta.html",
        form=form,
        materias=materias,
        productos_meta=productos_meta,
        insumos_precargados=insumos_precargados,
        modo_edicion=modo_edicion,
        cancel_url=cancel_url,
        mostrar_modal=False,
        active_page="recetas",
    )

@recetas_bp.route("/<int:id_receta>/editar", methods=["GET", "POST"], endpoint="editar")
@requiereRol("Gerente")
def modificar_receta(id_receta: int):
    receta = Receta.query.get_or_404(id_receta)
    form = RecetaForm(obj=receta)
    _cargar_formulario_receta(form)

    if request.method == "GET":
        form.estado.data = "1" if receta.estado else "0"

    if form.validate_on_submit():
        if form.id_producto.data != receta.id_producto or form.id_materia.data != receta.id_materia:
            flash("No se puede cambiar producto o insumo en edición. Crea un nuevo registro.", "danger")
            return render_template(
                "recetas/editar_receta.html",
                form=form,
                receta=receta,
                mostrar_modal=False,
                active_page="recetas",
            )

        try:
            id_producto = receta.id_producto
            id_materia = receta.id_materia
            cantidad = Decimal(str(form.cantidad.data))
            estado = form.estado.data == "1"

            recetas_activas = Receta.query.filter_by(id_producto=id_producto, estado=True).all()
            insumos_payload = [
                {"id_materia": r.id_materia, "cantidad": (cantidad if r.id_materia == id_materia else Decimal(str(r.cantidad)))}
                for r in recetas_activas
            ]

            if not any(item["id_materia"] == id_materia for item in insumos_payload):
                insumos_payload.append({"id_materia": id_materia, "cantidad": cantidad})

            Receta.reemplazar_receta_producto(id_producto=id_producto, insumos=insumos_payload)

            receta_actualizada = Receta.query.filter_by(id_producto=id_producto, id_materia=id_materia).first()
            if receta_actualizada:
                receta_actualizada.estado = estado

            registrar_auditoria(
                accion="Modificación de Ingredientes de Receta",
                modulo="Recetas",
                detalles={
                    "id_producto": id_producto,
                    "id_materia": id_materia,
                    "cantidad_nueva": str(cantidad),
                    "estado": "activa" if estado else "inactiva",
                },
                commit=False,
            )

            db.session.commit()
            return render_template(
                "recetas/editar_receta.html",
                form=form,
                receta=receta,
                mostrar_modal=True,
                active_page="recetas",
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except SQLAlchemyError:
            db.session.rollback()
            flash("No se pudo actualizar la receta.", "danger")

    if request.method == "POST":
        for erroresCampo in form.errors.values():
            if erroresCampo:
                flash(erroresCampo[0], "danger")
                break

    return render_template(
        "recetas/editar_receta.html",
        form=form,
        receta=receta,
        mostrar_modal=False,
        active_page="recetas",
    )


@recetas_bp.route("/producto/<int:id_producto>", methods=["GET"], endpoint="obtener_por_producto")
def detalle_recetas_producto(id_producto: int):
    recetas = (
        Receta.query.filter_by(id_producto=id_producto, estado=True)
        .order_by(Receta.id_receta.asc())
        .all()
    )

    return jsonify(
        {
            "id_producto": id_producto,
            "insumos": [
                {
                    "id_receta": receta.id_receta,
                    "id_materia": receta.id_materia,
                    "nombre_materia": receta.nombre_materia,
                    "unidad": receta.unidad_materia,
                    "cantidad": float(receta.cantidad),
                    "estado": receta.estado,
                }
                for receta in recetas
            ],
        }
    )


@recetas_bp.route("/producto/<int:id_producto>", methods=["POST"], endpoint="crear_receta")
@requiereRol("Gerente")
def crear_receta_api(id_producto: int):
    payload = request.get_json(silent=True) or {}
    insumos = payload.get("insumos", [])

    try:
        Receta.reemplazar_receta_producto(id_producto=id_producto, insumos=insumos)
        registrar_auditoria(
            accion="Creación/Actualización de Receta",
            modulo="Recetas",
            detalles={"id_producto": id_producto, "insumos": insumos},
            commit=False,
        )
        db.session.commit()
        return jsonify({"ok": True, "message": "Receta creada correctamente."}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "message": str(exc)}), 400
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"ok": False, "message": "Error al crear la receta."}), 500


@recetas_bp.route("/producto/<int:id_producto>", methods=["PUT"], endpoint="editar_receta")
@requiereRol("Gerente")
def editar_receta_api(id_producto: int):
    payload = request.get_json(silent=True) or {}
    insumos = payload.get("insumos", [])

    try:
        Receta.reemplazar_receta_producto(id_producto=id_producto, insumos=insumos)
        registrar_auditoria(
            accion="Modificación de Ingredientes de Receta",
            modulo="Recetas",
            detalles={"id_producto": id_producto, "insumos": insumos},
            commit=False,
        )
        db.session.commit()
        return jsonify({"ok": True, "message": "Receta actualizada correctamente."})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "message": str(exc)}), 400
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"ok": False, "message": "Error al actualizar la receta."}), 500
