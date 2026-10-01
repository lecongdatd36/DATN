from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower


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
        constraints = [
            models.UniqueConstraint(Lower("name"), name="inventory_supplier_name_unique"),
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="inventory_supplier_name_not_blank"),
        ]

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    code = models.CharField(
        "Mã nguyên liệu", max_length=20, unique=True,
        validators=[RegexValidator(r"\A[A-Z0-9][A-Z0-9_-]{0,19}\Z", "Mã chỉ gồm chữ A–Z, số, gạch ngang hoặc gạch dưới.")],
    )
    name = models.CharField("Tên nguyên liệu", max_length=150)
    unit = models.CharField("Đơn vị tính", max_length=30)
    stock_quantity = models.DecimalField("Tồn kho", max_digits=14, decimal_places=3, default=0)
    average_unit_cost = models.DecimalField(
        "Giá vốn bình quân", max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
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
            models.CheckConstraint(condition=models.Q(average_unit_cost__gte=0), name="inventory_average_cost_nonnegative"),
            models.CheckConstraint(condition=models.Q(low_stock_threshold__gte=0), name="inventory_threshold_nonnegative"),
            models.CheckConstraint(condition=models.Q(code__regex=r"^[A-Z0-9][A-Z0-9_-]{0,19}$"), name="inventory_ingredient_code_canonical"),
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="inventory_ingredient_name_not_blank"),
            models.CheckConstraint(condition=models.Q(unit__regex=r"\S"), name="inventory_ingredient_unit_not_blank"),
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
        SALE_USAGE = "SALE_USAGE", "Xuất theo món bán"
        SALE_RETURN = "SALE_RETURN", "Hoàn do hủy món"
        PURCHASE = "PURCHASE", "Nhận hàng"
        STOCKTAKE = "STOCKTAKE", "Chênh lệch kiểm kê"
        WASTE = "WASTE", "Hao hụt / hư hỏng"

    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="transactions")
    transaction_type = models.CharField("Loại giao dịch", max_length=16, choices=Type.choices)
    quantity = models.DecimalField("Số lượng", max_digits=14, decimal_places=3)
    stock_before = models.DecimalField("Tồn trước", max_digits=14, decimal_places=3)
    stock_after = models.DecimalField("Tồn sau", max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField("Đơn giá", max_digits=14, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    note = models.TextField("Ghi chú", blank=True, max_length=500)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    order_item_reference = models.PositiveBigIntegerField("Mã dòng món liên quan", null=True, blank=True, db_index=True)
    source_type = models.CharField("Loại chứng từ", max_length=20, blank=True, db_index=True)
    source_id = models.PositiveBigIntegerField("Mã chứng từ", null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "giao dịch kho"
        verbose_name_plural = "giao dịch kho"

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.ingredient}"


class RecipeIngredient(models.Model):
    dish = models.ForeignKey("menu.Dish", on_delete=models.CASCADE, related_name="recipe_ingredients", verbose_name="Món")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="recipe_lines", verbose_name="Nguyên liệu")
    quantity = models.DecimalField(
        "Định lượng cho một món", max_digits=14, decimal_places=3,
        validators=[MinValueValidator(0.001)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ingredient__name", "pk")
        verbose_name = "định lượng món"
        verbose_name_plural = "định lượng món"
        constraints = [
            models.UniqueConstraint(fields=("dish", "ingredient"), name="inventory_recipe_dish_ingredient_unique"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="inventory_recipe_quantity_positive"),
        ]

    @property
    def estimated_cost(self):
        return self.quantity * self.ingredient.average_unit_cost

    def __str__(self):
        return f"{self.dish} · {self.quantity} {self.ingredient.unit} {self.ingredient.name}"


class PurchaseReceipt(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Nháp"
        RECEIVED = "RECEIVED", "Đã nhận hàng"
        CANCELLED = "CANCELLED", "Đã hủy"

    receipt_code = models.CharField("Mã phiếu nhập", max_length=20, unique=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_receipts", verbose_name="Nhà cung cấp")
    invoice_number = models.CharField("Số hóa đơn nhà cung cấp", max_length=100, blank=True)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    note = models.TextField("Ghi chú", max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_purchase_receipts")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="confirmed_purchase_receipts")
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "phiếu nhập hàng"
        verbose_name_plural = "phiếu nhập hàng"

    @property
    def total(self):
        return sum((line.subtotal for line in self.lines.all()), 0)

    def __str__(self):
        return self.receipt_code or "Phiếu nhập chưa lưu"


class PurchaseReceiptLine(models.Model):
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="purchase_lines")
    quantity = models.DecimalField("Số lượng", max_digits=14, decimal_places=3, validators=[MinValueValidator(0.001)])
    unit_cost = models.DecimalField("Đơn giá", max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ("pk",)
        constraints = [
            models.UniqueConstraint(fields=("receipt", "ingredient"), name="inventory_purchase_line_unique"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="inventory_purchase_quantity_positive"),
            models.CheckConstraint(condition=models.Q(unit_cost__gt=0), name="inventory_purchase_cost_positive"),
        ]

    @property
    def subtotal(self):
        return self.quantity * self.unit_cost


class Stocktake(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Đang kiểm"
        POSTED = "POSTED", "Đã chốt"
        CANCELLED = "CANCELLED", "Đã hủy"

    stocktake_code = models.CharField("Mã kiểm kê", max_length=20, unique=True, blank=True)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    note = models.TextField("Ghi chú", max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_stocktakes")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="posted_stocktakes")
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.stocktake_code or "Phiếu kiểm kê chưa lưu"


class StocktakeLine(models.Model):
    stocktake = models.ForeignKey(Stocktake, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="stocktake_lines")
    system_quantity = models.DecimalField("Tồn hệ thống khi chốt", max_digits=14, decimal_places=3, default=0)
    actual_quantity = models.DecimalField("Tồn thực tế", max_digits=14, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ("ingredient__name", "pk")
        constraints = [models.UniqueConstraint(fields=("stocktake", "ingredient"), name="inventory_stocktake_line_unique")]

    @property
    def difference(self):
        return None if self.actual_quantity is None else self.actual_quantity - self.system_quantity


class WasteRecord(models.Model):
    class Reason(models.TextChoices):
        SPOILED = "SPOILED", "Hư hỏng"
        EXPIRED = "EXPIRED", "Hết hạn"
        PREPARATION = "PREPARATION", "Hao hụt sơ chế"
        BREAKAGE = "BREAKAGE", "Đổ vỡ"
        STAFF = "STAFF", "Nhân viên sử dụng"
        OTHER = "OTHER", "Khác"

    waste_code = models.CharField("Mã hao hụt", max_length=20, unique=True, blank=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="waste_records")
    quantity = models.DecimalField("Số lượng", max_digits=14, decimal_places=3, validators=[MinValueValidator(0.001)])
    reason = models.CharField("Nguyên nhân", max_length=20, choices=Reason.choices)
    unit_cost_snapshot = models.DecimalField("Đơn giá vốn", max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_cost = models.DecimalField("Giá trị hao hụt", max_digits=14, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    note = models.TextField("Ghi chú", max_length=500, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="waste_records")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.waste_code or "Hao hụt chưa lưu"
