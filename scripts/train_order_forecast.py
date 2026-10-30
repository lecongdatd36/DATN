"""AI interpreter entry point. Publication is handled only by update_forecast_daily.py."""
import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=("mo_phong", "application_export"), required=True)
    parser.add_argument("--reference-date", type=date.fromisoformat, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    from ai_tools.forecast_training import train
    train(args.input, args.output, args.source, args.reference_date, args.run_id)


if __name__ == "__main__":
    main()
