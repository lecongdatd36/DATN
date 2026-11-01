"""Reproducible ranking benchmark; creates no customers, bookings or business data."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apps.bookings.table_ranking import rank_tables


@dataclass(frozen=True)
class Area:
    name: str


@dataclass(frozen=True)
class Candidate:
    pk: int
    code: str
    capacity: int
    area: Area


def evaluate(seed=42, count=200):
    rng = random.Random(seed)
    scenarios = []
    for index in range(count):
        party_size = rng.randint(1, 14)
        tables = [Candidate(pk=table_id, code=f"B{table_id:03}", capacity=rng.choice((2, 4, 6, 8, 10, 12)),
                            area=Area(f"Area {rng.randint(1, 3)}"))
                  for table_id in range(1, rng.randint(2, 15) + 1)]
        eligible = [table for table in tables if table.capacity >= party_size]
        rows = rank_tables(tables, party_size)
        assert bool(rows) == bool(eligible), "Ranking must not invent or hide an eligible table"
        if not eligible:
            scenarios.append({"scenario": index + 1, "party_size": party_size, "eligible_tables": 0})
            continue
        best = rows[0]
        old_best = min(eligible, key=lambda table: (table.capacity, table.area.name, table.code, table.pk))
        assert best.table.pk == old_best.pk, "Ranking must retain the existing capacity-first best fit"
        assert best.spare_seats == min(table.capacity - party_size for table in eligible)
        assert [row.table.pk for row in rows] == [row.table.pk for row in rank_tables(list(reversed(tables)), party_size)]
        scenarios.append({
            "scenario": index + 1, "party_size": party_size, "eligible_tables": len(eligible),
            "selected_code": best.table.code, "selected_capacity": best.table.capacity,
            "score": float(best.score), "spare_seats": best.spare_seats,
            "first_fit_spare_seats": eligible[0].capacity - party_size,
            "existing_best_fit_spare_seats": old_best.capacity - party_size,
        })
    successful = [row for row in scenarios if row["eligible_tables"]]
    size = len(successful)
    return {
        "schema_version": 1, "algorithm": "best_fit_seat_utilization",
        "data_source": "synthetic_candidate_scenarios", "seed": seed,
        "scenario_count": count, "allocated_scenarios": size, "no_capacity_scenarios": count - size,
        "mean_spare_seats": sum(row["spare_seats"] for row in successful) / size if size else None,
        "first_fit_mean_spare_seats": sum(row["first_fit_spare_seats"] for row in successful) / size if size else None,
        "existing_best_fit_mean_spare_seats": sum(row["existing_best_fit_spare_seats"] for row in successful) / size if size else None,
        "minimum_spare_seats_and_deterministic_order": True,
        "limitations": [
            "Synthetic eligible candidates, not observed restaurant outcomes.",
            "Availability, time conflicts, permissions and concurrent writes are evaluated by Django tests separately.",
            "Best fit matches the previous capacity-first allocation; scoring adds an explanation, not a claim of better optimization.",
            "First fit selects the first eligible input candidate; it is a comparison baseline, not the former production algorithm.",
            "Optimizes unused seats for one party; does not optimize future demand or combine tables.",
        ],
        "scenarios": scenarios,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    output = args.output or Path("artifacts/ai/table-recommendations") / (
        "evaluation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("scenarios", "limitations")}, indent=2))
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
