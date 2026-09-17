"""Decorator kiểm tra quyền trên các view dạng hàm."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from core.permissions import can_manage_accounts


def manager_required(view_func=None, *, login_url=None, redirect_field_name="next"):
    def decorate(view):
        @wraps(view)
        def checked_view(request, *args, **kwargs):
            if not can_manage_accounts(request.user):
                raise PermissionDenied("Bạn không có quyền quản lý tài khoản.")
            return view(request, *args, **kwargs)

        return login_required(
            checked_view,
            login_url=login_url,
            redirect_field_name=redirect_field_name,
        )

    return decorate(view_func) if view_func is not None else decorate
