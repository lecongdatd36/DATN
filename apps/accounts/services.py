"""Các lệnh quản lý tài khoản có kiểm tra quyền và transaction riêng."""

from django.contrib.admin.models import CHANGE, DELETION, LogEntry
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError

from apps.accounts.models import User
from apps.employees.models import EmployeeActivityLog, EmployeeProfile, JobPosition
from .management_policy import check_target, lock_actor, validate_username


def _record_account_action(*, actor, target, action_code, description, action_flag=CHANGE):
    """Nhật ký chỉ chứa hành động và đối tượng, không chứa dữ liệu mật khẩu."""
    LogEntry.objects.create(
        user_id=actor.pk,
        content_type=ContentType.objects.get_for_model(target),
        object_id=str(target.pk),
        object_repr=str(target)[:200],
        action_flag=action_flag,
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
    current_actor = lock_actor(actor)
    target = User.objects.select_for_update().get(pk=target_id)
    check_target(current_actor, target)
    return target


def _next_employee_code():
    used = set(EmployeeProfile.objects.values_list("employee_code", flat=True))
    used.update(EmployeeActivityLog.objects.values_list("employee_code_snapshot", flat=True))
    number = 1
    while f"NV{number:04d}" in used:
        number += 1
    return f"NV{number:04d}"


@transaction.atomic
def delete_account(*, actor, target_id):
    """Xóa tài khoản và hồ sơ trong cùng transaction, giữ lịch sử thao tác."""
    target = _get_managed_target(actor=actor, target_id=target_id)
    profile = EmployeeProfile.objects.select_for_update().filter(user=target).first()
    # LogEntry.user của Django dùng CASCADE: xóa người thực hiện sẽ làm mất
    # lịch sử họ đã ghi. Những tài khoản này phải khóa để giữ nguyên nhật ký.
    if LogEntry.objects.filter(user=target).exists():
        raise ValidationError("Tài khoản đã thực hiện thao tác có nhật ký cần lưu giữ. Hãy khóa tài khoản thay vì xóa.")
    username = target.username
    _record_account_action(
        actor=actor, target=target, action_code="DELETE", action_flag=DELETION,
        description=f"Xóa tài khoản {username}" + (f" và hồ sơ {profile.employee_code}." if profile else "."),
    )
    _record_employee_activity(
        actor=actor, target=target, action=EmployeeActivityLog.Action.DELETE,
        description=f"Xóa tài khoản {username} và hồ sơ nhân viên liên kết.",
    )
    try:
        if profile is not None:
            profile.delete()
        target.delete()
    except (ProtectedError, RestrictedError) as error:
        raise ValidationError("Tài khoản hoặc hồ sơ đang có dữ liệu nghiệp vụ liên kết. Hãy khóa tài khoản hoặc chuyển sang nghỉ việc thay vì xóa.") from error
    return username


@transaction.atomic
def create_account_with_profile(*, actor, account_data, profile_data, password, position_code):
    actor = lock_actor(actor)
    position = JobPosition.objects.filter(code=position_code, is_active=True).first()
    if position is None:
        raise ValidationError({"job_position": "Vị trí công việc không còn hoạt động."})
    profile_data = dict(profile_data)
    profile_data.pop("username", None)
    profile_data.pop("email", None)
    profile_data["employee_code"] = profile_data.get("employee_code") or _next_employee_code()
    profile_data["phone"] = "".join(profile_data.get("phone", "").split())
    user = User(**{key: value for key, value in account_data.items() if key in {"username", "email", "first_name", "last_name"}})
    user.is_staff = position.code == "MANAGER"
    user.is_active = profile_data.get("employment_status") != "RESIGNED"
    validate_password(password, user=user)
    user.set_password(password)
    validate_username(user)
    user.save()
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
    data = dict(data)
    if set(data) - {"username", "email", "first_name", "last_name", "is_active"}:
        raise ValidationError("Thông tin tài khoản không hợp lệ.")
    active = data.pop("is_active", target.is_active)
    for field, value in data.items():
        setattr(target, field, value)
    validate_username(target)
    apply_account_active(actor=actor, target=target, is_active=active)
    target.save(update_fields=(*data.keys(), "updated_at"))
    _record_account_action(
        actor=actor,
        target=target,
        action_code="UPDATE",
        description="Cập nhật thông tin tài khoản nhân viên.",
    )
    _record_employee_activity(actor=actor, target=target, action=EmployeeActivityLog.Action.UPDATE, description="Cập nhật thông tin đăng nhập.")
    return target


@transaction.atomic
def set_account_active(*, actor, target_id, is_active):
    target = _get_managed_target(actor=actor, target_id=target_id)
    apply_account_active(actor=actor, target=target, is_active=is_active)
    return target


def apply_account_active(*, actor, target, is_active):
    """Dùng trong transaction sau khi service đã khóa và kiểm tra đối tượng."""
    if not isinstance(is_active, bool):
        raise ValidationError("Trạng thái tài khoản phải là giá trị đúng hoặc sai.")
    profile = getattr(target, "employee_profile", None)
    if is_active and profile is not None and profile.employment_status == "RESIGNED":
        raise ValidationError("Nhân viên đã nghỉ việc. Hãy cập nhật trạng thái làm việc trước khi mở khóa.")
    if target.is_active == is_active:
        return target
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
