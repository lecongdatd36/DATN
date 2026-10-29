"""Reproducible fictional baskets; never connects to Django or its database."""

import csv
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import random

from ai_tools.schema import SCHEMA_VERSION, TRANSACTION_FIELDS


DEMO_DISHES = (
    ("DEMO01", "Cơm gà"), ("DEMO02", "Canh rau"), ("DEMO03", "Trà đá"),
    ("DEMO04", "Bún bò"), ("DEMO05", "Nem rán"), ("DEMO06", "Nước cam"),
    ("DEMO07", "Cá kho"), ("DEMO08", "Cơm trắng"), ("DEMO09", "Rau xào"),
    ("DEMO10", "Lẩu nấm"), ("DEMO11", "Mì"), ("DEMO12", "Chè"),
)


def demo_rows(*, baskets=2000, days=180, seed=42, start=date(2026, 1, 1)):
    if baskets < 2 or days < 2:
        raise ValueError("Cần ít nhất 2 giỏ món và 2 ngày để chia tập theo thời gian.")
    rng = random.Random(seed)
    names = dict(DEMO_DISHES)
    bundles = [codes for codes in (
        ("DEMO01", "DEMO02", "DEMO03"), ("DEMO04", "DEMO05", "DEMO06"),
        ("DEMO07", "DEMO08", "DEMO09"), ("DEMO10", "DEMO11", "DEMO03"),
    )]
    for index in range(baskets):
        day = start + timedelta(days=index * days // baskets)
        closed_at = datetime.combine(day, time(rng.choice((11, 12, 18, 19, 20)), rng.randrange(60)),
                                     tzinfo=timezone(timedelta(hours=7)))
        # These associations are deliberately planted for a reproducible demo.
        bundle = rng.choice(bundles)
        chosen = {bundle[0]}
        chosen.update(code for code in bundle[1:] if rng.random() < 0.8)
        if rng.random() < 0.3:
            chosen.add(rng.choice(DEMO_DISHES)[0])
        if rng.random() < 0.2:
            chosen.add("DEMO12")
        for code in sorted(chosen):
            yield {
                "schema_version": SCHEMA_VERSION, "data_source": "synthetic_demo",
                "basket_id": f"DEMO-{index + 1:06d}", "basket_closed_at": closed_at.isoformat(),
                "dish_id": code, "dish_code": code, "dish_name": names[code],
                "quantity": rng.choice((1, 1, 1, 2, 3)),
            }


def write_demo_csv(path, **options):
    rows = iter(demo_rows(**options))
    first = next(rows)  # Validate options before creating any file.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRANSACTION_FIELDS)
        writer.writeheader()
        writer.writerow(first)
        writer.writerows(rows)
    return path
