"""Quyền thao tác lên tài khoản cụ thể, không dùng các cờ admin làm vai trò."""

from core.permissions import can_manage_accounts


def can_manage_target(actor, target):
    if (
        not can_manage_accounts(actor)
        or target is None
        or target.pk is None
        or actor.pk == target.pk
        or target.is_superuser
    ):
        return False
    # Superuser quản lý cả manager và tài khoản cũ chưa có hồ sơ nhân sự.
    if actor.is_superuser:
        return True
    profile = getattr(target, "employee_profile", None)
    if profile is None or profile.job_position.code == "MANAGER":
        return False
    # Không hạ mức bảo vệ của tài khoản quản lý bị khóa hoặc có quyền cấp riêng.
    management_permission = {
        "codename": "manage_staff", "content_type__app_label": "employees",
    }
    return not (
        target.user_permissions.filter(**management_permission).exists()
        or target.groups.filter(
            permissions__codename="manage_staff",
            permissions__content_type__app_label="employees",
        ).exists()
    )


def can_view_account(actor, target):
    return bool(
        can_manage_accounts(actor)
        and target
        and target.pk is not None
    )
