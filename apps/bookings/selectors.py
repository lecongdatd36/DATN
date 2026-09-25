import re
from django.core.exceptions import ValidationError
from django.db.models import Case, DateTimeField, F, Q, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from apps.seating.models import DiningTable
from apps.customers.validators import normalize_phone
from .models import Booking, BookingSettings


BLOCKING_STATUSES = (Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.SEATED)


def default_duration_minutes():
    return BookingSettings.objects.get(pk=1).default_duration_minutes


def next_booking(booking):
    return Booking.objects.filter(
        table_id=booking.table_id, status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED),
        ends_at__gt=timezone.now(), starts_at__gte=booking.ends_at,
    ).exclude(pk=booking.pk).order_by("starts_at", "pk").first()


def overdue_bookings():
    return Booking.objects.select_related("table").filter(status=Booking.Status.SEATED, ends_at__lte=timezone.now()).order_by("ends_at", "pk")


def overlapping_bookings(*, starts_at, ends_at, table_id=None, exclude_id=None):
    result = Booking.objects.annotate(effective_start=Case(
        When(status=Booking.Status.SEATED, then=Coalesce("seated_at", "starts_at")),
        default=F("starts_at"), output_field=DateTimeField(),
    )).filter(status__in=BLOCKING_STATUSES, effective_start__lt=ends_at, ends_at__gt=starts_at)
    if table_id is not None:
        result = result.filter(table_id=table_id)
    if exclude_id is not None:
        result = result.exclude(pk=exclude_id)
    return result


def protected_bookings():
    # A seated party still occupies its table even if its planned end has passed.
    return Booking.objects.filter(Q(status=Booking.Status.SEATED) | Q(status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED), ends_at__gt=timezone.now()))


def available_tables(*, starts_at, ends_at, party_size):
    busy = overlapping_bookings(starts_at=starts_at, ends_at=ends_at).values("table_id")
    result = DiningTable.objects.select_related("area").filter(is_active=True, area__is_active=True, capacity__gte=party_size).exclude(pk__in=busy)
    if starts_at <= timezone.now():
        result = result.exclude(bookings__status=Booking.Status.SEATED)
    return result


def booking_list(*, q="", date=None, status="", table=None):
    result = Booking.objects.select_related("table", "table__area")
    if q:
        criteria = Q(customer_name__icontains=q) | Q(customer_phone__icontains=q) | Q(table__code__icontains=q)
        try:
            criteria |= Q(customer_phone=normalize_phone(q))
        except ValidationError:
            pass
        match = re.fullmatch(r"(?:DB|LK)([0-9]{1,18})", q, re.IGNORECASE)
        if match:
            criteria |= Q(pk=int(match.group(1)))
        result = result.filter(criteria)
    if date:
        result = result.filter(starts_at__date=date)
    if status:
        result = result.filter(status=status)
    if table:
        result = result.filter(table=table)
    return result
