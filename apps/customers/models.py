from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from .validators import normalize_phone, validate_phone


class Customer(models.Model):
    full_name = models.CharField("họ tên", max_length=150)
    phone = models.CharField(
        "số điện thoại", max_length=20, unique=True, validators=[validate_phone],
        error_messages={"unique": "Số điện thoại đã có hồ sơ khách hàng. Hãy tìm khách theo số điện thoại."},
    )
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lần cuối", auto_now=True)

    class Meta:
        verbose_name = "khách hàng"
        verbose_name_plural = "khách hàng"
        ordering = ("-created_at", "-pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(phone__regex=r"^0[0-9]{9,10}$"), name="customers_phone_canonical"),
            models.CheckConstraint(condition=models.Q(full_name__regex=r"\S"), name="customers_name_not_blank"),
        ]

    @property
    def customer_code(self):
        return f"KH{self.pk:06d}" if self.pk else ""

    def clean(self):
        super().clean()
        self.full_name = " ".join(self.full_name.split())
        if not self.full_name:
            raise ValidationError({"full_name": "Vui lòng nhập họ tên khách hàng."})
        try:
            self.phone = normalize_phone(self.phone)
        except ValidationError as error:
            raise ValidationError({"phone": error.messages}) from error

    def get_absolute_url(self):
        return reverse("customers:customer_detail", args=[self.pk])

    def __str__(self):
        return f"{self.customer_code} — {self.full_name}"


class CustomerActivityLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Thêm khách hàng"
        UPDATE = "UPDATE", "Sửa khách hàng"
        DELETE = "DELETE", "Xóa khách hàng"

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    customer_code_snapshot = models.CharField("mã khách hàng", max_length=30)
    customer_name_snapshot = models.CharField("tên khách hàng", max_length=150)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="customer_activity_logs")
    performed_by_name_snapshot = models.CharField("người thực hiện", max_length=301)
    action = models.CharField("hành động", max_length=10, choices=Action.choices)
    description = models.TextField("mô tả")
    created_at = models.DateTimeField("thời gian", auto_now_add=True)

    class Meta:
        verbose_name = "nhật ký khách hàng"
        verbose_name_plural = "nhật ký khách hàng"
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.customer_code_snapshot} — {self.get_action_display()}"
