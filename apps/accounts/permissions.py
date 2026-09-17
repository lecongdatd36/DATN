"""Quyền thao tác lên tài khoản cụ thể, không dùng các cờ admin làm vai trò."""

from core.constants import SystemRole
from core.permissions import can_manage_accounts


def can_manage_target(actor, target):
    return bool(
        can_manage_accounts(actor)
        and target
        and target.pk is not None
        and actor.pk != target.pk
        and target.role == SystemRole.EMPLOYEE
        and not target.is_superuser
    )
