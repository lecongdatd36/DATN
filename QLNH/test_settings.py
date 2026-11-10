"""Settings used by the test runner without production manifest URL rewriting."""

from .settings import *  # noqa: F403

# Tests explicitly opt in with dummy credentials; never inherit a real .env app.
ZALOPAY_APP_ID = ""
ZALOPAY_KEY1 = ""
ZALOPAY_KEY2 = ""

STORAGES = {  # noqa: F405
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
