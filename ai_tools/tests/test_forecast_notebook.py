import csv
from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ai_tools.forecast_demo import FIELDS
from ai_tools.forecast_notebook import prepare_run, read_dataset, train_run
from ai_tools.forecast_store import csv_bytes


class ForecastNotebookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.reference = date(2026, 12, 12)

    def rows(self, count=200, future=0):
        return [{"ngay": (self.reference - timedelta(days=count) + timedelta(days=i)).isoformat(),
                 "so_don": str(40 + i % 7), "nguon_du_lieu": "application_export"}
                for i in range(count + future)]

    def csv(self, rows, name="input.csv", fields=FIELDS):
        path = self.root / name
        path.write_bytes(csv_bytes(rows, fields))
        return path

    def prepare(self, path, **kwargs):
        return prepare_run(root=self.root / "runs", mode="csv", source="application_export",
                           csv_path=path, reference_date=self.reference.isoformat(), **kwargs)

    def test_demo_runs_are_seeded_and_preserve_previous_results(self):
        first = prepare_run(root=self.root, reference_date=self.reference.isoformat())
        original = (first / "input.csv").read_bytes()
        second = prepare_run(root=self.root, reference_date=self.reference.isoformat())
        self.assertNotEqual(first, second)
        self.assertEqual(original, (second / "input.csv").read_bytes())
        self.assertEqual(original, (first / "input.csv").read_bytes())
        self.assertEqual(read_dataset(first)["training_last_date"], "2026-12-11")
        self.assertFalse(list(self.root.rglob("current.json")))

    def test_application_mode_never_falls_back_to_demo(self):
        with self.assertRaises(ValueError):
            prepare_run(root=self.root, mode="demo", source="application_export")
        with self.assertRaises(FileNotFoundError):
            prepare_run(root=self.root, mode="csv", source="application_export", csv_path=self.root / "missing.csv")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_mode_and_source_are_rejected(self):
        for mode, source in (("invalid", "mo_phong"), ("demo", "invalid")):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                prepare_run(root=self.root, mode=mode, source=source)

    def test_csv_snapshot_excludes_future_and_extra_columns_without_modifying_source(self):
        rows = self.rows(future=4)
        for row in rows:
            row["extra_field"] = "not-for-the-result-archive"
        source = self.csv(rows, fields=[*FIELDS, "extra_field"])
        original = source.read_bytes()
        run = self.prepare(source)
        dataset = read_dataset(run)
        self.assertEqual(dataset["training_days"], 200)
        self.assertEqual(dataset["excluded_future_rows"], 4)
        self.assertEqual(dataset["training_last_date"], "2026-12-11")
        with (run / "input.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, FIELDS)
            self.assertEqual(len(list(reader)), 200)
        self.assertNotIn(b"not-for-the-result-archive", (run / "input.csv").read_bytes())
        self.assertEqual(source.read_bytes(), original)

    def test_missing_duplicate_negative_and_mixed_data_are_rejected(self):
        invalid_sets = []
        rows = self.rows()
        invalid_sets.append(rows[:10] + rows[11:])
        invalid_sets.append(rows[:10] + [dict(rows[9])] + rows[10:])
        rows = self.rows()
        rows[10]["so_don"] = "-1"
        invalid_sets.append(rows)
        rows = self.rows()
        rows[10]["nguon_du_lieu"] = "mo_phong"
        invalid_sets.append(rows)
        for i, rows in enumerate(invalid_sets):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.prepare(self.csv(rows, name=f"invalid-{i}.csv"))

    def test_missing_yesterday_and_insufficient_history_are_rejected(self):
        for i, rows in enumerate((self.rows()[:-1], self.rows(count=119))):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.prepare(self.csv(rows, name=f"short-{i}.csv"))

    def test_changed_snapshot_and_wrong_run_id_are_detected(self):
        run = self.prepare(self.csv(self.rows()))
        dataset_path = run / "dataset.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        dataset["run_id"] = "different_run"
        dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Run ID"):
            read_dataset(run)
        dataset["run_id"] = run.name
        dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
        with (run / "input.csv").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(ValueError, "CSV"):
            read_dataset(run)

    def test_trainer_failure_does_not_overwrite_previous_run_or_publish_results(self):
        run = self.prepare(self.csv(self.rows()))
        previous = self.root / "previous_success"
        previous.mkdir()
        (previous / "evaluation.json").write_text("previous success", encoding="utf-8")
        trainer = Mock(side_effect=RuntimeError("training failed"))
        with patch.dict("sys.modules", {"ai_tools.forecast_training": SimpleNamespace(train=trainer)}):
            with self.assertRaisesRegex(RuntimeError, "training failed"):
                train_run(run)
        self.assertEqual((previous / "evaluation.json").read_text(encoding="utf-8"), "previous success")
        self.assertFalse((run / "evaluation.json").exists())
        self.assertFalse(list(self.root.rglob("current.json")))

    def test_notebook_is_current_and_all_code_cells_compile(self):
        from scripts.build_forecast_notebook import BASE, build
        actual = json.loads((BASE / "notebooks/03_random_forest_du_bao_so_don.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(actual, build(), "Run scripts/build_forecast_notebook.py after changing embedded sources")
        self.assertEqual(actual["nbformat"], 4)
        for cell in actual["cells"]:
            if cell["cell_type"] == "code":
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])
                compile("".join(cell["source"]), cell["id"], "exec")
