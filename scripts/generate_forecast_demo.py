"""Extend demo CSV only. Use update_forecast_daily.py for the full pipeline."""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_tools.forecast_demo import extend_demo
from ai_tools.forecast_store import UpdateLock, vietnam_today


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/ai/forecast")
    parser.add_argument("--through", type=date.fromisoformat, default=vietnam_today() - timedelta(days=1))
    args = parser.parse_args()
    with UpdateLock(args.root):
        rows = extend_demo(args.root / "daily_orders_demo_v1.csv", args.through)
    print("Demo rows:", len(rows), "last day:", rows[-1]["ngay"])


if __name__ == "__main__":
    main()
