from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from apps.orders import finance_services as finance
from apps.orders.models import CashShift, FinanceLog, Invoice, InvoiceRefund, Order, Payment
from core.rate_limits import consume_budgets


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinanceConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.actor = get_user_model().objects.create_superuser(username="finance-race", password="Test!123")

    def race(self, action, workers=2):
        barrier = Barrier(workers)
        def work(index):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                barrier.wait(timeout=10)
                try:
                    return action(actor, index)
                except ValidationError:
                    return "blocked"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, index) for index in range(workers)]
            return [future.result(timeout=25) for future in futures]

    def test_concurrent_open_creates_exactly_one_cash_shift(self):
        results = self.race(lambda actor, _: finance.open_shift(actor=actor, opening_amount=100000).pk)
        self.assertEqual(results.count("blocked"), 1)
        self.assertEqual(CashShift.objects.filter(status="OPEN").count(), 1)

    def test_concurrent_refund_submissions_complete_only_once(self):
        shift = finance.open_shift(actor=self.actor, opening_amount=100000)
        invoice = Invoice.objects.create(order=Order.objects.create(), invoice_code="RACE-REFUND", total=100000,
            paid_amount=100000, status="PAID", closed_at=timezone.now())
        payment = Payment.objects.create(invoice=invoice, amount=100000, method="CASH")
        row = finance.request_refund(actor=self.actor, payment_id=payment.pk, amount=30000, method="CASH", reason="Concurrent refund test")
        row = finance.review_refund(actor=self.actor, refund_id=row.pk, revision=1, approve=True, note="Verified refund request")
        results = self.race(lambda actor, _: finance.complete_refund(actor=actor, refund_id=row.pk, revision=row.revision,
            reference="", note="Cash returned to customer", verified=True).pk)
        self.assertEqual(results, [row.pk, row.pk])
        invoice.refresh_from_db()
        self.assertEqual(invoice.refunded_amount, 30000)
        self.assertEqual(FinanceLog.objects.filter(refund=row, action="Ghi nhận đã hoàn").count(), 1)
        self.assertEqual(shift.refunds.filter(status="COMPLETED").count(), 1)

    def test_concurrent_close_preserves_one_snapshot(self):
        shift = finance.open_shift(actor=self.actor, opening_amount=100000)
        results = self.race(lambda actor, _: finance.close_shift(actor=actor, shift_id=shift.pk, revision=1, counted_amount=100000).pk)
        self.assertEqual(results.count("blocked"), 1)
        shift.refresh_from_db()
        self.assertEqual((shift.status, shift.expected_amount, shift.counted_amount), ("CLOSED", 100000, 100000))
        self.assertEqual(FinanceLog.objects.filter(shift=shift, action="Chốt ca thu ngân").count(), 1)

    def test_concurrent_rate_budgets_never_exceed_limit(self):
        results = self.race(lambda actor, _: consume_budgets([("race", "one-source", 2, 300)]), workers=6)
        self.assertEqual(results.count(0), 2)
        self.assertTrue(all(type(result) is int for result in results))
