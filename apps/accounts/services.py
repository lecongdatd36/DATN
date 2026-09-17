"""Các lệnh quản lý tài khoản có kiểm tra quyền và transaction riêng."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.contrib.auth.models import Group

from apps.accounts.models import User
from apps.employees.models import EmployeeActivityLog, EmployeeProfile, JobPosition
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


def _record_employee_activity(*, actor, target, action, description):
    profile = getattr(target, "employee_profile", None)
    if profile is None:
        return
    EmployeeActivityLog.objects.create(
        employee=profile,
        employee_code_snapshot=profile.employee_code,
        employee_name_snapshot=profile.full_name,
        action=action,
        performed_by=actor,
        performed_by_name_snapshot=actor.get_full_name() or actor.username,
        description=description,
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


def _next_employee_code():
    used = set(EmployeeProfile.objects.values_list("employee_code", flat=True))
    number = 1
    while f"NV{number:04d}" in used:
        number += 1
    return f"NV{number:04d}"


@transaction.atomic
def create_account_with_profile(*, actor, account_data, profile_data, password, position_code):
    if not can_manage_accounts(actor):
        raise PermissionDenied("Bạn không có quyền tạo tài khoản.")
    position = JobPosition.objects.select_for_update().get(code=position_code, is_active=True)
    profile_data = dict(profile_data)
    profile_data.pop("username", None)
    profile_data.pop("email", None)
    profile_data["employee_code"] = profile_data.get("employee_code") or _next_employee_code()
    user = User.objects.create_user(password=password, **account_data)
    user.groups.add(position.group)
    employee = EmployeeProfile(user=user, job_position=position, **profile_data)
    employee.full_clean()
    employee.save()
    EmployeeActivityLog.objects.create(
        employee=employee,
        employee_code_snapshot=employee.employee_code,
        employee_name_snapshot=employee.full_name,
        action=EmployeeActivityLog.Action.CREATE,
        performed_by=actor,
        performed_by_name_snapshot=actor.get_full_name() or actor.username,
        description=f"Tạo tài khoản và hồ sơ với vị trí {position.name}.",
    )
    return employee


@transaction.atomic
def update_employee_account(*, actor, target_id, data):
    target = _get_managed_target(actor=actor, target_id=target_id)
    for field, value in data.items():
        setattr(target, field, value)
    target.is_staff = False
    target.is_superuser = False
    target.full_clean()
    target.save(update_fields=(*data.keys(), "is_staff", "is_superuser", "updated_at"))
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
    _record_employee_activity(
        actor=actor,
        target=target,
        action=EmployeeActivityLog.Action.LOCK_ACCOUNT if not is_active else EmployeeActivityLog.Action.UNLOCK_ACCOUNT,
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
    _record_employee_activity(
        actor=actor,
        target=target,
        action=EmployeeActivityLog.Action.RESET_PASSWORD,
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
