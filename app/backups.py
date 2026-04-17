import os
import subprocess
import time
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for

backups_bp = Blueprint("backups", __name__, url_prefix="/backups")

EXTENSIONES_PERMITIDAS = {"sql"}
TAMANO_MAXIMO_SQL = 10 * 1024 * 1024  # 10 MB


def _timeout_restore_segundos() -> int:
    valor = current_app.config.get("BACKUP_RESTORE_TIMEOUT_SECONDS", os.getenv("BACKUP_RESTORE_TIMEOUT_SECONDS", 1800))
    try:
        timeout = int(valor)
    except (TypeError, ValueError):
        timeout = 1800
    return max(timeout, 60)


def _timeout_dump_segundos() -> int:
    valor = current_app.config.get("BACKUP_DUMP_TIMEOUT_SECONDS", os.getenv("BACKUP_DUMP_TIMEOUT_SECONDS", 600))
    try:
        timeout = int(valor)
    except (TypeError, ValueError):
        timeout = 600
    return max(timeout, 60)


def _esta_autenticado() -> bool:
    return bool(session.get("inicioSesion") and session.get("usuarioId"))


def _requiere_sesion(funcion_vista):
    @wraps(funcion_vista)
    def envoltura(*args, **kwargs):
        if not _esta_autenticado():
            if request.headers.get("X-Requested-With", "") == "XMLHttpRequest":
                return jsonify({
                    "ok": False,
                    "message": "Tu sesión expiró. Inicia sesión nuevamente.",
                    "redirect": url_for("auth.iniciarSesion"),
                }), 401
            return redirect(url_for("auth.iniciarSesion"))
        return funcion_vista(*args, **kwargs)

    return envoltura


def _rol_permitido() -> bool:
    rol = (session.get("usuarioRol") or "").strip()
    return rol in {"Gerente", "Gerente de Tienda", "Admin General", "Admin General (TI)"}


def _archivo_sql_valido(nombre_archivo: str | None) -> bool:
    if not nombre_archivo or "." not in nombre_archivo:
        return False
    extension = nombre_archivo.rsplit(".", 1)[1].lower().strip()
    return extension in EXTENSIONES_PERMITIDAS


def _credenciales_mysql() -> dict[str, str | int]:
    return {
        "host": current_app.config.get("MYSQL_HOST", "localhost"),
        "port": int(current_app.config.get("MYSQL_PORT", 3306)),
        "user": current_app.config.get("MYSQL_USER", "root"),
        "password": current_app.config.get("MYSQL_PASSWORD", ""),
        "database": current_app.config.get("MYSQL_DATABASE", ""),
    }


def _es_peticion_ajax() -> bool:
    return request.headers.get("X-Requested-With", "") == "XMLHttpRequest"


def _ejecutar_mysqldump() -> bytes:
    credenciales = _credenciales_mysql()
    if not credenciales["database"]:
        raise RuntimeError("No se encontró el nombre de la base de datos en la configuración.")

    comando = [
        "mysqldump",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--default-character-set=utf8mb4",
        "-h",
        str(credenciales["host"]),
        "-P",
        str(credenciales["port"]),
        "-u",
        str(credenciales["user"]),
        str(credenciales["database"]),
    ]

    import shutil
    
    entorno = os.environ.copy()
    if credenciales["password"]:
        entorno["MYSQL_PWD"] = str(credenciales["password"])
        
    # Añadir rutas comunes de MySQL a la variable PATH
    rutas_comunes = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin",
        r"C:\Program Files\MySQL\MySQL Server 8.1\bin",
        r"C:\Program Files\MySQL\MySQL Server 8.2\bin",
        r"C:\xampp\mysql\bin",
        r"C:\wamp64\bin\mysql\mysql8.0.31\bin"
    ]
    rutas_existentes = [r for r in rutas_comunes if os.path.exists(r)]
    if rutas_existentes:
        entorno["PATH"] = os.pathsep.join(rutas_existentes) + os.pathsep + entorno.get("PATH", "")

    executable = shutil.which("mysqldump", path=entorno["PATH"])
    if not executable:
        raise RuntimeError("No se encontró el ejecutable 'mysqldump' en el sistema. Asegúrate de tener MySQL instalado y en el PATH.")
    
    comando[0] = executable

    try:
        proceso = subprocess.run(
            comando,
            capture_output=True,
            env=entorno,
            check=False,
            timeout=_timeout_dump_segundos(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError("No se encontró el ejecutable 'mysqldump' en el sistema. Asegúrate de tener MySQL instalado y en el PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"El backup excedió el tiempo máximo de ejecución ({_timeout_dump_segundos()}s)."
        ) from exc

    if proceso.returncode != 0:
        detalle = (proceso.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise RuntimeError(detalle or "No fue posible generar el backup.")

    return proceso.stdout


def _ejecutar_restore(sql_bytes: bytes) -> None:
    credenciales = _credenciales_mysql()
    if not credenciales["database"]:
        raise RuntimeError("No se encontró el nombre de la base de datos en la configuración.")

    comando = [
        "mysql",
        "--default-character-set=utf8mb4",
        "--max_allowed_packet=512M",
        "-h",
        str(credenciales["host"]),
        "-P",
        str(credenciales["port"]),
        "-u",
        str(credenciales["user"]),
        str(credenciales["database"]),
    ]

    import shutil

    entorno = os.environ.copy()
    if credenciales["password"]:
        entorno["MYSQL_PWD"] = str(credenciales["password"])

    # Añadir rutas comunes de MySQL a la variable PATH
    rutas_comunes = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin",
        r"C:\Program Files\MySQL\MySQL Server 8.1\bin",
        r"C:\Program Files\MySQL\MySQL Server 8.2\bin",
        r"C:\xampp\mysql\bin",
        r"C:\wamp64\bin\mysql\mysql8.0.31\bin"
    ]
    rutas_existentes = [r for r in rutas_comunes if os.path.exists(r)]
    if rutas_existentes:
        entorno["PATH"] = os.pathsep.join(rutas_existentes) + os.pathsep + entorno.get("PATH", "")

    executable = shutil.which("mysql", path=entorno["PATH"])
    if not executable:
        raise RuntimeError("No se encontró el ejecutable 'mysql' en el sistema. Asegúrate de tener MySQL instalado y en el PATH.")
    
    comando[0] = executable

    try:
        proceso = subprocess.run(
            comando,
            input=sql_bytes,
            capture_output=True,
            env=entorno,
            check=False,
            timeout=_timeout_restore_segundos(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError("No se encontró el ejecutable 'mysql' en el sistema. Asegúrate de tener MySQL instalado y en el PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"La restauración excedió el tiempo máximo de ejecución ({_timeout_restore_segundos()}s)."
        ) from exc

    if proceso.returncode != 0:
        detalle = (proceso.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise RuntimeError(detalle or "No fue posible restaurar la base de datos.")


@backups_bp.route("", methods=["GET"], endpoint="index")
@_requiere_sesion
def index():
    if not _rol_permitido():
        flash("No tienes permisos para acceder al módulo de backups.", "danger")
        return redirect(url_for("dashboard_operador"))

    return render_template("backups.html", active_page="backups")


@backups_bp.route("/download", methods=["GET"], endpoint="download")
@_requiere_sesion
def download():
    if not _rol_permitido():
        flash("No tienes permisos para generar backups.", "danger")
        return redirect(url_for("backups.index"))

    try:
        contenido_sql = _ejecutar_mysqldump()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"backup_{current_app.config.get('MYSQL_DATABASE', 'database')}_{timestamp}.sql"

        return send_file(
            BytesIO(contenido_sql),
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype="application/sql",
            max_age=0,
        )
    except Exception as exc:
        flash(f"Error al generar el backup: {exc}", "danger")
        return redirect(url_for("backups.index"))


@backups_bp.route("/restore", methods=["POST"], endpoint="restore")
@_requiere_sesion
def restore():
    if not _rol_permitido():
        mensaje = "No tienes permisos para restaurar backups."
        if _es_peticion_ajax():
            return jsonify({"ok": False, "message": mensaje}), 403
        flash(mensaje, "danger")
        return redirect(url_for("backups.index"))

    archivo = request.files.get("backup_file")

    if not archivo or not archivo.filename:
        mensaje = "Debes seleccionar un archivo .sql para restaurar."
        if _es_peticion_ajax():
            return jsonify({"ok": False, "message": mensaje}), 400
        flash(mensaje, "warning")
        return redirect(url_for("backups.index"))

    if not _archivo_sql_valido(archivo.filename):
        mensaje = "Archivo inválido. Solo se permiten archivos con extensión .sql."
        if _es_peticion_ajax():
            return jsonify({"ok": False, "message": mensaje}), 400
        flash(mensaje, "danger")
        return redirect(url_for("backups.index"))

    contenido_sql = archivo.read()
    if not contenido_sql:
        mensaje = "El archivo está vacío."
        if _es_peticion_ajax():
            return jsonify({"ok": False, "message": mensaje}), 400
        flash(mensaje, "danger")
        return redirect(url_for("backups.index"))

    if len(contenido_sql) > TAMANO_MAXIMO_SQL:
        mensaje = "El archivo excede el tamaño máximo permitido (10 MB)."
        if _es_peticion_ajax():
            return jsonify({"ok": False, "message": mensaje}), 400
        flash(mensaje, "danger")
        return redirect(url_for("backups.index"))

    try:
        _ejecutar_restore(contenido_sql)

        # Re-crea tablas/esquemas faltantes para que la app no quede inconsistente
        # cuando el backup proviene de una versión anterior.
        from db_init import inicializar_db

        ultimo_error = None
        for _ in range(3):
            try:
                inicializar_db()
                ultimo_error = None
                break
            except Exception as exc:
                ultimo_error = exc
                time.sleep(1)

        if ultimo_error:
            raise RuntimeError(f"La base se restauró, pero no se pudo revalidar el esquema: {ultimo_error}")

        # Invalidar sesión actual para evitar tokens huérfanos tras restore.
        session.clear()

        mensaje = "Base de datos restaurada correctamente. Debes iniciar sesión nuevamente."
        if _es_peticion_ajax():
            return jsonify({
                "ok": True,
                "message": mensaje,
                "redirect": url_for("auth.iniciarSesion"),
            }), 200

        flash(mensaje, "success")
        return redirect(url_for("auth.iniciarSesion"))
    except Exception as exc:
        mensaje = f"Error al restaurar la base de datos: {exc}"
        if _es_peticion_ajax():
            return jsonify({"ok": False, "message": mensaje}), 500
        flash(mensaje, "danger")

    return redirect(url_for("backups.index"))
