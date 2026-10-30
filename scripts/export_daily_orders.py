"""Read-only application export. Explicit observation start, complete days only."""
import argparse
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_tools.forecast_demo import FIELDS
from ai_tools.forecast_store import VIETNAM, csv_bytes, vietnam_today


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True,
                        help="First confirmed day of application observation, including zero-order days")
    parser.add_argument("--reference-date", type=date.fromisoformat, default=vietnam_today())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.start_date >= args.reference_date:
        parser.error("start-date must precede reference-date")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
    import django
    django.setup()
    from apps.orders.models import Order
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    start = datetime.combine(args.start_date, time.min, tzinfo=VIETNAM)
    cutoff = datetime.combine(args.reference_date, time.min, tzinfo=VIETNAM)
    totals = dict(Order.objects.filter(
        status="COMPLETED", split_root__isnull=True,
        opened_at__gte=start, opened_at__lt=cutoff,
        closed_at__isnull=False, closed_at__lt=cutoff,
    ).annotate(day=TruncDate("opened_at", tzinfo=VIETNAM))
      .values("day").annotate(total=Count("id")).values_list("day", "total"))
    rows = []
    for i in range((args.reference_date - args.start_date).days):
        day = args.start_date + timedelta(days=i)
        rows.append({"ngay": day.isoformat(), "so_don": totals.get(day, 0),
                     "nguon_du_lieu": "application_export"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(csv_bytes(rows, FIELDS))
    print("APPLICATION EXPORT:", args.output.resolve(), "DAYS:", len(rows))
    print("Observation interval is operator-confirmed; no synthetic fallback.")


if __name__ == "__main__":
    main()
