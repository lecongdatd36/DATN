from django import forms
from apps.accounts.forms import BootstrapFormMixin
from apps.bookings.models import Booking
from apps.bookings.forms import TableChoiceField
from apps.bookings.selectors import default_duration_minutes
from apps.customers.validators import normalize_phone
from apps.menu.models import Dish
from apps.seating.models import DiningTable
from .models import Order, Payment


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


class BulkAddItemsForm(forms.Form):
    dishes = forms.ModelMultipleChoiceField(
        label="Món đã chọn",
        queryset=Dish.objects.none(),
        error_messages={
            "required": "Hãy chọn ít nhất một món.",
            "invalid_choice": "Một món đã hết hoặc ngừng phục vụ. Hãy tải lại thực đơn.",
        },
    )
    expected_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, dishes_queryset=None, **kwargs):
        # Keep legacy single-dish clients compatible with the POS multi-select.
        bound_data = args[0] if args else kwargs.get("data")
        if bound_data is not None and "dishes" not in bound_data and bound_data.get("dish"):
            data = bound_data.copy()
            data.setlist("dishes", [bound_data.get("dish")])
            if args:
                args = (data, *args[1:])
            else:
                kwargs["data"] = data
        super().__init__(*args, **kwargs)
        self.fields["dishes"].queryset = dishes_queryset if dishes_queryset is not None else Dish.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        selected = cleaned_data.get("dishes")
        if not selected:
            return cleaned_data
        if selected.count() > 50:
            self.add_error("dishes", "Mỗi lần chỉ thêm tối đa 50 món.")
            return cleaned_data

        items = []
        for dish in selected:
            raw_quantity = self.data.get(f"quantity_{dish.pk}", self.data.get("quantity", "1"))
            try:
                quantity = int(raw_quantity)
            except (TypeError, ValueError):
                self.add_error(None, f"Số lượng của {dish.name} không hợp lệ.")
                continue
            if not 1 <= quantity <= 100:
                self.add_error(None, f"Số lượng của {dish.name} phải từ 1 đến 100.")
                continue
            note = self.data.get(f"note_{dish.pk}", self.data.get("note", "")).strip()
            if len(note) > 500:
                self.add_error(None, f"Ghi chú của {dish.name} không được dài quá 500 ký tự.")
                continue
            items.append({"dish_id": dish.pk, "quantity": quantity, "note": note})
        cleaned_data["items"] = items
        return cleaned_data


class ReasonForm(RevisionForm):
    reason = forms.CharField(label="Lý do hủy", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class PaymentForm(RevisionForm):
    payment_method = forms.ChoiceField(label="Phương thức thanh toán", choices=[("CASH", "Tiền mặt"), ("BANK_TRANSFER", "Chuyển khoản")])
    reference = forms.CharField(label="Ghi chú / mã giao dịch", max_length=100, required=False)
    field_order = ("payment_method", "reference", "expected_revision")


class TablePaymentForm(BootstrapFormMixin, forms.Form):
    orders = forms.ModelMultipleChoiceField(
        label="Bàn thanh toán",
        queryset=Order.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={
            "required": "Hãy chọn ít nhất một bàn cần thanh toán.",
            "invalid_choice": "Một bàn đã thay đổi trạng thái. Hãy tải lại danh sách.",
        },
    )
    payment_method = forms.ChoiceField(label="Phương thức thanh toán", choices=Payment.Method.choices)
    reference = forms.CharField(label="Ghi chú / mã giao dịch", max_length=100, required=False)

    def __init__(self, *args, order_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["orders"].queryset = order_queryset if order_queryset is not None else Order.objects.none()
        self.fields["orders"].widget.attrs["class"] = "form-check-input"


class OrderFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Mã đơn / bàn / tên khách", required=False, max_length=150)
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Đơn chưa kết thúc"), *Order.Status.choices, ("all", "Tất cả")])


class KitchenFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Món / mã đơn / bàn", required=False, max_length=150)
    status = forms.ChoiceField(label="Trạng thái món", required=False,
        choices=[("", "Đang chờ xử lý / giao món"), ("PENDING", "Đã gửi Bếp"), ("COOKING", "Đang làm"), ("READY", "Đã xong")])
