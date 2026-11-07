from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse


PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"
LAPTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeviceLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "CASHIER", "INVENTORY", "KITCHEN"):
            user = get_user_model().objects.create_user(username="device-" + role.lower(), password="test-device-password")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user

    def login(self, role, agent=LAPTOP, **data):
        self.client.logout()
        return self.client.post(reverse("accounts:login"), {
            "username": self.users[role].username, "password": "test-device-password", **data,
        }, HTTP_USER_AGENT=agent)

    def test_every_role_lands_in_correct_workspace_on_phone_and_laptop(self):
        destinations = {"MANAGER": "accounts:workspace", "INVENTORY": "inventory:workspace", "KITCHEN": "kitchen:workspace"}
        for role in self.users:
            for agent in (LAPTOP, PHONE):
                expected = destinations.get(role, "sales:mobile" if agent == PHONE else "sales:workspace")
                with self.subTest(role=role, agent=agent):
                    response = self.login(role, agent)
                    self.assertEqual(response.url, reverse(expected))
                    self.assertEqual(self.client.get(response.url).status_code, 200)

    def test_viewport_hint_and_no_javascript_fallback(self):
        self.assertEqual(self.login("WAITER", PHONE, mobile_view="").url, reverse("sales:mobile"))
        self.assertEqual(self.login("WAITER", LAPTOP, mobile_view="1").url, reverse("sales:mobile"))
        self.assertEqual(self.login("WAITER", PHONE, mobile_view="0").url, reverse("sales:workspace"))

    def test_next_sales_links_keep_order_and_choose_device(self):
        response = self.login("WAITER", PHONE, next=reverse("sales:workspace") + "?order=42#sales-menu")
        self.assertEqual(response.url, reverse("sales:mobile") + "?order=42&page=menu#sales-menu")
        response = self.login("WAITER", PHONE, next=reverse("sales:workspace") + "?open_table=7")
        self.assertEqual(response.url, reverse("sales:mobile") + "?table=7&page=open")
        response = self.login("WAITER", LAPTOP, next=reverse("sales:mobile") + "?page=order&order=42")
        self.assertEqual(response.url, reverse("sales:workspace") + "?order=42")

    def test_safe_next_other_modules_preserved_and_external_next_rejected(self):
        next_url = reverse("bookings:list") + "?status=PENDING"
        self.assertEqual(self.login("MANAGER", PHONE, next=next_url).url, next_url)
        self.assertEqual(self.login("WAITER", PHONE, next="https://example.test/").url, reverse("sales:mobile"))
        explicit_desktop = reverse("sales:workspace") + "?desktop=1"
        self.assertEqual(self.login("WAITER", PHONE, next=explicit_desktop).url, explicit_desktop)

    def test_management_navigation_has_inventory_usage_and_all_management_modules(self):
        self.client.force_login(self.users["MANAGER"])
        response = self.client.get(reverse("sales:mobile"), {"page": "personal"})
        for route in ("inventory:daily_usage", "employees:employee_list", "accounts:account_list", "bookings:settings"):
            self.assertContains(response, reverse(route))
        workspace = self.client.get(reverse("accounts:workspace"))
        self.assertContains(workspace, reverse("sales:mobile") + "?page=personal")
        self.assertContains(workspace, 'data-mobile-notification-open')
        self.client.force_login(self.users["INVENTORY"])
        response = self.client.get(reverse("inventory:daily_usage"))
        self.assertNotContains(response, reverse("accounts:account_list"))
