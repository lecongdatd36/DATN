"""Read a validated published snapshot. Never train or write from a request."""
import json
import logging
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from ai_tools.forecast_store import read_published, source_directory, vietnam_today

logger = logging.getLogger(__name__)


def get_order_forecast(reference_date=None):
    today = reference_date or vietnam_today()
    source = settings.ORDER_FORECAST_SOURCE
    root = Path(settings.ORDER_FORECAST_ROOT)
    result = {"ready": False, "is_demo": source == "mo_phong", "data_source": source}
    try:
        manifest, metadata, forecast_rows = read_published(root, source)
        rows = [{"day": date.fromisoformat(row["ngay"]), "orders": int(row["so_don_du_kien"])}
                for row in forecast_rows]
        published_at = datetime.fromisoformat(manifest["published_at"])
        if published_at.tzinfo is None:
            raise ValueError("Publication time must include timezone")
        result.update({
            "ready": True, "rows": rows, "run_id": manifest["run_id"],
            "trained_until": date.fromisoformat(metadata["training_last_date"]),
            "date_from": rows[0]["day"], "date_to": rows[-1]["day"],
            "mae": metadata["mae_ai"], "baseline_mae": metadata["mae_baseline"],
            "has_past_dates": rows[0]["day"] < today,
            "is_stale": rows[0]["day"] != today,
            "published_at": published_at,
        })
        try:
            failure = json.loads((source_directory(root, source) / "last_failure.json").read_text(encoding="utf-8"))
            failed_at = datetime.fromisoformat(failure["failed_at"])
            result["last_update_failed"] = failed_at > published_at
        except (OSError, ValueError, KeyError, TypeError):
            result["last_update_failed"] = False
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        logger.exception("Khong doc duoc bo du bao da cong bo; source=%s", source)
        result["ready"] = False
    return result
