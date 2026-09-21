from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable


class LiveTableTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.waiter = get_user_model().objects.create_user(username="live_waiter")
        cls.waiter.groups.add(Group.objects.get(name="WAITER"))
        cls.area = Area.objects.create(name="Tầng 1")
        cls.customer = Customer.objects.create(full_name="Khách", phone="0912345678")
        now = timezone.now()
        for number in range(21):
            table = DiningTable.objects.create(code=f"B{number:02d}", area=cls.area, capacity=4)
            Booking.objects.create(customer=cls.customer, customer_name="Khách", customer_phone=cls.customer.phone,
                                   table=table, party_size=2, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1), status="SEATED")

    def setUp(self):
        self.client.force_login(self.waiter)

    def test_fragment_has_filtered_results_without_page_or_form(self):
        response = self.client.get(reverse("seating:table_list"), {"status": "occupied", "area": self.area.pk}, HTTP_X_TABLE_REFRESH="1")
        self.assertContains(response, 'id="table-live-results"')
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "<form")
        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertIn("status=occupied", response.context["query_string"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_refresh_clamps_page_after_customers_leave(self):
        params = {"status": "occupied", "page": 2}
        first = self.client.get(reverse("seating:table_list"), params, HTTP_X_TABLE_REFRESH="1")
        self.assertEqual(first.context["page_obj"].number, 2)
        Booking.objects.all().update(status="COMPLETED")
        response = self.client.get(reverse("seating:table_list"), params, HTTP_X_TABLE_REFRESH="1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_fragment_rechecks_authentication_and_permission(self):
        self.waiter.groups.clear()
        response = self.client.get(reverse("seating:table_list"), HTTP_X_TABLE_REFRESH="1")
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("seating:table_list"), HTTP_X_TABLE_REFRESH="1").status_code, 302)

    def test_normal_page_preserves_fallback_and_loads_refresh_script(self):
        response = self.client.get(reverse("seating:table_list"))
        self.assertContains(response, "table-live.js")
        self.assertContains(response, "data-table-filters")
        self.assertContains(response, "Cập nhật ngay")
        self.assertContains(response, 'id="table-live-results"')
