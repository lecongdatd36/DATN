from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.urls import reverse


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ xác nhận"
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        SEATED = "SEATED", "Đang phục vụ"
        COMPLETED = "COMPLETED", "Hoàn tất"
        CANCELLED = "CANCELLED", "Đã hủy"
        NO_SHOW = "NO_SHOW", "Không đến"

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="bookings", verbose_name="Khách hàng", null=True, blank=True)
    is_walk_in = models.BooleanField("Khách không đặt trước", default=False, editable=False)
    table = models.ForeignKey("seating.DiningTable", on_delete=models.PROTECT, related_name="bookings", verbose_name="Bàn")
    customer_name = models.CharField("Tên khách khi đặt", max_length=150)
    customer_phone = models.CharField("Điện thoại khi đặt", max_length=20, blank=True)
    party_size = models.PositiveSmallIntegerField("Số khách", validators=[MinValueValidator(1), MaxValueValidator(100)])
    starts_at = models.DateTimeField("Giờ đến")
    ends_at = models.DateTimeField("Giờ kết thúc dự kiến")
    seated_at = models.DateTimeField("Giờ nhận khách thực tế", null=True, blank=True, editable=False)
    completed_at = models.DateTimeField("Giờ khách rời bàn", null=True, blank=True, editable=False)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.PENDING)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "đặt bàn"
        verbose_name_plural = "đặt bàn"
        ordering = ("-starts_at", "-pk")
        permissions = [("manage_booking", "Tạo và cập nhật đặt bàn")]
        constraints = [
            models.CheckConstraint(condition=models.Q(is_walk_in=True) | models.Q(customer__isnull=False), name="booking_reserved_customer_required"),
            models.CheckConstraint(condition=models.Q(is_walk_in=False) | models.Q(status__in=["SEATED", "COMPLETED"]), name="booking_walk_in_status"),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="booking_time_order"),
            models.CheckConstraint(condition=models.Q(party_size__gte=1, party_size__lte=100), name="booking_party_range"),
            models.CheckConstraint(condition=models.Q(status__in=["PENDING", "CONFIRMED", "SEATED", "COMPLETED", "CANCELLED", "NO_SHOW"]), name="booking_valid_status"),
            models.CheckConstraint(condition=models.Q(completed_at__isnull=True) | models.Q(seated_at__isnull=True) | models.Q(completed_at__gte=models.F("seated_at")), name="booking_actual_time_order"),
        ]
        indexes = [models.Index(fields=("table", "status", "starts_at", "ends_at"), name="booking_slot_idx")]

    @property
    def booking_code(self):
        return f"{'LK' if self.is_walk_in else 'DB'}{self.pk:06d}" if self.pk else ""

    @property
    def duration_minutes(self):
        return int((self.ends_at - self.starts_at).total_seconds() // 60)

    @property
    def can_edit(self):
        return self.status in (self.Status.PENDING, self.Status.CONFIRMED)

    def get_absolute_url(self):
        return reverse("bookings:detail", args=[self.pk])

    def __str__(self):
        return f"{self.booking_code} — {self.customer_name}"


class BookingActivityLog(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="activity_logs")
    action = models.CharField("Thao tác", max_length=100)
    description = models.TextField("Nội dung")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField("Người thực hiện", max_length=150)
    created_at = models.DateTimeField("Thời gian", auto_now_add=True)

    class Meta:
        verbose_name = "nhật ký đặt bàn"
        verbose_name_plural = "nhật ký đặt bàn"
        ordering = ("-created_at", "-pk")


class BookingSettings(models.Model):
    default_duration_minutes = models.PositiveSmallIntegerField(
        "Thời lượng mặc định (phút)", default=120, validators=[MinValueValidator(1), MaxValueValidator(1440)],
    )
    revision = models.PositiveIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cấu hình đặt bàn"
        verbose_name_plural = "cấu hình đặt bàn"
        permissions = [("configure_bookings", "Cấu hình thời lượng đặt bàn")]
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="booking_settings_singleton"),
            models.CheckConstraint(condition=models.Q(default_duration_minutes__gte=1, default_duration_minutes__lte=1440), name="booking_default_duration_range"),
        ]


class BookingSettingsLog(models.Model):
    previous_minutes = models.PositiveSmallIntegerField()
    new_minutes = models.PositiveSmallIntegerField()
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
