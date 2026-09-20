from datetime import timedelta
from django.core.exceptions import ValidationError

DEFAULT_DURATION_MINUTES = 120
MAX_DURATION_MINUTES = 1440


def planned_end(starts_at, duration_minutes):
    if type(duration_minutes) is not int or not 1 <= duration_minutes <= MAX_DURATION_MINUTES:
        raise ValidationError({"duration_minutes": "Thời lượng phải là số phút nguyên từ 1 đến 1440."})
    try:
        return starts_at + timedelta(minutes=duration_minutes)
    except (OverflowError, TypeError) as error:
        raise ValidationError({"starts_at": "Giờ đến không hợp lệ."}) from error
