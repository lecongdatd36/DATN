from django.contrib.auth import get_user_model
from django.test import TestCase

from . import PASSWORD


class UserModelTests(TestCase):
    def test_user_has_no_role_field_and_password_is_hashed(self):
        user = get_user_model().objects.create_user(username="employee", password=PASSWORD)
        self.assertFalse(hasattr(user, "role"))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_superuser_has_admin_flags(self):
        user = get_user_model().objects.create_superuser(username="admin_test", password=PASSWORD)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.groups.filter(name="MANAGER").exists())
