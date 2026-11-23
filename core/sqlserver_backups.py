"""COPY_ONLY SQL Server backups; restore checks always use a UUID database."""
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.db import connection, connections


def fingerprint(cursor):
    cursor.execute("""SELECT t.name, c.name, ty.name, c.max_length, c.precision,
        c.scale, c.is_nullable, c.is_identity, c.is_computed
        FROM sys.tables t JOIN sys.columns c ON c.object_id=t.object_id
        JOIN sys.types ty ON ty.user_type_id=c.user_type_id
        ORDER BY t.name,c.column_id""")
    return hashlib.sha256(json.dumps(cursor.fetchall(), ensure_ascii=False).encode()).hexdigest()


def execute(cursor, sql, params):
    cursor.execute(sql, params)
    while cursor.nextset():
        pass


def create_backup(directory=None):
    directory = Path(directory or settings.BASE_DIR / "artifacts/backups").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime("qlnh_%Y%m%dT%H%M%SZ_") + uuid4().hex[:8] + ".bak")
    name = connection.ops.quote_name(connection.settings_dict["NAME"])
    with connection.cursor() as cursor:
        schema_hash = fingerprint(cursor)
        execute(cursor, f"BACKUP DATABASE {name} TO DISK=%s WITH COPY_ONLY, CHECKSUM", [str(path)])
        execute(cursor, "RESTORE VERIFYONLY FROM DISK=%s WITH CHECKSUM", [str(path)])
    if not path.is_file():
        raise ValueError("SQL Server backup path must be accessible to both SQL Server and this application.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {"format": "sqlserver-native", "file": path.name, "sha256": digest,
                "schema_sha256": schema_hash, "created_at": datetime.now(timezone.utc).isoformat(),
                "backup_verified": True, "restore_verified": False}
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def verify_restore(backup):
    path = Path(backup).resolve()
    manifest_path = path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "sqlserver-native":
        raise ValueError("Expected a SQL Server native backup.")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["sha256"]:
            raise ValueError("Backup checksum does not match.")
    database = "qlnh_restore_" + uuid4().hex
    if not re.fullmatch(r"qlnh_restore_[0-9a-f]{32}", database) or database == connection.settings_dict["NAME"]:
        raise ValueError("Unsafe restore database name.")
    name = connection.ops.quote_name(database)
    with connection.cursor() as cursor:
        cursor.execute("RESTORE FILELISTONLY FROM DISK=%s", [str(path)])
        files = cursor.fetchall()
    moves, params = [], [str(path)]
    for index, row in enumerate(files):
        if row[2] not in {"D", "L"}:
            raise ValueError("Only standard SQL Server data/log backups are supported.")
        moves.append("MOVE %s TO %s")
        params.extend([row[0], str(path.parent / f"{database}_{index}.{'ldf' if row[2] == 'L' else 'mdf'}")])
    restored = None
    alias = database
    try:
        with connection.cursor() as cursor:
            execute(cursor, f"RESTORE DATABASE {name} FROM DISK=%s WITH " + ", ".join(moves), params)
        configuration = {**connection.settings_dict, "NAME": database}
        connections.databases[alias] = configuration
        restored = connections[alias]
        with restored.cursor() as cursor:
            if fingerprint(cursor) != manifest["schema_sha256"]:
                raise ValueError("Restored schema differs from the backup.")
        manifest["restore_verified"] = True
        manifest["verified_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    finally:
        if restored is not None:
            restored.close()
            del connections[alias]
        connections.databases.pop(alias, None)
        with connection.cursor() as cursor:
            cursor.execute("SELECT DB_ID(%s)", [database])
            if cursor.fetchone()[0] is not None:
                cursor.execute(f"DROP DATABASE {name}")
    return manifest
