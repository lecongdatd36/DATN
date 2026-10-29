from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.customers.models import Customer
from apps.inventory.models import Ingredient
from apps.menu.models import Category, Dish, Unit
from apps.orders.models import (
    Order, OrderItem, PaymentRequest, QRCheckInRequest, QROrderRequest, QRServiceRequest,
)
from apps.seating.models import Area, DiningTable


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_superuser(username="notify_manager", password="Notify-Test-8632!")
        cls.limited = get_user_model().objects.create_user(username="notify_limited")
        cls.limited.user_permissions.add(Permission.objects.get(content_type__app_label="bookings", codename="view_booking"))
        cls.area = Area.objects.create(name="Notification area")
        cls.table = DiningTable.objects.create(code="NT01", area=cls.area, capacity=4)
        cls.customer = Customer.objects.create(full_name="Notification customer", phone="0912345678")
        now = timezone.now()
        cls.booking = Booking.objects.create(
            customer=cls.customer, table=cls.table, customer_name=cls.customer.full_name,
            party_size=2, starts_at=now + timedelta(hours=1), ends_at=now + timedelta(hours=3),
        )
        Booking.objects.create(
            customer=cls.customer, table=cls.table, customer_name=cls.customer.full_name,
            party_size=2, starts_at=now - timedelta(hours=3), ends_at=now - timedelta(hours=1),
        )
        # The arrival grace period may end before the planned visit ends.
        Booking.objects.create(
            customer=cls.customer, table=cls.table, customer_name=cls.customer.full_name,
            party_size=2, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1),
        )
        cls.checkin = QRCheckInRequest.objects.create(table=cls.table, guest_count=2)
        cls.order = Order.objects.create(table=cls.table, status=Order.Status.IN_PROGRESS)
        cls.qr_order = QROrderRequest.objects.create(table=cls.table, order=cls.order)
        cls.service = QRServiceRequest.objects.create(table=cls.table, order=cls.order, request_type=QRServiceRequest.RequestType.WATER)
        dish = Dish.objects.create(
            code="NTD01", name="Test dish", price=50000,
            category=Category.objects.create(name="Notification dishes"),
            unit=Unit.objects.create(name="Notification portion"),
        )
        cls.ready = OrderItem.objects.create(
            order=cls.order, dish=dish, dish_code=dish.code, dish_name=dish.name,
            unit_name=dish.unit.name, unit_price=50000, quantity=3, status=OrderItem.Status.READY,
        )
        cls.pending = OrderItem.objects.create(
            order=cls.order, dish=dish, dish_code=dish.code, dish_name=dish.name,
            unit_name=dish.unit.name, unit_price=50000, quantity=2, status=OrderItem.Status.PENDING,
        )
        cls.payment_order = Order.objects.create(table=cls.table, status=Order.Status.PAYMENT_REQUESTED)
        cls.payment = PaymentRequest.objects.create(order=cls.payment_order)
        cls.ingredient = Ingredient.objects.create(code="NTI01", name="Low stock", unit="kg", stock_quantity=2, low_stock_threshold=2)
        Ingredient.objects.create(code="NTI02", name="Inactive low stock", unit="kg", is_active=False)
        cls.cleaning = DiningTable.objects.create(code="NT02", area=cls.area, capacity=2, status=DiningTable.Status.CLEANING)

    def state(self, user=None, **headers):
        self.client.force_login(user or self.manager)
        return self.client.get(reverse("notification_state"), **headers)

    def test_counts_exclude_expired_and_inactive_and_total_does_not_double_count(self):
        response = self.state()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"], {
            "bookings": 1, "sales": 5, "tasks": 4, "payments": 1,
            "kitchen": 1, "inventory": 1, "tables": 1, "total": 9,
        })
        QRCheckInRequest.objects.filter(pk=self.checkin.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.state().json()["counts"]["sales"], 4)

    def test_counts_and_etag_change_after_work_is_processed(self):
        response = self.state()
        unchanged = self.state(HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(unchanged.status_code, 304)
        Booking.objects.filter(pk=self.booking.pk).update(status=Booking.Status.CONFIRMED)
        QRCheckInRequest.objects.filter(pk=self.checkin.pk).update(status=QRCheckInRequest.Status.CONFIRMED)
        QROrderRequest.objects.filter(pk=self.qr_order.pk).update(status=QROrderRequest.Status.CONFIRMED)
        QRServiceRequest.objects.filter(pk=self.service.pk).update(status=QRServiceRequest.Status.COMPLETED)
        OrderItem.objects.filter(pk=self.ready.pk).update(status=OrderItem.Status.SERVED)
        OrderItem.objects.filter(pk=self.pending.pk).update(status=OrderItem.Status.COOKING)
        PaymentRequest.objects.filter(pk=self.payment.pk).update(status=PaymentRequest.Status.COMPLETED)
        Ingredient.objects.filter(pk=self.ingredient.pk).update(stock_quantity=10)
        DiningTable.objects.filter(pk=self.cleaning.pk).update(status=DiningTable.Status.AVAILABLE)
        changed = self.state(HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["counts"]["total"], 0)
        self.assertNotEqual(changed["ETag"], response["ETag"])

    def test_only_permitted_categories_are_exposed(self):
        payload = self.state(self.limited).json()
        self.assertEqual(payload["counts"]["total"], 1)
        self.assertEqual([entry["key"] for entry in payload["entries"]], ["bookings"])
        self.limited.user_permissions.clear()
        self.assertEqual(self.state(self.limited).json()["counts"]["total"], 0)

    def test_closed_order_requests_are_not_counted(self):
        Order.objects.filter(pk__in=[self.order.pk, self.payment_order.pk]).update(status=Order.Status.CANCELLED)
        payload = self.state().json()
        self.assertEqual(payload["counts"]["sales"], 1)  # unexpired check-in only
        self.assertEqual(payload["counts"]["kitchen"], 0)

    def test_anonymous_access_requires_login_and_post_is_rejected(self):
        self.assertEqual(self.client.get(reverse("notification_state")).status_code, 302)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse("notification_state")).status_code, 405)

    def test_badges_render_in_desktop_and_mobile_templates(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("bookings:list"))
        self.assertContains(response, 'data-notification-count="bookings"')
        self.assertContains(response, 'data-notification-url="' + reverse("notification_state") + '"')
        self.assertContains(response, "nav-notifications.js")
        response = self.client.get(reverse("sales:mobile") + "?page=personal")
        self.assertContains(response, 'data-notification-count="total"')
        self.assertContains(response, 'data-notification-entry="bookings"')
