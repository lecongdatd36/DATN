"""Kiểm tra invariant của Custom User, kể cả ghi trực tiếp qua ORM."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from . import TEST_PASSWORD


class UserModelTests(TestCase):
    def test_new_user_defaults_to_employee_and_hashes_password(self):
        user = get_user_model().objects.create_user(
            username="employee",
            email="Employee@EXAMPLE.TEST",
            password=TEST_PASSWORD,
        )
        self.assertEqual(user.role, "EMPLOYEE")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.email, "Employee@example.test")
        self.assertNotEqual(user.password, TEST_PASSWORD)
        self.assertTrue(user.check_password(TEST_PASSWORD))
        self.assertEqual(str(user), "employee")

    def test_business_manager_does_not_require_django_staff_privilege(self):
        user = get_user_model().objects.create_user(
            username="manager", password=TEST_PASSWORD, role="MANAGER"
        )
        self.assertEqual(user.role, "MANAGER")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_superuser_is_manager_and_has_django_admin_flags(self):
        user = get_user_model().objects.create_superuser(
            username="admin_test", password=TEST_PASSWORD
        )
        self.assertEqual(user.role, "MANAGER")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(TEST_PASSWORD))

    def test_create_superuser_rejects_inconsistent_flags_or_role(self):
        for extra_fields in (
            {"is_staff": False},
            {"is_superuser": False},
            {"role": "EMPLOYEE"},
        ):
            with self.subTest(extra_fields=extra_fields):
                with self.assertRaises(ValueError):
                    get_user_model().objects.create_superuser(
                        username="invalid_admin",
                        password=TEST_PASSWORD,
                        **extra_fields,
                    )
        self.assertFalse(
            get_user_model().objects.filter(username="invalid_admin").exists()
        )

    def test_duplicate_username_is_rejected_by_database(self):
        get_user_model().objects.create_user(username="same_username")
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.create_user(username="same_username")

    def test_invalid_role_is_rejected_by_model_validation_and_database(self):
        user = get_user_model().objects.create_user(username="valid_user")
        user.role = "CASHIER"
        with self.assertRaises(ValidationError):
            user.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.filter(pk=user.pk).update(role="CASHIER")
        user.refresh_from_db()
        self.assertEqual(user.role, "EMPLOYEE")

    def test_database_prevents_superuser_without_manager_role_or_staff_flag(self):
        user = get_user_model().objects.create_superuser(username="admin_test")
        for invalid_values in ({"role": "EMPLOYEE"}, {"is_staff": False}):
            with self.subTest(invalid_values=invalid_values):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    get_user_model().objects.filter(pk=user.pk).update(
                        **invalid_values
                    )

    def test_created_at_is_preserved_and_updated_at_tracks_changes(self):
        user = get_user_model().objects.create_user(username="timestamp_test")
        created_at, previous_update = user.created_at, user.updated_at
        self.assertTrue(timezone.is_aware(created_at))
        user.email = "changed@example.test"
        # Hai lần lưu liên tiếp có thể cùng tick đồng hồ Windows.
        # Cố định thời điểm để kiểm chứng auto_now mà không phụ thuộc tốc độ máy.
        next_update = previous_update + timedelta(seconds=1)
        with patch("django.utils.timezone.now", return_value=next_update):
            user.save()
        user.refresh_from_db()
        self.assertEqual(user.created_at, created_at)
        self.assertEqual(user.updated_at, next_update)
