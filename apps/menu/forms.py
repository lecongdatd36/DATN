from django import forms
from django.db.models import Q
from apps.accounts.forms import BootstrapFormMixin
from .models import Category, Unit, Dish
from .images import validate_upload_size


class RevisionForm(BootstrapFormMixin, forms.ModelForm):
    expected_revision = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["expected_revision"].required = True
            self.initial["expected_revision"] = self.instance.revision
        if "is_active" in self.fields:
            self.fields["is_active"].widget.attrs["class"] = "form-check-input ms-2"

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


class CategoryForm(RevisionForm):
    class Meta:
        model = Category
        fields = ("name", "is_active")
        labels = {"name": "Tên nhóm món"}
        help_texts = {"is_active": "Ngừng nhóm sẽ tạm ngừng phục vụ tất cả món thuộc nhóm. Mở lại giữ nguyên trạng thái riêng của từng món."}


class UnitForm(RevisionForm):
    class Meta:
        model = Unit
        fields = ("name", "is_active")
        labels = {"name": "Tên đơn vị tính"}
        help_texts = {"name": "Ví dụ: Phần, Đĩa, Ly, Chai.", "is_active": "Ngừng đơn vị sẽ tạm ngừng phục vụ các món dùng đơn vị này."}


class DishForm(RevisionForm):
    image = forms.FileField(label="Ảnh món", required=False, validators=[validate_upload_size],
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "data-dish-upload": ""}),
        help_text="JPEG, PNG hoặc WebP; tối đa 5 MB, 20 triệu điểm ảnh. Ảnh được tự thu nhỏ. Bỏ trống để giữ ảnh hiện tại, chọn Xóa để gỡ ảnh.")

    class Meta:
        model = Dish
        fields = ("code", "name", "category", "unit", "price", "status", "description", "image")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "price": forms.NumberInput(attrs={"min": 1, "max": 999999999, "step": 1})}
        help_texts = {"price": "Nhập số nguyên đồng, ví dụ 85000. Giá bán lớn hơn 0.", "code": "Mã duy nhất, ví dụ M001. Chữ thường được đổi thành chữ hoa.", "status": "Hết món: tạm hết, có thể mở lại. Ngừng bán: chỉ Quản lí được mở lại."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field, model in (("category", Category), ("unit", Unit)):
            self.fields[field].queryset = model.objects.filter(Q(is_active=True) | Q(pk=getattr(self.instance, f"{field}_id")))

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class AvailabilityForm(BootstrapFormMixin, forms.Form):
    status = forms.ChoiceField(label="Trạng thái phục vụ", choices=[(Dish.Status.AVAILABLE, "Còn món"), (Dish.Status.SOLD_OUT, "Hết món")])
    expected_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class CatalogFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Tìm tên", required=False, max_length=100)
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Tất cả"), ("active", "Đang sử dụng"), ("inactive", "Ngừng sử dụng")])


class DishFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Mã / tên món", required=False, max_length=150)
    category = forms.ModelChoiceField(label="Nhóm món", queryset=Category.objects.all(), required=False, empty_label="Tất cả nhóm")
    unit = forms.ModelChoiceField(label="Đơn vị tính", queryset=Unit.objects.all(), required=False, empty_label="Tất cả đơn vị")
    status = forms.ChoiceField(label="Trạng thái phục vụ", required=False, choices=[("", "Tất cả"), *Dish.Status.choices, ("paused", "Tạm ngừng theo danh mục")])
