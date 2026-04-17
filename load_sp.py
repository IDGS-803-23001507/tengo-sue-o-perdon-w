import pymysql
from config import Config

def load_procedure():
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
            # First drop it if exists
            cursor.execute("DROP PROCEDURE IF EXISTS sp_cambiar_estado_pedido;")
            print("Dropped existing procedure.")

            # Read the file
            with open("sp_cambiar_estado_pedido.sql", "r", encoding="utf-8") as f:
                sql_content = f.read()

            # Execute the create procedure statement
            cursor.execute(sql_content)
            print("Procedure created successfully.")
    except Exception as e:
        print("Error executing procedure SQL:", e)
    finally:
        conexion.close()

if __name__ == "__main__":
    load_procedure()
