from datetime import date

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.employees.models import EmployeeActivityLog, EmployeeProfile, JobPosition
from apps.accounts.services import create_account_with_profile
from apps.accounts.services import reset_employee_password, set_account_active
from . import AccountTestCase, PASSWORD


class AccountServiceTests(AccountTestCase):
    def payload(self, **overrides):
        payload = {
            "username": "kitchen01", "email": "kitchen@example.test", "full_name": "Kitchen Test",
            "phone": "0901000003", "join_date": date.today(), "employment_status": "WORKING",
            "address": "Address", "date_of_birth": None, "gender": "", "avatar": "", "note": "",
            "employee_code": "NV0003",
        }
        payload.update(overrides)
        return payload

    def test_create_account_creates_user_profile_and_group_atomically(self):
        employee = create_account_with_profile(
            actor=self.manager, account_data={"username": "kitchen01", "email": "kitchen@example.test", "is_staff": False},
            profile_data=self.payload(), password="Kitchen-Password!9642", position_code="KITCHEN",
        )
        self.assertEqual(employee.job_position.code, "KITCHEN")
        self.assertTrue(employee.user.groups.filter(name="KITCHEN").exists())
        self.assertTrue(employee.user.check_password("Kitchen-Password!9642"))

    def test_invalid_profile_rolls_back_user(self):
        with self.assertRaises(ValidationError):
            create_account_with_profile(
                actor=self.manager, account_data={"username": "rollback", "email": "rollback@test.local", "is_staff": False},
                profile_data=self.payload(phone="bad-phone"), password="Kitchen-Password!9642", position_code="KITCHEN",
            )
        self.assertFalse(get_user_model().objects.filter(username="rollback").exists())

    def test_all_job_positions_have_groups(self):
        positions = set(JobPosition.objects.values_list("code", flat=True))
        self.assertEqual(positions, {"MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"})
        self.assertEqual(Group.objects.filter(name__in=positions).count(), 5)

    def test_account_security_actions_write_employee_activity_logs(self):
        set_account_active(actor=self.manager, target_id=self.employee.pk, is_active=False)
        set_account_active(actor=self.manager, target_id=self.employee.pk, is_active=True)
        reset_employee_password(actor=self.manager, target_id=self.employee.pk, password="Reset-Password!9642")
        actions = set(EmployeeActivityLog.objects.filter(employee=self.employee_profile).values_list("action", flat=True))
        self.assertTrue({"LOCK_ACCOUNT", "UNLOCK_ACCOUNT", "RESET_PASSWORD"}.issubset(actions))
