"""Common test overrides without importing a database profile."""
from .base_settings import *  # noqa: F403

# Tests explicitly opt in with dummy credentials; never inherit a real .env app.
ZALOPAY_APP_ID = ""
ZALOPAY_KEY1 = ""
ZALOPAY_KEY2 = ""
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURITY_RATE_LIMIT_ENABLED = False
CASH_SHIFT_REQUIRED = False
APRIORI_QUALITY_GATE_ENABLED = False

STORAGES = {  # noqa: F405
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
