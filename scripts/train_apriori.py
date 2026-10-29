import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_tools.apriori import run_experiment


def main():
    parser = argparse.ArgumentParser(description="Train and evaluate Apriori on a single CSV data source.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-support", type=float, default=0.04)
    parser.add_argument("--min-confidence", type=float, default=0.3)
    parser.add_argument("--min-lift", type=float, default=1.05)
    args = parser.parse_args()
    try:
        model = run_experiment(args.csv, args.output, min_support=args.min_support,
                               min_confidence=args.min_confidence, min_lift=args.min_lift)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"data_source": model["data_source"], "training": model["training"],
                      "evaluation": model["evaluation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
