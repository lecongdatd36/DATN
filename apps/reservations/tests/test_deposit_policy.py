"""Regression coverage for the policy shared by guest and staff bookings."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.bookings import services as bookings
from apps.orders.models import Order
from apps.reservations import services
from apps.reservations.deposit_policy import deposit_quote
from apps.reservations.models import DepositPayment, IngredientHold, Reservation, ReservationPolicy
from . import test_reservations as fixtures


class DepositQuoteTests(SimpleTestCase):
    policy = {"deposit_policy_version": 2, "table_deposit": 100000,
              "ready_percent": 50, "deposit_min_guests": 6}

    def quote(self, **kwargs):
        return deposit_quote(policy=self.policy, party_size=kwargs.pop("party_size", 4), **kwargs)

    def test_groups_of_one_to_five_do_not_pay_a_table_deposit(self):
        for count in range(1, 6):
            with self.subTest(count=count):
                quote = self.quote(party_size=count, subtotal=800000)
                self.assertEqual((quote["amount"], quote["rule"]), (0, "SMALL_GROUP"))

    def test_six_guests_and_above_require_the_configured_deposit(self):
        for count in (6, 7, 100):
            with self.subTest(count=count):
                quote = self.quote(party_size=count)
                self.assertEqual((quote["amount"], quote["rule"]), (100000, "GROUP"))

    def test_private_and_multiple_tables_require_review_and_deposit(self):
        for need in ("PRIVATE", "MULTIPLE"):
            with self.subTest(need=need):
                quote = self.quote(seating_need=need)
                self.assertEqual((quote["amount"], quote["rule"]), (100000, need))
                self.assertTrue(quote["needs_review"])

    def test_ready_food_uses_percentage_instead_of_an_additional_table_deposit(self):
        quote = self.quote(mode="READY", party_size=8, subtotal=400001, seating_need="PRIVATE")
        self.assertEqual((quote["amount"], quote["rule"]), (Decimal(200001), "READY"))

    def test_old_snapshots_keep_the_original_fixed_deposit(self):
        policy = {key: value for key, value in self.policy.items() if key != "deposit_policy_version"}
        quote = deposit_quote(policy=policy, party_size=2)
        self.assertEqual((quote["amount"], quote["rule"]), (100000, "LEGACY"))

    def test_policy_switches_do_not_disable_other_deposit_reasons(self):
        policy = {**self.policy, "require_group_deposit": False}
        self.assertEqual(deposit_quote(policy=policy, party_size=8)["amount"], 0)
        self.assertEqual(deposit_quote(policy=policy, party_size=8, seating_need="PRIVATE")["amount"], 100000)

    def test_invalid_guests_mode_and_seating_are_rejected(self):
        for count in (True, 0, -1, 101, "6", None):
            with self.subTest(count=count), self.assertRaises(ValidationError):
                self.quote(party_size=count)
        for kwargs in ({"mode": "UNKNOWN"}, {"seating_need": "UNKNOWN"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.quote(**kwargs)


@override_settings(VNPAY_TMN_CODE="TESTCODE", VNPAY_HASH_SECRET="test-only-deposit-secret")
class DepositPolicyFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.ReservationTests.setUpTestData.__func__(cls)
        ReservationPolicy.objects.filter(pk=1).update(deposit_min_guests=6)

    def setUp(self):
        clock = patch("apps.reservations.services.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def create_row(self, **kwargs):
        values = dict(full_name="Khách kiểm thử", phone="0912345688", starts_at=self.arrival,
                      party_size=4, duration_minutes=120, mode="TABLE", items=[],
                      request_key=uuid4(), source_digest="a"*64)
        values.update(kwargs)
        return services.create_request(**values)

    def test_small_party_is_confirmed_without_payment_or_inventory_changes(self):
        row = self.create_row()
        self.assertEqual((row.status, row.booking.status, row.deposit_required), ("CONFIRMED", "CONFIRMED", 0))
        self.assertIsNone(row.hold_expires_at)
        self.assertFalse(DepositPayment.objects.exists())
        self.assertFalse(Order.objects.exists())
        self.assertFalse(IngredientHold.objects.exists())
        self.ingredient.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity, 10)
        self.assertEqual(self.table.status, "AVAILABLE")

    def test_arrival_preorders_do_not_make_a_small_group_pay_for_ready_food(self):
        row = self.create_row(items=[{"dish_id": self.dish.pk, "quantity": 2}])
        self.assertEqual((row.subtotal, row.deposit_required, row.status), (400000, 0, "CONFIRMED"))
        self.assertFalse(IngredientHold.objects.exists())

    def test_group_booking_waits_for_deposit_and_expires_without_payment(self):
        row = self.create_row(party_size=6)
        self.assertEqual((row.status, row.booking.status, row.deposit_required), ("WAITING", "PENDING", 100000))
        services.expire_holds(now=self.now+timedelta(minutes=11))
        row.refresh_from_db()
        self.assertEqual((row.status, row.booking.status), ("EXPIRED", "CANCELLED"))

    def test_special_seating_requires_customer_acceptance_before_holding(self):
        for need in ("PRIVATE", "MULTIPLE"):
            with self.subTest(need=need):
                row = self.create_row(seating_need=need)
                self.assertEqual((row.status, row.deposit_required), ("REVIEW", 100000))
                self.assertIsNone(row.booking_id)
                services.review_request(actor=self.manager, reservation_id=row.pk, revision=row.revision,
                                        action="offer", note="Nhà hàng xác nhận bố trí phù hợp", starts_at=self.arrival)
                row.refresh_from_db()
                services.accept_offer(token=row.access_token, revision=row.revision)
                row.refresh_from_db()
                self.assertEqual((row.status, row.booking.status), ("WAITING", "PENDING"))
                services.close_request(actor=self.manager, reservation_id=row.pk, revision=row.revision,
                                       action="cancel", reason="Kết thúc lượt kiểm thử", verified=True)

    def test_ready_food_keeps_fifty_percent_deposit_for_small_groups(self):
        row = self.create_row(mode="READY", items=[{"dish_id": self.dish.pk, "quantity": 2}])
        self.assertEqual((row.status, row.deposit_required, row.deposit_rule), ("REVIEW", 200000, "READY"))

    def test_duplicate_free_booking_does_not_create_an_extra_hold(self):
        key = uuid4()
        one = self.create_row(request_key=key)
        two = self.create_row(request_key=key)
        self.assertEqual(one.pk, two.pk)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_policy_changes_do_not_reprice_an_existing_request(self):
        row = self.create_row(party_size=6)
        ReservationPolicy.objects.filter(pk=1).update(table_deposit=250000, deposit_min_guests=1)
        row.refresh_from_db()
        self.assertEqual(row.deposit_required, 100000)
        self.assertEqual(row.policy_snapshot["table_deposit"], 100000)

    def test_manager_waiver_confirms_and_records_reason_without_fake_payment(self):
        row = self.create_row(party_size=6)
        services.waive_deposit(actor=self.manager, reservation_id=row.pk, revision=row.revision,
                               reason="Khách quen được quản lý xác nhận")
        row.refresh_from_db()
        self.assertEqual((row.status, row.booking.status, row.deposit_required), ("CONFIRMED", "CONFIRMED", 0))
        self.assertEqual(row.deposit_waived_by, self.manager)
        self.assertEqual(row.deposit_waived_amount, 100000)
        self.assertTrue(row.deposit_waiver_reason)
        self.assertFalse(row.deposits.exists())

    def test_unauthorized_user_cannot_waive_a_deposit(self):
        row = self.create_row(party_size=6)
        with self.assertRaises(PermissionDenied):
            services.waive_deposit(actor=self.staff, reservation_id=row.pk, revision=row.revision, reason="Không được phép")
        row.refresh_from_db()
        self.assertEqual((row.status, row.deposit_required), ("WAITING", 100000))

    def test_pending_payment_prevents_waiving_and_late_bank_success(self):
        row = self.create_row(party_size=6)
        services.checkout(token=row.access_token, revision=row.revision,
                          return_url="https://example.test/return", ip_address="127.0.0.1")
        with self.assertRaises(ValidationError):
            services.waive_deposit(actor=self.manager, reservation_id=row.pk, revision=row.revision, reason="Khách đã mở thanh toán")

    def test_free_booking_cannot_open_a_payment(self):
        row = self.create_row()
        with self.assertRaises(ValidationError):
            services.checkout(token=row.access_token, revision=row.revision,
                              return_url="https://example.test/return", ip_address="127.0.0.1")
        self.assertFalse(row.deposits.exists())

    def test_staff_group_booking_uses_the_same_policy_as_the_guest_channel(self):
        booking = bookings.save_booking(actor=self.manager, customer_phone="0912345688",
                                         customer_name="Khách tại quầy", table_id=self.table.pk,
                                         party_size=6, starts_at=self.arrival, duration_minutes=120)
        row = booking.online_reservation
        self.assertEqual((row.status, row.deposit_required, row.deposit_rule), ("WAITING", 100000, "GROUP"))

    def test_staff_manager_can_waive_a_group_deposit_during_creation(self):
        booking = bookings.save_booking(actor=self.manager, customer_phone="0912345688",
                                         customer_name="Khách tại quầy", table_id=self.table.pk,
                                         party_size=6, starts_at=self.arrival, duration_minutes=120,
                                         waiver_reason="Quản lý xác nhận khách quen")
        row = booking.online_reservation
        self.assertEqual((row.status, row.deposit_required, row.deposit_waived_amount), ("CONFIRMED", 0, 100000))
        booking.refresh_from_db()
        self.assertEqual(booking.status, "CONFIRMED")
