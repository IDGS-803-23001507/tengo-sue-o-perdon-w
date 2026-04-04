import os
from urllib.parse import quote_plus

# Este código carga variables de entorno desde un archivo .env local si existe, permitiendo que las variables de entorno del sistema tengan prioridad. Esto es útil para configurar la aplicación sin exponer credenciales en el código fuente.

# Si quieren agregar una variable de entorno se añade en el archivo .env con el formato CLAVE=valor

def _load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")

    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


_load_local_env()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "urban-coffee-dev-secret-key")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3307))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "urban")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    )