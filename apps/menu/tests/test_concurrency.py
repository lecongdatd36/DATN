from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings

from apps.menu.models import Category, Unit, Dish, MenuActivityLog
from apps.menu.services import save_dish, save_catalog, change_availability


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MenuConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.actors = [get_user_model().objects.create_superuser(username=f"menu_admin_{i}", password="Test!123") for i in range(2)]
        self.category = Category.objects.create(name="Món chính")
        self.unit = Unit.objects.create(name="Phần")

    def run_parallel(self, action):
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

    def create_dish(self, actor):
        return save_dish(actor=actor, code="M001", name="Cơm", category_id=self.category.pk,
                         unit_id=self.unit.pk, price=85000, status="AVAILABLE")

    def test_duplicate_dish_creation_commits_once(self):
        def action(actor, index):
            self.create_dish(actor)
            return "created"
        self.assertCountEqual(self.run_parallel(action), ["created", "blocked"])
        self.assertEqual(Dish.objects.count(), 1)
        self.assertEqual(MenuActivityLog.objects.count(), 1)

    def test_price_edit_and_kitchen_status_change_cannot_overwrite(self):
        dish = self.create_dish(self.actors[0])

        def action(actor, index):
            if index == 0:
                save_dish(actor=actor, dish_id=dish.pk, code=dish.code, name=dish.name, category_id=self.category.pk,
                          unit_id=self.unit.pk, price=95000, status="AVAILABLE", expected_revision=1)
                return "price"
            change_availability(actor=actor, dish_id=dish.pk, status="SOLD_OUT", expected_revision=1)
            return "status"
        results = self.run_parallel(action)
        self.assertEqual(results.count("blocked"), 1)
        dish.refresh_from_db()
        self.assertEqual(dish.revision, 2)
        self.assertIn((dish.price, dish.status), [(95000, "AVAILABLE"), (85000, "SOLD_OUT")])
        self.assertEqual(MenuActivityLog.objects.count(), 2)

    def test_category_shutdown_and_creation_leave_no_orderable_dish(self):
        def action(actor, index):
            if index == 0:
                save_catalog(actor=actor, kind="category", object_id=self.category.pk, name=self.category.name, is_active=False, expected_revision=1)
                return "closed"
            self.create_dish(actor)
            return "created"
        results = self.run_parallel(action)
        self.assertEqual(results[0], "closed")
        self.assertIn(results[1], ("created", "blocked"))
        self.category.refresh_from_db()
        self.assertFalse(self.category.is_active)
        for dish in Dish.objects.select_related("category", "unit"):
            self.assertFalse(dish.is_orderable)
