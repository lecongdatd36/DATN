from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import save_booking, transition_booking
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable
from apps.seating.selectors import tables


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TableOccupancyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.waiter = get_user_model().objects.create_user(username="occupancy_waiter", password="Test-password!123")
        cls.waiter.groups.add(Group.objects.get(name="WAITER"))
        cls.area = Area.objects.create(name="Tầng 1")
        cls.table = DiningTable.objects.create(code="B01", capacity=4, area=cls.area)
        cls.customer = Customer.objects.create(full_name="Khách kiểm thử", phone="0912345678")
        cls.now = timezone.now().replace(second=0, microsecond=0)

    def setUp(self):
        self.client.force_login(self.waiter)

    def booking(self, status, *, start=None, end=None, table=None):
        return Booking.objects.create(
            customer=self.customer, customer_name=self.customer.full_name, customer_phone=self.customer.phone,
            table=table or self.table, party_size=2, starts_at=start or self.now - timedelta(hours=1),
            ends_at=end or self.now + timedelta(hours=1), status=status,
        )

    def listing(self, params=None):
        with patch("apps.seating.views.timezone.now", return_value=self.now):
            return self.client.get(reverse("seating:table_list"), params or {})

    def test_seated_party_is_visible_even_after_planned_end(self):
        booking = self.booking("SEATED", end=self.now - timedelta(minutes=1))
        response = self.listing()
        self.assertContains(response, "Đang phục vụ")
        self.assertContains(response, "Đã quá giờ dự kiến, chưa rời bàn")
        self.assertContains(response, booking.get_absolute_url())
        self.assertNotContains(response, "Có thể sử dụng")
        self.assertEqual(response.context["page_obj"][0].current_status, "occupied")
        self.assertEqual(list(tables(status="empty", at=self.now)), [])
        booking.refresh_from_db()
        self.assertEqual(booking.status, "SEATED")

    def test_actual_receiving_and_completion_update_table_page(self):
        start = self.now + timedelta(hours=1)
        booking = save_booking(actor=self.waiter, customer_phone=self.customer.phone, table_id=self.table.pk,
                               party_size=2, starts_at=start, duration_minutes=120)
        booking = transition_booking(actor=self.waiter, booking_id=booking.pk, target="CONFIRMED", expected_status=booking.status, expected_revision=booking.revision)
        self.now = start
        self.assertEqual(self.listing().context["page_obj"][0].current_status, "reserved")
        with patch("apps.bookings.services.timezone.now", return_value=self.now):
            booking = transition_booking(actor=self.waiter, booking_id=booking.pk, target="SEATED", expected_status=booking.status, expected_revision=booking.revision)
        self.assertEqual(self.listing().context["page_obj"][0].current_status, "occupied")
        with patch("apps.bookings.services.timezone.now", return_value=self.now + timedelta(minutes=1)):
            booking = transition_booking(actor=self.waiter, booking_id=booking.pk, target="COMPLETED", expected_status=booking.status, expected_revision=booking.revision)
        self.assertEqual(self.listing().context["page_obj"][0].current_status, "empty")

    def test_current_reservations_hold_table_and_future_reservation_does_not(self):
        future = self.booking("CONFIRMED", start=self.now + timedelta(hours=1), end=self.now + timedelta(hours=2))
        table = tables(at=self.now).get()
        self.assertEqual(table.current_status, "empty")
        self.assertEqual(table.next_booking_id, future.pk)
        self.assertContains(self.listing(), "Có lịch lúc")
        for status in ("PENDING", "CONFIRMED"):
            current = self.booking(status)
            self.assertEqual(tables(at=self.now).get().current_status, "reserved")
            self.assertContains(self.listing(), current.get_absolute_url())
            current.delete()

    def test_end_boundary_expired_and_terminal_bookings_do_not_hold_table(self):
        for status in ("PENDING", "CONFIRMED"):
            self.booking(status, end=self.now)
        for status in ("CANCELLED", "NO_SHOW", "COMPLETED"):
            self.booking(status)
        table = tables(at=self.now).get()
        self.assertEqual(table.current_status, "empty")
        self.assertIsNone(table.next_booking_id)
        self.assertEqual(len(self.listing().context["page_obj"]), 1)

    def test_occupied_wins_over_current_and_future_reservations(self):
        seated = self.booking("SEATED", end=self.now - timedelta(minutes=1))
        self.booking("CONFIRMED")
        future = self.booking("PENDING", start=self.now + timedelta(hours=2), end=self.now + timedelta(hours=3))
        table = tables(at=self.now).get()
        self.assertEqual(table.current_status, "occupied")
        self.assertEqual(table.current_visit_id, seated.pk)
        self.assertEqual(table.next_booking_id, future.pk)

    def test_filters_match_visible_status_and_preserve_pagination(self):
        self.booking("SEATED")
        reserved = DiningTable.objects.create(code="B02", capacity=4, area=self.area)
        self.booking("PENDING", table=reserved)
        inactive = DiningTable.objects.create(code="B03", capacity=4, area=self.area, is_active=False)
        for index in range(21):
            DiningTable.objects.create(code=f"EMPTY{index:02d}", capacity=4, area=self.area)
        for status, target in (("occupied", self.table), ("reserved", reserved), ("inactive", inactive)):
            response = self.listing({"status": status})
            self.assertEqual(list(response.context["page_obj"]), [target])
        response = self.listing({"status": "empty", "area": self.area.pk, "page": 2})
        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(response.context["page_obj"]), 1)
        self.assertIn("status=empty", response.context["query_string"])

    def test_closed_area_is_not_empty_and_seated_party_is_not_hidden(self):
        Area.objects.filter(pk=self.area.pk).update(is_active=False)
        self.assertEqual(tables(at=self.now).get().current_status, "inactive")
        self.assertFalse(tables(status="empty", at=self.now).exists())
        self.booking("SEATED")
        response = self.listing()
        self.assertEqual(response.context["page_obj"][0].current_status, "occupied")
        self.assertContains(response, "Khu vực đã ngừng sử dụng")

    def test_booking_links_require_booking_permission_and_query_count_is_bounded(self):
        booking = self.booking("SEATED")
        viewer = get_user_model().objects.create_user(username="table_only")
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="seating", codename="view_diningtable"))
        self.client.force_login(viewer)
        response = self.listing()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, booking.get_absolute_url())
        self.assertContains(response, "Đang phục vụ")
        with self.assertNumQueries(1):
            result = list(tables(at=self.now))
            self.assertEqual(result[0].current_visit_id, booking.pk)
