from django.test import TestCase
from django.urls import reverse

from apps.menu.models import Category, Dish, Unit


class CustomerMenuTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Món chính", is_active=True)
        cls.unit = Unit.objects.create(name="Phần", is_active=True)
        cls.available = Dish.objects.create(code="M001", name="Cơm gà", category=cls.category,
                                             unit=cls.unit, price=50000, status=Dish.Status.AVAILABLE)
        cls.sold_out = Dish.objects.create(code="M002", name="Bún bò", category=cls.category,
                                           unit=cls.unit, price=60000, status=Dish.Status.SOLD_OUT)
        cls.inactive = Dish.objects.create(code="M003", name="Món ẩn", category=cls.category,
                                           unit=cls.unit, price=70000, status=Dish.Status.INACTIVE)

    def test_public_menu_shows_available_and_sold_out_dishes(self):
        response = self.client.get(reverse("customer_portal:menu"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cơm gà")
        self.assertContains(response, "Bún bò")
        self.assertContains(response, "Hết món")
        self.assertNotContains(response, "Món ẩn")

    def test_public_pages_include_staff_login_link(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, "Đăng nhập")

    def test_public_menu_search_and_category_filter(self):
        response = self.client.get(reverse("customer_portal:menu"), {"q": "bún"})
        self.assertContains(response, "Bún bò")
        self.assertNotContains(response, "Cơm gà")

        other_category = Category.objects.create(name="Tráng miệng", is_active=True)
        Dish.objects.create(code="M004", name="Chè sen", category=other_category,
                    unit=self.unit, price=30000, status=Dish.Status.AVAILABLE)
        response = self.client.get(reverse("customer_portal:menu"), {"category": other_category.pk})
        self.assertContains(response, "Chè sen")
        self.assertNotContains(response, "Cơm gà")

    def test_inactive_dish_detail_is_not_public(self):
        self.assertEqual(
            self.client.get(reverse("customer_portal:dish_detail", args=[self.available.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("customer_portal:dish_detail", args=[self.inactive.pk])).status_code,
            404,
        )

    def test_inactive_category_is_not_public(self):
        category = Category.objects.create(name="Tạm dừng", is_active=False)
        dish = Dish.objects.create(code="M005", name="Món tạm dừng", category=category,
                       unit=self.unit, price=40000, status=Dish.Status.AVAILABLE)
        response = self.client.get(reverse("customer_portal:menu"))
        self.assertNotContains(response, dish.name)