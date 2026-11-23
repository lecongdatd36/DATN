"""Refunds, verified provider reconciliation and cashier handover, serialized with POS writes."""
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from core.permissions import can_manage_accounts
from .models import CashShift, FinanceLog, Invoice, InvoiceRefund, Order, Payment, PaymentReconciliation, ZaloPayTransaction


def money(value, *, zero=False):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Số tiền không hợp lệ.") from None
    if not value.is_finite() or value != value.to_integral_value() or value < 0 or (not zero and value == 0) or value > 999999999999:
        raise ValidationError("Số tiền phải là số nguyên đồng trong giới hạn cho phép.")
    return value


def text(value, *, minimum=5, maximum=1000):
    value = value.strip() if isinstance(value, str) else ""
    if not minimum <= len(value) <= maximum:
        raise ValidationError(f"Nội dung cần từ {minimum} đến {maximum} ký tự.")
    return value


def actor_for(actor, *, manager=False):
    from .services import _lock_actor
    actor = _lock_actor(actor, "collect_payment")
    if manager and not can_manage_accounts(actor):
        raise PermissionDenied("Chỉ quản lý được duyệt hoàn tiền và đối soát.")
    return actor


def log(actor, action, description, **targets):
    FinanceLog.objects.create(actor=actor, action=action, description=description, **targets)


def current_shift(actor):
    if actor is None or not getattr(actor, "pk", None):
        return None
    return CashShift.objects.select_for_update().filter(cashier=actor, status=CashShift.Status.OPEN).first()


def _sum(query):
    return query.aggregate(total=Sum("amount"))["total"] or Decimal(0)


def shift_totals(shift):
    receipts = {row["method"]: str(row["amount"]) for row in shift.payments.exclude(method=Payment.Method.DEPOSIT).values("method").annotate(amount=Sum("amount"))}
    refunds = {row["method"]: str(row["amount"]) for row in shift.refunds.filter(status="COMPLETED").values("method").annotate(amount=Sum("amount"))}
    expected = shift.opening_amount + Decimal(receipts.get("CASH", "0")) - Decimal(refunds.get("CASH", "0"))
    return {"receipts": receipts, "refunds": refunds, "expected_cash": str(expected),
        "receipt_count": shift.payments.exclude(method=Payment.Method.DEPOSIT).count(),
        "refund_count": shift.refunds.filter(status="COMPLETED").count()}


@transaction.atomic
def open_shift(*, actor, opening_amount, note=""):
    actor = actor_for(actor)
    if current_shift(actor):
        raise ValidationError("Bạn đang có ca thu ngân mở. Chốt ca hiện tại trước khi mở ca mới.")
    row = CashShift.objects.create(cashier=actor, opening_amount=money(opening_amount, zero=True),
        note=text(note, minimum=0, maximum=500))
    log(actor, "Mở ca thu ngân", f"Tiền đầu ca {row.opening_amount:.0f} đồng.", shift=row)
    return row


@transaction.atomic
def close_shift(*, actor, shift_id, revision, counted_amount, note=""):
    actor = actor_for(actor)
    row = CashShift.objects.select_for_update().get(pk=shift_id)
    if row.cashier_id != actor.pk and not can_manage_accounts(actor):
        raise PermissionDenied("Bạn chỉ được chốt ca của mình.")
    if row.status != "OPEN" or row.revision != revision:
        raise ValidationError("Ca đã thay đổi hoặc đã được chốt. Tải lại trước khi thao tác.")
    snapshot = shift_totals(row)
    row.expected_amount = Decimal(snapshot["expected_cash"])
    row.counted_amount = money(counted_amount, zero=True)
    row.difference = row.counted_amount - row.expected_amount
    row.closing_note = text(note, minimum=5 if row.difference else 0)
    row.totals_snapshot = snapshot
    row.closed_at = timezone.now()
    row.status = "CLOSED"
    row.revision += 1
    row.save()
    log(actor, "Chốt ca thu ngân", f"Theo hệ thống {row.expected_amount:.0f}; thực đếm {row.counted_amount:.0f}; chênh lệch {row.difference:.0f}. {row.closing_note}", shift=row)
    return row


@transaction.atomic
def review_shift(*, actor, shift_id, revision, note):
    actor = actor_for(actor, manager=True)
    row = CashShift.objects.select_for_update().get(pk=shift_id)
    if row.status != "CLOSED" or row.revision != revision:
        raise ValidationError("Ca không còn ở trạng thái chờ xác nhận.")
    row.review_note = text(note)
    row.status = "REVIEWED"
    row.reviewed_at = timezone.now()
    row.reviewed_by = actor
    row.revision += 1
    row.save()
    log(actor, "Xác nhận bàn giao", row.review_note, shift=row)
    return row


@transaction.atomic
def request_refund(*, actor, payment_id, amount, method, reason, request_key=None):
    actor = actor_for(actor)
    amount, reason = money(amount), text(reason)
    if method not in {value for value, _ in InvoiceRefund._meta.get_field("method").choices}:
        raise ValidationError("Phương thức hoàn không hợp lệ.")
    try:
        key = UUID(str(request_key)) if request_key else uuid4()
    except (ValueError, TypeError):
        raise ValidationError("Mã yêu cầu hoàn không hợp lệ.") from None
    existing = InvoiceRefund.objects.filter(request_key=key).first()
    if existing:
        if (existing.requested_by_id, existing.payment_id, existing.amount, existing.method, existing.reason) != (actor.pk, int(payment_id), amount, method, reason):
            raise ValidationError("Mã yêu cầu đã được dùng cho nội dung khác.")
        return existing
    payment = Payment.objects.select_for_update().select_related("invoice").get(pk=payment_id)
    invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    reserved = _sum(payment.refunds.filter(status__in=("REQUESTED", "APPROVED", "COMPLETED")))
    invoice_reserved = _sum(invoice.refunds.filter(status__in=("REQUESTED", "APPROVED", "COMPLETED")))
    if invoice.status == "CANCELLED" or amount > payment.amount - reserved or amount > invoice.paid_amount - invoice_reserved:
        raise ValidationError("Số tiền vượt khoản còn được hoàn hoặc hóa đơn đã hủy.")
    row = InvoiceRefund.objects.create(request_key=key, invoice=invoice, payment=payment, amount=amount,
        method=method, reason=reason, requested_by=actor)
    log(actor, "Yêu cầu hoàn hóa đơn", f"{invoice.invoice_code}: {amount:.0f} đồng. {reason}", refund=row)
    return row


@transaction.atomic
def review_refund(*, actor, refund_id, revision, approve, note):
    actor = actor_for(actor, manager=True)
    row = InvoiceRefund.objects.select_for_update().get(pk=refund_id)
    if (row.status != "REQUESTED" and not (row.status == "APPROVED" and not approve)) or row.revision != revision:
        raise ValidationError("Yêu cầu hoàn đã được xử lý hoặc đã thay đổi.")
    row.status = "APPROVED" if approve else "REJECTED"
    row.reviewed_by = actor
    row.reviewed_at = timezone.now()
    row.review_note = text(note)
    row.revision += 1
    row.save()
    log(actor, "Duyệt hoàn" if approve else "Từ chối hoàn", row.review_note, refund=row)
    return row


@transaction.atomic
def complete_refund(*, actor, refund_id, revision, reference, note, verified=False):
    actor = actor_for(actor)
    row = InvoiceRefund.objects.select_for_update().select_related("payment").get(pk=refund_id)
    if row.status == "COMPLETED":
        return row  # Repeated submission never pays/refunds twice.
    if row.status != "APPROVED" or row.revision != revision or verified is not True:
        raise ValidationError("Cần phiếu đã duyệt, đúng phiên bản và xác nhận đã thực sự hoàn tiền.")
    row.reference = text(reference, minimum=0 if row.method == "CASH" else 3, maximum=100)
    row.completion_note = text(note)
    if row.method != "CASH" and InvoiceRefund.objects.filter(status="COMPLETED", method=row.method, reference=row.reference).exists():
        raise ValidationError("Bằng chứng giao dịch hoàn đã được sử dụng.")
    row.cash_shift = current_shift(actor)
    if row.method == "CASH":
        if row.cash_shift is None:
            raise ValidationError("Mở ca thu ngân trước khi hoàn tiền mặt.")
        if Decimal(shift_totals(row.cash_shift)["expected_cash"]) < row.amount:
            raise ValidationError("Tiền mặt theo ca không đủ để hoàn khoản này.")
    invoice = Invoice.objects.select_for_update().get(pk=row.invoice_id)
    if _sum(row.payment.refunds.filter(status="COMPLETED")) + row.amount > row.payment.amount or invoice.refunded_amount + row.amount > invoice.paid_amount:
        raise ValidationError("Khoản hoàn vượt số tiền thực nhận còn lại.")
    row.status = "COMPLETED"
    row.completed_by = actor
    row.completed_at = timezone.now()
    row.revision += 1
    row.save()
    invoice.refunded_amount += row.amount
    invoice.save(update_fields=("refunded_amount", "updated_at"))
    if invoice.status == "PAID" and invoice.customer_id:
        from apps.customers.models import Customer
        from apps.customers.services import tier_for_spending
        customer = Customer.objects.select_for_update().get(pk=invoice.customer_id)
        customer.total_spending = max(Decimal(0), customer.total_spending - row.amount)
        customer.membership_tier = tier_for_spending(customer.total_spending)
        customer.save(update_fields=("total_spending", "membership_tier", "updated_at"))
    from .services import _log
    _log(actor, invoice.order, "Hoàn tiền hóa đơn", f"Phiếu hoàn {row.pk}; {row.amount:.0f} đồng; {row.get_method_display()}; {row.reference}. {row.reason}")
    log(actor, "Ghi nhận đã hoàn", row.completion_note, refund=row, shift=row.cash_shift)
    return row


@transaction.atomic
def reconcile_zalopay(*, actor, transaction_id, outcome, reference, reason, verified=False):
    actor = actor_for(actor, manager=True)
    row = ZaloPayTransaction.objects.select_for_update(of=("self",)).select_related("order_payment__order").get(pk=transaction_id)
    if hasattr(row, "reconciliation"):
        raise ValidationError("Giao dịch đã có kết quả đối soát.")
    if row.status != "REVIEW" or not row.order_payment_id or not row.zp_trans_id or not row.paid_at or verified is not True:
        raise ValidationError("Chỉ đối soát khoản tiền đơn hàng đã được cổng xác minh và đang cần xử lý.")
    reason, reference = text(reason), text(reference, minimum=3, maximum=100)
    online = row.order_payment
    order = Order.objects.select_for_update().get(pk=online.order_id)
    if outcome == "MATCHED":
        if not Payment.objects.filter(invoice__order=order, method="ZALOPAY", reference=row.zp_trans_id, amount=row.amount).exists():
            raise ValidationError("Chưa có phiếu thu cùng mã ZaloPay, đơn và số tiền để khớp.")
    elif outcome == "APPLIED":
        from .services import _complete_payment, payment_preview
        if order.status != "PAYMENT_REQUESTED" or Invoice.objects.filter(order=order, paid_amount__gt=0).exists():
            raise ValidationError("Đơn không còn chờ thu hoặc đã có tiền thu. Hãy hoàn khoản nhận thừa.")
        if order.online_payments.exclude(pk=online.pk).filter(Q(status="PENDING") | Q(zalopay_transaction__status="REVIEW", zalopay_transaction__reconciliation__isnull=True)).exists():
            raise ValidationError("Đơn còn giao dịch khác đang chờ. Xác minh các khoản đó trước.")
        items = list(order.items.select_for_update().exclude(status="CANCELLED"))
        if not items or any(item.status != "SERVED" for item in items):
            raise ValidationError("Chỉ áp dụng vào đơn có món đã phục vụ đầy đủ.")
        preview = payment_preview(order, promotion_code=online.promotion_code or None)
        if preview["invoice_total"] - preview["deposit_credit"] != row.amount:
            raise ValidationError("Số tiền hiện tại không khớp khoản nhận; không tự áp dụng vào đơn.")
        invoice = _complete_payment(order=order, subtotal=preview["subtotal"], discount_percent=preview["discount_percent"],
            discount_amount=preview["discount"], membership_discount_amount=preview["membership_discount"],
            promotion_code=preview["promotion_code"], promotion_discount_amount=preview["promotion_discount"],
            total=preview["invoice_total"], expected_deposit=preview["deposit_credit"], payment_method="ZALOPAY",
            reference=row.zp_trans_id, actor=actor, actor_snapshot=actor.username)
        # Cash was received at the verified provider timestamp, not when reviewed.
        invoice.payments.filter(method="ZALOPAY", reference=row.zp_trans_id).update(created_at=row.paid_at, cash_shift=None)
        row.status = "PAID"
        online.status, online.paid_at = "PAID", row.paid_at
        online.provider_transaction_no = row.zp_trans_id
        online.save()
    elif outcome != "REFUNDED":
        raise ValidationError("Kết quả đối soát không hợp lệ.")
    if outcome == "REFUNDED" and PaymentReconciliation.objects.filter(outcome="REFUNDED", reference=reference).exists():
        raise ValidationError("Bằng chứng hoàn khoản nhận thừa đã được sử dụng.")
    result = PaymentReconciliation.objects.create(transaction=row, outcome=outcome, amount=row.amount,
        reference=reference, reason=reason, resolved_by=actor)
    if outcome == "REFUNDED":
        online.status = "CANCELLED"
        online.save(update_fields=("status", "updated_at"))
    elif outcome == "MATCHED":
        online.status, online.paid_at = "PAID", row.paid_at
        online.provider_transaction_no = row.zp_trans_id
        online.save(update_fields=("status", "paid_at", "provider_transaction_no", "updated_at"))
    row.last_error = ""
    row.save(update_fields=("status", "last_error", "updated_at"))
    log(actor, "Đối soát ZaloPay", f"{row.app_trans_id}: {outcome}; {reference}; {reason}", reconciliation=result)
    return result
