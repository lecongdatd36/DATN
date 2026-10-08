from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, MaxLengthValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class PromotionCode(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "PERCENT", "Phần trăm"
        FIXED = "FIXED", "Số tiền cố định"

    code = models.CharField("Mã giảm giá", max_length=30, unique=True)
    name = models.CharField("Tên chương trình", max_length=150)
    discount_type = models.CharField("Loại giảm", max_length=10, choices=DiscountType.choices)
    value = models.DecimalField("Giá trị", max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    minimum_order = models.DecimalField("Đơn tối thiểu", max_digits=12, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    maximum_discount = models.DecimalField("Giảm tối đa", max_digits=12, decimal_places=0, null=True, blank=True, validators=[MinValueValidator(1)])
    starts_at = models.DateTimeField("Bắt đầu")
    ends_at = models.DateTimeField("Kết thúc")
    is_active = models.BooleanField("Đang áp dụng", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "mã giảm giá"
        verbose_name_plural = "mã giảm giá"
        constraints = [
            models.CheckConstraint(condition=models.Q(value__gt=0), name="promotion_value_positive"),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="promotion_valid_period"),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class Order(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Đang mở"
        IN_PROGRESS = "IN_PROGRESS", "Đang phục vụ"
        PAYMENT_REQUESTED = "PAYMENT_REQUESTED", "Yêu cầu thanh toán"
        COMPLETED = "COMPLETED", "Hoàn tất"
        CANCELLED = "CANCELLED", "Đã hủy"

    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, related_name="order", verbose_name="Lượt khách", null=True, blank=True)
    table = models.ForeignKey("seating.DiningTable", on_delete=models.PROTECT, related_name="orders", null=True, blank=True, verbose_name="Bàn")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="orders", null=True, blank=True, verbose_name="Khách hàng")
    employee = models.ForeignKey("employees.EmployeeProfile", on_delete=models.SET_NULL, related_name="orders", null=True, blank=True, verbose_name="Nhân viên phục vụ")
    split_root = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="split_checks", null=True, blank=True,
        verbose_name="Hóa đơn gốc khi tách",
    )
    order_code = models.CharField("Mã đơn", max_length=20, unique=True, null=True, blank=True)
    guest_count = models.PositiveSmallIntegerField("Số khách", default=1, validators=[MinValueValidator(1), MaxValueValidator(100)])
    status = models.CharField("Trạng thái", max_length=20, choices=Status.choices, default=Status.OPEN)
    subtotal = models.DecimalField("Tạm tính", max_digits=14, decimal_places=0, default=0)
    discount_amount = models.DecimalField("Giảm giá", max_digits=14, decimal_places=0, default=0)
    promotion_code_snapshot = models.CharField("Mã giảm giá", max_length=30, blank=True)
    promotion_discount_amount = models.DecimalField("Giảm theo mã", max_digits=14, decimal_places=0, default=0)
    total_amount = models.DecimalField("Tổng thanh toán", max_digits=14, decimal_places=0, default=0)
    note = models.TextField("Ghi chú", blank=True, max_length=1000)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    opened_at = models.DateTimeField("Mở lúc", null=True, blank=True)
    closed_at = models.DateTimeField("Đóng lúc", null=True, blank=True)
    created_at = models.DateTimeField("Mở lúc", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "đơn hàng"
        verbose_name_plural = "đơn hàng"
        permissions = [
            ("manage_order", "Mở đơn và gọi món"),
            ("collect_payment", "Thu tiền đơn hàng"),
            ("work_kitchen", "Xử lý món tại Bếp"),
            ("cancel_prepared_item", "Hủy món đã bắt đầu làm"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["OPEN", "IN_PROGRESS", "PAYMENT_REQUESTED", "COMPLETED", "CANCELLED"]), name="order_valid_status"),
            models.CheckConstraint(condition=models.Q(split_root__isnull=True) | ~models.Q(split_root=models.F("id")), name="order_split_root_not_self"),
        ]

    @property
    def reservation(self):
        return self.booking

    @property
    def total(self):
        return sum((item.subtotal for item in self.items.all() if item.status != OrderItem.Status.CANCELLED), Decimal(0))

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.pk])

    @property
    def check_root(self):
        return self.split_root or self

    @property
    def is_split_check(self):
        return self.split_root_id is not None

    def __str__(self):
        return self.order_code or "Đơn chưa lưu"


class OrderItem(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Chưa gửi Bếp"
        PENDING = "PENDING", "Chờ chế biến"
        COOKING = "COOKING", "Đang làm"
        READY = "READY", "Đã xong"
        SERVED = "SERVED", "Đã phục vụ"
        CANCELLED = "CANCELLED", "Đã hủy"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    dish = models.ForeignKey("menu.Dish", on_delete=models.PROTECT, related_name="order_items", verbose_name="Món")
    dish_code = models.CharField(max_length=20)
    dish_name = models.CharField(max_length=150)
    unit_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=9, decimal_places=0, validators=[MinValueValidator(1), MaxValueValidator(999999999)])
    quantity = models.PositiveSmallIntegerField("Số lượng", validators=[MinValueValidator(1), MaxValueValidator(100)])
    seat_number = models.PositiveSmallIntegerField(
        "Vị trí khách",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Số ghế/vị trí của khách trong bàn; bỏ trống nếu là món dùng chung.",
    )
    total_price = models.DecimalField("Thành tiền", max_digits=12, decimal_places=0, default=0)
    unit_cost_snapshot = models.DecimalField(
        "Giá vốn một món", max_digits=12, decimal_places=0, default=0,
        validators=[MinValueValidator(0)],
    )
    total_cost = models.DecimalField(
        "Tổng giá vốn", max_digits=14, decimal_places=0, default=0,
        validators=[MinValueValidator(0)],
    )
    inventory_deducted_at = models.DateTimeField("Đã trừ kho lúc", null=True, blank=True)
    inventory_returned_at = models.DateTimeField("Đã hoàn kho lúc", null=True, blank=True)
    note = models.TextField("Ghi chú cho Bếp", blank=True, max_length=500, validators=[MaxLengthValidator(500)])
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.DRAFT)
    cancellation_reason = models.CharField("Lý do hủy", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = "món trong đơn"
        verbose_name_plural = "món trong đơn"
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=100), name="order_item_quantity_range"),
            models.CheckConstraint(
                condition=models.Q(seat_number__isnull=True) | models.Q(seat_number__gte=1, seat_number__lte=100),
                name="order_item_seat_range",
            ),
            models.CheckConstraint(condition=models.Q(unit_price__gte=1, unit_price__lte=999999999), name="order_item_price_range"),
            models.CheckConstraint(condition=models.Q(unit_cost_snapshot__gte=0), name="order_item_unit_cost_nonnegative"),
            models.CheckConstraint(condition=models.Q(total_cost__gte=0), name="order_item_total_cost_nonnegative"),
            models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "PENDING", "COOKING", "READY", "SERVED", "CANCELLED"]), name="order_item_valid_status"),
            models.CheckConstraint(condition=~models.Q(status="CANCELLED") | models.Q(cancellation_reason__regex=r"\S", cancelled_at__isnull=False), name="order_item_cancel_reason"),
        ]
        indexes = [models.Index(fields=("status", "sent_at"), name="order_kitchen_queue_idx")]

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def sent_to_kitchen_at(self):
        return self.sent_at

    @property
    def cooking_at(self):
        return self.started_at

    def __str__(self):
        return f"{self.dish_name} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        self.total_cost = self.unit_cost_snapshot * self.quantity
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = tuple(set(update_fields) | {"total_price", "total_cost", "updated_at"})
        return super().save(*args, **kwargs)


class Invoice(models.Model):
    class Status(models.TextChoices):
        UNPAID = "UNPAID", "Chưa thanh toán"
        PAID = "PAID", "Đã thanh toán"
        CANCELLED = "CANCELLED", "Đã hủy"

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="invoice", verbose_name="Đơn hàng")
    invoice_code = models.CharField("Mã hóa đơn", max_length=20, unique=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    subtotal = models.DecimalField("Tạm tính", max_digits=12, decimal_places=0, default=0)
    discount_percent = models.DecimalField("Phần trăm giảm", max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField("Tiền giảm", max_digits=12, decimal_places=0, default=0)
    membership_discount_amount = models.DecimalField("Ưu đãi hạng", max_digits=12, decimal_places=0, default=0)
    promotion_code = models.CharField("Mã giảm giá", max_length=30, blank=True)
    promotion_discount_amount = models.DecimalField("Giảm theo mã", max_digits=12, decimal_places=0, default=0)
    total_amount = models.DecimalField("Cần thanh toán", max_digits=12, decimal_places=0, default=0)
    total = models.DecimalField("Tổng tiền", max_digits=12, decimal_places=0, default=0, validators=[MinValueValidator(0), MaxValueValidator(999999999999)])
    paid_amount = models.DecimalField("Đã thu", max_digits=12, decimal_places=0, default=0, validators=[MinValueValidator(0), MaxValueValidator(999999999999)])
    status = models.CharField("Trạng thái", max_length=20, choices=Status.choices, default=Status.UNPAID)
    payment_method = models.CharField("Phương thức thanh toán", max_length=20, blank=True, default="CASH")
    created_at = models.DateTimeField("Thời gian tạo", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField("Thời gian chốt", null=True, blank=True)

    @property
    def paid_at(self):
        return self.closed_at

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "hóa đơn"
        verbose_name_plural = "hóa đơn"

    @property
    def remaining(self):
        return self.total - self.paid_amount

    def __str__(self):
        return self.invoice_code


class PaymentBatch(models.Model):
    total = models.DecimalField("Tổng tiền", max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])
    method = models.CharField("Phương thức", max_length=20, choices=[
        ("CASH", "Tiền mặt"), ("CARD", "Thẻ"), ("TRANSFER", "Chuyển khoản"), ("OTHER", "Khác"),
    ], default="CASH")
    reference = models.CharField("Ghi chú / mã giao dịch", max_length=100, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField("Người thực hiện", max_length=150, blank=True)
    created_at = models.DateTimeField("Thời gian thanh toán", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "lần thanh toán nhiều bàn"
        verbose_name_plural = "các lần thanh toán nhiều bàn"

    @property
    def batch_code(self):
        return f"TT{self.pk:06d}" if self.pk else ""

    def __str__(self):
        return self.batch_code


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Tiền mặt"
        CARD = "CARD", "Thẻ"
        BANK_TRANSFER = "BANK_TRANSFER", "Chuyển khoản"
        VNPAY = "VNPAY", "VNPAY"
        OTHER = "OTHER", "Khác"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    batch = models.ForeignKey(PaymentBatch, on_delete=models.PROTECT, related_name="payments", null=True, blank=True)
    amount = models.DecimalField("Số tiền", max_digits=12, decimal_places=0, validators=[MinValueValidator(1), MaxValueValidator(999999999999)])
    method = models.CharField("Phương thức", max_length=20, choices=Method.choices, default=Method.CASH)
    reference = models.CharField("Ghi chú / mã giao dịch", max_length=100, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField("Người thực hiện", max_length=150, blank=True)
    created_at = models.DateTimeField("Thời gian thanh toán", auto_now_add=True)

    @property
    def transaction_code(self):
        return self.reference

    @property
    def paid_by(self):
        return self.performed_by

    @property
    def paid_at(self):
        return self.created_at

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "phiếu thu"
        verbose_name_plural = "phiếu thu"

    def __str__(self):
        return f"{self.amount} {self.method}"


class OnlinePayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Đang chờ"
        PAID = "PAID", "Thành công"
        FAILED = "FAILED", "Thất bại"
        CANCELLED = "CANCELLED", "Đã hủy"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="online_payments")
    txn_ref = models.CharField("Mã tham chiếu", max_length=100, unique=True)
    amount = models.DecimalField("Số tiền", max_digits=12, decimal_places=0, validators=[MinValueValidator(1)])
    subtotal = models.DecimalField("Tạm tính", max_digits=12, decimal_places=0)
    discount_percent = models.DecimalField("Phần trăm giảm", max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField("Tiền giảm", max_digits=12, decimal_places=0, default=0)
    membership_discount_amount = models.DecimalField("Ưu đãi hạng", max_digits=12, decimal_places=0, default=0)
    promotion_code = models.CharField("Mã giảm giá", max_length=30, blank=True)
    promotion_discount_amount = models.DecimalField("Giảm theo mã", max_digits=12, decimal_places=0, default=0)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider_transaction_no = models.CharField("Mã giao dịch VNPAY", max_length=30, blank=True)
    bank_code = models.CharField("Ngân hàng", max_length=30, blank=True)
    response_code = models.CharField("Mã phản hồi", max_length=10, blank=True)
    raw_response = models.JSONField("Phản hồi cổng thanh toán", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "giao dịch trực tuyến"
        verbose_name_plural = "giao dịch trực tuyến"

    def __str__(self):
        return f"{self.txn_ref} — {self.get_status_display()}"


class OrderActivityLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="activity_logs")
    action = models.CharField("Thao tác", max_length=100)
    description = models.TextField("Nội dung")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField("Người thực hiện", max_length=150)
    created_at = models.DateTimeField("Thời gian", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "nhật ký đơn hàng"
        verbose_name_plural = "nhật ký đơn hàng"


class PaymentRequest(models.Model):
    class Status(models.TextChoices):
        WAITING = "WAITING", "Đang chờ"
        PROCESSING = "PROCESSING", "Đang xử lý"
        COMPLETED = "COMPLETED", "Hoàn tất"
        CANCELLED = "CANCELLED", "Đã hủy"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payment_requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="payment_requests")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING, db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, max_length=500)

    class Meta:
        ordering = ("-requested_at", "-pk")
        constraints = [
            models.UniqueConstraint(fields=("order",), condition=models.Q(status__in=("WAITING", "PROCESSING")), name="one_active_payment_request_per_order"),
        ]


def default_qr_check_in_expiry():
    return timezone.now() + timedelta(minutes=15)


class QRCheckInRequest(models.Model):
    class Status(models.TextChoices):
        WAITING_CONFIRMATION = "WAITING_CONFIRMATION", "Chờ nhân viên nhận bàn"
        CONFIRMED = "CONFIRMED", "Đã nhận bàn"
        REJECTED = "REJECTED", "Đã từ chối"
        EXPIRED = "EXPIRED", "Đã hết hạn"

    table = models.ForeignKey("seating.DiningTable", on_delete=models.PROTECT, related_name="qr_check_in_requests")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="qr_check_in_requests")
    guest_count = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.WAITING_CONFIRMATION, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_qr_check_in_expiry, db_index=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="confirmed_qr_check_in_requests")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejected_qr_check_in_requests")
    rejected_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "yêu cầu nhận bàn QR"
        verbose_name_plural = "yêu cầu nhận bàn QR"
        constraints = [
            models.CheckConstraint(condition=models.Q(guest_count__gte=1, guest_count__lte=100), name="qr_check_in_guest_count_range"),
            models.CheckConstraint(
                condition=models.Q(status__in=("WAITING_CONFIRMATION", "CONFIRMED", "REJECTED", "EXPIRED")),
                name="qr_check_in_valid_status",
            ),
            models.UniqueConstraint(
                fields=("table",),
                condition=models.Q(status="WAITING_CONFIRMATION"),
                name="one_waiting_qr_check_in_per_table",
            ),
        ]

    def __str__(self):
        return f"NBQR-{self.pk:06d}" if self.pk else "NBQR"


class QROrderRequest(models.Model):
    class Status(models.TextChoices):
        WAITING_CONFIRMATION = "WAITING_CONFIRMATION", "Chờ nhân viên xác nhận"
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        REJECTED = "REJECTED", "Đã từ chối"
        CANCELLED = "CANCELLED", "Đã hủy"

    table = models.ForeignKey("seating.DiningTable", on_delete=models.PROTECT, related_name="qr_order_requests")
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="qr_order_requests")
    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="qr_order_requests")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.WAITING_CONFIRMATION, db_index=True)
    note = models.TextField(blank=True, max_length=500)
    client_request_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="confirmed_qr_order_requests")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejected_qr_order_requests")
    rejected_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "yêu cầu gọi món QR"
        verbose_name_plural = "yêu cầu gọi món QR"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=("WAITING_CONFIRMATION", "CONFIRMED", "REJECTED", "CANCELLED")),
                name="qr_request_valid_status",
            ),
        ]

    def __str__(self):
        return f"QR-{self.pk:06d}"


class QRServiceRequest(models.Model):
    class RequestType(models.TextChoices):
        STAFF = "STAFF", "Gọi nhân viên"
        WATER = "WATER", "Xin thêm nước"
        ICE = "ICE", "Xin thêm đá"
        BOWLS = "BOWLS", "Xin thêm chén"
        OTHER = "OTHER", "Yêu cầu khác"

    class Status(models.TextChoices):
        WAITING = "WAITING", "Đang chờ nhân viên"
        COMPLETED = "COMPLETED", "Đã xử lý"
        CANCELLED = "CANCELLED", "Đã hủy"

    table = models.ForeignKey(
        "seating.DiningTable", on_delete=models.PROTECT, related_name="qr_service_requests"
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="qr_service_requests")
    request_type = models.CharField(max_length=12, choices=RequestType.choices)
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING, db_index=True)
    client_request_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_qr_service_requests",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = "yêu cầu phục vụ QR"
        verbose_name_plural = "yêu cầu phục vụ QR"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(request_type__in=("STAFF", "WATER", "ICE", "BOWLS", "OTHER")),
                name="qr_service_request_valid_type",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=("WAITING", "COMPLETED", "CANCELLED")),
                name="qr_service_request_valid_status",
            ),
            models.UniqueConstraint(
                fields=("table", "request_type"),
                condition=models.Q(status="WAITING"),
                name="one_waiting_qr_service_per_table_type",
            ),
        ]

    def __str__(self):
        return f"PVQR-{self.pk:06d}" if self.pk else "PVQR"


class QROrderRequestItem(models.Model):
    request = models.ForeignKey(QROrderRequest, on_delete=models.CASCADE, related_name="items")
    order_item = models.OneToOneField("OrderItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="qr_request_item")
    dish = models.ForeignKey("menu.Dish", on_delete=models.PROTECT, related_name="qr_order_request_items")
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    note = models.TextField(blank=True, max_length=500)
    unit_price_snapshot = models.DecimalField(max_digits=9, decimal_places=0, validators=[MinValueValidator(1), MaxValueValidator(999999999)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = "món trong yêu cầu QR"
        verbose_name_plural = "món trong yêu cầu QR"
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=100), name="qr_request_item_quantity_range"),
            models.CheckConstraint(condition=models.Q(unit_price_snapshot__gte=1), name="qr_request_item_price_positive"),
        ]
