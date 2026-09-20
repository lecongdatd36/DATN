"""Nghiệp vụ nhân viên dùng chung chính sách với quản lý tài khoản."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.management_policy import check_target, lock_actor, validate_username
from apps.accounts.services import (
    _record_account_action, apply_account_active, create_account_with_profile, delete_account,
)
from .models import EmployeeActivityLog, EmployeeProfile, EmploymentStatus, JobPosition

User = get_user_model()


def _log(*, actor, employee, action, description):
    EmployeeActivityLog.objects.create(
        employee=employee,
        employee_code_snapshot=employee.employee_code,
        employee_name_snapshot=employee.full_name,
        performed_by=actor,
        performed_by_name_snapshot=actor.get_full_name() or actor.username,
        action=action, description=description,
    )


def _get_target(actor, employee_id):
    actor = lock_actor(actor)
    employee = EmployeeProfile.objects.select_for_update().get(pk=employee_id)
    user = User.objects.select_for_update().get(pk=employee.user_id)
    employee.user = user
    user.employee_profile = employee
    check_target(actor, user)
    return actor, employee


def create_employee(*, actor, user_data, profile_data, password):
    data = dict(profile_data)
    position = data.pop("job_position")
    return create_account_with_profile(
        actor=actor, account_data=user_data, profile_data=data,
        password=password, position_code=position.code,
    )


@transaction.atomic
def update_employee(*, actor, employee_id, user_data, profile_data, password=None):
    actor, employee = _get_target(actor, employee_id)
    user = employee.user
    if set(user_data) - {"username", "email"}:
        raise ValidationError("Thông tin tài khoản không hợp lệ.")
    allowed = {"employee_code", "full_name", "phone", "address", "date_of_birth", "gender", "job_position", "join_date", "employment_status", "resignation_date", "avatar", "note"}
    if set(profile_data) - allowed:
        raise ValidationError("Thông tin hồ sơ không hợp lệ.")
    previous_status = employee.employment_status
    previous_position = employee.job_position_id
    data = dict(profile_data)
    if "phone" in data:
        data["phone"] = "".join(data["phone"].split())
    data["employee_code"] = data.get("employee_code") or employee.employee_code
    if "job_position" in data:
        position = JobPosition.objects.filter(pk=data["job_position"].pk).first()
        if position is None or (not position.is_active and position.pk != previous_position):
            raise ValidationError({"job_position": "Vị trí công việc không còn hoạt động."})
        data["job_position"] = position
    for field, value in data.items():
        setattr(employee, field, value)
    if employee.employment_status != EmploymentStatus.RESIGNED:
        employee.resignation_date = None
    employee.full_clean()
    for field, value in user_data.items():
        setattr(user, field, value)
    user.is_staff = employee.job_position.code == "MANAGER"
    if password:
        validate_password(password, user=user)
        user.set_password(password)
    validate_username(user)
    fields = [*user_data, "is_staff", "updated_at"]
    if password:
        fields.append("password")
    user.save(update_fields=fields)
    employee.save()
    # Thay nhóm vị trí, giữ các nhóm thuộc module khác.
    position_groups = JobPosition.objects.values_list("group_id", flat=True)
    user.groups.remove(*position_groups)
    user.groups.add(employee.job_position.group)
    if employee.employment_status == EmploymentStatus.RESIGNED:
        apply_account_active(actor=actor, target=user, is_active=False)
    # Đi làm lại giữ nguyên khóa; quản lý phải mở khóa tường minh.
    action = EmployeeActivityLog.Action.UPDATE
    if employee.employment_status != previous_status:
        action = EmployeeActivityLog.Action.RESIGN if employee.employment_status == EmploymentStatus.RESIGNED else EmployeeActivityLog.Action.STATUS
    _log(actor=actor, employee=employee, action=action, description=f"Cập nhật hồ sơ; trạng thái: {employee.get_employment_status_display()}.")
    if previous_position != employee.job_position_id:
        user.session_version += 1
        user.save(update_fields=("session_version", "updated_at"))
        _log(actor=actor, employee=employee, action=EmployeeActivityLog.Action.CHANGE_POSITION, description=f"Đổi vị trí sang {employee.job_position.name}.")
    if password:
        _record_account_action(actor=actor, target=user, action_code="RESET_PASSWORD", description="Đặt lại mật khẩu từ hồ sơ nhân viên.")
        _log(actor=actor, employee=employee, action=EmployeeActivityLog.Action.RESET_PASSWORD, description="Đặt lại mật khẩu từ hồ sơ nhân viên.")
    return employee


@transaction.atomic
def change_employee_status(*, actor, employee_id, status, resignation_date=None):
    actor, employee = _get_target(actor, employee_id)
    if status not in EmploymentStatus.values:
        raise ValidationError({"status": "Trạng thái nhân viên không hợp lệ."})
    employee.employment_status = status
    employee.resignation_date = resignation_date if status == EmploymentStatus.RESIGNED else None
    employee.full_clean()
    employee.save(update_fields=("employment_status", "resignation_date", "updated_at"))
    if status == EmploymentStatus.RESIGNED:
        apply_account_active(actor=actor, target=employee.user, is_active=False)
    action = EmployeeActivityLog.Action.RESIGN if status == EmploymentStatus.RESIGNED else EmployeeActivityLog.Action.STATUS
    _log(actor=actor, employee=employee, action=action, description=f"Cập nhật trạng thái: {employee.get_employment_status_display()}.")
    return employee


@transaction.atomic
def delete_employee(*, actor, employee_id):
    actor, employee = _get_target(actor, employee_id)
    return delete_account(actor=actor, target_id=employee.user_id)
