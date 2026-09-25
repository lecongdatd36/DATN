from django import forms
from apps.accounts.forms import BootstrapFormMixin
from apps.bookings.models import Booking
from apps.bookings.forms import TableChoiceField
from apps.bookings.selectors import default_duration_minutes
from apps.customers.validators import normalize_phone
from apps.menu.models import Dish
from apps.seating.models import DiningTable
from .models import Order


class VisitChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.booking_code} — Bàn {obj.table.code} — {obj.customer_name}"


class OpenOrderForm(BootstrapFormMixin, forms.Form):
    booking = VisitChoiceField(label="Lượt khách đang phục vụ", queryset=Booking.objects.filter(status=Booking.Status.SEATED).select_related("table"))


class WalkInForm(BootstrapFormMixin, forms.Form):
    table = TableChoiceField(label="Bàn", queryset=DiningTable.objects.filter(is_active=True, area__is_active=True).select_related("area"))
    party_size = forms.IntegerField(label="Số khách", min_value=1, max_value=100)
    customer_name = forms.CharField(label="Tên khách (không bắt buộc)", max_length=150, required=False)
    customer_phone = forms.CharField(label="Số điện thoại (không bắt buộc)", max_length=32, required=False, widget=forms.TextInput(attrs={"type": "tel"}))
    duration_minutes = forms.IntegerField(label="Thời lượng dự kiến (phút)", min_value=1, max_value=1440, required=False,
        help_text="Dùng để kiểm tra lịch đặt tiếp theo, không tự kết thúc lượt khi hết giờ.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("duration_minutes", default_duration_minutes())

    def clean_customer_phone(self):
        phone = self.cleaned_data["customer_phone"]
        return normalize_phone(phone) if phone else ""


class RevisionForm(BootstrapFormMixin, forms.Form):
    expected_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class ItemEditForm(RevisionForm):
    quantity = forms.IntegerField(label="Số lượng", min_value=1, max_value=100)
    note = forms.CharField(label="Ghi chú cho Bếp", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}), help_text="Ví dụ: ít cay, không hành.")


class DishChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        price = format(obj.price, ",.0f").replace(",", ".")
        return f"{obj.code} — {obj.name} — {price} đ/{obj.unit.name}"


class DishSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and hasattr(value, "instance"):
            dish = value.instance
            option["attrs"]["data-image-url"] = dish.thumbnail.url if dish.thumbnail else ""
        return option


class AddItemForm(ItemEditForm):
    dish = DishChoiceField(label="Món còn phục vụ", queryset=Dish.objects.filter(status=Dish.Status.AVAILABLE, category__is_active=True, unit__is_active=True).select_related("unit", "category"), widget=DishSelect(attrs={"data-dish-select": ""}))
    field_order = ("dish", "quantity", "note", "expected_revision")


class ReasonForm(RevisionForm):
    reason = forms.CharField(label="Lý do hủy", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class OrderFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Mã đơn / bàn / tên khách", required=False, max_length=150)
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Đơn chưa kết thúc"), *Order.Status.choices, ("all", "Tất cả")])


class KitchenFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Món / mã đơn / bàn", required=False, max_length=150)
    status = forms.ChoiceField(label="Trạng thái món", required=False,
        choices=[("", "Đang chờ xử lý / giao món"), ("SENT", "Đã gửi Bếp"), ("COOKING", "Đang làm"), ("READY", "Đã xong")])
