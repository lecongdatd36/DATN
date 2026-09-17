from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import EmployeeProfile, JobPosition
from . import PASSWORD


class AccountViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        manager_position = JobPosition.objects.get(code="MANAGER")
        cls.manager = user_model.objects.create_user(username="manager", password=PASSWORD, is_staff=True)
        EmployeeProfile.objects.create(user=cls.manager, employee_code="NV0100", full_name="Manager", phone="0902000001", job_position=manager_position, join_date=date.today())
        cls.manager.groups.add(manager_position.group)

    def setUp(self):
        self.client.force_login(self.manager)

    def test_create_account_form_creates_manager_or_employee_in_one_flow(self):
        response = self.client.post(reverse("accounts:account_create"), {
            "username": "waiter01", "email": "waiter@example.test", "password1": "Waiter-Password!9642", "password2": "Waiter-Password!9642",
            "account_type": "EMPLOYEE", "job_position": JobPosition.objects.get(code="WAITER").pk,
            "employee_code": "NV0101", "full_name": "Waiter One", "phone": "0902000002", "join_date": date.today().isoformat(), "employment_status": "WORKING",
        })
        self.assertRedirects(response, reverse("accounts:account_list"))
        employee = EmployeeProfile.objects.get(employee_code="NV0101")
        self.assertTrue(employee.user.groups.filter(name="WAITER").exists())

    def test_employee_create_redirects_to_account_create(self):
        response = self.client.get(reverse("employees:employee_create"))
        self.assertRedirects(response, f"{reverse('accounts:account_create')}?type=EMPLOYEE")

    def test_account_list_is_separate_from_employee_list(self):
        response = self.client.get(reverse("accounts:account_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.manager.username)

    def test_manager_can_view_manager_account_but_cannot_edit_it(self):
        detail = self.client.get(reverse("accounts:account_detail", args=[self.manager.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Quản trị viên / Quản lý")
        self.assertContains(detail, "Quản trị viên / Quản lý")
        self.assertNotContains(detail, "get_role_display")
        self.assertEqual(
            self.client.get(reverse("accounts:account_update", args=[self.manager.pk])).status_code,
            403,
        )
