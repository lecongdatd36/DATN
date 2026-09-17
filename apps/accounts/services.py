"""Các lệnh quản lý tài khoản có kiểm tra quyền và transaction riêng."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.permissions import can_manage_target
from core.permissions import can_manage_accounts


def _record_account_action(*, actor, target, action_code, description):
    """Nhật ký chỉ chứa hành động và đối tượng, không chứa dữ liệu mật khẩu."""
    LogEntry.objects.create(
        user_id=actor.pk,
        content_type=ContentType.objects.get_for_model(target),
        object_id=str(target.pk),
        object_repr=str(target)[:200],
        action_flag=CHANGE,
        change_message=f"{action_code}: {description}",
    )


def _get_managed_target(*, actor, target_id):
    if not can_manage_accounts(actor) or actor.pk is None:
        raise PermissionDenied("Bạn không có quyền quản lý tài khoản.")
    # Đọc lại actor để không chấp nhận quyền cũ từ một instance đã lưu trong bộ nhớ.
    current_actor = User.objects.select_for_update().filter(pk=actor.pk).first()
    if not can_manage_accounts(current_actor):
        raise PermissionDenied("Bạn không có quyền quản lý tài khoản.")
    target = User.objects.select_for_update().get(pk=target_id)
    if not can_manage_target(current_actor, target):
        raise PermissionDenied("Chỉ được thao tác tài khoản nhân viên khác.")
    return target


@transaction.atomic
def create_employee_account(*, actor, data, password):
    if not can_manage_accounts(actor):
        raise PermissionDenied("Bạn không có quyền quản lý tài khoản.")
    current_actor = User.objects.select_for_update().filter(pk=actor.pk).first()
    if not can_manage_accounts(current_actor):
        raise PermissionDenied("Bạn không có quyền quản lý tài khoản.")
    validate_password(password)
    user = User(**data, role="EMPLOYEE", is_staff=False, is_superuser=False)
    user.set_password(password)
    user.full_clean()
    user.save()
    _record_account_action(
        actor=current_actor,
        target=user,
        action_code="CREATE",
        description="Tạo tài khoản nhân viên.",
    )
    return user


@transaction.atomic
def update_employee_account(*, actor, target_id, data):
    target = _get_managed_target(actor=actor, target_id=target_id)
    for field, value in data.items():
        setattr(target, field, value)
    target.role = "EMPLOYEE"
    target.is_staff = False
    target.is_superuser = False
    target.full_clean()
    target.save(update_fields=(*data.keys(), "role", "is_staff", "is_superuser", "updated_at"))
    _record_account_action(
        actor=actor,
        target=target,
        action_code="UPDATE",
        description="Cập nhật thông tin tài khoản nhân viên.",
    )
    return target


@transaction.atomic
def set_account_active(*, actor, target_id, is_active):
    target = _get_managed_target(actor=actor, target_id=target_id)
    if not isinstance(is_active, bool):
        raise ValidationError("Trạng thái tài khoản phải là giá trị đúng hoặc sai.")
    target.is_active = is_active
    if not is_active:
        target.session_version += 1
    target.save(update_fields=("is_active", "session_version", "updated_at"))
    _record_account_action(
        actor=actor,
        target=target,
        action_code="UNLOCK" if is_active else "LOCK",
        description="Mở khóa tài khoản." if is_active else "Khóa tài khoản.",
    )
    return target


@transaction.atomic
def reset_employee_password(*, actor, target_id, password):
    target = _get_managed_target(actor=actor, target_id=target_id)
    if not isinstance(password, str):
        raise ValidationError("Mật khẩu không hợp lệ.")
    validate_password(password, user=target)
    target.set_password(password)
    target.save(update_fields=("password", "updated_at"))
    _record_account_action(
        actor=actor,
        target=target,
        action_code="RESET_PASSWORD",
        description="Đặt lại mật khẩu nhân viên.",
    )
    return target


@transaction.atomic
def change_own_password(*, actor, old_password, new_password):
    """Đổi mật khẩu trên dữ liệu mới nhất, không ghi đè trạng thái hoặc vai trò."""
    if not actor or not actor.is_authenticated or actor.pk is None:
        raise PermissionDenied("Bạn phải đăng nhập để đổi mật khẩu.")
    current_user = User.objects.select_for_update().filter(pk=actor.pk).first()
    if current_user is None or not current_user.is_active:
        raise PermissionDenied("Tài khoản không còn được phép đổi mật khẩu.")
    if not isinstance(old_password, str) or not current_user.check_password(old_password):
        raise ValidationError({"old_password": "Mật khẩu hiện tại không đúng."})
    if not isinstance(new_password, str):
        raise ValidationError({"new_password1": "Mật khẩu mới không hợp lệ."})
    try:
        validate_password(new_password, user=current_user)
    except ValidationError as error:
        raise ValidationError({"new_password1": error.messages}) from error
    current_user.set_password(new_password)
    current_user.save(update_fields=("password", "updated_at"))
    _record_account_action(
        actor=current_user,
        target=current_user,
        action_code="CHANGE_PASSWORD",
        description="Tự đổi mật khẩu tài khoản.",
    )
    return current_user
