from django.core.exceptions import ValidationError


def validate_avatar(value):
    if value and not getattr(value, "_committed", False) and value.size > 5 * 1024 * 1024:
        raise ValidationError("Ảnh đại diện không được vượt quá 5 MB.")
