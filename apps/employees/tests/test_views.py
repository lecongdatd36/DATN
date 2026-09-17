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
        manager_position = JobPosition.objects.get(code="MANAGER")
        cls.manager = user_model.objects.create_user(username="manager", password=PASSWORD, is_staff=True)
        EmployeeProfile.objects.create(user=cls.manager, employee_code="NV0100", full_name="Manager", phone="0903000001", job_position=manager_position, join_date=date.today())
        cls.manager.groups.add(manager_position.group)
        cls.employee_user = user_model.objects.create_user(username="waiter01", password=PASSWORD)
        cls.employee = EmployeeProfile.objects.create(user=cls.employee_user, employee_code="NV0101", full_name="Nguyen Van A", phone="0903000002", job_position=JobPosition.objects.get(code="WAITER"), join_date=date.today())

    def setUp(self):
        self.client.force_login(self.manager)

    def test_employee_page_lists_profile_and_account(self):
        response = self.client.get(reverse("employees:employee_list"))
        self.assertContains(response, self.employee.employee_code)
        self.assertContains(response, self.employee_user.username)

    def test_employee_create_redirects_to_account_creation(self):
        response = self.client.get(reverse("employees:employee_create"))
        self.assertRedirects(response, f"{reverse('accounts:account_create')}?type=EMPLOYEE")

    def test_resign_locks_account(self):
        response = self.client.post(reverse("employees:employee_status", args=[self.employee.pk]), {"status": EmploymentStatus.RESIGNED, "resignation_date": date.today().isoformat()})
        self.assertRedirects(response, reverse("employees:employee_list"))
        self.employee_user.refresh_from_db()
        self.assertFalse(self.employee_user.is_active)

    def test_delete_removes_profile_and_user_and_keeps_delete_snapshot(self):
        response = self.client.post(reverse("employees:employee_delete", args=[self.employee.pk]))
        self.assertRedirects(response, reverse("employees:employee_list"))
        self.assertFalse(EmployeeProfile.objects.filter(pk=self.employee.pk).exists())
        self.assertFalse(get_user_model().objects.filter(pk=self.employee_user.pk).exists())
        log = EmployeeActivityLog.objects.get(action=EmployeeActivityLog.Action.DELETE)
        self.assertEqual(log.employee_code_snapshot, "NV0101")
        self.assertIsNone(log.employee_id)

    def test_employee_cannot_manage_employees(self):
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.get(reverse("employees:employee_list")).status_code, 403)
