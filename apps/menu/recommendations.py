"""Resolve trained item codes against the live orderable menu."""

from functools import lru_cache
import logging
from pathlib import Path

from django.conf import settings

from ai_tools.inference import InvalidAprioriModel, load_model, recommend
from .models import Dish

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _cached_model(path, modified_ns, size):
    return load_model(path)


def dish_recommendations(selected_ids):
    if not selected_ids:
        return []
    try:
        path = Path(settings.APRIORI_MODEL_PATH)
        stat = path.stat()
        model = _cached_model(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    except (OSError, InvalidAprioriModel) as error:
        logger.warning("Apriori model unavailable: %s", error)
        return []
    if model["data_source"] != "application_export":
        return []
    trained_by_code = {item["dish_code"]: item["dish_id"] for item in model["catalog"]}
    # Codes are stable between exported data and deployment DBs; PKs may differ.
    selected_codes = Dish.objects.filter(pk__in=selected_ids).values_list("code", flat=True)
    cart = [trained_by_code[code] for code in selected_codes if code in trained_by_code]
    if not cart:
        return []
    dishes = Dish.objects.filter(code__in=trained_by_code, status=Dish.Status.AVAILABLE,
                                 category__is_active=True, unit__is_active=True)
    live_by_item = {trained_by_code[dish.code]: dish for dish in dishes}
    suggestions = recommend(cart, model["rules"], k=3, allowed_items=live_by_item)
    return [{"id": live_by_item[item].pk, "name": live_by_item[item].name,
             "price": str(live_by_item[item].price)} for item in suggestions]
