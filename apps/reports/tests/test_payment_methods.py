from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from apps.orders.models import Invoice, Order, Payment
from apps.reservations.models import DepositPayment, DepositRefund, Reservation
from apps.reports.selectors import report_data


class PaymentMethodShareTests(TestCase):
    def test_past_deposit_refund_does_not_change_receipt_method_percentages(self):
        now = timezone.now()
        reservation = Reservation.objects.create(mode="TABLE", status="CANCELLED", source_digest="report-test",
            full_name="Report fixture", phone="0900000000", party_size=2, starts_at=now+timedelta(days=1))
        DepositPayment.objects.create(reservation=reservation, txn_ref="report-old-deposit", amount=200000,
            revision=1, status="PAID", paid_at=now-timedelta(days=2))
        DepositRefund.objects.create(reservation=reservation, amount=50000, reason="Prior deposit returned",
            status="COMPLETED", completed_at=now)
        invoice = Invoice.objects.create(order=Order.objects.create(), invoice_code="REPORT-SHARE", total=100000,
            paid_amount=100000, status="PAID", closed_at=now)
        Payment.objects.create(invoice=invoice, amount=100000, method="CASH")
        report = report_data(now-timedelta(hours=1), now+timedelta(hours=1))
        self.assertEqual(report["collected"], 50000)
        self.assertEqual(report["payment_methods"][0]["percent"], 100)
