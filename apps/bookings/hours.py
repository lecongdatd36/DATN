"""Shared reservation limits in the restaurant's local timezone."""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import BookingSettings


def booking_hours_help(settings):
    return (
        f"Giờ phục vụ: {settings.opening_time:%H:%M}–{settings.closing_time:%H:%M}. "
        "Thời gian dùng bàn phải kết thúc chậm nhất vào giờ đóng cửa."
    )


def validate_booking_hours(starts_at, ends_at, *, settings=None):
    settings = settings or BookingSettings.objects.get(pk=1)
    if timezone.is_naive(starts_at) or timezone.is_naive(ends_at):
        raise ValidationError({"starts_at": "Thời gian đặt bàn phải có múi giờ."})
    start, end = timezone.localtime(starts_at), timezone.localtime(ends_at)
    if not settings.opening_time <= start.time() < settings.closing_time:
        raise ValidationError({"starts_at": booking_hours_help(settings)})
    if end <= start or end.date() != start.date() or end.time() > settings.closing_time:
        raise ValidationError({"duration_minutes": booking_hours_help(settings)})
