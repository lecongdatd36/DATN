from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, MaxLengthValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from .images import validate_upload_size


class CatalogEntry(models.Model):
    name = models.CharField("Tên", max_length=100)
    is_active = models.BooleanField("Đang sử dụng", default=True)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("name", "pk")
        constraints = [
            models.UniqueConstraint(Lower("name"), name="menu_%(class)s_name_unique", violation_error_message="Tên đã tồn tại."),
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="menu_%(class)s_name_not_blank"),
        ]

    def __str__(self):
        return self.name


class Category(CatalogEntry):
    class Meta(CatalogEntry.Meta):
        abstract = False
        verbose_name = "nhóm món"
        verbose_name_plural = "nhóm món"


class Unit(CatalogEntry):
    class Meta(CatalogEntry.Meta):
        abstract = False
        verbose_name = "đơn vị tính"
        verbose_name_plural = "đơn vị tính"


class Dish(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Còn món"
        SOLD_OUT = "SOLD_OUT", "Hết món"
        INACTIVE = "INACTIVE", "Ngừng bán"

    code = models.CharField("Mã món", max_length=20, unique=True,
        validators=[RegexValidator(r"\A[A-Z0-9][A-Z0-9_-]{0,19}\Z", "Mã món chỉ gồm chữ A–Z, số, gạch ngang hoặc gạch dưới; bắt đầu bằng chữ hoặc số.")],
        error_messages={"unique": "Mã món đã tồn tại."})
    name = models.CharField("Tên món", max_length=150)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="dishes", verbose_name="Nhóm món")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="dishes", verbose_name="Đơn vị tính")
    price = models.DecimalField("Giá bán (đồng)", max_digits=9, decimal_places=0, validators=[MinValueValidator(1), MaxValueValidator(999999999)])
    description = models.TextField("Mô tả", blank=True, max_length=2000, validators=[MaxLengthValidator(2000)])
    tracks_inventory = models.BooleanField(
        "Quản lý tồn kho theo công thức",
        default=False,
        help_text="Bật để bắt buộc món có ít nhất một nguyên liệu trước khi gửi xuống Bếp.",
    )
    image = models.ImageField("Ảnh món", upload_to="dishes/", blank=True, validators=[validate_upload_size])
    thumbnail = models.ImageField(upload_to="dishes/", blank=True, editable=False)
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    revision = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "món"
        verbose_name_plural = "món"
        ordering = ("category__name", "name", "pk")
        permissions = [("manage_menu", "Quản lý thực đơn và giá bán"), ("change_availability", "Cập nhật còn món / hết món")]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=1, price__lte=999999999), name="menu_dish_price_range"),
            models.CheckConstraint(condition=models.Q(code__regex=r"^[A-Z0-9][A-Z0-9_-]{0,19}$"), name="menu_dish_code_canonical"),
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="menu_dish_name_not_blank"),
            models.CheckConstraint(condition=models.Q(status__in=["AVAILABLE", "SOLD_OUT", "INACTIVE"]), name="menu_dish_valid_status"),
        ]

    @property
    def is_orderable(self):
        return self.status == self.Status.AVAILABLE and self.category.is_active and self.unit.is_active

    @property
    def availability_label(self):
        if self.status == self.Status.INACTIVE:
            return "Ngừng bán"
        if not self.category.is_active or not self.unit.is_active:
            return "Tạm ngừng theo danh mục"
        return self.get_status_display()

    @property
    def can_toggle_availability(self):
        return self.status != self.Status.INACTIVE and self.category.is_active and self.unit.is_active

    def get_absolute_url(self):
        return reverse("menu:detail", args=[self.pk])

    def __str__(self):
        return f"{self.code} — {self.name}"


class MenuActivityLog(models.Model):
    class Entity(models.TextChoices):
        CATEGORY = "CATEGORY", "Nhóm món"
        UNIT = "UNIT", "Đơn vị tính"
        DISH = "DISH", "Món"

    entity = models.CharField("Loại", max_length=10, choices=Entity.choices)
    object_id = models.PositiveBigIntegerField()
    label_snapshot = models.CharField("Tên tại thời điểm thao tác", max_length=180)
    action = models.CharField("Hành động", max_length=40)
    description = models.TextField("Nội dung")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_snapshot = models.CharField("Người thực hiện", max_length=150)
    created_at = models.DateTimeField("Thời gian", auto_now_add=True)

    class Meta:
        verbose_name = "nhật ký thực đơn"
        verbose_name_plural = "nhật ký thực đơn"
        ordering = ("-created_at", "-pk")
