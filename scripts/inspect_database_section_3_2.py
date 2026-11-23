"""Read-only PostgreSQL schema evidence and figures for thesis section 3.2."""
import collections
import json
import os
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
import django
django.setup()
from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

OUT = ROOT / "docs" / "section-3-2"
OUT.mkdir(parents=True, exist_ok=True)
models = {m._meta.db_table: m for m in apps.get_models(include_auto_created=True)}
with connection.cursor() as cur:
    cur.execute("BEGIN READ ONLY")
    try:
        cur.execute("SHOW server_version")
        server = cur.fetchone()[0]
        cur.execute("SHOW transaction_isolation")
        isolation = cur.fetchone()[0]
        cur.execute("SHOW TimeZone")
        db_timezone = cur.fetchone()[0]
        cur.execute("""SELECT c.relname, a.attnum, a.attname,
                       pg_catalog.format_type(a.atttypid,a.atttypmod), a.attnotnull
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
            WHERE n.nspname='public' AND c.relkind='r'
                  AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname,a.attnum""")
        tables = {}
        for name, ordinal, col, dtype, notnull in cur.fetchall():
            table = tables.setdefault(name, {"name": name, "columns": []})
            table["columns"].append({"name": col, "type": dtype, "nullable": not notnull})
        cur.execute("""SELECT c.relname, co.conname, co.contype,
                              pg_get_constraintdef(co.oid), co.confdeltype,
                              co.condeferrable, co.condeferred
            FROM pg_catalog.pg_constraint co
            JOIN pg_catalog.pg_class c ON c.oid=co.conrelid
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' ORDER BY c.relname,co.conname""")
        for name, cname, kind, definition, delete, deferred, initially in cur.fetchall():
            tables[name].setdefault("constraints", []).append({
                "name": cname, "kind": kind, "definition": definition,
                "delete_code": delete, "deferrable": deferred, "initially_deferred": initially,
            })
        cur.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname")
        for name, index, definition in cur.fetchall():
            tables[name].setdefault("indexes", []).append({"name": index, "definition": definition})
        executor = MigrationExecutor(connection)
        pending = [f"{m.app_label}.{m.name}" for m, backwards in executor.migration_plan(executor.loader.graph.leaf_nodes())]
        applied = sorted(f"{label}.{name}" for label, name in executor.loader.applied_migrations)
        for name, table in tables.items():
            model = models.get(name)
            if not model:
                continue
            table["model"] = model._meta.label
            table["app"] = model._meta.app_label
            table["fields"] = []
            for field in model._meta.local_fields:
                record = {"name": field.name, "column": field.column, "class": field.get_internal_type(), "unique": field.unique}
                if field.is_relation:
                    record.update(target=field.related_model._meta.db_table,
                                  on_delete=field.remote_field.on_delete.__name__, unique=field.unique)
                table["fields"].append(record)
            table["model_column_match"] = {f.column for f in model._meta.local_fields} == {c["name"] for c in table["columns"]}
    finally:
        cur.execute("ROLLBACK")

counts = collections.Counter(c["kind"] for t in tables.values() for c in t.get("constraints", []))
groups = collections.Counter(t.get("app", "technical") for t in tables.values())
snapshot = {"checked_at": datetime.now().astimezone().isoformat(), "server": server,
    "transaction_isolation": isolation, "database_timezone": db_timezone,
    "django_timezone": settings.TIME_ZONE, "use_tz": settings.USE_TZ,
    "table_count": len(tables), "column_count": sum(len(t["columns"]) for t in tables.values()),
    "constraint_counts": dict(counts), "table_groups": dict(groups),
    "index_count": sum(len(t.get("indexes", [])) for t in tables.values()),
    "applied_migration_count": len(applied), "pending_migrations": pending,
    "model_column_mismatches": [n for n,t in tables.items() if t.get("model_column_match") is False],
    "scope": "Read-only public schema metadata; no business records or credentials exported.",
    "tables": list(tables.values())}
(OUT / "postgresql-schema-evidence.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in snapshot.items() if k != "tables"}, ensure_ascii=True, indent=2))
