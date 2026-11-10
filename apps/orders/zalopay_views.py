import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.reservations.models import Reservation
from . import zalopay, zalopay_services
from .models import Order, ZaloPayTransaction


def _private(response):
    response["Referrer-Policy"] = "same-origin"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def base_url(request):
    # PUBLIC_BASE_URL is also used by printed table QR codes and can contain an
    # obsolete LAN IP. Return this browser to the origin it actually opened.
    return request.build_absolute_uri("/").rstrip("/")


def callback_url(request):
    return settings.ZALOPAY_CALLBACK_URL or request.build_absolute_uri(reverse("zalopay:callback"))


def serialize(row):
    return {"app_trans_id": row.app_trans_id, "amount": str(row.amount), "status": row.status,
        "status_label": row.get_status_display(), "sandbox": True, "message": row.last_error,
        "order_url": row.order_url if row.status == "PENDING" and row.expires_at > timezone.now() else "",
        "result_url": reverse("zalopay:result", args=[row.token]),
        "query_url": reverse("zalopay:query", args=[row.token]),
        "state_url": reverse("zalopay:state", args=[row.token])}


def _input(request):
    if request.content_type == "application/json":
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        return data
    return request.POST


@login_required
@never_cache
@require_POST
def create(request):
    try:
        data = _input(request)
        row = zalopay_services.create_order_payment(actor=request.user, order_id=int(data.get("order_id", "")),
            base_url=base_url(request), callback_url=callback_url(request), promotion_code=data.get("promotion_code") or None,
            quick_payment=data.get("quick_payment") in ("1", 1, True))
    except PermissionDenied:
        return JsonResponse({"error": "Bạn chưa có quyền thu tiền."}, status=403)
    except ImproperlyConfigured:
        return JsonResponse({"error": "ZaloPay Sandbox chưa sẵn sàng."}, status=503)
    except (ValueError, TypeError, ValidationError, Order.DoesNotExist):
        return JsonResponse({"error": "Không thể tạo thanh toán. Kiểm tra đơn hàng và các giao dịch đang chờ."}, status=400)
    return _private(JsonResponse(serialize(row), status=201))


@never_cache
@require_POST
def deposit_create(request, token):
    reservation = get_object_or_404(Reservation, access_token=token)
    try:
        data = _input(request)
        if data.get("agree") != "yes":
            raise ValidationError("Cần đồng ý điều kiện thanh toán trước khi trả cọc.")
        row = zalopay_services.create_deposit_payment(token=token, revision=int(data.get("revision", "0")),
            base_url=base_url(request), callback_url=callback_url(request))
    except ImproperlyConfigured:
        error_message = "ZaloPay Sandbox chưa được cấu hình kết nối. Vui lòng liên hệ nhà hàng."
    except ValidationError as error:
        error_message = " ".join(error.messages)
    except (ValueError, TypeError):
        error_message = "Thông tin thanh toán không hợp lệ. Vui lòng tải lại lịch đặt bàn rồi thử lại."
    else:
        state_data = serialize(row)
        if request.content_type == "application/json" or "application/json" in request.headers.get("Accept", ""):
            return _private(JsonResponse(state_data, status=201))
        return _private(redirect(state_data["order_url"] or state_data["result_url"]))
    if request.content_type == "application/json" or "application/json" in request.headers.get("Accept", ""):
        return _private(JsonResponse({"error": error_message}, status=400))
    messages.error(request, error_message)
    return _private(redirect("online_reservations:detail", token=reservation.access_token))


@csrf_exempt
@require_POST
def callback(request):
    try:
        if len(request.body) > 65536:
            raise ValueError
        result = zalopay_services.process_callback(json.loads(request.body))
    except (ValueError, TypeError):
        result = {"return_code": -1, "return_message": "Invalid JSON"}
    except (DatabaseError, ImproperlyConfigured):
        result = {"return_code": 0, "return_message": "Temporarily unavailable"}
    return JsonResponse(result)


@never_cache
@require_GET
def result(request, token):
    row = get_object_or_404(ZaloPayTransaction, token=token)
    # No provider query/settlement is performed from redirect parameters.
    return _private(render(request, "staff/sales/zalopay_result.html", {"payment": row, "payment_state": serialize(row)}))


@never_cache
@require_GET
def state(request, token):
    return _private(JsonResponse(serialize(get_object_or_404(ZaloPayTransaction, token=token))))


@never_cache
@require_POST
def query(request, token):
    get_object_or_404(ZaloPayTransaction, token=token)
    try:
        row = zalopay_services.query_transaction(token)
    except (ValidationError, ImproperlyConfigured, zalopay.GatewayUnavailable):
        return _private(JsonResponse({"error": "Chưa xác minh được giao dịch. Giữ mã hiện tại và thử truy vấn lại sau."}, status=503))
    return _private(JsonResponse(serialize(row)))
