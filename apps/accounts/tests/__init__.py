from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import EmployeeProfile, JobPosition

PASSWORD = "Only-For-Tests!8537"


class AccountTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.manager_position = JobPosition.objects.get(code="MANAGER")
        cls.waiter_position = JobPosition.objects.get(code="WAITER")
        cls.manager = user_model.objects.create_user(username="manager_test", password=PASSWORD, is_staff=True)
        cls.manager_profile = EmployeeProfile.objects.create(
            user=cls.manager, employee_code="NV0001", full_name="Manager Test", phone="0901000001",
            job_position=cls.manager_position, join_date=date.today(),
        )
        cls.manager.groups.add(cls.manager_position.group)
        cls.employee = user_model.objects.create_user(username="employee_test", email="employee@example.test", password=PASSWORD)
        cls.employee_profile = EmployeeProfile.objects.create(
            user=cls.employee, employee_code="NV0002", full_name="Employee Test", phone="0901000002",
            job_position=cls.waiter_position, join_date=date.today(),
        )
