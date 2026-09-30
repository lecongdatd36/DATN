from django.db.models import Case, CharField, Count, DecimalField, Exists, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from apps.bookings.models import Booking
from apps.orders.models import Order, OrderItem
from .models import Area, DiningTable


def areas(*, q="", status=""):
    result = Area.objects.annotate(table_count=Count("tables")).order_by("name", "pk")
    if q:
        result = result.filter(name__icontains=q)
    if status:
        result = result.filter(is_active=status == "active")
    return result


def table_status_counts(*, at=None):
    """Tính tổng quan bàn bằng một truy vấn gọn, không dựng toàn bộ dữ liệu thẻ bàn."""
    now = at if at is not None else timezone.now()
    seated = Booking.objects.filter(table_id=OuterRef("pk"), status=Booking.Status.SEATED)
    held = Booking.objects.filter(
        table_id=OuterRef("pk"),
        status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED),
        starts_at__lte=now,
        ends_at__gt=now,
    )
    result = DiningTable.objects.annotate(has_seated=Exists(seated), has_held=Exists(held)).aggregate(
        all=Count("pk"),
        occupied=Count("pk", filter=Q(has_seated=True) | Q(status=DiningTable.Status.OCCUPIED)),
        cleaning=Count("pk", filter=Q(status=DiningTable.Status.CLEANING)),
        inactive=Count("pk", filter=Q(has_seated=False) & (Q(is_active=False) | Q(area__is_active=False))),
        reserved=Count("pk", filter=Q(has_seated=False, has_held=True, is_active=True, area__is_active=True)),
    )
    result["empty"] = result["all"] - result["occupied"] - result["inactive"] - result["reserved"] - result["cleaning"]
    return result


def tables(*, q="", status="", area=None, at=None):
    now = at if at is not None else timezone.now()
    seated = Booking.objects.filter(table_id=OuterRef("pk"), status=Booking.Status.SEATED).order_by("starts_at", "pk")
    waiting = Booking.objects.filter(table_id=OuterRef("pk"), status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED))
    held = waiting.filter(starts_at__lte=now, ends_at__gt=now).order_by("starts_at", "pk")
    upcoming = waiting.filter(starts_at__gt=now).order_by("starts_at", "pk")
    current_order = Order.objects.filter(table_id=OuterRef("pk")).exclude(status__in=(Order.Status.COMPLETED, Order.Status.CANCELLED)).order_by("-pk")
    line_total = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=0))
    order_items = (
        OrderItem.objects.filter(
            order__table_id=OuterRef("pk"),
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .values("order__table_id")
    )
    order_total = order_items.annotate(value=Sum(line_total)).values("value")[:1]
    order_quantity = order_items.annotate(value=Sum("quantity")).values("value")[:1]
    result = DiningTable.objects.select_related("area").annotate(
        current_visit_id=Subquery(seated.values("pk")[:1]),
        current_visit_revision=Subquery(seated.values("revision")[:1]),
        current_visit_customer=Subquery(seated.values("customer_name")[:1]),
        current_visit_party_size=Subquery(seated.values("party_size")[:1]),
        current_visit_seated_at=Subquery(seated.values("seated_at")[:1]),
        current_visit_end=Subquery(seated.values("ends_at")[:1]),
        held_booking_id=Subquery(held.values("pk")[:1]),
        held_booking_status=Subquery(held.values("status")[:1]),
        held_booking_revision=Subquery(held.values("revision")[:1]),
        next_booking_id=Subquery(upcoming.values("pk")[:1]),
        next_booking_start=Subquery(upcoming.values("starts_at")[:1]),
        current_order_id=Subquery(current_order.values("pk")[:1]),
        current_order_status=Subquery(current_order.values("status")[:1]),
        current_order_total=Coalesce(Subquery(order_total), Value(0), output_field=DecimalField(max_digits=14, decimal_places=0)),
        current_order_quantity=Coalesce(Subquery(order_quantity), Value(0), output_field=IntegerField()),
    ).annotate(current_status=Case(
        # An actual seated party remains visible even after its planned end.
        When(Q(current_visit_id__isnull=False) | Q(status=DiningTable.Status.OCCUPIED), then=Value("occupied")),
        When(Q(is_active=False) | Q(area__is_active=False), then=Value("inactive")),
        When(status=DiningTable.Status.CLEANING, then=Value("cleaning")),
        When(Q(held_booking_id__isnull=False) | Q(status=DiningTable.Status.RESERVED), then=Value("reserved")),
        default=Value("empty"), output_field=CharField(),
    ))
    if q:
        result = result.filter(Q(code__icontains=q) | Q(area__name__icontains=q))
    if area:
        result = result.filter(area=area)
    if status == "active":
        result = result.filter(is_active=True, area__is_active=True)
    elif status == "inactive":
        result = result.filter(Q(is_active=False) | Q(area__is_active=False))
    elif status in ("occupied", "reserved", "cleaning", "empty"):
        result = result.filter(current_status=status)
    return result
