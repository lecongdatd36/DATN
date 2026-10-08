from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking, BookingActivityLog
from apps.bookings.selectors import available_tables
from apps.bookings.services import expire_overdue_bookings, save_booking, transition_booking
from apps.customers.models import Customer
from apps.customers.services import delete_customer
from apps.seating.models import Area, DiningTable
from apps.seating.services import save_area, save_table


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BookingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            actor = get_user_model().objects.create_user(username=role.lower(), password="Secret!Test123", is_staff=role == "MANAGER")
            actor.groups.add(Group.objects.get(name=role))
            cls.users[role] = actor
        cls.manager = cls.users["MANAGER"]
        cls.superuser = get_user_model().objects.create_superuser(username="root", password="Secret!Test123")
        cls.area = Area.objects.create(name="Tầng 1")
        cls.table = DiningTable.objects.create(code="B01", area=cls.area, capacity=4)
        cls.other_table = DiningTable.objects.create(code="B02", area=cls.area, capacity=8)
        cls.customer = Customer.objects.create(full_name="Khách An", phone="0912345678")
        cls.start = (timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)
        cls.end = cls.start + timedelta(hours=2)

    def create(self, **kwargs):
        data = dict(actor=self.manager, customer_phone=self.customer.phone, table_id=self.table.pk, party_size=4, starts_at=self.start, ends_at=self.end)
        data.update(kwargs)
        return save_booking(**data)

    def change(self, booking, target, **kwargs):
        data = dict(actor=self.manager, booking_id=booking.pk, target=target, expected_status=booking.status, expected_revision=booking.revision)
        data.update(kwargs)
        return transition_booking(**data)

    def edit(self, booking, **kwargs):
        data = dict(booking_id=booking.pk, expected_revision=booking.revision, customer_phone=booking.customer_phone, table_id=booking.table_id, party_size=booking.party_size, starts_at=booking.starts_at, ends_at=booking.ends_at)
        data.update(kwargs)
        return self.create(**data)

    def payload(self):
        return {"customer_phone": "+84 912 345 678", "table": self.table.pk, "party_size": 4,
                "starts_at": timezone.localtime(self.start).strftime("%Y-%m-%dT%H:%M"),
                "duration_minutes": 120}

    def test_three_roles_create_and_manage_and_two_are_denied(self):
        for role, actor in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(actor)
                allowed = role in ("MANAGER", "WAITER", "CASHIER")
                for name in ("list", "create", "availability"):
                    self.assertEqual(self.client.get(reverse(f"bookings:{name}")).status_code, 200 if allowed else 403)
                data = self.payload()
                data["table"] = self.other_table.pk
                if allowed:
                    response = self.client.post(reverse("bookings:create"), data)
                    booking = Booking.objects.latest("pk")
                    self.assertRedirects(response, booking.get_absolute_url())
                    self.change(booking, Booking.Status.CANCELLED, actor=actor)
                else:
                    self.assertEqual(self.client.post(reverse("bookings:create"), data).status_code, 403)
                    with self.assertRaises(PermissionDenied):
                        self.create(actor=actor)

    def test_detail_edit_and_transition_routes_enforce_roles(self):
        booking = self.create()
        for role, actor in self.users.items():
            self.client.force_login(actor)
            allowed = role in ("MANAGER", "WAITER", "CASHIER")
            response = self.client.get(booking.get_absolute_url())
            self.assertEqual(response.status_code, 200 if allowed else 403)
            if allowed:
                if role == "MANAGER":
                    self.assertContains(response, "Nhật ký đặt bàn")
                else:
                    self.assertNotContains(response, "Nhật ký đặt bàn")
            for name, args in (("update", [booking.pk]), ("transition", [booking.pk, "CONFIRMED"])):
                self.assertEqual(self.client.get(reverse(f"bookings:{name}", args=args)).status_code, 200 if allowed else 403)
                if not allowed:
                    self.assertEqual(self.client.post(reverse(f"bookings:{name}", args=args), {}).status_code, 403)

    def test_actor_revoked_or_locked_is_rechecked(self):
        actor = self.users["WAITER"]
        self.assertTrue(actor.has_perm("bookings.manage_booking"))
        actor.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.create(actor=actor)
        get_user_model().objects.filter(pk=self.superuser.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.create(actor=self.superuser)

    def test_superuser_can_manage_without_employee_profile(self):
        booking = self.create(actor=self.superuser)
        confirmed = self.change(booking, Booking.Status.CONFIRMED, actor=self.superuser)
        self.assertEqual(confirmed.status, Booking.Status.CONFIRMED)

    def test_overlap_variants_rejected_but_adjacent_and_other_tables_allowed(self):
        self.create()
        for start, end in ((self.start, self.end), (self.start - timedelta(hours=1), self.start + timedelta(minutes=1)), (self.end - timedelta(minutes=1), self.end + timedelta(hours=1)), (self.start + timedelta(minutes=10), self.end - timedelta(minutes=10)), (self.start - timedelta(hours=1), self.end + timedelta(hours=1))):
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError) as caught:
                self.create(starts_at=start, ends_at=end)
            self.assertIn("table", caught.exception.message_dict)
        self.create(starts_at=self.end, ends_at=self.end + timedelta(hours=1))
        self.create(starts_at=self.start - timedelta(hours=1), ends_at=self.start)
        self.create(table_id=self.other_table.pk)
        self.assertEqual(Booking.objects.count(), 4)

    def test_cancel_or_no_show_releases_slot_and_retains_history(self):
        for target in (Booking.Status.CANCELLED, Booking.Status.NO_SHOW):
            booking = self.create()
            with patch("apps.bookings.services.timezone.now", return_value=self.start):
                terminal = self.change(booking, target)
            self.assertEqual(terminal.status, target)
            self.assertEqual(terminal.activity_logs.count(), 2)
            self.assertIn(self.table, available_tables(starts_at=self.start, ends_at=self.end, party_size=4))
        self.assertEqual(Booking.objects.count(), 2)

    def test_overdue_unattended_booking_is_expired_and_table_is_released(self):
        now = timezone.now()
        expired = Booking.objects.create(
            customer=self.customer,
            table=self.table,
            customer_name=self.customer.full_name,
            customer_phone=self.customer.phone,
            party_size=2,
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(minutes=1),
            status=Booking.Status.CONFIRMED,
        )
        DiningTable.objects.filter(pk=self.table.pk).update(status=DiningTable.Status.RESERVED)

        self.assertEqual(expire_overdue_bookings(at=now), 1)
        expired.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(expired.status, Booking.Status.NO_SHOW)
        self.assertEqual(expired.revision, 2)
        self.assertEqual(self.table.status, DiningTable.Status.AVAILABLE)
        self.assertEqual(expired.activity_logs.get().actor_snapshot, "Hệ thống")
        self.assertEqual(expire_overdue_bookings(at=now), 0)

    def test_expiry_keeps_table_reserved_for_the_next_booking(self):
        now = timezone.now()
        Booking.objects.create(
            customer=self.customer,
            table=self.table,
            customer_name=self.customer.full_name,
            customer_phone=self.customer.phone,
            party_size=2,
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(minutes=1),
            status=Booking.Status.PENDING,
        )
        future = Booking.objects.create(
            customer=self.customer,
            table=self.table,
            customer_name=self.customer.full_name,
            customer_phone=self.customer.phone,
            party_size=2,
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            status=Booking.Status.CONFIRMED,
        )
        DiningTable.objects.filter(pk=self.table.pk).update(status=DiningTable.Status.RESERVED)

        self.assertEqual(expire_overdue_bookings(at=now), 1)
        future.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(future.status, Booking.Status.CONFIRMED)
        self.assertEqual(self.table.status, DiningTable.Status.RESERVED)

    def test_capacity_period_past_and_missing_customer_validation(self):
        invalid = [
            {"party_size": 5}, {"party_size": 0}, {"party_size": 101},
            {"starts_at": self.end}, {"ends_at": self.start},
            {"starts_at": timezone.now() - timedelta(minutes=1)},
            {"customer_phone": "0912345600"}, {"customer_phone": "bad"},
            {"table_id": 999999}, {"starts_at": self.start.replace(tzinfo=None)},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.create(**kwargs)
        self.assertEqual(Booking.objects.count(), 0)

    def test_closed_table_and_area_are_rejected(self):
        DiningTable.objects.filter(pk=self.table.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.create()
        DiningTable.objects.filter(pk=self.table.pk).update(is_active=True)
        Area.objects.filter(pk=self.area.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.create()

    def test_confirmation_receiving_and_completion_workflow(self):
        booking = self.create()
        booking = self.change(booking, Booking.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            self.change(booking, Booking.Status.SEATED)
        with patch("apps.bookings.services.timezone.now", return_value=self.start):
            booking = self.change(booking, Booking.Status.SEATED)
            with self.assertRaises(ValidationError):
                self.change(booking, Booking.Status.CANCELLED)
            booking = self.change(booking, Booking.Status.COMPLETED)
        self.assertEqual(booking.status, Booking.Status.COMPLETED)
        self.assertEqual(booking.activity_logs.count(), 4)
        with self.assertRaises(ValidationError):
            self.change(booking, Booking.Status.PENDING)

    def test_cannot_seat_unconfirmed_or_mark_no_show_early(self):
        booking = self.create()
        with self.assertRaises(ValidationError):
            self.change(booking, Booking.Status.SEATED)
        with self.assertRaises(ValidationError):
            self.change(booking, Booking.Status.NO_SHOW)
        with patch("apps.bookings.services.timezone.now", return_value=self.end):
            with self.assertRaises(ValidationError):
                self.change(booking, Booking.Status.CONFIRMED)

    def test_overdue_seated_party_blocks_next_checkin_until_completed(self):
        first = self.change(self.create(), Booking.Status.CONFIRMED)
        second = self.create(starts_at=self.end, ends_at=self.end + timedelta(hours=1))
        second = self.change(second, Booking.Status.CONFIRMED)
        with patch("apps.bookings.services.timezone.now", return_value=self.start):
            first = self.change(first, Booking.Status.SEATED)
        with patch("apps.bookings.services.timezone.now", return_value=self.end + timedelta(minutes=1)):
            with self.assertRaises(ValidationError):
                self.change(second, Booking.Status.SEATED)
            self.change(first, Booking.Status.COMPLETED)
            second = self.change(second, Booking.Status.SEATED)
        self.assertEqual(second.status, Booking.Status.SEATED)

    def test_edit_confirmed_requires_reconfirmation_and_unchanged_does_not_log(self):
        booking = self.change(self.create(), Booking.Status.CONFIRMED)
        same = self.edit(booking)
        self.assertEqual(same.status, Booking.Status.CONFIRMED)
        self.assertEqual(same.activity_logs.count(), 2)
        edited = self.edit(booking, party_size=3)
        self.assertEqual(edited.status, Booking.Status.PENDING)
        self.assertEqual(edited.revision, booking.revision + 1)
        self.assertEqual(edited.activity_logs.count(), 3)

    def test_stale_edit_or_confirmation_cannot_overwrite_changed_pending_booking(self):
        booking = self.create()
        edited = self.edit(booking, party_size=3)
        with self.assertRaises(ValidationError):
            self.edit(booking, party_size=2)
        with self.assertRaises(ValidationError):
            self.change(booking, Booking.Status.CONFIRMED)
        edited.refresh_from_db()
        self.assertEqual(edited.party_size, 3)
        self.assertEqual(edited.status, Booking.Status.PENDING)

    def test_seated_and_terminal_booking_cannot_be_edited(self):
        booking = self.create()
        cancelled = self.change(booking, Booking.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            self.edit(cancelled)
        active = self.change(self.create(), Booking.Status.CONFIRMED)
        with patch("apps.bookings.services.timezone.now", return_value=self.start):
            active = self.change(active, Booking.Status.SEATED)
            with self.assertRaises(ValidationError):
                self.edit(active)

    def test_customer_and_table_history_protected_after_cancellation(self):
        booking = self.change(self.create(), Booking.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            delete_customer(actor=self.manager, customer_id=self.customer.pk)
        with self.assertRaises(ProtectedError):
            self.table.delete()
        self.customer.full_name = "Tên mới"
        self.customer.save()
        booking.refresh_from_db()
        self.assertEqual(booking.customer_name, "Khách An")

    def test_active_booking_guards_seating_mutations_and_cancel_releases_guard(self):
        booking = self.create()
        other_area = Area.objects.create(name="Tầng 2")
        with self.assertRaises(ValidationError):
            save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)
        base = dict(actor=self.manager, table_id=self.table.pk, code=self.table.code, area_id=self.area.pk, capacity=4, is_active=True)
        for changes in ({"capacity": 3}, {"is_active": False}, {"area_id": other_area.pk}):
            with self.assertRaises(ValidationError):
                save_table(**{**base, **changes})
        save_table(**{**base, "capacity": 5})
        self.change(booking, Booking.Status.CANCELLED)
        save_table(**{**base, "capacity": 2, "is_active": False})
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)

    def test_overdue_seated_booking_still_protects_table_and_area(self):
        booking = self.change(self.create(), Booking.Status.CONFIRMED)
        with patch("apps.bookings.services.timezone.now", return_value=self.start):
            self.change(booking, Booking.Status.SEATED)
        with patch("apps.bookings.selectors.timezone.now", return_value=self.end + timedelta(hours=1)):
            with self.assertRaises(ValidationError):
                save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)

    def test_audit_failure_rolls_back_create_update_and_transition(self):
        with patch("apps.bookings.services._log", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertFalse(Booking.objects.exists())
        booking = self.create()
        with patch("apps.bookings.services._log", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                self.edit(booking, party_size=2)
            with self.assertRaises(RuntimeError):
                self.change(booking, Booking.Status.CONFIRMED)
        booking.refresh_from_db()
        self.assertEqual((booking.party_size, booking.status, booking.revision), (4, "PENDING", 1))
        self.assertEqual(booking.activity_logs.count(), 1)

    def test_actor_deletion_keeps_booking_audit(self):
        actor = self.users["WAITER"]
        booking = self.create(actor=actor)
        actor.delete()
        booking.refresh_from_db()
        self.assertIsNone(booking.created_by_id)
        log = booking.activity_logs.get()
        self.assertIsNone(log.performed_by_id)
        self.assertEqual(log.actor_snapshot, "waiter")

    def test_availability_page_finds_only_suitable_tables_and_prefills_booking(self):
        self.create()
        self.client.force_login(self.users["WAITER"])
        params = {key: value for key, value in self.payload().items() if key in ("starts_at", "duration_minutes", "party_size")}
        response = self.client.get(reverse("bookings:availability"), params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([table.pk for table in response.context["page_obj"]], [self.other_table.pk])
        url = response.context["page_obj"][0].booking_url
        form_response = self.client.get(url)
        self.assertEqual(str(form_response.context["form"]["table"].value()), str(self.other_table.pk))
        self.assertEqual(form_response.context["form"]["starts_at"].value(), params["starts_at"])

    def test_create_edit_and_status_post_workflow_in_local_timezone(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("bookings:create"), self.payload())
        booking = Booking.objects.get()
        self.assertEqual(booking.starts_at, self.start)
        self.assertRedirects(response, booking.get_absolute_url())
        data = {**self.payload(), "party_size": 3, "expected_revision": booking.revision}
        response = self.client.post(reverse("bookings:update", args=[booking.pk]), data)
        self.assertRedirects(response, booking.get_absolute_url())
        booking.refresh_from_db()
        response = self.client.post(reverse("bookings:transition", args=[booking.pk, "CONFIRMED"]), {"expected_status": booking.status, "expected_revision": booking.revision})
        self.assertRedirects(response, booking.get_absolute_url())
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.party_size), ("CONFIRMED", 3))

    def test_invalid_inputs_and_service_errors_are_rendered(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("bookings:create"), {**self.payload(), "party_size": 9})
        self.assertEqual(response.status_code, 200)
        self.assertIn("party_size", response.context["form"].errors)
        response = self.client.post(reverse("bookings:create"), {**self.payload(), "duration_minutes": 0})
        self.assertIn("duration_minutes", response.context["form"].errors)
        self.assertEqual(self.client.get(reverse("bookings:detail", args=[999999])).status_code, 404)
        booking = self.create()
        response = self.client.post(reverse("bookings:transition", args=[booking.pk, "SEATED"]), {"expected_status": booking.status, "expected_revision": booking.revision})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_get_is_readonly_post_requires_csrf_and_anonymous_redirects(self):
        booking = self.create()
        self.assertEqual(self.client.get(reverse("bookings:list")).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.manager)
        for name, args in (("create", []), ("update", [booking.pk]), ("transition", [booking.pk, "CANCELLED"])):
            url = reverse(f"bookings:{name}", args=args)
            self.assertEqual(csrf.get(url).status_code, 200)
            self.assertEqual(csrf.post(url, self.payload()).status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, "PENDING")
        self.assertEqual(booking.activity_logs.count(), 1)

    def test_search_date_status_table_filters_and_pagination(self):
        booking = self.create()
        self.client.force_login(self.manager)
        for q in (booking.booking_code, "Khách An", "0912345678", "+84 912 345 678", "B01"):
            response = self.client.get(reverse("bookings:list"), {"q": q})
            self.assertEqual(list(response.context["page_obj"]), [booking])
        for index in range(21):
            self.create(starts_at=self.start + timedelta(days=index + 1), ends_at=self.end + timedelta(days=index + 1))
        response = self.client.get(reverse("bookings:list"), {"status": "PENDING", "table": self.table.pk, "page": 2})
        self.assertEqual(response.context["page_obj"].paginator.count, 22)
        self.assertEqual(len(response.context["page_obj"]), 2)
        self.assertIn("status=PENDING", response.context["query_string"])
        response = self.client.get(reverse("bookings:list"), {"date": timezone.localtime(self.start).date().isoformat()})
        self.assertEqual(list(response.context["page_obj"]), [booking])
        response = self.client.get(reverse("bookings:list"), {"status": "INVALID"})
        self.assertTrue(response.context["filter_form"].errors)

    def test_database_constraints(self):
        booking = self.create()
        for changes in ({"ends_at": self.start}, {"party_size": 0}, {"status": "INVALID"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Booking.objects.filter(pk=booking.pk).update(**changes)

    def test_admin_is_readonly(self):
        booking = self.create()
        self.client.force_login(self.superuser)
        for model, pk in (("booking", booking.pk), ("bookingactivitylog", booking.activity_logs.get().pk)):
            url = reverse(f"admin:bookings_{model}_change", args=[pk])
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
            self.assertEqual(self.client.get(reverse(f"admin:bookings_{model}_add")).status_code, 403)
            self.assertEqual(self.client.post(reverse(f"admin:bookings_{model}_delete", args=[pk]), {"post": "yes"}).status_code, 403)
