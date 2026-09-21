from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.selectors import available_tables
from apps.bookings.services import save_booking, transition_booking
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable
from apps.seating.selectors import tables


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ActualArrivalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = get_user_model().objects.create_superuser(username="arrival_admin", password="Test-password!123")
        cls.customer = Customer.objects.create(full_name="Khách", phone="0912345678")
        cls.area = Area.objects.create(name="Tầng 1")
        cls.table = DiningTable.objects.create(code="B01", area=cls.area, capacity=4)
        cls.day = timezone.localdate() + timedelta(days=2)
        cls.start = timezone.make_aware(datetime.combine(cls.day, datetime.min.time()).replace(hour=19))
        cls.early = cls.start - timedelta(minutes=30)

    def setUp(self):
        self.client.force_login(self.actor)
        self.booking = save_booking(actor=self.actor, customer_phone=self.customer.phone, table_id=self.table.pk,
                                    party_size=2, starts_at=self.start, duration_minutes=120)
        self.booking = self.change(self.booking, "CONFIRMED")

    def change(self, booking, target):
        return transition_booking(actor=self.actor, booking_id=booking.pk, target=target,
                                  expected_status=booking.status, expected_revision=booking.revision)

    def test_early_arrival_records_actual_time_and_preserves_plan(self):
        with patch("django.utils.timezone.now", return_value=self.early):
            response = self.client.get(self.booking.get_absolute_url())
            self.assertContains(response, reverse("bookings:transition", args=[self.booking.pk, "SEATED"]))
            self.assertContains(response, "đến sớm")
            seated = self.change(self.booking, "SEATED")
        self.assertEqual(seated.starts_at, self.start)
        self.assertEqual(seated.ends_at, self.start + timedelta(hours=2))
        self.assertEqual(seated.seated_at, self.early)
        self.assertEqual(tables(at=self.early).get().current_status, "occupied")
        finish = self.start + timedelta(hours=1)
        with patch("django.utils.timezone.now", return_value=finish):
            completed = self.change(seated, "COMPLETED")
        self.assertEqual(completed.completed_at, finish)
        self.assertEqual(completed.seated_at, self.early)
        self.assertEqual(tables(at=finish).get().current_status, "empty")

    def test_early_arrival_blocked_by_reservation_before_original_start(self):
        earlier = save_booking(actor=self.actor, customer_phone=self.customer.phone, table_id=self.table.pk,
                               party_size=2, starts_at=self.start - timedelta(hours=1), ends_at=self.start)
        for status in ("PENDING", "CONFIRMED"):
            Booking.objects.filter(pk=earlier.pk).update(status=status)
            with patch("django.utils.timezone.now", return_value=self.early), self.assertRaises(ValidationError):
                self.change(self.booking, "SEATED")
        self.booking.refresh_from_db()
        self.assertIsNone(self.booking.seated_at)
        self.assertEqual(self.booking.status, "CONFIRMED")

    def test_early_arrival_cannot_take_table_with_overdue_customer(self):
        Booking.objects.create(customer=self.customer, table=self.table, customer_name="Khách trước", customer_phone=self.customer.phone,
                               party_size=2, starts_at=self.start - timedelta(hours=3), ends_at=self.start - timedelta(hours=1), status="SEATED")
        with patch("django.utils.timezone.now", return_value=self.early), self.assertRaises(ValidationError):
            self.change(self.booking, "SEATED")

    def test_early_occupied_interval_blocks_availability_and_new_booking(self):
        with patch("django.utils.timezone.now", return_value=self.early):
            self.change(self.booking, "SEATED")
            start = self.early + timedelta(minutes=5)
            end = self.start
            self.assertFalse(available_tables(starts_at=start, ends_at=end, party_size=2).exists())
            with self.assertRaises(ValidationError):
                save_booking(actor=self.actor, customer_phone=self.customer.phone, table_id=self.table.pk,
                             party_size=2, starts_at=start, ends_at=end)

    def test_wrong_day_expired_and_unconfirmed_cannot_receive(self):
        for now in (self.early - timedelta(days=1), self.start + timedelta(hours=2)):
            with patch("django.utils.timezone.now", return_value=now), self.assertRaises(ValidationError):
                self.change(self.booking, "SEATED")
        self.booking.status = "PENDING"
        self.booking.save(update_fields=["status"])
        with patch("django.utils.timezone.now", return_value=self.early), self.assertRaises(ValidationError):
            self.change(self.booking, "SEATED")

    def test_failed_audit_rolls_back_arrival_timestamp(self):
        with patch("django.utils.timezone.now", return_value=self.early), patch("apps.bookings.services._log", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                self.change(self.booking, "SEATED")
        self.booking.refresh_from_db()
        self.assertIsNone(self.booking.seated_at)
        self.assertEqual(self.booking.status, "CONFIRMED")

    def test_legacy_seated_booking_keeps_unknown_arrival_and_can_finish(self):
        Booking.objects.filter(pk=self.booking.pk).update(status="SEATED")
        self.booking.refresh_from_db()
        with patch("django.utils.timezone.now", return_value=self.start):
            finished = self.change(self.booking, "COMPLETED")
        self.assertIsNone(finished.seated_at)
        self.assertEqual(finished.completed_at, self.start)

    def test_completion_time_constraint_and_repeated_submission(self):
        with patch("django.utils.timezone.now", return_value=self.early):
            seated = self.change(self.booking, "SEATED")
            with self.assertRaises(ValidationError):
                self.change(self.booking, "SEATED")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.filter(pk=seated.pk).update(completed_at=self.early - timedelta(seconds=1))
        with patch("django.utils.timezone.now", return_value=self.early - timedelta(seconds=1)), self.assertRaises(ValidationError):
            self.change(seated, "COMPLETED")
