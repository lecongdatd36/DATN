"""Explainable best-fit ranking of tables that have already passed availability checks."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.seating.models import DiningTable


@dataclass(frozen=True)
class TableRecommendation:
    table: "DiningTable"
    rank: int
    score: Decimal
    spare_seats: int
    reason: str


def rank_tables(tables, party_size):
    """Maximize seat utilization; break ties by area, table code, then primary key."""
    if isinstance(party_size, bool) or not isinstance(party_size, int) or not 1 <= party_size <= 100:
        raise ValueError("Party size must be an integer between 1 and 100.")
    candidates = sorted(
        (table for table in tables if table.capacity >= party_size),
        key=lambda table: (table.capacity, table.area.name, table.code, table.pk),
    )
    return [
        TableRecommendation(
            table=table,
            rank=index,
            score=(Decimal(100) * party_size / table.capacity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            spare_seats=table.capacity - party_size,
            reason=(f"Đủ {party_size} khách, dư {table.capacity - party_size} chỗ; "
                    "không trùng lịch trong thời gian đã chọn."),
        )
        for index, table in enumerate(candidates, start=1)
    ]
