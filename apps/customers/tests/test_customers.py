from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.customers.forms import CustomerForm
from apps.customers.models import Customer, CustomerActivityLog
from apps.customers.services import create_customer, delete_customer, update_customer
from apps.customers.validators import normalize_phone


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CustomerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for code in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            user = get_user_model().objects.create_user(username=code.lower(), password="Secret-test-123!", is_staff=code == "MANAGER")
            user.groups.add(Group.objects.get(name=code))
            cls.users[code] = user
        cls.superuser = get_user_model().objects.create_superuser(username="super", password="Secret-test-123!")
        cls.customer = create_customer(actor=cls.users["MANAGER"], full_name="Nguyễn An", phone="0912345678")

    def url(self, name, detail=False):
        return reverse(f"customers:customer_{name}", args=[self.customer.pk] if detail else None)

    def test_form_has_only_name_phone_and_normalizes_input(self):
        form = CustomerForm(data={"full_name": "  Trần   Bình  ", "phone": "+84 912 345 679", "email": "ignored@example.com"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(set(form.fields), {"full_name", "phone"})
        self.assertEqual(form.cleaned_data, {"full_name": "Trần Bình", "phone": "0912345679"})

    def test_duplicate_phone_is_field_error_for_form_and_service(self):
        form = CustomerForm(data={"full_name": "Trùng", "phone": "+84 912 345 678"})
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)
        with self.assertRaises(ValidationError) as caught:
            create_customer(actor=self.users["WAITER"], full_name="Trùng", phone="0912.345.678")
        self.assertIn("phone", caught.exception.message_dict)
        self.assertEqual(Customer.objects.count(), 1)

    def test_invalid_phone_values_rejected(self):
        for value in ("", "123", "912345678", "+1 2125551234", "091234567a", "091234567890", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_phone(value)

    def test_empty_name_rejected_without_log(self):
        with self.assertRaises(ValidationError):
            create_customer(actor=self.users["MANAGER"], full_name="   ", phone="0912345699")
        self.assertEqual(CustomerActivityLog.objects.count(), 1)

    def test_database_prevents_noncanonical_phone_and_blank_name(self):
        for name, phone in (("An", "+84912345699"), ("  ", "0912345699"), ("An", self.customer.phone)):
            with self.subTest(name=name, phone=phone), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Customer.objects.create(full_name=name, phone=phone)

    def test_all_roles_view_permissions_and_visible_actions(self):
        for code, user in self.users.items():
            with self.subTest(role=code):
                self.client.force_login(user)
                allowed = code in ("MANAGER", "WAITER", "CASHIER")
                response = self.client.get(self.url("list"))
                self.assertEqual(response.status_code, 200 if allowed else 403)
                self.assertEqual(self.client.get(self.url("detail", True)).status_code, 200 if allowed else 403)
                if allowed:
                    self.assertContains(response, self.url("create"))
                    self.assertContains(response, self.url("update", True))
                    if code == "MANAGER":
                        self.assertContains(response, self.url("delete", True))
                        self.assertContains(response, self.url("logs"))
                    else:
                        self.assertNotContains(response, self.url("delete", True))
                        self.assertNotContains(response, self.url("logs"))
                self.assertEqual(self.client.get(self.url("logs")).status_code, 200 if code == "MANAGER" else 403)

    def test_waiter_cashier_create_and_update_through_ui(self):
        for index, code in enumerate(("WAITER", "CASHIER")):
            with self.subTest(role=code):
                self.client.force_login(self.users[code])
                phone = f"090000000{index}"
                response = self.client.post(self.url("create"), {"full_name": "Khách mới", "phone": phone})
                customer = Customer.objects.get(phone=phone)
                self.assertRedirects(response, customer.get_absolute_url())
                response = self.client.post(reverse("customers:customer_update", args=[customer.pk]), {"full_name": "Tên mới", "phone": phone})
                self.assertRedirects(response, customer.get_absolute_url())
                customer.refresh_from_db()
                self.assertEqual(customer.full_name, "Tên mới")
                self.assertEqual(customer.activity_logs.count(), 2)

    def test_forbidden_direct_posts_cannot_change_data(self):
        for code in ("WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            with self.subTest(role=code):
                self.client.force_login(self.users[code])
                self.assertEqual(self.client.get(self.url("delete", True)).status_code, 403)
                self.assertEqual(self.client.post(self.url("delete", True)).status_code, 403)
                if code in ("KITCHEN", "INVENTORY"):
                    for route, detail in (("create", False), ("update", True)):
                        self.assertEqual(self.client.get(self.url(route, detail)).status_code, 403)
                        self.assertEqual(self.client.post(self.url(route, detail), {"full_name": "Hack", "phone": "0900000001"}).status_code, 403)
        self.assertEqual(Customer.objects.get(pk=self.customer.pk).full_name, "Nguyễn An")
        self.assertEqual(CustomerActivityLog.objects.count(), 1)

    def test_service_rechecks_revoked_or_inactive_actor(self):
        actor = self.users["WAITER"]
        self.assertTrue(actor.has_perm("customers.add_customer"))
        actor.groups.clear()
        with self.assertRaises(PermissionDenied):
            create_customer(actor=actor, full_name="An", phone="0912345600")
        actor = self.users["MANAGER"]
        get_user_model().objects.filter(pk=actor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            update_customer(actor=actor, customer_id=self.customer.pk, full_name="An", phone=self.customer.phone)

    def test_services_enforce_permissions_without_views(self):
        with self.assertRaises(PermissionDenied):
            delete_customer(actor=self.users["WAITER"], customer_id=self.customer.pk)
        with self.assertRaises(PermissionDenied):
            update_customer(actor=self.users["KITCHEN"], customer_id=self.customer.pk, full_name="An", phone=self.customer.phone)

    def test_get_delete_is_readonly_and_post_retains_snapshots(self):
        self.client.force_login(self.users["MANAGER"])
        self.assertEqual(self.client.get(self.url("delete", True)).status_code, 200)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertRedirects(self.client.post(self.url("delete", True)), self.url("list"))
        self.assertFalse(Customer.objects.exists())
        logs = CustomerActivityLog.objects.all()
        self.assertEqual(logs.count(), 2)
        self.assertTrue(all(log.customer_id is None for log in logs))
        self.assertTrue(all(log.customer_code_snapshot == self.customer.customer_code for log in logs))
        response = self.client.get(self.url("logs"), {"action": "DELETE", "q": self.customer.customer_code})
        self.assertContains(response, "Đã xóa")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_delete_protected_or_restricted_customer_rolls_back_log(self):
        for error_type in (ProtectedError, RestrictedError):
            with self.subTest(error_type=error_type):
                with patch.object(Customer, "delete", side_effect=error_type("Linked record", [self.customer])):
                    with self.assertRaises(ValidationError):
                        delete_customer(actor=self.superuser, customer_id=self.customer.pk)
                self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
                self.assertEqual(CustomerActivityLog.objects.count(), 1)

    def test_failed_audit_rolls_back_customer_write(self):
        with patch("apps.customers.services._log", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                create_customer(actor=self.superuser, full_name="An", phone="0912345600")
            with self.assertRaises(RuntimeError):
                update_customer(actor=self.superuser, customer_id=self.customer.pk, full_name="Changed", phone=self.customer.phone)
        self.assertEqual(Customer.objects.count(), 1)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, "Nguyễn An")

    def test_unchanged_edit_does_not_add_audit_noise(self):
        update_customer(actor=self.users["CASHIER"], customer_id=self.customer.pk, full_name="  Nguyễn   An ", phone="+84 912345678")
        self.assertEqual(CustomerActivityLog.objects.count(), 1)

    def test_customer_audit_survives_actor_deletion(self):
        actor = self.users["WAITER"]
        created = create_customer(actor=actor, full_name="An", phone="0912345600")
        actor.delete()
        log = created.activity_logs.get()
        self.assertIsNone(log.performed_by_id)
        self.assertEqual(log.performed_by_name_snapshot, "waiter")

    def test_search_by_code_name_normalized_phone_and_pagination(self):
        self.client.force_login(self.users["MANAGER"])
        for query in (self.customer.customer_code, "Nguyễn", "+84 912 345 678", "3456"):
            response = self.client.get(self.url("list"), {"q": query})
            self.assertEqual(list(response.context["page_obj"]), [self.customer])
        for index in range(21):
            Customer.objects.create(full_name="Khách phân trang", phone=f"090000{index:04d}")
        response = self.client.get(self.url("list"), {"q": "Khách phân trang", "page": 2})
        self.assertEqual(len(response.context["page_obj"]), 1)
        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertIn("q=", response.context["query_string"])

    def test_invalid_filters_are_visible_errors(self):
        self.client.force_login(self.users["MANAGER"])
        for route, params in (("list", {"q": "a" * 151}), ("logs", {"action": "INVALID"})):
            response = self.client.get(self.url(route), params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["filter_form"].errors)
            self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_invalid_edit_redisplays_customer_context(self):
        self.client.force_login(self.users["MANAGER"])
        response = self.client.post(self.url("update", True), {"full_name": "", "phone": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.customer.customer_code)
        self.assertTrue(response.context["form"].errors)

    def test_anonymous_redirect_inactive_denial_and_csrf_protection(self):
        self.assertEqual(self.client.get(self.url("list")).status_code, 302)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.superuser)
        for route, detail in (("create", False), ("update", True), ("delete", True)):
            self.assertEqual(csrf_client.post(self.url(route, detail), {"full_name": "An", "phone": "0912345600"}).status_code, 403)
        self.assertEqual(Customer.objects.count(), 1)

    def test_superuser_can_crud_without_profile(self):
        self.client.force_login(self.superuser)
        for route, detail in (("list", False), ("create", False), ("detail", True), ("update", True), ("delete", True), ("logs", False)):
            self.assertEqual(self.client.get(self.url(route, detail)).status_code, 200)
        customer = create_customer(actor=self.superuser, full_name="Super", phone="0912345600")
        update_customer(actor=self.superuser, customer_id=customer.pk, full_name="Updated", phone=customer.phone)
        delete_customer(actor=self.superuser, customer_id=customer.pk)
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())

    def test_customers_permission_does_not_grant_personnel_access(self):
        for code in ("WAITER", "CASHIER"):
            self.client.force_login(self.users[code])
            self.assertEqual(self.client.get(reverse("employees:employee_list")).status_code, 403)
            self.assertEqual(self.client.get(reverse("accounts:account_list")).status_code, 403)

    def test_admin_customer_and_audit_are_readonly(self):
        self.client.force_login(self.superuser)
        for model, pk in (("customer", self.customer.pk), ("customeractivitylog", CustomerActivityLog.objects.first().pk)):
            url = reverse(f"admin:customers_{model}_change", args=[pk])
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.post(url, {"full_name": "Changed"}).status_code, 403)
            self.assertEqual(self.client.get(reverse(f"admin:customers_{model}_add")).status_code, 403)
            self.assertEqual(self.client.post(reverse(f"admin:customers_{model}_delete", args=[pk]), {"post": "yes"}).status_code, 403)

    def test_customer_name_is_escaped_in_ui(self):
        customer = create_customer(actor=self.superuser, full_name="<script>alert(1)</script>", phone="0912345600")
        self.client.force_login(self.superuser)
        response = self.client.get(customer.get_absolute_url())
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
