import pymysql
from flask import current_app
from sqlalchemy import inspect, text

from config import Config
from model import Rol, Usuario, Cliente, Empleado, UnidadMedida, db


def asegurar_base_de_datos() -> None:
    conexion = pymysql.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        autocommit=True,
        charset="utf8mb4",
    )

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conexion.close()


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

    for nombre_rol in (
        "Admin General (TI)",
        "Gerente de Tienda",
        "Cajero",
        "Barista",
        "Cliente",
        "Gerente",
        "Operador",
    ):
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


def asegurar_esquema_proveedores() -> None:
    inspector = inspect(db.engine)
    tablas = set(inspector.get_table_names())

    if "Proveedor" not in tablas:
        return

    columnas = {columna["name"] for columna in inspector.get_columns("Proveedor")}

    if "colonia" in columnas:
        db.session.execute(text("ALTER TABLE `Proveedor` MODIFY COLUMN `colonia` VARCHAR(100) NULL"))

    if "calle" in columnas:
        db.session.execute(text("ALTER TABLE `Proveedor` MODIFY COLUMN `calle` VARCHAR(100) NULL"))

    if "num_exterior" in columnas:
        db.session.execute(text("ALTER TABLE `Proveedor` MODIFY COLUMN `num_exterior` VARCHAR(10) NULL"))

    db.session.commit()


def asegurar_procedimientos_almacenados() -> None:
    db.session.execute(text("DROP PROCEDURE IF EXISTS crear_venta_general"))
    db.session.execute(text("DROP PROCEDURE IF EXISTS crear_venta_online"))
    db.session.execute(text("DROP PROCEDURE IF EXISTS pagar_venta"))
    db.session.execute(text("DROP PROCEDURE IF EXISTS sp_registrar_venta"))
    db.session.execute(
        text(
            """
            CREATE PROCEDURE sp_registrar_venta(
                IN p_id_usuario INT,
                IN p_id_producto INT,
                IN p_cantidad INT,
                IN p_tipo_venta VARCHAR(20),
                IN p_metodo_pago VARCHAR(20)
            )
            BEGIN
                DECLARE v_precio DECIMAL(10,2);
                DECLARE v_stock INT;
                DECLARE v_total DECIMAL(10,2);
                DECLARE v_utilidad DECIMAL(10,2);
                DECLARE v_id_venta INT;

                IF p_cantidad IS NULL OR p_cantidad <= 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cantidad inválida para venta';
                END IF;

                START TRANSACTION;

                SELECT precio_venta, stock
                INTO v_precio, v_stock
                FROM Producto
                WHERE id_producto = p_id_producto AND estatus = 1
                FOR UPDATE;

                IF v_precio IS NULL THEN
                    ROLLBACK;
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto no disponible';
                END IF;

                IF v_stock < p_cantidad THEN
                    ROLLBACK;
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Stock insuficiente';
                END IF;

                SET v_total = ROUND(v_precio * p_cantidad, 2);
                SET v_utilidad = ROUND(v_total * 0.35, 2);

                INSERT INTO ventas (id_usuario, total, utilidad_bruta, estatus, origen, creado_en, tipo_venta, metodo_pago)
                VALUES (p_id_usuario, v_total, v_utilidad, 1, 'POS', NOW(), p_tipo_venta, p_metodo_pago);

                SET v_id_venta = LAST_INSERT_ID();

                INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, descuento)
                VALUES (v_id_venta, p_id_producto, p_cantidad, v_precio, 0);

                UPDATE Producto
                SET stock = stock - p_cantidad
                WHERE id_producto = p_id_producto;

                COMMIT;

                SELECT v_id_venta AS id_venta, v_total AS total;
            END
            """
        )
    )

    db.session.execute(
        text(
            """
            CREATE PROCEDURE crear_venta_general(
                IN p_id_usuario INT,
                IN p_id_cliente INT,
                IN p_tipo VARCHAR(20),
                IN p_id_producto INT,
                IN p_cantidad INT,
                IN p_id_venta_existente INT
            )
            BEGIN
                DECLARE v_id_venta INT;
                DECLARE v_precio DECIMAL(10,2);
                DECLARE v_faltantes INT;

                DECLARE EXIT HANDLER FOR SQLEXCEPTION
                BEGIN
                    ROLLBACK;
                    RESIGNAL;
                END;

                IF p_cantidad IS NULL OR p_cantidad <= 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cantidad inválida';
                END IF;

                START TRANSACTION;

                SELECT precio_venta INTO v_precio
                FROM Producto
                WHERE id_producto = p_id_producto AND estatus = 1
                FOR UPDATE;

                IF v_precio IS NULL THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto no disponible';
                END IF;

                IF (
                    SELECT COUNT(*)
                    FROM Recetas
                    WHERE id_producto = p_id_producto AND estado = 1
                ) = 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto sin receta activa';
                END IF;

                SELECT COUNT(*) INTO v_faltantes
                FROM Materia_prima mp
                JOIN Recetas r ON r.id_materia = mp.id_materia
                WHERE r.id_producto = p_id_producto
                  AND r.estado = 1
                  AND mp.stock_actual < (r.cantidad * p_cantidad);

                IF v_faltantes > 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Stock insuficiente de insumos para este producto';
                END IF;

                IF p_id_venta_existente IS NULL OR p_id_venta_existente = 0 THEN
                    INSERT INTO ventas (
                        id_usuario,
                        id_cliente,
                        tipo_venta,
                        estado,
                        total,
                        utilidad_bruta,
                        estatus,
                        creado_en,
                        metodo_pago
                    )
                    VALUES (
                        p_id_usuario,
                        p_id_cliente,
                        p_tipo,
                        'pendiente',
                        0,
                        0,
                        0,
                        NOW(),
                        NULL
                    );
                    SET v_id_venta = LAST_INSERT_ID();
                ELSE
                    SET v_id_venta = p_id_venta_existente;

                    IF (
                        SELECT COUNT(*)
                        FROM ventas
                        WHERE id_venta = v_id_venta
                        FOR UPDATE
                    ) = 0 THEN
                        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La venta indicada no existe';
                    END IF;
                END IF;

                INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, descuento)
                VALUES (v_id_venta, p_id_producto, p_cantidad, v_precio, 0);

                UPDATE Materia_prima mp
                JOIN Recetas r ON mp.id_materia = r.id_materia
                SET mp.stock_actual = mp.stock_actual - (r.cantidad * p_cantidad)
                WHERE r.id_producto = p_id_producto
                  AND r.estado = 1;

                UPDATE ventas
                SET total = (
                        SELECT COALESCE(SUM(dv.cantidad * dv.precio_unitario), 0)
                        FROM detalle_venta dv
                        WHERE dv.id_venta = v_id_venta
                    ),
                    utilidad_bruta = ROUND((
                        SELECT COALESCE(SUM(dv.cantidad * dv.precio_unitario), 0)
                        FROM detalle_venta dv
                        WHERE dv.id_venta = v_id_venta
                    ) * 0.35, 2)
                WHERE id_venta = v_id_venta;

                COMMIT;

                SELECT v_id_venta AS id_venta_generada;
            END
            """
        )
    )

    db.session.execute(
        text(
            """
            CREATE PROCEDURE crear_venta_online(
                IN p_id_usuario INT,
                IN p_id_cliente INT,
                IN p_hora_recogida DATETIME,
                IN p_notas VARCHAR(200),
                IN p_id_producto INT,
                IN p_cantidad INT,
                IN p_id_venta_existente INT
            )
            BEGIN
                DECLARE v_id_venta INT;
                DECLARE v_precio DECIMAL(10,2);
                DECLARE v_faltantes INT;

                DECLARE EXIT HANDLER FOR SQLEXCEPTION
                BEGIN
                    ROLLBACK;
                    RESIGNAL;
                END;

                START TRANSACTION;

                IF p_id_venta_existente IS NULL OR p_id_venta_existente = 0 THEN
                    INSERT INTO ventas (
                        id_usuario,
                        id_cliente,
                        tipo_venta,
                        estado,
                        total,
                        utilidad_bruta,
                        estatus,
                        creado_en,
                        metodo_pago,
                        codigo_recogida
                    )
                    VALUES (
                        p_id_usuario,
                        p_id_cliente,
                        'en_linea',
                        'pendiente',
                        0,
                        0,
                        0,
                        NOW(),
                        'Efectivo',
                        CONCAT('ORD', LPAD(FLOOR(RAND() * 10000), 4, '0'))
                    );

                    SET v_id_venta = LAST_INSERT_ID();

                    INSERT INTO pedidos (id_venta, hora_solicitud, hora_recogida, estado, notas)
                    VALUES (v_id_venta, NOW(), p_hora_recogida, 'pendiente', p_notas);
                ELSE
                    SET v_id_venta = p_id_venta_existente;
                END IF;

                IF p_cantidad IS NULL OR p_cantidad <= 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cantidad inválida';
                END IF;

                SELECT precio_venta INTO v_precio
                FROM Producto
                WHERE id_producto = p_id_producto AND estatus = 1
                FOR UPDATE;

                IF v_precio IS NULL THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto no disponible';
                END IF;

                IF (
                    SELECT COUNT(*)
                    FROM Recetas
                    WHERE id_producto = p_id_producto AND estado = 1
                ) = 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto sin receta activa';
                END IF;

                SELECT COUNT(*) INTO v_faltantes
                FROM Materia_prima mp
                JOIN Recetas r ON r.id_materia = mp.id_materia
                WHERE r.id_producto = p_id_producto
                  AND r.estado = 1
                  AND mp.stock_actual < (r.cantidad * p_cantidad);

                IF v_faltantes > 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Stock insuficiente de insumos para este producto';
                END IF;

                INSERT INTO detalle_venta (id_venta, id_producto, cantidad, precio_unitario, descuento)
                VALUES (v_id_venta, p_id_producto, p_cantidad, v_precio, 0);

                UPDATE Materia_prima mp
                JOIN Recetas r ON mp.id_materia = r.id_materia
                SET mp.stock_actual = mp.stock_actual - (r.cantidad * p_cantidad)
                WHERE r.id_producto = p_id_producto
                  AND r.estado = 1;

                UPDATE ventas
                SET total = (
                        SELECT COALESCE(SUM(dv.cantidad * dv.precio_unitario), 0)
                        FROM detalle_venta dv
                        WHERE dv.id_venta = v_id_venta
                    ),
                    utilidad_bruta = ROUND((
                        SELECT COALESCE(SUM(dv.cantidad * dv.precio_unitario), 0)
                        FROM detalle_venta dv
                        WHERE dv.id_venta = v_id_venta
                    ) * 0.35, 2)
                WHERE id_venta = v_id_venta;

                COMMIT;

                SELECT v_id_venta AS id_generado;
            END
            """
        )
    )

    db.session.execute(
        text(
            """
            CREATE PROCEDURE pagar_venta(
                IN p_id_venta INT,
                IN p_metodo_pago VARCHAR(30)
            )
            BEGIN
                DECLARE v_tipo VARCHAR(20);

                IF (SELECT COUNT(*) FROM ventas WHERE id_venta = p_id_venta) = 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La venta no existe';
                END IF;

                UPDATE ventas
                SET
                    metodo_pago = p_metodo_pago,
                    estado = 'pagado',
                    estatus = 1
                WHERE id_venta = p_id_venta;

                SELECT tipo_venta INTO v_tipo
                FROM ventas
                WHERE id_venta = p_id_venta;

                IF v_tipo = 'en_linea' THEN
                    UPDATE pedidos
                    SET estado = 'entregado'
                    WHERE id_venta = p_id_venta;
                END IF;

                SELECT 'Pago registrado con éxito' AS mensaje;
            END
            """
        )
    )

    db.session.execute(text("DROP PROCEDURE IF EXISTS sp_finalizar_solicitud"))
    db.session.execute(text("DROP PROCEDURE IF EXISTS sp_finalizar_solicitud_produccion"))
    db.session.execute(
        text(
            """
            CREATE PROCEDURE sp_finalizar_solicitud_produccion(
                IN p_id_solicitud INT
            )
            BEGIN
                DECLARE v_estado VARCHAR(20);
                DECLARE v_detalles INT;
                DECLARE v_sin_receta INT;
                DECLARE v_faltantes INT;

                DECLARE EXIT HANDLER FOR SQLEXCEPTION
                BEGIN
                    ROLLBACK;
                    RESIGNAL;
                END;

                START TRANSACTION;

                SELECT estado INTO v_estado
                FROM Solicitud_produccion
                WHERE id_solicitud = p_id_solicitud
                FOR UPDATE;

                IF v_estado IS NULL THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Solicitud no encontrada';
                END IF;

                IF v_estado = 'cancelado' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se puede finalizar una solicitud cancelada';
                END IF;

                IF v_estado = 'finalizado' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La solicitud ya está finalizada';
                END IF;

                SELECT COUNT(*) INTO v_detalles
                FROM Detalle_produccion
                WHERE id_solicitud = p_id_solicitud;

                IF v_detalles = 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La solicitud no tiene detalles';
                END IF;

                SELECT COUNT(*) INTO v_sin_receta
                FROM (
                    SELECT dp.id_producto
                    FROM Detalle_produccion dp
                    LEFT JOIN Recetas r
                        ON r.id_producto = dp.id_producto
                       AND r.estado = 1
                    WHERE dp.id_solicitud = p_id_solicitud
                    GROUP BY dp.id_producto
                    HAVING COUNT(r.id_receta) = 0
                ) t;

                IF v_sin_receta > 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Hay productos sin receta activa';
                END IF;

                DROP TEMPORARY TABLE IF EXISTS tmp_consumo_materia;
                CREATE TEMPORARY TABLE tmp_consumo_materia (
                    id_materia INT PRIMARY KEY,
                    cantidad_requerida DECIMAL(12,4) NOT NULL
                );

                INSERT INTO tmp_consumo_materia (id_materia, cantidad_requerida)
                SELECT
                    r.id_materia,
                    SUM(dp.cantidad * r.cantidad) AS cantidad_requerida
                FROM Detalle_produccion dp
                JOIN Recetas r
                    ON r.id_producto = dp.id_producto
                   AND r.estado = 1
                WHERE dp.id_solicitud = p_id_solicitud
                GROUP BY r.id_materia;

                SELECT m.id_materia
                FROM Materia_prima m
                JOIN tmp_consumo_materia t ON t.id_materia = m.id_materia
                FOR UPDATE;

                SELECT COUNT(*) INTO v_faltantes
                FROM Materia_prima m
                JOIN tmp_consumo_materia t ON t.id_materia = m.id_materia
                WHERE m.stock_actual < t.cantidad_requerida;

                IF v_faltantes > 0 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Stock insuficiente de materias primas';
                END IF;

                UPDATE Materia_prima m
                JOIN tmp_consumo_materia t ON t.id_materia = m.id_materia
                SET m.stock_actual = m.stock_actual - t.cantidad_requerida;

                DROP TEMPORARY TABLE IF EXISTS tmp_produccion_producto;
                CREATE TEMPORARY TABLE tmp_produccion_producto (
                    id_producto INT PRIMARY KEY,
                    cantidad_producida INT NOT NULL
                );

                INSERT INTO tmp_produccion_producto (id_producto, cantidad_producida)
                SELECT dp.id_producto, SUM(dp.cantidad)
                FROM Detalle_produccion dp
                WHERE dp.id_solicitud = p_id_solicitud
                GROUP BY dp.id_producto;

                SELECT p.id_producto
                FROM Producto p
                JOIN tmp_produccion_producto t ON t.id_producto = p.id_producto
                FOR UPDATE;

                UPDATE Producto p
                JOIN tmp_produccion_producto t ON t.id_producto = p.id_producto
                SET p.stock = p.stock + t.cantidad_producida;

                UPDATE Solicitud_produccion
                SET estado = 'finalizado'
                WHERE id_solicitud = p_id_solicitud;

                DROP TEMPORARY TABLE IF EXISTS tmp_consumo_materia;
                DROP TEMPORARY TABLE IF EXISTS tmp_produccion_producto;

                COMMIT;
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

    for nombre in [
        "Admin General (TI)",
        "Gerente de Tienda",
        "Cajero",
        "Barista",
        "Cliente",
        "Gerente",
        "Operador",
    ]:
        if not Rol.query.filter_by(nombre=nombre).first():
            db.session.add(Rol(nombre=nombre))

    db.session.commit()

    rol_gerente = Rol.query.filter(
        Rol.nombre.in_(["Gerente de Tienda", "Gerente", "Admin General (TI)"])
    ).first()
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
    asegurar_esquema_proveedores()
    asegurar_procedimientos_almacenados()
    seed_db()