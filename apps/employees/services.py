from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core.permissions import can_manage_accounts

from .models import EmployeeActivityLog, EmployeeProfile

User = get_user_model()


def _check_actor(actor):
    if not can_manage_accounts(actor):
        raise PermissionDenied("Bạn không có quyền quản lý nhân viên.")


def _log(*, actor, employee, action, description):
    EmployeeActivityLog.objects.create(
        employee=employee, performed_by=actor, action=action, description=description
    )


@transaction.atomic
def create_employee(*, actor, user_data, profile_data, password):
    _check_actor(actor)
    validate_password(password)
    user = User.objects.create_user(password=password, role="EMPLOYEE", is_staff=False, is_superuser=False, **user_data)
    employee = EmployeeProfile.objects.create(user=user, **profile_data)
    _log(actor=actor, employee=employee, action=EmployeeActivityLog.Action.CREATE, description="Tạo hồ sơ nhân viên.")
    return employee


@transaction.atomic
def update_employee(*, actor, employee_id, user_data, profile_data, password=None):
    _check_actor(actor)
    employee = EmployeeProfile.objects.select_for_update().select_related("user").get(pk=employee_id)
    user = employee.user
    for field, value in user_data.items():
        setattr(user, field, value)
    user.role = "EMPLOYEE"
    user.is_staff = False
    user.is_superuser = False
    if password:
        validate_password(password, user=user)
        user.set_password(password)
    user_fields = (*user_data.keys(), "role", "is_staff", "is_superuser", "updated_at")
    if password:
        user_fields = (*user_fields, "password")
    user.save(update_fields=user_fields)
    for field, value in profile_data.items():
        setattr(employee, field, value)
    employee.full_clean()
    employee.save()
    _log(actor=actor, employee=employee, action=EmployeeActivityLog.Action.UPDATE, description="Cập nhật hồ sơ nhân viên.")
    return employee


@transaction.atomic
def change_employee_status(*, actor, employee_id, status):
    _check_actor(actor)
    employee = EmployeeProfile.objects.select_for_update().get(pk=employee_id)
    employee.employment_status = status
    employee.save(update_fields=("employment_status", "updated_at"))
    if status == "RESIGNED":
        employee.user.is_active = False
        employee.user.session_version += 1
        employee.user.save(update_fields=("is_active", "session_version", "updated_at"))
    _log(actor=actor, employee=employee, action=EmployeeActivityLog.Action.STATUS, description=f"Cập nhật trạng thái: {employee.get_employment_status_display()}.")
    return employee
