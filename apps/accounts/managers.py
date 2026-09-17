from django.contrib.auth.models import UserManager as DjangoUserManager

from core.constants import SystemRole


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", SystemRole.MANAGER)
        if extra_fields["role"] != SystemRole.MANAGER:
            raise ValueError("Superuser phải có vai trò Quản trị viên / Quản lý.")
        return super().create_superuser(username, email, password, **extra_fields)

    create_superuser.alters_data = True

    async def acreate_superuser(
        self, username, email=None, password=None, **extra_fields
    ):
        extra_fields.setdefault("role", SystemRole.MANAGER)
        if extra_fields["role"] != SystemRole.MANAGER:
            raise ValueError("Superuser phải có vai trò Quản trị viên / Quản lý.")
        return await super().acreate_superuser(
            username, email, password, **extra_fields
        )

    acreate_superuser.alters_data = True
