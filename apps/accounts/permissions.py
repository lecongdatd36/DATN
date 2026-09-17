"""Quyền thao tác lên tài khoản cụ thể, không dùng các cờ admin làm vai trò."""

from core.permissions import can_manage_accounts


def can_manage_target(actor, target):
    profile = getattr(target, "employee_profile", None)
    return bool(
        can_manage_accounts(actor)
        and target
        and target.pk is not None
        and actor.pk != target.pk
        and profile is not None
        and profile.job_position.code != "MANAGER"
        and not target.is_superuser
    )


def can_view_account(actor, target):
    return bool(
        can_manage_accounts(actor)
        and target
        and target.pk is not None
    )
