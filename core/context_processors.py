"""Cung cấp các quyết định quyền truy cập đã tập trung hóa cho template."""

from core.permissions import can_access_admin, can_manage_accounts


def access_policy(request):
    return {
        "access": {
            "can_manage_accounts": can_manage_accounts(request.user),
            "can_access_admin": can_access_admin(request.user),
        }
    }
