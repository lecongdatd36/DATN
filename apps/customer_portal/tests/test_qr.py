from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.menu.models import Category, Dish, Unit
from apps.orders.models import Order
from apps.seating.models import Area, DiningTable, DiningTableQRToken


class CustomerQRFoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.area = Area.objects.create(name="Tầng 1", is_active=True)
        cls.table = DiningTable.objects.create(code="B10", area=cls.area, capacity=4, is_active=True)
        cls.token = DiningTableQRToken.objects.create(table=cls.table)
        cls.category = Category.objects.create(name="Món chính", is_active=True)
        cls.unit = Unit.objects.create(name="Phần", is_active=True)
        cls.dish = Dish.objects.create(
            code="QR-MAIN-01",
            name="Cơm gà QR",
            category=cls.category,
            unit=cls.unit,
            price=65000,
            status=Dish.Status.AVAILABLE,
        )

    def url(self):
        return reverse("customer_portal:qr_table", args=[self.token.token])

    def test_invalid_token_is_rejected(self):
        response = self.client.get(reverse("customer_portal:qr_table", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(response.status_code, 404)

    def test_closed_table_shows_check_in_request_without_opening_order(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yêu cầu nhận bàn")
        self.assertContains(response, "Chọn món trong lúc chờ nhân viên nhận bàn")
        self.assertEqual(Order.objects.count(), 0)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.AVAILABLE)

    def test_qr_menu_renders_mobile_search_category_and_dish_list(self):
        response = self.client.get(self.url())

        self.assertContains(response, 'data-qr-search')
        self.assertContains(response, f'id="qr-category-{self.category.pk}"')
        self.assertContains(response, 'data-qr-dish')
        self.assertContains(response, self.dish.name)
        self.assertContains(response, 'data-qr-cart-open', count=2)

    def test_qr_requires_exactly_one_active_order(self):
        self.table.status = DiningTable.Status.OCCUPIED
        self.table.save(update_fields=("status",))
        Order.objects.create(table=self.table, status=Order.Status.COMPLETED, order_code="DH000001", guest_count=2, opened_at=timezone.now())
        response = self.client.get(self.url())

        self.assertContains(response, "Bàn đang đồng bộ đơn phục vụ")

    def test_valid_qr_exposes_current_order_without_mutating_it(self):
        self.table.status = DiningTable.Status.OCCUPIED
        self.table.save(update_fields=("status",))
        order = Order.objects.create(table=self.table, status=Order.Status.OPEN, order_code="DH000002", guest_count=2, opened_at=timezone.now())
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bàn B10")
        self.assertContains(response, order.order_code)
        self.assertEqual(Order.objects.count(), 1)
