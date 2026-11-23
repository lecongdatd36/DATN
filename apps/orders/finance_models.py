"""Accounting documents; receipts and original invoices are never overwritten by refunds."""
from uuid import uuid4
from django.conf import settings
from django.db import models
from django.utils import timezone


class CashShift(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Đang mở"
        CLOSED = "CLOSED", "Đã chốt, chờ xác nhận"
        REVIEWED = "REVIEWED", "Đã xác nhận bàn giao"

    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_shifts")
    opening_amount = models.DecimalField("Tiền đầu ca", max_digits=14, decimal_places=0)
    counted_amount = models.DecimalField("Tiền thực đếm", max_digits=14, decimal_places=0, null=True, blank=True)
    expected_amount = models.DecimalField("Tiền mặt theo hệ thống", max_digits=14, decimal_places=0, null=True, blank=True)
    difference = models.DecimalField("Chênh lệch", max_digits=14, decimal_places=0, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_cash_shifts")
    note = models.CharField("Ghi chú đầu ca", max_length=500, blank=True)
    closing_note = models.CharField("Ghi chú bàn giao / lý do chênh lệch", max_length=1000, blank=True)
    review_note = models.CharField("Xác nhận của quản lý", max_length=1000, blank=True)
    totals_snapshot = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-opened_at", "-pk")
        constraints = [
            models.UniqueConstraint(fields=("cashier",), condition=models.Q(status="OPEN"), name="one_open_cash_shift_per_cashier"),
            models.CheckConstraint(condition=models.Q(opening_amount__gte=0) & (models.Q(counted_amount__isnull=True) | models.Q(counted_amount__gte=0)), name="cash_shift_nonnegative_cash"),
            models.CheckConstraint(condition=models.Q(status="OPEN", closed_at__isnull=True, counted_amount__isnull=True, expected_amount__isnull=True, difference__isnull=True) | models.Q(status__in=("CLOSED", "REVIEWED"), closed_at__isnull=False, counted_amount__isnull=False, expected_amount__isnull=False, difference__isnull=False), name="cash_shift_closing_fields"),
            models.CheckConstraint(condition=models.Q(status="REVIEWED", reviewed_at__isnull=False, reviewed_by__isnull=False) | models.Q(status__in=("OPEN", "CLOSED"), reviewed_at__isnull=True, reviewed_by__isnull=True), name="cash_shift_review_fields"),
        ]

    def __str__(self):
        return f"CA{self.pk:06d} · {self.cashier}"


class InvoiceRefund(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Chờ duyệt"
        APPROVED = "APPROVED", "Đã duyệt, chờ hoàn"
        COMPLETED = "COMPLETED", "Đã ghi nhận hoàn tiền"
        REJECTED = "REJECTED", "Đã từ chối"

    request_key = models.UUIDField(default=uuid4, unique=True, editable=False)
    invoice = models.ForeignKey("orders.Invoice", on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey("orders.Payment", on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField("Số tiền hoàn", max_digits=12, decimal_places=0)
    method = models.CharField("Cách hoàn", max_length=20, choices=(("CASH", "Tiền mặt"), ("BANK_TRANSFER", "Chuyển khoản"), ("CARD", "Thẻ"), ("VNPAY", "VNPAY"), ("ZALOPAY", "ZaloPay")))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    reason = models.CharField("Lý do", max_length=1000)
    reference = models.CharField("Mã giao dịch hoàn / bằng chứng", max_length=100, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_invoice_refunds")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_invoice_refunds")
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="completed_invoice_refunds")
    cash_shift = models.ForeignKey(CashShift, on_delete=models.PROTECT, null=True, blank=True, related_name="refunds")
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=1000, blank=True)
    completion_note = models.CharField(max_length=1000, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-requested_at", "-pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="invoice_refund_amount_positive"),
            models.CheckConstraint(condition=models.Q(status__in=("REQUESTED", "APPROVED", "COMPLETED", "REJECTED")), name="invoice_refund_status_valid"),
            models.CheckConstraint(condition=models.Q(method__in=("CASH", "BANK_TRANSFER", "CARD", "VNPAY", "ZALOPAY")), name="invoice_refund_method_valid"),
            models.CheckConstraint(condition=models.Q(status="COMPLETED", completed_at__isnull=False, completed_by__isnull=False) | (~models.Q(status="COMPLETED") & models.Q(completed_at__isnull=True, completed_by__isnull=True)), name="invoice_refund_completion_fields"),
            models.UniqueConstraint(fields=("method", "reference"), condition=models.Q(status="COMPLETED") & ~models.Q(method="CASH") & ~models.Q(reference=""), name="invoice_refund_unique_transfer_proof"),
        ]


class PaymentReconciliation(models.Model):
    class Outcome(models.TextChoices):
        APPLIED = "APPLIED", "Đã áp dụng vào hóa đơn"
        REFUNDED = "REFUNDED", "Đã hoàn khoản nhận thừa"
        MATCHED = "MATCHED", "Đã khớp với phiếu thu có sẵn"

    transaction = models.OneToOneField("orders.ZaloPayTransaction", on_delete=models.PROTECT, related_name="reconciliation")
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    reference = models.CharField(max_length=100)
    reason = models.CharField(max_length=1000)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    resolved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-resolved_at", "-pk")
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="reconciliation_positive_amount")]


class FinanceLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    shift = models.ForeignKey(CashShift, on_delete=models.PROTECT, null=True, blank=True, related_name="logs")
    refund = models.ForeignKey(InvoiceRefund, on_delete=models.PROTECT, null=True, blank=True, related_name="logs")
    reconciliation = models.ForeignKey(PaymentReconciliation, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=60)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
