from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.inventory.models import Ingredient, InventoryTransaction, PurchaseReceipt, RecipeIngredient, Stocktake, Supplier, WasteRecord
from apps.inventory.services import (
    add_purchase_line, confirm_purchase_receipt, create_purchase_receipt, create_stocktake,
    post_stocktake, record_inventory_transaction, record_waste,
)
from apps.menu.models import Category, Dish, Unit


class InventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="inventory_flow", password="StrongPass123!")
        cls.user.groups.add(Group.objects.get(name="INVENTORY"))
        cls.ingredient = Ingredient.objects.create(code="NL01", name="Gạo", unit="kg", low_stock_threshold=5)

    def test_import_export_and_adjustment_are_atomic(self):
        record_inventory_transaction(actor=self.user, ingredient_id=self.ingredient.pk, transaction_type="IMPORT", quantity="10", unit_cost="10000")
        record_inventory_transaction(actor=self.user, ingredient_id=self.ingredient.pk, transaction_type="EXPORT", quantity="3")
        transaction = record_inventory_transaction(actor=self.user, ingredient_id=self.ingredient.pk, transaction_type="ADJUSTMENT", quantity="6.5")
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity, Decimal("6.500"))
        self.assertEqual(transaction.stock_before, Decimal("7.000"))
        self.assertEqual(InventoryTransaction.objects.count(), 3)

    def test_adjustment_can_set_stock_to_zero_but_import_requires_cost(self):
        record_inventory_transaction(
            actor=self.user, ingredient_id=self.ingredient.pk,
            transaction_type="IMPORT", quantity="2", unit_cost="10000",
        )
        record_inventory_transaction(
            actor=self.user, ingredient_id=self.ingredient.pk,
            transaction_type="ADJUSTMENT", quantity="0",
        )
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity, Decimal("0.000"))
        with self.assertRaisesMessage(ValidationError, "đơn giá"):
            record_inventory_transaction(
                actor=self.user, ingredient_id=self.ingredient.pk,
                transaction_type="IMPORT", quantity="1", unit_cost="0",
            )

    def test_import_updates_weighted_average_cost(self):
        record_inventory_transaction(
            actor=self.user, ingredient_id=self.ingredient.pk,
            transaction_type="IMPORT", quantity="10", unit_cost="10000",
        )
        record_inventory_transaction(
            actor=self.user, ingredient_id=self.ingredient.pk,
            transaction_type="IMPORT", quantity="10", unit_cost="20000",
        )
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity, Decimal("20.000"))
        self.assertEqual(self.ingredient.average_unit_cost, Decimal("15000.00"))

    def test_inventory_user_can_manage_catalog_and_recipe_from_workspace(self):
        category = Category.objects.create(name="Món kho")
        unit = Unit.objects.create(name="Phần kho")
        dish = Dish.objects.create(code="KHO01", name="Cơm kho", category=category, unit=unit, price=50000)
        self.client.force_login(self.user)

        workspace = self.client.get(reverse("inventory:workspace"))
        self.assertContains(workspace, "Công thức món")
        self.assertContains(workspace, dish.name)
        self.assertEqual(self.client.get(reverse("inventory:ingredient_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:supplier_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:recipe", args=[dish.pk])).status_code, 200)

        response = self.client.post(reverse("inventory:ingredient_create"), {
            "code": "NL-MOI", "name": "Nguyên liệu mới", "unit": "kg",
            "low_stock_threshold": "1", "is_active": "on",
        })
        self.assertRedirects(response, reverse("inventory:workspace"))
        new_ingredient = Ingredient.objects.get(code="NL-MOI")

        response = self.client.post(reverse("inventory:supplier_create"), {
            "name": "Nhà cung cấp A", "phone": "0900000000", "address": "Địa chỉ A", "is_active": "on",
        })
        self.assertRedirects(response, reverse("inventory:workspace"))
        self.assertTrue(Supplier.objects.filter(name="Nhà cung cấp A").exists())

        response = self.client.post(reverse("inventory:recipe", args=[dish.pk]), {
            "ingredient": new_ingredient.pk, "quantity": "0.250",
        })
        self.assertRedirects(response, reverse("inventory:recipe", args=[dish.pk]))
        self.assertTrue(RecipeIngredient.objects.filter(dish=dish, ingredient=new_ingredient, quantity=Decimal("0.250")).exists())

    def test_purchase_stocktake_and_waste_keep_audited_stock(self):
        supplier = Supplier.objects.create(name="Nhà cung cấp kiểm thử")
        receipt = create_purchase_receipt(actor=self.user, supplier_id=supplier.pk, invoice_number="HD-001")
        add_purchase_line(
            actor=self.user, receipt_id=receipt.pk, ingredient_id=self.ingredient.pk,
            quantity=Decimal("10"), unit_cost=Decimal("20000"),
        )
        confirm_purchase_receipt(actor=self.user, receipt_id=receipt.pk)
        self.ingredient.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, PurchaseReceipt.Status.RECEIVED)
        self.assertEqual(self.ingredient.stock_quantity, Decimal("10.000"))
        self.assertEqual(self.ingredient.average_unit_cost, Decimal("20000.00"))
        self.assertEqual(InventoryTransaction.objects.filter(transaction_type="PURCHASE").count(), 1)
        with self.assertRaises(ValidationError):
            confirm_purchase_receipt(actor=self.user, receipt_id=receipt.pk)

        stocktake = create_stocktake(actor=self.user, note="Cuối ca")
        line = stocktake.lines.get(ingredient=self.ingredient)
        post_stocktake(actor=self.user, stocktake_id=stocktake.pk, actual_quantities={line.pk: "8.5"})
        self.ingredient.refresh_from_db()
        stocktake.refresh_from_db()
        self.assertEqual(stocktake.status, Stocktake.Status.POSTED)
        self.assertEqual(self.ingredient.stock_quantity, Decimal("8.500"))

        waste = record_waste(
            actor=self.user, ingredient_id=self.ingredient.pk,
            quantity="0.5", reason=WasteRecord.Reason.SPOILED, note="Không đạt chất lượng",
        )
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity, Decimal("8.000"))
        self.assertEqual(waste.total_cost, Decimal("10000"))
        self.assertEqual(InventoryTransaction.objects.filter(transaction_type="WASTE").count(), 1)

    def test_new_inventory_workflow_pages_render(self):
        self.client.force_login(self.user)
        supplier = Supplier.objects.create(name="Nhà cung cấp màn hình")
        receipt = create_purchase_receipt(actor=self.user, supplier_id=supplier.pk)
        stocktake = create_stocktake(actor=self.user)
        for url in (
            reverse("inventory:purchase_list"),
            reverse("inventory:purchase_detail", args=[receipt.pk]),
            reverse("inventory:stocktake_list"),
            reverse("inventory:stocktake_detail", args=[stocktake.pk]),
            reverse("inventory:waste"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_stock_shortage_auto_sells_out_but_restock_requires_manual_reopen(self):
        category = Category.objects.create(name="Món tự động hết")
        unit = Unit.objects.create(name="Phần tự động")
        dish = Dish.objects.create(
            code="AUTO-HET",
            name="Món theo kho",
            category=category,
            unit=unit,
            price=50000,
            tracks_inventory=True,
            status=Dish.Status.AVAILABLE,
        )
        RecipeIngredient.objects.create(dish=dish, ingredient=self.ingredient, quantity=Decimal("1"))
        record_inventory_transaction(
            actor=self.user,
            ingredient_id=self.ingredient.pk,
            transaction_type=InventoryTransaction.Type.IMPORT,
            quantity="2",
            unit_cost="10000",
        )
        dish.refresh_from_db()
        self.assertEqual(dish.status, Dish.Status.AVAILABLE)

        record_inventory_transaction(
            actor=self.user,
            ingredient_id=self.ingredient.pk,
            transaction_type=InventoryTransaction.Type.EXPORT,
            quantity="2",
        )
        dish.refresh_from_db()
        self.assertEqual(dish.status, Dish.Status.SOLD_OUT)
        self.assertIsNotNone(dish.inventory_sold_out_at)

        record_inventory_transaction(
            actor=self.user,
            ingredient_id=self.ingredient.pk,
            transaction_type=InventoryTransaction.Type.IMPORT,
            quantity="2",
            unit_cost="10000",
        )
        dish.refresh_from_db()
        self.assertEqual(dish.status, Dish.Status.SOLD_OUT)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("inventory:workspace")), "Đủ kho · cần mở bán")
