"""Forms for authentication, account filtering and administration."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm as DjangoPasswordChangeForm,
    SetPasswordForm,
    UserChangeForm,
    UserCreationForm,
)

from apps.employees.models import EmployeeProfile, EmploymentStatus, JobPosition


class BootstrapFormMixin:
    """Style public forms without replacing Django's validation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            widget.attrs["class"] = "form-select" if isinstance(widget, forms.Select) else "form-control"
            if isinstance(widget, forms.PasswordInput):
                widget.attrs["autocomplete"] = (
                    "current-password" if name in {"password", "old_password"} else "new-password"
                )
            bound_field = self[name]
            if field.help_text:
                widget.attrs["aria-describedby"] = f"{bound_field.auto_id}_helptext"

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name not in self.fields:
                continue
            widget = self.fields[name].widget
            widget.attrs["class"] += " is-invalid"
            widget.attrs["aria-invalid"] = "true"
            helptext = widget.attrs.get("aria-describedby", "")
            widget.attrs["aria-describedby"] = f"{helptext} {self[name].auto_id}_errors".strip()


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": "Tên đăng nhập hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.",
        "inactive": "Tài khoản đã bị khóa. Vui lòng liên hệ quản lý.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Tên đăng nhập"
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password"].label = "Mật khẩu"


class AccountFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(
        label="Tìm tài khoản", required=False, max_length=100, strip=True,
        widget=forms.TextInput(attrs={"placeholder": "Tên đăng nhập, họ tên hoặc email"}),
    )
    status = forms.ChoiceField(
        label="Trạng thái", required=False,
        choices=[("", "Tất cả trạng thái"), ("active", "Đang hoạt động"), ("inactive", "Đã khóa")],
    )
    account_type = forms.ChoiceField(label="Loại tài khoản", required=False, choices=[("", "Tất cả loại"), ("MANAGER", "Quản trị viên / Quản lý"), ("EMPLOYEE", "Nhân viên")])
    position = forms.ModelChoiceField(label="Vị trí", required=False, queryset=JobPosition.objects.filter(is_active=True), empty_label="Tất cả vị trí")


class PasswordChangeForm(BootstrapFormMixin, DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Mật khẩu hiện tại"
        self.fields["new_password1"].label = "Mật khẩu mới"
        self.fields["new_password2"].label = "Nhập lại mật khẩu mới"


class EmployeePasswordResetForm(BootstrapFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Mật khẩu mới"
        self.fields["new_password2"].label = "Nhập lại mật khẩu mới"


class AccountUpdateForm(BootstrapFormMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name", "is_active")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class AccountCreateForm(BootstrapFormMixin, forms.Form):
    ACCOUNT_TYPES = (("MANAGER", "Quản trị viên / Quản lý nhà hàng"), ("EMPLOYEE", "Nhân viên nhà hàng"))
    username = forms.CharField(label="Tên đăng nhập", max_length=150)
    email = forms.EmailField(label="Email", required=False)
    password1 = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Xác nhận mật khẩu", widget=forms.PasswordInput)
    account_type = forms.ChoiceField(label="Loại tài khoản", choices=ACCOUNT_TYPES, widget=forms.RadioSelect)
    job_position = forms.ModelChoiceField(label="Vị trí công việc", queryset=JobPosition.objects.filter(is_active=True), required=False)
    employee_code = forms.CharField(label="Mã nhân viên", required=False, max_length=20, widget=forms.HiddenInput)
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    phone = forms.CharField(label="Số điện thoại", max_length=20)
    address = forms.CharField(label="Địa chỉ", required=False, max_length=255)
    date_of_birth = forms.DateField(label="Ngày sinh", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(label="Giới tính", required=False, choices=(('', 'Chưa chọn'), *EmployeeProfile._meta.get_field('gender').choices))
    join_date = forms.DateField(label="Ngày vào làm", widget=forms.DateInput(attrs={"type": "date"}))
    employment_status = forms.ChoiceField(label="Trạng thái", choices=EmploymentStatus.choices, initial=EmploymentStatus.WORKING)
    avatar = forms.ImageField(label="Ảnh đại diện", required=False)
    note = forms.CharField(label="Ghi chú", required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["job_position"].queryset = JobPosition.objects.filter(is_active=True).exclude(code="MANAGER")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("account_type") == "MANAGER":
            cleaned["job_position"] = JobPosition.objects.filter(code="MANAGER", is_active=True).first()
        elif not cleaned.get("job_position"):
            self.add_error("job_position", "Vui lòng chọn vị trí cho nhân viên.")
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Hai mật khẩu không khớp.")
        elif cleaned.get("password1"):
            validate_password(cleaned["password1"])
        return cleaned

    def clean_phone(self):
        return "".join(self.cleaned_data["phone"].split())


class UserCreationAdminForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name", "is_active", "is_staff")


class UserChangeAdminForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name", "is_active", "is_staff")
