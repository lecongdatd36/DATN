import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import httpx
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.orders import services, zalopay, zalopay_services
from apps.orders.models import Invoice, OnlinePayment, Order, Payment, ZaloPayTransaction
from apps.reservations.models import DepositPayment
from apps.reservations.tests import test_reservations as reservation_fixtures
from . import test_integrated_flow as order_fixtures


SANDBOX = {"ZALOPAY_APP_ID": "9876", "ZALOPAY_KEY1": "test-only-key-one", "ZALOPAY_KEY2": "test-only-key-two",
    "ZALOPAY_ENDPOINT": "https://sb-openapi.zalopay.vn/v2/create"}


def response(data):
    return httpx.Response(200, json=data, request=httpx.Request("POST", SANDBOX["ZALOPAY_ENDPOINT"]))


def receipt(row, **changes):
    data = {"app_id": row.app_id, "app_trans_id": row.app_trans_id, "amount": int(row.amount),
        "zp_trans_id": 261110000000000 + row.pk, "embed_data": row.request_data["embed_data"], **changes}
    raw = json.dumps(data, separators=(",", ":"))
    return {"type": 1, "data": raw, "mac": hmac.new(SANDBOX["ZALOPAY_KEY2"].encode(), raw.encode(), hashlib.sha256).hexdigest()}


class FakeGatewayMixin:
    def setUp(self):
        super().setUp()
        mocker = patch("apps.orders.zalopay.httpx.post")
        self.gateway = mocker.start()
        self.addCleanup(mocker.stop)
        self.gateway.return_value = response({"return_code": 1, "order_url": "https://qcgateway.zalopay.vn/pay?order=test"})


@override_settings(**SANDBOX)
class ZaloPayOrderTests(FakeGatewayMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        order_fixtures.IntegratedRestaurantFlowTests.setUpTestData.__func__(cls)

    revision = order_fixtures.IntegratedRestaurantFlowTests.revision
    ready_order_for_payment = order_fixtures.IntegratedRestaurantFlowTests.ready_order_for_payment

    def create(self, order=None):
        self.order = order or self.ready_order_for_payment()
        return zalopay_services.create_order_payment(actor=self.users["CASHIER"], order_id=self.order.pk,
            base_url="https://merchant.example")

    def test_create_persists_pending_before_network_and_uses_official_mac(self):
        self.order = self.ready_order_for_payment()
        def network(url, **kwargs):
            row = ZaloPayTransaction.objects.get()
            self.assertEqual(row.status, "PENDING")
            self.assertFalse(Invoice.objects.exists())
            payload = kwargs["data"]
            value = "|".join(str(payload[key]) for key in
                ("app_id", "app_trans_id", "app_user", "amount", "app_time", "embed_data", "item"))
            expected = hmac.new(SANDBOX["ZALOPAY_KEY1"].encode(), value.encode(), hashlib.sha256).hexdigest()
            self.assertEqual(payload["mac"], expected)
            self.assertEqual(payload["amount"], 95000)
            self.assertEqual(url, SANDBOX["ZALOPAY_ENDPOINT"])
            self.assertFalse(kwargs["follow_redirects"])
            self.assertNotIn("mac", row.request_data)
            return response({"return_code": 1, "order_url": "https://qcgateway.zalopay.vn/pay?order=test"})
        self.gateway.side_effect = network
        row = self.create(self.order)
        self.assertEqual(row.status, "PENDING")
        self.assertRegex(row.app_trans_id, r"^\d{6}_[0-9a-f]{32}$")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "PAYMENT_REQUESTED")

    def test_id_uses_vietnam_date_even_with_utc_host(self):
        with patch("apps.orders.zalopay.timezone.now", return_value=datetime(2026, 11, 10, 18, tzinfo=dt_timezone.utc)), override_settings(TIME_ZONE="UTC"):
            first, second = zalopay.transaction_id(), zalopay.transaction_id()
        self.assertTrue(first.startswith("261111_"))
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), 40)

    def test_success_and_duplicate_callback_finalize_exactly_once(self):
        row = self.create()
        payload = receipt(row)
        callback = reverse("zalopay:callback")
        client = Client(enforce_csrf_checks=True)
        for _ in range(2):
            self.assertEqual(client.post(callback, payload, content_type="application/json").json()["return_code"], 1)
        row.refresh_from_db()
        self.order.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(row.status, "PAID")
        self.assertEqual(self.order.status, "COMPLETED")
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(Payment.objects.get().method, "ZALOPAY")
        self.assertEqual(Payment.objects.get().amount, 95000)
        self.assertEqual(self.customer.total_spending, 95000)

    def test_bad_signature_or_tampered_identity_never_pays(self):
        row = self.create()
        bad = receipt(row)
        bad["mac"] = "0" * 64
        self.assertEqual(zalopay_services.process_callback(bad)["return_code"], -1)
        for changes in ({"amount": 1}, {"amount": "NaN"}, {"app_id": 1}, {"app_trans_id": "unknown"},
                {"embed_data": '{"target":"order","target_id":999999}'}, {"zp_trans_id": 0}):
            with self.subTest(changes=changes):
                self.assertEqual(zalopay_services.process_callback(receipt(row, **changes))["return_code"], 2)
        row.refresh_from_db()
        self.assertEqual(row.status, "PENDING")
        self.assertFalse(Invoice.objects.exists())

    def test_redirect_cannot_mark_paid_or_query_gateway(self):
        row = self.create()
        self.gateway.reset_mock()
        result = self.client.get(reverse("zalopay:result", args=[row.token]), {"status": 1, "amount": int(row.amount), "checksum": "fake"})
        self.assertContains(result, "Chờ kết quả")
        self.gateway.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.status, "PENDING")
        self.assertFalse(Invoice.objects.exists())

    def test_missing_callback_query_success_checks_amount_and_uses_key1(self):
        row = self.create()
        self.gateway.return_value = response({"return_code": 1, "amount": int(row.amount), "zp_trans_id": 261110000000999})
        result = zalopay_services.query_transaction(row.token)
        self.assertEqual(result.status, "PAID")
        url, kwargs = self.gateway.call_args.args[0], self.gateway.call_args.kwargs
        self.assertEqual(url, "https://sb-openapi.zalopay.vn/v2/query")
        value = f"9876|{row.app_trans_id}|{SANDBOX['ZALOPAY_KEY1']}"
        self.assertEqual(kwargs["data"]["mac"], hmac.new(SANDBOX["ZALOPAY_KEY1"].encode(), value.encode(), hashlib.sha256).hexdigest())
        duplicate = receipt(row, zp_trans_id=261110000000999)
        self.assertEqual(zalopay_services.process_callback(duplicate)["return_code"], 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_query_wrong_amount_does_not_pay(self):
        row = self.create()
        self.gateway.return_value = response({"return_code": 1, "amount": 1, "zp_trans_id": 123})
        with self.assertRaises(ValidationError):
            zalopay_services.query_transaction(row.token)
        self.assertFalse(Invoice.objects.exists())
        row.refresh_from_db()
        self.assertEqual(row.status, "PENDING")

    def test_unpaid_query_stays_pending_and_is_rate_limited(self):
        row = self.create()
        self.gateway.reset_mock()
        self.gateway.return_value = response({"return_code": 3, "is_processing": True})
        for _ in range(2):
            self.assertEqual(zalopay_services.query_transaction(row.token).status, "PENDING")
        self.assertEqual(self.gateway.call_count, 1)
        self.assertFalse(Invoice.objects.exists())

    def test_definitive_failure_does_not_close_order(self):
        row = self.create()
        self.gateway.return_value = response({"return_code": 2, "is_processing": False})
        self.assertEqual(zalopay_services.query_transaction(row.token).status, "FAILED")
        row.order_payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(row.order_payment.status, "FAILED")
        self.assertEqual(self.order.status, "PAYMENT_REQUESTED")
        self.assertFalse(Invoice.objects.exists())

    def test_create_rejected_is_saved_as_failed(self):
        self.gateway.return_value = response({"return_code": 2})
        row = self.create()
        self.assertEqual(row.status, "FAILED")
        self.assertEqual(row.order_payment.status, "FAILED")
        self.assertFalse(Invoice.objects.exists())

    def test_timeout_reuses_pending_and_blocks_double_collection(self):
        self.gateway.side_effect = httpx.ReadTimeout("do not expose request body")
        row = self.create()
        again = self.create(self.order)
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(self.gateway.call_count, 1)
        self.assertEqual(ZaloPayTransaction.objects.count(), 1)
        self.assertEqual(row.status, "PENDING")
        for method in ("CASH", "BANK_TRANSFER"):
            with self.assertRaises(ValidationError):
                services.process_payment(actor=self.users["CASHIER"], order_id=self.order.pk, payment_method=method)
        with self.assertRaises(ValidationError):
            services.create_vnpay_payment(actor=self.users["CASHIER"], order_id=self.order.pk, return_url="https://merchant.example", ip_address="127.0.0.1")

    def test_stale_order_receipt_is_reconciled_without_overwriting_order(self):
        row = self.create()
        Order.objects.filter(pk=self.order.pk).update(revision=row.order_revision+1)
        self.assertEqual(zalopay_services.process_callback(receipt(row))["return_code"], 1)
        row.refresh_from_db()
        self.assertEqual(row.status, "REVIEW")
        self.assertFalse(Invoice.objects.exists())

    def test_api_requires_payment_permission_and_ignores_client_amount(self):
        order = self.ready_order_for_payment()
        url = reverse("zalopay:create")
        self.assertEqual(self.client.post(url, {"order_id": order.pk}).status_code, 302)
        self.client.force_login(self.users["WAITER"])
        self.assertEqual(self.client.post(url, {"order_id": order.pk}).status_code, 403)
        self.client.force_login(self.users["CASHIER"])
        result = self.client.post(url, {"order_id": order.pk, "amount": 1}, content_type="application/json")
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["amount"], "95000")
        self.assertTrue(result.json()["sandbox"])

    def test_production_endpoint_is_rejected_before_network_or_db_write(self):
        order = self.ready_order_for_payment()
        with override_settings(ZALOPAY_ENDPOINT="https://openapi.zalopay.vn/v2/create"), self.assertRaises(ImproperlyConfigured):
            self.create(order)
        self.gateway.assert_not_called()
        self.assertFalse(ZaloPayTransaction.objects.exists())

    def test_missing_keys_and_external_checkout_url_are_not_used(self):
        with override_settings(ZALOPAY_KEY1=""):
            self.assertFalse(zalopay.enabled())
        self.gateway.return_value = response({"return_code": 1, "order_url": "https://gateway.zalopay.vn/pay"})
        row = self.create()
        self.assertEqual(row.order_url, "")
        self.assertEqual(row.status, "PENDING")

    def test_public_state_and_query_use_capability_and_query_requires_csrf(self):
        row = self.create()
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(reverse("zalopay:state", args=[row.token])).json()["status"], "PENDING")
        self.assertEqual(client.post(reverse("zalopay:query", args=[row.token])).status_code, 403)
        client.get(reverse("zalopay:result", args=[row.token]))
        self.gateway.return_value = response({"return_code": 3, "is_processing": True})
        result = client.post(reverse("zalopay:query", args=[row.token]), HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "PENDING")

    def test_pos_selection_redirects_to_sandbox_without_settling(self):
        order = self.ready_order_for_payment()
        self.client.force_login(self.users["CASHIER"])
        response_view = self.client.get(reverse("sales:workspace"), {"order": order.pk})
        self.assertContains(response_view, 'value="ZALOPAY"')
        result = self.client.post(reverse("sales:payment"), {"order_id": order.pk, "payment_method": "ZALOPAY"})
        self.assertEqual(result.status_code, 302)
        self.assertTrue(result.url.startswith("https://qcgateway.zalopay.vn/"))
        self.assertFalse(Invoice.objects.exists())

    @override_settings(PUBLIC_BASE_URL="http://192.168.1.14:8000", ALLOWED_HOSTS=["localhost"],
        ZALOPAY_CALLBACK_URL="https://sandbox-merchant.example/payments/zalopay/callback/")
    def test_browser_return_uses_current_origin_and_callback_can_be_public(self):
        order = self.ready_order_for_payment()
        self.client.force_login(self.users["CASHIER"])
        result = self.client.post(reverse("zalopay:create"), {"order_id": order.pk}, HTTP_HOST="localhost:8000")
        self.assertEqual(result.status_code, 201)
        row = ZaloPayTransaction.objects.get()
        embedded = json.loads(row.request_data["embed_data"])
        self.assertEqual(embedded["redirecturl"], "http://localhost:8000"+reverse("zalopay:result", args=[row.token]))
        self.assertEqual(row.request_data["callback_url"], "https://sandbox-merchant.example/payments/zalopay/callback/")
        self.assertNotIn("192.168.1.14", json.dumps(row.request_data))

    @override_settings(PUBLIC_BASE_URL="http://192.168.1.14:8000", ALLOWED_HOSTS=["localhost"], ZALOPAY_CALLBACK_URL="")
    def test_default_callback_also_uses_reachable_request_origin(self):
        from django.test import RequestFactory
        from apps.orders.zalopay_views import base_url, callback_url
        request = RequestFactory().get("/sales/", HTTP_HOST="localhost:8000")
        self.assertEqual(base_url(request), "http://localhost:8000")
        self.assertEqual(callback_url(request), "http://localhost:8000/payments/zalopay/callback/")


@override_settings(**SANDBOX)
class ZaloPayDepositTests(FakeGatewayMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        reservation_fixtures.ReservationTests.setUpTestData.__func__(cls)

    at = reservation_fixtures.ReservationTests.at
    create_row = reservation_fixtures.ReservationTests.create_row

    def create(self):
        with self.at(self.now):
            self.reservation = self.create_row()
            return zalopay_services.create_deposit_payment(token=self.reservation.access_token,
                revision=self.reservation.revision, base_url="https://merchant.example")

    def test_deposit_callback_is_idempotent_and_never_opens_order(self):
        with self.at(self.now):
            row = self.create()
            for _ in range(2):
                self.assertEqual(zalopay_services.process_callback(receipt(row))["return_code"], 1)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, "CONFIRMED")
        self.assertEqual(self.reservation.received, 100000)
        self.assertEqual(DepositPayment.objects.count(), 1)
        self.assertFalse(Order.objects.exists())

    def test_late_deposit_is_recorded_for_refund_without_confirming_table(self):
        row = self.create()
        with self.at(self.now+timedelta(minutes=11)):
            self.assertEqual(zalopay_services.process_callback(receipt(row))["return_code"], 1)
            self.assertEqual(zalopay_services.process_callback(receipt(row))["return_code"], 1)
        row.refresh_from_db()
        self.reservation.refresh_from_db()
        self.assertEqual(row.status, "REVIEW")
        self.assertEqual(self.reservation.status, "EXPIRED")
        self.assertEqual(self.reservation.refunds.count(), 1)
        self.assertFalse(Order.objects.exists())

    def test_deposit_create_requires_current_revision_and_consent(self):
        with self.at(self.now):
            reservation = self.create_row()
            url = reverse("zalopay:deposit_create", args=[reservation.access_token])
            result = self.client.post(url, {"revision": reservation.revision}, content_type="application/json")
            self.assertEqual(result.status_code, 400)
            self.assertFalse(ZaloPayTransaction.objects.exists())
            result = self.client.post(url, {"revision": reservation.revision, "agree": "yes"}, content_type="application/json")
            self.assertEqual(result.status_code, 201)
            again = self.client.post(url, {"revision": reservation.revision, "agree": "yes"}, content_type="application/json")
            self.assertEqual(again.json()["app_trans_id"], result.json()["app_trans_id"])
            self.assertEqual(self.gateway.call_count, 1)

    def test_deposit_wrong_amount_never_confirms(self):
        row = self.create()
        with self.at(self.now):
            result = zalopay_services.process_callback(receipt(row, amount=1))
        self.assertEqual(result["return_code"], 2)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, "WAITING")
        self.assertEqual(self.reservation.received, 0)

    def test_short_hold_shows_specific_error_without_changing_reservation(self):
        with self.at(self.now):
            reservation = self.create_row()
        original_expiry = reservation.hold_expires_at
        url = reverse("zalopay:deposit_create", args=[reservation.access_token])
        with self.at(self.now+timedelta(minutes=6)):
            result = self.client.post(url, {"revision": reservation.revision, "agree": "yes"}, content_type="application/json")
            self.assertEqual(result.status_code, 400)
            self.assertIn("dưới 5 phút", result.json()["error"])
            detail = self.client.get(reverse("online_reservations:detail", args=[reservation.access_token]))
            self.assertContains(detail, "ZaloPay: không đủ thời gian thanh toán")
            self.assertFalse(detail.context["zalopay_can_create"])
            self.client.post(url, {"revision": reservation.revision, "agree": "yes"})
            detail = self.client.get(reverse("online_reservations:detail", args=[reservation.access_token]))
            self.assertContains(detail, "Thời gian giữ chỗ còn dưới 5 phút")
        self.gateway.assert_not_called()
        self.assertFalse(DepositPayment.objects.exists())
        self.assertFalse(ZaloPayTransaction.objects.exists())
        reservation.refresh_from_db()
        self.assertEqual(reservation.hold_expires_at, original_expiry)
        self.assertEqual(reservation.status, "WAITING")
        self.assertEqual(reservation.revision, 1)

    def test_existing_pending_checkout_can_resume_with_less_than_five_minutes(self):
        row = self.create()
        with self.at(self.now+timedelta(minutes=6)):
            detail = self.client.get(reverse("online_reservations:detail", args=[self.reservation.access_token]))
            self.assertContains(detail, "Tiếp tục giao dịch ZaloPay")
            self.assertNotContains(detail, "ZaloPay: không đủ thời gian thanh toán")
            again = zalopay_services.create_deposit_payment(token=self.reservation.access_token,
                revision=self.reservation.revision, base_url="https://merchant.example")
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(self.gateway.call_count, 1)
        self.assertEqual(ZaloPayTransaction.objects.count(), 1)

    def test_final_invoice_only_charges_remainder_after_zalopay_deposit(self):
        from apps.reservations import services as reservations
        row = self.create()
        with self.at(self.now):
            zalopay_services.process_callback(receipt(row))
        self.reservation.refresh_from_db()
        with self.at(self.arrival):
            order = reservations.receive(actor=self.manager, reservation_id=self.reservation.pk, revision=self.reservation.revision)
            order.items.update(status="SERVED")
            services.prepare_quick_payment(actor=self.manager, order_id=order.pk)
            payment = zalopay_services.create_order_payment(actor=self.manager, order_id=order.pk, base_url="https://merchant.example")
            self.assertEqual(payment.amount, 300000)
            self.assertEqual(zalopay_services.process_callback(receipt(payment))["return_code"], 1)
        invoice = Invoice.objects.get(order=order)
        self.assertEqual(invoice.total, 400000)
        self.assertEqual(invoice.payments.get(method="DEPOSIT").amount, 100000)
        self.assertEqual(invoice.payments.get(method="ZALOPAY").amount, 300000)


@override_settings(**SANDBOX)
class ZaloPayConcurrencyTests(FakeGatewayMixin, TransactionTestCase):
    serialized_rollback = True
    revision = order_fixtures.IntegratedRestaurantFlowTests.revision
    ready_order_for_payment = order_fixtures.IntegratedRestaurantFlowTests.ready_order_for_payment

    def setUp(self):
        super().setUp()
        order_fixtures.IntegratedRestaurantFlowTests.setUpTestData.__func__(type(self))
        self.order = self.ready_order_for_payment()

    def race(self, action):
        barrier = Barrier(2)
        def work(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return action(index)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(work, index) for index in range(2)]
            return [future.result(timeout=25) for future in futures]

    def create(self):
        return zalopay_services.create_order_payment(actor=self.users["CASHIER"], order_id=self.order.pk, base_url="https://merchant.example")

    def test_concurrent_create_sends_only_one_gateway_request(self):
        result = self.race(lambda _: self.create().pk)
        self.assertEqual(result[0], result[1])
        self.assertEqual(self.gateway.call_count, 1)
        self.assertEqual(ZaloPayTransaction.objects.count(), 1)
        self.assertEqual(OnlinePayment.objects.count(), 1)

    def test_concurrent_callbacks_create_exactly_one_receipt(self):
        row = self.create()
        payload = receipt(row)
        self.assertEqual(self.race(lambda _: zalopay_services.process_callback(payload)["return_code"]), [1, 1])
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_spending, 95000)

    def test_query_and_callback_race_settle_once(self):
        row = self.create()
        payload = receipt(row)
        provider_id = json.loads(payload["data"])["zp_trans_id"]
        self.gateway.return_value = response({"return_code": 1, "amount": int(row.amount), "zp_trans_id": provider_id})
        result = self.race(lambda index: zalopay_services.process_callback(payload)["return_code"] if index == 0
            else zalopay_services.query_transaction(row.token).status)
        self.assertEqual(result, [1, "PAID"])
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
