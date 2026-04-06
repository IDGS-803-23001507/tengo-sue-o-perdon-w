import json
from datetime import datetime, timezone
from typing import Any

from flask import current_app, has_request_context, request, session
from pymongo import DESCENDING, MongoClient

_mongo_client: MongoClient | None = None

CLAVES_SENSIBLES = {
    "password",
    "contrasena",
    "contrasenahash",
    "token",
    "token_sesion",
    "tarjeta",
    "card",
    "cvv",
}


def _es_sensible(clave: str) -> bool:
    clave_normalizada = (clave or "").strip().lower()
    return any(s in clave_normalizada for s in CLAVES_SENSIBLES)


def _sanitizar_detalles(detalles: Any) -> str:
    if detalles is None:
        return ""

    def limpiar(valor: Any) -> Any:
        if isinstance(valor, dict):
            limpio = {}
            for k, v in valor.items():
                if _es_sensible(str(k)):
                    limpio[k] = "[REDACTED]"
                else:
                    limpio[k] = limpiar(v)
            return limpio
        if isinstance(valor, list):
            return [limpiar(v) for v in valor]
        if isinstance(valor, tuple):
            return tuple(limpiar(v) for v in valor)
        return valor

    try:
        if isinstance(detalles, (dict, list, tuple)):
            texto = json.dumps(limpiar(detalles), ensure_ascii=False, default=str)
        else:
            texto = str(detalles)
    except Exception:
        texto = "Detalle no serializable"

    return texto[:4000]


def _obtener_ip() -> str:
    if not has_request_context():
        return ""

    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        return xff.split(",")[0].strip()[:64]

    return (request.remote_addr or "")[:64]


def _obtener_collection():
    global _mongo_client

    uri = current_app.config.get("MONGO_URI", "")
    db_name = current_app.config.get("MONGO_DB", "urban_coffee")
    collection_name = current_app.config.get("MONGO_AUDIT_COLLECTION", "auditoria_logs")

    if not uri:
        return None

    if _mongo_client is None:
        _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=2000)

    return _mongo_client[db_name][collection_name]


def registrar_auditoria(
    accion: str,
    modulo: str,
    detalles: Any = None,
    usuario_id: int | None = None,
    commit: bool = False,
) -> None:
    try:
        usuario_id_final = usuario_id
        if usuario_id_final is None and has_request_context():
            usuario_id_final = session.get("usuarioId")

        collection = _obtener_collection()
        if collection is None:
            return

        collection.insert_one(
            {
                "usuario_id": usuario_id_final,
                "accion": (accion or "")[:150],
                "modulo": (modulo or "")[:80],
                "detalles": _sanitizar_detalles(detalles),
                "ip_direccion": _obtener_ip(),
                "fecha_hora": datetime.now(timezone.utc),
            }
        )
    except Exception as exc:
        try:
            current_app.logger.warning("No se pudo registrar auditoría: %s", exc)
        except Exception:
            pass


def obtener_logs_auditoria(limit: int = 300) -> list[dict[str, Any]]:
    try:
        collection = _obtener_collection()
        if collection is None:
            return []

        logs = []
        cursor = collection.find({}, {"_id": 0}).sort("fecha_hora", DESCENDING).limit(limit)
        for log in cursor:
            fecha = log.get("fecha_hora")
            if isinstance(fecha, datetime):
                fecha_txt = fecha.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            else:
                fecha_txt = "-"

            logs.append(
                {
                    "fecha_hora_text": fecha_txt,
                    "usuario_id": log.get("usuario_id"),
                    "accion": log.get("accion", ""),
                    "modulo": log.get("modulo", ""),
                    "ip_direccion": log.get("ip_direccion", ""),
                    "detalles": log.get("detalles", ""),
                }
            )

        return logs
    except Exception as exc:
        try:
            current_app.logger.warning("No se pudieron leer logs de auditoría: %s", exc)
        except Exception:
            pass
        return []
