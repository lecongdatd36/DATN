import re
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse


PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile Safari/604.1"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CanonicalMobileTablesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "CASHIER"):
            user = get_user_model().objects.create_user(username="canonical-" + role.lower())
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user

    def test_phone_table_entry_uses_the_actual_order_mobile_screen(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(reverse("seating:table_list"), HTTP_USER_AGENT=PHONE)
                self.assertRedirects(response, reverse("sales:mobile"))
                mobile = self.client.get(response.url)
                self.assertContains(mobile, 'data-mobile-app')
                self.assertNotContains(mobile, 'data-mobile-table-page')

    def test_area_status_search_are_preserved_without_desktop_pagination(self):
        self.client.force_login(self.users["MANAGER"])
        response = self.client.get(reverse("seating:table_list"), {
            "area": "5", "status": "reserved", "q": "VIP", "page": "3",
        }, HTTP_USER_AGENT=PHONE)
        self.assertEqual(urlsplit(response.url).path, reverse("sales:mobile"))
        self.assertEqual(parse_qs(urlsplit(response.url).query), {"area": ["5"], "q": ["VIP"], "status": ["RESERVED"]})

    def test_desktop_and_refresh_fragments_keep_existing_management_behaviour(self):
        self.client.force_login(self.users["MANAGER"])
        url = reverse("seating:table_list")
        self.assertTemplateUsed(self.client.get(url), "seating/table_list.html")
        self.assertTemplateUsed(self.client.get(url, {"desktop": "1"}, HTTP_USER_AGENT=PHONE), "seating/table_list.html")
        self.assertTemplateUsed(self.client.get(url, HTTP_USER_AGENT=PHONE, HTTP_X_TABLE_REFRESH="1"), "seating/includes/table_results.html")

    def test_seating_only_user_is_not_sent_to_a_forbidden_order_screen(self):
        viewer = get_user_model().objects.create_user(username="seating-only")
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="seating", codename="view_diningtable"))
        self.client.force_login(viewer)
        response = self.client.get(reverse("seating:table_list"), HTTP_USER_AGENT=PHONE)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-canonical-mobile-tables')

    def test_each_role_gets_the_same_navigation_in_management_and_order(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(user)
                links = []
                for route in ("accounts:workspace", "sales:mobile"):
                    response = self.client.get(reverse(route))
                    source = response.content.decode()
                    nav = re.search(r'<nav class="m-nav\b[^>]*>(.*?)</nav>', source, re.S).group(1)
                    links.append(re.findall(r'href="([^"]+)"', nav))
                    self.assertContains(response, 'data-mobile-notification-open')
                self.assertEqual(links[0], links[1])
