"""Database-owned locks, shared across workers and released on rollback."""
from contextlib import contextmanager
from django.db import connection, OperationalError
from django.db.transaction import TransactionManagementError


def row_lock_options():
    return {"of": ("self",)} if connection.features.has_select_for_update_of else {}


def _sqlserver_lock(key, owner, timeout):
    with connection.cursor() as cursor:
        cursor.execute("""SET NOCOUNT ON;
            DECLARE @result int;
            EXEC @result = sys.sp_getapplock @Resource=%s,
                @LockMode='Exclusive', @LockOwner=%s, @LockTimeout=%s;
            SELECT @result;""", [f"qlnh:{key}", owner, timeout])
        return cursor.fetchone()[0] >= 0


def transaction_lock(key):
    if not connection.in_atomic_block:
        raise TransactionManagementError("Application transaction locks require transaction.atomic().")
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])
    elif connection.vendor == "microsoft":
        if not _sqlserver_lock(key, "Transaction", 10000):
            raise OperationalError("Could not acquire the application transaction lock.")
    else:
        raise OperationalError("This database does not support application locks.")


@contextmanager
def session_lock(key):
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
            acquired = cursor.fetchone()[0]
    elif connection.vendor == "microsoft":
        acquired = _sqlserver_lock(key, "Session", 0)
    else:
        raise OperationalError("This database does not support application locks.")
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
                else:
                    cursor.execute("EXEC sys.sp_releaseapplock @Resource=%s, @LockOwner='Session'", [f"qlnh:{key}"])
