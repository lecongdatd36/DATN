from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import EmployeeProfile, EmploymentStatus, JobPosition

User = get_user_model()


class EmployeeForm(forms.ModelForm):
    username = forms.CharField(label="Tên đăng nhập", max_length=150)
    email = forms.EmailField(label="Email", required=False)
    password1 = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Nhập lại mật khẩu", widget=forms.PasswordInput, required=False)

    class Meta:
        model = EmployeeProfile
        fields = ("employee_code", "full_name", "phone", "address", "date_of_birth", "gender", "job_position", "join_date", "employment_status", "avatar", "note")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}), "join_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields["username"].initial = user.username
            self.fields["email"].initial = user.email
            self.fields["password1"].required = False
            self.fields["password2"].required = False
        else:
            self.fields["password1"].required = True
            self.fields["password2"].required = True

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        query = User.objects.filter(username__iexact=username)
        if self.user:
            query = query.exclude(pk=self.user.pk)
        if query.exists():
            raise forms.ValidationError("Tên đăng nhập đã tồn tại.")
        return username

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Hai mật khẩu không khớp.")
            elif password1:
                validate_password(password1, user=self.user)
        return cleaned


class EmployeeFilterForm(forms.Form):
    q = forms.CharField(label="Tìm nhân viên", required=False)
    position = forms.ChoiceField(label="Vị trí", required=False, choices=[("", "Tất cả vị trí"), *JobPosition.choices])
    status = forms.ChoiceField(label="Trạng thái", required=False, choices=[("", "Tất cả trạng thái"), *EmploymentStatus.choices])
