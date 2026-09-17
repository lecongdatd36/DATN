from django.contrib.auth.models import UserManager as DjangoUserManager
from asgiref.sync import sync_to_async

class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        user = super().create_superuser(username, email, password, **extra_fields)
        self._assign_manager_group(user)
        return user

    create_superuser.alters_data = True

    async def acreate_superuser(
        self, username, email=None, password=None, **extra_fields
    ):
        user = await super().acreate_superuser(
            username, email, password, **extra_fields
        )
        await sync_to_async(self._assign_manager_group)(user)
        return user

    @staticmethod
    def _assign_manager_group(user):
        from apps.employees.models import JobPosition

        position = JobPosition.objects.filter(code="MANAGER", is_active=True).first()
        if position:
            user.groups.add(position.group)

    acreate_superuser.alters_data = True
