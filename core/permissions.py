"""Chính sách truy cập dùng chung cho view, template và Django admin."""

def can_manage_accounts(user):
    profile = getattr(user, "employee_profile", None)
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.has_perm("employees.change_employeeprofile"))
    )


def can_access_admin(user):
    return can_manage_accounts(user) and bool(user.is_staff)
