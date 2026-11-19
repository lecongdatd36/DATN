"""AI-environment integration test for zero-order data and downloadable result integrity."""
from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from ai_tools.forecast_demo import FIELDS
from ai_tools.forecast_notebook import PLOTS, create_archive, create_report, prepare_run, train_run
from ai_tools.forecast_store import csv_bytes


class NotebookTrainingTests(unittest.TestCase):
    def test_zero_baseline_reporting_history_and_corruption_checks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference = date(2027, 1, 1)
            rows = [{"ngay": (reference - timedelta(days=120) + timedelta(days=i)).isoformat(),
                     "so_don": "0", "nguon_du_lieu": "application_export"} for i in range(120)]
            source = root / "zeros.csv"
            source.write_bytes(csv_bytes(rows, FIELDS))
            run = prepare_run(root=root / "runs", mode="csv", source="application_export",
                              reference_date=reference.isoformat(), csv_path=source)
            train_run(run)
            report = create_report(run)
            self.assertEqual(report["mae_ai"], 0)
            self.assertEqual(report["mae_baseline"], 0)
            self.assertEqual(report["rmse_baseline"], 0)
            self.assertIsNone(report["mae_improvement_percent"])
            self.assertEqual(report["reference_date"], "2027-01-01")
            self.assertTrue(all((run / "charts" / name).is_file() for name in PLOTS))
            first, second = create_archive(run), create_archive(run)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file())
            with zipfile.ZipFile(first) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["run_id"], run.name)
                self.assertEqual(len(manifest["sha256"]), 16)
                self.assertIn(b"2027-01-07", archive.read("du_bao_7_ngay.csv"))
            with self.assertRaises(FileExistsError):
                train_run(run)
            with self.assertRaises(FileExistsError):
                create_report(run)
            with (run / "forecast_demo.joblib").open("ab") as stream:
                stream.write(b"corrupted")
            with self.assertRaisesRegex(ValueError, "checksum"):
                create_archive(run)


if __name__ == "__main__":
    unittest.main()
