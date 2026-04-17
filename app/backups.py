import os
import shutil
import subprocess
import time
from datetime import datetime
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for

backups_bp = Blueprint("backups", __name__, url_prefix="/backups")

EXTENSIONES_PERMITIDAS = {"sql"}
TAMANO_MAXIMO_SQL = 10 * 1024 * 1024  # 10 MB


def _resolver_binario_mysql(nombre_base: str, env_var: str) -> str:
    """Resuelve la ruta de ejecutables MySQL en PATH, variables o rutas comunes de Windows."""
    valor_env = (current_app.config.get(env_var) or os.getenv(env_var) or "").strip()
    if valor_env and Path(valor_env).is_file():
        return valor_env

    encontrado = shutil.which(nombre_base)
    if encontrado:
        return encontrado

    if os.name == "nt":
        ejecutable = f"{nombre_base}.exe"
        candidatos = [
            Path(r"C:\xampp\mysql\bin") / ejecutable,
            Path(r"C:\laragon\bin\mysql\bin") / ejecutable,
            Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin") / ejecutable,
            Path(r"C:\Program Files\MySQL\MySQL Server 8.4\bin") / ejecutable,
            Path(r"C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin") / ejecutable,
        ]

        # Soporta instalaciones con versión variable: C:\Program Files\MySQL\MySQL Server *\bin
        candidatos.extend(
            Path(p)
            for p in sorted(
                Path(r"C:\Program Files\MySQL").glob(f"MySQL Server*\\bin\\{ejecutable}")
            )
        )

        for candidato in candidatos:
            if candidato.is_file():
                return str(candidato)

    raise RuntimeError(
        f"No se encontró el ejecutable '{nombre_base}'. "
        f"Agrega su carpeta al PATH o configura {env_var} con la ruta completa."
    )


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
        "user": current_app.config.get("MYSQL_APP_ADMIN_USER", "app_admin"),
        "password": current_app.config.get("MYSQL_APP_ADMIN_PASSWORD", ""),
        "database": current_app.config.get("MYSQL_DATABASE", ""),
    }


def _credenciales_mysql_candidatas() -> list[dict[str, str | int]]:
    """Construye una cadena de credenciales para backup/restore con fallback automático."""
    host = current_app.config.get("MYSQL_HOST", "localhost")
    port = int(current_app.config.get("MYSQL_PORT", 3306))
    database = current_app.config.get("MYSQL_DATABASE", "")

    candidatos = [
        {
            "host": host,
            "port": port,
            "user": current_app.config.get("BACKUP_MYSQL_USER") or os.getenv("BACKUP_MYSQL_USER", ""),
            "password": current_app.config.get("BACKUP_MYSQL_PASSWORD") or os.getenv("BACKUP_MYSQL_PASSWORD", ""),
            "database": database,
        },
        {
            "host": host,
            "port": port,
            "user": current_app.config.get("MYSQL_APP_ADMIN_USER", "app_admin"),
            "password": current_app.config.get("MYSQL_APP_ADMIN_PASSWORD", ""),
            "database": database,
        },
        {
            "host": host,
            "port": port,
            "user": current_app.config.get("MYSQL_USER", "root"),
            "password": current_app.config.get("MYSQL_PASSWORD", ""),
            "database": database,
        },
    ]

    # Filtrar entradas vacías y duplicadas por (user,password)
    unicos: list[dict[str, str | int]] = []
    vistos: set[tuple[str, str]] = set()
    for c in candidatos:
        user = str(c.get("user") or "").strip()
        password = str(c.get("password") or "")
        if not user:
            continue
        firma = (user, password)
        if firma in vistos:
            continue
        vistos.add(firma)
        unicos.append(c)

    return unicos


def _es_error_autenticacion_mysql(detalle: str) -> bool:
    detalle_min = (detalle or "").lower()
    return "1045" in detalle_min or "access denied" in detalle_min


def _es_peticion_ajax() -> bool:
    return request.headers.get("X-Requested-With", "") == "XMLHttpRequest"


def _ejecutar_mysqldump() -> bytes:
    credenciales = _credenciales_mysql()
    if not credenciales["database"]:
        raise RuntimeError("No se encontró el nombre de la base de datos en la configuración.")

    ejecutable = _resolver_binario_mysql("mysqldump", "BACKUP_MYSQLDUMP_PATH")
    ultimo_detalle = ""
    candidatos = _credenciales_mysql_candidatas()

    for idx, candidato in enumerate(candidatos):
        comando = [
            ejecutable,
            "--single-transaction",
            "--routines",
            "--triggers",
            "--events",
            "--default-character-set=utf8mb4",
            "-h",
            str(candidato["host"]),
            "-P",
            str(candidato["port"]),
            "-u",
            str(candidato["user"]),
            str(candidato["database"]),
        ]

        entorno = os.environ.copy()
        if candidato["password"]:
            entorno["MYSQL_PWD"] = str(candidato["password"])

        try:
            proceso = subprocess.run(
                comando,
                capture_output=True,
                env=entorno,
                check=False,
                timeout=_timeout_dump_segundos(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "No se encontró el ejecutable 'mysqldump'. "
                "Configura BACKUP_MYSQLDUMP_PATH o agrega MySQL\\bin al PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"El backup excedió el tiempo máximo de ejecución ({_timeout_dump_segundos()}s)."
            ) from exc

        if proceso.returncode == 0:
            return proceso.stdout

        detalle = (proceso.stderr or b"").decode("utf-8", errors="ignore").strip()
        ultimo_detalle = detalle or "No fue posible generar el backup."

        # Si falla por autenticación y hay más credenciales, intentar con la siguiente.
        if _es_error_autenticacion_mysql(ultimo_detalle) and idx < len(candidatos) - 1:
            continue
        break

    raise RuntimeError(ultimo_detalle)


def _ejecutar_restore(sql_bytes: bytes) -> None:
    credenciales = _credenciales_mysql()
    if not credenciales["database"]:
        raise RuntimeError("No se encontró el nombre de la base de datos en la configuración.")

    ejecutable = _resolver_binario_mysql("mysql", "BACKUP_MYSQL_PATH")
    ultimo_detalle = ""
    candidatos = _credenciales_mysql_candidatas()

    for idx, candidato in enumerate(candidatos):
        comando = [
            ejecutable,
            "--default-character-set=utf8mb4",
            "--max_allowed_packet=512M",
            "-h",
            str(candidato["host"]),
            "-P",
            str(candidato["port"]),
            "-u",
            str(candidato["user"]),
            str(candidato["database"]),
        ]

        entorno = os.environ.copy()
        if candidato["password"]:
            entorno["MYSQL_PWD"] = str(candidato["password"])

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
            raise RuntimeError(
                "No se encontró el ejecutable 'mysql'. "
                "Configura BACKUP_MYSQL_PATH o agrega MySQL\\bin al PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"La restauración excedió el tiempo máximo de ejecución ({_timeout_restore_segundos()}s)."
            ) from exc

        if proceso.returncode == 0:
            return

        detalle = (proceso.stderr or b"").decode("utf-8", errors="ignore").strip()
        ultimo_detalle = detalle or "No fue posible restaurar la base de datos."

        if _es_error_autenticacion_mysql(ultimo_detalle) and idx < len(candidatos) - 1:
            continue
        break

    raise RuntimeError(ultimo_detalle)


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
