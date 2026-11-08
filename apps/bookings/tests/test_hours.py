from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.forms import SlotForm, PublicAvailabilityForm, PublicReservationForm
from apps.bookings.models import Booking, BookingSettings, BookingSettingsLog
from apps.bookings.services import create_public_booking, save_booking, update_booking_settings
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BookingHoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="hours-manager")
        cls.manager.groups.add(Group.objects.get(name="MANAGER"))
        cls.table = DiningTable.objects.create(code="H01", area=Area.objects.create(name="Hours"), capacity=4)
        cls.customer = Customer.objects.create(full_name="Khách giờ mở cửa", phone="0912345678")
        cls.day = timezone.localdate() + timedelta(days=2)

    def at(self, hour, minute=0):
        return timezone.make_aware(datetime.combine(self.day, time(hour, minute)))

    def public(self, hour, minute=0, duration=120):
        return create_public_booking(full_name=self.customer.full_name, phone=self.customer.phone,
                                     starts_at=self.at(hour, minute), party_size=2, duration_minutes=duration)

    def staff(self, hour, minute=0, duration=120, **kwargs):
        return save_booking(actor=self.manager, customer_phone=self.customer.phone, table_id=self.table.pk,
                            starts_at=self.at(hour, minute), party_size=2, duration_minutes=duration, **kwargs)

    def test_services_reject_night_and_after_closing_without_writes(self):
        for service in (self.public, self.staff):
            for hour, minute, duration in ((3, 0, 120), (8, 59, 120), (22, 0, 1), (21, 0, 61), (21, 30, 180)):
                with self.subTest(service=service.__name__, hour=hour, minute=minute):
                    with self.assertRaisesMessage(ValidationError, "09:00–22:00"):
                        service(hour, minute, duration)
        self.assertEqual(Booking.objects.count(), 0)

    def test_opening_and_exact_closing_accept_local_time(self):
        first, last = self.public(9), self.staff(20)
        self.assertEqual(timezone.localtime(first.starts_at).hour, 9)
        self.assertEqual(timezone.localtime(last.ends_at).hour, 22)

    def test_edit_cannot_move_existing_booking_to_3am(self):
        booking = self.staff(12)
        with self.assertRaises(ValidationError):
            self.staff(3, booking_id=booking.pk, expected_revision=booking.revision)
        booking.refresh_from_db()
        self.assertEqual(timezone.localtime(booking.starts_at).hour, 12)

    def test_all_slot_forms_validate_hours_without_javascript(self):
        for form_class in (SlotForm, PublicAvailabilityForm, PublicReservationForm):
            for hour, duration, field in ((3, 120, "starts_at"), (21, 120, "duration_minutes")):
                form = form_class(data={"starts_at": self.at(hour).strftime("%Y-%m-%dT%H:%M"),
                                        "party_size": 2, "duration_minutes": duration,
                                        "full_name": self.customer.full_name, "phone": self.customer.phone})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_configured_hours_are_logged_and_used_by_service_and_form(self):
        current = BookingSettings.objects.get(pk=1)
        updated = update_booking_settings(actor=self.manager, default_duration_minutes=120,
                                          expected_revision=current.revision, opening_time=time(10), closing_time=time(21))
        self.assertEqual(updated.revision, current.revision + 1)
        self.assertEqual(BookingSettingsLog.objects.get().new_hours["opening_time"], "10:00")
        with self.assertRaisesMessage(ValidationError, "10:00–21:00"):
            self.public(9)
        self.assertIn("10:00–21:00", SlotForm().fields["starts_at"].help_text)
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("bookings:settings")), "Giờ phục vụ")

    def test_invalid_hours_cannot_be_saved(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("bookings:settings"), {
            "opening_time": "22:00", "closing_time": "09:00", "default_duration_minutes": 120,
            "expected_revision": BookingSettings.objects.get(pk=1).revision,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("closing_time", response.context["form"].errors)
        self.assertEqual(BookingSettings.objects.get(pk=1).opening_time, time(9))
