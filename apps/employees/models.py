from django.conf import settings
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models


class JobPosition(models.TextChoices):
    MANAGER = "MANAGER", "Quản lý"
    WAITER = "WAITER", "Phục vụ"
    CASHIER = "CASHIER", "Thu ngân"
    KITCHEN = "KITCHEN", "Bếp"
    INVENTORY = "INVENTORY", "Kho"


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
    phone = models.CharField("số điện thoại", max_length=20, validators=[RegexValidator(r"^0[0-9]{9,10}$", "Số điện thoại không hợp lệ.")])
    address = models.CharField("địa chỉ", max_length=255, blank=True)
    date_of_birth = models.DateField("ngày sinh", null=True, blank=True)
    gender = models.CharField("giới tính", max_length=10, choices=Gender.choices, blank=True)
    job_position = models.CharField("vị trí", max_length=20, choices=JobPosition.choices)
    join_date = models.DateField("ngày vào làm")
    employment_status = models.CharField("trạng thái", max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.WORKING)
    avatar = models.ImageField("ảnh đại diện", upload_to="employees/", blank=True)
    note = models.TextField("ghi chú", blank=True)
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lần cuối", auto_now=True)

    class Meta:
        ordering = ("employee_code", "pk")
        indexes = [models.Index(fields=("full_name",)), models.Index(fields=("phone",)), models.Index(fields=("employment_status",))]

    def __str__(self):
        return f"{self.employee_code} - {self.full_name}"


class EmployeeActivityLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Tạo mới"
        UPDATE = "UPDATE", "Cập nhật"
        RESIGN = "RESIGN", "Nghỉ việc"
        STATUS = "STATUS", "Đổi trạng thái"

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.PROTECT, related_name="activity_logs")
    action = models.CharField("hành động", max_length=20, choices=Action.choices)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee_activity_logs")
    description = models.TextField("mô tả")
    created_at = models.DateTimeField("thời gian", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.employee} - {self.get_action_display()}"
