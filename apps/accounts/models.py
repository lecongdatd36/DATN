from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.crypto import salted_hmac

from apps.accounts.managers import UserManager
from core.constants import SystemRole


class User(AbstractUser):
    Role = SystemRole

    role = models.CharField(
        "vai trò hệ thống",
        max_length=20,
        choices=SystemRole.choices,
        default=SystemRole.EMPLOYEE,
    )
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lần cuối", auto_now=True)
    session_version = models.PositiveIntegerField(default=0, editable=False)

    objects = UserManager()

    class Meta:
        verbose_name = "tài khoản"
        verbose_name_plural = "tài khoản"
        ordering = ("username", "pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=SystemRole.values),
                name="accounts_user_role_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_superuser=False)
                    | models.Q(role=SystemRole.MANAGER, is_staff=True)
                ),
                name="accounts_superuser_manager_staff",
            ),
        ]

    def clean(self):
        super().clean()
        if self.is_superuser:
            errors = {}
            if self.role != SystemRole.MANAGER:
                errors["role"] = "Superuser phải có vai trò Quản trị viên / Quản lý."
            if not self.is_staff:
                errors["is_staff"] = "Superuser phải được phép truy cập Django admin."
            if errors:
                raise ValidationError(errors)

    def _get_session_auth_hash(self, secret=None):
        # Cả hash hiện tại lẫn SECRET_KEY_FALLBACKS của Django đều đi qua đây.
        # Tăng version khi khóa làm phiên cũ hết hiệu lực ngay cả sau khi mở khóa.
        return salted_hmac(
            "apps.accounts.models.User.get_session_auth_hash",
            f"{self.password}:{self.session_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()
