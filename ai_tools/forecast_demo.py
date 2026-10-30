"""Append-only seeded demo series, compatible with the original seed-42 CSV."""
import math
import random
from datetime import date, timedelta
from pathlib import Path

from .forecast_store import atomic_bytes, csv_bytes, read_daily

START = date(2025, 10, 30)
SEED = 42
FIELDS = ["ngay", "so_don", "nguon_du_lieu"]


def extend_demo(path, through):
    """Caller holds the update lock. Preserve old rows, replay RNG before appending."""
    path = Path(path)
    rows = read_daily(path, "mo_phong") if path.exists() else []
    if rows and rows[0]["ngay"] != START.isoformat():
        raise ValueError("Demo start/seed contract differs from original series")
    existing_end = date.fromisoformat(rows[-1]["ngay"]) if rows else START - timedelta(days=1)
    if existing_end >= through:
        return rows
    rng = random.Random(SEED)
    factors = [0.85, 0.80, 0.90, 0.95, 1.15, 1.50, 1.35]
    for i in range((through - START).days + 1):
        day = START + timedelta(days=i)
        noise = rng.gauss(0, 7)
        if day <= existing_end:
            continue
        expected = (40 + 0.025 * i) * factors[day.weekday()] * (1 + 0.10 * math.sin(2 * math.pi * i / 365))
        rows.append({"ngay": day.isoformat(), "so_don": str(max(0, round(expected + noise))),
                     "nguon_du_lieu": "mo_phong"})
    atomic_bytes(path, csv_bytes(rows, FIELDS))
    return rows
