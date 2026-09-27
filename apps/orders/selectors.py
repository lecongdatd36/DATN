import re
from django.db.models import Q
from .models import Order, OrderItem


def order_list(*, q="", status=""):
    result = Order.objects.select_related("booking__table").prefetch_related("items")
    if q:
        criteria = Q(booking__table__code__icontains=q) | Q(booking__customer_name__icontains=q)
        match = re.fullmatch(r"DH([0-9]{1,18})", q, re.IGNORECASE)
        if match:
            criteria |= Q(pk=int(match.group(1)))
        result = result.filter(criteria)
    if not status:
        result = result.exclude(status__in=(Order.Status.PAID, Order.Status.VOID))
    elif status != "all":
        result = result.filter(status=status)
    return result


def kitchen_items(*, q="", status=""):
    result = OrderItem.objects.select_related("order__booking__table", "dish").filter(order__status=Order.Status.OPEN,
        status__in=(OrderItem.Status.SENT, OrderItem.Status.COOKING, OrderItem.Status.READY)).order_by("sent_at", "pk")
    if q:
        criteria = Q(dish_name__icontains=q) | Q(order__booking__table__code__icontains=q)
        match = re.fullmatch(r"DH([0-9]{1,18})", q, re.IGNORECASE)
        if match:
            criteria |= Q(order_id=int(match.group(1)))
        result = result.filter(criteria)
    if status:
        result = result.filter(status=status)
    return result
