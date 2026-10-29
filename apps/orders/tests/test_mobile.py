from datetime import timedelta
from decimal import Decimal
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.customers.models import Customer, MembershipTier
from apps.menu.models import Category, Dish, Unit
from apps.seating.models import Area, DiningTable
from apps.orders import services
from apps.orders.models import Invoice, OnlinePayment, Order, OrderItem, Payment, PromotionCode, QRCheckInRequest


class MobileStaffTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("WAITER", "CASHIER", "KITCHEN", "MANAGER"):
            user = get_user_model().objects.create_user(username="mobile_" + role.lower(), password="Mobile-test-Only!123")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.area = Area.objects.create(name="Tầng 1 mobile")
        cls.table = DiningTable.objects.create(area=cls.area, code="B01", name="Bàn 01", capacity=4)
        cls.other = DiningTable.objects.create(area=cls.area, code="B02", name="Bàn 02", capacity=4)
        cls.category = Category.objects.create(name="Món chính mobile")
        cls.unit = Unit.objects.create(name="Phần mobile")
        cls.dish = Dish.objects.create(category=cls.category, unit=cls.unit, code="MB01", name="Phở bò tái", price=Decimal("50000"))
        cls.tier = MembershipTier.objects.create(name="Mobile Vàng", minimum_spending=0, discount_percent=5)
        cls.customer = Customer.objects.create(full_name="Khách kiểm thử mobile", phone="0901234567", membership_tier=cls.tier)

    def setUp(self):
        self.client.force_login(self.users["WAITER"])

    def test_prepared_item_cancel_is_hidden_and_denied_for_waiter_and_cashier(self):
        order = self.ready_to_pay()
        item = order.items.get()
        for status in (OrderItem.Status.COOKING, OrderItem.Status.READY, OrderItem.Status.SERVED):
            OrderItem.objects.filter(pk=item.pk).update(status=status)
            for role in ("WAITER", "CASHIER"):
                with self.subTest(status=status, role=role):
                    self.client.force_login(self.users[role])
                    response = self.get_page("order", order=order.pk)
                    self.assertNotContains(response, 'class="m-cancel"')
                    response = self.action("cancel-item", order, item_id=item.pk, reason="Thử hủy món đã làm")
                    self.assertEqual(response.status_code, 403)
                    item.refresh_from_db()
                    self.assertEqual(item.status, status)
        self.client.force_login(self.users["MANAGER"])
        response = self.get_page("order", order=order.pk)
        self.assertContains(response, "Hủy món đã làm (quản lý)")
        self.assertContains(response, "không hoàn nguyên liệu đã dùng")

    def test_cashier_queue_requires_collection_permission_and_checks_served_items(self):
        order = self.ready_to_pay()
        self.assertEqual(self.get_page("payments").status_code, 403)
        self.client.force_login(self.users["CASHIER"])
        response = self.get_page("payments")
        self.assertEqual(response.status_code, 200)
        check = next(check for check in response.context["mobile_checks"] if check.pk == order.pk)
        self.assertTrue(check.mobile_can_pay)
        self.assertEqual(check.mobile_due, Decimal("95000"))
        self.assertContains(response, f"page=checkout&amp;order={order.pk}")
        OrderItem.objects.filter(order=order).update(status=OrderItem.Status.READY)
        response = self.get_page("payments")
        check = next(check for check in response.context["mobile_checks"] if check.pk == order.pk)
        self.assertFalse(check.mobile_can_pay)
        self.assertContains(response, "Món chưa phục vụ")
        self.assertNotContains(response, f"page=checkout&amp;order={order.pk}")

    def get_page(self, page="tables", **params):
        return self.client.get(reverse("sales:mobile"), {"page": page, **params})

    def action(self, action, order=None, **data):
        if order:
            order.refresh_from_db()
            data = {"order_id": order.pk, "expected_revision": order.revision, **data}
        return self.client.post(reverse("sales:mobile_action", args=[action]), data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def opened(self, table=None):
        return services.open_table(actor=self.users["WAITER"], table_id=(table or self.table).pk, guest_count=2,
                                   customer_id=self.customer.pk, note="Có trẻ em · Ưu tiên yên tĩnh")

    def ready_to_pay(self):
        order = self.opened()
        item = services.add_item(actor=self.users["WAITER"], order_id=order.pk, expected_revision=order.revision, dish_id=self.dish.pk, quantity=2, note="Không hành")
        order.refresh_from_db()
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=order.revision)
        for status, role in (("COOKING", "KITCHEN"), ("READY", "KITCHEN"), ("SERVED", "WAITER")):
            order.refresh_from_db()
            services.transition_item(actor=self.users[role], order_id=order.pk, item_id=item.pk, expected_revision=order.revision, target=status)
        order.refresh_from_db()
        return order

    def pay_data(self, **overrides):
        return {"payment_method": "CASH", "cash_received": "100000", "reviewed_total": "95000", "promotion_code": "", **overrides}

    def test_login_mobile_flag_only_changes_staff_destination(self):
        self.client.logout()
        for role in ("WAITER", "CASHIER"):
            response = self.client.post(reverse("accounts:login"), {"username": self.users[role].username, "password": "Mobile-test-Only!123", "mobile_view": "1"})
            self.assertRedirects(response, reverse("sales:mobile"), fetch_redirect_response=False)
            self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username": self.users["WAITER"].username, "password": "Mobile-test-Only!123"})
        self.assertRedirects(response, reverse("sales:workspace"), fetch_redirect_response=False)

    def test_workspace_permission_and_customer_form(self):
        self.assertContains(self.get_page(), "Sơ đồ bàn")
        response = self.get_page("open", table=self.table.pk)
        self.assertContains(response, 'name="customer_phone"')
        self.assertNotContains(response, "Khách cũ")
        self.assertNotContains(response, "Khách mới")
        for page in ("checkout", "split", "invoices", "receipt"):
            self.assertEqual(self.get_page(page).status_code, 403)
        self.client.force_login(self.users["KITCHEN"])
        self.assertEqual(self.get_page().status_code, 403)

    def test_anonymous_customer_and_known_phone(self):
        response = self.action("open", table_id=self.table.pk, guest_count=2)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Order.objects.get(table=self.table).customer_id)
        response = self.action("open", table_id=self.other.pk, guest_count=2, customer_phone="+84 90 123 45 67", customer_name="Không ghi đè")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(table=self.other)
        self.assertEqual(order.customer_id, self.customer.pk)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, "Khách kiểm thử mobile")

    def test_failed_open_rolls_back_new_customer(self):
        self.opened()
        response = self.action("open", table_id=self.table.pk, guest_count=2, customer_phone="0987654321", customer_name="Không tạo hồ sơ mồ côi")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Customer.objects.filter(phone="0987654321").exists())

    def test_cashier_can_open_add_send_and_view_same_order(self):
        self.client.force_login(self.users["CASHIER"])
        self.assertEqual(self.action("open", table_id=self.table.pk, guest_count=2, customer_phone=self.customer.phone).status_code, 200)
        order = Order.objects.get(table=self.table)
        result = self.action("add", order, dish_id=self.dish.pk, quantity=1, note="Ít cay")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["draft_count"], 1)
        self.assertEqual(self.action("send", order).status_code, 200)
        self.assertEqual(order.items.get().status, OrderItem.Status.PENDING)
        self.assertContains(self.get_page("order", order=order.pk), self.customer.full_name)

    def test_stale_add_cannot_duplicate_items(self):
        order = self.opened()
        revision = order.revision
        self.assertEqual(self.action("add", order, dish_id=self.dish.pk, quantity=1).status_code, 200)
        response = self.action("add", order, expected_revision=revision, dish_id=self.dish.pk, quantity=1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(order.items.count(), 1)

    def test_waiter_can_request_but_cannot_collect(self):
        order = self.ready_to_pay()
        self.assertEqual(self.action("request-payment", order).status_code, 200)
        self.assertEqual(self.action("pay", order, **self.pay_data()).status_code, 403)
        self.assertFalse(Invoice.objects.exists())

    def test_cash_payment_and_replay(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        revision = order.revision
        response = self.action("pay", order, **self.pay_data())
        self.assertEqual(response.status_code, 200, response.content)
        invoice = Invoice.objects.get(order=order)
        self.assertEqual(invoice.total, Decimal("95000"))
        self.assertEqual(self.client.session["mobile_tender"]["change"], "5000")
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.CLEANING)
        replay = self.action("pay", order, expected_revision=revision, **self.pay_data())
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(Payment.objects.count(), 1)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_spending, Decimal("95000"))
        self.assertContains(self.get_page("receipt", invoice=invoice.pk), invoice.invoice_code)

    def test_payment_validates_method_received_cash_and_reviewed_total(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        cases = [self.pay_data(payment_method="VNPAY"), self.pay_data(cash_received="90000"), self.pay_data(cash_received="NaN"), self.pay_data(reviewed_total="1"), self.pay_data(payment_method="BANK_TRANSFER")]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.action("pay", order, **data).status_code, 409)
                self.assertFalse(Invoice.objects.exists())
                order.refresh_from_db()
                self.assertNotEqual(order.status, Order.Status.PAYMENT_REQUESTED)

    def test_transfer_requires_received_confirmation(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        data = self.pay_data(payment_method="BANK_TRANSFER", received_transfer="yes", transaction_code="BANK-MOBILE-TEST")
        self.assertEqual(self.action("pay", order, **data).status_code, 200)
        self.assertEqual(Payment.objects.get().reference, "BANK-MOBILE-TEST")

    def test_unserved_order_cannot_be_paid(self):
        order = self.opened()
        services.add_item(actor=self.users["WAITER"], order_id=order.pk, expected_revision=order.revision, dish_id=self.dish.pk, quantity=2)
        self.client.force_login(self.users["CASHIER"])
        response = self.get_page("checkout", order=order.pk)
        self.assertNotContains(response, "data-payment-form")
        self.assertEqual(self.action("pay", order, **self.pay_data()).status_code, 409)
        self.assertFalse(Payment.objects.exists())
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PAYMENT_REQUESTED)
        self.assertEqual(self.action("pay", order, **self.pay_data()).status_code, 409)
        self.assertFalse(Payment.objects.exists())

    def test_quote_and_payment_recheck_discount(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        now = timezone.now()
        PromotionCode.objects.create(code="MOBILE10", name="Mobile 10", discount_type="PERCENT", value=10, minimum_order=0, starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1))
        quote = self.client.get(reverse("sales:mobile_quote"), {"order": order.pk, "promotion": "MOBILE10"}).json()
        self.assertEqual(Decimal(quote["due"]), Decimal("85500"))
        self.assertEqual(self.action("pay", order, **self.pay_data(promotion_code="MOBILE10", reviewed_total="95000")).status_code, 409)
        self.assertEqual(self.action("pay", order, **self.pay_data(promotion_code="MOBILE10", reviewed_total=quote["due"])).status_code, 200)

    def test_membership_change_invalidates_reviewed_amount(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        self.tier.discount_percent = 10
        self.tier.save()
        self.assertEqual(self.action("pay", order, **self.pay_data()).status_code, 409)
        self.assertFalse(Payment.objects.exists())

    def test_existing_online_transaction_blocks_mobile_collection(self):
        order = self.ready_to_pay()
        OnlinePayment.objects.create(order=order, txn_ref="mobile-block-test", amount=95000, subtotal=100000)
        self.client.force_login(self.users["CASHIER"])
        self.assertNotContains(self.get_page("checkout", order=order.pk), "data-payment-form")
        self.assertEqual(self.action("pay", order, **self.pay_data()).status_code, 409)
        self.assertFalse(Payment.objects.exists())

    def test_split_and_pay_last_check_only_closes_table(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        self.assertEqual(self.action("prepare-split", order).status_code, 200)
        item = order.items.get()
        self.assertEqual(self.action("split", order, **{f"quantity_{item.pk}": 1}).status_code, 200)
        child = Order.objects.get(split_root=order)
        data = self.pay_data(reviewed_total="47500", cash_received="50000")
        self.assertEqual(self.action("pay", child, **data).status_code, 200)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.OCCUPIED)
        self.assertEqual(self.action("pay", order, **data).status_code, 200)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.CLEANING)

    def test_booking_seating_preserves_customer_and_note(self):
        booking = Booking.objects.create(customer=self.customer, customer_name="Tên khi đặt", customer_phone=self.customer.phone, table=self.table, party_size=3, starts_at=timezone.now()+timedelta(minutes=10), ends_at=timezone.now()+timedelta(hours=2), status=Booking.Status.CONFIRMED)
        result = self.action("booking-seat", booking_id=booking.pk, expected_revision=booking.revision, expected_status=booking.status, verified="yes", note="Đối chiếu: có trẻ em")
        self.assertEqual(result.status_code, 200, result.content)
        order = Order.objects.get(booking=booking)
        self.assertEqual(order.customer_id, self.customer.pk)
        self.assertEqual(order.note, "Đối chiếu: có trẻ em")
        self.assertEqual(order.guest_count, 3)

    def test_qr_with_customer_is_one_atomic_receiving_flow(self):
        checkin = QRCheckInRequest.objects.create(table=self.table, guest_count=2)
        opening = self.get_page("open", table=self.table.pk, checkin=checkin.pk)
        self.assertEqual(opening.context["opening_guests"], 2)
        result = self.action("open", table_id=self.table.pk, guest_count=2, checkin_id=checkin.pk, customer_phone=self.customer.phone)
        self.assertEqual(result.status_code, 200, result.content)
        checkin.refresh_from_db()
        self.assertEqual(checkin.status, QRCheckInRequest.Status.CONFIRMED)
        self.assertEqual(checkin.order.customer_id, self.customer.pk)
        self.assertEqual(Order.objects.filter(table=self.table).count(), 1)

    def test_expired_qr_rolls_back_table_and_customer(self):
        checkin = QRCheckInRequest.objects.create(table=self.table, guest_count=2, expires_at=timezone.now()-timedelta(minutes=1))
        result = self.action("open", table_id=self.table.pk, guest_count=2, checkin_id=checkin.pk, customer_phone="0987654321", customer_name="Khách QR hết hạn")
        self.assertEqual(result.status_code, 409)
        self.assertFalse(Order.objects.filter(table=self.table).exists())
        self.assertFalse(Customer.objects.filter(phone="0987654321").exists())

    def test_csrf_and_bad_identifiers(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.users["WAITER"])
        self.assertEqual(csrf_client.post(reverse("sales:mobile_action", args=["open"]), {"table_id": self.table.pk, "guest_count": 1}).status_code, 403)
        self.assertEqual(self.get_page("order", order="bad").status_code, 404)

    def test_mobile_pages_render_and_optional_visual_capture(self):
        order = self.ready_to_pay()
        self.client.force_login(self.users["CASHIER"])
        captures = {"tables": {}, "open": {"table": self.other.pk}, "menu": {"order": order.pk}, "order": {"order": order.pk}, "checkout": {"order": order.pk}, "tasks": {}, "invoices": {}, "personal": {}}
        directory = os.environ.get("MOBILE_CAPTURE_DIR")
        for page, params in captures.items():
            response = self.get_page(page, **params)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertContains(response, 'id="mobile-page"')
            if page == "checkout":
                self.assertNotContains(response, 'value="VNPAY"')
                self.assertContains(response, "data-payment-form")
            if directory:
                folder = Path(directory).resolve()
                self.assertTrue(folder.is_relative_to(Path(settings.BASE_DIR).resolve()))
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{page}.html").write_bytes(response.content)
