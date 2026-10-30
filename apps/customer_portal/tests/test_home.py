from django.test import TestCase
from django.urls import reverse

from apps.menu.models import Category, Dish, Unit

from ..home import homepage_context


class CustomerHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Món chính")
        cls.unit = Unit.objects.create(name="Phần")
        cls.rice = Dish.objects.create(
            code="HOME01", name="Cơm gà", category=cls.category,
            unit=cls.unit, price=75000, status=Dish.Status.AVAILABLE,
        )
        cls.sold_out = Dish.objects.create(
            code="HOME02", name="Bún bò", category=cls.category,
            unit=cls.unit, price=80000, status=Dish.Status.SOLD_OUT,
        )
        cls.inactive = Dish.objects.create(
            code="HOME03", name="Món riêng nội bộ", category=cls.category,
            unit=cls.unit, price=90000, status=Dish.Status.INACTIVE,
        )

    def test_home_renders_public_database_menu_and_current_brand(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CƠM QUÊ")
        self.assertContains(response, "Cơm gà")
        self.assertContains(response, "75.000")
        self.assertContains(response, "Bún bò")
        self.assertContains(response, "Tạm hết món")
        self.assertNotContains(response, self.inactive.name)
        self.assertContains(response, reverse("customer_portal:dish_detail", args=[self.rice.pk]))
        self.assertContains(response, reverse("customer_reservations:create"))
        self.assertContains(response, 'data-restaurant-name="CƠM QUÊ"')
        self.assertEqual(response.context["menu_dish_count"], 2)

    def test_photos_and_categories_use_public_data_without_extra_queries(self):
        Dish.objects.filter(pk=self.rice.pk).update(image="dishes/home-rice.jpg")
        Dish.objects.filter(pk=self.sold_out.pk).update(image="dishes/home-sold-out.jpg")
        hidden_category = Category.objects.create(name="Nội bộ", is_active=False)
        Dish.objects.create(
            code="HOME04", name="Món ngừng danh mục", category=hidden_category,
            unit=self.unit, price=10000,
        )
        hidden_unit = Unit.objects.create(name="Đơn vị ngừng", is_active=False)
        Dish.objects.create(
            code="HOME05", name="Món ngừng đơn vị", category=self.category,
            unit=hidden_unit, price=10000,
        )
        with self.assertNumQueries(2):
            context = homepage_context()
            self.assertEqual([dish.pk for dish in context["menu_dishes"]], [self.rice.pk, self.sold_out.pk])
            self.assertEqual([dish.pk for dish in context["hero_dishes"]], [self.rice.pk])
            self.assertEqual(context["primary_dish"].image.name, "dishes/home-rice.jpg")
            self.assertEqual(context["home_categories"][0]["count"], 2)
            self.assertEqual(context["home_categories"][0]["cover"].pk, self.rice.pk)

    def test_missing_photos_use_placeholder_and_empty_menu_still_renders(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "images/dish-placeholder.svg")
        Dish.objects.update(status=Dish.Status.INACTIVE)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Căn bếp đang cập nhật thực đơn")
        self.assertContains(response, "images/dish-placeholder.svg")
        self.assertEqual(response.context["menu_dish_count"], 0)
        self.assertIsNone(response.context["primary_dish"])
