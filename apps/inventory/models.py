from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Supplier(models.Model):
    name = models.CharField("Tên nhà cung cấp", max_length=150)
    phone = models.CharField("Số điện thoại", max_length=20, blank=True)
    address = models.CharField("Địa chỉ", max_length=255, blank=True)
    is_active = models.BooleanField("Đang hợp tác", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "nhà cung cấp"
        verbose_name_plural = "nhà cung cấp"

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    code = models.CharField("Mã nguyên liệu", max_length=20, unique=True)
    name = models.CharField("Tên nguyên liệu", max_length=150)
    unit = models.CharField("Đơn vị tính", max_length=30)
    stock_quantity = models.DecimalField("Tồn kho", max_digits=14, decimal_places=3, default=0)
    low_stock_threshold = models.DecimalField("Ngưỡng sắp hết", max_digits=14, decimal_places=3, default=0)
    is_active = models.BooleanField("Đang sử dụng", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "nguyên liệu"
        verbose_name_plural = "nguyên liệu"
        permissions = [("manage_inventory", "Nhập, xuất và điều chỉnh kho")]
        constraints = [
            models.CheckConstraint(condition=models.Q(stock_quantity__gte=0), name="inventory_stock_nonnegative"),
            models.CheckConstraint(condition=models.Q(low_stock_threshold__gte=0), name="inventory_threshold_nonnegative"),
        ]

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    def __str__(self):
        return f"{self.code} - {self.name}"


class InventoryTransaction(models.Model):
    class Type(models.TextChoices):
        IMPORT = "IMPORT", "Nhập kho"
        EXPORT = "EXPORT", "Xuất kho"
        ADJUSTMENT = "ADJUSTMENT", "Điều chỉnh"

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="transactions")
    transaction_type = models.CharField("Loại giao dịch", max_length=12, choices=Type.choices)
    quantity = models.DecimalField("Số lượng", max_digits=14, decimal_places=3)
    stock_before = models.DecimalField("Tồn trước", max_digits=14, decimal_places=3)
    stock_after = models.DecimalField("Tồn sau", max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField("Đơn giá", max_digits=14, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    note = models.TextField("Ghi chú", blank=True, max_length=500)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "giao dịch kho"
        verbose_name_plural = "giao dịch kho"

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.ingredient}"
