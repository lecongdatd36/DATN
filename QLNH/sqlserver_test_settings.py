"""Run the same application regression suite against SQL Server."""
from copy import deepcopy
from .sqlserver_settings import *  # noqa: F403
from .test_defaults import *  # noqa: F403
from .sqlserver_settings import DATABASES as SQLSERVER_DATABASES, DATABASE_CONNECTION_POOLING

# The PostgreSQL alias exists only for the explicit data-copy command. Browser
# harnesses call setup_databases() directly and must never create/migrate it.
DATABASES = {"default": deepcopy(SQLSERVER_DATABASES["default"])}
