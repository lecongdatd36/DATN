from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import transition_booking
from apps.customers.models import Customer
from apps.menu.models import Category, Unit, Dish
from apps.menu.services import change_availability
from apps.seating.models import Area, DiningTable
from apps.orders.models import Order, OrderItem, OrderActivityLog
from apps.orders import services


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OrderConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.actors = [get_user_model().objects.create_superuser(username=f"orders_{i}", password="Test!123") for i in range(2)]
        self.area = Area.objects.create(name="Tầng 1")
        self.table = DiningTable.objects.create(code="B01", area=self.area, capacity=4)
        self.customer = Customer.objects.create(full_name="Khách", phone="0912345678")
        self.category = Category.objects.create(name="Món chính")
        self.unit = Unit.objects.create(name="Phần")
        self.dish = Dish.objects.create(code="M001", name="Cơm", category=self.category, unit=self.unit, price=85000)

    def visit(self):
        now = timezone.now()
        return Booking.objects.create(customer=self.customer, customer_name=self.customer.full_name, customer_phone=self.customer.phone,
            table=self.table, party_size=2, starts_at=now - timedelta(minutes=5), ends_at=now + timedelta(hours=2), status="SEATED", seated_at=now - timedelta(minutes=5))

    def race(self, action):
        barrier = Barrier(2)

        def work(index):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actors[index].pk)
                barrier.wait(timeout=10)
                try:
                    return action(actor, index)
                except ValidationError:
                    return "blocked"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(work, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_two_users_open_one_order_per_visit(self):
        visit = self.visit()
        results = self.race(lambda actor, _: services.open_order(actor=actor, booking_id=visit.pk).pk)
        self.assertEqual(results[0], results[1])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderActivityLog.objects.count(), 1)

    def test_two_walk_ins_cannot_claim_same_table(self):
        results = self.race(lambda actor, _: services.open_walk_in_order(actor=actor, table_id=self.table.pk, party_size=2).pk)
        self.assertEqual(results.count("blocked"), 1)
        self.assertEqual(Booking.objects.filter(status="SEATED").count(), 1)
        self.assertEqual(Order.objects.count(), 1)

    def test_completion_and_open_order_are_serialized(self):
        visit = self.visit()

        def action(actor, index):
            if index == 0:
                transition_booking(actor=actor, booking_id=visit.pk, target="COMPLETED", expected_status="SEATED", expected_revision=1)
                return "completed"
            services.open_order(actor=actor, booking_id=visit.pk)
            return "opened"
        results = self.race(action)
        visit.refresh_from_db()
        if visit.status == "COMPLETED":
            self.assertEqual(results, ["completed", "blocked"])
            self.assertFalse(Order.objects.exists())
        else:
            self.assertEqual(results, ["blocked", "opened"])
            self.assertEqual(Order.objects.count(), 1)

    def test_cancel_and_start_cooking_only_one_wins(self):
        order = services.open_order(actor=self.actors[0], booking_id=self.visit().pk)
        item = services.add_item(actor=self.actors[0], order_id=order.pk, expected_revision=1, dish_id=self.dish.pk, quantity=2)
        services.send_to_kitchen(actor=self.actors[0], order_id=order.pk, expected_revision=2)

        def action(actor, index):
            services.transition_item(actor=actor, order_id=order.pk, item_id=item.pk, expected_revision=3,
                target="CANCELLED" if index == 0 else "COOKING", reason="Khách đổi ý")
            return "changed"
        self.assertCountEqual(self.race(action), ["changed", "blocked"])
        item.refresh_from_db()
        self.assertIn(item.status, ("CANCELLED", "COOKING"))
        self.assertEqual(OrderActivityLog.objects.count(), 4)

    def test_menu_sold_out_and_send_are_serialized(self):
        order = services.open_order(actor=self.actors[0], booking_id=self.visit().pk)
        item = services.add_item(actor=self.actors[0], order_id=order.pk, expected_revision=1, dish_id=self.dish.pk, quantity=2)

        def action(actor, index):
            if index == 0:
                change_availability(actor=actor, dish_id=self.dish.pk, status="SOLD_OUT", expected_revision=1)
                return "sold_out"
            services.send_to_kitchen(actor=actor, order_id=order.pk, expected_revision=2)
            return "sent"
        results = self.race(action)
        self.assertEqual(results[0], "sold_out")
        item.refresh_from_db()
        self.assertEqual(item.status, "DRAFT" if results[1] == "blocked" else "SENT")
        self.assertEqual(OrderActivityLog.objects.filter(action="Gửi Bếp").count(), 0 if results[1] == "blocked" else 1)
