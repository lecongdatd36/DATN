from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer, MembershipTier
from apps.employees.models import EmployeeProfile, JobPosition
from apps.menu.models import Category, Dish, Unit
from apps.seating.models import Area, DiningTable
from apps.orders.models import Invoice, OnlinePayment, Order, OrderItem, Payment, PaymentRequest, PromotionCode
from apps.orders import services
from apps.orders.vnpay import sign


class IntegratedRestaurantFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.users = {}
        for role in ("MANAGER", "WAITER", "KITCHEN", "CASHIER"):
            user = user_model.objects.create_user(username=f"flow_{role.lower()}", password="StrongPass123!")
            user.groups.add(Group.objects.get(name=role))
            position = JobPosition.objects.get(code=role)
            EmployeeProfile.objects.create(
                user=user, employee_code=f"F{role[:2]}", full_name=role, phone=f"09000000{len(cls.users):02d}",
                job_position=position, join_date="2026-01-01",
            )
            cls.users[role] = user
        cls.area = Area.objects.create(name="Tầng tích hợp")
        cls.table = DiningTable.objects.create(code="IT01", name="Bàn tích hợp", area=cls.area, capacity=4)
        cls.category = Category.objects.create(name="Món chính tích hợp")
        cls.unit = Unit.objects.create(name="Phần tích hợp")
        cls.dish = Dish.objects.create(code="ITD01", name="Cơm gà", category=cls.category, unit=cls.unit, price=Decimal("50000"))
        cls.tier, _ = MembershipTier.objects.update_or_create(
            name="Vàng", defaults={"minimum_spending": 0, "discount_percent": Decimal("5"), "is_active": True}
        )
        cls.customer = Customer.objects.create(full_name="Nguyễn Văn A", phone="0912345678", membership_tier=cls.tier)

    def revision(self, order):
        order.refresh_from_db()
        return order.revision

    def ready_order_for_payment(self, request_payment=True):
        order = services.open_table(
            actor=self.users["WAITER"], table_id=self.table.pk, guest_count=2, customer_id=self.customer.pk
        )
        item = services.add_item(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order),
            dish_id=self.dish.pk, quantity=2,
        )
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        for target, actor in (
            (OrderItem.Status.COOKING, self.users["KITCHEN"]),
            (OrderItem.Status.READY, self.users["KITCHEN"]),
            (OrderItem.Status.SERVED, self.users["WAITER"]),
        ):
            services.transition_item(
                actor=actor, order_id=order.pk, item_id=item.pk,
                expected_revision=self.revision(order), target=target,
            )
        if request_payment:
            services.request_payment(
                actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order)
            )
        return order

    def active_promotion(self, code="GIAM10"):
        now = timezone.now()
        return PromotionCode.objects.create(
            code=code,
            name="Giảm 10 phần trăm",
            discount_type=PromotionCode.DiscountType.PERCENT,
            value=Decimal("10"),
            minimum_order=Decimal("50000"),
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )

    def test_complete_pos_kitchen_payment_cleaning_flow(self):
        order = services.open_table(actor=self.users["WAITER"], table_id=self.table.pk, guest_count=2, customer_id=self.customer.pk)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.OCCUPIED)
        item = services.add_item(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order), dish_id=self.dish.pk, quantity=2, note="Không hành")
        self.dish.price = Decimal("60000")
        self.dish.save(update_fields=("price",))
        self.assertEqual(item.unit_price, Decimal("50000"))
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        item.refresh_from_db()
        self.assertEqual(item.status, OrderItem.Status.PENDING)
        services.transition_item(actor=self.users["KITCHEN"], order_id=order.pk, item_id=item.pk, expected_revision=self.revision(order), target=OrderItem.Status.COOKING)
        services.transition_item(actor=self.users["KITCHEN"], order_id=order.pk, item_id=item.pk, expected_revision=self.revision(order), target=OrderItem.Status.READY)
        services.transition_item(actor=self.users["WAITER"], order_id=order.pk, item_id=item.pk, expected_revision=self.revision(order), target=OrderItem.Status.SERVED)
        request = services.request_payment(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        self.assertEqual(request.status, PaymentRequest.Status.WAITING)
        invoice = services.process_payment(actor=self.users["CASHIER"], order_id=order.pk, payment_method="CASH")
        order.refresh_from_db()
        self.table.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.subtotal, Decimal("100000"))
        self.assertEqual(invoice.discount_amount, Decimal("5000"))
        self.assertEqual(invoice.total_amount, Decimal("95000"))
        self.assertEqual(self.customer.total_spending, Decimal("95000"))
        self.assertEqual(self.table.status, DiningTable.Status.CLEANING)
        self.client.force_login(self.users["CASHIER"])
        self.assertContains(self.client.get(reverse("sales:invoice_print", args=[invoice.pk])), invoice.invoice_code)
        self.client.force_login(self.users["MANAGER"])
        history = self.client.get(self.customer.get_absolute_url())
        self.assertContains(history, invoice.invoice_code)
        self.assertContains(history, "95.000")
        services.finish_cleaning(actor=self.users["WAITER"], table_id=self.table.pk)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.AVAILABLE)

    def test_staff_workspaces_are_role_protected(self):
        self.client.force_login(self.users["WAITER"])
        self.assertEqual(self.client.get(reverse("sales:workspace")).status_code, 200)
        self.assertEqual(self.client.get(reverse("kitchen:workspace")).status_code, 403)
        self.client.force_login(self.users["KITCHEN"])
        self.assertEqual(self.client.get(reverse("kitchen:workspace")).status_code, 200)
        self.assertEqual(self.client.get(reverse("sales:workspace")).status_code, 403)

    def test_kitchen_ticket_prominently_shows_item_and_table_notes(self):
        order = services.open_table(
            actor=self.users["WAITER"], table_id=self.table.pk, guest_count=2,
            customer_id=self.customer.pk, note="Khách dị ứng đậu phộng",
        )
        services.add_item(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order),
            dish_id=self.dish.pk, quantity=1, note="Không hành\nÍt cay",
        )
        services.send_to_kitchen(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order)
        )
        self.client.force_login(self.users["KITCHEN"])
        response = self.client.get(reverse("kitchen:workspace"))
        self.assertContains(response, "GHI CHÚ MÓN")
        self.assertContains(response, "Không hành")
        self.assertContains(response, "Ít cay")
        self.assertContains(response, "GHI CHÚ BÀN")
        self.assertContains(response, "Khách dị ứng đậu phộng")

    def test_manager_operational_pages_render(self):
        self.client.force_login(self.users["MANAGER"])
        for route in (
            reverse("orders:invoice_list"),
            reverse("orders:activity_logs"),
            reverse("customers:membership_tier_list"),
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_changing_tier_rules_recalculates_existing_customers(self):
        self.client.force_login(self.users["MANAGER"])
        response = self.client.post(reverse("customers:membership_tier_update", args=[self.tier.pk]), {
            "name": self.tier.name,
            "minimum_spending": "200000",
            "discount_percent": "5",
            "is_active": "on",
        })
        self.assertRedirects(response, reverse("customers:membership_tier_list"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.membership_tier.name, "Đồng")

        self.customer.total_spending = Decimal("250000")
        self.customer.save(update_fields=("total_spending", "updated_at"))
        response = self.client.post(reverse("customers:membership_tier_update", args=[self.tier.pk]), {
            "name": self.tier.name,
            "minimum_spending": "200000",
            "discount_percent": "7.5",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.membership_tier_id, self.tier.pk)

    def test_promotion_stacks_after_membership_and_is_snapshotted(self):
        self.active_promotion()
        order = self.ready_order_for_payment()
        preview = services.apply_promotion(
            actor=self.users["CASHIER"], order_id=order.pk, promotion_code="giam10"
        )
        self.assertEqual(preview["membership_discount"], Decimal("5000"))
        self.assertEqual(preview["promotion_discount"], Decimal("9500"))
        self.assertEqual(preview["due"], Decimal("85500"))

        invoice = services.process_payment(
            actor=self.users["CASHIER"], order_id=order.pk, payment_method="CASH"
        )
        self.assertEqual(invoice.membership_discount_amount, Decimal("5000"))
        self.assertEqual(invoice.promotion_code, "GIAM10")
        self.assertEqual(invoice.promotion_discount_amount, Decimal("9500"))
        self.assertEqual(invoice.total_amount, Decimal("85500"))

    def test_table_page_has_quick_payment_and_can_settle_by_table(self):
        self.active_promotion()
        order = self.ready_order_for_payment(request_payment=False)
        self.client.force_login(self.users["CASHIER"])
        table_page = self.client.get(reverse("seating:table_list"))
        self.assertContains(table_page, f"Thanh toán nhanh bàn {self.table.code}")
        self.assertContains(table_page, self.customer.full_name)
        self.assertContains(table_page, self.tier.name)
        self.assertContains(table_page, "5,00%")
        self.assertContains(table_page, "5.000")
        self.assertContains(table_page, "95.000")

        response = self.client.post(reverse("sales:payment"), {
            "order_id": order.pk,
            "quick_payment": "1",
            "promotion_code": "GIAM10",
            "payment_method": "CASH",
            "next": reverse("seating:table_list"),
        })
        self.assertRedirects(response, reverse("seating:table_list"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.invoice.total_amount, Decimal("85500"))

    def test_split_check_by_item_quantity_and_close_table_only_after_all_checks_paid(self):
        order = self.ready_order_for_payment()
        item = order.items.get()

        child = services.split_order(
            actor=self.users["CASHIER"],
            order_id=order.pk,
            expected_revision=self.revision(order),
            quantities={item.pk: 1},
        )
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)
        self.assertEqual(child.split_root_id, order.pk)
        self.assertEqual(child.status, Order.Status.PAYMENT_REQUESTED)
        self.assertEqual(child.items.get().quantity, 1)
        self.assertEqual(order.total, Decimal("50000"))
        self.assertEqual(child.total, Decimal("50000"))
        self.assertTrue(PaymentRequest.objects.filter(order=child, status=PaymentRequest.Status.WAITING).exists())

        child_invoice = services.process_payment(
            actor=self.users["CASHIER"], order_id=child.pk, payment_method="CASH"
        )
        self.table.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(child_invoice.total_amount, Decimal("47500"))
        self.assertEqual(self.table.status, DiningTable.Status.OCCUPIED)
        self.assertEqual(order.status, Order.Status.PAYMENT_REQUESTED)

        root_invoice = services.process_payment(
            actor=self.users["CASHIER"], order_id=order.pk, payment_method="BANK_TRANSFER"
        )
        self.table.refresh_from_db()
        self.assertEqual(root_invoice.total_amount, Decimal("47500"))
        self.assertEqual(self.table.status, DiningTable.Status.CLEANING)

    def test_unpaid_split_check_can_merge_back_into_root(self):
        order = self.ready_order_for_payment()
        item = order.items.get()
        child = services.split_order(
            actor=self.users["CASHIER"], order_id=order.pk,
            expected_revision=self.revision(order), quantities={item.pk: 1},
        )

        target = services.merge_split_order(
            actor=self.users["CASHIER"], order_id=child.pk, expected_revision=child.revision,
        )
        target.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(target.pk, order.pk)
        self.assertEqual(target.total, Decimal("100000"))
        self.assertEqual(sum(target.items.values_list("quantity", flat=True)), 2)
        self.assertEqual(child.status, Order.Status.CANCELLED)
        self.assertFalse(child.items.exists())
        self.assertFalse(PaymentRequest.objects.filter(order=child, status=PaymentRequest.Status.WAITING).exists())

    def test_one_check_accepts_multiple_payment_methods_before_closing_table(self):
        order = self.ready_order_for_payment()
        first_invoice = services.record_payment(
            actor=self.users["CASHIER"], order_id=order.pk,
            expected_revision=self.revision(order), amount=Decimal("30000"), payment_method=Payment.Method.CASH,
        )
        order.refresh_from_db()
        self.table.refresh_from_db()
        self.assertEqual(first_invoice.status, Invoice.Status.UNPAID)
        self.assertEqual(first_invoice.total, Decimal("95000"))
        self.assertEqual(first_invoice.remaining, Decimal("65000"))
        self.assertEqual(order.status, Order.Status.PAYMENT_REQUESTED)
        self.assertEqual(self.table.status, DiningTable.Status.OCCUPIED)
        self.client.force_login(self.users["CASHIER"])
        workspace = self.client.get(reverse("sales:workspace"), {"order": order.pk})
        self.assertTrue(workspace.context["can_continue_partial_payment"])
        self.assertFalse(workspace.context["can_collect_payment"])
        self.assertContains(workspace, reverse("orders:payment", args=[order.pk]))
        with self.assertRaisesMessage(ValidationError, "thu một phần"):
            services.process_payment(actor=self.users["CASHIER"], order_id=order.pk, payment_method="CASH")
        with self.assertRaisesMessage(ValidationError, "phát sinh giao dịch"):
            services.split_order(
                actor=self.users["CASHIER"], order_id=order.pk,
                expected_revision=order.revision, quantities={order.items.get().pk: 1},
            )

        final_invoice = services.record_payment(
            actor=self.users["CASHIER"], order_id=order.pk,
            expected_revision=order.revision, amount=Decimal("65000"), payment_method=Payment.Method.CARD,
        )
        order.refresh_from_db()
        self.table.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(final_invoice.status, Invoice.Status.PAID)
        self.assertEqual(final_invoice.payments.count(), 2)
        self.assertEqual(set(final_invoice.payments.values_list("method", flat=True)), {Payment.Method.CASH, Payment.Method.CARD})
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(self.table.status, DiningTable.Status.CLEANING)
        self.assertEqual(self.customer.total_spending, Decimal("95000"))

    def test_cashier_can_open_and_submit_split_check_form(self):
        order = self.ready_order_for_payment()
        item = order.items.get()
        self.client.force_login(self.users["CASHIER"])
        page = self.client.get(reverse("orders:split_order", args=[order.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Tách hóa đơn")
        self.assertContains(page, item.dish_name)

        response = self.client.post(reverse("orders:split_order", args=[order.pk]), {
            "expected_revision": self.revision(order),
            f"quantity_{item.pk}": "1",
        })
        child = Order.objects.get(split_root=order)
        self.assertRedirects(response, child.get_absolute_url())
        detail = self.client.get(child.get_absolute_url())
        self.assertContains(detail, order.order_code)
        self.assertContains(detail, child.order_code)
        self.assertContains(detail, "Ghép về")

    def test_manager_can_open_visible_promotion_management(self):
        self.client.force_login(self.users["MANAGER"])
        response = self.client.get(reverse("sales:promotion_list"))
        self.assertContains(response, "Mã giảm giá")
        self.assertContains(response, reverse("sales:promotion_create"))

    def test_phone_lookup_and_automatic_customer_creation_when_opening_table(self):
        self.client.force_login(self.users["WAITER"])
        lookup = self.client.get(reverse("sales:customer_lookup"), {"phone": "+84 912 345 678"})
        self.assertEqual(lookup.status_code, 200)
        self.assertTrue(lookup.json()["found"])
        self.assertEqual(lookup.json()["customer"]["name"], self.customer.full_name)

        new_table = DiningTable.objects.create(code="IT02", name="Bàn khách mới", area=self.area, capacity=4)
        response = self.client.post(reverse("sales:action", args=["open"]), {
            "table_id": new_table.pk,
            "guest_count": 3,
            "customer_phone": "+84 903 456 789",
            "customer_name": "Trần Khách Mới",
        })
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get(phone="0903456789")
        order = Order.objects.get(table=new_table)
        self.assertEqual(order.customer, customer)
        self.assertEqual(customer.membership_tier, self.tier)
        workspace = self.client.get(reverse("sales:workspace"), {"order": order.pk})
        self.assertContains(workspace, customer.full_name)
        self.assertContains(workspace, customer.phone)
        table_overview = self.client.get(reverse("sales:workspace"))
        self.assertContains(table_overview, f"?order={order.pk}#sales-order")
        estimate = self.client.get(reverse("sales:estimate_print", args=[order.pk]))
        self.assertContains(estimate, "PHIẾU TẠM TÍNH")
        self.assertContains(estimate, customer.full_name)

    def test_new_phone_requires_customer_name(self):
        self.client.force_login(self.users["WAITER"])
        new_table = DiningTable.objects.create(code="IT03", name="Bàn thiếu tên", area=self.area, capacity=4)
        response = self.client.post(reverse("sales:action", args=["open"]), {
            "table_id": new_table.pk,
            "guest_count": 2,
            "customer_phone": "0903999888",
        })
        self.assertRedirects(response, reverse("sales:workspace"))
        self.assertFalse(Customer.objects.filter(phone="0903999888").exists())
        self.assertFalse(Order.objects.filter(table=new_table).exists())

        new_table.status = DiningTable.Status.OCCUPIED
        new_table.save(update_fields=("status", "updated_at"))
        self.client.post(reverse("sales:action", args=["open"]), {
            "table_id": new_table.pk,
            "guest_count": 2,
            "customer_phone": "0903999777",
            "customer_name": "Không được lưu",
        })
        self.assertFalse(Customer.objects.filter(phone="0903999777").exists())

    def test_table_manager_renders_direct_pos_order_without_booking(self):
        order = services.open_table(
            actor=self.users["WAITER"], table_id=self.table.pk, guest_count=2, customer_id=self.customer.pk
        )
        empty_table = DiningTable.objects.create(code="IT04", name="Bàn trống POS", area=self.area, capacity=4)
        self.assertIsNone(order.booking_id)
        self.client.force_login(self.users["MANAGER"])
        response = self.client.get(reverse("seating:table_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.get_absolute_url())
        self.assertContains(response, f'{reverse("sales:workspace")}?order={order.pk}#sales-order')
        self.assertContains(response, f'{reverse("sales:workspace")}?open_table={empty_table.pk}#sales-tables')
        self.assertNotContains(response, f'{reverse("orders:walk_in")}?table={empty_table.pk}')
        self.assertNotContains(response, "/dat-ban/None/")

    def test_grouped_table_payment_page_is_visible(self):
        order = self.ready_order_for_payment(request_payment=False)
        self.client.force_login(self.users["CASHIER"])
        response = self.client.get(reverse("orders:table_payment"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thanh toán theo bàn")
        self.assertContains(response, "Chọn một hoặc nhiều bàn")
        self.assertContains(response, f'value="{order.pk}"')

        response = self.client.post(reverse("orders:table_payment"), {
            "orders": [order.pk],
            "payment_method": "CASH",
            "promotion_code": "",
            "reference": "GOP-BAN-TEST",
        })
        self.assertRedirects(response, reverse("seating:table_list"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIsNotNone(order.invoice.payments.get().batch_id)

    def test_table_card_amount_uses_only_current_order_and_all_discounts(self):
        self.active_promotion()
        first = self.ready_order_for_payment()
        services.process_payment(
            actor=self.users["CASHIER"], order_id=first.pk,
            payment_method="CASH", promotion_code="GIAM10",
        )
        services.finish_cleaning(actor=self.users["WAITER"], table_id=self.table.pk)

        second = services.open_table(
            actor=self.users["WAITER"], table_id=self.table.pk, guest_count=1, customer_id=self.customer.pk
        )
        services.add_item(
            actor=self.users["WAITER"], order_id=second.pk, expected_revision=self.revision(second),
            dish_id=self.dish.pk, quantity=1,
        )
        self.client.force_login(self.users["CASHIER"])
        response = self.client.get(reverse("seating:table_list"))
        table_row = next(row for row in response.context["page_obj"] if row.pk == self.table.pk)
        self.assertEqual(table_row.current_order_subtotal, Decimal("50000"))
        self.assertEqual(table_row.current_order_total, Decimal("47500"))

    def test_pos_http_payment_applies_tier_and_opens_printable_invoice(self):
        order = services.open_table(
            actor=self.users["WAITER"], table_id=self.table.pk, guest_count=2, customer_id=self.customer.pk
        )
        item = services.add_item(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order),
            dish_id=self.dish.pk, quantity=2,
        )
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        for target, actor in ((OrderItem.Status.COOKING, self.users["KITCHEN"]), (OrderItem.Status.READY, self.users["KITCHEN"]), (OrderItem.Status.SERVED, self.users["WAITER"])):
            services.transition_item(
                actor=actor, order_id=order.pk, item_id=item.pk,
                expected_revision=self.revision(order), target=target,
            )
        services.request_payment(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))

        self.client.force_login(self.users["CASHIER"])
        response = self.client.post(reverse("sales:payment"), {
            "order_id": order.pk,
            "payment_method": "BANK_TRANSFER",
            "transaction_code": "VCB-TEST-001",
            "print_after_payment": "1",
        })
        invoice = Invoice.objects.get(order=order)
        self.assertRedirects(response, reverse("sales:invoice_print", args=[invoice.pk]), fetch_redirect_response=False)
        self.assertEqual(invoice.discount_amount, Decimal("5000"))
        self.assertEqual(invoice.total_amount, Decimal("95000"))
        self.assertEqual(invoice.payments.get().transaction_code, "VCB-TEST-001")
        printed = self.client.get(reverse("sales:invoice_print", args=[invoice.pk]))
        self.assertContains(printed, "HÓA ĐƠN THANH TOÁN")
        self.assertContains(printed, "Chuyển khoản")
        self.assertContains(printed, "95.000")

    def test_legacy_batch_service_uses_safe_direct_order_payment(self):
        order = services.open_table(actor=self.users["WAITER"], table_id=self.table.pk, guest_count=1)
        item = services.add_item(
            actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order),
            dish_id=self.dish.pk, quantity=1,
        )
        services.send_to_kitchen(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))
        for target, actor in ((OrderItem.Status.COOKING, self.users["KITCHEN"]), (OrderItem.Status.READY, self.users["KITCHEN"]), (OrderItem.Status.SERVED, self.users["WAITER"])):
            services.transition_item(actor=actor, order_id=order.pk, item_id=item.pk, expected_revision=self.revision(order), target=target)
        services.request_payment(actor=self.users["WAITER"], order_id=order.pk, expected_revision=self.revision(order))

        batch, table_codes = services.pay_tables(
            actor=self.users["CASHIER"], order_ids=[order.pk], payment_method="CASH"
        )
        self.assertEqual(table_codes, [self.table.code])
        self.assertEqual(batch.total, Decimal("50000"))
        self.assertEqual(batch.payments.get().invoice.order_id, order.pk)

    @override_settings(
        VNPAY_TMN_CODE="TESTTMN",
        VNPAY_HASH_SECRET="test-secret",
        VNPAY_PAYMENT_URL="https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
        VNPAY_RETURN_URL="https://merchant.example/sales/payment/vnpay/return/",
    )
    def test_vnpay_ipn_settles_once_and_updates_membership(self):
        order = self.ready_order_for_payment()
        online_payment, gateway_url = services.create_vnpay_payment(
            actor=self.users["CASHIER"], order_id=order.pk,
            return_url="https://ignored.example/return", ip_address="127.0.0.1",
        )
        self.assertIn("https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?", gateway_url)
        self.assertIn("vnp_SecureHash=", gateway_url)
        params = {
            "vnp_TmnCode": "TESTTMN",
            "vnp_TxnRef": online_payment.txn_ref,
            "vnp_Amount": "9500000",
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
            "vnp_TransactionNo": "14567890",
            "vnp_BankCode": "NCB",
        }
        params["vnp_SecureHash"] = sign(params)

        response = self.client.get(reverse("sales:vnpay_ipn"), params)
        self.assertEqual(response.json()["RspCode"], "00")
        order.refresh_from_db()
        self.customer.refresh_from_db()
        online_payment.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(online_payment.status, OnlinePayment.Status.PAID)
        self.assertEqual(self.customer.total_spending, Decimal("95000"))
        self.assertEqual(order.invoice.payments.get().method, Payment.Method.VNPAY)

        repeated = self.client.get(reverse("sales:vnpay_ipn"), params)
        self.customer.refresh_from_db()
        self.assertEqual(repeated.json()["RspCode"], "02")
        self.assertEqual(self.customer.total_spending, Decimal("95000"))

    @override_settings(VNPAY_TMN_CODE="TESTTMN", VNPAY_HASH_SECRET="test-secret")
    def test_vnpay_ipn_rejects_bad_signature_and_wrong_amount(self):
        order = self.ready_order_for_payment()
        online_payment, _ = services.create_vnpay_payment(
            actor=self.users["CASHIER"], order_id=order.pk,
            return_url="https://merchant.example/return", ip_address="127.0.0.1",
        )
        bad_signature = self.client.get(reverse("sales:vnpay_ipn"), {
            "vnp_TmnCode": "TESTTMN", "vnp_TxnRef": online_payment.txn_ref,
            "vnp_Amount": "9500000", "vnp_SecureHash": "not-valid",
        })
        self.assertEqual(bad_signature.json()["RspCode"], "97")

        wrong_amount = {
            "vnp_TmnCode": "TESTTMN",
            "vnp_TxnRef": online_payment.txn_ref,
            "vnp_Amount": "10000",
            "vnp_ResponseCode": "00",
            "vnp_TransactionStatus": "00",
        }
        wrong_amount["vnp_SecureHash"] = sign(wrong_amount)
        response = self.client.get(reverse("sales:vnpay_ipn"), wrong_amount)
        self.assertEqual(response.json()["RspCode"], "04")
        order.refresh_from_db()
        online_payment.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAYMENT_REQUESTED)
        self.assertEqual(online_payment.status, OnlinePayment.Status.PENDING)
