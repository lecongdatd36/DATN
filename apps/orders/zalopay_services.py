"""Sandbox checkout orchestration. Network calls never run while holding DB locks."""
import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.menu_lock import lock_menu
from core.seating_lock import lock_seating_schedule
from . import services, zalopay
from .models import Invoice, OnlinePayment, Order, OrderItem, Payment, ZaloPayTransaction


def _lock():
    lock_seating_schedule()
    lock_menu()


def _target(row):
    if row.order_payment_id:
        return "order", row.order_payment.order_id
    return "reservation", row.deposit_payment.reservation_id


def _new_transaction(*, reference, amount, base_url, expires_at, callback_url=None, order_payment=None, deposit_payment=None, order_revision=0):
    app_id, _, _ = zalopay.configuration()
    target = "order" if order_payment else "reservation"
    target_id = order_payment.order_id if order_payment else deposit_payment.reservation_id
    row = ZaloPayTransaction.objects.create(app_id=app_id, app_trans_id=reference, amount=amount,
        expires_at=expires_at, order_payment=order_payment, deposit_payment=deposit_payment, order_revision=order_revision)
    result_url = base_url.rstrip("/") + reverse("zalopay:result", args=[row.token])
    payload = {"app_id": app_id, "app_trans_id": reference, "app_user": f"{target}_{target_id}",
        "app_time": int(timezone.now().timestamp() * 1000), "amount": int(amount),
        "embed_data": zalopay.json_text({"redirecturl": result_url, "target": target, "target_id": target_id}),
        "item": zalopay.json_text([{"itemid": str(target_id), "itemname": target,
            "itemprice": int(amount), "itemquantity": 1}]),
        "description": f"Sandbox - {target} #{target_id}",
        "callback_url": callback_url or base_url.rstrip("/") + reverse("zalopay:callback"),
        "expire_duration_seconds": min(900, int((expires_at-timezone.now()).total_seconds()))}
    if payload["expire_duration_seconds"] < zalopay.MIN_EXPIRE_SECONDS:
        raise ValidationError("Thời gian giữ chỗ còn dưới 5 phút nên không thể mở thanh toán ZaloPay. Vui lòng chọn lịch hẹn khác hoặc liên hệ nhà hàng; lịch hiện tại chưa được gia hạn.")
    row.request_data = payload  # MAC/keys are never persisted.
    row.save(update_fields=("request_data", "updated_at"))
    return row


def _pending_order(order):
    pending = order.online_payments.filter(status=OnlinePayment.Status.PENDING).first()
    if not pending:
        return None
    row = ZaloPayTransaction.objects.filter(order_payment=pending).first()
    if not row:
        raise ValidationError("Hóa đơn đang có giao dịch cổng khác chờ kết quả.")
    return row


def create_order_payment(*, actor, order_id, base_url, callback_url=None, promotion_code=None, quick_payment=False):
    zalopay.configuration()
    if promotion_code is not None and (not isinstance(promotion_code, str) or len(promotion_code)>30):
        raise ValidationError("Mã ưu đãi không hợp lệ.")
    with transaction.atomic():
        services._lock_actor(actor, "collect_payment")
        if quick_payment:
            services.prepare_quick_payment(actor=actor, order_id=order_id)
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status != Order.Status.PAYMENT_REQUESTED:
            raise ValidationError("Đơn chưa ở trạng thái yêu cầu thanh toán.")
        if Invoice.objects.filter(order=order, paid_amount__gt=0).exists():
            raise ValidationError("Hóa đơn đã có khoản thu, không tạo giao dịch mới.")
        existing = _pending_order(order)
        if existing:
            return existing
        items = order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED)
        if not items.exists() or items.exclude(status=OrderItem.Status.SERVED).exists():
            raise ValidationError("Cần phục vụ xong tất cả món trước khi thanh toán.")
        quote = services.payment_preview(order, promotion_code=promotion_code)
        if quote["due"] <= 0:
            raise ValidationError("Không có số tiền cần thanh toán qua ZaloPay.")
        services._store_promotion(order, quote)
        order.save(update_fields=("promotion_code_snapshot", "promotion_discount_amount", "discount_amount", "total_amount", "updated_at"))
        reference = zalopay.transaction_id()
        payment = OnlinePayment.objects.create(order=order, txn_ref=reference, amount=quote["due"],
            deposit_amount=quote["deposit_credit"], subtotal=quote["subtotal"], discount_percent=quote["discount_percent"],
            discount_amount=quote["discount"], membership_discount_amount=quote["membership_discount"],
            promotion_code=quote["promotion_code"], promotion_discount_amount=quote["promotion_discount"])
        row = _new_transaction(reference=reference, amount=payment.amount, base_url=base_url,
            expires_at=timezone.now()+timedelta(minutes=15), callback_url=callback_url,
            order_payment=payment, order_revision=order.revision)
    return _send_create(row)


def create_deposit_payment(*, token, revision, base_url, callback_url=None):
    from apps.reservations import services as reservations
    from apps.reservations.models import DepositPayment, Reservation
    zalopay.configuration()
    with transaction.atomic():
        _lock()
        reservations.expire_holds()
        reservation = Reservation.objects.select_for_update().get(access_token=token)
        if (reservation.status != "WAITING" or reservation.revision != revision or
                reservation.hold_expires_at <= timezone.now()):
            raise ValidationError("Yêu cầu không còn trong thời gian thanh toán cọc.")
        if reservation.deposits.filter(status__in=("PAID", "REVIEW")).exists():
            raise ValidationError("Cọc đã có khoản nhận tiền; cần đối soát trước.")
        pending = reservation.deposits.filter(status="PENDING").first()
        if pending:
            existing = ZaloPayTransaction.objects.filter(deposit_payment=pending).first()
            if existing:
                return existing
            raise ValidationError("Cọc đang có giao dịch cổng khác chờ kết quả.")
        reference = zalopay.transaction_id()
        payment = DepositPayment.objects.create(reservation=reservation, txn_ref=reference,
            amount=reservation.deposit_required, revision=reservation.revision)
        row = _new_transaction(reference=reference, amount=payment.amount, base_url=base_url,
            expires_at=reservation.hold_expires_at, callback_url=callback_url, deposit_payment=payment)
    return _send_create(row)


def _send_create(row):
    payload = {**row.request_data, "mac": zalopay.create_mac(row.request_data)}
    try:
        result = zalopay.post("create", payload)
    except zalopay.GatewayUnavailable as error:
        ZaloPayTransaction.objects.filter(pk=row.pk, status="PENDING").update(last_error=str(error))
        row.refresh_from_db()
        return row  # Outcome unknown: keep the durable reference, never blindly recreate.
    with transaction.atomic():
        _lock()
        current = ZaloPayTransaction.objects.select_for_update().get(pk=row.pk)
        current.response_data = _safe_response(result)
        if current.status == "PENDING":
            if result.get("return_code") == 2:
                _fail(current)
                current.last_error = "ZaloPay Sandbox từ chối tạo giao dịch. Có thể thử lại sau khi kiểm tra cấu hình."
            elif result.get("return_code") == 1:
                current.order_url = zalopay.checkout_url(result.get("order_url"))
                if not current.order_url:
                    current.last_error = "Chưa có đường dẫn thanh toán Sandbox hợp lệ. Hãy truy vấn giao dịch."
            else:
                current.last_error = "Chưa rõ kết quả tạo giao dịch. Hãy truy vấn trước khi tạo lại."
        current.save()
    return current


def _safe_response(result):
    return {key: result[key] for key in ("return_code", "sub_return_code", "amount", "zp_trans_id", "is_processing") if key in result}


def _fail(row):
    row.status = "FAILED"
    if row.order_payment_id:
        OnlinePayment.objects.filter(pk=row.order_payment_id, status="PENDING").update(status="FAILED")
    else:
        from apps.reservations.models import DepositPayment
        DepositPayment.objects.filter(pk=row.deposit_payment_id, status="PENDING").update(status="FAILED")


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValidationError("Invalid numeric field")
    if isinstance(value, str) and not value.isdigit():
        raise ValidationError("Invalid numeric field")
    return int(value)


@transaction.atomic
def _settle(reference, data, *, callback):
    _lock()
    row = ZaloPayTransaction.objects.select_for_update().get(app_trans_id=reference)
    app_id, _, _ = zalopay.configuration()
    if row.app_id != app_id or ("app_id" in data and _integer(data["app_id"]) != row.app_id):
        raise ValidationError("Invalid app_id")
    if _integer(data.get("amount")) != row.amount:
        raise ValidationError("Invalid amount")
    if "app_trans_id" in data and data["app_trans_id"] != row.app_trans_id:
        raise ValidationError("Invalid app_trans_id")
    provider_id = str(_integer(data.get("zp_trans_id")))
    if int(provider_id) <= 0 or len(provider_id) > 40:
        raise ValidationError("Invalid zp_trans_id")
    if callback:
        if "app_id" not in data or data.get("app_trans_id") != reference:
            raise ValidationError("Missing order identity")
        try:
            embedded = json.loads(data.get("embed_data", ""))
        except (TypeError, ValueError):
            raise ValidationError("Invalid order identity") from None
        target, target_id = _target(row)
        if not isinstance(embedded, dict) or embedded.get("target") != target or embedded.get("target_id") != target_id:
            raise ValidationError("Invalid order identity")
    if row.zp_trans_id and row.zp_trans_id != provider_id:
        raise ValidationError("Conflicting provider transaction")
    if ZaloPayTransaction.objects.filter(zp_trans_id=provider_id).exclude(pk=row.pk).exists():
        raise ValidationError("Provider transaction already used")
    if row.status in ("PAID", "REVIEW"):
        return row
    row.zp_trans_id = provider_id
    row.paid_at = timezone.now()
    row.last_error = ""
    try:
        with transaction.atomic():
            if row.order_payment_id:
                payment = OnlinePayment.objects.select_for_update().get(pk=row.order_payment_id)
                order = Order.objects.select_for_update().get(pk=payment.order_id)
                if (payment.txn_ref != reference or payment.amount != row.amount or
                        order.status != Order.Status.PAYMENT_REQUESTED or order.revision != row.order_revision):
                    raise ValidationError("Đơn hàng đã thay đổi hoặc đã được thanh toán bằng giao dịch khác.")
                services._complete_payment(order=order, subtotal=payment.subtotal, discount_percent=payment.discount_percent,
                    discount_amount=payment.discount_amount, membership_discount_amount=payment.membership_discount_amount,
                    promotion_code=payment.promotion_code, promotion_discount_amount=payment.promotion_discount_amount,
                    total=payment.amount+payment.deposit_amount, expected_deposit=payment.deposit_amount,
                    payment_method=Payment.Method.ZALOPAY, reference=provider_id, actor_snapshot="ZaloPay Sandbox")
                payment.status = "PAID"
                payment.paid_at = row.paid_at
                payment.provider_transaction_no = provider_id
                payment.save()
                row.status = "PAID"
            else:
                from apps.reservations import services as reservations
                from apps.reservations.models import DepositPayment
                reservations.expire_holds()
                payment = DepositPayment.objects.select_for_update().get(pk=row.deposit_payment_id)
                if payment.txn_ref != reference or payment.amount != row.amount:
                    raise ValidationError("Khoản cọc không khớp giao dịch.")
                accepted = reservations.confirm_deposit_payment(payment, provider_reference=provider_id)
                row.status = "PAID" if accepted else "REVIEW"
    except ValidationError:
        # Preserve verified money for reconciliation; never alter the original invoice.
        row.status = "REVIEW"
        row.last_error = "Đã nhận tiền Sandbox nhưng đơn/lịch đã thay đổi. Nhà hàng cần đối soát."
    row.response_data = _safe_response(data)
    row.save()
    return row


def process_callback(payload):
    try:
        data = zalopay.callback_data(payload)
    except ValidationError:
        return {"return_code": -1, "return_message": "Invalid callback"}
    try:
        _settle(data.get("app_trans_id"), data, callback=True)
    except (ValidationError, ZaloPayTransaction.DoesNotExist):
        return {"return_code": 2, "return_message": "Transaction does not match"}
    return {"return_code": 1, "return_message": "success"}


def query_transaction(token):
    app_id, _, _ = zalopay.configuration()
    with transaction.atomic():
        _lock()
        row = ZaloPayTransaction.objects.select_for_update().get(token=token)
        if row.status in ("PAID", "REVIEW"):
            return row
        if row.app_id != app_id:
            raise ValidationError("App giao dịch không khớp cấu hình Sandbox hiện tại.")
        if row.last_queried_at and row.last_queried_at > timezone.now()-timedelta(seconds=30):
            return row
        row.last_queried_at = timezone.now()
        row.save(update_fields=("last_queried_at", "updated_at"))
    result = zalopay.post("query", zalopay.query_payload(row.app_trans_id))
    if result.get("return_code") == 1:
        return _settle(row.app_trans_id, result, callback=False)
    with transaction.atomic():
        _lock()
        current = ZaloPayTransaction.objects.select_for_update().get(pk=row.pk)
        if current.status not in ("PAID", "REVIEW"):
            current.response_data = _safe_response(result)
            if result.get("return_code") == 2 and result.get("is_processing") is False:
                _fail(current)
            current.save()
        return current
