from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking, BookingActivityLog, BookingSettings
from apps.bookings.selectors import recommended_tables
from apps.bookings.services import create_public_booking, save_booking
from apps.bookings.table_ranking import rank_tables
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TableRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.waiter = get_user_model().objects.create_user(username="table_waiter")
        cls.waiter.groups.add(Group.objects.get(name="WAITER"))
        cls.area = Area.objects.create(name="Area A")
        cls.small = DiningTable.objects.create(code="Z04", area=cls.area, capacity=4)
        cls.large = DiningTable.objects.create(code="A08", area=cls.area, capacity=8)
        cls.customer = Customer.objects.create(full_name="Private customer", phone="0912345678")
        cls.start = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        cls.end = cls.start + timedelta(hours=2)

    def recommend(self, **kwargs):
        return recommended_tables(**dict(starts_at=self.start, ends_at=self.end, party_size=3, **kwargs))

    def occupy(self, status=Booking.Status.CONFIRMED, **kwargs):
        values = dict(
            customer=self.customer, customer_name=self.customer.full_name, customer_phone=self.customer.phone,
            table=self.small, party_size=3, starts_at=self.start, ends_at=self.end, status=status,
        )
        values.update(kwargs)
        return Booking.objects.create(**values)

    def params(self, **kwargs):
        return dict(starts_at=timezone.localtime(self.start).strftime("%Y-%m-%dT%H:%M"), party_size=3, **kwargs)

    def test_best_fit_score_and_explanation(self):
        rows = self.recommend()
        self.assertEqual([row.table.pk for row in rows], [self.small.pk, self.large.pk])
        self.assertEqual([row.rank for row in rows], [1, 2])
        self.assertEqual([row.score for row in rows], [Decimal("75.00"), Decimal("37.50")])
        self.assertEqual(rows[0].spare_seats, 1)
        self.assertIn("Đủ 3 khách, dư 1 chỗ", rows[0].reason)

    def test_exact_fit_scores_100_and_undersized_tables_are_excluded(self):
        self.assertEqual(rank_tables([self.small, self.large], 4)[0].score, 100)
        self.assertEqual([row.table.pk for row in rank_tables([self.small, self.large], 5)], [self.large.pk])
        self.assertEqual(rank_tables([self.small, self.large], 9), [])

    def test_invalid_party_sizes_are_rejected(self):
        for value in (0, -1, 101, True, "3", 3.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rank_tables([self.small], value)

    def test_invalid_time_ranges_are_rejected(self):
        for start, end in ((self.start, self.start), (self.end, self.start), (timezone.make_naive(self.start), self.end)):
            with self.subTest(start=start), self.assertRaises(ValidationError):
                recommended_tables(starts_at=start, ends_at=end, party_size=3)

    def test_equal_scores_have_stable_area_then_code_order(self):
        other_area = Area.objects.create(name="Area B")
        later = DiningTable.objects.create(code="A04", area=other_area, capacity=4)
        earlier = DiningTable.objects.create(code="B04", area=self.area, capacity=4)
        rows = rank_tables([later, self.small, earlier], 3)
        self.assertEqual([row.table.pk for row in rows], [earlier.pk, self.small.pk, later.pk])

    def test_overlapping_pending_confirmed_and_seated_visits_are_excluded(self):
        for status in (Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.SEATED):
            with self.subTest(status=status):
                booking = self.occupy(status=status, seated_at=self.start if status == Booking.Status.SEATED else None)
                self.assertEqual([row.table.pk for row in self.recommend()], [self.large.pk])
                booking.delete()

    def test_cancelled_completed_and_no_show_do_not_block(self):
        for status in (Booking.Status.CANCELLED, Booking.Status.COMPLETED, Booking.Status.NO_SHOW):
            with self.subTest(status=status):
                booking = self.occupy(status=status)
                self.assertEqual(len(self.recommend()), 2)
                booking.delete()

    def test_adjacent_non_overlapping_bookings_are_allowed(self):
        self.occupy(starts_at=self.start - timedelta(hours=2), ends_at=self.start)
        self.occupy(starts_at=self.end, ends_at=self.end + timedelta(hours=2))
        self.assertEqual(self.recommend()[0].table.pk, self.small.pk)

    def test_cross_midnight_overlap_is_excluded(self):
        start = timezone.localtime(self.start).replace(hour=23, minute=30)
        end = start + timedelta(hours=2)
        self.occupy(starts_at=start + timedelta(minutes=45), ends_at=end + timedelta(hours=1))
        rows = recommended_tables(starts_at=start, ends_at=end, party_size=3)
        self.assertEqual([row.table.pk for row in rows], [self.large.pk])

    def test_overdue_seated_visit_blocks_even_with_stale_table_status(self):
        now = timezone.now()
        self.occupy(status=Booking.Status.SEATED, starts_at=now - timedelta(hours=3),
                    ends_at=now - timedelta(hours=1), seated_at=now - timedelta(hours=3))
        self.assertEqual([row.table.pk for row in self.recommend()], [self.large.pk])

    def test_inactive_occupied_and_cleaning_tables_are_excluded(self):
        for status in (DiningTable.Status.OCCUPIED, DiningTable.Status.CLEANING):
            with self.subTest(status=status):
                DiningTable.objects.filter(pk=self.small.pk).update(status=status)
                self.assertEqual([row.table.pk for row in self.recommend()], [self.large.pk])
        DiningTable.objects.filter(pk=self.small.pk).update(status=DiningTable.Status.AVAILABLE, is_active=False)
        self.assertEqual([row.table.pk for row in self.recommend()], [self.large.pk])
        self.area.is_active = False
        self.area.save(update_fields=("is_active",))
        self.assertEqual(self.recommend(), [])

    def test_requested_area_is_a_hard_constraint(self):
        other = Area.objects.create(name="Area B")
        DiningTable.objects.create(code="EXACT03", area=other, capacity=3)
        self.assertEqual(self.recommend()[0].table.code, "EXACT03")
        self.assertEqual(self.recommend(area_id=self.area.pk)[0].table.pk, self.small.pk)

    def test_ranking_reads_in_one_query_without_creating_bookings(self):
        with self.assertNumQueries(1):
            rows = self.recommend()
            self.assertEqual(rows[0].table.area.name, self.area.name)
        self.assertFalse(Booking.objects.exists())

    def test_staff_results_show_scores_reasons_and_preserve_booking_prefill(self):
        self.client.force_login(self.waiter)
        response = self.client.get(reverse("bookings:availability"), self.params())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["best_recommendation"].table.pk, self.small.pk)
        self.assertContains(response, "ĐỀ XUẤT HÀNG ĐẦU")
        self.assertContains(response, "Đủ 3 khách, dư 1 chỗ")
        chosen = self.client.get(response.context["page_obj"][0].booking_url)
        self.assertEqual(str(chosen.context["form"]["table"].value()), str(self.small.pk))
        self.assertFalse(Booking.objects.exists())

    def test_staff_pagination_keeps_global_ranks(self):
        for capacity in range(10, 30):
            DiningTable.objects.create(code=f"PAGE{capacity}", area=self.area, capacity=capacity)
        self.client.force_login(self.waiter)
        response = self.client.get(reverse("bookings:availability"), self.params(page=2))
        self.assertEqual([table.recommendation.rank for table in response.context["page_obj"]], [21, 22])
        self.assertEqual(response.context["best_recommendation"].table.pk, self.small.pk)

    def test_staff_access_still_requires_booking_permission(self):
        self.assertEqual(self.client.get(reverse("bookings:availability"), self.params()).status_code, 302)
        kitchen = get_user_model().objects.create_user(username="table_kitchen")
        kitchen.groups.add(Group.objects.get(name="KITCHEN"))
        self.client.force_login(kitchen)
        self.assertEqual(self.client.get(reverse("bookings:availability"), self.params()).status_code, 403)

    def test_public_results_and_link_preserve_validated_search_values(self):
        response = self.client.get(reverse("customer_reservations:check"), self.params(area=self.area.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["table_recommendations"][0].table.pk, self.small.pk)
        self.assertContains(response, "Đủ 3 khách, dư 1 chỗ")
        self.assertNotContains(response, self.customer.phone)
        next_page = self.client.get(response.context["reservation_url"])
        form = next_page.context["form"]
        self.assertEqual(str(form["party_size"].value()), "3")
        self.assertEqual(str(form["duration_minutes"].value()), "120")
        self.assertEqual(str(form["area"].value()), str(self.area.pk))
        self.assertEqual(form["starts_at"].value(), self.params()["starts_at"])
        self.assertFalse(Booking.objects.exists())

    def test_no_public_result_and_invalid_form_do_not_show_recommendations(self):
        response = self.client.get(reverse("customer_reservations:check"), {**self.params(), "party_size": 100})
        self.assertContains(response, "Chưa có bàn phù hợp")
        invalid = self.client.get(reverse("customer_reservations:check"), {**self.params(), "party_size": 0})
        self.assertNotIn("table_recommendations", invalid.context)

    def test_public_creation_rechecks_preview_and_uses_next_best_table(self):
        self.assertEqual(self.recommend()[0].table.pk, self.small.pk)
        save_booking(actor=self.waiter, customer_phone=self.customer.phone, table_id=self.small.pk,
                     party_size=3, starts_at=self.start, ends_at=self.end)
        booking = create_public_booking(full_name="New guest", phone="0901234567", starts_at=self.start, party_size=3)
        self.assertEqual(booking.table_id, self.large.pk)
        self.assertIn("37.50/100", booking.activity_logs.get().description)

    def test_failed_public_allocation_rolls_back_new_customer(self):
        before = Customer.objects.count()
        with self.assertRaises(ValidationError):
            create_public_booking(full_name="No capacity", phone="0901234567", starts_at=self.start, party_size=100)
        self.assertEqual(Customer.objects.count(), before)

    def test_failed_audit_rolls_back_allocation(self):
        with patch("apps.bookings.services._log", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                create_public_booking(full_name="New guest", phone="0901234567", starts_at=self.start, party_size=3)
        self.assertFalse(Booking.objects.exists())


class TableRecommendationConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        BookingSettings.objects.get_or_create(pk=1, defaults={"default_duration_minutes": 120})
        self.area = Area.objects.create(name="Concurrency area")
        self.small = DiningTable.objects.create(code="CON04", area=self.area, capacity=4)
        self.start = timezone.now() + timedelta(days=1)

    def allocate_parallel(self):
        barrier = Barrier(2)

        def allocate(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    booking = create_public_booking(full_name=f"Guest {index}", phone=f"090123456{index}",
                                                    starts_at=self.start, party_size=3)
                    return booking.table_id
                except ValidationError:
                    return "blocked"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(allocate, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_parallel_requests_use_distinct_ranked_tables(self):
        large = DiningTable.objects.create(code="CON08", area=self.area, capacity=8)
        self.assertCountEqual(self.allocate_parallel(), [self.small.pk, large.pk])
        self.assertEqual(Booking.objects.count(), 2)
        self.assertEqual(BookingActivityLog.objects.count(), 2)

    def test_parallel_requests_cannot_claim_the_same_last_table(self):
        self.assertCountEqual(self.allocate_parallel(), [self.small.pk, "blocked"])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
