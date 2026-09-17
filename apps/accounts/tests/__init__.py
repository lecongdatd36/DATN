"""Dữ liệu kiểm thử riêng, chỉ được tạo trong database test của Django."""

from django.contrib.auth import get_user_model
from django.test import TestCase


TEST_PASSWORD = "Only-For-Tests!8537"
NEW_PASSWORD = "Changed-For-Tests!9642"


class AccountTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        user_model = get_user_model()
        cls.manager = user_model.objects.create_user(
            username="manager_test", password=TEST_PASSWORD, role="MANAGER"
        )
        cls.employee = user_model.objects.create_user(
            username="employee_test",
            email="employee@example.test",
            password=TEST_PASSWORD,
        )
        cls.other_manager = user_model.objects.create_user(
            username="other_manager_test", password=TEST_PASSWORD, role="MANAGER"
        )
        cls.inactive_employee = user_model.objects.create_user(
            username="inactive_employee_test",
            password=TEST_PASSWORD,
            is_active=False,
        )
