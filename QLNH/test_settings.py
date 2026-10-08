"""Settings used by the test runner without production manifest URL rewriting."""

from .settings import *  # noqa: F403

STORAGES = {  # noqa: F405
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
