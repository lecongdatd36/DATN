"""Chính sách truy cập dùng chung cho view, template và Django admin."""

from core.constants import SystemRole


def can_manage_accounts(user):
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and getattr(user, "role", None) == SystemRole.MANAGER
    )


def can_access_admin(user):
    return can_manage_accounts(user) and bool(user.is_staff)
