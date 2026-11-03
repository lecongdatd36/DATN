"""Restaurant-local reservation hours, shared by forms and write services."""
from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from .duration import planned_end
from .models import BookingSettings


HOUR_FIELDS = ("opening_time", "closing_time", "last_booking_time")


def hours_snapshot(settings):
    return {name: getattr(settings, name).strftime("%H:%M") for name in HOUR_FIELDS}


def closing_at(starts_at, settings):
    if starts_at is None or timezone.is_naive(starts_at):
        raise ValidationError({"starts_at": "Giờ đến phải có múi giờ hợp lệ."})
    local = timezone.localtime(starts_at)
    clock = local.time()
    if not settings.opening_time <= clock <= settings.last_booking_time:
        raise ValidationError({"starts_at": (
            f"Nhà hàng mở cửa lúc {settings.opening_time:%H:%M}, đóng cửa lúc {settings.closing_time:%H:%M}; "
            f"nhận khách đặt bàn đến {settings.last_booking_time:%H:%M}."
        )})
    return timezone.make_aware(datetime.combine(local.date(), settings.closing_time), local.tzinfo)


def reservation_end(starts_at, duration_minutes=None, *, settings=None):
    settings = settings or BookingSettings.objects.get(pk=1)
    close = closing_at(starts_at, settings)
    requested_end = planned_end(starts_at, settings.default_duration_minutes if duration_minutes is None else duration_minutes)
    return min(requested_end, close)


def validate_reservation_period(starts_at, ends_at, *, settings=None):
    settings = settings or BookingSettings.objects.get(pk=1)
    close = closing_at(starts_at, settings)
    if ends_at > close:
        raise ValidationError({"ends_at": f"Giờ kết thúc dự kiến không được quá {settings.closing_time:%H:%M}."})
