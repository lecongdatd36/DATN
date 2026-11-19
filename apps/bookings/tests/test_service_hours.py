from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.forms import BookingForm, PublicAvailabilityForm, PublicReservationForm
from apps.bookings.models import Booking, BookingSettings, BookingSettingsLog
from apps.bookings.services import create_public_booking, save_booking, update_booking_settings
from apps.customers.models import Customer, CustomerActivityLog
from apps.seating.models import Area, DiningTable


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReservationHoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser(username="hours_admin")
        cls.area = Area.objects.create(name="Giờ phục vụ")
        cls.table = DiningTable.objects.create(code="H04", area=cls.area, capacity=4)
        cls.customer = Customer.objects.create(full_name="Khách có sẵn", phone="0912345678")

    def start(self, hour, minute=0):
        day = timezone.localdate() + timedelta(days=2)
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    def save(self, hour=18, **changes):
        return save_booking(**{ "actor": self.staff, "customer_phone": self.customer.phone,
            "table_id": self.table.pk, "party_size": 2, "starts_at": self.start(hour), **changes})

    def public(self, hour=18, **changes):
        return create_public_booking(**{"full_name": "Tên người đặt", "phone": self.customer.phone,
            "starts_at": self.start(hour), "party_size": 2, **changes})

    def params(self, hour=18, **changes):
        return {"starts_at": self.start(hour).strftime("%Y-%m-%dT%H:%M"), "party_size": 2, **changes}

    def test_default_hours_and_late_arrival_are_capped_at_closing(self):
        settings = BookingSettings.objects.get(pk=1)
        self.assertEqual((settings.opening_time, settings.last_booking_time, settings.closing_time), (time(9), time(21), time(22)))
        morning = self.save(hour=9)
        self.assertEqual(morning.duration_minutes, 120)
        late = self.public(hour=21)
        self.assertEqual(late.duration_minutes, 60)
        self.assertEqual(timezone.localtime(late.ends_at).time(), time(22))

    def test_before_opening_after_last_arrival_and_midnight_rejected_by_services(self):
        for start in (self.start(0), self.start(8, 59), self.start(21, 1), self.start(22)):
            for create in (self.save, self.public):
                with self.subTest(start=start, create=create.__name__), self.assertRaises(ValidationError):
                    create(starts_at=start)
        self.assertFalse(Booking.objects.exists())

    def test_staff_custom_duration_and_direct_end_cannot_cross_closing(self):
        booking = self.save(hour=21, duration_minutes=180)
        self.assertEqual(booking.duration_minutes, 60)
        with self.assertRaises(ValidationError):
            self.save(hour=20, ends_at=self.start(23))
        with self.assertRaises(ValidationError):
            self.save(hour=18, duration_minutes=0)

    def test_forms_share_hours_validation_and_public_ignores_forged_duration(self):
        for form_class in (PublicReservationForm, PublicAvailabilityForm, BookingForm):
            payload = {**self.params(hour=21), "full_name": "Khách", "phone": self.customer.phone,
                       "customer_phone": self.customer.phone, "table": self.table.pk}
            form = form_class(data=payload)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["ends_at"], self.start(22))
            bad = form_class(data={**payload, **self.params(hour=0)})
            self.assertFalse(bad.is_valid())
            self.assertIn("starts_at", bad.errors)
        for form_class in (PublicReservationForm, PublicAvailabilityForm):
            form = form_class(data={**payload, "duration_minutes": 1})
            self.assertNotIn("duration_minutes", form.fields)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["ends_at"], self.start(22))

    def test_online_post_and_search_use_same_shortened_slot(self):
        search = self.client.get(reverse("customer_reservations:check"), self.params(hour=21))
        self.assertTrue(search.context["searched"])
        self.assertNotContains(search, 'name="duration_minutes"')
        response = self.client.post(reverse("customer_reservations:create"), {
            **self.params(hour=21), "full_name": "Khách online", "phone": self.customer.phone, "duration_minutes": 1,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Booking.objects.get().duration_minutes, 60)

    def test_changed_hours_apply_to_new_bookings_with_audit_and_revision(self):
        original = self.save(hour=18)
        settings = update_booking_settings(actor=self.staff, default_duration_minutes=120, expected_revision=1,
            opening_time=time(9), closing_time=time(21), last_booking_time=time(20))
        self.assertEqual(settings.revision, 2)
        self.assertEqual(BookingSettingsLog.objects.get().new_hours["last_booking_time"], "20:00")
        original.refresh_from_db()
        self.assertEqual(original.duration_minutes, 120)
        with self.assertRaises(ValidationError):
            self.save(hour=21)
        for changes in ({"opening_time": time(22)}, {"last_booking_time": time(21)}):
            with self.assertRaises(ValidationError):
                update_booking_settings(actor=self.staff, default_duration_minutes=120, expected_revision=2, **changes)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BookingSettings.objects.filter(pk=1).update(last_booking_time=time(22))

    def test_staff_lookup_requires_permission_and_returns_only_name_and_phone(self):
        url = reverse("bookings:customer_lookup")
        self.assertEqual(self.client.get(url, {"phone": self.customer.phone}).status_code, 302)
        self.client.force_login(self.staff)
        response = self.client.get(url, {"phone": "+84 912 345 678"})
        self.assertEqual(response.json(), {"found": True, "phone": self.customer.phone, "name": self.customer.full_name})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(self.client.get(url, {"phone": "0901234567"}).json()["found"])
        self.assertEqual(self.client.get(url, {"phone": "bad"}).status_code, 400)
        outsider = get_user_model().objects.create_user(username="hours_outsider")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url, {"phone": self.customer.phone}).status_code, 403)

    def test_new_customer_created_with_booking_and_existing_name_is_preserved(self):
        booking = self.save(customer_phone="0901234567", customer_name="  Khách   mới ")
        self.assertEqual(booking.customer.full_name, "Khách mới")
        self.assertTrue(CustomerActivityLog.objects.filter(customer=booking.customer).exists())
        other = self.save(hour=21, customer_name="Không ghi đè tên cũ")
        self.assertEqual(other.customer_name, self.customer.full_name)

    def test_failed_booking_rolls_back_new_customer(self):
        self.save()
        with self.assertRaises(ValidationError):
            self.save(customer_phone="0901234567", customer_name="Khách mới")
        self.assertFalse(Customer.objects.filter(phone="0901234567").exists())

    def test_staff_post_creates_customer_inline_and_can_edit_unchanged_recent_arrival(self):
        self.client.force_login(self.staff)
        payload = {**self.params(hour=18), "customer_phone": "0901234567", "customer_name": "Khách mới",
                   "table": self.table.pk}
        response = self.client.post(reverse("bookings:create"), payload)
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get()
        self.assertEqual(booking.customer.full_name, "Khách mới")
        with patch("django.utils.timezone.now", return_value=self.start(18, 5)):
            response = self.client.post(reverse("bookings:update", args=[booking.pk]), {
                **payload, "party_size": 3, "expected_revision": booking.revision,
            })
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.party_size, 3)

    def test_booking_permission_does_not_grant_customer_creation(self):
        actor = get_user_model().objects.create_user(username="booking_only")
        actor.user_permissions.add(Permission.objects.get(codename="manage_booking"))
        with self.assertRaises(ValidationError):
            self.save(actor=actor, customer_phone="0901234567", customer_name="Khách mới")
        self.assertFalse(Customer.objects.filter(phone="0901234567").exists())

    def test_table_options_filter_capacity_conflicts_and_keep_current_booking(self):
        self.client.force_login(self.staff)
        url = reverse("bookings:table_options")
        params = self.params(hour=21, booking_id="")
        self.assertEqual(len(self.client.get(url, params).json()["tables"]), 1)
        self.assertEqual(self.client.get(url, {**params, "booking_id": "invalid"}).status_code, 400)
        booked = self.save(hour=21)
        self.assertEqual(self.client.get(url, params).json()["tables"], [])
        rows = self.client.get(url, {**params, "booking_id": booked.pk}).json()["tables"]
        self.assertEqual([row["id"] for row in rows], [self.table.pk])
        self.assertEqual(self.client.get(url, {**params, "party_size": 5}).json()["tables"], [])
        self.assertEqual(self.client.get(url, self.params(hour=0)).status_code, 400)
        self.assertEqual(self.client.post(url, params).status_code, 405)
