from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from apps.bookings.models import Booking, BookingActivityLog
from apps.bookings.services import save_booking
from apps.customers.models import Customer
from apps.seating.models import Area, DiningTable
from apps.seating.services import save_area


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BookingConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.actors = [get_user_model().objects.create_superuser(username=f"booking_admin_{i}", password="Secret!Test123") for i in range(2)]
        self.area = Area.objects.create(name="Tầng 1")
        self.table = DiningTable.objects.create(code="B01", area=self.area, capacity=4)
        self.customer = Customer.objects.create(full_name="Khách", phone="0912345678")
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=1)

    def run_parallel(self, close_area=False):
        barrier = Barrier(2)

        def work(index):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actors[index].pk)
                barrier.wait(timeout=10)
                try:
                    if close_area and index == 0:
                        save_area(actor=actor, area_id=self.area.pk, name=self.area.name, is_active=False)
                        return "closed"
                    save_booking(actor=actor, customer_phone=self.customer.phone, table_id=self.table.pk, party_size=4, starts_at=self.start, ends_at=self.end)
                    return "booked"
                except ValidationError:
                    return "blocked"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(work, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_simultaneous_booking_same_slot_commits_once(self):
        self.assertCountEqual(self.run_parallel(), ["booked", "blocked"])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookingActivityLog.objects.count(), 1)

    def test_booking_and_area_shutdown_are_serialized(self):
        results = self.run_parallel(close_area=True)
        self.area.refresh_from_db()
        if self.area.is_active:
            self.assertEqual(results, ["blocked", "booked"])
            self.assertEqual(Booking.objects.count(), 1)
        else:
            self.assertEqual(results, ["closed", "blocked"])
            self.assertEqual(Booking.objects.count(), 0)
