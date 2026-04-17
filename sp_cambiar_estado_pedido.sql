CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_cambiar_estado_pedido`(
                IN p_id_pedido INT,
                IN p_nuevo_estado VARCHAR(20),
                IN p_id_usuario INT,
                IN p_motivo VARCHAR(200)
            )
BEGIN
                DECLARE v_estado_actual VARCHAR(20);
                DECLARE v_stock_descontado TINYINT(1);
                DECLARE v_id_venta INT;
                DECLARE v_faltantes_mp INT DEFAULT 0;
                DECLARE v_faltantes_producto INT DEFAULT 0;
                DECLARE v_transicion_valida INT DEFAULT 0;
                DECLARE v_movimientos_salida INT DEFAULT 0;

                DECLARE EXIT HANDLER FOR SQLEXCEPTION
                BEGIN
                    ROLLBACK;
                    RESIGNAL;
                END;

                SET p_nuevo_estado = LOWER(TRIM(COALESCE(p_nuevo_estado, '')));

                IF p_nuevo_estado NOT IN ('pendiente', 'aceptado', 'preparando', 'entregado', 'cancelado', 'rechazado') THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Estado destino inválido';
                END IF;

                START TRANSACTION;

                SELECT LOWER(TRIM(estado)), COALESCE(stock_descontado, 0), id_venta
                INTO v_estado_actual, v_stock_descontado, v_id_venta
                FROM pedidos
                WHERE id_pedido = p_id_pedido
                FOR UPDATE;

                IF v_estado_actual IS NULL THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Pedido no encontrado';
                END IF;

                IF p_nuevo_estado <> v_estado_actual THEN
                    SET v_transicion_valida = (
                        (v_estado_actual = 'pendiente' AND p_nuevo_estado IN ('aceptado', 'cancelado', 'rechazado'))
                        OR (v_estado_actual = 'aceptado' AND p_nuevo_estado IN ('preparando', 'cancelado', 'rechazado'))
                        OR (v_estado_actual = 'preparando' AND p_nuevo_estado IN ('entregado', 'cancelado', 'rechazado'))
                    );

                    IF v_transicion_valida = 0 THEN
                        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Transición inválida: solo se permite avanzar';
                    END IF;

                    IF p_nuevo_estado = 'aceptado' AND v_stock_descontado = 0 THEN
                        IF (
                            SELECT COUNT(*)
                            FROM detalle_venta
                            WHERE id_venta = v_id_venta
                        ) = 0 THEN
                            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La venta del pedido no tiene productos';
                        END IF;

                        DROP TEMPORARY TABLE IF EXISTS tmp_consumo_producto_stock;
                        CREATE TEMPORARY TABLE tmp_consumo_producto_stock (
                            id_producto INT PRIMARY KEY,
                            cantidad_requerida INT NOT NULL
                        );

                        INSERT INTO tmp_consumo_producto_stock (id_producto, cantidad_requerida)
                        SELECT dv.id_producto, SUM(dv.cantidad)
                        FROM detalle_venta dv
                        JOIN Producto p ON p.id_producto = dv.id_producto
                        WHERE dv.id_venta = v_id_venta
                          AND COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock'
                        GROUP BY dv.id_producto;

                        SELECT p.id_producto
                        FROM Producto p
                        JOIN tmp_consumo_producto_stock t ON t.id_producto = p.id_producto
                        FOR UPDATE;

                        SELECT COUNT(*) INTO v_faltantes_producto
                        FROM Producto p
                        JOIN tmp_consumo_producto_stock t ON t.id_producto = p.id_producto
                        WHERE COALESCE(p.stock, 0) < t.cantidad_requerida;

                        IF v_faltantes_producto > 0 THEN
                            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se puede aceptar: stock insuficiente de producto terminado';
                        END IF;

                        UPDATE Producto p
                        JOIN tmp_consumo_producto_stock t ON t.id_producto = p.id_producto
                        SET p.stock = p.stock - t.cantidad_requerida,
                            p.stock_reservado = GREATEST(0, p.stock_reservado - t.cantidad_requerida);

                        IF EXISTS (
                            SELECT 1
                            FROM detalle_venta dv
                            JOIN Producto p ON p.id_producto = dv.id_producto
                            LEFT JOIN Recetas r
                                ON r.id_producto = p.id_producto
                               AND r.estado = 1
                            WHERE dv.id_venta = v_id_venta
                              AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'
                            GROUP BY dv.id_producto
                            HAVING COUNT(r.id_receta) = 0
                        ) THEN
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
                            SUM(dv.cantidad * r.cantidad) AS cantidad_requerida
                        FROM detalle_venta dv
                        JOIN Producto p ON p.id_producto = dv.id_producto
                        JOIN Recetas r
                            ON r.id_producto = p.id_producto
                           AND r.estado = 1
                           AND (dv.id_variante IS NULL AND r.id_variante IS NULL OR r.id_variante = dv.id_variante)
                        WHERE dv.id_venta = v_id_venta
                          AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'
                        GROUP BY r.id_materia;

                        SELECT m.id_materia
                        FROM Materia_prima m
                        JOIN tmp_consumo_materia t ON t.id_materia = m.id_materia
                        FOR UPDATE;

                        SELECT COUNT(*) INTO v_faltantes_mp
                        FROM Materia_prima m
                        JOIN tmp_consumo_materia t ON t.id_materia = m.id_materia
                        WHERE m.stock_actual < t.cantidad_requerida;

                        IF v_faltantes_mp > 0 THEN
                            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se puede aceptar: stock insuficiente de materias primas';
                        END IF;

                        UPDATE Materia_prima m
                        JOIN tmp_consumo_materia t ON t.id_materia = m.id_materia
                        SET m.stock_actual = m.stock_actual - t.cantidad_requerida;

                        INSERT INTO inventario_movimientos (
                            id_pedido,
                            id_materia,
                            cantidad,
                            tipo,
                            fecha,
                            id_usuario
                        )
                        SELECT
                            p_id_pedido,
                            t.id_materia,
                            t.cantidad_requerida,
                            'salida_pedido_online',
                            NOW(),
                            p_id_usuario
                        FROM tmp_consumo_materia t;

                        DROP TEMPORARY TABLE IF EXISTS tmp_consumo_producto_stock;
                        DROP TEMPORARY TABLE IF EXISTS tmp_consumo_materia;

                        UPDATE pedidos
                        SET stock_descontado = 1,
                            stock_descontado_en = NOW()
                        WHERE id_pedido = p_id_pedido;
                    END IF;

                    IF p_nuevo_estado IN ('cancelado', 'rechazado') THEN
                        IF v_stock_descontado = 0 THEN
                            UPDATE Producto p
                            JOIN detalle_venta dv ON dv.id_producto = p.id_producto
                            SET p.stock_reservado = GREATEST(0, p.stock_reservado - dv.cantidad)
                            WHERE dv.id_venta = v_id_venta AND COALESCE(p.tipo_preparacion, 'materia_prima') = 'stock';
                        END IF;
                    END IF;

                    IF p_nuevo_estado IN ('cancelado', 'rechazado')
                       AND v_stock_descontado = 1
                       AND v_estado_actual IN ('aceptado', 'preparando') THEN

                        DROP TEMPORARY TABLE IF EXISTS tmp_reversion_materia;
                        CREATE TEMPORARY TABLE tmp_reversion_materia (
                            id_materia INT PRIMARY KEY,
                            cantidad_reponer DECIMAL(12,4) NOT NULL
                        );

                        INSERT INTO tmp_reversion_materia (id_materia, cantidad_reponer)
                        SELECT
                            im.id_materia,
                            SUM(im.cantidad) AS cantidad_reponer
                        FROM inventario_movimientos im
                        WHERE im.id_pedido = p_id_pedido
                          AND im.tipo = 'salida_pedido_online'
                        GROUP BY im.id_materia;

                        SELECT COUNT(*) INTO v_movimientos_salida
                        FROM tmp_reversion_materia;

                        IF v_movimientos_salida = 0 THEN
                            INSERT INTO tmp_reversion_materia (id_materia, cantidad_reponer)
                            SELECT
                                r.id_materia,
                                SUM(dv.cantidad * r.cantidad) AS cantidad_reponer
                            FROM detalle_venta dv
                            JOIN Producto p ON p.id_producto = dv.id_producto
                            JOIN Recetas r
                                ON r.id_producto = p.id_producto
                               AND r.estado = 1
                            WHERE dv.id_venta = v_id_venta
                              AND COALESCE(p.tipo_preparacion, 'materia_prima') <> 'stock'
                            GROUP BY r.id_materia;
                        END IF;

                        IF (SELECT COUNT(*) FROM tmp_reversion_materia) > 0 THEN
                            SELECT m.id_materia
                            FROM Materia_prima m
                            JOIN tmp_reversion_materia t ON t.id_materia = m.id_materia
                            FOR UPDATE;

                            UPDATE Materia_prima m
                            JOIN tmp_reversion_materia t ON t.id_materia = m.id_materia
                            SET m.stock_actual = m.stock_actual + t.cantidad_reponer;

                            INSERT INTO inventario_movimientos (
                                id_pedido,
                                id_materia,
                                cantidad,
                                tipo,
                                fecha,
                                id_usuario
                            )
                            SELECT
                                p_id_pedido,
                                t.id_materia,
                                t.cantidad_reponer,
                                'entrada_cancelacion',
                                NOW(),
                                p_id_usuario
                            FROM tmp_reversion_materia t;
                        END IF;

                        DROP TEMPORARY TABLE IF EXISTS tmp_reversion_materia;

                        UPDATE pedidos
                        SET stock_descontado = 0,
                            stock_descontado_en = NULL
                        WHERE id_pedido = p_id_pedido;
                    END IF;

                    UPDATE pedidos
                    SET estado = p_nuevo_estado,
                        version = COALESCE(version, 0) + 1
                    WHERE id_pedido = p_id_pedido;

                    UPDATE ventas
                    SET estado = p_nuevo_estado
                    WHERE id_venta = v_id_venta;

                    INSERT INTO pedido_estado_historial (
                        id_pedido,
                        estado_origen,
                        estado_destino,
                        id_usuario,
                        motivo,
                        fecha
                    )
                    VALUES (
                        p_id_pedido,
                        v_estado_actual,
                        p_nuevo_estado,
                        p_id_usuario,
                        p_motivo,
                        NOW()
                    );
                END IF;

                COMMIT;

                SELECT p_id_pedido AS id_pedido, p_nuevo_estado AS estado_actual;
            END