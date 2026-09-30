import hashlib
import hmac
from urllib.parse import quote_plus, urlencode

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _configuration():
    if not settings.VNPAY_TMN_CODE or not settings.VNPAY_HASH_SECRET:
        raise ImproperlyConfigured(
            "Chưa cấu hình VNPAY_TMN_CODE và VNPAY_HASH_SECRET trong file .env."
        )
    return settings.VNPAY_TMN_CODE, settings.VNPAY_HASH_SECRET


def _signed_data(params):
    filtered = {
        key: str(value)
        for key, value in params.items()
        if key.startswith("vnp_") and key not in {"vnp_SecureHash", "vnp_SecureHashType"} and value not in (None, "")
    }
    return urlencode(sorted(filtered.items()), quote_via=quote_plus)


def sign(params):
    _, secret = _configuration()
    return hmac.new(secret.encode("utf-8"), _signed_data(params).encode("utf-8"), hashlib.sha512).hexdigest()


def verify(params):
    supplied_hash = str(params.get("vnp_SecureHash", ""))
    if not supplied_hash:
        return False
    try:
        expected_hash = sign(params)
    except ImproperlyConfigured:
        return False
    return hmac.compare_digest(supplied_hash.lower(), expected_hash.lower())


def payment_url(params):
    tmn_code, _ = _configuration()
    payload = {**params, "vnp_TmnCode": tmn_code}
    payload["vnp_SecureHash"] = sign(payload)
    return f"{settings.VNPAY_PAYMENT_URL}?{urlencode(sorted(payload.items()), quote_via=quote_plus)}"
