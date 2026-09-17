from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import EmployeeProfile, JobPosition


class EmployeeModelTests(TestCase):
    def test_employee_profile_uses_job_position_model(self):
        user = get_user_model().objects.create_user(username="waiter01", password="Only-For-Tests!8537")
        position = JobPosition.objects.get(code="WAITER")
        employee = EmployeeProfile.objects.create(user=user, employee_code="NV0001", full_name="Nguyen Van A", phone="0901234567", job_position=position, join_date=date.today())
        self.assertEqual(employee.job_position.code, "WAITER")
        self.assertEqual(user.employee_profile, employee)
