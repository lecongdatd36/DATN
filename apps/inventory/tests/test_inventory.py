from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.inventory.models import Ingredient, InventoryTransaction
from apps.inventory.services import record_inventory_transaction


class InventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="inventory_flow", password="StrongPass123!")
        cls.user.groups.add(Group.objects.get(name="INVENTORY"))
        cls.ingredient = Ingredient.objects.create(code="NL01", name="Gạo", unit="kg", low_stock_threshold=5)

    def test_import_export_and_adjustment_are_atomic(self):
        record_inventory_transaction(actor=self.user, ingredient_id=self.ingredient.pk, transaction_type="IMPORT", quantity="10")
        record_inventory_transaction(actor=self.user, ingredient_id=self.ingredient.pk, transaction_type="EXPORT", quantity="3")
        transaction = record_inventory_transaction(actor=self.user, ingredient_id=self.ingredient.pk, transaction_type="ADJUSTMENT", quantity="6.5")
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity, Decimal("6.500"))
        self.assertEqual(transaction.stock_before, Decimal("7.000"))
        self.assertEqual(InventoryTransaction.objects.count(), 3)
