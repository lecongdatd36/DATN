"""Mixin áp dụng cùng chính sách quản lý cho các class-based view."""

from django.contrib.auth.mixins import AccessMixin

from core.permissions import can_manage_accounts


class ManagerRequiredMixin(AccessMixin):
    permission_denied_message = "Bạn không có quyền quản lý tài khoản."

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_accounts(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)
