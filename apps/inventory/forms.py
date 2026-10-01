from django import forms

from apps.accounts.forms import BootstrapFormMixin
from .models import Ingredient, InventoryTransaction, PurchaseReceipt, PurchaseReceiptLine, RecipeIngredient, Supplier, WasteRecord


class IngredientChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, ingredient):
        return f"{ingredient.code} — {ingredient.name} · tồn {ingredient.stock_quantity} {ingredient.unit} · {ingredient.average_unit_cost:.0f} đ/{ingredient.unit}"


class InventoryFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(required=False, label="Tìm nguyên liệu")
    low_stock = forms.BooleanField(required=False, label="Chỉ hiện sắp hết")


class InventoryTransactionForm(BootstrapFormMixin, forms.Form):
    ingredient = forms.ModelChoiceField(queryset=Ingredient.objects.filter(is_active=True), label="Nguyên liệu")
    transaction_type = forms.ChoiceField(choices=[
        (InventoryTransaction.Type.IMPORT, "Nhập kho"),
        (InventoryTransaction.Type.EXPORT, "Xuất kho thủ công"),
        (InventoryTransaction.Type.ADJUSTMENT, "Điều chỉnh tồn thực tế"),
    ], label="Loại giao dịch")
    quantity = forms.DecimalField(min_value=0, max_digits=14, decimal_places=3, label="Số lượng / tồn mới")
    unit_cost = forms.DecimalField(min_value=0, max_digits=14, decimal_places=0, required=False, initial=0, label="Đơn giá")
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.filter(is_active=True), required=False, label="Nhà cung cấp")
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}), label="Ghi chú")

    def clean(self):
        cleaned = super().clean()
        transaction_type = cleaned.get("transaction_type")
        quantity = cleaned.get("quantity")
        unit_cost = cleaned.get("unit_cost") or 0
        if quantity is not None and transaction_type != InventoryTransaction.Type.ADJUSTMENT and quantity <= 0:
            self.add_error("quantity", "Số lượng nhập hoặc xuất phải lớn hơn 0.")
        if transaction_type == InventoryTransaction.Type.IMPORT and unit_cost <= 0:
            self.add_error("unit_cost", "Nhập kho phải có đơn giá lớn hơn 0 để tính đúng giá vốn.")
        return cleaned


class IngredientForm(BootstrapFormMixin, forms.ModelForm):
    COMMON_UNITS = ("kg", "g", "lít", "ml", "quả", "chai", "gói", "hộp", "lon", "phần")

    class Meta:
        model = Ingredient
        fields = ("code", "name", "unit", "low_stock_threshold", "is_active")
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "Ví dụ: NL-THIT-HEO"}),
            "unit": forms.TextInput(attrs={"list": "ingredient-unit-list", "placeholder": "kg, lít, quả..."}),
            "low_stock_threshold": forms.NumberInput(attrs={"min": "0", "step": "0.001"}),
        }
        help_texts = {
            "unit": "Đơn vị này phải trùng với định lượng dùng trong công thức món.",
            "low_stock_threshold": "Hệ thống cảnh báo sắp hết khi tồn kho nhỏ hơn hoặc bằng mức này.",
            "is_active": "Ngừng sử dụng sẽ không cho thêm nguyên liệu này vào công thức mới.",
        }

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_unit(self):
        return self.cleaned_data["unit"].strip().lower()


class SupplierForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ("name", "phone", "address", "is_active")

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


class PurchaseReceiptForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PurchaseReceipt
        fields = ("supplier", "invoice_number", "note")
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True).order_by("name")


class PurchaseReceiptLineForm(BootstrapFormMixin, forms.ModelForm):
    ingredient = IngredientChoiceField(queryset=Ingredient.objects.none(), label="Nguyên liệu")

    class Meta:
        model = PurchaseReceiptLine
        fields = ("ingredient", "quantity", "unit_cost")
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": "0.001", "step": "0.001"}),
            "unit_cost": forms.NumberInput(attrs={"min": "1", "step": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ingredient"].queryset = Ingredient.objects.filter(is_active=True).order_by("name")


class WasteRecordForm(BootstrapFormMixin, forms.ModelForm):
    ingredient = IngredientChoiceField(queryset=Ingredient.objects.none(), label="Nguyên liệu")

    class Meta:
        model = WasteRecord
        fields = ("ingredient", "quantity", "reason", "note")
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": "0.001", "step": "0.001"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ingredient"].queryset = Ingredient.objects.filter(is_active=True).order_by("name")


class RecipeIngredientForm(BootstrapFormMixin, forms.ModelForm):
    ingredient = IngredientChoiceField(queryset=Ingredient.objects.none(), label="Nguyên liệu")

    class Meta:
        model = RecipeIngredient
        fields = ("ingredient", "quantity")
        widgets = {"quantity": forms.NumberInput(attrs={"min": "0.001", "step": "0.001"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ingredient"].queryset = Ingredient.objects.filter(is_active=True).order_by("name", "pk")
        self.fields["ingredient"].help_text = "Mỗi nguyên liệu chỉ xuất hiện một lần trong công thức."
        self.fields["quantity"].help_text = "Định lượng cho 1 món, theo đúng đơn vị kho của nguyên liệu."
