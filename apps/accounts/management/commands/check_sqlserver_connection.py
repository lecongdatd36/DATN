"""Read-only connection preflight; never print credentials or modify the DB."""
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection


class Command(BaseCommand):
    help = "Check SQL Server connectivity, database name and server version without changing data."

    def handle(self, *args, **options):
        if connection.vendor != "microsoft":
            raise CommandError("Select DJANGO_SETTINGS_MODULE=QLNH.sqlserver_settings.")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ProductVersion') AS varchar(128))")
                database, version = cursor.fetchone()
        except (DatabaseError, ImportError, OSError) as error:
            # Native-driver errors can include connection details; keep them out of build logs.
            raise CommandError(
                "SQL Server connection failed. Check SQLSERVER_HOST/PORT/DB/USER/PASSWORD, "
                "TLS certificate, native driver dependencies and the hosting IP allowlist. "
                f"Error type: {type(error).__name__}."
            ) from None
        finally:
            connection.close()
        if database != connection.settings_dict["NAME"]:
            raise CommandError("Connected to an unexpected database; stopping before migrations.")
        self.stdout.write(self.style.SUCCESS(f"SQL Server {version}: database {database}; connection OK (read-only)."))
