from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.bookings.models import Booking
from apps.customers.models import Customer
from apps.orders.models import Invoice, OrderItem, Payment
from apps.inventory.models import PurchaseReceipt, PurchaseReceiptLine, WasteRecord


MONEY_FIELD = DecimalField(max_digits=14, decimal_places=0)


def _money_sum(field_name):
    return Coalesce(Sum(field_name), Decimal("0"), output_field=MONEY_FIELD)


def report_data(start_at, end_at):
    paid_invoices = Invoice.objects.filter(
        status=Invoice.Status.PAID,
        closed_at__gte=start_at,
        closed_at__lt=end_at,
    )
    invoice_summary = paid_invoices.aggregate(
        revenue=_money_sum("total"),
        invoice_count=Count("pk"),
        average_bill=Coalesce(Avg("total"), Decimal("0"), output_field=MONEY_FIELD),
    )
    cost_of_goods = (
        OrderItem.objects.filter(
            order__invoice__status=Invoice.Status.PAID,
            order__invoice__closed_at__gte=start_at,
            order__invoice__closed_at__lt=end_at,
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .aggregate(total=_money_sum("total_cost"))["total"]
    )
    gross_profit = invoice_summary["revenue"] - cost_of_goods
    gross_margin = gross_profit / invoice_summary["revenue"] * 100 if invoice_summary["revenue"] else Decimal("0")
    purchase_cost = PurchaseReceiptLine.objects.filter(
        receipt__status=PurchaseReceipt.Status.RECEIVED,
        receipt__received_at__gte=start_at,
        receipt__received_at__lt=end_at,
    ).aggregate(
        total=Coalesce(
            Sum(ExpressionWrapper(F("quantity") * F("unit_cost"), output_field=MONEY_FIELD)),
            Decimal("0"), output_field=MONEY_FIELD,
        )
    )["total"]
    waste_cost = WasteRecord.objects.filter(created_at__gte=start_at, created_at__lt=end_at).aggregate(
        total=_money_sum("total_cost")
    )["total"]

    payments = Payment.objects.filter(created_at__gte=start_at, created_at__lt=end_at)
    collected = payments.aggregate(total=_money_sum("amount"))["total"]

    remaining_expression = ExpressionWrapper(F("total") - F("paid_amount"), output_field=MONEY_FIELD)
    outstanding = Invoice.objects.filter(status=Invoice.Status.UNPAID).aggregate(
        total=Coalesce(Sum(remaining_expression), Decimal("0"), output_field=MONEY_FIELD),
        count=Count("pk"),
    )

    bookings = Booking.objects.filter(starts_at__gte=start_at, starts_at__lt=end_at)
    booking_summary = bookings.aggregate(
        total=Count("pk"),
        guests=Coalesce(Sum("party_size"), 0),
        served=Count("pk", filter=Q(status__in=[Booking.Status.SEATED, Booking.Status.COMPLETED])),
        completed=Count("pk", filter=Q(status=Booking.Status.COMPLETED)),
        cancelled=Count("pk", filter=Q(status__in=[Booking.Status.CANCELLED, Booking.Status.NO_SHOW])),
        walk_ins=Count("pk", filter=Q(is_walk_in=True)),
    )

    current_tz = timezone.get_current_timezone()
    revenue_by_day = list(
        paid_invoices.annotate(day=TruncDate("closed_at", tzinfo=current_tz))
        .values("day")
        .annotate(total=_money_sum("total"), invoice_count=Count("pk"))
        .order_by("day")
    )
    max_daily_revenue = max((row["total"] for row in revenue_by_day), default=Decimal("0"))
    for row in revenue_by_day:
        row["percent"] = float(row["total"] / max_daily_revenue * 100) if max_daily_revenue else 0

    method_labels = dict(Payment.Method.choices)
    payment_methods = list(
        payments.values("method")
        .annotate(total=_money_sum("amount"), payment_count=Count("pk"))
        .order_by("-total", "method")
    )
    for row in payment_methods:
        row["label"] = method_labels.get(row["method"], row["method"])
        row["percent"] = float(row["total"] / collected * 100) if collected else 0

    item_revenue = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=MONEY_FIELD)
    top_dishes = list(
        OrderItem.objects.filter(
            order__invoice__status=Invoice.Status.PAID,
            order__invoice__closed_at__gte=start_at,
            order__invoice__closed_at__lt=end_at,
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .annotate(line_revenue=item_revenue)
        .values("dish_code", "dish_name", "unit_name")
        .annotate(
            sold_quantity=Sum("quantity"),
            revenue=Sum("line_revenue"),
            cost=Sum("total_cost"),
            order_count=Count("order_id", distinct=True),
        )
        .order_by("-sold_quantity", "-revenue", "dish_name")[:10]
    )
    for row in top_dishes:
        row["profit"] = row["revenue"] - (row["cost"] or Decimal("0"))

    top_tables = list(
        paid_invoices.values("order__table__code", "order__table__area__name")
        .annotate(revenue=_money_sum("total"), invoice_count=Count("pk"))
        .order_by("-revenue", "order__table__code")[:10]
    )

    recent_invoices = paid_invoices.select_related(
        "order__table__area", "order__booking__table__area",
    ).prefetch_related(Prefetch("payments", queryset=Payment.objects.select_related("batch"))).order_by("-closed_at", "-pk")[:10]

    return {
        **invoice_summary,
        "cost_of_goods": cost_of_goods,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "purchase_cost": purchase_cost,
        "waste_cost": waste_cost,
        "collected": collected,
        "outstanding": outstanding,
        "booking_summary": booking_summary,
        "new_customers": Customer.objects.filter(created_at__gte=start_at, created_at__lt=end_at).count(),
        "revenue_by_day": revenue_by_day,
        "payment_methods": payment_methods,
        "top_dishes": top_dishes,
        "top_tables": top_tables,
        "recent_invoices": recent_invoices,
    }


def paid_invoices_for_export(start_at, end_at):
    return (
        Invoice.objects.filter(
            status=Invoice.Status.PAID,
            closed_at__gte=start_at,
            closed_at__lt=end_at,
        )
        .select_related("customer", "order__table__area", "order__booking__table__area")
        .prefetch_related(Prefetch("payments", queryset=Payment.objects.select_related("batch")), "order__items")
        .order_by("closed_at", "pk")
    )
