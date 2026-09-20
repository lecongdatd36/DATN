from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.forms import BookingForm, SlotForm
from apps.bookings.models import Booking, BookingSettings, BookingSettingsLog
from apps.bookings.services import save_booking, transition_booking, update_booking_settings
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BookingDurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="duration_manager", password="Secret!Test123")
        cls.manager.groups.add(Group.objects.get(name="MANAGER"))
        cls.waiter = get_user_model().objects.create_user(username="duration_waiter", password="Secret!Test123")
        cls.waiter.groups.add(Group.objects.get(name="WAITER"))
        cls.superuser = get_user_model().objects.create_superuser(username="duration_root", password="Secret!Test123")
        cls.area = Area.objects.create(name="Tầng 1")
        cls.table = DiningTable.objects.create(code="B01", area=cls.area, capacity=4)
        cls.customer = Customer.objects.create(full_name="Khách An", phone="0912345678")
        cls.start = (timezone.now() + timedelta(days=1)).replace(hour=16, minute=30, second=0, microsecond=0)  # 23:30 Vietnam, crosses midnight.

    def create(self, **changes):
        data = dict(actor=self.waiter, customer_phone=self.customer.phone, table_id=self.table.pk, party_size=2, starts_at=self.start)
        return save_booking(**{**data, **changes})

    def payload(self):
        return {"customer_phone": self.customer.phone, "table": self.table.pk, "party_size": 2,
                "starts_at": timezone.localtime(self.start).strftime("%Y-%m-%dT%H:%M")}

    def configure(self, minutes, **changes):
        return update_booking_settings(**{ "actor": self.manager, "default_duration_minutes": minutes,
            "expected_revision": BookingSettings.objects.get(pk=1).revision, **changes})

    def test_default_duration_and_no_end_input_with_or_without_javascript(self):
        self.client.force_login(self.waiter)
        response = self.client.get(reverse("bookings:create"))
        self.assertNotContains(response, 'name="ends_at"')
        self.assertEqual(response.context["form"]["duration_minutes"].value(), 120)
        self.assertContains(response, "booking-duration.js")
        response = self.client.post(reverse("bookings:create"), self.payload())
        booking = Booking.objects.get()
        self.assertRedirects(response, booking.get_absolute_url())
        self.assertEqual(booking.ends_at, self.start + timedelta(minutes=120))

    def test_setting_only_affects_new_bookings_and_existing_duration_is_preserved(self):
        old = self.create(duration_minutes=90)
        self.configure(180)
        old.refresh_from_db()
        self.assertEqual(old.ends_at, self.start + timedelta(minutes=90))
        self.client.force_login(self.waiter)
        response = self.client.get(reverse("bookings:update", args=[old.pk]))
        self.assertEqual(response.context["form"]["duration_minutes"].value(), 90)
        response = self.client.post(reverse("bookings:update", args=[old.pk]), {**self.payload(), "expected_revision": old.revision})
        self.assertRedirects(response, old.get_absolute_url())
        old.refresh_from_db()
        self.assertEqual(old.duration_minutes, 90)
        self.assertEqual(old.activity_logs.count(), 1)
        new = self.create(starts_at=self.start + timedelta(days=1))
        self.assertEqual(new.duration_minutes, 180)

    def test_explicit_duration_overrides_default_and_forged_end_is_ignored(self):
        self.configure(180)
        self.client.force_login(self.waiter)
        response = self.client.post(reverse("bookings:create"), {**self.payload(), "duration_minutes": 45, "ends_at": "2099-01-01T12:00"})
        booking = Booking.objects.get()
        self.assertRedirects(response, booking.get_absolute_url())
        self.assertEqual(booking.ends_at, self.start + timedelta(minutes=45))

    def test_form_and_service_reject_invalid_durations(self):
        for value in (0, -1, 1441, 1.5, "invalid"):
            with self.subTest(value=value):
                form = BookingForm(data={**self.payload(), "duration_minutes": value})
                self.assertFalse(form.is_valid())
                self.assertIn("duration_minutes", form.errors)
                with self.assertRaises(ValidationError):
                    self.create(duration_minutes=value)
        with self.assertRaises(ValidationError):
            self.create(duration_minutes=120, ends_at=self.start + timedelta(hours=3))

    def test_derived_end_conflict_and_midnight_boundary(self):
        first = self.create(duration_minutes=120)
        self.assertNotEqual(timezone.localtime(first.starts_at).date(), timezone.localtime(first.ends_at).date())
        with self.assertRaises(ValidationError):
            self.create(starts_at=self.start + timedelta(minutes=119), duration_minutes=90)
        second = self.create(starts_at=first.ends_at, duration_minutes=60)
        self.assertEqual(second.ends_at, first.ends_at + timedelta(minutes=60))

    def test_availability_preserves_custom_duration_and_computes_end(self):
        self.client.force_login(self.waiter)
        params = {"starts_at": self.payload()["starts_at"], "party_size": 2, "duration_minutes": 75}
        response = self.client.get(reverse("bookings:availability"), params)
        self.assertEqual(response.context["planned_end"], self.start + timedelta(minutes=75))
        link = response.context["page_obj"][0].booking_url
        self.assertIn("duration_minutes=75", link)
        self.assertNotIn("ends_at", link)
        self.assertEqual(self.client.get(link).context["form"]["duration_minutes"].value(), "75")
        # A link formed before the setting changes retains its explicitly selected duration.
        self.configure(180)
        self.assertEqual(self.client.get(link).context["form"]["duration_minutes"].value(), "75")

    def test_settings_permissions_get_post_service_and_navigation(self):
        url = reverse("bookings:settings")
        for actor, allowed in ((self.manager, True), (self.superuser, True), (self.waiter, False)):
            self.client.force_login(actor)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200 if allowed else 403)
            listing = self.client.get(reverse("bookings:list"))
            if allowed:
                self.assertContains(listing, url)
                response = self.client.post(url, {"default_duration_minutes": 90, "expected_revision": BookingSettings.objects.get(pk=1).revision})
                self.assertRedirects(response, url)
            else:
                self.assertNotContains(listing, url)
                self.assertEqual(self.client.post(url, {"default_duration_minutes": 90, "expected_revision": 1}).status_code, 403)
                with self.assertRaises(PermissionDenied):
                    self.configure(60, actor=actor)

    def test_stale_or_revoked_settings_changes_fail(self):
        original_revision = BookingSettings.objects.get(pk=1).revision
        self.configure(90)
        with self.assertRaises(ValidationError):
            self.configure(180, expected_revision=original_revision)
        self.assertTrue(self.manager.has_perm("bookings.configure_bookings"))
        self.manager.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.configure(60)

    def test_settings_audit_rollback_csrf_and_no_get_writes(self):
        self.client.force_login(self.manager)
        self.client.get(reverse("bookings:settings"))
        self.assertEqual(BookingSettingsLog.objects.count(), 0)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.manager)
        self.assertEqual(csrf.post(reverse("bookings:settings"), {"default_duration_minutes": 90, "expected_revision": 1}).status_code, 403)
        with patch("apps.bookings.services.BookingSettingsLog.objects.create", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                self.configure(90)
        self.assertEqual(BookingSettings.objects.get(pk=1).default_duration_minutes, 120)
        self.configure(90)
        self.configure(90)
        self.assertEqual(BookingSettingsLog.objects.count(), 1)
        self.assertEqual(BookingSettingsLog.objects.get().previous_minutes, 120)

    def test_database_settings_constraints(self):
        for changes in ({"default_duration_minutes": 0}, {"default_duration_minutes": 1441}, {"id": 2}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                BookingSettings.objects.filter(pk=1).update(**changes)

    def test_overrun_alert_links_next_booking_without_auto_completion(self):
        first = self.create()
        first = transition_booking(actor=self.waiter, booking_id=first.pk, target="CONFIRMED", expected_status=first.status, expected_revision=first.revision)
        with patch("apps.bookings.services.timezone.now", return_value=self.start):
            first = transition_booking(actor=self.waiter, booking_id=first.pk, target="SEATED", expected_status=first.status, expected_revision=first.revision)
        second = self.create(starts_at=first.ends_at, duration_minutes=60)
        self.client.force_login(self.waiter)
        with patch("django.utils.timezone.now", return_value=first.ends_at + timedelta(minutes=1)):
            response = self.client.get(reverse("bookings:list"))
            self.assertContains(response, "có nguy cơ chậm")
            self.assertContains(response, second.get_absolute_url())
            self.assertContains(self.client.get(first.get_absolute_url()), "Đang phục vụ")
            self.assertContains(self.client.get(second.get_absolute_url()), "phục vụ quá giờ dự kiến")
        first.refresh_from_db()
        self.assertEqual(first.status, "SEATED")
        self.assertEqual(first.revision, 3)
