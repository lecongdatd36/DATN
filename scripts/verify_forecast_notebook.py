"""Execute every notebook code cell locally, including fresh training/report workers.

Checks demo mode and a synthetic CSV fixture with the application schema. The latter
tests upload/download wiring with mocks; it is not real sales data or a hosted Colab test.
"""
import argparse
import contextlib
import csv
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch
from uuid import uuid4
import zipfile

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from ai_tools.forecast_demo import extend_demo
from ai_tools.forecast_store import csv_bytes, read_daily


def verify_run(notebook, root, reference, application_fixture=False):
    root.mkdir(parents=True, exist_ok=False)
    uploads, downloads = [], []
    original_hash = None
    if application_fixture:
        demo = root / "fixture_demo.csv"
        extend_demo(demo, reference + timedelta(days=7))
        rows = read_daily(demo, "mo_phong")
        for row in rows:
            row["nguon_du_lieu"] = "application_export"
            row["extra_field"] = "do-not-export-this-field"
        fixture = root / "application_schema_fixture.csv"
        fixture.write_bytes(csv_bytes(rows, ["ngay", "so_don", "nguon_du_lieu", "extra_field"]))
        original_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        google, colab, files = ModuleType("google"), ModuleType("google.colab"), ModuleType("google.colab.files")
        google.__path__ = []
        colab.__path__ = []

        def upload():
            uploads.append(True)
            return {str(fixture): fixture.read_bytes()}

        files.upload = upload
        files.download = lambda path: downloads.append(path)
        colab.files, google.colab = files, colab
        fake_modules = {"google": google, "google.colab": colab, "google.colab.files": files}
    else:
        fake_modules = {}
    scope = {"__name__": "__notebook__"}
    log = io.StringIO()
    old_path = list(sys.path)
    original_modules = {name: value for name, value in sys.modules.items() if name == "ai_tools" or name.startswith("ai_tools.")}
    try:
        with patch.dict(os.environ, {"QLNH_FORECAST_NOTEBOOK_ROOT": str(root)}), patch.dict(sys.modules, fake_modules), contextlib.redirect_stdout(log):
            for cell in notebook["cells"]:
                if cell["cell_type"] != "code":
                    continue
                source = "".join(cell["source"])
                if cell["id"] == "configuration":
                    source = source.replace('REFERENCE_DATE = ""', f'REFERENCE_DATE = "{reference.isoformat()}"', 1)
                    if application_fixture:
                        source = source.replace('DATA_MODE = "demo"', 'DATA_MODE = "csv"', 1)
                        source = source.replace('DATA_SOURCE = "mo_phong"', 'DATA_SOURCE = "application_export"', 1)
                exec(compile(source, cell["id"], "exec"), scope)
            loaded = Path(sys.modules["ai_tools.forecast_notebook"].__file__).resolve()
            assert loaded.is_relative_to(scope["SUPPORT_ROOT"]), "Notebook must execute embedded code, not repository imports"
            folder, archive, report = scope["OUTPUT_DIR"], Path(scope["ARCHIVE"]), scope["REPORT"]
            expected_source = "application_export" if application_fixture else "mo_phong"
            assert report["data_source"] == expected_source
            assert report["reference_date"] == reference.isoformat()
            assert report["training_last_date"] == (reference - timedelta(days=1)).isoformat()
            assert report["excluded_future_rows"] == (8 if application_fixture else 0)
            assert scope["DATASET"]["run_id"] == report["run_id"] == folder.name
            with (folder / "du_bao_7_ngay.csv").open(encoding="utf-8-sig", newline="") as stream:
                forecast = list(csv.DictReader(stream))
            assert [row["ngay"] for row in forecast] == [(reference + timedelta(days=i)).isoformat() for i in range(7)]
            assert all(int(row["so_don_du_kien"]) >= 0 and row["run_id"] == folder.name and row["nguon_du_lieu"] == expected_source for row in forecast)
            with (folder / "kiem_tra_du_bao.csv").open(encoding="utf-8-sig", newline="") as stream:
                evaluation = list(csv.DictReader(stream))
            assert len(evaluation) == 28
            assert len({row["ngay_bat_dau_du_bao"] for row in evaluation}) == 4
            assert not list(root.rglob("current.json")), "Notebook must not publish a Dashboard manifest"
            with zipfile.ZipFile(archive) as stream:
                manifest = json.loads(stream.read("manifest.json"))
                assert manifest["run_id"] == folder.name
                for name, checksum in manifest["sha256"].items():
                    assert hashlib.sha256(stream.read(name)).hexdigest() == checksum
                assert set(stream.read("input.csv").decode("utf-8-sig").splitlines()[0].split(",")) == {"ngay", "so_don", "nguon_du_lieu"}
                assert "demo_input.csv" not in stream.namelist()
                assert "application_schema_fixture.csv" not in stream.namelist()
            from PIL import Image
            for name in report["charts"]:
                with Image.open(folder / "charts" / name) as chart:
                    assert chart.format == "PNG" and chart.width >= 1000
                    chart.verify()
            if application_fixture:
                assert uploads == [True] and downloads == [str(archive)]
                assert hashlib.sha256(fixture.read_bytes()).hexdigest() == original_hash
    finally:
        (root / "execution.log").write_text(log.getvalue(), encoding="utf-8")
        sys.path[:] = old_path
        for name in list(sys.modules):
            if name == "ai_tools" or name.startswith("ai_tools."):
                del sys.modules[name]
        sys.modules.update(original_modules)
    return {"mode": "application_schema_fixture" if application_fixture else "demo", "output": str(folder),
            "archive": str(archive), "mae_ai": report["mae_ai"], "mae_baseline": report["mae_baseline"],
            "charts": len(report["charts"]), "forecast_days": len(forecast), "evaluation_rows": len(evaluation)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date(2026, 12, 12))
    args = parser.parse_args()
    notebook = json.loads((BASE / "notebooks/03_random_forest_du_bao_so_don.ipynb").read_text(encoding="utf-8"))
    root = BASE / "artifacts/ai/forecast_notebook_validation" / uuid4().hex
    results = [verify_run(notebook, root / "demo", args.reference_date),
               verify_run(notebook, root / "csv", args.reference_date, application_fixture=True)]
    (root / "verification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("All notebook code cells and worker processes passed; Colab upload/download adapters tested with mocks.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
