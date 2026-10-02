from django import forms
from django.db.models import Q
from django.utils import timezone
from apps.accounts.forms import BootstrapFormMixin
from apps.customers.validators import normalize_phone
from apps.seating.models import Area, DiningTable
from .models import Booking
from .duration import planned_end, MAX_DURATION_MINUTES
from .selectors import available_transfer_tables, default_duration_minutes


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
    reason = forms.CharField(label="Lý do", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class TransferTableForm(BootstrapFormMixin, forms.Form):
    table = TableChoiceField(label="Chuyển sang bàn", queryset=DiningTable.objects.none(), empty_label="Chọn bàn trống phù hợp")
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, booking=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = available_transfer_tables(booking) if booking else DiningTable.objects.none()
        self.fields["table"].help_text = "Chỉ hiện bàn đang hoạt động, đủ chỗ, không có khách và không vướng lịch trong thời gian còn lại."


class CancelSeatedVisitForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        label="Lý do hủy bàn",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ví dụ: khách đổi ý và rời nhà hàng"}),
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class BookingFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Mã đặt / tên / điện thoại / bàn", required=False, max_length=150)
    visit_type = forms.ChoiceField(label="Loại lượt", required=False, choices=[
        ("", "Khách đặt trước"), ("walk_in", "Khách trực tiếp"), ("all", "Tất cả"),
    ])
    date = forms.DateField(label="Ngày đến", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Tất cả"), *Booking.Status.choices])
    table = TableChoiceField(label="Bàn", queryset=DiningTable.objects.select_related("area"), required=False, empty_label="Tất cả bàn")


class BookingSettingsForm(BootstrapFormMixin, forms.Form):
    default_duration_minutes = forms.IntegerField(label="Thời lượng mặc định (phút)", min_value=1, max_value=MAX_DURATION_MINUTES)
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class PublicReservationForm(forms.Form):
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    phone = forms.CharField(label="Số điện thoại", max_length=20, widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}))
    starts_at = time_field("Ngày và giờ đến")
    party_size = forms.IntegerField(label="Số khách", min_value=1, max_value=100)
    area = forms.ModelChoiceField(label="Khu vực mong muốn", queryset=Area.objects.filter(is_active=True), required=False, empty_label="Không chọn khu vực")
    duration_minutes = forms.IntegerField(label="Thời lượng dự kiến (phút)", min_value=1, max_value=MAX_DURATION_MINUTES, required=False)
    note = forms.CharField(label="Ghi chú", max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ví dụ: cần ghế trẻ em hoặc bàn yên tĩnh"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_minutes = default_duration_minutes()
        self.initial.setdefault("duration_minutes", self.default_minutes)

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if not name:
            raise forms.ValidationError("Vui lòng nhập họ tên.")
        return name

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean(self):
        data = super().clean()
        starts_at = data.get("starts_at")
        duration = data.get("duration_minutes") or self.default_minutes
        if starts_at and starts_at < timezone.now():
            self.add_error("starts_at", "Giờ đến phải ở tương lai.")
        if starts_at and duration:
            try:
                data["ends_at"] = planned_end(starts_at, duration)
            except forms.ValidationError as error:
                self.add_error("duration_minutes", error.messages)
        return data


class PublicReservationLookupForm(forms.Form):
    reservation_code = forms.CharField(label="Mã đặt bàn", max_length=20)
    phone = forms.CharField(label="Số điện thoại", max_length=20, widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}))

    def clean_reservation_code(self):
        code = self.cleaned_data["reservation_code"].strip().upper()
        if not code.startswith("DB") or not code[2:].isdigit():
            raise forms.ValidationError("Mã đặt bàn không hợp lệ.")
        return code

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class PublicAvailabilityForm(forms.Form):
    starts_at = time_field("Ngày và giờ đến")
    party_size = forms.IntegerField(label="Số khách", min_value=1, max_value=100)
    area = forms.ModelChoiceField(label="Khu vực mong muốn", queryset=Area.objects.filter(is_active=True), required=False, empty_label="Tất cả khu vực")
    duration_minutes = forms.IntegerField(label="Thời lượng dự kiến (phút)", min_value=1, max_value=MAX_DURATION_MINUTES, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_minutes = default_duration_minutes()
        self.initial.setdefault("duration_minutes", self.default_minutes)

    def clean(self):
        data = super().clean()
        starts_at = data.get("starts_at")
        duration = data.get("duration_minutes") or self.default_minutes
        if starts_at and starts_at < timezone.now():
            self.add_error("starts_at", "Giờ đến phải ở tương lai.")
        if starts_at and duration:
            try:
                data["ends_at"] = planned_end(starts_at, duration)
            except forms.ValidationError as error:
                self.add_error("duration_minutes", error.messages)
        return data
