from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, MaxLengthValidator
from django.db import models
from django.urls import reverse


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
    order_code = models.CharField("Mã đơn", max_length=20, unique=True, null=True, blank=True)
    guest_count = models.PositiveSmallIntegerField("Số khách", default=1, validators=[MinValueValidator(1), MaxValueValidator(100)])
    status = models.CharField("Trạng thái", max_length=20, choices=Status.choices, default=Status.OPEN)
    subtotal = models.DecimalField("Tạm tính", max_digits=14, decimal_places=0, default=0)
    discount_amount = models.DecimalField("Giảm giá", max_digits=14, decimal_places=0, default=0)
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
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["OPEN", "IN_PROGRESS", "PAYMENT_REQUESTED", "COMPLETED", "CANCELLED"]), name="order_valid_status")]

    @property
    def reservation(self):
        return self.booking

    @property
    def total(self):
        return sum((item.subtotal for item in self.items.all() if item.status != OrderItem.Status.CANCELLED), Decimal(0))

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.pk])

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
    total_price = models.DecimalField("Thành tiền", max_digits=12, decimal_places=0, default=0)
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
            models.CheckConstraint(condition=models.Q(unit_price__gte=1, unit_price__lte=999999999), name="order_item_price_range"),
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
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = tuple(set(update_fields) | {"total_price", "updated_at"})
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
