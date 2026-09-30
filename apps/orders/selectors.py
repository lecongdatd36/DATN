import re
from decimal import Decimal
from django.db.models import Q
from apps.seating.models import Area
from .models import Invoice, Order, OrderItem


def order_list(*, q="", status=""):
    result = Order.objects.select_related("booking__table", "table", "customer", "employee").prefetch_related("items")
    if q:
        criteria = Q(booking__table__code__icontains=q) | Q(booking__customer_name__icontains=q) | Q(table__code__icontains=q) | Q(customer__full_name__icontains=q)
        match = re.fullmatch(r"DH([0-9]{1,18})", q, re.IGNORECASE)
        if match:
            criteria |= Q(pk=int(match.group(1)))
        result = result.filter(criteria)
    if not status:
        result = result.exclude(status__in=(Order.Status.COMPLETED, Order.Status.CANCELLED))
    elif status != "all":
        result = result.filter(status=status)
    return result


def kitchen_items(*, q="", status=""):
    result = OrderItem.objects.select_related("order__booking__table", "order__table", "dish").filter(order__status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
        status__in=(OrderItem.Status.PENDING, OrderItem.Status.COOKING, OrderItem.Status.READY)).order_by("sent_at", "pk")
    if q:
        criteria = Q(dish_name__icontains=q) | Q(order__booking__table__code__icontains=q) | Q(order__table__code__icontains=q)
        match = re.fullmatch(r"DH([0-9]{1,18})", q, re.IGNORECASE)
        if match:
            criteria |= Q(order_id=int(match.group(1)))
        result = result.filter(criteria)
    if status:
        result = result.filter(status=status)
    return result


def payable_table_orders(*, area_id=None):
    queryset = (
        Order.objects.filter(
            booking__status="SEATED",
            status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS, Order.Status.PAYMENT_REQUESTED),
        )
        .select_related("booking__table__area", "invoice")
        .prefetch_related("items")
        .order_by("booking__table__area__name", "booking__table__code", "pk")
    )
    if area_id:
        queryset = queryset.filter(booking__table__area_id=area_id)

    ready = []
    for order in queryset:
        items = [item for item in order.items.all() if item.status != OrderItem.Status.CANCELLED]
        if not items or any(item.status != OrderItem.Status.SERVED for item in items):
            continue
        invoice = getattr(order, "invoice", None)
        if invoice and invoice.status != Invoice.Status.UNPAID:
            continue
        remaining = invoice.remaining if invoice else order.total
        if remaining <= Decimal("0"):
            continue
        order.payable_amount = remaining
        ready.append(order)
    return ready


def payment_areas():
    return Area.objects.filter(is_active=True).order_by("name", "pk")
