from django import forms

from apps.accounts.forms import BootstrapFormMixin
from .models import Ingredient, InventoryTransaction, Supplier


class InventoryFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(required=False, label="Tìm nguyên liệu")
    low_stock = forms.BooleanField(required=False, label="Chỉ hiện sắp hết")


class InventoryTransactionForm(BootstrapFormMixin, forms.Form):
    ingredient = forms.ModelChoiceField(queryset=Ingredient.objects.filter(is_active=True), label="Nguyên liệu")
    transaction_type = forms.ChoiceField(choices=InventoryTransaction.Type.choices, label="Loại giao dịch")
    quantity = forms.DecimalField(min_value=0.001, max_digits=14, decimal_places=3, label="Số lượng / tồn mới")
    unit_cost = forms.DecimalField(min_value=0, max_digits=14, decimal_places=0, required=False, initial=0, label="Đơn giá")
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.filter(is_active=True), required=False, label="Nhà cung cấp")
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}), label="Ghi chú")
