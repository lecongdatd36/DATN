"""SQL Server branch: isolated settings; PostgreSQL .env remains untouched."""
from .settings import *  # noqa: F403
from copy import deepcopy

_postgres_source = deepcopy(DATABASES["default"])  # noqa: F405

load_dotenv(BASE_DIR / ".env.sqlserver", override=True, encoding="utf-8")  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "core.db.backends.sqlserver",
        "NAME": os.environ.get("SQLSERVER_DB", "QLNH_SQLSERVER"),
        "HOST": os.environ.get("SQLSERVER_HOST", "localhost"),
        "PORT": os.environ.get("SQLSERVER_PORT", ""),
        "USER": os.environ.get("SQLSERVER_USER", ""),
        "PASSWORD": os.environ.get("SQLSERVER_PASSWORD", ""),
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "python_driver": "mssql_python",
            "connection_timeout": 5,
            "connection_retries": 0,
            "isolation_level": "READ COMMITTED",
            "extra_params": os.environ.get("SQLSERVER_EXTRA_PARAMS", "Encrypt=yes"),
        },
        "TEST": {"COLLATION": "Latin1_General_100_BIN2"},
    }
}
DATABASE_CONNECTION_POOLING = False
# Explicit read source for the one-way local copy command. Application queries
# continue using default; PostgreSQL isn't written by that command.
DATABASES["postgres_source"] = _postgres_source
SERIALIZATION_MODULES = {"json_precise": "core.serializers_precise"}
