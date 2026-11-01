from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.inventory.models import Ingredient, InventoryTransaction, RecipeIngredient, Supplier
from apps.inventory.services import add_purchase_line, confirm_purchase_receipt, create_purchase_receipt
from apps.menu.models import Category, Dish, Unit
from apps.orders import services
from apps.orders.models import OrderItem
from apps.seating.models import Area, DiningTable


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OrderStockFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "KITCHEN", "CASHIER"):
            user = get_user_model().objects.create_user(username=f"stock_{role.lower()}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        area = Area.objects.create(name="Stock flow area")
        cls.table = DiningTable.objects.create(code="STOCK01", area=area, capacity=4)
        category = Category.objects.create(name="Stock flow category")
        unit = Unit.objects.create(name="Stock flow portion")
        cls.dish = Dish.objects.create(
            code="STOCK-DISH", name="Stock flow dish", category=category, unit=unit,
            price=50000, tracks_inventory=True,
        )
        cls.ingredient = Ingredient.objects.create(code="STOCK-RICE", name="Rice", unit="kg")
        RecipeIngredient.objects.create(dish=cls.dish, ingredient=cls.ingredient, quantity=Decimal("0.200"))
        cls.supplier = Supplier.objects.create(name="Stock flow supplier")

    def stock(self):
        self.ingredient.refresh_from_db()
        return self.ingredient.stock_quantity

    def revision(self, order):
        order.refresh_from_db()
        return order.revision

    def purchase(self):
        receipt = create_purchase_receipt(actor=self.users["MANAGER"], supplier_id=self.supplier.pk)
        add_purchase_line(
            actor=self.users["MANAGER"], receipt_id=receipt.pk, ingredient_id=self.ingredient.pk,
            quantity=Decimal("10"), unit_cost=Decimal("50000"),
        )
        return receipt

    def open_order(self):
        return services.open_walk_in_order(actor=self.users["WAITER"], table_id=self.table.pk, party_size=2)

    def test_purchase_draft_receipt_kitchen_and_payment_change_stock_at_the_correct_steps(self):
        receipt = self.purchase()
        self.assertEqual(self.stock(), 0)
        self.assertFalse(InventoryTransaction.objects.exists())

        confirm_purchase_receipt(actor=self.users["MANAGER"], receipt_id=receipt.pk)
        self.assertEqual(self.stock(), Decimal("10"))
        self.assertEqual(self.ingredient.average_unit_cost, Decimal("50000"))
        with self.assertRaises(ValidationError):
            confirm_purchase_receipt(actor=self.users["MANAGER"], receipt_id=receipt.pk)
        self.assertEqual(self.stock(), Decimal("10"))

        order = self.open_order()
        item = services.add_item(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order),
            dish_id=self.dish.pk, quantity=1,
        )
        services.edit_item(
            actor=self.users["WAITER"], order_id=order.pk, item_id=item.pk,
            expected_revision=self.revision(order), quantity=2,
        )
        self.assertEqual(self.stock(), Decimal("10"))
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        self.assertEqual(self.stock(), Decimal("9.600"))
        item.refresh_from_db()
        self.assertEqual(item.total_cost, Decimal("20000"))
        with self.assertRaises(ValidationError):
            services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        for state, role in (("COOKING", "KITCHEN"), ("READY", "KITCHEN"), ("SERVED", "WAITER")):
            services.transition_item(
                actor=self.users[role], order_id=order.pk, item_id=item.pk,
                expected_revision=self.revision(order), target=state,
            )
            self.assertEqual(self.stock(), Decimal("9.600"))

        services.request_payment(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        services.process_payment(actor=self.users["CASHIER"], order_id=order.pk, payment_method="CASH")
        self.assertEqual(self.stock(), Decimal("9.600"))
        self.assertEqual(list(InventoryTransaction.objects.order_by("pk").values_list(
            "transaction_type", "quantity", "stock_before", "stock_after",
        )), [
            (InventoryTransaction.Type.PURCHASE, Decimal("10"), Decimal("0"), Decimal("10")),
            (InventoryTransaction.Type.SALE_USAGE, Decimal("0.400"), Decimal("10"), Decimal("9.600")),
        ])

    def test_cancelling_after_cooking_does_not_put_consumed_ingredients_back_into_stock(self):
        receipt = self.purchase()
        confirm_purchase_receipt(actor=self.users["MANAGER"], receipt_id=receipt.pk)
        order = self.open_order()
        item = services.add_item(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order),
            dish_id=self.dish.pk, quantity=2,
        )
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        services.transition_item(
            actor=self.users["KITCHEN"], order_id=order.pk, item_id=item.pk,
            expected_revision=self.revision(order), target=OrderItem.Status.COOKING,
        )
        services.transition_item(
            actor=self.users["MANAGER"], order_id=order.pk, item_id=item.pk,
            expected_revision=self.revision(order), target=OrderItem.Status.CANCELLED, reason="Customer cancelled after cooking started",
        )
        self.assertEqual(self.stock(), Decimal("9.600"))
        self.assertFalse(InventoryTransaction.objects.filter(transaction_type=InventoryTransaction.Type.SALE_RETURN).exists())
        item.refresh_from_db()
        self.assertIsNone(item.inventory_returned_at)
