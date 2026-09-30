from django import forms

from apps.accounts.forms import BootstrapFormMixin
from .models import Customer, CustomerActivityLog, MembershipTier
from .validators import normalize_phone


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    phone = forms.CharField(
        label="Số điện thoại", max_length=32,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "placeholder": "Ví dụ: 0912345678"}),
    )

    class Meta:
        model = Customer
        fields = ("full_name", "phone")
        labels = {"full_name": "Họ tên"}
        widgets = {"full_name": forms.TextInput(attrs={"autocomplete": "name"})}

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        existing = Customer.objects.filter(phone=phone)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("Số điện thoại đã có hồ sơ khách hàng. Hãy tìm khách theo số điện thoại.")
        return phone


class CustomerFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        label="Tìm khách hàng", required=False, max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Mã khách, họ tên hoặc số điện thoại"}),
    )


class CustomerLogFilterForm(CustomerFilterForm):
    action = forms.ChoiceField(label="Hành động", required=False, choices=[("", "Tất cả hành động"), *CustomerActivityLog.Action.choices])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["q"].widget.attrs["placeholder"] = "Mã khách, tên khách hoặc người thực hiện"


class MembershipTierForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MembershipTier
        fields = ("name", "minimum_spending", "discount_percent", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ví dụ: Vàng"}),
            "minimum_spending": forms.NumberInput(attrs={"min": 0, "step": 1000}),
            "discount_percent": forms.NumberInput(attrs={"min": 0, "max": 100, "step": "0.01"}),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())
