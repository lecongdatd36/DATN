from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.inventory.models import InventoryTransaction
from apps.menu.models import Category, Dish, Unit
from apps.orders.models import Order, OrderItem, QROrderRequest
from apps.orders.services import create_qr_order_request
from apps.seating.models import Area, DiningTable, DiningTableQRToken


class CustomerQRRequestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.area = Area.objects.create(name="QR Orders", is_active=True)
        cls.table = DiningTable.objects.create(code="B20", area=cls.area, capacity=4, status=DiningTable.Status.OCCUPIED)
        cls.token = DiningTableQRToken.objects.create(table=cls.table)
        cls.order = Order.objects.create(table=cls.table, status=Order.Status.OPEN, order_code="DH000020", guest_count=2)
        cls.category = Category.objects.create(name="QR Món", is_active=True)
        cls.unit = Unit.objects.create(name="Phần", is_active=True)
        cls.dish = Dish.objects.create(code="QR01", name="Cơm QR", category=cls.category, unit=cls.unit,
                                       price=50000, status=Dish.Status.AVAILABLE)

    def test_submit_creates_waiting_request_with_price_snapshot_only(self):
        qr_request = create_qr_order_request(
            token=self.token.token,
            items=[{"dish_id": self.dish.pk, "quantity": 2, "note": "Ít cay"}],
        )

        self.assertEqual(qr_request.status, QROrderRequest.Status.WAITING_CONFIRMATION)
        item = qr_request.items.get()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.note, "Ít cay")
        self.assertEqual(item.unit_price_snapshot, Decimal("50000"))
        self.assertFalse(OrderItem.objects.filter(order=self.order).exists())
        self.assertEqual(InventoryTransaction.objects.count(), 0)

        Dish.objects.filter(pk=self.dish.pk).update(price=55000)
        self.assertEqual(qr_request.items.get().unit_price_snapshot, Decimal("50000"))

    def test_status_page_only_shows_requests_saved_in_customer_session(self):
        qr_request = create_qr_order_request(token=self.token.token, items=[{"dish_id": self.dish.pk, "quantity": 1}])
        status_url = reverse("customer_portal:qr_status", args=[self.token.token])
        self.assertEqual(self.client.get(status_url).status_code, 200)
        session = self.client.session
        session["qr_request_ids"] = [str(qr_request.pk)]
        session.save()

        response = self.client.get(status_url)
        data_response = self.client.get(reverse("customer_portal:qr_status_data", args=[self.token.token]))
        self.assertContains(response, str(qr_request))
        self.assertEqual(data_response.status_code, 200)
        self.assertEqual(data_response.json()["requests"][0]["items"][0]["status"], "Chờ nhân viên xác nhận")

    def test_unavailable_dish_rolls_back_request(self):
        Dish.objects.filter(pk=self.dish.pk).update(status=Dish.Status.SOLD_OUT)

        with self.assertRaises(ValidationError):
            create_qr_order_request(token=self.token.token, items=[{"dish_id": self.dish.pk, "quantity": 1}])

        self.assertFalse(QROrderRequest.objects.exists())

    def test_public_post_returns_created_request(self):
        response = self.client.post(
            reverse("customer_portal:qr_request", args=[self.token.token]),
            data='{"items":[{"dish_id": %d, "quantity": 1, "note": "Không hành"}]}' % self.dish.pk,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "Chờ nhân viên xác nhận")