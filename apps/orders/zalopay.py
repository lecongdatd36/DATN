"""Official ZaloPay v2 protocol, restricted to Sandbox even if env is misconfigured.

https://developer.zalopay.vn/v2/general/overview.html
No example merchant credentials are included in this module.
"""
import hashlib
import hmac
import json
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils import timezone

MIN_EXPIRE_SECONDS = 300


class GatewayUnavailable(Exception):
    pass


def configuration():
    try:
        endpoint = urlparse(settings.ZALOPAY_ENDPOINT)
    except ValueError:
        raise ImproperlyConfigured("Endpoint ZaloPay Sandbox không hợp lệ.") from None
    if (endpoint.scheme != "https" or endpoint.netloc != "sb-openapi.zalopay.vn" or
            endpoint.path.rstrip("/") not in ("/v2", "/v2/create") or endpoint.query or endpoint.fragment):
        raise ImproperlyConfigured("ZaloPay chỉ cho phép endpoint Sandbox v2 chính thức.")
    try:
        app_id = int(settings.ZALOPAY_APP_ID)
    except (TypeError, ValueError):
        app_id = 0
    if app_id <= 0 or not settings.ZALOPAY_KEY1 or not settings.ZALOPAY_KEY2:
        raise ImproperlyConfigured("ZaloPay Sandbox chưa được cấu hình thông tin kết nối.")
    return app_id, settings.ZALOPAY_KEY1, settings.ZALOPAY_KEY2


def enabled():
    try:
        configuration()
        return True
    except ImproperlyConfigured:
        return False


def digest(key, value):
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def transaction_id():
    # yyMMdd must follow Vietnam's date, regardless of host/Django timezone.
    day = timezone.now().astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%y%m%d")
    return f"{day}_{uuid4().hex}"


def create_mac(payload):
    _, key1, _ = configuration()
    fields = ("app_id", "app_trans_id", "app_user", "amount", "app_time", "embed_data", "item")
    return digest(key1, "|".join(str(payload[field]) for field in fields))


def query_payload(app_trans_id):
    app_id, key1, _ = configuration()
    return {"app_id": app_id, "app_trans_id": app_trans_id,
        "mac": digest(key1, f"{app_id}|{app_trans_id}|{key1}")}


def callback_data(payload):
    _, _, key2 = configuration()
    if not isinstance(payload, dict) or payload.get("type") != 1:
        raise ValidationError("Invalid callback type")
    data, mac = payload.get("data"), payload.get("mac")
    if (not isinstance(data, str) or not isinstance(mac, str) or len(mac) != 64 or
            any(char not in "0123456789abcdefABCDEF" for char in mac) or
            not hmac.compare_digest(digest(key2, data), mac.lower())):
        raise ValidationError("Invalid callback signature")
    try:
        result = json.loads(data)
    except (TypeError, ValueError):
        raise ValidationError("Invalid callback data") from None
    if not isinstance(result, dict):
        raise ValidationError("Invalid callback data")
    return result


def post(operation, payload):
    configuration()
    if operation not in ("create", "query"):
        raise ValueError("Unsupported Sandbox operation")
    # Host is checked above; do not follow a redirect to another host/production.
    endpoint = settings.ZALOPAY_ENDPOINT.rstrip("/")
    base = endpoint[:-len("/create")] if endpoint.endswith("/create") else endpoint
    url = base + "/" + operation
    try:
        response = httpx.post(url, data=payload, timeout=15.0, follow_redirects=False)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (httpx.HTTPError, ValueError):
        # Do not leak signed request bodies or secrets via network exceptions.
        raise GatewayUnavailable("Chưa nhận được kết quả từ ZaloPay Sandbox. Hãy truy vấn lại giao dịch hiện có.") from None


def checkout_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        url = urlparse(value)
    except ValueError:
        return ""
    if url.scheme == "https" and url.netloc == "qcgateway.zalopay.vn":
        return value
    return ""
