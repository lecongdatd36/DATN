import csv
import io
import json
import subprocess
import sys
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_tools.forecast_demo import FIELDS, extend_demo
from ai_tools.forecast_store import (UpdateLock, atomic_bytes, atomic_json, csv_bytes,
                                     read_daily, read_published, sha256, training_rows)
from ai_tools.forecast_update import update_forecast

PROJECT = Path(__file__).resolve().parents[2]


def fixture_trainer(project, ai_python, folder, source, reference, run_id, log_path):
    """Small valid artifacts for orchestration tests; AI correctness tested separately."""
    daily = training_rows(folder / "input.csv", source, reference)
    metadata = {
        "schema_version": 2, "run_id": run_id, "data_source": source,
        "timezone": "Asia/Ho_Chi_Minh", "reference_date": reference.isoformat(),
        "training_last_date": (reference - timedelta(days=1)).isoformat(),
        "training_days": len(daily), "input_sha256": sha256((folder / "input.csv").read_bytes()),
        "model_sha256": sha256(b"fixture-model-only"),
        "horizon_days": 7, "evaluation_days": 28,
        "final_model_refitted_on_all_days": True, "mae_ai": 0, "mae_baseline": 0, "rmse_ai": 0,
    }
    atomic_json(folder / "evaluation.json", metadata)
    rows = [{"ngay": (reference + timedelta(days=i)).isoformat(), "so_don_du_kien": str(reference.day + i),
             "nguon_du_lieu": source, "run_id": run_id} for i in range(7)]
    atomic_bytes(folder / "du_bao_7_ngay.csv", csv_bytes(rows, list(rows[0])))
    evaluation = [{"ngay": (reference - timedelta(days=28 - i)).isoformat(),
                   "ngay_bat_dau_du_bao": (reference - timedelta(days=28 - (i // 7) * 7)).isoformat(),
                   "buoc_du_bao": i % 7 + 1, "thuc_te": 1, "du_bao_ai": 1,
                   "du_bao_tuan_truoc": 1, "run_id": run_id, "nguon_du_lieu": source} for i in range(28)]
    atomic_bytes(folder / "kiem_tra_du_bao.csv", csv_bytes(evaluation, list(evaluation[0])))
    (folder / "forecast_demo.joblib").write_bytes(b"fixture-model-only")


class ForecastUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = date(2026, 10, 30)

    def update(self, reference=None, **kwargs):
        return update_forecast(PROJECT, self.root, reference_date=reference or self.reference,
                               trainer=kwargs.pop("trainer", fixture_trainer), **kwargs)

    def test_demo_extension_preserves_old_rows_and_seed(self):
        one, two = self.root / "one.csv", self.root / "two.csv"
        extend_demo(one, date(2026, 10, 29))
        old = read_daily(one, "mo_phong")
        self.assertEqual([row["so_don"] for row in old[:4]], ["37", "45", "60", "59"])
        extend_demo(one, date(2026, 12, 31))
        extend_demo(two, date(2026, 12, 31))
        self.assertEqual(read_daily(one, "mo_phong")[:len(old)], old)
        self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_month_year_and_leap_day_references_produce_new_runs(self):
        ids = set()
        for reference in (date(2026, 10, 31), date(2026, 11, 1), date(2026, 12, 31),
                          date(2027, 1, 1), date(2028, 2, 29), date(2028, 3, 1)):
            manifest = self.update(reference)
            _, metadata, rows = read_published(self.root, "mo_phong")
            ids.add(manifest["run_id"])
            self.assertEqual(rows[0]["ngay"], reference.isoformat())
            self.assertEqual(rows[-1]["ngay"], (reference + timedelta(days=6)).isoformat())
            self.assertEqual(metadata["training_last_date"], (reference - timedelta(days=1)).isoformat())
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(list((self.root / "mo_phong/runs").iterdir())), 6)

    def test_snapshot_excludes_future_values(self):
        path = self.root / "daily_orders_demo_v1.csv"
        extend_demo(path, date(2027, 1, 10))
        self.update(date(2026, 12, 12))
        manifest, _, _ = read_published(self.root, "mo_phong")
        snapshot = self.root / "mo_phong/runs" / manifest["run_id"] / "input.csv"
        self.assertEqual(read_daily(snapshot, "mo_phong")[-1]["ngay"], "2026-12-11")

    def test_missing_day_duplicate_negative_and_mixed_source_rejected(self):
        path = self.root / "data.csv"
        extend_demo(path, self.reference - timedelta(days=1))
        original = read_daily(path, "mo_phong")
        for kind in ("missing", "duplicate", "negative", "mixed"):
            rows = [dict(row) for row in original]
            if kind == "missing": rows.pop(30)
            if kind == "duplicate": rows[30]["ngay"] = rows[29]["ngay"]
            if kind == "negative": rows[30]["so_don"] = "-1"
            if kind == "mixed": rows[30]["nguon_du_lieu"] = "application_export"
            atomic_bytes(path, csv_bytes(rows, FIELDS))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                training_rows(path, "mo_phong", self.reference)

    def test_application_requires_input_and_never_falls_back(self):
        self.update()
        with self.assertLogs("qlnh.forecast_update", level="ERROR"), self.assertRaises(ValueError):
            self.update(source="application_export")
        self.assertFalse((self.root / "application_export/current.json").exists())
        self.assertTrue((self.root / "mo_phong/current.json").exists())
        path = self.root / "app.csv"
        path.write_bytes((self.root / "daily_orders_demo_v1.csv").read_bytes())
        with self.assertLogs("qlnh.forecast_update", level="ERROR"), self.assertRaises(ValueError):
            self.update(source="application_export", input_path=path)
        rows = read_daily(path, "mo_phong")
        for row in rows: row["nguon_du_lieu"] = "application_export"
        atomic_bytes(path, csv_bytes(rows, FIELDS))
        self.update(source="application_export", input_path=path)
        self.assertEqual(read_published(self.root, "application_export")[1]["data_source"], "application_export")

    def test_missing_yesterday_or_too_little_history_rejected(self):
        path = self.root / "input.csv"
        extend_demo(path, self.reference - timedelta(days=2))
        with self.assertRaises(ValueError): training_rows(path, "mo_phong", self.reference)
        with self.assertRaises(ValueError): training_rows(path, "mo_phong", date(2025, 12, 1))

    def test_training_failure_retains_previous_publication_and_logs(self):
        self.update()
        pointer = self.root / "mo_phong/current.json"
        before = pointer.read_bytes()
        def fail(*args): raise RuntimeError("simulated trainer failure")
        with self.assertLogs("qlnh.forecast_update", level="ERROR"), self.assertRaises(RuntimeError):
            self.update(self.reference + timedelta(days=1), trainer=fail)
        self.assertEqual(pointer.read_bytes(), before)
        self.assertTrue((self.root / "mo_phong/last_failure.json").exists())

    def test_invalid_outputs_never_publish(self):
        self.update()
        pointer = self.root / "mo_phong/current.json"
        before = pointer.read_bytes()
        for kind in ("source", "run", "date", "fraction", "negative", "metric", "metadata_run", "training_cutoff", "evaluation", "missing_model", "wrong_model"):
            def bad(*args):
                fixture_trainer(*args)
                folder = args[2]
                path = folder / "du_bao_7_ngay.csv"
                rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
                if kind == "source": rows[0]["nguon_du_lieu"] = "application_export"
                if kind == "run": rows[0]["run_id"] = "wrong"
                if kind == "date": rows[0]["ngay"] = "2020-01-01"
                if kind == "fraction": rows[0]["so_don_du_kien"] = "1.5"
                if kind == "negative": rows[0]["so_don_du_kien"] = "-2"
                atomic_bytes(path, csv_bytes(rows, list(rows[0])))
                if kind in ("metric", "metadata_run", "training_cutoff"):
                    path = folder / "evaluation.json"
                    value = json.loads(path.read_text())
                    if kind == "metric": value["mae_ai"] = -1
                    if kind == "metadata_run": value["run_id"] = "another-run"
                    if kind == "training_cutoff": value["training_last_date"] = "2030-01-01"
                    atomic_json(path, value)
                if kind == "evaluation": (folder / "kiem_tra_du_bao.csv").write_text("broken")
                if kind == "missing_model": (folder / "forecast_demo.joblib").unlink()
                if kind == "wrong_model": (folder / "forecast_demo.joblib").write_bytes(b"model-from-another-run")
            with self.subTest(kind=kind), self.assertLogs("qlnh.forecast_update", level="ERROR"):
                with self.assertRaises((ValueError, OSError)):
                    self.update(trainer=bad, force=True)
            self.assertEqual(pointer.read_bytes(), before)

    def test_atomic_pointer_swap_and_publish_failure(self):
        old = self.update()
        from ai_tools import forecast_store
        real_atomic = forecast_store.atomic_json
        observed = []
        def swap(path, value):
            observed.append(read_published(self.root, "mo_phong")[0]["run_id"])
            real_atomic(path, value)
            observed.append(read_published(self.root, "mo_phong")[0]["run_id"])
        with patch.object(forecast_store, "atomic_json", side_effect=swap):
            new = self.update(self.reference + timedelta(days=1))
        self.assertEqual(observed, [old["run_id"], new["run_id"]])
        with patch.object(forecast_store, "atomic_json", side_effect=OSError("replace failed")):
            with self.assertLogs("qlnh.forecast_update", level="ERROR"), self.assertRaises(OSError):
                self.update(self.reference + timedelta(days=2))
        self.assertEqual(read_published(self.root, "mo_phong")[0]["run_id"], new["run_id"])

    def test_corrupted_published_csv_detected_by_checksum(self):
        manifest = self.update()
        path = self.root / "mo_phong/runs" / manifest["run_id"] / "du_bao_7_ngay.csv"
        path.write_text("corrupted")
        with self.assertRaises(ValueError): read_published(self.root, "mo_phong")

    def test_reader_during_repeated_publications_never_mixes_runs(self):
        self.update()
        stopped = threading.Event()
        started = threading.Event()
        failures = []
        def reader():
            while not stopped.is_set():
                try:
                    manifest, metadata, rows = read_published(self.root, "mo_phong")
                    self.assertEqual(manifest["run_id"], metadata["run_id"])
                    self.assertEqual({row["run_id"] for row in rows}, {manifest["run_id"]})
                    started.set()
                except Exception as exc:
                    failures.append(exc)
                    started.set()
                    return
        worker = threading.Thread(target=reader)
        worker.start()
        try:
            self.assertTrue(started.wait(10))
            for _ in range(10): self.update(force=True)
        finally:
            stopped.set()
            worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])

    def test_same_day_is_idempotent_force_keeps_history(self):
        old = self.update()
        def fail(*args): raise AssertionError("Trainer should not be invoked")
        self.assertEqual(self.update(trainer=fail), old)
        new = self.update(force=True)
        self.assertNotEqual(old["run_id"], new["run_id"])
        self.assertTrue((self.root / "mo_phong/runs" / old["run_id"]).exists())

    def test_separate_process_cannot_update_while_locked(self):
        with UpdateLock(self.root):
            result = subprocess.run([sys.executable, str(PROJECT / "scripts/update_forecast_daily.py"),
                                     "--root", str(self.root)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("another manual/scheduled update", result.stderr)
            self.assertFalse((self.root / "mo_phong").exists())
        self.update()  # Lock released; the next updater can proceed.

    def test_dead_process_releases_lock(self):
        code = "from ai_tools.forecast_store import UpdateLock; import sys; lock=UpdateLock(sys.argv[1]); lock.__enter__(); print('LOCKED', flush=True); sys.stdin.read()"
        child = subprocess.Popen([sys.executable, "-c", code, str(self.root)], cwd=PROJECT,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "LOCKED")
        finally:
            child.terminate()
            child.communicate(timeout=10)
        self.update()

    def test_live_midnight_rollover_rejects_obsolete_run(self):
        with patch("ai_tools.forecast_update.vietnam_today", side_effect=[self.reference, self.reference + timedelta(days=1)]):
            with self.assertLogs("qlnh.forecast_update", level="ERROR"), self.assertRaises(ValueError):
                update_forecast(PROJECT, self.root, trainer=fixture_trainer)
        self.assertFalse((self.root / "mo_phong/current.json").exists())


if __name__ == "__main__":
    unittest.main()
