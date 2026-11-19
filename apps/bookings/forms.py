from django.utils.translation import gettext_lazy as _
from django import forms
from django.db.models import Q
from django.utils import timezone
from apps.accounts.forms import BootstrapFormMixin
from apps.customers.validators import normalize_phone
from apps.seating.models import Area, DiningTable
from .models import Booking, BookingSettings
from .duration import MAX_DURATION_MINUTES
from .selectors import available_transfer_tables
from .scheduling import reservation_end
from .hours import booking_hours_help


class TableChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.code} — {obj.area.name} ({obj.capacity} chỗ)"


def time_field(label):
    return forms.DateTimeField(label=label, input_formats=["%Y-%m-%dT%H:%M"], widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}))


class ReservationScheduleMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service_settings = BookingSettings.objects.get(pk=1)
        self.default_minutes = self.service_settings.default_duration_minutes
        if "duration_minutes" in self.fields:
            self.initial.setdefault("duration_minutes", self.default_minutes)
        self.fields["starts_at"].help_text = booking_hours_help(self.service_settings)

    def clean(self):
        data = super().clean()
        start = data.get("starts_at")
        if start and start < timezone.now() and start != getattr(self, "original_start", None):
            self.add_error("starts_at", "Giờ đến phải ở tương lai.")
        if start and "duration_minutes" not in self.errors:
            try:
                data["ends_at"] = reservation_end(start, data.get("duration_minutes"), settings=self.service_settings)
            except forms.ValidationError as error:
                for field, errors in error.error_dict.items():
                    self.add_error(field if field in self.fields else None, errors)
        return data


class SlotForm(ReservationScheduleMixin, BootstrapFormMixin, forms.Form):
    starts_at = time_field("Giờ đến")
    duration_minutes = forms.IntegerField(label=_("Thời lượng dự kiến (phút)"), min_value=1, max_value=MAX_DURATION_MINUTES, required=False, help_text=_("Chỉ đổi khi khách dự kiến dùng bàn lâu hơn hoặc ngắn hơn thường lệ."))
    party_size = forms.IntegerField(label=_("Số khách"), min_value=1, max_value=100)

    def clean_duration_minutes(self):
        return self.cleaned_data["duration_minutes"] if self.cleaned_data["duration_minutes"] is not None else self.default_minutes


class BookingForm(SlotForm):
    expected_revision = forms.IntegerField(required=False, widget=forms.HiddenInput)
    customer_phone = forms.CharField(label=_("Số điện thoại khách hàng"), max_length=32, widget=forms.TextInput(attrs={"type": "tel"}))
    customer_name = forms.CharField(label=_("Tên khách hàng mới"), max_length=150, required=False, help_text=_("Chỉ cần nhập nếu số điện thoại chưa có hồ sơ khách hàng."))
    table = TableChoiceField(label=_("Bàn"), queryset=DiningTable.objects.none())
    field_order = ("customer_phone", "customer_name", "starts_at", "party_size", "table", "duration_minutes")

    def __init__(self, *args, booking=None, **kwargs):
        self.original_start = booking.starts_at if booking else None
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
    reason = forms.CharField(label=_("Lý do"), required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class TransferTableForm(BootstrapFormMixin, forms.Form):
    table = TableChoiceField(label=_("Chuyển sang bàn"), queryset=DiningTable.objects.none(), empty_label=_("Chọn bàn trống phù hợp"))
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, booking=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = available_transfer_tables(booking) if booking else DiningTable.objects.none()
        self.fields["table"].help_text = "Chỉ hiện bàn đang hoạt động, đủ chỗ, không có khách và không vướng lịch trong thời gian còn lại."


class CancelSeatedVisitForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        label=_("Lý do hủy bàn"),
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("Ví dụ: khách đổi ý và rời nhà hàng")}),
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)


class BookingFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label=_("Mã đặt / tên / điện thoại / bàn"), required=False, max_length=150)
    visit_type = forms.ChoiceField(label=_("Loại lượt"), required=False, choices=[
        ("", "Khách đặt trước"), ("walk_in", "Khách trực tiếp"), ("all", "Tất cả"),
    ])
    date = forms.DateField(label=_("Ngày đến"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(label=_("Trạng thái"), required=False, choices=[("", "Tất cả"), *Booking.Status.choices])
    table = TableChoiceField(label=_("Bàn"), queryset=DiningTable.objects.select_related("area"), required=False, empty_label=_("Tất cả bàn"))


class BookingSettingsForm(BootstrapFormMixin, forms.Form):
    opening_time = forms.TimeField(label=_("Giờ mở cửa"), widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}), required=False)
    closing_time = forms.TimeField(label=_("Giờ đóng cửa"), widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}), required=False)
    last_booking_time = forms.TimeField(label=_("Giờ nhận khách đặt bàn cuối"), widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}), required=False)
    default_duration_minutes = forms.IntegerField(label=_("Thời lượng mặc định (phút)"), min_value=1, max_value=MAX_DURATION_MINUTES)
    no_show_grace_minutes = forms.IntegerField(
        label=_("Tự động ghi nhận không đến sau (phút)"), min_value=0, max_value=240, required=False,
        help_text=_("Tính từ giờ hẹn. Nhập 0 nếu muốn giải phóng bàn ngay khi quá giờ hẹn."),
    )
    expected_revision = forms.IntegerField(widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if data.get("opening_time") and data.get("closing_time") and data["closing_time"] <= data["opening_time"]:
            self.add_error("closing_time", "Giờ đóng cửa phải sau giờ mở cửa trong cùng ngày.")
        return data


class PublicReservationForm(ReservationScheduleMixin, forms.Form):
    full_name = forms.CharField(label=_("Họ và tên"), max_length=150)
    phone = forms.CharField(label=_("Số điện thoại"), max_length=20, widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}))
    starts_at = time_field("Ngày và giờ đến")
    party_size = forms.IntegerField(label=_("Số khách"), min_value=1, max_value=100)
    area = forms.ModelChoiceField(label=_("Khu vực mong muốn"), queryset=Area.objects.filter(is_active=True), required=False, empty_label=_("Không chọn khu vực"))
    note = forms.CharField(label=_("Ghi chú"), max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ví dụ: cần ghế trẻ em hoặc bàn yên tĩnh"}))

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if not name:
            raise forms.ValidationError(_("Vui lòng nhập họ tên."))
        return name

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class PublicReservationLookupForm(forms.Form):
    reservation_code = forms.CharField(label=_("Mã đặt bàn"), max_length=20)
    phone = forms.CharField(label=_("Số điện thoại"), max_length=20, widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}))

    def clean_reservation_code(self):
        code = self.cleaned_data["reservation_code"].strip().upper()
        if not code.startswith("DB") or not code[2:].isdigit():
            raise forms.ValidationError(_("Mã đặt bàn không hợp lệ."))
        return code

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class PublicAvailabilityForm(ReservationScheduleMixin, forms.Form):
    starts_at = time_field("Ngày và giờ đến")
    party_size = forms.IntegerField(label=_("Số khách"), min_value=1, max_value=100)
    area = forms.ModelChoiceField(label=_("Khu vực mong muốn"), queryset=Area.objects.filter(is_active=True), required=False, empty_label=_("Tất cả khu vực"))
