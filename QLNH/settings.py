"""PostgreSQL profile; SQL Server uses QLNH.sqlserver_settings independently."""
import dj_database_url

from .base_settings import *  # noqa: F403

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()  # noqa: F405
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL, conn_max_age=600, conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": required_env("DB_NAME"),  # noqa: F405
            "USER": required_env("DB_USER"),  # noqa: F405
            "PASSWORD": required_env("DB_PASSWORD"),  # noqa: F405
            "HOST": required_env("DB_HOST"),  # noqa: F405
            "PORT": required_env("DB_PORT"),  # noqa: F405
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"connect_timeout": 5},
        }
    }
