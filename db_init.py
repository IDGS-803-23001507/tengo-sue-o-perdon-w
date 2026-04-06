from flask import current_app
from sqlalchemy import inspect, text

from model import Rol, Usuario, Cliente, Empleado, UnidadMedida, db


def asegurar_esquema_usuarios() -> None:
    inspector = inspect(db.engine)
    tablas = set(inspector.get_table_names())

    if "roles" not in tablas:
        db.session.execute(
            text(
                """
                CREATE TABLE roles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(20) NOT NULL UNIQUE
                )
                """
            )
        )

    for nombre_rol in ("Gerente", "Operador", "Cliente"):
        db.session.execute(text("INSERT IGNORE INTO roles (nombre) VALUES (:nombre)"), {"nombre": nombre_rol})

    columnas = {columna["name"] for columna in inspector.get_columns("usuarios")}

    sentencias_migracion = []

    if "nombre" not in columnas:
        sentencias_migracion.append("ALTER TABLE usuarios ADD COLUMN nombre VARCHAR(120) NOT NULL DEFAULT 'Sin nombre'")

    if "estado" not in columnas:
        sentencias_migracion.append("ALTER TABLE usuarios ADD COLUMN estado VARCHAR(20) NOT NULL DEFAULT 'Activo'")

    if "usuario" not in columnas:
        sentencias_migracion.append("ALTER TABLE usuarios ADD COLUMN usuario VARCHAR(60) NULL")

    if "rol_id" not in columnas:
        sentencias_migracion.append("ALTER TABLE usuarios ADD COLUMN rol_id INT NULL")

    for sentencia in sentencias_migracion:
        db.session.execute(text(sentencia))

    db.session.execute(text("UPDATE usuarios SET usuario = SUBSTRING_INDEX(correo, '@', 1) WHERE usuario IS NULL OR usuario = ''"))

    if "rol" in columnas:
        db.session.execute(
            text(
                """
                UPDATE usuarios u
                LEFT JOIN roles r ON r.nombre = u.rol
                SET u.rol_id = r.id
                WHERE u.rol_id IS NULL
                """
            )
        )

        db.session.execute(
            text(
                """
                UPDATE usuarios u
                LEFT JOIN roles r ON r.id = u.rol_id
                SET u.rol = r.nombre
                WHERE (u.rol IS NULL OR u.rol = '')
                  AND u.rol_id IS NOT NULL
                """
            )
        )

        db.session.execute(text("ALTER TABLE usuarios MODIFY COLUMN rol VARCHAR(20) NULL"))

    db.session.execute(
        text(
            """
            UPDATE usuarios
            SET rol_id = (SELECT id FROM roles WHERE nombre = 'Cliente' LIMIT 1)
            WHERE rol_id IS NULL
            """
        )
    )

    db.session.execute(text("ALTER TABLE usuarios MODIFY COLUMN rol_id INT NOT NULL"))

    inspector = inspect(db.engine)
    llaves_foraneas = {fk.get("name") for fk in inspector.get_foreign_keys("usuarios")}
    if "fk_usuarios_roles" not in llaves_foraneas:
        db.session.execute(
            text(
                """
                ALTER TABLE usuarios
                ADD CONSTRAINT fk_usuarios_roles
                FOREIGN KEY (rol_id) REFERENCES roles(id)
                """
            )
        )

    db.session.commit()


def asegurar_esquema_unidades() -> None:
    inspector = inspect(db.engine)
    tablas = set(inspector.get_table_names())

    if "Unidad_medida" not in tablas:
        return

    columnas = {columna["name"] for columna in inspector.get_columns("Unidad_medida")}

    if "tipo" not in columnas:
        db.session.execute(
            text(
                """
                ALTER TABLE `Unidad_medida`
                ADD COLUMN `tipo` ENUM('liquido','solido') NOT NULL DEFAULT 'solido'
                """
            )
        )

    if "factor" not in columnas:
        db.session.execute(
            text(
                """
                ALTER TABLE `Unidad_medida`
                ADD COLUMN `factor` DECIMAL(10,4) NOT NULL DEFAULT 1.0000
                """
            )
        )

    db.session.execute(
        text(
            """
            UPDATE `Unidad_medida`
            SET `tipo` = CASE
                WHEN LOWER(`abreviacion`) IN ('l', 'ml') THEN 'liquido'
                ELSE 'solido'
            END,
            `factor` = CASE
                WHEN LOWER(`abreviacion`) = 'kg' THEN 1000.0000
                WHEN LOWER(`abreviacion`) = 'kl' THEN 1000.0000
                WHEN LOWER(`abreviacion`) = 'g' THEN 1.0000
                WHEN LOWER(`abreviacion`) = 'oz' THEN 28.3500
                WHEN LOWER(`abreviacion`) = 'l' THEN 1000.0000
                WHEN LOWER(`abreviacion`) = 'ml' THEN 1.0000
                WHEN LOWER(`abreviacion`) IN ('pz', 'u') THEN 1.0000
                ELSE COALESCE(`factor`, 1.0000)
            END
            """
        )
    )

    db.session.commit()


def _generar_usuario_unico(correo_base: str) -> str:
    usuario_base = correo_base.split("@")[0] or "gerente"
    usuario_generado = usuario_base
    consecutivo = 0

    while Empleado.query.filter_by(username=usuario_generado).first():
        consecutivo += 1
        usuario_generado = f"{usuario_base}{consecutivo}"

    return usuario_generado


def _generar_correo_unico(correo_base: str, usuario_base: str) -> str:
    correo_final = correo_base

    if not Usuario.query.filter_by(correo=correo_final).first():
        return correo_final

    dominio = "urbancoffee.com"
    if "@" in correo_base:
        _, dominio = correo_base.split("@", 1)

    consecutivo = 0
    while Usuario.query.filter_by(correo=correo_final).first():
        consecutivo += 1
        correo_final = f"{usuario_base}{consecutivo}@{dominio}"

    return correo_final


def seed_db() -> None:

    unidades_base = [
        ("Kilogramo", "kg", "solido", 1000 ),
        ("Gramo", "g", "solido", 1),
        ("Litro", "L", "liquido", 1000),
        ("Mililitro", "ml", "liquido", 1),
        ("Pieza", "pz", "conteo", 1),
        ("Unidad", "u", "conteo", 1),
    ]

    for nombre, abreviacion, tipo, factor in unidades_base:
        existe_unidad = UnidadMedida.query.filter_by(abreviacion=abreviacion).first()
        if not existe_unidad:
            db.session.add(UnidadMedida(nombre=nombre, abreviacion=abreviacion, tipo=tipo, factor=factor))

    for nombre in ["Gerente", "Operador", "Cliente"]:
        if not Rol.query.filter_by(nombre=nombre).first():
            db.session.add(Rol(nombre=nombre))

    db.session.commit()

    rol_gerente = Rol.query.filter_by(nombre="Gerente").first()
    if not rol_gerente:
        return

    gerente_existente = Usuario.query.filter(
        Usuario.rolId == rol_gerente.id,
        Usuario.estado == "Activo",
    ).first()

    if gerente_existente:
        return
    
    nombre = str(current_app.config.get("USUARIO_GERENTE_NOMBRE", "Administrador")).strip()
    correo_base = str(current_app.config.get("USUARIO_GERENTE_CORREO", "admin@urbancoffee.com")).strip().lower()
    contrasena = str(current_app.config.get("USUARIO_GERENTE_PASSWORD", "PasswordSegura123!"))

    if not correo_base:
        correo_base = "admin@urbancoffee.com"

    usuario_generado = _generar_usuario_unico(correo_base)
    usuario_base = correo_base.split("@")[0] or "gerente"
    correo_final = _generar_correo_unico(correo_base, usuario_base)

    admin = Usuario(
        correo=correo_final,
        rolId=rol_gerente.id,
        estado="Activo"
    )
    admin.establecerContrasena(contrasena)
    admin.resetearSeguridad()

    db.session.add(admin)
    db.session.flush() 

    empleado_admin = Empleado(
        usuarioId=admin.id,
        username=usuario_generado,
        nombre=nombre
    )

    db.session.add(empleado_admin)
    db.session.commit()

def inicializar_db() -> None:
    db.create_all()
    asegurar_esquema_usuarios()
    asegurar_esquema_unidades()
    seed_db()