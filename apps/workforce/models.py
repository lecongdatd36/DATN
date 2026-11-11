from datetime import datetime, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class WorkShift(models.Model):
    code = models.CharField("Mã ca", max_length=20, unique=True)
    name = models.CharField("Tên ca", max_length=100)
    starts_at = models.TimeField("Giờ bắt đầu")
    ends_at = models.TimeField("Giờ kết thúc")
    break_minutes = models.PositiveSmallIntegerField("Phút nghỉ không tính công", default=0)
    grace_minutes = models.PositiveSmallIntegerField("Phút trễ cho phép", default=5)
    is_active = models.BooleanField("Đang sử dụng", default=True)

    class Meta:
        ordering = ("starts_at", "code")

    def clean(self):
        if self.starts_at is not None and self.ends_at is not None:
            start = datetime.combine(datetime.today(), self.starts_at)
            end = datetime.combine(datetime.today(), self.ends_at)
            if end <= start:
                end += timedelta(days=1)
            duration = (end - start).total_seconds() / 60
            if duration > 960:
                raise ValidationError("Ca tối đa 16 giờ; giờ kết thúc nhỏ hơn giờ bắt đầu là ca qua đêm.")
            if self.break_minutes is not None and self.break_minutes >= duration:
                raise ValidationError({"break_minutes": "Giờ nghỉ phải nhỏ hơn thời lượng ca."})
        if self.grace_minutes is not None and self.grace_minutes > 60:
            raise ValidationError({"grace_minutes": "Mức trễ cho phép tối đa 60 phút."})

    def __str__(self):
        return f"{self.code} · {self.name}"


class WorkSchedule(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Nháp"
        PUBLISHED = "PUBLISHED", "Đã công bố"
        CANCELLED = "CANCELLED", "Đã hủy"

    employee = models.ForeignKey("employees.EmployeeProfile", on_delete=models.PROTECT, related_name="work_schedules")
    shift = models.ForeignKey(WorkShift, on_delete=models.PROTECT, related_name="schedules")
    work_date = models.DateField("Ngày bắt đầu ca")
    starts_at = models.DateTimeField("Bắt đầu")
    ends_at = models.DateTimeField("Kết thúc")
    shift_name = models.CharField(max_length=100)
    break_minutes = models.PositiveSmallIntegerField(default=0)
    grace_minutes = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    revision = models.PositiveIntegerField(default=1)
    note = models.CharField("Ghi chú", max_length=250, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_work_schedules")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_at", "employee__employee_code", "pk")
        constraints = [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="work_schedule_positive_duration")]
        indexes = [models.Index(fields=("employee", "starts_at", "ends_at")), models.Index(fields=("work_date", "status"))]


class Attendance(models.Model):
    class Review(models.TextChoices):
        PENDING = "PENDING", "Chờ duyệt"
        APPROVED = "APPROVED", "Đã duyệt"

    schedule = models.OneToOneField(WorkSchedule, on_delete=models.PROTECT, related_name="attendance")
    checked_in_at = models.DateTimeField("Giờ vào thực tế", null=True, blank=True)
    checked_out_at = models.DateTimeField("Giờ ra thực tế", null=True, blank=True)
    review = models.CharField(max_length=10, choices=Review.choices, default=Review.PENDING)
    note = models.TextField("Lý do điều chỉnh", blank=True, max_length=1000)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_attendances")
    approved_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(checked_out_at__isnull=True) | (models.Q(checked_in_at__isnull=False) & models.Q(checked_out_at__gt=models.F("checked_in_at"))), name="attendance_valid_clock_order"),
            models.CheckConstraint(condition=models.Q(review="PENDING", approved_at__isnull=True) | models.Q(review="APPROVED", approved_at__isnull=False), name="attendance_review_timestamp"),
        ]

    @property
    def late_minutes(self):
        return max(0, int((self.checked_in_at - self.schedule.starts_at).total_seconds() // 60)) if self.checked_in_at else 0

    @property
    def is_late(self):
        return self.late_minutes > self.schedule.grace_minutes

    @property
    def early_minutes(self):
        return max(0, int((self.schedule.ends_at - self.checked_out_at).total_seconds() // 60)) if self.checked_out_at else 0

    @property
    def worked_minutes(self):
        if not self.checked_in_at or not self.checked_out_at:
            return 0
        start = max(self.checked_in_at, self.schedule.starts_at)
        end = min(self.checked_out_at, self.schedule.ends_at)
        return max(0, int((end - start).total_seconds() // 60) - self.schedule.break_minutes)

    @property
    def condition(self):
        if not self.checked_in_at:
            return "Vắng" if self.review == self.Review.APPROVED else "Thiếu giờ vào"
        if not self.checked_out_at:
            return "Thiếu giờ ra"
        labels = []
        if self.is_late:
            labels.append(f"Trễ {self.late_minutes} phút")
        if self.early_minutes:
            labels.append(f"Về sớm {self.early_minutes} phút")
        return " · ".join(labels) or "Đủ giờ"


class FaceProfile(models.Model):
    employee = models.OneToOneField("employees.EmployeeProfile", on_delete=models.CASCADE, related_name="face_profile")
    embeddings = models.JSONField(default=list)
    model_version = models.CharField(max_length=60, default="sface-2021dec-v1")
    consent_at = models.DateTimeField()
    enrolled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class KioskDevice(models.Model):
    name = models.CharField("Tên thiết bị", max_length=100)
    token_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FaceChallenge(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    device = models.ForeignKey(KioskDevice, on_delete=models.CASCADE, null=True, blank=True)
    session_digest = models.CharField(max_length=64, blank=True, default="", db_index=True)
    neutral_yaw = models.FloatField(null=True, blank=True)
    action = models.CharField(max_length=4, choices=(("AUTO", "Tự xác định"), ("IN", "Vào ca"), ("OUT", "Ra ca")))
    is_automatic = models.BooleanField(default=False)
    poses = models.JSONField(default=list)
    step = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    employee = models.ForeignKey("employees.EmployeeProfile", on_delete=models.CASCADE, null=True)
    profile_version = models.DateTimeField(null=True)
    frame_hashes = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    last_attempt_at = models.DateTimeField(null=True)
    used_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(device__isnull=False, session_digest="") | (models.Q(device__isnull=True) & ~models.Q(session_digest="")),
            name="face_challenge_has_one_source",
        )]


class AttendanceLog(models.Model):
    schedule = models.ForeignKey(WorkSchedule, on_delete=models.PROTECT, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    device = models.ForeignKey(KioskDevice, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=30)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
