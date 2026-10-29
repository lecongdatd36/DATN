"""Write synthetic CSV only; never populate the restaurant database."""

import argparse
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_tools.demo import write_demo_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ai/demo_transactions.csv"))
    parser.add_argument("--baskets", type=int, default=2000)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    args = parser.parse_args()
    try:
        path = write_demo_csv(args.output, baskets=args.baskets, days=args.days, seed=args.seed, start=args.start)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"SYNTHETIC DEMO: {args.baskets} baskets -> {path}")


if __name__ == "__main__":
    main()
