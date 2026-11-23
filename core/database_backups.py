"""Database backups and restoration checks into a disposable database."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4
from django.conf import settings
from django.db import connection
from psycopg import connect, sql


def executable(name):
    configured = os.environ.get(name.upper() + "_PATH")
    found = configured or shutil.which(name)
    if not found and os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PostgreSQL"
        versions = sorted((p for p in root.glob("*") if p.name.isdigit()), key=lambda p: int(p.name), reverse=True)
        found = next((str(p / "bin" / (name + ".exe")) for p in versions if (p / "bin" / (name + ".exe")).is_file()), None)
    if not found:
        raise ValueError(f"Chưa tìm thấy {name}; cấu hình {name.upper()}_PATH.")
    return found


def db_environment(database=None):
    db = connection.settings_dict
    if connection.vendor != "postgresql":
        raise ValueError("Chỉ hỗ trợ PostgreSQL.")
    env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}}
    env.update({"PGDATABASE": str(database or db["NAME"]), "PGUSER": str(db["USER"]), "PGPASSWORD": str(db["PASSWORD"]),
        "PGHOST": str(db["HOST"] or "localhost"), "PGPORT": str(db["PORT"] or 5432), "PGCONNECT_TIMEOUT": "10"})
    for key, value in db.get("OPTIONS", {}).items():
        if key in {"sslmode", "sslrootcert", "sslcert", "sslkey"}:
            env["PG" + key.upper()] = str(value)
    return env


def fingerprint(cursor):
    cursor.execute("""SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid WHERE n.nspname=current_schema()
        AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""")
    return hashlib.sha256(json.dumps(cursor.fetchall(), ensure_ascii=False).encode()).hexdigest()


def run(args, *, database=None):
    result = subprocess.run(args, env=db_environment(database), capture_output=True, timeout=600, shell=False)
    if result.returncode:
        raise ValueError(f"Công cụ PostgreSQL thất bại (mã {result.returncode}); không ghi đè database đang sử dụng.")
    return result


def create_backup(directory=None):
    if connection.vendor == "microsoft":
        from .sqlserver_backups import create_backup as sqlserver_backup
        return sqlserver_backup(directory)
    directory = Path(directory or settings.BASE_DIR / "artifacts/backups").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("qlnh_%Y%m%dT%H%M%SZ_") + uuid4().hex[:8] + ".dump"
    output = directory / name
    temporary = output.with_suffix(".dump.partial")
    manifest = output.with_suffix(".manifest.json")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with connection.cursor() as cursor:
            schema_hash = fingerprint(cursor)
        run([executable("pg_dump"), "--format=custom", "--no-owner", "--no-privileges", "--file", str(temporary)])
        run([executable("pg_restore"), "--list", str(temporary)])
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        temporary.replace(output)
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump({"format": "postgresql-custom", "created_at": datetime.now(timezone.utc).isoformat(),
                "file": output.name, "sha256": digest, "schema_sha256": schema_hash, "restore_verified": False}, stream, indent=2)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def verify_restore(backup):
    if connection.vendor == "microsoft":
        from .sqlserver_backups import verify_restore as sqlserver_restore
        return sqlserver_restore(backup)
    backup = Path(backup).resolve()
    manifest_path = backup.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with backup.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["sha256"]:
            raise ValueError("Checksum bản sao lưu không khớp.")
    database = "qlnh_restore_" + uuid4().hex
    if not re.fullmatch(r"qlnh_restore_[0-9a-f]{32}", database) or database == connection.settings_dict["NAME"]:
        raise ValueError("Tên database kiểm chứng không an toàn.")
    env = db_environment()
    params = {"host": env["PGHOST"], "port": env["PGPORT"], "user": env["PGUSER"], "password": env["PGPASSWORD"],
        "dbname": env["PGDATABASE"], "autocommit": True, "connect_timeout": 10}
    for name in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
        if "PG" + name.upper() in env:
            params[name] = env["PG" + name.upper()]
    with connect(**params) as administration:
        administration.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
        try:
            run([executable("pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", database, str(backup)], database=database)
            with connect(**{**params, "dbname": database}) as restored:
                with restored.cursor() as cursor:
                    if fingerprint(cursor) != manifest["schema_sha256"]:
                        raise ValueError("Schema sau khôi phục khác bản sao lưu.")
            manifest["restore_verified"] = True
            manifest["verified_at"] = datetime.now(timezone.utc).isoformat()
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        finally:
            # Only the UUID database created by this invocation is ever dropped.
            administration.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
    return manifest
