import os
from urllib.parse import quote_plus

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

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "urban_coffee")

    MYSQL_APP_ADMIN_USER = os.getenv("MYSQL_APP_ADMIN_USER", "app_admin")
    MYSQL_APP_ADMIN_PASSWORD = os.getenv("MYSQL_APP_ADMIN_PASSWORD", MYSQL_PASSWORD)

    MYSQL_APP_GERENTE_USER = os.getenv("MYSQL_APP_GERENTE_USER", "app_gerente")
    MYSQL_APP_GERENTE_PASSWORD = os.getenv("MYSQL_APP_GERENTE_PASSWORD", MYSQL_PASSWORD)

    MYSQL_APP_OPERATIVO_USER = os.getenv("MYSQL_APP_OPERATIVO_USER", "app_operativo")
    MYSQL_APP_OPERATIVO_PASSWORD = os.getenv("MYSQL_APP_OPERATIVO_PASSWORD", MYSQL_PASSWORD)

    MYSQL_APP_CLIENTE_USER = os.getenv("MYSQL_APP_CLIENTE_USER", "app_cliente")
    MYSQL_APP_CLIENTE_PASSWORD = os.getenv("MYSQL_APP_CLIENTE_PASSWORD", MYSQL_PASSWORD)

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    )

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@urbancoffee.local")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}

    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.getenv("MONGO_DB", "urban_coffee")
    MONGO_AUDIT_COLLECTION = os.getenv("MONGO_AUDIT_COLLECTION", "auditoria_logs")  

    USUARIO_GERENTE_NOMBRE = os.getenv("USUARIO_GERENTE_NOMBRE", "Administrador Urban Coffee")
    USUARIO_GERENTE_CORREO = os.getenv("USUARIO_GERENTE_CORREO", "admin@urbancoffee.com")
    USUARIO_GERENTE_PASSWORD = os.getenv("USUARIO_GERENTE_PASSWORD", "PasswordSegura123!")
    USUARIO_GERENTE_ROL_ID = int(os.getenv("USUARIO_GERENTE_ROL_ID", 6))  