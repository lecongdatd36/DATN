"""Khóa giao dịch và đọc lại quyền trước mọi thay đổi nhân sự."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection

from core.permissions import can_manage_accounts
from .models import User
from .permissions import can_manage_target


def lock_actor(actor):
    if not actor or not actor.is_authenticated or actor.pk is None:
        raise PermissionDenied("Bạn không có quyền quản lý nhân viên.")
    # PostgreSQL: cùng một khóa cho các service ghi nhân sự. Giữ thứ tự khóa
    # nhất quán và tránh cấp trùng mã khi hai quản lý tạo nhân viên đồng thời.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [81723001])
    current = User.objects.select_for_update().filter(pk=actor.pk).first()
    if not can_manage_accounts(current):
        raise PermissionDenied("Bạn không có quyền quản lý nhân viên.")
    return current


def check_target(actor, target):
    if not can_manage_target(actor, target):
        raise PermissionDenied("Không được sửa chính mình hoặc superuser. Chỉ superuser được quản lý tài khoản quản lý và tài khoản chưa có hồ sơ.")


def validate_username(user):
    duplicate = User.objects.filter(username__iexact=user.username)
    if user.pk:
        duplicate = duplicate.exclude(pk=user.pk)
    if duplicate.exists():
        raise ValidationError({"username": "Tên đăng nhập đã tồn tại."})
    user.full_clean()
