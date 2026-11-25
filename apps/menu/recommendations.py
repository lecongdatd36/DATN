"""Resolve trained item codes against the live orderable menu."""

from functools import lru_cache
import logging
from pathlib import Path
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import Coalesce
from django.utils import timezone

from ai_tools.inference import InvalidAprioriModel, load_model, recommend
from ai_tools.quality import assess_model_quality
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
        return popular_recommendations(selected_ids) if settings.APRIORI_QUALITY_GATE_ENABLED else []
    if settings.APRIORI_QUALITY_GATE_ENABLED and not assess_model_quality(model,
            min_train=settings.APRIORI_MIN_TRAIN_BASKETS, min_eligible=settings.APRIORI_MIN_EVALUATION_BASKETS)["passed"]:
        return popular_recommendations(selected_ids)
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


def popular_recommendations(selected_ids):
    """Conservative baseline from settled, unrefunded receipts; filter current menu first."""
    from apps.orders.models import OrderItem
    ranking = (OrderItem.objects.filter(status="SERVED", order__invoice__status="PAID", order__invoice__refunded_amount=0,
        order__invoice__closed_at__gte=timezone.now()-timedelta(days=90), dish__status=Dish.Status.AVAILABLE,
        dish__category__is_active=True, dish__unit__is_active=True)
        .exclude(dish_id__in=selected_ids).annotate(visit=Coalesce("order__split_root_id", "order_id"))
        .values("dish_id", "dish__name", "dish__price").annotate(visits=Count("visit", distinct=True))
        .order_by("-visits", "dish_id")[:3])
    return [{"id": row["dish_id"], "name": row["dish__name"], "price": str(row["dish__price"])} for row in ranking]
