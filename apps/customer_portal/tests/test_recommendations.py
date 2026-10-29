import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.menu.models import Category, Dish, Unit
from apps.orders.models import Order, OrderItem
from apps.seating.models import Area, DiningTable, DiningTableQRToken


class MenuRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dishes = []
        for number in range(5):
            category = Category.objects.create(name=f"Recommendation category {number}")
            unit = Unit.objects.create(name=f"Recommendation unit {number}")
            cls.dishes.append(Dish.objects.create(code=f"REC{number}", name=f"Món gợi ý {number}",
                                                   category=category, unit=unit, price=10000 + number * 1000))
        cls.manager = get_user_model().objects.create_superuser(username="recommend_manager", password="Recommendations-123!")
        cls.table = DiningTable.objects.create(code="RE01", area=Area.objects.create(name="Recommendations"), capacity=4)
        cls.token = DiningTableQRToken.objects.create(table=cls.table)
        cls.order = Order.objects.create(table=cls.table, status=Order.Status.OPEN)
        dish = cls.dishes[0]
        OrderItem.objects.create(order=cls.order, dish=dish, dish_code=dish.code, dish_name=dish.name,
                                  unit_name=dish.unit.name, unit_price=dish.price, quantity=1)

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "model.json"
        self.model = {
            "schema_version": 1, "algorithm": "Apriori", "data_source": "application_export",
            "catalog": [{"dish_id": f"trained-{i}", "dish_code": dish.code, "dish_name": "Old name"}
                        for i, dish in enumerate(self.dishes)],
            "rules": [{"antecedents": ["trained-0"], "consequents": [f"trained-{i}"],
                       "support": 0.2, "confidence": 1 - i / 10, "lift": 2} for i in range(1, 5)],
        }
        self.write_model()
        self.settings_override = override_settings(APRIORI_MODEL_PATH=self.path)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def write_model(self):
        self.path.write_text(json.dumps(self.model, ensure_ascii=False), encoding="utf-8")

    def query(self, *ids):
        return self.client.get(reverse("customer_portal:recommendations"), {"dish": ids})

    def test_uses_codes_across_database_ids_and_live_names_and_prices(self):
        before = (Order.objects.count(), OrderItem.objects.count())
        response = self.query(self.dishes[0].pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [
            {"id": dish.pk, "name": dish.name, "price": str(dish.price)} for dish in self.dishes[1:4]
        ])
        self.assertEqual((Order.objects.count(), OrderItem.objects.count()), before)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_never_recommends_an_already_selected_dish(self):
        payload = self.query(self.dishes[0].pk, self.dishes[1].pk).json()
        self.assertEqual([item["id"] for item in payload["items"]], [dish.pk for dish in self.dishes[2:]])

    def test_unavailable_items_are_removed_before_top_three_is_applied(self):
        Dish.objects.filter(pk=self.dishes[1].pk).update(status=Dish.Status.SOLD_OUT)
        Category.objects.filter(pk=self.dishes[2].category_id).update(is_active=False)
        Unit.objects.filter(pk=self.dishes[3].unit_id).update(is_active=False)
        self.assertEqual([item["id"] for item in self.query(self.dishes[0].pk).json()["items"]], [self.dishes[4].pk])

    def test_empty_and_unknown_selection_return_no_suggestions(self):
        self.assertEqual(self.query().json(), {"items": []})
        self.assertEqual(self.query(9999999).json(), {"items": []})

    def test_bad_input_and_post_are_rejected(self):
        for ids in (("no-id",), ("0",), ("-1",), ("9" * 30,), ("１",), tuple("1" for _ in range(51))):
            with self.subTest(ids=ids[:2]):
                self.assertEqual(self.query(*ids).status_code, 400)
        self.assertEqual(self.client.post(reverse("customer_portal:recommendations")).status_code, 405)

    def test_missing_and_invalid_model_do_not_break_the_menu(self):
        self.path.unlink()
        self.assertEqual(self.query(self.dishes[0].pk).json(), {"items": []})
        self.model["rules"][0]["consequents"] = ["unknown-model-item"]
        self.write_model()
        self.assertEqual(self.query(self.dishes[0].pk).json(), {"items": []})

    def test_synthetic_model_cannot_be_matched_to_live_menu(self):
        self.model["data_source"] = "synthetic_demo"
        self.write_model()
        self.assertEqual(self.query(self.dishes[0].pk).json(), {"items": []})

    def test_widgets_render_in_qr_mobile_and_desktop_menu(self):
        response = self.client.get(reverse("customer_portal:qr_table", args=[self.token.token]))
        self.assertContains(response, 'data-recommendation-mode="qr"')
        self.client.force_login(self.manager)
        response = self.client.get(reverse("sales:mobile"), {"page": "menu", "order": self.order.pk})
        self.assertContains(response, 'data-recommendation-mode="staff"')
        self.assertContains(response, f'data-recommendation-seed="{self.dishes[0].pk}"')
        response = self.client.get(reverse("sales:workspace"), {"order": self.order.pk})
        self.assertContains(response, 'data-recommendation-mode="pos"')
        self.assertContains(response, 'data-recommendations-order-status="OPEN"')
