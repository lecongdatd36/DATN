"""Forecast data/publication contract. Standard library only; also used by Django."""
import csv
import hashlib
import io
import json
import math
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
SOURCES = ("mo_phong", "application_export")
FILES = ("input.csv", "du_bao_7_ngay.csv", "evaluation.json",
         "kiem_tra_du_bao.csv", "forecast_demo.joblib")


def vietnam_today():
    return datetime.now(VIETNAM).date()


def source_directory(root, source):
    if source not in SOURCES:
        raise ValueError("Unknown forecast source")
    return Path(root) / source


def _retry_windows_sharing(operation):
    # Windows may briefly deny opening/replacing a file while a previous handle
    # is closing. Retry only this transient sharing case, never expose a partial file.
    for attempt in range(10):
        try:
            return operation()
        except PermissionError:
            if os.name != "nt" or attempt == 9:
                raise
            time.sleep(min(0.01 * (attempt + 1), 0.05))


def read_bytes(path):
    return _retry_windows_sharing(Path(path).read_bytes)


def atomic_bytes(path, content):
    """Replace one file on the same filesystem, never expose partial contents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _retry_windows_sharing(lambda: os.replace(temporary, path))
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2,
                                 allow_nan=False).encode("utf-8"))


def csv_bytes(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def read_daily(path, source):
    source_directory(".", source)
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"ngay", "so_don", "nguon_du_lieu"}.issubset(reader.fieldnames or []):
            raise ValueError("Daily CSV missing required columns")
        rows = list(reader)
    previous = None
    for row in rows:
        day = date.fromisoformat(row["ngay"])
        if previous is not None and day != previous + timedelta(days=1):
            raise ValueError("Daily CSV must have consecutive unique ordered dates; no filling gaps")
        if row["nguon_du_lieu"] != source:
            raise ValueError("Daily CSV source mismatch; sources must never be mixed")
        if not re.fullmatch(r"[0-9]+", row["so_don"]):
            raise ValueError("Orders must be nonnegative integers")
        previous = day
    if not rows:
        raise ValueError("Daily CSV is empty")
    return rows


def training_rows(path, source, reference_date):
    # A snapshot for a historical reference date must never contain future data.
    rows = [row for row in read_daily(path, source)
            if date.fromisoformat(row["ngay"]) < reference_date]
    if len(rows) < 120:
        raise ValueError("At least 120 consecutive training days are required")
    if date.fromisoformat(rows[-1]["ngay"]) != reference_date - timedelta(days=1):
        raise ValueError("Training data must end exactly yesterday; no synthetic application fallback")
    return rows


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def validate_result(metadata, rows, source, reference_date, run_id):
    if metadata["schema_version"] != 2 or metadata["run_id"] != run_id:
        raise ValueError("Metadata run identity mismatch")
    if metadata["data_source"] != source or metadata["timezone"] != "Asia/Ho_Chi_Minh":
        raise ValueError("Metadata source/timezone mismatch")
    if metadata["reference_date"] != reference_date.isoformat():
        raise ValueError("Reference date mismatch")
    if metadata["training_last_date"] != (reference_date - timedelta(days=1)).isoformat():
        raise ValueError("Training cutoff mismatch")
    if metadata["horizon_days"] != 7 or metadata["evaluation_days"] != 28:
        raise ValueError("Invalid forecast/evaluation horizon")
    if not metadata["final_model_refitted_on_all_days"]:
        raise ValueError("Final model was not refitted")
    for key in ("mae_ai", "mae_baseline", "rmse_ai"):
        value = metadata[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid evaluation metric")
    expected = [(reference_date + timedelta(days=i)).isoformat() for i in range(7)]
    if [row["ngay"] for row in rows] != expected:
        raise ValueError("Forecast must have exactly 7 consecutive days starting on reference date")
    for row in rows:
        if row["nguon_du_lieu"] != source or row["run_id"] != run_id:
            raise ValueError("Forecast CSV run/source mismatch")
        if not re.fullmatch(r"[0-9]+", row["so_don_du_kien"]):
            raise ValueError("Predictions must be nonnegative integers")


def load_bundle(folder, source, reference_date, run_id, hashes=None, full=False):
    folder = Path(folder)
    names = FILES if full else ("evaluation.json", "du_bao_7_ngay.csv")
    contents = {}
    for name in names:
        content = read_bytes(folder / name)
        if not content:
            raise ValueError(f"Empty artifact: {name}")
        if hashes is not None and sha256(content) != hashes[name]:
            raise ValueError(f"Artifact checksum mismatch: {name}")
        contents[name] = content
    metadata = json.loads(contents["evaluation.json"])
    rows = list(csv.DictReader(io.StringIO(contents["du_bao_7_ngay.csv"].decode("utf-8-sig"))))
    validate_result(metadata, rows, source, reference_date, run_id)
    if full:
        if metadata["input_sha256"] != sha256(contents["input.csv"]):
            raise ValueError("Training input checksum mismatch")
        if metadata["model_sha256"] != sha256(contents["forecast_demo.joblib"]):
            raise ValueError("Model/metadata checksum mismatch")
        daily = training_rows(folder / "input.csv", source, reference_date)
        if metadata["training_days"] != len(daily):
            raise ValueError("Training input length mismatch")
        evaluation = list(csv.DictReader(io.StringIO(contents["kiem_tra_du_bao.csv"].decode("utf-8-sig"))))
        expected_days = [(reference_date - timedelta(days=i)).isoformat() for i in range(28, 0, -1)]
        if [row["ngay"] for row in evaluation] != expected_days:
            raise ValueError("Evaluation must cover the last 28 training days")
        for i, row in enumerate(evaluation):
            if row["run_id"] != run_id or row["nguon_du_lieu"] != source:
                raise ValueError("Evaluation run/source mismatch")
            origin = expected_days[(i // 7) * 7]
            if row["ngay_bat_dau_du_bao"] != origin or int(row["buoc_du_bao"]) != i % 7 + 1:
                raise ValueError("Invalid rolling evaluation origin")
            for key in ("thuc_te", "du_bao_ai", "du_bao_tuan_truoc"):
                value = float(row[key])
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid evaluation prediction")
    return metadata, rows


def publish(root, source, run_id, reference_date):
    directory = source_directory(root, source)
    folder = directory / "runs" / run_id
    load_bundle(folder, source, reference_date, run_id, full=True)
    manifest = {
        "schema_version": 2, "run_id": run_id, "data_source": source,
        "reference_date": reference_date.isoformat(),
        "published_at": datetime.now(VIETNAM).isoformat(),
        "sha256": {name: sha256((folder / name).read_bytes()) for name in FILES},
    }
    # Only this pointer changes. Published run directories must never be edited/deleted.
    atomic_json(directory / "current.json", manifest)
    return manifest


def read_published(root, source):
    directory = source_directory(root, source)
    manifest = json.loads(read_bytes(directory / "current.json"))
    run_id = manifest["run_id"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid run directory")
    if manifest["schema_version"] != 2 or manifest["data_source"] != source:
        raise ValueError("Invalid publication manifest")
    reference_date = date.fromisoformat(manifest["reference_date"])
    metadata, rows = load_bundle(directory / "runs" / run_id, source,
                                 reference_date, run_id, manifest["sha256"])
    return manifest, metadata, rows


class UpdateAlreadyRunning(RuntimeError):
    pass


class UpdateLock:
    """OS lock; released even on process death. Never unlink the lock file."""
    def __init__(self, root):
        self.path = Path(root) / "update.lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise UpdateAlreadyRunning("Another forecast update holds the lock") from exc
        return self

    def __exit__(self, *args):
        if os.name == "nt":
            import msvcrt
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()
