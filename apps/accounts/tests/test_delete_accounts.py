from unittest.mock import patch

from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError, RestrictedError
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.services import delete_account, update_employee_account
from apps.employees.models import EmployeeActivityLog, EmployeeProfile
from . import AccountTestCase, PASSWORD

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AccountDeletionTests(AccountTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.root = User.objects.create_superuser(username="delete_admin", password=PASSWORD)
        cls.legacy = User.objects.create_user(username="legacy_delete", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.root)

    def delete_url(self, user):
        return reverse("accounts:account_delete", args=[user.pk])

    def test_list_and_detail_link_to_confirmation_and_get_does_not_delete(self):
        listing = self.client.get(reverse("accounts:account_list"))
        self.assertNotContains(listing, self.delete_url(self.root))
        for target in [self.manager, self.employee, self.legacy]:
            self.assertContains(listing, self.delete_url(target))
            detail = self.client.get(reverse("accounts:account_detail", args=[target.pk]))
            self.assertContains(detail, self.delete_url(target))
            response = self.client.get(self.delete_url(target))
            self.assertContains(response, "Xác nhận xóa tài khoản")
            self.assertContains(response, target.username)
            self.assertTrue(User.objects.filter(pk=target.pk).exists())
        self.assertEqual(LogEntry.objects.count(), 0)
        self.assertEqual(EmployeeActivityLog.objects.count(), 0)

    def test_delete_account_without_profile_records_durable_audit(self):
        pk, username = self.legacy.pk, self.legacy.username
        response = self.client.post(self.delete_url(self.legacy))
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.assertFalse(User.objects.filter(pk=pk).exists())
        log = LogEntry.objects.get(action_flag=DELETION, object_id=str(pk))
        self.assertEqual(log.user_id, self.root.pk)
        self.assertEqual(log.object_repr, username)
        self.assertIn(username, log.change_message)

    def test_delete_manager_removes_profile_and_preserves_existing_history(self):
        update_employee_account(actor=self.root, target_id=self.manager.pk, data={"email": "updated@example.test"})
        history = self.manager_profile.activity_logs.get(action="UPDATE")
        account_pk, profile_pk = self.manager.pk, self.manager_profile.pk
        response = self.client.post(self.delete_url(self.manager))
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.assertFalse(User.objects.filter(pk=account_pk).exists())
        self.assertFalse(EmployeeProfile.objects.filter(pk=profile_pk).exists())
        history.refresh_from_db()
        self.assertIsNone(history.employee_id)
        deleted = EmployeeActivityLog.objects.get(action="DELETE")
        self.assertIsNone(deleted.employee_id)
        self.assertEqual(deleted.employee_code_snapshot, self.manager_profile.employee_code)
        self.assertEqual(deleted.performed_by_id, self.root.pk)
        self.assertEqual(LogEntry.objects.filter(object_id=str(account_pk)).count(), 2)
        self.assertTrue(User.objects.filter(pk=self.root.pk, is_active=True, is_superuser=True).exists())

    def test_manager_can_delete_ordinary_employee(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.delete_url(self.employee))
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.assertFalse(User.objects.filter(pk=self.employee.pk).exists())

    def test_self_and_superusers_are_protected_at_view_and_service(self):
        for actor, target in [(self.root, self.root), (self.root, User.objects.create_superuser(username="other_root", password=PASSWORD)), (self.manager, self.manager)]:
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.delete_url(target)).status_code, 403)
            self.assertEqual(self.client.post(self.delete_url(target)).status_code, 403)
            with self.assertRaises(PermissionDenied):
                delete_account(actor=actor, target_id=target.pk)
            self.assertTrue(User.objects.filter(pk=target.pk).exists())

    def test_unauthorized_and_anonymous_requests_cannot_delete(self):
        for actor, target in [(self.manager, self.root), (self.manager, self.legacy), (self.employee, self.manager)]:
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.delete_url(target)).status_code, 403)
            self.assertEqual(self.client.post(self.delete_url(target)).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.delete_url(self.legacy)).status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.legacy.pk).exists())

    def test_delete_requires_csrf_and_does_not_accept_delete_http_method(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.root)
        self.assertEqual(client.post(self.delete_url(self.legacy)).status_code, 403)
        self.assertEqual(self.client.delete(self.delete_url(self.legacy)).status_code, 405)
        self.assertTrue(User.objects.filter(pk=self.legacy.pk).exists())

    def test_deleted_account_session_no_longer_authenticates(self):
        old_session = Client()
        old_session.force_login(self.legacy)
        self.client.post(self.delete_url(self.legacy))
        self.assertEqual(old_session.get(reverse("accounts:workspace")).status_code, 302)

    def test_accounts_that_authored_admin_logs_are_preserved_on_both_routes(self):
        update_employee_account(actor=self.manager, target_id=self.employee.pk, data={"email": "employee@example.test"})
        original = LogEntry.objects.get(user=self.manager)
        for url in [self.delete_url(self.manager), reverse("employees:employee_delete", args=[self.manager_profile.pk])]:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Hãy khóa tài khoản thay vì xóa")
            self.assertTrue(User.objects.filter(pk=self.manager.pk).exists())
            self.assertTrue(EmployeeProfile.objects.filter(pk=self.manager_profile.pk).exists())
            self.assertTrue(LogEntry.objects.filter(pk=original.pk).exists())
        self.assertFalse(LogEntry.objects.filter(action_flag=DELETION).exists())

    def test_protected_business_data_rolls_back_profile_deletion_and_audits(self):
        for error_type in [ProtectedError, RestrictedError]:
            with self.subTest(error=error_type.__name__):
                # Các module đơn hàng/kho chưa tồn tại: mô phỏng FK ngăn xóa User
                # sau khi hồ sơ đã được xóa để kiểm chứng rollback toàn transaction.
                with patch.object(User, "delete", side_effect=error_type("linked business record", [])):
                    response = self.client.post(self.delete_url(self.employee))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "dữ liệu nghiệp vụ liên kết")
                self.assertTrue(User.objects.filter(pk=self.employee.pk).exists())
                self.assertTrue(EmployeeProfile.objects.filter(pk=self.employee_profile.pk).exists())
                self.assertFalse(LogEntry.objects.filter(action_flag=DELETION).exists())
                self.assertFalse(EmployeeActivityLog.objects.filter(action="DELETE").exists())

    def test_audit_failure_rolls_back_and_does_not_delete_account(self):
        with patch("apps.accounts.services._record_employee_activity", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                delete_account(actor=self.root, target_id=self.employee.pk)
        self.assertTrue(User.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(EmployeeProfile.objects.filter(pk=self.employee_profile.pk).exists())
        self.assertFalse(LogEntry.objects.filter(action_flag=DELETION).exists())

    def test_missing_account_returns_404(self):
        url = reverse("accounts:account_delete", args=[999999])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
