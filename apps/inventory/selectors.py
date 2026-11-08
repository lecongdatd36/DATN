from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum
from django.utils import timezone

from .models import InventoryTransaction


def daily_ingredient_usage(*, day=None):
    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    types = InventoryTransaction.Type
    transactions = InventoryTransaction.objects.filter(
        created_at__gte=start, created_at__lt=end,
        transaction_type__in=(types.SALE_USAGE, types.EXPORT, types.SALE_RETURN, types.WASTE),
    )
    quantity_field = DecimalField(max_digits=20, decimal_places=3)
    rows = list(transactions.order_by().values(
        "ingredient_id", "ingredient__code", "ingredient__name", "ingredient__unit",
    ).annotate(
        sale_quantity=Sum("quantity", filter=Q(transaction_type=types.SALE_USAGE), default=0, output_field=quantity_field),
        export_quantity=Sum("quantity", filter=Q(transaction_type=types.EXPORT), default=0, output_field=quantity_field),
        return_quantity=Sum("quantity", filter=Q(transaction_type=types.SALE_RETURN), default=0, output_field=quantity_field),
        waste_quantity=Sum("quantity", filter=Q(transaction_type=types.WASTE), default=0, output_field=quantity_field),
        transaction_count=Count("pk"),
    ).order_by("ingredient__name", "ingredient_id"))
    for row in rows:
        row["used_quantity"] = row["sale_quantity"] + row["export_quantity"] - row["return_quantity"]
    return {
        "usage_day": day,
        "usage_rows": rows,
        "used_ingredient_count": sum(row["sale_quantity"] + row["export_quantity"] > Decimal(0) for row in rows),
        "usage_transaction_count": sum(row["transaction_count"] for row in rows),
        "usage_transactions": transactions.select_related("ingredient", "performed_by"),
    }
