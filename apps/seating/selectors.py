from django.db.models import Case, CharField, Count, OuterRef, Q, Subquery, Value, When
from django.utils import timezone
from apps.bookings.models import Booking
from .models import Area, DiningTable


def areas(*, q="", status=""):
    result = Area.objects.annotate(table_count=Count("tables")).order_by("name", "pk")
    if q:
        result = result.filter(name__icontains=q)
    if status:
        result = result.filter(is_active=status == "active")
    return result


def tables(*, q="", status="", area=None, at=None):
    now = at if at is not None else timezone.now()
    seated = Booking.objects.filter(table_id=OuterRef("pk"), status=Booking.Status.SEATED).order_by("starts_at", "pk")
    waiting = Booking.objects.filter(table_id=OuterRef("pk"), status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED))
    held = waiting.filter(starts_at__lte=now, ends_at__gt=now).order_by("starts_at", "pk")
    upcoming = waiting.filter(starts_at__gt=now).order_by("starts_at", "pk")
    result = DiningTable.objects.select_related("area").annotate(
        current_visit_id=Subquery(seated.values("pk")[:1]),
        current_visit_end=Subquery(seated.values("ends_at")[:1]),
        held_booking_id=Subquery(held.values("pk")[:1]),
        next_booking_id=Subquery(upcoming.values("pk")[:1]),
        next_booking_start=Subquery(upcoming.values("starts_at")[:1]),
    ).annotate(current_status=Case(
        # An actual seated party remains visible even after its planned end.
        When(current_visit_id__isnull=False, then=Value("occupied")),
        When(Q(is_active=False) | Q(area__is_active=False), then=Value("inactive")),
        When(held_booking_id__isnull=False, then=Value("reserved")),
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
    elif status in ("occupied", "reserved", "empty"):
        result = result.filter(current_status=status)
    return result
