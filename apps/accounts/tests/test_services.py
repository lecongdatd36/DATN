"""Dịch vụ phải tự kiểm tra quyền, validation và vô hiệu hóa phiên cũ."""

from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.services import (
    change_own_password,
    reset_employee_password,
    set_account_active,
)

from . import AccountTestCase, NEW_PASSWORD, TEST_PASSWORD


class AccountServiceTests(AccountTestCase):
    def test_manager_locks_and_unlocks_without_deleting_user(self):
        original_count = get_user_model().objects.count()
        original_password = self.employee.password
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=False
        )
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertEqual(self.employee.password, original_password)
        self.assertEqual(get_user_model().objects.count(), original_count)
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=True
        )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_unauthorized_actor_cannot_call_mutation_services_directly(self):
        for actor in (AnonymousUser(), self.employee, self.inactive_employee):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    set_account_active(
                        actor=actor, target_id=self.employee.pk, is_active=False
                    )
                with self.assertRaises(PermissionDenied):
                    reset_employee_password(
                        actor=actor,
                        target_id=self.employee.pk,
                        password=NEW_PASSWORD,
                    )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_manager_cannot_lock_or_reset_self_another_manager_or_superuser(self):
        superuser = get_user_model().objects.create_superuser(username="super_test")
        for target in (self.manager, self.other_manager, superuser):
            with self.subTest(target=target.username):
                with self.assertRaises(PermissionDenied):
                    set_account_active(
                        actor=self.manager, target_id=target.pk, is_active=False
                    )
                with self.assertRaises(PermissionDenied):
                    reset_employee_password(
                        actor=self.manager,
                        target_id=target.pk,
                        password=NEW_PASSWORD,
                    )
                target.refresh_from_db()
                self.assertTrue(target.is_active)

    def test_inactive_manager_cannot_change_an_employee(self):
        self.manager.is_active = False
        self.manager.save()
        with self.assertRaises(PermissionDenied):
            set_account_active(
                actor=self.manager, target_id=self.employee.pk, is_active=False
            )
        with self.assertRaises(PermissionDenied):
            reset_employee_password(
                actor=self.manager,
                target_id=self.employee.pk,
                password=NEW_PASSWORD,
            )

    def test_stale_actor_instance_cannot_keep_revoked_manager_privileges(self):
        get_user_model().objects.filter(pk=self.manager.pk).update(role="EMPLOYEE")
        # Instance ở caller vẫn giữ MANAGER; quyền hiện tại trong DB phải thắng.
        self.assertEqual(self.manager.role, "MANAGER")
        with self.assertRaises(PermissionDenied):
            set_account_active(
                actor=self.manager, target_id=self.employee.pk, is_active=False
            )
        with self.assertRaises(PermissionDenied):
            reset_employee_password(
                actor=self.manager,
                target_id=self.employee.pk,
                password=NEW_PASSWORD,
            )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_reset_password_hashes_new_value_and_rejects_old_credentials(self):
        reset_employee_password(
            actor=self.manager, target_id=self.employee.pk, password=NEW_PASSWORD
        )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.check_password(NEW_PASSWORD))
        self.assertFalse(self.employee.check_password(TEST_PASSWORD))
        self.assertNotEqual(self.employee.password, NEW_PASSWORD)

    def test_invalid_reset_password_leaves_existing_password_unchanged(self):
        previous_password = self.employee.password
        for password in ("123", "1234567890", "password", self.employee.username):
            with self.subTest(password=password):
                with self.assertRaises(ValidationError):
                    reset_employee_password(
                        actor=self.manager,
                        target_id=self.employee.pk,
                        password=password,
                    )
                self.employee.refresh_from_db()
                self.assertEqual(self.employee.password, previous_password)

    def test_old_session_remains_invalid_after_lock_then_unlock(self):
        employee_client = Client()
        employee_client.force_login(self.employee)
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=False
        )
        # Không truy cập trong khi khóa: cookie cũ vẫn phải bị thu hồi sau mở khóa.
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=True
        )
        response = employee_client.get(reverse("accounts:workspace"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.assertTrue(
            employee_client.login(
                username=self.employee.username, password=TEST_PASSWORD
            )
        )

    def test_manager_password_reset_revokes_employee_session(self):
        employee_client = Client()
        employee_client.force_login(self.employee)
        reset_employee_password(
            actor=self.manager, target_id=self.employee.pk, password=NEW_PASSWORD
        )
        response = employee_client.get(reverse("accounts:workspace"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.assertTrue(
            employee_client.login(
                username=self.employee.username, password=NEW_PASSWORD
            )
        )

    def test_secret_key_rotation_preserves_session_but_not_revoked_session(self):
        employee_client = Client()
        old_test_key = "old-test-key-for-session-rotation-only"
        with override_settings(SECRET_KEY=old_test_key, SECRET_KEY_FALLBACKS=[]):
            employee_client.force_login(self.employee)
        with override_settings(
            SECRET_KEY="new-test-key-for-session-rotation-only",
            SECRET_KEY_FALLBACKS=[old_test_key],
        ):
            self.assertEqual(
                employee_client.get(reverse("accounts:workspace")).status_code,
                200,
            )
            set_account_active(
                actor=self.manager, target_id=self.employee.pk, is_active=False
            )
            set_account_active(
                actor=self.manager, target_id=self.employee.pk, is_active=True
            )
            self.assertEqual(
                employee_client.get(reverse("accounts:workspace")).status_code,
                302,
            )

    def test_password_change_cannot_reactivate_a_concurrently_locked_user(self):
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=False
        )
        self.assertTrue(self.employee.is_active)
        with self.assertRaises(PermissionDenied):
            change_own_password(
                actor=self.employee,
                old_password=TEST_PASSWORD,
                new_password=NEW_PASSWORD,
            )
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_password_change_checks_latest_password_after_manager_reset(self):
        reset_employee_password(
            actor=self.manager, target_id=self.employee.pk, password=NEW_PASSWORD
        )
        with self.assertRaises(ValidationError):
            change_own_password(
                actor=self.employee,
                old_password=TEST_PASSWORD,
                new_password="Another-For-Tests!2357",
            )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.check_password(NEW_PASSWORD))

    def test_password_change_preserves_role_and_revocation_version_from_database(self):
        get_user_model().objects.filter(pk=self.employee.pk).update(
            role="MANAGER", session_version=5
        )
        change_own_password(
            actor=self.employee,
            old_password=TEST_PASSWORD,
            new_password=NEW_PASSWORD,
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.role, "MANAGER")
        self.assertEqual(self.employee.session_version, 5)
        self.assertTrue(self.employee.check_password(NEW_PASSWORD))

    def test_successful_mutations_record_actor_target_and_action_without_passwords(self):
        password_hashes = [self.employee.password]
        own_new_password = "Own-Change-For-Tests!7625"
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=False
        )
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=True
        )
        reset_user = reset_employee_password(
            actor=self.manager, target_id=self.employee.pk, password=NEW_PASSWORD
        )
        password_hashes.append(reset_user.password)
        changed_user = change_own_password(
            actor=self.employee,
            old_password=NEW_PASSWORD,
            new_password=own_new_password,
        )
        password_hashes.append(changed_user.password)
        entries = list(LogEntry.objects.order_by("pk"))
        self.assertEqual(len(entries), 4)
        expected = (
            ("LOCK", self.manager.pk),
            ("UNLOCK", self.manager.pk),
            ("RESET_PASSWORD", self.manager.pk),
            ("CHANGE_PASSWORD", self.employee.pk),
        )
        content_type = ContentType.objects.get_for_model(get_user_model())
        for entry, (action_code, actor_id) in zip(entries, expected, strict=True):
            with self.subTest(action=action_code):
                self.assertEqual(entry.user_id, actor_id)
                self.assertEqual(entry.content_type_id, content_type.pk)
                self.assertEqual(entry.object_id, str(self.employee.pk))
                self.assertEqual(entry.action_flag, CHANGE)
                self.assertTrue(entry.change_message.startswith(f"{action_code}: "))
                self.assertIsNotNone(entry.action_time)
                for sensitive_value in (
                    TEST_PASSWORD, NEW_PASSWORD, own_new_password, *password_hashes
                ):
                    self.assertNotIn(sensitive_value, entry.change_message)
                    self.assertNotIn(sensitive_value, entry.object_repr)

    def test_forbidden_and_invalid_mutations_do_not_record_success_logs(self):
        with self.assertRaises(PermissionDenied):
            set_account_active(
                actor=self.employee, target_id=self.employee.pk, is_active=False
            )
        with self.assertRaises(ValidationError):
            reset_employee_password(
                actor=self.manager, target_id=self.employee.pk, password="123"
            )
        with self.assertRaises(ValidationError):
            change_own_password(
                actor=self.employee,
                old_password="wrong-current-password",
                new_password=NEW_PASSWORD,
            )
        self.assertFalse(LogEntry.objects.exists())

    def test_audit_write_failure_rolls_back_status_session_version_and_password(self):
        operations = (
            (
                set_account_active,
                {"actor": self.manager, "target_id": self.employee.pk, "is_active": False},
            ),
            (
                reset_employee_password,
                {"actor": self.manager, "target_id": self.employee.pk, "password": NEW_PASSWORD},
            ),
            (
                change_own_password,
                {
                    "actor": self.employee,
                    "old_password": TEST_PASSWORD,
                    "new_password": NEW_PASSWORD,
                },
            ),
        )
        before = (
            self.employee.is_active, self.employee.session_version, self.employee.password
        )
        for service, arguments in operations:
            with self.subTest(service=service.__name__):
                with patch(
                    "apps.accounts.services.LogEntry.objects.create",
                    side_effect=RuntimeError("audit storage unavailable"),
                ):
                    with self.assertRaisesMessage(RuntimeError, "audit storage unavailable"):
                        service(**arguments)
                self.employee.refresh_from_db()
                self.assertEqual(
                    (
                        self.employee.is_active,
                        self.employee.session_version,
                        self.employee.password,
                    ),
                    before,
                )
                self.assertFalse(LogEntry.objects.exists())
