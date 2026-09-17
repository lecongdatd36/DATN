from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.employees.models import EmployeeProfile, JobPosition
from apps.employees.services import create_employee, update_employee


class EmployeeModelTests(TestCase):
    def test_employee_profile_is_linked_to_user(self):
        user = get_user_model().objects.create_user(username="waiter01", password="Only-For-Tests!8537")
        employee = EmployeeProfile.objects.create(
            user=user, employee_code="NV0001", full_name="Nguyen Van A", phone="0901234567",
            job_position=JobPosition.WAITER, join_date=date.today(),
        )
        self.assertEqual(str(employee), "NV0001 - Nguyen Van A")
        self.assertEqual(user.employee_profile, employee)

    def test_manager_can_create_and_update_employee_transactionally(self):
        manager = get_user_model().objects.create_user(
            username="manager", password="Only-For-Tests!8537", role="MANAGER"
        )
        employee = create_employee(
            actor=manager,
            user_data={"username": "waiter02", "email": "waiter@example.test"},
            profile_data={
                "employee_code": "NV0002", "full_name": "Tran Thi B", "phone": "0912345678",
                "job_position": JobPosition.WAITER, "join_date": date.today(),
            },
            password="New-Employee!9642",
        )
        update_employee(
            actor=manager,
            employee_id=employee.pk,
            user_data={"username": "cashier02", "email": "cashier@example.test"},
            profile_data={"full_name": "Tran Thi C", "phone": "0912345679", "job_position": "CASHIER", "join_date": date.today(), "employee_code": "NV0002"},
            password="Updated-Employee!9642",
        )
        employee.refresh_from_db()
        self.assertEqual(employee.full_name, "Tran Thi C")
        self.assertTrue(employee.user.check_password("Updated-Employee!9642"))
