import json
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.reservations.models import Reservation
from core.devices import is_mobile_request
from . import zalopay, zalopay_services
from .models import Invoice, Order, ZaloPayTransaction
from .permissions import has_order_permission


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


def payment_destination(row, request):
    if row.deposit_payment_id:
        return reverse('online_reservations:detail', args=[row.deposit_payment.reservation.access_token]), True
    order_id = row.order_payment.order_id
    invoice = Invoice.objects.filter(order_id=order_id, status=Invoice.Status.PAID).first() if row.status == 'PAID' else None
    mobile = is_mobile_request(request)
    if mobile and invoice and has_order_permission(request.user, 'collect_payment'):
        return reverse('sales:mobile')+'?'+urlencode({'page':'receipt','invoice':invoice.pk}), True
    if mobile:
        params = {'page':'tables','paid_order':order_id} if invoice else {'page':'order','order':order_id}
        target = reverse('sales:mobile')+'?'+urlencode(params)
    elif invoice:
        params = {'paid_order':order_id}
        order = row.order_payment.order
        table_id = order.table_id or (order.booking.table_id if order.booking_id else None)
        if table_id:
            params['table'] = table_id
        target = reverse('sales:workspace')+'?'+urlencode(params)
    else:
        target = reverse('sales:workspace')+'?'+urlencode({'order':order_id})+'#sales-order'
    permitted = has_order_permission(request.user, 'view_order')
    return target if permitted else reverse('accounts:login')+'?'+urlencode({'next':target}), permitted


def serialize(row, request=None):
    return_url, auto_return = payment_destination(row, request) if request else ('', False)
    pending = row.status == 'PENDING'
    expired = pending and row.expires_at <= timezone.now()
    return {"app_trans_id": row.app_trans_id, "amount": str(row.amount), "status": row.status,
        "status_label": _("Hết hạn mở cổng · Chờ xác minh") if expired else _(row.get_status_display()),
        "sandbox": True,
        "message": _("Đã hết thời gian mở cổng thanh toán. ZaloPay chưa trả kết quả cuối cùng. Kiểm tra lại giao dịch hoặc liên hệ người quản lý để đối soát; chưa thu thêm tiền cho đơn này.") if expired else row.last_error,
        "checkout_expired": expired, "auto_poll": pending and not expired,
        "expires_at": row.expires_at.isoformat(),
        "can_change_method": bool(expired and row.order_payment_id and request and has_order_permission(request.user, 'collect_payment')),
        "return_url": return_url, "auto_return": auto_return,
        "order_url": row.order_url if pending and not expired else "",
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
    return _private(JsonResponse(serialize(row, request), status=201))


@never_cache
@require_POST
def deposit_create(request, token):
    reservation = get_object_or_404(Reservation, access_token=token)
    try:
        data = _input(request)
        if data.get("agree") != "yes":
            raise ValidationError(_("Cần đồng ý điều kiện thanh toán trước khi trả cọc."))
        row = zalopay_services.create_deposit_payment(token=token, revision=int(data.get("revision", "0")),
            base_url=base_url(request), callback_url=callback_url(request))
    except ImproperlyConfigured:
        error_message = "ZaloPay Sandbox chưa được cấu hình kết nối. Vui lòng liên hệ nhà hàng."
    except ValidationError as error:
        error_message = " ".join(error.messages)
    except (ValueError, TypeError):
        error_message = "Thông tin thanh toán không hợp lệ. Vui lòng tải lại lịch đặt bàn rồi thử lại."
    else:
        state_data = serialize(row, request)
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
    row = get_object_or_404(ZaloPayTransaction.objects.select_related('order_payment__order__table','deposit_payment__reservation'), token=token)
    # No provider query/settlement is performed from redirect parameters.
    payment_state = serialize(row, request)
    if row.status == 'PAID' and payment_state['auto_return']:
        return _private(redirect(payment_state['return_url']))
    return _private(render(request, "staff/sales/zalopay_result.html", {
        "payment": row, "payment_state": payment_state,
        "payment_base": 'customer/base_customer.html' if row.deposit_payment_id else 'base.html',
    }))


@never_cache
@require_GET
def state(request, token):
    return _private(JsonResponse(serialize(get_object_or_404(ZaloPayTransaction, token=token), request)))


@never_cache
@require_POST
def query(request, token):
    get_object_or_404(ZaloPayTransaction, token=token)
    try:
        row = zalopay_services.query_transaction(token)
    except (ValidationError, ImproperlyConfigured, zalopay.GatewayUnavailable):
        return _private(JsonResponse({"error": "Chưa xác minh được giao dịch. Giữ mã hiện tại và thử truy vấn lại sau."}, status=503))
    return _private(JsonResponse(serialize(row, request)))


@login_required
@never_cache
@require_POST
def change_method(request, token):
    if not has_order_permission(request.user, 'collect_payment'):
        raise PermissionDenied
    get_object_or_404(ZaloPayTransaction, token=token)
    try:
        row = zalopay_services.abandon_order_payment(actor=request.user, token=token,
            reason=request.POST.get('reason'), confirm_unpaid=request.POST.get('confirm_unpaid') == 'yes')
    except (ValidationError, ImproperlyConfigured, zalopay.GatewayUnavailable) as error:
        message = ' '.join(error.messages) if isinstance(error, ValidationError) else str(error)
        messages.error(request, message)
        return _private(redirect('zalopay:result', token=token))
    target, _ = payment_destination(row, request)
    if row.status in ('ABANDONED', 'FAILED'):
        messages.success(request, 'Đã mở lại lựa chọn thanh toán. Chọn tiền mặt, chuyển khoản hoặc tạo giao dịch ZaloPay mới. Giao dịch cũ được giữ để đối soát.')
        if is_mobile_request(request) or request.POST.get('return_mobile') == '1':
            target = reverse('sales:mobile')+'?'+urlencode({'page':'checkout','order':row.order_payment.order_id})
    elif row.status == 'REVIEW':
        messages.error(request, 'ZaloPay đã ghi nhận tiền, cần đối soát. Kiểm tra khoản nhận trước khi thu thêm.')
        target = reverse('zalopay:result', args=[row.token])
    else:
        messages.success(request, 'ZaloPay vừa xác nhận thanh toán thành công. Hóa đơn đã được cập nhật.')
    return _private(redirect(target))
