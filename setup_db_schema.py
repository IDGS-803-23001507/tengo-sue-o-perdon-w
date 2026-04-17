import pymysql
from config import Config

def setup_schema():
    conexion = pymysql.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DATABASE,
        autocommit=True,
        charset="utf8mb4",
    )

    try:
        with conexion.cursor() as cursor:
            # Add columns to pedidos
            try:
                cursor.execute("ALTER TABLE pedidos ADD COLUMN stock_descontado TINYINT(1) DEFAULT 0;")
                print("Added stock_descontado column.")
            except Exception as e:
                print("stock_descontado:", e)
            
            try:
                cursor.execute("ALTER TABLE pedidos ADD COLUMN stock_descontado_en DATETIME NULL;")
                print("Added stock_descontado_en column.")
            except Exception as e:
                print("stock_descontado_en:", e)
            
            try:
                cursor.execute("ALTER TABLE pedidos ADD COLUMN version INT DEFAULT 0;")
                print("Added version column.")
            except Exception as e:
                print("version:", e)

            # Create inventario_movimientos table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventario_movimientos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_pedido INT,
                id_materia INT,
                cantidad DECIMAL(12,4),
                tipo VARCHAR(50),
                fecha DATETIME,
                id_usuario INT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            print("Created inventario_movimientos table.")

            # Create pedido_estado_historial table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedido_estado_historial (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_pedido INT,
                estado_origen VARCHAR(20),
                estado_destino VARCHAR(20),
                id_usuario INT,
                motivo VARCHAR(200),
                fecha DATETIME
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            print("Created pedido_estado_historial table.")
            
    except Exception as e:
        print("Error updating schema:", e)
    finally:
        conexion.close()

if __name__ == "__main__":
    setup_schema()
