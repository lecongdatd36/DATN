"""Quyền theo system role được áp dụng đồng nhất ở helper và HTTP."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views import View

from core.decorators import manager_required
from core.mixins import ManagerRequiredMixin
from core.permissions import can_access_admin, can_manage_accounts


@manager_required
def manager_only_view(request):
    return HttpResponse("allowed")


class ManagerOnlyView(ManagerRequiredMixin, View):
    def get(self, request):
        return HttpResponse("allowed")


class PermissionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_account_permission_requires_active_authenticated_manager(self):
        user_model = get_user_model()
        cases = (
            (AnonymousUser(), False),
            (user_model(role="EMPLOYEE", is_active=True), False),
            (user_model(role="EMPLOYEE", is_staff=True, is_active=True), False),
            (user_model(role="MANAGER", is_active=False), False),
            (user_model(role="MANAGER", is_active=True), True),
        )
        for user, expected in cases:
            with self.subTest(user=user, expected=expected):
                self.assertEqual(can_manage_accounts(user), expected)

    def test_admin_permission_also_requires_staff(self):
        user_model = get_user_model()
        cases = (
            (AnonymousUser(), False),
            (user_model(role="MANAGER", is_staff=False, is_active=True), False),
            (user_model(role="MANAGER", is_staff=True, is_active=True), True),
            (user_model(role="MANAGER", is_staff=True, is_active=False), False),
            (user_model(role="EMPLOYEE", is_staff=True, is_active=True), False),
        )
        for user, expected in cases:
            with self.subTest(user=user, expected=expected):
                self.assertEqual(can_access_admin(user), expected)

    def test_decorator_redirects_anonymous_user_to_login(self):
        request = self.factory.get(reverse("accounts:account_list"))
        request.user = AnonymousUser()
        response = manager_only_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.assertIn("next=", response.url)

    def test_decorator_forbids_employee_and_allows_manager(self):
        request = self.factory.get("/protected/")
        request.user = get_user_model()(role="EMPLOYEE", is_active=True)
        with self.assertRaises(PermissionDenied):
            manager_only_view(request)
        request.user = get_user_model()(role="MANAGER", is_active=True)
        self.assertEqual(manager_only_view(request).status_code, 200)

    def test_mixin_redirects_anonymous_and_forbids_employee(self):
        request = self.factory.get("/protected/")
        request.user = AnonymousUser()
        self.assertEqual(ManagerOnlyView.as_view()(request).status_code, 302)
        request.user = get_user_model()(role="EMPLOYEE", is_active=True)
        with self.assertRaises(PermissionDenied):
            ManagerOnlyView.as_view()(request)

    def test_mixin_allows_active_manager_and_forbids_inactive_manager(self):
        request = self.factory.get("/protected/")
        request.user = get_user_model()(role="MANAGER", is_active=True)
        self.assertEqual(ManagerOnlyView.as_view()(request).status_code, 200)
        request.user.is_active = False
        with self.assertRaises(PermissionDenied):
            ManagerOnlyView.as_view()(request)
