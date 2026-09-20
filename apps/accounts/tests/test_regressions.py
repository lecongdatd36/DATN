"""Kiểm thử hồi quy các lỗi phân quyền, trạng thái và biểu mẫu."""
from datetime import date, timedelta
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.services import (
    change_own_password, create_account_with_profile, reset_employee_password,
    set_account_active, update_employee_account,
)
from apps.employees.models import EmployeeActivityLog, EmployeeProfile, JobPosition
from apps.employees.services import change_employee_status, delete_employee, update_employee
from apps.employees.validators import validate_avatar
from core.permissions import can_manage_accounts
from . import AccountTestCase, PASSWORD

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PersonnelRegressionTests(AccountTestCase):
    def setUp(self):
        self.client.force_login(self.manager)

    def payload(self, **overrides):
        data = {
            "username": "new_waiter", "email": "new@example.test",
            "password1": "New-Password!3462", "password2": "New-Password!3462",
            "account_type": "EMPLOYEE", "job_position": self.waiter_position.pk,
            "full_name": "Nguyen Van Moi", "phone": "0901111222",
            "join_date": date.today().isoformat(), "employment_status": "WORKING",
        }
        data.update(overrides)
        return data

    def test_all_employee_groups_denied_management_get_and_post(self):
        routes = [
            ("accounts:account_list", []), ("accounts:account_create", []),
            ("accounts:account_update", [self.manager.pk]),
            ("accounts:account_lock", [self.manager.pk]),
            ("accounts:password_reset", [self.manager.pk]),
            ("employees:employee_list", []), ("employees:employee_create", []),
            ("employees:employee_update", [self.manager_profile.pk]),
            ("employees:employee_status", [self.manager_profile.pk]),
            ("employees:employee_delete", [self.manager_profile.pk]),
        ]
        for position in JobPosition.objects.exclude(code="MANAGER"):
            with self.subTest(position=position.code):
                self.employee.groups.set([position.group])
                self.employee.is_staff = True  # Cờ Admin không cấp quyền nghiệp vụ.
                self.employee.save(update_fields=["is_staff"])
                self.client.force_login(self.employee)
                for name, args in routes:
                    url = reverse(name, args=args)
                    self.assertEqual(self.client.get(url).status_code, 403, name)
                    self.assertEqual(self.client.post(url, {}).status_code, 403, name)

    def test_legacy_change_permission_does_not_grant_management(self):
        self.employee.user_permissions.add(Permission.objects.get(codename="change_employeeprofile"))
        self.assertFalse(can_manage_accounts(User.objects.get(pk=self.employee.pk)))

    def test_repair_migration_removes_excess_permissions_and_expires_sessions(self):
        permission = Permission.objects.get(codename="change_employeeprofile")
        for position in JobPosition.objects.all():
            position.group.permissions.add(permission)
        migration = import_module("apps.employees.migrations.0008_correct_staff_permissions")
        with connection.schema_editor() as editor:
            migration.correct_permissions(apps, editor)
        for position in JobPosition.objects.exclude(code="MANAGER"):
            self.assertFalse(position.group.permissions.filter(content_type__app_label__in=["accounts", "employees"]).exists())
        self.assertTrue(self.manager_position.group.permissions.filter(codename="manage_staff").exists())
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.session_version, 1)

    def test_anonymous_requests_redirect_before_object_lookup(self):
        self.client.logout()
        for name in ["employees:employee_status", "employees:employee_update", "employees:employee_delete"]:
            self.assertEqual(self.client.get(reverse(name, args=[999999])).status_code, 302)

    def test_manager_profiles_and_self_are_protected_on_all_write_routes(self):
        other_user = User.objects.create_user(username="other_manager", password=PASSWORD, is_staff=True)
        other_user.groups.add(self.manager_position.group)
        other = EmployeeProfile.objects.create(user=other_user, employee_code="NV0030", full_name="Other Manager", phone="0900000030", job_position=self.manager_position, join_date=date.today())
        for profile in [self.manager_profile, other]:
            for route in ["employee_update", "employee_status", "employee_delete"]:
                url = reverse("employees:" + route, args=[profile.pk])
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
        other_user.refresh_from_db()
        self.assertTrue(other_user.is_staff)

    def test_services_reject_manager_superuser_and_self_targets(self):
        self.employee.is_superuser = True
        self.employee.is_staff = True
        self.employee.save()
        for profile in [self.manager_profile, self.employee_profile]:
            for operation in [
                lambda: update_employee(actor=self.manager, employee_id=profile.pk, user_data={}, profile_data={}),
                lambda: change_employee_status(actor=self.manager, employee_id=profile.pk, status="RESIGNED", resignation_date=date.today()),
                lambda: delete_employee(actor=self.manager, employee_id=profile.pk),
            ]:
                with self.assertRaises(PermissionDenied):
                    operation()
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_superuser)

    def test_services_recheck_revoked_actor_permissions(self):
        self.assertTrue(can_manage_accounts(self.manager))  # Prime Django permission cache.
        self.manager.groups.clear()
        with self.assertRaises(PermissionDenied):
            update_employee(actor=self.manager, employee_id=self.employee_profile.pk, user_data={}, profile_data={})
        with self.assertRaises(PermissionDenied):
            set_account_active(actor=self.manager, target_id=self.employee.pk, is_active=False)
        with self.assertRaises(PermissionDenied):
            create_account_with_profile(actor=self.manager, account_data={}, profile_data={}, password=PASSWORD, position_code="WAITER")

    def test_edit_lock_then_unlock_does_not_revive_old_session(self):
        old_client = Client()
        old_client.force_login(self.employee)
        update_employee_account(actor=self.manager, target_id=self.employee.pk, data={"is_active": False})
        update_employee_account(actor=self.manager, target_id=self.employee.pk, data={"is_active": True})
        self.assertEqual(old_client.get(reverse("accounts:workspace")).status_code, 302)
        actions = set(self.employee_profile.activity_logs.values_list("action", flat=True))
        self.assertTrue({"LOCK_ACCOUNT", "UNLOCK_ACCOUNT"}.issubset(actions))

    def test_resigned_employee_cannot_be_unlocked_by_either_route(self):
        change_employee_status(actor=self.manager, employee_id=self.employee_profile.pk, status="RESIGNED", resignation_date=date.today())
        response = self.client.post(reverse("accounts:account_unlock", args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        with self.assertRaises(ValidationError):
            update_employee_account(actor=self.manager, target_id=self.employee.pk, data={"is_active": True})
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

    def test_rehire_requires_explicit_unlock(self):
        change_employee_status(actor=self.manager, employee_id=self.employee_profile.pk, status="RESIGNED", resignation_date=date.today())
        change_employee_status(actor=self.manager, employee_id=self.employee_profile.pk, status="WORKING")
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.employee_profile.refresh_from_db()
        self.assertIsNone(self.employee_profile.resignation_date)
        set_account_active(actor=self.manager, target_id=self.employee.pk, is_active=True)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_create_resigned_without_date_returns_form_error(self):
        response = self.client.post(reverse("accounts:account_create"), self.payload(employment_status="RESIGNED"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("resignation_date", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="new_waiter").exists())

    def test_create_resigned_with_date_creates_locked_account(self):
        response = self.client.post(reverse("accounts:account_create"), self.payload(employment_status="RESIGNED", resignation_date=date.today().isoformat()))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(username="new_waiter").is_active)

    def test_duplicate_and_invalid_username_return_form_errors(self):
        for username in [self.employee.username, self.employee.username.upper(), "bad name!"]:
            response = self.client.post(reverse("accounts:account_create"), self.payload(username=username))
            self.assertEqual(response.status_code, 200)
            self.assertIn("username", response.context["form"].errors)

    def test_profile_validation_errors_are_displayed_without_creating_user(self):
        for overrides, field in [({"phone": "bad"}, "phone"), ({"phone": self.employee_profile.phone}, "phone"), ({"join_date": (date.today() + timedelta(days=1)).isoformat()}, "join_date")]:
            response = self.client.post(reverse("accounts:account_create"), self.payload(**overrides))
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context["form"].errors)
            self.assertFalse(User.objects.filter(username="new_waiter").exists())

    def test_bad_resignation_date_maps_back_to_date_field(self):
        response = self.client.post(reverse("employees:employee_status", args=[self.employee_profile.pk]), {"status": "RESIGNED", "resignation_date": (date.today() - timedelta(days=1)).isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("resignation_date", response.context["form"].errors)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_missing_manager_position_returns_form_error(self):
        self.manager_position.is_active = False
        self.manager_position.save()
        response = self.client.post(reverse("accounts:account_create"), self.payload(account_type="MANAGER", job_position=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("account_type", response.context["form"].errors)

    def test_service_validates_password_and_username(self):
        for password, username in [("123", "new_user"), (PASSWORD, "bad name!")]:
            with self.assertRaises(ValidationError):
                create_account_with_profile(actor=self.manager, account_data={"username": username}, profile_data={"full_name": "New", "phone": "0901111222", "join_date": date.today()}, password=password, position_code="WAITER")
        self.assertFalse(User.objects.filter(username="new_user").exists())

    def test_position_change_updates_group_staff_and_expires_session(self):
        old_hash = self.employee.get_session_auth_hash()
        update_employee(actor=self.manager, employee_id=self.employee_profile.pk, user_data={}, profile_data={"job_position": self.manager_position})
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_staff)
        self.assertFalse(self.employee.is_superuser)
        self.assertEqual(list(self.employee.groups.values_list("name", flat=True)), ["MANAGER"])
        self.assertNotEqual(old_hash, self.employee.get_session_auth_hash())

    def test_password_reset_from_profile_has_audit_and_invalidates_session(self):
        old_hash = self.employee.get_session_auth_hash()
        update_employee(actor=self.manager, employee_id=self.employee_profile.pk, user_data={}, profile_data={}, password="Reset!6723-Secret")
        self.employee.refresh_from_db()
        self.assertNotEqual(old_hash, self.employee.get_session_auth_hash())
        log = self.employee_profile.activity_logs.get(action="RESET_PASSWORD")
        self.assertNotIn("Reset!6723-Secret", log.description)
        self.assertNotIn(self.employee.password, log.description)

    def test_audit_failure_rolls_back_account_change(self):
        with patch("apps.accounts.services._record_employee_activity", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                set_account_active(actor=self.manager, target_id=self.employee.pk, is_active=False)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(self.employee.session_version, 0)

    def test_admin_cannot_bypass_personnel_services(self):
        admin = User.objects.create_superuser(username="admin_regression", password=PASSWORD)
        self.client.force_login(admin)
        for model, pk in [("employees_employeeprofile", self.employee_profile.pk), ("employees_jobposition", self.waiter_position.pk), ("accounts_user", self.employee.pk)]:
            url = reverse("admin:" + model + "_change", args=[pk])
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:employees_jobposition_add")).status_code, 403)

    def test_account_search_and_workspace_use_profile_name_and_position(self):
        response = self.client.get(reverse("accounts:account_list"), {"q": self.employee_profile.full_name})
        self.assertEqual(response.context["paginator"].count, 1)
        self.client.force_login(self.employee)
        response = self.client.get(reverse("accounts:workspace"))
        self.assertContains(response, self.employee_profile.full_name)
        self.assertContains(response, self.waiter_position.name)

    def test_filtered_pagination_preserves_position_id_on_both_lists(self):
        for number in range(21):
            user = User.objects.create_user(username=f"paging{number}")
            EmployeeProfile.objects.create(user=user, employee_code=f"P{number:03d}", full_name="Paging", phone=f"091111{number:04d}", job_position=self.waiter_position, join_date=date.today())
        for name in ["accounts:account_list", "employees:employee_list"]:
            url = reverse(name)
            response = self.client.get(url, {"position": self.waiter_position.pk})
            self.assertContains(response, f"position={self.waiter_position.pk}&amp;page=2")
            second = self.client.get(url, {"position": self.waiter_position.pk, "page": 2})
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(second.context["page_obj"]), 2)

    def test_large_avatar_rejected(self):
        with self.assertRaises(ValidationError):
            validate_avatar(SimpleUploadedFile("large.png", b"x" * (5 * 1024 * 1024 + 1)))

    def test_security_forms_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        for name, args in [("accounts:account_create", []), ("accounts:account_lock", [self.employee.pk]), ("employees:employee_delete", [self.employee_profile.pk])]:
            self.assertEqual(client.post(reverse(name, args=args), {}).status_code, 403)

    def test_get_confirmation_does_not_mutate_and_logout_requires_post(self):
        for name, pk in [("accounts:account_lock", self.employee.pk), ("employees:employee_delete", self.employee_profile.pk)]:
            self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 200)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(self.employee_profile.activity_logs.count(), 0)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)

    def test_own_password_change_keeps_current_session_and_rejects_old_password(self):
        self.client.force_login(self.employee)
        with self.assertRaises(ValidationError):
            change_own_password(actor=self.employee, old_password="wrong", new_password="New-Secret!3482")
        response = self.client.post(reverse("accounts:password_change"), {"old_password": PASSWORD, "new_password1": "New-Secret!3482", "new_password2": "New-Secret!3482"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("accounts:workspace")).status_code, 200)

    def test_reset_password_expires_employee_session(self):
        client = Client()
        client.force_login(self.employee)
        reset_employee_password(actor=self.manager, target_id=self.employee.pk, password="Reset!new-9834")
        self.assertEqual(client.get(reverse("accounts:workspace")).status_code, 302)

    def test_login_rejects_locked_user_and_external_redirect(self):
        self.client.logout()
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        url = reverse("accounts:login")
        data = {"username": self.employee.username, "password": PASSWORD, "next": "https://example.test/"}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.employee.is_active = True
        self.employee.save(update_fields=["is_active"])
        self.assertRedirects(self.client.post(url, data), reverse("accounts:workspace"))

    def test_update_employee_form_valid_and_invalid_submissions(self):
        data = {
            "username": self.employee.username, "email": "changed@example.test",
            "employee_code": self.employee_profile.employee_code,
            "full_name": "Changed Name", "phone": self.employee_profile.phone,
            "job_position": self.waiter_position.pk, "join_date": date.today().isoformat(),
            "employment_status": "WORKING",
        }
        url = reverse("employees:employee_update", args=[self.employee_profile.pk])
        self.assertRedirects(self.client.post(url, data), reverse("employees:employee_list"))
        self.employee_profile.refresh_from_db()
        self.assertEqual(self.employee_profile.full_name, "Changed Name")
        data["username"] = self.manager.username
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)

    def test_update_account_form_uses_shared_lock_logic(self):
        response = self.client.post(reverse("accounts:account_update", args=[self.employee.pk]), {"username": self.employee.username, "email": self.employee.email, "first_name": "", "last_name": ""})
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertEqual(self.employee.session_version, 1)

    def test_service_does_not_allow_flags_in_update_payload(self):
        with self.assertRaises(ValidationError):
            update_employee_account(actor=self.manager, target_id=self.employee.pk, data={"is_superuser": True})
        with self.assertRaises(ValidationError):
            update_employee(actor=self.manager, employee_id=self.employee_profile.pk, user_data={"is_superuser": True}, profile_data={})

    def test_deleted_employee_code_is_not_reused_automatically(self):
        old_code = self.employee_profile.employee_code
        delete_employee(actor=self.manager, employee_id=self.employee_profile.pk)
        response = self.client.post(reverse("accounts:account_create"), self.payload())
        self.assertEqual(response.status_code, 302)
        profile = EmployeeProfile.objects.get(user__username="new_waiter")
        self.assertNotEqual(profile.employee_code, old_code)
