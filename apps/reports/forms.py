from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.forms import BootstrapFormMixin


class ReportFilterForm(BootstrapFormMixin, forms.Form):
    date_from = forms.DateField(
        label="Từ ngày",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        label="Đến ngày",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    @staticmethod
    def default_period():
        today = timezone.localdate()
        return today.replace(day=1), today

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if not date_from or not date_to:
            return cleaned_data
        if date_from > date_to:
            raise ValidationError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        if date_to - date_from > timedelta(days=366):
            raise ValidationError("Mỗi lần chỉ xem tối đa 367 ngày để báo cáo tải nhanh.")
        return cleaned_data
