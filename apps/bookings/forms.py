from django import forms
from django.db.models import Q
from apps.accounts.forms import BootstrapFormMixin
from apps.customers.validators import normalize_phone
from apps.seating.models import DiningTable
from .models import Booking
from .duration import planned_end, MAX_DURATION_MINUTES
from .selectors import default_duration_minutes


class TableChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.code} — {obj.area.name} ({obj.capacity} chỗ)"


def time_field(label):
    return forms.DateTimeField(label=label, input_formats=["%Y-%m-%dT%H:%M"], widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}))


class SlotForm(BootstrapFormMixin, forms.Form):
    starts_at = time_field("Giờ đến")
    duration_minutes = forms.IntegerField(label="Thời lượng dự kiến (phút)", min_value=1, max_value=MAX_DURATION_MINUTES, required=False, help_text="Chỉ đổi khi khách dự kiến dùng bàn lâu hơn hoặc ngắn hơn thường lệ.")
    party_size = forms.IntegerField(label="Số khách", min_value=1, max_value=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_minutes = default_duration_minutes()
        self.initial.setdefault("duration_minutes", self.default_minutes)

    def clean_duration_minutes(self):
        return self.cleaned_data["duration_minutes"] if self.cleaned_data["duration_minutes"] is not None else self.default_minutes

    def clean(self):
        data = super().clean()
        if data.get("starts_at") and data.get("duration_minutes"):
            try:
                data["ends_at"] = planned_end(data["starts_at"], data["duration_minutes"])
            except forms.ValidationError as error:
                for message in error.messages:
                    self.add_error("duration_minutes", message)
        return data


class BookingForm(SlotForm):
    expected_revision = forms.IntegerField(required=False, widget=forms.HiddenInput)
    customer_phone = forms.CharField(label="Số điện thoại khách hàng", max_length=32, widget=forms.TextInput(attrs={"type": "tel"}))
    table = TableChoiceField(label="Bàn", queryset=DiningTable.objects.none())
    field_order = ("customer_phone", "starts_at", "party_size", "table", "duration_minutes")

    def __init__(self, *args, booking=None, **kwargs):
        super().__init__(*args, **kwargs)
        if booking:
            self.fields["expected_revision"].required = True
            self.initial["duration_minutes"] = booking.duration_minutes
            self.default_minutes = booking.duration_minutes
        query = Q(is_active=True, area__is_active=True)
        if booking:
            query |= Q(pk=booking.table_id)
        self.fields["table"].queryset = DiningTable.objects.select_related("area").filter(query)

    def clean_customer_phone(self):
        return normalize_phone(self.cleaned_data["customer_phone"])


class TransitionForm(BootstrapFormMixin, forms.Form):
    expected_status = forms.ChoiceField(choices=Booking.Status.choices, widget=forms.HiddenInput)
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class BookingFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Mã đặt / tên / điện thoại / bàn", required=False, max_length=150)
    date = forms.DateField(label="Ngày đến", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Tất cả"), *Booking.Status.choices])
    table = TableChoiceField(label="Bàn", queryset=DiningTable.objects.select_related("area"), required=False, empty_label="Tất cả bàn")


class BookingSettingsForm(BootstrapFormMixin, forms.Form):
    default_duration_minutes = forms.IntegerField(label="Thời lượng mặc định (phút)", min_value=1, max_value=MAX_DURATION_MINUTES)
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)
