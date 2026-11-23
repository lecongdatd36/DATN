"""Export a fresh anonymous snapshot, evaluate offline, publish only after quality gates pass."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-python", type=Path, required=True)
    parser.add_argument("--provenance", choices=("unverified", "test", "confirmed_business"), required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/ai/apriori-refresh")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
    import django
    django.setup()
    from django.conf import settings
    from apps.orders.ai_export import transaction_rows
    from ai_tools.schema import TRANSACTION_FIELDS
    from ai_tools.quality import assess_model_quality
    from ai_tools.inference import load_model
    from ai_tools.forecast_store import atomic_bytes
    from django.utils import timezone
    folder = args.output_root / (timezone.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:10])
    folder.mkdir(parents=True, exist_ok=False)
    csv_path = folder / "transactions.csv"
    count, baskets = 0, set()
    with csv_path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRANSACTION_FIELDS)
        writer.writeheader()
        for row in transaction_rows(end_at=timezone.now()):
            writer.writerow(row)
            count += 1
            baskets.add(row["basket_id"])
    report = {"rows": count, "baskets": len(baskets), "provenance": args.provenance, "published": False}
    if len(baskets) < 2:
        report["reason"] = "Chưa đủ giỏ đã thanh toán để đánh giá; giữ model hiện tại."
    else:
        result = subprocess.run([str(args.ai_python.resolve()), "-X", "utf8", str(ROOT / "scripts/train_apriori.py"),
            str(csv_path), "--output", str(folder / "results"), "--provenance", args.provenance],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300)
        if result.returncode:
            report["reason"] = "Huấn luyện/đánh giá không hoàn tất; giữ model hiện tại."
            (folder / "training.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        else:
            model_path = folder / "results/apriori_model.json"
            model = load_model(model_path)
            quality = assess_model_quality(model, min_train=settings.APRIORI_MIN_TRAIN_BASKETS,
                min_eligible=settings.APRIORI_MIN_EVALUATION_BASKETS)
            report["quality_gate"] = quality
            if args.publish and quality["passed"]:
                destination = Path(settings.APRIORI_MODEL_PATH)
                if destination.exists():
                    (folder / "previous_model.json").write_bytes(destination.read_bytes())
                atomic_bytes(destination, model_path.read_bytes())
                report["published"] = True
            elif args.publish:
                report["reason"] = "Không công bố vì chưa qua điều kiện chất lượng."
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report, "report_path": str(folder / "report.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
