"""Copy a consistent PostgreSQL snapshot into a freshly migrated SQL Server DB."""
import json
import hashlib
from io import StringIO
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction


class Command(BaseCommand):
    help = "Copy local PostgreSQL to an empty SQL Server database; preserve original IDs and password hashes."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-target", required=True)
        parser.add_argument("--report", type=Path)

    def handle(self, *args, **options):
        if "postgres_source" not in connections:
            raise CommandError("Configure the local PostgreSQL source (DATABASE_URL or DB_*) before copying.")
        target, source = connections["default"], connections["postgres_source"]
        if target.vendor != "microsoft" or source.vendor != "postgresql":
            raise CommandError("Run with --settings=QLNH.sqlserver_settings and a PostgreSQL source.")
        if options["confirm_target"] != target.settings_dict["NAME"]:
            raise CommandError("--confirm-target must exactly match the SQL Server database name.")
        if source.settings_dict["HOST"] not in {"localhost", "127.0.0.1", "::1", ""}:
            raise CommandError("This command only copies the local PostgreSQL source.")
        # Refuse any database already in use; configuration seeded by migrate is
        # replaced only after these business tables have all been found empty.
        protected = ["accounts.User", "customers.Customer", "orders.Order", "orders.Payment",
                     "reservations.DepositPayment", "menu.Dish", "inventory.Ingredient", "employees.EmployeeProfile"]
        for label in protected:
            if apps.get_model(label)._base_manager.using("default").exists():
                raise CommandError(f"Target contains {label}; refusing to overwrite existing business data.")
        models = [model for model in apps.get_models(include_auto_created=True)
                  if model._meta.managed and not model._meta.proxy]
        tables = sorted({model._meta.db_table for model in models})
        directory = Path(settings.BASE_DIR) / "artifacts/sqlserver"
        directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=directory, suffix=".json", delete=False) as handle:
            path = Path(handle.name)
        os.chmod(path, 0o600)
        try:
            with transaction.atomic(using="postgres_source"):
                with source.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                with path.open("w", encoding="utf-8") as stream:
                    call_command("dumpdata", database="postgres_source", format="json_precise", use_base_manager=True,
                                 stdout=stream, verbosity=0)
                source_counts = {table: self.count(source, table) for table in tables}
            # loaddata preserves every PK and handles SQL Server IDENTITY_INSERT.
            # The outer transaction also rolls back the seed cleanup if loading,
            # constraint checking or row-count verification fails.
            with transaction.atomic(using="default"):
                # Recheck after exporting the source, holding table locks until
                # commit so an application write cannot race the empty check.
                with target.cursor() as cursor:
                    for table in tables:
                        cursor.execute(f"SELECT COUNT(*) FROM {target.ops.quote_name(table)} WITH (TABLOCKX, HOLDLOCK)")
                        cursor.fetchone()
                for label in protected:
                    if apps.get_model(label)._base_manager.using("default").exists():
                        raise CommandError(f"Target now contains {label}; copy rolled back.")
                with target.constraint_checks_disabled():
                    with target.cursor() as cursor:
                        for table in tables:
                            cursor.execute(f"DELETE FROM {target.ops.quote_name(table)}")
                    call_command("loaddata", str(path), database="default", verbosity=0)
                target.check_constraints()
                target_counts = {table: self.count(target, table) for table in tables}
                if target_counts != source_counts:
                    raise CommandError("Row counts differ; the SQL Server copy was rolled back.")
                stream = StringIO()
                call_command("dumpdata", database="default", format="json_precise", use_base_manager=True,
                             stdout=stream, verbosity=0)
                source_hash = self.digest(path.read_text(encoding="utf-8"))
                target_hash = self.digest(stream.getvalue())
                if source_hash != target_hash:
                    raise CommandError("Record contents differ; the SQL Server copy was rolled back.")
            # The report contains counts only, never rows or credentials.
            report = {"target": target.settings_dict["NAME"], "tables": target_counts,
                      "verified": True, "source_read_only": True, "records_sha256": target_hash}
            report_path = options["report"] or directory / "copy-report.json"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(
                f"Copied and verified {sum(target_counts.values())} rows across {len(tables)} tables. PostgreSQL was read-only."))
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def digest(value):
        rows = sorted(json.loads(value), key=lambda row: (row["model"], str(row["pk"])))
        return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def count(connection, table):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table)}")
            return cursor.fetchone()[0]
