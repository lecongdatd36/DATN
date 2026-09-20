from django import forms
from django.db.models import Q

from apps.accounts.forms import BootstrapFormMixin
from .models import Area, DiningTable


class AreaForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].widget.attrs["class"] = "form-check-input ms-2"

    class Meta:
        model = Area
        fields = ("name", "is_active")
        help_texts = {"is_active": "Khi ngừng khu vực, tất cả bàn thuộc khu vực tạm thời không sử dụng được. Mở lại khu vực sẽ cho phép dùng các bàn còn được bật."}

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


class DiningTableForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DiningTable
        fields = ("code", "area", "capacity", "is_active")
        widgets = {"capacity": forms.NumberInput(attrs={"min": 1, "max": 100})}
        help_texts = {"code": "Mã bàn duy nhất trong nhà hàng, ví dụ B01 hoặc T2-B01.", "is_active": "Bỏ chọn khi bàn cần bảo trì hoặc ngừng sử dụng."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].widget.attrs["class"] = "form-check-input ms-2"
        self.fields["area"].queryset = Area.objects.filter(Q(is_active=True) | Q(pk=self.instance.area_id))

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class AreaFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Tìm khu vực", required=False, max_length=100)
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Tất cả trạng thái"), ("active", "Đang sử dụng"), ("inactive", "Ngừng sử dụng")])


class TableFilterForm(AreaFilterForm):
    q = forms.CharField(label="Tìm mã bàn / khu vực", required=False, max_length=100)
    area = forms.ModelChoiceField(label="Khu vực", queryset=Area.objects.all(), required=False, empty_label="Tất cả khu vực")
    status = forms.ChoiceField(label="Trạng thái bàn", required=False, choices=[
        ("", "Tất cả trạng thái"), ("empty", "Trống hiện tại"),
        ("occupied", "Đang phục vụ"), ("reserved", "Đang giữ chỗ"),
        ("inactive", "Ngừng sử dụng"), ("active", "Đang mở (mọi trạng thái)"),
    ])
