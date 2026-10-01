from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.admin import admin_site
from apps.bookings.models import Booking, BookingActivityLog
from apps.bookings.services import transition_booking
from apps.customers.models import Customer
from apps.menu.models import Category, Unit, Dish
from apps.menu.services import save_dish
from apps.inventory.models import Ingredient, InventoryTransaction, RecipeIngredient
from apps.seating.models import Area, DiningTable
from apps.seating.selectors import tables
from apps.seating.services import save_table
from apps.orders.models import Order, OrderItem, OrderActivityLog
from apps.orders import services
from apps.orders.selectors import kitchen_items, order_list


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            user = get_user_model().objects.create_user(username=role.lower(), password="Test!123", is_staff=role == "MANAGER")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.manager, cls.waiter, cls.kitchen = (cls.users[key] for key in ("MANAGER", "WAITER", "KITCHEN"))
        cls.root = get_user_model().objects.create_superuser(username="root", password="Test!123")
        cls.area = Area.objects.create(name="Tầng 1")
        cls.table = DiningTable.objects.create(code="B01", area=cls.area, capacity=4)
        cls.other_table = DiningTable.objects.create(code="B02", area=cls.area, capacity=4)
        cls.customer = Customer.objects.create(full_name="Khách riêng", phone="0912345678")
        cls.category = Category.objects.create(name="Món chính")
        cls.unit = Unit.objects.create(name="Phần")
        cls.dish = Dish.objects.create(code="M001", name="Cơm chiên", category=cls.category, unit=cls.unit, price=85000)

    def setUp(self):
        now = timezone.now()
        self.visit = Booking.objects.create(customer=self.customer, customer_name=self.customer.full_name,
            customer_phone=self.customer.phone, table=self.table, party_size=2, starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(hours=2), seated_at=now - timedelta(minutes=5), status="SEATED")
        self.order = services.open_order(actor=self.waiter, booking_id=self.visit.pk)

    def url(self, name, *args):
        return reverse(f"orders:{name}", args=args or None)

    def revision(self):
        self.order.refresh_from_db()
        return self.order.revision

    def add(self, **changes):
        data = dict(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), dish_id=self.dish.pk, quantity=2, note="Ít cay")
        data.update(changes)
        return services.add_item(**data)

    def send(self):
        return services.send_to_kitchen(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision())

    def transition(self, item, target, actor=None, **kwargs):
        return services.transition_item(actor=actor or (self.kitchen if target in ("COOKING", "READY") else self.waiter),
            order_id=self.order.pk, item_id=item.pk, target=target, expected_revision=self.revision(), **kwargs)

    def complete_visit(self):
        self.visit.refresh_from_db()
        return transition_booking(actor=self.waiter, booking_id=self.visit.pk, target="COMPLETED",
            expected_status=self.visit.status, expected_revision=self.visit.revision)

    def test_permissions_and_navigation(self):
        for role, actor in self.users.items():
            self.client.force_login(actor)
            front = role in ("MANAGER", "WAITER", "CASHIER")
            for url in (self.url("list"), self.order.get_absolute_url(), self.url("open"), self.url("walk_in"), self.url("add_item", self.order.pk)):
                self.assertEqual(self.client.get(url).status_code, 200 if front else 403)
            self.assertEqual(self.client.get(self.url("kitchen")).status_code, 200 if role in ("MANAGER", "KITCHEN") else 403)
            workspace = self.client.get(reverse("accounts:workspace")).content.decode()
            self.assertEqual(f'href="{self.url("list")}"' in workspace, front)
            if front:
                detail = self.client.get(self.order.get_absolute_url())
                self.assertEqual("Nhật ký đơn" in detail.content.decode(), role == "MANAGER")
        self.client.logout()
        self.assertEqual(self.client.get(self.url("list")).status_code, 302)

    def test_staff_flag_inactive_and_revoked_permissions_are_rechecked(self):
        staff = get_user_model().objects.create_user(username="staff", is_staff=True)
        for actor in (staff, AnonymousUser(), self.kitchen, self.users["INVENTORY"]):
            with self.assertRaises(PermissionDenied):
                self.add(actor=actor)
        self.assertTrue(self.waiter.has_perm("orders.manage_order"))
        self.waiter.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.add()
        get_user_model().objects.filter(pk=self.root.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.add(actor=self.root)

    def test_open_is_idempotent_and_only_for_seated_visits(self):
        self.assertEqual(services.open_order(actor=self.root, booking_id=self.visit.pk).pk, self.order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderActivityLog.objects.count(), 1)
        for status in ("PENDING", "CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"):
            Booking.objects.filter(pk=self.visit.pk).update(status=status)
            with self.assertRaises(ValidationError):
                services.open_order(actor=self.waiter, booking_id=self.visit.pk)

    def test_walk_in_seats_and_opens_order_without_fake_customer(self):
        self.client.force_login(self.waiter)
        response = self.client.post(self.url("walk_in"), {"table": self.other_table.pk, "party_size": 3, "customer_name": "Khách trực tiếp"})
        order = Order.objects.exclude(pk=self.order.pk).get()
        self.assertRedirects(response, order.get_absolute_url())
        self.assertTrue(order.booking.is_walk_in)
        self.assertIsNone(order.booking.customer_id)
        self.assertEqual(order.booking.status, "SEATED")
        self.assertEqual(order.booking.duration_minutes, 120)
        self.assertTrue(order.booking.booking_code.startswith("LK"))
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(tables().get(pk=self.other_table.pk).current_status, "occupied")
        self.assertContains(self.client.get(order.booking.get_absolute_url()), "Khách không đặt trước")

    def test_walk_in_phone_matches_existing_customer_and_validates_phone(self):
        order = services.open_walk_in_order(actor=self.waiter, table_id=self.other_table.pk, party_size=2, customer_phone="+84912345678")
        self.assertEqual(order.booking.customer_id, self.customer.pk)
        self.assertEqual(order.booking.customer_name, self.customer.full_name)
        self.assertEqual(order.booking.customer_phone, self.customer.phone)
        with self.assertRaises(ValidationError):
            services.open_walk_in_order(actor=self.waiter, table_id=999999, party_size=2)

    def test_walk_in_rejects_occupied_overdue_closed_capacity_and_conflicting_reservation(self):
        Booking.objects.filter(pk=self.visit.pk).update(ends_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaises(ValidationError):
            services.open_walk_in_order(actor=self.waiter, table_id=self.table.pk, party_size=2)
        for changes in ({"party_size": 5}, {"party_size": 0}, {"duration_minutes": 0}, {"customer_phone": "bad"}):
            data = dict(actor=self.waiter, table_id=self.other_table.pk, party_size=2)
            data.update(changes)
            with self.assertRaises(ValidationError):
                services.open_walk_in_order(**data)
        DiningTable.objects.filter(pk=self.other_table.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            services.open_walk_in_order(actor=self.waiter, table_id=self.other_table.pk, party_size=2)
        DiningTable.objects.filter(pk=self.other_table.pk).update(is_active=True)
        now = timezone.now()
        Booking.objects.create(customer=self.customer, customer_name="Hẹn", customer_phone=self.customer.phone, table=self.other_table,
            party_size=2, starts_at=now + timedelta(minutes=30), ends_at=now + timedelta(hours=2), status="CONFIRMED")
        with self.assertRaises(ValidationError):
            services.open_walk_in_order(actor=self.waiter, table_id=self.other_table.pk, party_size=2)
        self.assertEqual(Order.objects.count(), 1)

    def test_walk_in_rolls_back_visit_when_order_audit_fails(self):
        before = BookingActivityLog.objects.count()
        with patch("apps.orders.services._log", side_effect=RuntimeError("Audit failed")), self.assertRaises(RuntimeError):
            services.open_walk_in_order(actor=self.waiter, table_id=self.other_table.pk, party_size=2)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookingActivityLog.objects.count(), before)
        self.assertEqual(tables().get(pk=self.other_table.pk).current_status, "empty")

    def test_snapshot_price_name_unit_and_multiple_rounds(self):
        first = self.add()
        save_dish(actor=self.manager, dish_id=self.dish.pk, expected_revision=1, code="M002", name="Cơm mới",
                  category_id=self.category.pk, unit_id=self.unit.pk, price=95000, status="AVAILABLE")
        Unit.objects.filter(pk=self.unit.pk).update(name="Đĩa")
        services.edit_item(actor=self.waiter, order_id=self.order.pk, item_id=first.pk, expected_revision=self.revision(), quantity=3, note="Không hành")
        first.refresh_from_db()
        self.assertEqual((first.dish_name, first.dish_code, first.unit_name, first.unit_price), ("Cơm chiên", "M001", "Phần", Decimal(85000)))
        self.send()
        second = self.add(quantity=1)
        self.assertEqual(second.unit_price, 95000)
        self.assertEqual(second.unit_name, "Đĩa")
        self.assertEqual(second.status, "DRAFT")
        self.assertEqual(self.order.total, 350000)

    def test_recipe_deducts_stock_snapshots_cost_and_returns_before_cooking(self):
        ingredient = Ingredient.objects.create(
            code="GAO01", name="Gạo", unit="kg", stock_quantity=Decimal("10"),
            average_unit_cost=Decimal("50000"), low_stock_threshold=Decimal("1"),
        )
        RecipeIngredient.objects.create(dish=self.dish, ingredient=ingredient, quantity=Decimal("0.200"))
        item = self.add(quantity=2)

        self.send()
        ingredient.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(ingredient.stock_quantity, Decimal("9.600"))
        self.assertEqual(item.unit_cost_snapshot, Decimal("10000"))
        self.assertEqual(item.total_cost, Decimal("20000"))
        self.assertIsNotNone(item.inventory_deducted_at)
        self.assertEqual(
            InventoryTransaction.objects.filter(
                transaction_type=InventoryTransaction.Type.SALE_USAGE,
                order_item_reference=item.pk,
            ).count(),
            1,
        )

        self.transition(item, OrderItem.Status.CANCELLED, reason="Khách đổi món")
        ingredient.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(ingredient.stock_quantity, Decimal("10.000"))
        self.assertIsNotNone(item.inventory_returned_at)
        self.assertEqual(
            InventoryTransaction.objects.filter(
                transaction_type=InventoryTransaction.Type.SALE_RETURN,
                order_item_reference=item.pk,
            ).count(),
            1,
        )

    def test_sending_to_kitchen_rolls_back_when_recipe_stock_is_insufficient(self):
        ingredient = Ingredient.objects.create(
            code="THIT01", name="Thịt", unit="kg", stock_quantity=Decimal("0.100"),
            average_unit_cost=Decimal("120000"), low_stock_threshold=Decimal("0"),
        )
        RecipeIngredient.objects.create(dish=self.dish, ingredient=ingredient, quantity=Decimal("0.200"))
        item = self.add(quantity=1)

        with self.assertRaisesMessage(ValidationError, "Không đủ tồn kho"):
            self.send()
        ingredient.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(ingredient.stock_quantity, Decimal("0.100"))
        self.assertEqual(item.status, OrderItem.Status.DRAFT)
        self.assertIsNone(item.inventory_deducted_at)
        self.assertFalse(InventoryTransaction.objects.filter(order_item_reference=item.pk).exists())

    def test_invoice_is_created_and_payment_marks_order_paid(self):
        item = self.add(quantity=2)
        self.send()
        for state in ("COOKING", "READY", "SERVED"):
            self.transition(item, state)
        item.refresh_from_db()
        self.assertEqual(item.status, "SERVED")
        services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="AWAITING_PAYMENT")

        invoice = services.record_payment(actor=self.users["CASHIER"], order_id=self.order.pk, expected_revision=self.revision(), amount=Decimal("170000"), payment_method="CASH")

        self.assertEqual(invoice.status, "PAID")
        self.assertEqual(invoice.total, Decimal("170000"))
        self.assertTrue(invoice.invoice_code.startswith("HD"))
        self.assertEqual(invoice.payments.count(), 1)
        self.assertEqual(invoice.payments.first().amount, Decimal("170000"))
        self.assertEqual(invoice.payments.first().method, "CASH")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "COMPLETED")

    def test_paid_invoice_closes_order_and_allows_visit_completion(self):
        item = self.add(quantity=2)
        self.send()
        for state in ("COOKING", "READY", "SERVED"):
            self.transition(item, state)
        services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="AWAITING_PAYMENT")
        services.record_payment(actor=self.users["CASHIER"], order_id=self.order.pk, expected_revision=self.revision(), amount=Decimal("170000"), payment_method="CASH")

        self.order.refresh_from_db()
        self.visit.refresh_from_db()
        self.assertEqual(self.order.status, "COMPLETED")
        self.assertEqual(self.order.invoice.status, "PAID")
        self.assertEqual(self.visit.status, "COMPLETED")
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.CLEANING)

    def test_payment_form_renders_and_records_payment(self):
        item = self.add(quantity=2)
        self.send()
        for state in ("COOKING", "READY", "SERVED"):
            self.transition(item, state)
        services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="AWAITING_PAYMENT")
        self.client.force_login(self.users["CASHIER"])

        response = self.client.get(self.url("payment", self.order.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thu tiền")

        response = self.client.post(self.url("payment", self.order.pk), {
            "expected_revision": self.revision(),
            "amount": "170000",
            "payment_method": "CASH",
            "reference": "Mã test",
        })
        self.assertRedirects(response, self.order.get_absolute_url())
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.invoice)
        self.assertEqual(self.order.invoice.status, "PAID")
        self.assertEqual(self.order.invoice.payments.first().amount, Decimal("170000"))

    def test_full_workflow_and_payment_boundary(self):
        item = self.add()
        self.send()
        for state in ("COOKING", "READY", "SERVED"):
            self.transition(item, state)
        item.refresh_from_db()
        self.assertTrue(all((item.sent_at, item.started_at, item.ready_at, item.served_at)))
        self.assertLessEqual(item.sent_at, item.started_at)
        self.assertFalse(kitchen_items().exists())
        services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="AWAITING_PAYMENT")
        with self.assertRaises(ValidationError):
            self.complete_visit()
        with self.assertRaises(ValidationError):
            self.add()
        self.assertEqual(tables().get(pk=self.table.pk).current_status, "occupied")
        services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="OPEN")
        self.add(quantity=1)
        self.assertEqual(self.order.items.count(), 2)

    def test_waiting_payment_requires_all_live_items_served(self):
        for stage in (None, "DRAFT", "SENT", "COOKING", "READY"):
            if stage == "DRAFT":
                item = self.add()
            elif stage == "SENT":
                self.send()
            elif stage:
                self.transition(item, stage)
            with self.assertRaises(ValidationError):
                services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="AWAITING_PAYMENT")

    def test_unavailable_dishes_cannot_be_added_or_sent(self):
        item = self.add()
        for update in ({"status": "SOLD_OUT"}, {"status": "INACTIVE"}):
            Dish.objects.filter(pk=self.dish.pk).update(**update)
            with self.assertRaises(ValidationError):
                self.add()
            with self.assertRaises(ValidationError):
                self.send()
        Dish.objects.filter(pk=self.dish.pk).update(status="AVAILABLE")
        Category.objects.filter(pk=self.category.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.add()
        with self.assertRaises(ValidationError):
            self.send()
        item.refresh_from_db()
        self.assertEqual(item.status, "DRAFT")

    def test_batch_send_is_atomic_when_one_dish_becomes_unavailable(self):
        first = self.add()
        other = Dish.objects.create(code="OTHER", name="Nước", category=self.category, unit=self.unit, price=10000)
        second = self.add(dish_id=other.pk)
        Dish.objects.filter(pk=other.pk).update(status="SOLD_OUT")
        with self.assertRaises(ValidationError):
            self.send()
        self.assertEqual(self.order.items.filter(status="DRAFT").count(), 2)
        self.assertEqual(self.order.items.filter(sent_at__isnull=False).count(), 0)

    def test_quantity_note_validation_and_post_price_tampering(self):
        for quantity in (0, -1, 101, 1.5, True, "2"):
            with self.assertRaises(ValidationError):
                self.add(quantity=quantity)
        with self.assertRaises(ValidationError):
            self.add(note="x" * 501)
        self.client.force_login(self.waiter)
        response = self.client.post(self.url("add_item", self.order.pk), {"expected_revision": self.revision(), "dish": self.dish.pk,
            "quantity": 1, "unit_price": 1, "status": "SERVED", "dish_name": "Hacked"})
        self.assertRedirects(response, self.order.get_absolute_url())
        item = self.order.items.get()
        self.assertEqual((item.unit_price, item.status, item.dish_name), (85000, "DRAFT", self.dish.name))

    def test_sent_items_cannot_be_edited_and_invalid_transitions_rejected(self):
        item = self.add()
        with self.assertRaises(ValidationError):
            self.transition(item, "COOKING")
        self.send()
        with self.assertRaises(ValidationError):
            services.edit_item(actor=self.waiter, order_id=self.order.pk, item_id=item.pk, expected_revision=self.revision(), quantity=3)
        with self.assertRaises(ValidationError):
            self.transition(item, "SERVED")
        with self.assertRaises(PermissionDenied):
            self.transition(item, "COOKING", actor=self.waiter)
        with self.assertRaises(PermissionDenied):
            self.transition(item, "CANCELLED", actor=self.kitchen, reason="Không làm được")

    def test_cancellation_requires_reason_and_prepared_requires_manager(self):
        item = self.add()
        with self.assertRaises(ValidationError):
            self.transition(item, "CANCELLED", reason="   ")
        self.send()
        self.transition(item, "COOKING")
        with self.assertRaises(PermissionDenied):
            self.transition(item, "CANCELLED", reason="Khách đổi món")
        self.transition(item, "CANCELLED", actor=self.manager, reason="Khách đổi món, quản lí duyệt")
        item.refresh_from_db()
        self.assertEqual(item.status, "CANCELLED")
        self.assertTrue(item.cancelled_at)
        self.assertEqual(self.order.total, 0)
        self.assertFalse(kitchen_items().exists())
        self.assertIn("quản lí duyệt", OrderActivityLog.objects.first().description)

    def test_cancelling_sent_item_and_void_order_allows_finishing_visit(self):
        item = self.add()
        self.send()
        self.transition(item, "CANCELLED", reason="Khách đổi ý trước khi làm")
        with self.assertRaises(ValidationError):
            self.complete_visit()
        services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="VOID", reason="Khách không dùng món")
        self.complete_visit()
        self.assertEqual(tables().get(pk=self.table.pk).current_status, "cleaning")
        with self.assertRaises(ValidationError):
            self.add()
        self.assertEqual(OrderActivityLog.objects.filter(action="Đã hủy").count(), 2)

    def test_void_rejects_live_items_and_needs_reason(self):
        with self.assertRaises(ValidationError):
            services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="VOID")
        self.add()
        with self.assertRaises(ValidationError):
            services.change_order_status(actor=self.waiter, order_id=self.order.pk, expected_revision=self.revision(), target="VOID", reason="Không được bỏ qua món")

    def test_booking_completion_is_blocked_in_service_and_ui(self):
        self.client.force_login(self.waiter)
        response = self.client.get(self.visit.get_absolute_url())
        self.assertContains(response, "Cần xử lý đơn")
        self.assertNotContains(response, reverse("bookings:transition", args=[self.visit.pk, "COMPLETED"]))
        with self.assertRaises(ValidationError):
            self.complete_visit()
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, "SEATED")

    def test_stale_form_and_repeat_send_do_not_duplicate_items_or_logs(self):
        revision = self.revision()
        item = self.add()
        with self.assertRaises(ValidationError):
            self.add(expected_revision=revision)
        revision = self.revision()
        self.send()
        with self.assertRaises(ValidationError):
            services.send_to_kitchen(actor=self.waiter, order_id=self.order.pk, expected_revision=revision)
        self.assertEqual(self.order.items.count(), 1)
        self.assertEqual(self.order.activity_logs.filter(action="Gửi Bếp").count(), 1)

    def test_item_cannot_be_mutated_through_another_order(self):
        item = self.add()
        other = services.open_walk_in_order(actor=self.waiter, table_id=self.other_table.pk, party_size=1)
        with self.assertRaises(OrderItem.DoesNotExist):
            services.edit_item(actor=self.waiter, order_id=other.pk, item_id=item.pk, expected_revision=other.revision, quantity=3)
        self.client.force_login(self.waiter)
        self.assertEqual(self.client.post(self.url("edit_item", other.pk, item.pk), {"quantity": 3, "expected_revision": other.revision}).status_code, 404)

    def test_mutation_audit_failure_rolls_back_items_status_revision(self):
        item = self.add()
        revision = self.revision()
        with patch("apps.orders.services._log", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                self.send()
            with self.assertRaises(RuntimeError):
                self.add()
            with self.assertRaises(RuntimeError):
                self.transition(item, "CANCELLED", reason="Thử hủy")
        item.refresh_from_db()
        self.assertEqual(item.status, "DRAFT")
        self.assertIsNone(item.sent_at)
        self.assertEqual(self.revision(), revision)
        self.assertEqual(self.order.items.count(), 1)

    def test_kitchen_queue_shows_only_submitted_items_without_customer_or_price(self):
        item = self.add()
        self.assertFalse(kitchen_items().exists())
        self.client.force_login(self.kitchen)
        self.assertEqual(self.client.get(self.url("transition_item", self.order.pk, item.pk, "COOKING")).status_code, 404)
        self.send()
        self.client.force_login(self.kitchen)
        response = self.client.get(self.url("kitchen"))
        self.assertContains(response, "Ít cay")
        self.assertContains(response, "Cơm chiên")
        self.assertNotContains(response, self.customer.full_name)
        self.assertNotContains(response, self.customer.phone)
        self.assertNotContains(response, "85.000")
        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 403)
        self.transition(item, "COOKING")
        self.assertFalse(kitchen_items(status="SENT").exists())
        self.assertEqual(kitchen_items(q="B01", status="COOKING").count(), 1)

    def test_kitchen_and_waiter_http_transitions(self):
        item = self.add()
        self.send()
        self.client.force_login(self.kitchen)
        for state in ("COOKING", "READY"):
            url = self.url("transition_item", self.order.pk, item.pk, state)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.customer.full_name)
            self.assertRedirects(self.client.post(url, {"expected_revision": self.revision()}), self.url("kitchen"))
        self.client.force_login(self.waiter)
        self.assertRedirects(self.client.post(self.url("transition_item", self.order.pk, item.pk, "SERVED"), {"expected_revision": self.revision()}), self.order.get_absolute_url())
        self.assertEqual(self.client.get(self.url("transition_item", self.order.pk, item.pk, "BAD")).status_code, 404)

    def test_csrf_get_and_escaped_notes(self):
        item = self.add(note="<script>alert(1)</script>")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.waiter)
        for route in (self.url("send", self.order.pk), self.url("edit_item", self.order.pk, item.pk), self.url("await", self.order.pk), self.url("void", self.order.pk)):
            self.assertEqual(client.get(route).status_code, 200)
            self.assertEqual(client.post(route, {"expected_revision": self.revision()}).status_code, 403)
        self.assertEqual(self.order.items.get().status, "DRAFT")
        self.assertContains(client.get(self.order.get_absolute_url()), "&lt;script&gt;")
        self.assertNotContains(client.get(self.order.get_absolute_url()), "<script>alert")

    def test_database_constraints_protect_snapshot_and_relations(self):
        item = self.add()
        for obj in (self.dish, self.visit, self.order):
            with self.assertRaises(ProtectedError):
                obj.delete()
        for change in ({"quantity": 0}, {"unit_price": 0}, {"status": "BAD"}, {"status": "CANCELLED"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                OrderItem.objects.filter(pk=item.pk).update(**change)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(booking=self.visit)

    def test_filters_pagination_and_no_per_row_related_queries(self):
        self.add()
        self.assertEqual(order_list(q=self.order.order_code).count(), 1)
        self.assertEqual(order_list(q="B01").count(), 1)
        self.assertFalse(order_list(status="VOID").exists())
        self.client.force_login(self.waiter)
        self.assertEqual(self.client.get(self.url("list"), {"status": "BAD"}).context["page_obj"].paginator.count, 0)
        self.send()
        with self.assertNumQueries(1):
            for item in kitchen_items():
                str(item.order.booking.table)
                str(item.order)
        with self.assertNumQueries(2):
            for order in order_list():
                order.total
                str(order.booking.table)

    def test_order_logs_keep_actor_after_account_deletion_and_admin_readonly(self):
        self.add(actor=self.users["CASHIER"])
        with self.assertRaises(ProtectedError):
            self.waiter.delete()
        self.users["CASHIER"].delete()
        self.assertEqual(OrderActivityLog.objects.filter(actor_snapshot="cashier", performed_by__isnull=True).count(), 1)
        request = RequestFactory().get("/admin/")
        request.user = self.root
        for model in (Order, OrderItem, OrderActivityLog):
            admin = admin_site._registry[model]
            self.assertTrue(admin.has_view_permission(request))
            self.assertFalse(admin.has_add_permission(request))
            self.assertFalse(admin.has_change_permission(request))
            self.assertFalse(admin.has_delete_permission(request))
            with self.assertRaises(PermissionDenied):
                admin.save_model(request, model(), None, False)

    def test_walk_in_protects_table_from_shutdown(self):
        services.open_walk_in_order(actor=self.waiter, table_id=self.other_table.pk, party_size=2)
        with self.assertRaises(ValidationError):
            save_table(actor=self.manager, table_id=self.other_table.pk, code=self.other_table.code,
                       area_id=self.area.pk, capacity=4, is_active=False)

    def test_denied_posts_cannot_open_add_send_edit_or_change_orders(self):
        item = self.add()
        for actor in (self.kitchen, self.users["INVENTORY"]):
            self.client.force_login(actor)
            for route in (self.url("open"), self.url("walk_in"), self.url("add_item", self.order.pk), self.url("send", self.order.pk),
                          self.url("edit_item", self.order.pk, item.pk), self.url("await", self.order.pk), self.url("void", self.order.pk)):
                self.assertEqual(self.client.post(route, {"expected_revision": self.revision(), "quantity": 1}).status_code, 403)
        self.assertEqual(self.order.items.count(), 1)
        self.assertEqual(self.order.items.get().status, "DRAFT")

    def test_http_edit_send_stale_error_void_and_await_reopen(self):
        self.client.force_login(self.waiter)
        item = self.add()
        self.assertRedirects(self.client.post(self.url("edit_item", self.order.pk, item.pk),
            {"expected_revision": self.revision(), "quantity": 3, "note": "Không hành"}), self.order.get_absolute_url())
        revision = self.revision()
        self.assertContains(self.client.get(self.url("send", self.order.pk)), "Không hành")
        self.assertRedirects(self.client.post(self.url("send", self.order.pk), {"expected_revision": revision}), self.order.get_absolute_url())
        self.assertContains(self.client.post(self.url("send", self.order.pk), {"expected_revision": revision}), "Đơn đã thay đổi")
        for state in ("COOKING", "READY", "SERVED"):
            self.transition(item, state)
        for route in ("await", "reopen"):
            self.assertRedirects(self.client.post(self.url(route, self.order.pk), {"expected_revision": self.revision()}), self.order.get_absolute_url())
        self.client.force_login(self.manager)
        self.assertRedirects(self.client.post(self.url("transition_item", self.order.pk, item.pk, "CANCELLED"),
            {"expected_revision": self.revision(), "reason": "Quản lí duyệt hủy"}), self.order.get_absolute_url())
        self.assertRedirects(self.client.post(self.url("void", self.order.pk), {"expected_revision": self.revision(), "reason": "Hủy toàn bộ"}), self.order.get_absolute_url())
