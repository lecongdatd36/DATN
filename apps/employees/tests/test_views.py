from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import EmployeeActivityLog, EmployeeProfile, EmploymentStatus, JobPosition


PASSWORD = "Only-For-Tests!8537"


class EmployeeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.manager = user_model.objects.create_user(username="manager", password=PASSWORD, role="MANAGER")
        cls.employee_user = user_model.objects.create_user(username="waiter01", password=PASSWORD)
        cls.employee = EmployeeProfile.objects.create(
            user=cls.employee_user,
            employee_code="NV0001",
            full_name="Nguyen Van A",
            phone="0901234567",
            job_position=JobPosition.WAITER,
            join_date=date.today(),
        )

    def setUp(self):
        self.client.force_login(self.manager)

    def employee_payload(self, **overrides):
        payload = {
            "username": "waiter02",
            "email": "waiter02@example.test",
            "password1": "New-Employee!9642",
            "password2": "New-Employee!9642",
            "employee_code": "NV0002",
            "full_name": "Tran Thi B",
            "phone": "0912345678",
            "job_position": JobPosition.CASHIER,
            "join_date": date.today().isoformat(),
            "employment_status": EmploymentStatus.WORKING,
        }
        payload.update(overrides)
        return payload

    def test_manager_can_list_create_view_update_and_view_history(self):
        self.assertEqual(self.client.get(reverse("employees:employee_list")).status_code, 200)
        response = self.client.post(reverse("employees:employee_create"), self.employee_payload())
        self.assertRedirects(response, reverse("employees:employee_list"))
        employee = EmployeeProfile.objects.get(employee_code="NV0002")
        self.assertTrue(EmployeeActivityLog.objects.filter(employee=employee, action="CREATE").exists())
        detail = self.client.get(reverse("employees:employee_detail", kwargs={"pk": employee.pk}))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Tạo mới")
        response = self.client.post(
            reverse("employees:employee_update", kwargs={"pk": employee.pk}),
            self.employee_payload(username="cashier02", full_name="Tran Thi C", password1="", password2=""),
        )
        self.assertRedirects(response, reverse("employees:employee_list"))
        employee.refresh_from_db()
        self.assertEqual(employee.full_name, "Tran Thi C")
        self.assertTrue(EmployeeActivityLog.objects.filter(employee=employee, action="UPDATE").exists())

    def test_resigning_employee_locks_account_and_writes_resign_log(self):
        response = self.client.post(
            reverse("employees:employee_status", kwargs={"pk": self.employee.pk}),
            {"status": EmploymentStatus.RESIGNED},
        )
        self.assertRedirects(response, reverse("employees:employee_list"))
        self.employee.refresh_from_db()
        self.employee_user.refresh_from_db()
        self.assertEqual(self.employee.employment_status, EmploymentStatus.RESIGNED)
        self.assertFalse(self.employee_user.is_active)
        self.assertTrue(EmployeeActivityLog.objects.filter(employee=self.employee, action="RESIGN").exists())

    def test_employee_cannot_access_employee_management(self):
        self.client.force_login(self.employee_user)
        for name, kwargs in (
            ("employee_list", {}),
            ("employee_create", {}),
            ("employee_detail", {"pk": self.employee.pk}),
            ("employee_update", {"pk": self.employee.pk}),
            ("employee_status", {"pk": self.employee.pk}),
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"employees:{name}", kwargs=kwargs)).status_code, 403)

    def test_employee_profile_cannot_be_deleted_from_admin(self):
        admin_user = get_user_model().objects.create_superuser(username="admin", password=PASSWORD)
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:employees_employeeprofile_delete", args=[self.employee.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(EmployeeProfile.objects.filter(pk=self.employee.pk).exists())
