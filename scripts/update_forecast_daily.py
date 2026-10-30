"""Single manual/scheduled forecast update entry point."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_tools.forecast_store import UpdateAlreadyRunning
from ai_tools.forecast_update import update_forecast


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("mo_phong", "application_export"), default="mo_phong")
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/ai/forecast")
    parser.add_argument("--input", type=Path, help="Application CSV only; never mixed with demo")
    parser.add_argument("--ai-python", type=Path)
    parser.add_argument("--force", action="store_true", help="Retrain even if today's publication exists")
    parser.add_argument("--reference-date", type=date.fromisoformat, help="Tests only: requires a separate --root")
    args = parser.parse_args()
    if args.reference_date and args.root.resolve() == (ROOT / "artifacts/ai/forecast").resolve():
        parser.error("--reference-date requires an isolated --root; do not replace the live forecast with test dates")
    logs = args.root.resolve() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers = [RotatingFileHandler(logs / "update.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
                logging.StreamHandler()]
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers)
    try:
        update_forecast(ROOT, args.root, args.source, args.reference_date,
                        args.input, args.ai_python, args.force)
    except UpdateAlreadyRunning:
        logging.info("Skipped: another manual/scheduled update is running")
        return 0
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
