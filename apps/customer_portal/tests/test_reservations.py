from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking, BookingSettings
from apps.bookings.services import create_public_booking
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable


class CustomerReservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        BookingSettings.objects.get_or_create(pk=1, defaults={"default_duration_minutes": 120})
        cls.area = Area.objects.create(name="Tầng 1", is_active=True)
        cls.table = DiningTable.objects.create(code="B01", area=cls.area, capacity=4, is_active=True)

    def starts_at(self, minutes=30):
        return timezone.now() + timedelta(minutes=minutes)

    def test_public_booking_creates_customer_and_stays_pending(self):
        booking = create_public_booking(
            full_name="  Nguyễn   An ", phone="+84 912 345 678", starts_at=self.starts_at(),
            party_size=2, area_id=self.area.pk, note="Bàn yên tĩnh",
        )

        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.customer_phone, "0912345678")
        self.assertEqual(booking.customer_name, "Nguyễn An")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(booking.table_id, self.table.pk)
        self.assertEqual(booking.table.status, DiningTable.Status.AVAILABLE)
        self.assertTrue(booking.activity_logs.filter(action="Khách tạo đặt bàn online").exists())

    def test_public_booking_reuses_existing_customer(self):
        customer = Customer.objects.create(full_name="Khách cũ", phone="0912345678")
        booking = create_public_booking(
            full_name="Tên mới", phone="0912345678", starts_at=self.starts_at(), party_size=2,
        )

        self.assertEqual(booking.customer_id, customer.pk)
        self.assertEqual(Customer.objects.count(), 1)

    def test_public_booking_rejects_overlapping_slot(self):
        create_public_booking(full_name="Nguyễn An", phone="0912345678", starts_at=self.starts_at(), party_size=2)

        with self.assertRaises(ValidationError):
            create_public_booking(full_name="Trần Bình", phone="0901234567", starts_at=self.starts_at(), party_size=2)

    def test_lookup_requires_matching_code_and_phone(self):
        booking = create_public_booking(
            full_name="Nguyễn An", phone="0912345678", starts_at=self.starts_at(), party_size=2,
        )
        url = reverse("customer_reservations:lookup")
        wrong = self.client.post(url, {"reservation_code": booking.booking_code, "phone": "0901234567"})
        self.assertEqual(wrong.status_code, 200)
        self.assertContains(wrong, "Không tìm thấy đặt bàn")

        correct = self.client.post(url, {"reservation_code": booking.booking_code, "phone": "0912345678"})
        self.assertRedirects(correct, reverse("customer_reservations:status", args=[booking.pk]))
        status = self.client.get(correct.url)
        self.assertEqual(status.status_code, 200)
        self.assertContains(status, "Chờ xác nhận")
