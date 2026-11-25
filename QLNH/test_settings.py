"""Settings used by the test runner without production manifest URL rewriting."""

from .settings import *  # noqa: F403

# Tests explicitly opt in with dummy credentials; never inherit a real .env app.
ZALOPAY_APP_ID = ""
ZALOPAY_KEY1 = ""
ZALOPAY_KEY2 = ""
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURITY_RATE_LIMIT_ENABLED = False  # Dedicated tests explicitly enable shared rate limits.
CASH_SHIFT_REQUIRED = False
APRIORI_QUALITY_GATE_ENABLED = False  # Quality selection is covered by explicit gate tests.

STORAGES = {  # noqa: F405
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
