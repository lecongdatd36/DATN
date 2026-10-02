from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.menu.models import Category, Dish, Unit
from apps.orders.models import Order, OrderItem, QROrderRequest
from apps.orders.services import confirm_qr_order_request, create_qr_order_request, reject_qr_order_request
from apps.seating.models import Area, DiningTable, DiningTableQRToken


class QRStaffActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="qr_staff_manager", password="Test!123", is_staff=True)
        cls.manager.groups.add(Group.objects.get(name="MANAGER"))
        cls.area = Area.objects.create(name="QR Staff", is_active=True)
        cls.table = DiningTable.objects.create(code="B30", area=cls.area, capacity=4, status=DiningTable.Status.OCCUPIED)
        cls.token = DiningTableQRToken.objects.create(table=cls.table)
        cls.order = Order.objects.create(table=cls.table, status=Order.Status.OPEN, order_code="DH000030", guest_count=2)
        cls.category = Category.objects.create(name="QR Staff Món", is_active=True)
        cls.unit = Unit.objects.create(name="Phần", is_active=True)
        cls.dish = Dish.objects.create(code="QR30", name="Món xác nhận", category=cls.category, unit=cls.unit,
                                       price=40000, status=Dish.Status.AVAILABLE)

    def request(self):
        return create_qr_order_request(token=self.token.token, items=[{"dish_id": self.dish.pk, "quantity": 1}])

    def test_confirm_is_atomic_and_cannot_run_twice(self):
        qr_request = self.request()
        confirmed = confirm_qr_order_request(actor=self.manager, request_id=qr_request.pk)

        self.assertEqual(confirmed.status, QROrderRequest.Status.CONFIRMED)
        self.assertEqual(confirmed.confirmed_by_id, self.manager.pk)
        order_item = OrderItem.objects.get(order=self.order)
        self.assertEqual(order_item.status, OrderItem.Status.PENDING)
        self.assertEqual(order_item.unit_price, self.dish.price)
        self.assertEqual(order_item.qr_request_item.request_id, qr_request.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.IN_PROGRESS)
        with self.assertRaises(ValidationError):
            confirm_qr_order_request(actor=self.manager, request_id=qr_request.pk)

    def test_reject_requires_reason_and_does_not_create_order_item(self):
        qr_request = self.request()
        with self.assertRaises(ValidationError):
            reject_qr_order_request(actor=self.manager, request_id=qr_request.pk, reason="")
        rejected = reject_qr_order_request(actor=self.manager, request_id=qr_request.pk, reason="Món vừa hết.")

        self.assertEqual(rejected.status, QROrderRequest.Status.REJECTED)
        self.assertEqual(rejected.reject_reason, "Món vừa hết.")
        self.assertFalse(OrderItem.objects.filter(order=self.order).exists())

    def test_confirm_rechecks_dish_availability(self):
        qr_request = self.request()
        Dish.objects.filter(pk=self.dish.pk).update(status=Dish.Status.SOLD_OUT)

        with self.assertRaises(ValidationError):
            confirm_qr_order_request(actor=self.manager, request_id=qr_request.pk)
        qr_request.refresh_from_db()
        self.assertEqual(qr_request.status, QROrderRequest.Status.WAITING_CONFIRMATION)

    def test_sales_action_requires_staff_order_permission(self):
        qr_request = self.request()
        response = self.client.post(reverse("sales:qr_request_action", args=[qr_request.pk, "confirm"]))
        self.assertEqual(response.status_code, 302)
        qr_request.refresh_from_db()
        self.assertEqual(qr_request.status, QROrderRequest.Status.WAITING_CONFIRMATION)

    def test_kitchen_failure_rolls_back_order_item_and_request(self):
        qr_request = self.request()
        with patch("apps.orders.services.send_to_kitchen", side_effect=ValidationError("Không đủ tồn kho.")):
            with self.assertRaises(ValidationError):
                confirm_qr_order_request(actor=self.manager, request_id=qr_request.pk)

        qr_request.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(qr_request.status, QROrderRequest.Status.WAITING_CONFIRMATION)
        self.assertFalse(OrderItem.objects.filter(order=self.order).exists())
        self.assertEqual(self.order.status, Order.Status.OPEN)