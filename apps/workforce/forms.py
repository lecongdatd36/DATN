from datetime import timedelta
from django import forms
from django.utils import timezone
from apps.accounts.forms import BootstrapFormMixin
from apps.employees.models import EmployeeProfile, EmploymentStatus
from .models import WorkShift


def available_employees():
    return EmployeeProfile.objects.filter(employment_status=EmploymentStatus.WORKING, user__is_active=True, job_position__is_active=True)


class ShiftForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"

    class Meta:
        model = WorkShift
        fields = ("code", "name", "starts_at", "ends_at", "break_minutes", "grace_minutes", "is_active")
        widgets = {"starts_at": forms.TimeInput(format="%H:%M", attrs={"type": "time"}), "ends_at": forms.TimeInput(format="%H:%M", attrs={"type": "time"})}


class ScheduleForm(BootstrapFormMixin, forms.Form):
    employees = forms.ModelMultipleChoiceField(label="Nhân viên (có thể chọn nhiều)", queryset=available_employees(), widget=forms.SelectMultiple(attrs={"size": 6}))
    shift = forms.ModelChoiceField(label="Ca làm", queryset=WorkShift.objects.filter(is_active=True))
    work_date = forms.DateField(label="Ngày bắt đầu ca", initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))
    note = forms.CharField(label="Ghi chú", required=False, max_length=250)


class RangeForm(BootstrapFormMixin, forms.Form):
    start = forms.DateField(label="Từ ngày", widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="Đến ngày", widget=forms.DateInput(attrs={"type": "date"}))
    employee = forms.ModelChoiceField(label="Nhân viên", required=False, queryset=EmployeeProfile.objects.all(), empty_label="Tất cả nhân viên")

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and not timedelta(0) <= data["end"]-data["start"] <= timedelta(days=61):
            raise forms.ValidationError("Chọn khoảng thời gian từ 1 đến 62 ngày.")
        return data


class CorrectionForm(BootstrapFormMixin, forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    checked_in = forms.DateTimeField(label="Giờ vào thực tế", required=False, widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M:%S", attrs={"type": "datetime-local", "step": 1}))
    checked_out = forms.DateTimeField(label="Giờ ra thực tế", required=False, widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M:%S", attrs={"type": "datetime-local", "step": 1}))
    reason = forms.CharField(label="Lý do điều chỉnh / mở lại", required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class DeviceForm(BootstrapFormMixin, forms.Form):
    name = forms.CharField(label="Tên máy tại cửa", max_length=100)
    confirm = forms.BooleanField(label="Tôi đang dùng máy đặt tại cửa. Kích hoạt sẽ đăng xuất tài khoản quản lý khỏi trình duyệt này.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["confirm"].widget.attrs["class"] = "form-check-input"
