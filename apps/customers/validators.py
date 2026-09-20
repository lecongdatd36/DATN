import re

from django.core.exceptions import ValidationError


def normalize_phone(value):
    if not isinstance(value, str):
        raise ValidationError("Số điện thoại không hợp lệ.")
    phone = re.sub(r"[\s().-]", "", value)
    if phone.startswith("+84"):
        phone = "0" + phone[3:]
    if not re.fullmatch(r"0[0-9]{9,10}", phone):
        raise ValidationError("Nhập số điện thoại Việt Nam gồm 10–11 chữ số, bắt đầu bằng 0 hoặc dùng mã +84.")
    return phone


def validate_phone(value):
    normalize_phone(value)
