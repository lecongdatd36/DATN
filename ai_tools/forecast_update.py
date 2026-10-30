"""Offline update orchestration; no Django, numpy, pandas or sklearn imports."""
import logging
import os
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .forecast_demo import FIELDS, extend_demo
from .forecast_store import (VIETNAM, UpdateLock, atomic_bytes, atomic_json,
                             csv_bytes, publish, read_published,
                             source_directory, training_rows, vietnam_today)

logger = logging.getLogger("qlnh.forecast_update")


def run_training(project, ai_python, folder, source, reference_date, run_id, log_path):
    if not ai_python.is_file():
        raise FileNotFoundError(f"AI Python not found: {ai_python}")
    command = [str(ai_python), str(project / "scripts/train_order_forecast.py"),
               "--input", str(folder / "input.csv"), "--output", str(folder),
               "--source", source, "--reference-date", reference_date.isoformat(),
               "--run-id", run_id]
    with log_path.open("ab") as stream:
        subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=3600,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})


def update_forecast(project, root, source="mo_phong", reference_date=None,
                    input_path=None, ai_python=None, force=False, trainer=run_training):
    project, root = Path(project).resolve(), Path(root).resolve()
    live_clock = reference_date is None
    reference_date = reference_date or vietnam_today()
    directory = source_directory(root, source)
    ai_python = Path(ai_python or project / "artifacts/ai/forecast_venv" /
                     ("Scripts/python.exe" if os.name == "nt" else "bin/python")).resolve()
    with UpdateLock(root):
        run_id = f"{reference_date:%Y%m%d}_{datetime.now(VIETNAM):%H%M%S}_{uuid.uuid4().hex}"
        try:
            if not force:
                try:
                    manifest, _, _ = read_published(root, source)
                except (OSError, ValueError, KeyError, TypeError):
                    manifest = None
                if manifest and manifest["reference_date"] == reference_date.isoformat():
                    logger.info("Already current: source=%s run=%s", source, manifest["run_id"])
                    return manifest
            if source == "mo_phong":
                if input_path is not None:
                    raise ValueError("Demo input is managed separately; --input is only for application_export")
                input_path = root / "daily_orders_demo_v1.csv"
                extend_demo(input_path, reference_date - timedelta(days=1))
            elif input_path is None:
                raise ValueError("application_export requires --input; no demo fallback")
            rows = training_rows(input_path, source, reference_date)
            folder = directory / "runs" / run_id
            folder.mkdir(parents=True, exist_ok=False)
            atomic_bytes(folder / "input.csv", csv_bytes(rows, FIELDS))
            logs = root / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            log_path = logs / f"{run_id}.log"
            logger.info("Training source=%s reference=%s run=%s log=%s", source, reference_date, run_id, log_path)
            trainer(project, ai_python, folder, source, reference_date, run_id, log_path)
            if live_clock and vietnam_today() != reference_date:
                raise ValueError("Vietnam date changed during training; retry for the new day")
            manifest = publish(root, source, run_id, reference_date)
            logger.info("Published source=%s reference=%s run=%s", source, reference_date, run_id)
        except Exception:
            logger.exception("Update failed; previous publication retained. source=%s run=%s", source, run_id)
            try:
                atomic_json(directory / "last_failure.json", {
                    "run_id": run_id, "reference_date": reference_date.isoformat(),
                    "failed_at": datetime.now(VIETNAM).isoformat(),
                })
            except OSError:
                logger.exception("Could not write failure status")
            raise
        return manifest
