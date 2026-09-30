from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower


class Area(models.Model):
    name = models.CharField("Tên khu vực", max_length=100)
    is_active = models.BooleanField("Đang sử dụng", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "khu vực"
        verbose_name_plural = "khu vực"
        ordering = ("name", "pk")
        constraints = [
            models.UniqueConstraint(Lower("name"), name="seating_area_name_unique", violation_error_message="Tên khu vực đã tồn tại."),
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="seating_area_name_not_blank"),
        ]

    def __str__(self):
        return self.name


class DiningTable(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Trống"
        RESERVED = "RESERVED", "Đã đặt"
        OCCUPIED = "OCCUPIED", "Đang phục vụ"
        CLEANING = "CLEANING", "Cần dọn"

    code = models.CharField(
        "Mã bàn", max_length=20, unique=True,
        validators=[RegexValidator(r"\A[A-Z0-9][A-Z0-9_-]{0,19}\Z", "Mã bàn chỉ gồm chữ A–Z, số, dấu gạch ngang hoặc gạch dưới; bắt đầu bằng chữ hoặc số.")],
        error_messages={"unique": "Mã bàn đã tồn tại."},
    )
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="tables", verbose_name="Khu vực")
    name = models.CharField("Tên bàn", max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField("Số chỗ ngồi", validators=[MinValueValidator(1), MaxValueValidator(100)])
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    is_active = models.BooleanField("Đang sử dụng", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "bàn"
        verbose_name_plural = "bàn"
        ordering = ("area__name", "code", "pk")
        permissions = [("manage_seating", "Quản lý khu vực và bàn")]
        constraints = [
            models.CheckConstraint(condition=models.Q(capacity__gte=1, capacity__lte=100), name="seating_capacity_range"),
            models.CheckConstraint(condition=models.Q(code__regex=r"^[A-Z0-9][A-Z0-9_-]{0,19}$"), name="seating_code_canonical"),
            models.CheckConstraint(condition=models.Q(status__in=["AVAILABLE", "RESERVED", "OCCUPIED", "CLEANING"]), name="seating_table_valid_status"),
        ]

    @property
    def table_code(self):
        return self.code

    @property
    def is_available(self):
        """Bàn còn được cấu hình sử dụng; trạng thái vận hành kiểm tra riêng."""
        return self.is_active and self.area.is_active

    def __str__(self):
        return self.code


class SeatingActivityLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Thêm mới"
        UPDATE = "UPDATE", "Cập nhật"

    class Entity(models.TextChoices):
        AREA = "AREA", "Khu vực"
        TABLE = "TABLE", "Bàn"

    entity = models.CharField("Loại", max_length=10, choices=Entity.choices)
    object_id = models.PositiveBigIntegerField("ID đối tượng")
    label_snapshot = models.CharField("Tên / mã tại thời điểm thao tác", max_length=100)
    action = models.CharField("Hành động", max_length=10, choices=Action.choices)
    description = models.TextField("Nội dung")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField("Người thực hiện", max_length=150)
    created_at = models.DateTimeField("Thời gian", auto_now_add=True)

    class Meta:
        verbose_name = "nhật ký khu vực và bàn"
        verbose_name_plural = "nhật ký khu vực và bàn"
        ordering = ("-created_at", "-pk")
