from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.tests import AccountTestCase
from core.permissions import can_access_admin, can_manage_accounts


class PermissionTests(AccountTestCase):
    def test_manager_permission_comes_from_job_position(self):
        self.assertTrue(can_manage_accounts(self.manager))
        self.assertFalse(can_manage_accounts(self.employee))

    def test_admin_permission_requires_staff_and_manager_position(self):
        self.assertTrue(can_access_admin(self.manager))
        self.manager.is_staff = False
        self.assertFalse(can_access_admin(self.manager))

    def test_unknown_employee_user_cannot_manage(self):
        user = get_user_model().objects.create_user(username="orphan", password="x")
        self.assertFalse(can_manage_accounts(user))
