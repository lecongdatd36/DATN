"""Tái hiện màn hình có superuser, manager và tài khoản cũ thiếu hồ sơ."""
from datetime import date

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.services import set_account_active, update_employee_account
from apps.employees.models import EmployeeProfile, JobPosition
from apps.employees.services import change_employee_status, delete_employee, update_employee
from . import PASSWORD

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SuperuserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(username="root", password=PASSWORD)
        cls.manager = User.objects.create_user(username="manager", password=PASSWORD, is_staff=True)
        position = JobPosition.objects.get(code="MANAGER")
        cls.manager.groups.add(position.group)
        cls.profile = EmployeeProfile.objects.create(
            user=cls.manager, employee_code="NV0010", full_name="Manager Test",
            phone="0900000010", join_date=date.today(), job_position=position,
        )
        cls.legacy = User.objects.create_user(username="legacy", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.root)

    def test_three_account_screen_shows_actions_for_manager_and_legacy_only(self):
        response = self.client.get(reverse("accounts:account_list"))
        self.assertEqual(response.context["paginator"].count, 3)
        self.assertContains(response, "Chỉ xem", count=1)
        self.assertContains(response, "Tài khoản đang đăng nhập")
        self.assertContains(response, "Chưa có hồ sơ nhân sự", count=1)
        for target in [self.manager, self.legacy]:
            for route in ["account_update", "account_lock", "password_reset"]:
                url = reverse("accounts:" + route, args=[target.pk])
                self.assertContains(response, url)
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertNotContains(response, reverse("accounts:account_update", args=[self.root.pk]))

    def test_superuser_can_edit_manager_without_removing_management_rights(self):
        response = self.client.post(reverse("accounts:account_update", args=[self.manager.pk]), {
            "username": self.manager.username, "email": "manager@example.test", "is_active": "on",
        })
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.email, "manager@example.test")
        self.assertTrue(self.manager.is_staff)
        self.assertTrue(self.manager.has_perm("employees.manage_staff"))

    def test_manager_lock_unlock_and_reset_expire_sessions_and_log_actions(self):
        old = Client()
        old.force_login(self.manager)
        for route in ["account_lock", "account_unlock"]:
            self.assertEqual(self.client.post(reverse("accounts:" + route, args=[self.manager.pk])).status_code, 302)
        self.assertEqual(old.get(reverse("accounts:workspace")).status_code, 302)
        response = self.client.post(reverse("accounts:password_reset", args=[self.manager.pk]), {
            "new_password1": "Reset!manager-6932", "new_password2": "Reset!manager-6932",
        })
        self.assertEqual(response.status_code, 302)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.check_password("Reset!manager-6932"))
        self.assertTrue({"LOCK_ACCOUNT", "UNLOCK_ACCOUNT", "RESET_PASSWORD"}.issubset(set(self.profile.activity_logs.values_list("action", flat=True))))

    def test_legacy_account_actions_work_without_creating_fake_profile(self):
        self.assertEqual(self.client.post(reverse("accounts:account_update", args=[self.legacy.pk]), {
            "username": self.legacy.username, "email": "legacy@example.test", "is_active": "on",
        }).status_code, 302)
        for route in ["account_lock", "account_unlock"]:
            self.assertEqual(self.client.post(reverse("accounts:" + route, args=[self.legacy.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse("accounts:password_reset", args=[self.legacy.pk]), {
            "new_password1": "Reset!legacy-6932", "new_password2": "Reset!legacy-6932",
        }).status_code, 302)
        self.legacy.refresh_from_db()
        self.assertTrue(self.legacy.is_active)
        self.assertTrue(self.legacy.check_password("Reset!legacy-6932"))
        self.assertFalse(EmployeeProfile.objects.filter(user=self.legacy).exists())
        self.assertEqual(LogEntry.objects.filter(object_id=str(self.legacy.pk)).count(), 4)

    def test_superuser_can_update_manager_profile_and_status(self):
        self.assertEqual(self.client.get(reverse("employees:employee_update", args=[self.profile.pk])).status_code, 200)
        update_employee(actor=self.root, employee_id=self.profile.pk, user_data={}, profile_data={"full_name": "Updated Manager"})
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_staff)
        self.assertTrue(self.manager.groups.filter(name="MANAGER").exists())
        change_employee_status(actor=self.root, employee_id=self.profile.pk, status="RESIGNED", resignation_date=date.today())
        self.manager.refresh_from_db()
        self.assertFalse(self.manager.is_active)
        change_employee_status(actor=self.root, employee_id=self.profile.pk, status="WORKING")
        set_account_active(actor=self.root, target_id=self.manager.pk, is_active=True)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_superuser_remains_when_deleting_manager(self):
        delete_employee(actor=self.root, employee_id=self.profile.pk)
        self.assertFalse(User.objects.filter(pk=self.manager.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.root.pk, is_superuser=True, is_active=True).exists())

    def test_self_and_other_superusers_still_protected(self):
        other_root = User.objects.create_superuser(username="other_root", password=PASSWORD)
        for target in [self.root, other_root]:
            for route in ["account_update", "account_lock", "password_reset"]:
                url = reverse("accounts:" + route, args=[target.pk])
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
            with self.assertRaises(PermissionDenied):
                set_account_active(actor=self.root, target_id=target.pk, is_active=False)

    def test_ordinary_manager_does_not_gain_access_to_managers_or_legacy_accounts(self):
        self.client.force_login(self.manager)
        for target in [self.root, self.manager, self.legacy]:
            self.assertEqual(self.client.get(reverse("accounts:account_update", args=[target.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                update_employee_account(actor=self.manager, target_id=target.pk, data={"email": "changed@example.test"})

    def test_services_recheck_superuser_flag_instead_of_trusting_cached_actor(self):
        User.objects.filter(pk=self.root.pk).update(is_superuser=False)
        with self.assertRaises(PermissionDenied):
            set_account_active(actor=self.root, target_id=self.manager.pk, is_active=False)
