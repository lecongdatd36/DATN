from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.utils import timezone


class JobPosition(models.Model):
    code = models.CharField("mã vị trí", max_length=20, unique=True)
    name = models.CharField("tên vị trí", max_length=100)
    description = models.TextField("mô tả", blank=True)
    group = models.OneToOneField(Group, on_delete=models.PROTECT, related_name="job_position")
    is_active = models.BooleanField("đang sử dụng", default=True)
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lần cuối", auto_now=True)

    class Meta:
        ordering = ("code", "pk")

    def __str__(self):
        return self.name


class EmploymentStatus(models.TextChoices):
    WORKING = "WORKING", "Đang làm việc"
    ON_LEAVE = "ON_LEAVE", "Tạm nghỉ"
    RESIGNED = "RESIGNED", "Đã nghỉ việc"


class Gender(models.TextChoices):
    MALE = "MALE", "Nam"
    FEMALE = "FEMALE", "Nữ"
    OTHER = "OTHER", "Khác"


class EmployeeProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee_profile")
    employee_code = models.CharField("mã nhân viên", max_length=20, unique=True, validators=[MinLengthValidator(3)])
    full_name = models.CharField("họ và tên", max_length=150)
    phone = models.CharField("số điện thoại", max_length=20, unique=True, validators=[RegexValidator(r"^0[0-9]{9,10}$", "Số điện thoại không hợp lệ.")])
    address = models.CharField("địa chỉ", max_length=255, blank=True)
    date_of_birth = models.DateField("ngày sinh", null=True, blank=True)
    gender = models.CharField("giới tính", max_length=10, choices=Gender.choices, blank=True)
    job_position = models.ForeignKey(JobPosition, on_delete=models.PROTECT, related_name="employees", verbose_name="vị trí")
    join_date = models.DateField("ngày vào làm")
    employment_status = models.CharField("trạng thái", max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.WORKING)
    resignation_date = models.DateField("ngày nghỉ việc", null=True, blank=True)
    avatar = models.ImageField("ảnh đại diện", upload_to="employees/", blank=True)
    note = models.TextField("ghi chú", blank=True)
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lần cuối", auto_now=True)

    class Meta:
        ordering = ("employee_code", "pk")
        indexes = [models.Index(fields=("full_name",)), models.Index(fields=("phone",)), models.Index(fields=("job_position",)), models.Index(fields=("employment_status",))]

    def clean(self):
        super().clean()
        if self.join_date and self.join_date > timezone.localdate():
            raise ValidationError({"join_date": "Ngày vào làm không được ở tương lai."})
        if self.date_of_birth and self.join_date and self.date_of_birth >= self.join_date:
            raise ValidationError({"date_of_birth": "Ngày sinh phải trước ngày vào làm."})
        if self.employment_status == EmploymentStatus.RESIGNED and not self.resignation_date:
            raise ValidationError({"resignation_date": "Nhân viên đã nghỉ việc phải có ngày nghỉ việc."})
        if self.resignation_date and self.join_date and self.resignation_date < self.join_date:
            raise ValidationError({"resignation_date": "Ngày nghỉ việc không được trước ngày vào làm."})

    def __str__(self):
        return f"{self.employee_code} - {self.full_name}"


class EmployeeActivityLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Tạo mới"
        UPDATE = "UPDATE", "Cập nhật"
        CHANGE_POSITION = "CHANGE_POSITION", "Đổi vị trí"
        RESET_PASSWORD = "RESET_PASSWORD", "Đặt lại mật khẩu"
        LOCK_ACCOUNT = "LOCK_ACCOUNT", "Khóa tài khoản"
        UNLOCK_ACCOUNT = "UNLOCK_ACCOUNT", "Mở khóa tài khoản"
        RESIGN = "RESIGN", "Nghỉ việc"
        STATUS = "STATUS", "Đổi trạng thái"
        DELETE = "DELETE", "Xóa nhân viên"

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    employee_code_snapshot = models.CharField("mã nhân viên", max_length=20, default="")
    employee_name_snapshot = models.CharField("tên nhân viên", max_length=150, default="")
    action = models.CharField("hành động", max_length=20, choices=Action.choices)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="employee_activity_logs")
    performed_by_name_snapshot = models.CharField("người thực hiện", max_length=150, blank=True, default="")
    description = models.TextField("mô tả")
    created_at = models.DateTimeField("thời gian", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.employee} - {self.get_action_display()}"
