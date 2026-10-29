"""Read paid visits for basket analysis without exporting customer identities."""

from django.db.models import F, Max, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ai_tools.schema import SCHEMA_VERSION
from .models import Invoice, Order, OrderItem


def transaction_rows(*, start_at=None, end_at=None):
    # Every non-cancelled check in a split group must be fully settled.
    unfinished = (
        Order.objects.exclude(status=Order.Status.CANCELLED)
        .annotate(basket_root=Coalesce("split_root_id", "pk"))
        .exclude(status=Order.Status.COMPLETED, invoice__status=Invoice.Status.PAID,
                 invoice__closed_at__isnull=False)
        .order_by().values("basket_root")
    )
    settled = (
        Order.objects.filter(status=Order.Status.COMPLETED, invoice__status=Invoice.Status.PAID,
                             invoice__closed_at__isnull=False)
        .annotate(basket_root=Coalesce("split_root_id", "pk"))
        .exclude(basket_root__in=Subquery(unfinished))
    )
    baskets = settled.order_by().values("basket_root").annotate(basket_closed_at=Max("invoice__closed_at"))
    if start_at is not None:
        baskets = baskets.filter(basket_closed_at__gte=start_at)
    if end_at is not None:
        baskets = baskets.filter(basket_closed_at__lt=end_at)
    closed_at = dict(baskets.values_list("basket_root", "basket_closed_at"))
    if not closed_at:
        return
    items = (
        OrderItem.objects.filter(status=OrderItem.Status.SERVED, order_id__in=Subquery(settled.values("pk")))
        .annotate(basket_root=Coalesce("order__split_root_id", "order_id"))
        .filter(basket_root__in=closed_at)
        .values("basket_root", "dish_id", dish_code_export=F("dish__code"), dish_name_export=F("dish__name"))
        .annotate(quantity_sum=Sum("quantity"))
        .order_by("basket_root", "dish_id")
    )
    for item in items.iterator(chunk_size=2000):
        root = item["basket_root"]
        yield {
            "schema_version": SCHEMA_VERSION, "data_source": "application_export",
            "basket_id": f"VISIT-{root}",
            "basket_closed_at": timezone.localtime(closed_at[root]).isoformat(),
            "dish_id": str(item["dish_id"]), "dish_code": item["dish_code_export"],
            "dish_name": item["dish_name_export"], "quantity": item["quantity_sum"],
        }
