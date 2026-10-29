import csv
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.customers.models import Customer
from apps.menu.models import Category, Dish, Unit
from apps.orders.ai_export import transaction_rows
from apps.orders.models import Invoice, Order, OrderItem


class AITransactionExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(full_name="Private Customer", phone="0901234567")
        category = Category.objects.create(name="Export dishes")
        unit = Unit.objects.create(name="Export portion")
        cls.dish = Dish.objects.create(code="AIX01", name="Cơm gà", category=category, unit=unit, price=50000)
        cls.other = Dish.objects.create(code="AIX02", name="Canh rau", category=category, unit=unit, price=20000)
        cls.closed = timezone.make_aware(datetime(2026, 10, 1, 0, 15))

    def paid_order(self, *, split_root=None, closed=None):
        order = Order.objects.create(status=Order.Status.COMPLETED, customer=self.customer, split_root=split_root)
        Invoice.objects.create(order=order, invoice_code=f"AI-{order.pk}", status=Invoice.Status.PAID,
                               closed_at=closed or self.closed, total=50000, paid_amount=50000)
        return order

    def item(self, order, *, dish=None, quantity=1, status=OrderItem.Status.SERVED):
        dish = dish or self.dish
        return OrderItem.objects.create(order=order, dish=dish, dish_code=dish.code, dish_name=dish.name,
                                         unit_name=dish.unit.name, unit_price=dish.price, quantity=quantity,
                                         status=status, cancellation_reason="Cancelled" if status == OrderItem.Status.CANCELLED else "",
                                         cancelled_at=self.closed if status == OrderItem.Status.CANCELLED else None)

    def test_only_settled_orders_and_served_items_are_exported(self):
        order = self.paid_order()
        self.item(order, quantity=2)
        self.item(order, quantity=3)
        self.item(order, dish=self.other, status=OrderItem.Status.CANCELLED)
        self.item(order, dish=self.other, status=OrderItem.Status.DRAFT)
        unpaid = Order.objects.create(status=Order.Status.PAYMENT_REQUESTED)
        self.item(unpaid, dish=self.other)
        before = (Order.objects.count(), OrderItem.objects.count(), Invoice.objects.count())
        rows = list(transaction_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 5)
        self.assertEqual(rows[0]["dish_id"], str(self.dish.pk))
        self.assertEqual(rows[0]["data_source"], "application_export")
        self.assertEqual(before, (Order.objects.count(), OrderItem.objects.count(), Invoice.objects.count()))

    def test_split_checks_form_one_basket_using_latest_settlement(self):
        root = self.paid_order(closed=self.closed - timedelta(days=1))
        child = self.paid_order(split_root=root)
        self.item(root)
        self.item(child, quantity=2)
        self.item(child, dish=self.other)
        rows = list(transaction_rows(start_at=self.closed.replace(hour=0, minute=0)))
        self.assertEqual({row["basket_id"] for row in rows}, {f"VISIT-{root.pk}"})
        self.assertEqual({row["basket_closed_at"] for row in rows}, {self.closed.isoformat()})
        self.assertEqual(next(row["quantity"] for row in rows if row["dish_id"] == str(self.dish.pk)), 3)

    def test_group_is_excluded_until_all_active_checks_are_settled(self):
        root = self.paid_order()
        self.item(root)
        child = Order.objects.create(split_root=root, status=Order.Status.PAYMENT_REQUESTED)
        self.item(child, dish=self.other)
        self.assertEqual(list(transaction_rows()), [])
        child.status = Order.Status.CANCELLED
        child.save()
        self.assertEqual(len(list(transaction_rows())), 1)

    def test_missing_invoice_timestamp_does_not_mark_group_complete(self):
        root = self.paid_order()
        self.item(root)
        child = self.paid_order(split_root=root)
        child.invoice.closed_at = None
        child.invoice.save()
        self.item(child, dish=self.other)
        self.assertEqual(list(transaction_rows()), [])

    def test_command_uses_business_dates_and_omits_customer_details(self):
        order = self.paid_order()
        self.item(order)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "transactions.csv"
            call_command("export_ai_transactions", output=output, date_from=self.closed.date(),
                         date_to=self.closed.date(), stdout=StringIO())
            text = output.read_text(encoding="utf-8-sig")
            rows = list(csv.DictReader(StringIO(text)))
            self.assertEqual(len(rows), 1)
            self.assertNotIn(self.customer.full_name, text)
            self.assertNotIn(self.customer.phone, text)
            self.assertNotIn("customer_id", rows[0])
            with self.assertRaises(CommandError):
                call_command("export_ai_transactions", output=output, stdout=StringIO())
            self.assertEqual(output.read_text(encoding="utf-8-sig"), text)

    def test_invalid_period_does_not_create_output(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "invalid.csv"
            with self.assertRaises(CommandError):
                call_command("export_ai_transactions", output=output, date_from=self.closed.date(),
                             date_to=(self.closed - timedelta(days=1)).date(), stdout=StringIO())
            self.assertFalse(output.exists())
