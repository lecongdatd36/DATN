"""SQL Server profile for local development and Render/SmarterASP.NET."""
from .base_settings import *  # noqa: F403

if not IS_RENDER:  # noqa: F405
    load_dotenv(BASE_DIR / ".env.sqlserver", override=True, encoding="utf-8")  # noqa: F405

# Never fall back to localhost or Windows Authentication on Render.
if IS_RENDER:  # noqa: F405
    for _name in ("SQLSERVER_HOST", "SQLSERVER_DB", "SQLSERVER_USER", "SQLSERVER_PASSWORD"):
        required_env(_name)  # noqa: F405

_user = os.environ.get("SQLSERVER_USER", "")  # noqa: F405
_password = os.environ.get("SQLSERVER_PASSWORD", "")  # noqa: F405
if bool(_user) != bool(_password):
    raise ImproperlyConfigured("SQLSERVER_USER và SQLSERVER_PASSWORD phải được cấu hình cùng nhau.")  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "core.db.backends.sqlserver",
        "NAME": os.environ.get("SQLSERVER_DB", "QLNH_SQLSERVER"),
        "HOST": os.environ.get("SQLSERVER_HOST", "localhost"),
        "PORT": os.environ.get("SQLSERVER_PORT", "1433"),
        "USER": _user,
        "PASSWORD": _password,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "python_driver": "mssql_python",
            "connection_timeout": positive_int_env("SQLSERVER_CONNECTION_TIMEOUT", 15),
            "connection_retries": 0,
            "isolation_level": "READ COMMITTED",
            "extra_params": os.environ.get("SQLSERVER_EXTRA_PARAMS", "Encrypt=yes;TrustServerCertificate=no"),
        },
        "TEST": {"COLLATION": "Latin1_General_100_BIN2"},
    }
}
DATABASE_CONNECTION_POOLING = False
# Preserve the optional local copy source without requiring PostgreSQL on Render.
if not IS_RENDER and (os.environ.get("DATABASE_URL") or all(  # noqa: F405
    os.environ.get(name) for name in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")
)):
    from .settings import DATABASES as _postgres_databases
    if _postgres_databases["default"]["ENGINE"] == "django.db.backends.postgresql":
        DATABASES["postgres_source"] = _postgres_databases["default"]
SERIALIZATION_MODULES = {"json_precise": "core.serializers_precise"}
