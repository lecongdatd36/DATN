"""Forms for authentication, account filtering and administration."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm as DjangoPasswordChangeForm,
    SetPasswordForm,
    UserChangeForm,
    UserCreationForm,
)


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


class UserCreationAdminForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name", "role", "is_active", "is_staff")


class UserChangeAdminForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name", "role", "is_active", "is_staff")
