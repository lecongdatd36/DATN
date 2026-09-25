from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, MaxLengthValidator
from django.db import models
from django.urls import reverse


class Order(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Đang phục vụ"
        AWAITING_PAYMENT = "AWAITING_PAYMENT", "Chờ thanh toán"
        VOID = "VOID", "Đã hủy"

    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, related_name="order", verbose_name="Lượt khách")
    status = models.CharField("Trạng thái", max_length=20, choices=Status.choices, default=Status.OPEN)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField("Mở lúc", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "đơn hàng"
        verbose_name_plural = "đơn hàng"
        permissions = [("manage_order", "Mở đơn và gọi món"), ("work_kitchen", "Xử lý món tại Bếp"), ("cancel_prepared_item", "Hủy món đã bắt đầu làm")]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["OPEN", "AWAITING_PAYMENT", "VOID"]), name="order_valid_status")]

    @property
    def order_code(self):
        return f"DH{self.pk:06d}" if self.pk else ""

    @property
    def total(self):
        return sum((item.subtotal for item in self.items.all() if item.status != OrderItem.Status.CANCELLED), Decimal(0))

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.pk])

    def __str__(self):
        return self.order_code


class OrderItem(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Chưa gửi Bếp"
        SENT = "SENT", "Đã gửi Bếp"
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
    note = models.TextField("Ghi chú cho Bếp", blank=True, max_length=500, validators=[MaxLengthValidator(500)])
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.DRAFT)
    cancellation_reason = models.CharField("Lý do hủy", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "pk")
        verbose_name = "món trong đơn"
        verbose_name_plural = "món trong đơn"
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=100), name="order_item_quantity_range"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=1, unit_price__lte=999999999), name="order_item_price_range"),
            models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "SENT", "COOKING", "READY", "SERVED", "CANCELLED"]), name="order_item_valid_status"),
            models.CheckConstraint(condition=~models.Q(status="CANCELLED") | models.Q(cancellation_reason__regex=r"\S", cancelled_at__isnull=False), name="order_item_cancel_reason"),
        ]
        indexes = [models.Index(fields=("status", "sent_at"), name="order_kitchen_queue_idx")]

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.dish_name} × {self.quantity}"


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
