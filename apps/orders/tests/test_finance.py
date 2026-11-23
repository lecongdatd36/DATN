from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.customers.models import Customer
from apps.menu.models import Category, Dish, Unit
from apps.seating.models import Area, DiningTable
from apps.orders import finance_services as finance, services
from apps.orders.models import CashShift, FinanceLog, Invoice, InvoiceRefund, OnlinePayment, Order, OrderItem, Payment, PaymentReconciliation, ZaloPayTransaction
from apps.orders.ai_export import transaction_rows
from apps.reports.selectors import report_data


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_superuser(username="finance-manager", password="Test!123")
        cls.cashier = get_user_model().objects.create_user(username="finance-cashier", password="Test!123")
        cls.cashier.groups.add(Group.objects.get(name="CASHIER"))
        cls.waiter = get_user_model().objects.create_user(username="finance-waiter")
        cls.waiter.groups.add(Group.objects.get(name="WAITER"))
        cls.customer = Customer.objects.create(full_name="Finance customer", phone="0901100000")
        cls.table = DiningTable.objects.create(code="FIN01", area=Area.objects.create(name="Finance area"), capacity=4)
        cls.dish = Dish.objects.create(code="FIN-DISH", name="Finance dish", category=Category.objects.create(name="Finance menu"),
            unit=Unit.objects.create(name="Finance portion"), price=100000)

    def order(self):
        row = Order.objects.create(status="PAYMENT_REQUESTED", table=self.table, customer=self.customer)
        row.order_code = f"FN{row.pk}"
        row.save(update_fields=("order_code",))
        OrderItem.objects.create(order=row, dish=self.dish, dish_code=self.dish.code, dish_name=self.dish.name,
            unit_name=self.dish.unit.name, unit_price=100000, quantity=1, status="SERVED")
        return row

    def paid(self, method="CASH"):
        row = self.order()
        invoice = services.process_payment(actor=self.cashier, order_id=row.pk, payment_method=method)
        return invoice, invoice.payments.get()

    def request(self, payment, **changes):
        data = dict(actor=self.cashier, payment_id=payment.pk, amount=30000, method="BANK_TRANSFER", reason="Customer refund request")
        data.update(changes)
        return finance.request_refund(**data)

    def approve(self, refund):
        return finance.review_refund(actor=self.manager, refund_id=refund.pk, revision=refund.revision, approve=True, note="Manager verified request")

    def complete(self, refund, **changes):
        data = dict(actor=self.cashier, refund_id=refund.pk, revision=refund.revision,
            reference=f"REFUND-{refund.pk}", note="Transfer completed to customer", verified=True)
        data.update(changes)
        return finance.complete_refund(**data)

    def test_refund_keeps_original_receipt_and_updates_membership_once(self):
        invoice, payment = self.paid()
        refund = self.approve(self.request(payment))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_spending, 100000)
        completed = self.complete(refund)
        self.complete(refund)
        invoice.refresh_from_db(); payment.refresh_from_db(); self.customer.refresh_from_db()
        self.assertEqual((invoice.total, invoice.paid_amount, invoice.refunded_amount), (100000, 100000, 30000))
        self.assertEqual(payment.amount, 100000)
        self.assertEqual(self.customer.total_spending, 70000)
        self.assertEqual(FinanceLog.objects.filter(refund=completed, action="Ghi nhận đã hoàn").count(), 1)
        self.assertEqual(list(transaction_rows()), [])

    def test_pending_refunds_reserve_the_receipt_and_rejection_releases_it(self):
        _, payment = self.paid()
        refund = self.request(payment, amount=80000)
        with self.assertRaises(ValidationError):
            self.request(payment, amount=30000)
        finance.review_refund(actor=self.manager, refund_id=refund.pk, revision=refund.revision, approve=False, note="Incorrect request rejected")
        self.assertEqual(self.request(payment, amount=100000).amount, 100000)

    def test_request_idempotency_rejects_reused_key_with_different_content(self):
        _, payment = self.paid()
        key = uuid4()
        first = self.request(payment, request_key=key)
        self.assertEqual(self.request(payment, request_key=key).pk, first.pk)
        with self.assertRaises(ValidationError):
            self.request(payment, request_key=key, amount=1)

    def test_refund_permissions_recheck_actor_and_require_approval(self):
        _, payment = self.paid()
        with self.assertRaises(PermissionDenied):
            self.request(payment, actor=self.waiter)
        row = self.request(payment)
        with self.assertRaises(PermissionDenied):
            finance.review_refund(actor=self.cashier, refund_id=row.pk, revision=1, approve=True, note="Cannot self approve")
        with self.assertRaises(ValidationError):
            self.complete(row)
        self.cashier.is_active = False
        self.cashier.save(update_fields=("is_active",))
        with self.assertRaises(PermissionDenied):
            self.request(payment)

    def test_refund_requires_proof_confirmation_and_valid_amounts(self):
        _, payment = self.paid()
        for amount in (0, -1, "NaN", "Infinity", "1.5", 100001):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                self.request(payment, amount=amount)
        row = self.approve(self.request(payment))
        for changes in ({"verified": False}, {"reference": ""}, {"revision": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.complete(row, **changes)
        self.assertEqual(Invoice.objects.get(pk=payment.invoice_id).refunded_amount, 0)

    def test_duplicate_bank_proof_cannot_complete_two_refunds(self):
        _, payment = self.paid()
        one = self.approve(self.request(payment))
        two = self.approve(self.request(payment))
        self.complete(one, reference="BANK-ONE")
        with self.assertRaises(ValidationError):
            self.complete(two, reference="BANK-ONE")
        two.refresh_from_db()
        self.assertEqual(two.status, "APPROVED")

    def test_cash_shift_collect_refund_close_and_review(self):
        shift = finance.open_shift(actor=self.cashier, opening_amount=50000)
        invoice, payment = self.paid()
        self.assertEqual(payment.cash_shift_id, shift.pk)
        row = self.approve(self.request(payment, method="CASH"))
        self.complete(row, reference="")
        self.assertEqual(Decimal(finance.shift_totals(shift)["expected_cash"]), 120000)
        with self.assertRaises(ValidationError):
            finance.close_shift(actor=self.cashier, shift_id=shift.pk, revision=shift.revision, counted_amount=119000)
        closed = finance.close_shift(actor=self.cashier, shift_id=shift.pk, revision=shift.revision,
            counted_amount=119000, note="Cash count discrepancy recorded")
        self.assertEqual((closed.expected_amount, closed.difference), (120000, -1000))
        snapshot = closed.totals_snapshot
        self.paid()
        closed.refresh_from_db()
        self.assertEqual(closed.totals_snapshot, snapshot)
        with self.assertRaises(PermissionDenied):
            finance.review_shift(actor=self.cashier, shift_id=closed.pk, revision=closed.revision, note="Verify handover")
        reviewed = finance.review_shift(actor=self.manager, shift_id=closed.pk, revision=closed.revision, note="Verified cash handover")
        self.assertEqual(reviewed.status, "REVIEWED")
        self.assertEqual(closed.payments.count(), 1)

    def test_cash_refund_requires_open_shift_with_sufficient_cash(self):
        _, payment = self.paid()
        row = self.approve(self.request(payment, method="CASH"))
        with self.assertRaises(ValidationError):
            self.complete(row)
        finance.open_shift(actor=self.cashier, opening_amount=0)
        with self.assertRaises(ValidationError):
            self.complete(row)

    @override_settings(CASH_SHIFT_REQUIRED=True)
    def test_required_shift_rolls_back_checkout_without_open_shift(self):
        order = self.order()
        with self.assertRaises(ValidationError):
            services.process_payment(actor=self.cashier, order_id=order.pk, payment_method="CASH")
        self.assertFalse(Invoice.objects.filter(order=order).exists())
        order.refresh_from_db()
        self.assertEqual(order.status, "PAYMENT_REQUESTED")

    def test_one_open_shift_and_stale_close_are_blocked(self):
        shift = finance.open_shift(actor=self.cashier, opening_amount=0)
        with self.assertRaises(ValidationError):
            finance.open_shift(actor=self.cashier, opening_amount=0)
        with self.assertRaises(ValidationError):
            finance.close_shift(actor=self.cashier, shift_id=shift.pk, revision=0, counted_amount=0)

    def review_transaction(self, order, amount=100000, provider="12345"):
        online = OnlinePayment.objects.create(order=order, txn_ref=f"ZP-{order.pk}", amount=amount, subtotal=100000)
        return ZaloPayTransaction.objects.create(app_id=1, app_trans_id=online.txn_ref, order_payment=online,
            amount=amount, status="REVIEW", zp_trans_id=provider, paid_at=timezone.now()-timedelta(minutes=5), expires_at=timezone.now())

    def test_review_money_can_be_refunded_without_duplicate_invoice_receipt(self):
        invoice, _ = self.paid()
        row = self.review_transaction(invoice.order)
        before = report_data(timezone.now()-timedelta(hours=1), timezone.now()+timedelta(hours=1))
        self.assertEqual(before["collected"], 200000)
        result = finance.reconcile_zalopay(actor=self.manager, transaction_id=row.pk, outcome="REFUNDED",
            reference="ZP-REFUND-123", reason="Late duplicate payment refunded", verified=True)
        self.assertEqual(result.outcome, "REFUNDED")
        after = report_data(timezone.now()-timedelta(hours=1), timezone.now()+timedelta(hours=1))
        self.assertEqual(after["collected"], 100000)
        self.assertEqual(after["revenue"], 100000)
        self.assertEqual(invoice.payments.count(), 1)
        row.order_payment.refresh_from_db()
        self.assertEqual(row.order_payment.status, "CANCELLED")
        with self.assertRaises(ValidationError):
            finance.reconcile_zalopay(actor=self.manager, transaction_id=row.pk, outcome="REFUNDED",
                reference="ZP-REFUND-123", reason="Repeated payment refund", verified=True)

    def test_verified_review_can_apply_to_matching_unpaid_order(self):
        order = self.order()
        row = self.review_transaction(order)
        finance.reconcile_zalopay(actor=self.manager, transaction_id=row.pk, outcome="APPLIED", reference="CHECK-123",
            reason="Verified gateway funds and current order", verified=True)
        invoice = Invoice.objects.get(order=order)
        row.refresh_from_db()
        self.assertEqual((invoice.status, row.status), ("PAID", "PAID"))
        self.assertEqual(invoice.payments.get().created_at, row.paid_at)

    def test_reconciliation_rejects_unverified_unmatched_or_wrong_amount(self):
        row = self.review_transaction(self.order(), amount=90000)
        for outcome, verified in (("APPLIED", True), ("MATCHED", True), ("REFUNDED", False)):
            with self.subTest(outcome=outcome), self.assertRaises(ValidationError):
                finance.reconcile_zalopay(actor=self.manager, transaction_id=row.pk, outcome=outcome,
                    reference="CHECK-123", reason="Verified gateway payment", verified=verified)
        self.assertFalse(PaymentReconciliation.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_report_refunds_reduce_net_revenue_not_receipt_method_share(self):
        _, payment = self.paid()
        row = self.approve(self.request(payment, amount=50000))
        self.complete(row)
        report = report_data(timezone.now()-timedelta(hours=1), timezone.now()+timedelta(hours=1))
        self.assertEqual((report["gross_revenue"], report["revenue"], report["collected"]), (100000, 50000, 50000))
        self.assertEqual(report["payment_methods"][0]["percent"], 100)
        from apps.accounts.dashboard import dashboard_data
        self.assertEqual(dashboard_data(self.manager)["revenue"], 50000)

    def test_refund_of_past_invoice_is_a_negative_revenue_entry_today(self):
        import csv
        from io import StringIO
        from apps.accounts.dashboard import dashboard_data
        invoice, payment = self.paid()
        invoice.closed_at = timezone.now()-timedelta(days=2)
        invoice.save(update_fields=("closed_at",))
        self.complete(self.approve(self.request(payment, amount=50000)))
        dashboard = dashboard_data(self.manager)
        self.assertEqual(dashboard["revenue"], -50000)
        self.assertEqual(dashboard["chart"]["revenue"][-1], -50000)
        self.client.force_login(self.manager)
        today = timezone.localdate().isoformat()
        response = self.client.get(reverse("reports:export_revenue"), {"date_from": today, "date_to": today})
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(sum(Decimal(row["Doanh thu"]) for row in rows), -50000)
        self.assertTrue(rows[0]["Loại bút toán"].startswith("HOAN_TIEN"))

    def test_finance_views_permissions_and_post_workflow(self):
        pages = ("cash_shifts", "refunds", "reconciliation")
        for page in pages:
            self.assertEqual(self.client.get(reverse("orders:"+page)).status_code, 302)
        self.client.force_login(self.waiter)
        for page in pages:
            self.assertEqual(self.client.get(reverse("orders:"+page)).status_code, 403)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("orders:cash_shifts")).status_code, 200)
        self.assertEqual(self.client.get(reverse("orders:refunds")).status_code, 200)
        self.assertEqual(self.client.get(reverse("orders:reconciliation")).status_code, 403)
        response = self.client.post(reverse("orders:cash_shifts"), {"opening_amount": 0, "note": "Start shift"})
        self.assertEqual(response.status_code, 302)
        shift = CashShift.objects.get()
        self.assertEqual(self.client.get(reverse("orders:cash_shift_detail", args=[shift.pk])).status_code, 200)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("orders:reconciliation")).status_code, 200)

    @override_settings(APRIORI_QUALITY_GATE_ENABLED=True)
    def test_quality_gate_uses_only_live_unrefunded_popular_dishes(self):
        from apps.menu.recommendations import dish_recommendations
        selected = Dish.objects.create(code="FIN-SELECTED", name="Selected dish", category=self.dish.category, unit=self.dish.unit, price=1000)
        invoice, _ = self.paid()
        self.assertEqual([row["id"] for row in dish_recommendations([selected.pk])], [self.dish.pk])
        self.assertEqual(dish_recommendations([self.dish.pk]), [])
        invoice.refunded_amount = 10000
        invoice.save(update_fields=("refunded_amount",))
        self.assertEqual(dish_recommendations([selected.pk]), [])

    def test_ai_quality_pages_are_report_permission_protected(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("reports:ai_quality")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:ai_transactions")).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("reports:ai_quality")).status_code, 200)
        response = self.client.get(reverse("reports:ai_transactions"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.customer.full_name.encode(), response.content)
        self.assertNotIn(self.customer.phone.encode(), response.content)
