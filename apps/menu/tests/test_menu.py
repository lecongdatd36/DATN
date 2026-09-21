from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.admin import admin_site
from apps.menu.models import Category, Unit, Dish, MenuActivityLog
from apps.menu.services import save_catalog, save_dish, change_availability
from apps.menu.selectors import dishes


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MenuTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            actor = get_user_model().objects.create_user(username=role.lower(), password="Test!123", is_staff=role == "MANAGER")
            actor.groups.add(Group.objects.get(name=role))
            cls.users[role] = actor
        cls.manager = cls.users["MANAGER"]
        cls.superuser = get_user_model().objects.create_superuser(username="root", password="Test!123")
        cls.category = save_catalog(actor=cls.manager, kind="category", name="Món chính", is_active=True)
        cls.unit = save_catalog(actor=cls.manager, kind="unit", name="Đĩa", is_active=True)
        cls.dish = save_dish(actor=cls.manager, code="M001", name="Cơm chiên", category_id=cls.category.pk,
                            unit_id=cls.unit.pk, price=85000, status="AVAILABLE")

    def url(self, name, pk=None):
        return reverse(f"menu:{name}", args=[pk] if pk is not None else None)

    def dish_data(self, **overrides):
        data = dict(code=self.dish.code, name=self.dish.name, category=self.category.pk, unit=self.unit.pk,
                    price="85000", status="AVAILABLE", description="", expected_revision=self.dish.revision)
        data.update(overrides)
        return data

    def save(self, **overrides):
        data = dict(actor=self.manager, dish_id=self.dish.pk, code=self.dish.code, name=self.dish.name,
                    category_id=self.category.pk, unit_id=self.unit.pk, price=85000, status="AVAILABLE",
                    expected_revision=self.dish.revision)
        data.update(overrides)
        return save_dish(**data)

    def test_role_matrix_and_menu_controls(self):
        for role, actor in self.users.items():
            self.client.force_login(actor)
            allowed = role != "INVENTORY"
            response = self.client.get(self.url("dish_list"))
            self.assertEqual(response.status_code, 200 if allowed else 403)
            self.assertEqual(self.client.get(self.dish.get_absolute_url()).status_code, 200 if allowed else 403)
            self.assertEqual(self.client.get(self.url("logs")).status_code, 200 if role == "MANAGER" else 403)
            if allowed:
                self.assertContains(response, "Cơm chiên")
                self.assertContains(response, "85.000")
                self.assertEqual(self.url("dish_update", self.dish.pk) in response.content.decode(), role == "MANAGER")
                self.assertEqual(self.url("availability", self.dish.pk) in response.content.decode(), role in ("MANAGER", "KITCHEN"))
            workspace = self.client.get(reverse("accounts:workspace"))
            self.assertEqual(self.url("dish_list") in workspace.content.decode(), allowed)

    def test_management_get_and_post_forbidden_to_other_roles(self):
        for role in ("WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            self.client.force_login(self.users[role])
            with self.assertRaises(PermissionDenied):
                self.save(actor=self.users[role])
            with self.assertRaises(PermissionDenied):
                save_catalog(actor=self.users[role], kind="unit", name="Bad", is_active=True)
            for name, pk in (("dish_create", None), ("dish_update", self.dish.pk), ("category_create", None),
                             ("category_update", self.category.pk), ("unit_create", None), ("unit_update", self.unit.pk),
                             ("category_list", None), ("unit_list", None)):
                self.assertEqual(self.client.get(self.url(name, pk)).status_code, 403)
                self.assertEqual(self.client.post(self.url(name, pk), self.dish_data()).status_code, 403)
        self.assertEqual(MenuActivityLog.objects.count(), 3)

    def test_anonymous_staff_flag_and_inactive_users_have_no_access(self):
        self.assertEqual(self.client.get(self.url("dish_list")).status_code, 302)
        actor = get_user_model().objects.create_user(username="staff_only", is_staff=True)
        self.client.force_login(actor)
        self.assertEqual(self.client.get(self.url("dish_list")).status_code, 403)
        for user in (AnonymousUser(), actor):
            with self.assertRaises(PermissionDenied):
                self.save(actor=user)
        get_user_model().objects.filter(pk=self.manager.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.save()

    def test_superuser_without_employee_can_manage(self):
        self.client.force_login(self.superuser)
        for name in ("dish_list", "dish_create", "category_list", "unit_list", "logs"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 200)
        changed = self.save(actor=self.superuser, price=90000)
        self.assertEqual(changed.price, Decimal("90000"))

    def test_create_and_edit_through_ui(self):
        self.client.force_login(self.manager)
        self.assertRedirects(self.client.post(self.url("category_create"), {"name": "  Đồ   uống ", "is_active": "on"}), self.url("category_list"))
        self.assertRedirects(self.client.post(self.url("unit_create"), {"name": "Ly", "is_active": "on"}), self.url("unit_list"))
        response = self.client.post(self.url("dish_create"), self.dish_data(code=" nuoc-01 ", name="  Nước   cam ",
            category=Category.objects.get(name="Đồ uống").pk, unit=Unit.objects.get(name="Ly").pk, price="45000", expected_revision=""))
        dish = Dish.objects.get(code="NUOC-01")
        self.assertRedirects(response, dish.get_absolute_url())
        self.assertEqual(dish.name, "Nước cam")
        response = self.client.post(self.url("dish_update", self.dish.pk), self.dish_data(price="95000", status="INACTIVE"))
        self.assertRedirects(response, self.dish.get_absolute_url())
        self.dish.refresh_from_db()
        self.assertEqual(self.dish.price, Decimal("95000"))
        self.assertFalse(self.dish.is_orderable)
        self.assertContains(self.client.get(self.url("logs")), "85000")
        self.assertContains(self.client.get(self.url("logs")), "95000")

    def test_kitchen_can_only_change_availability_even_with_extra_post_fields(self):
        self.client.force_login(self.users["KITCHEN"])
        self.assertContains(self.client.get(self.url("availability", self.dish.pk)), "Cập nhật còn / hết món")
        response = self.client.post(self.url("availability", self.dish.pk), self.dish_data(status="SOLD_OUT", price="1", name="Tampered"))
        self.assertRedirects(response, self.dish.get_absolute_url())
        self.dish.refresh_from_db()
        self.assertEqual(self.dish.price, 85000)
        self.assertEqual(self.dish.name, "Cơm chiên")
        self.assertEqual(self.dish.status, "SOLD_OUT")
        change_availability(actor=self.users["KITCHEN"], dish_id=self.dish.pk, status="AVAILABLE", expected_revision=self.dish.revision)
        self.dish.refresh_from_db()
        self.assertTrue(self.dish.is_orderable)

    def test_status_endpoint_rejects_unauthorized_and_stopped_dishes(self):
        for role in ("WAITER", "CASHIER", "INVENTORY"):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.post(self.url("availability", self.dish.pk), self.dish_data()).status_code, 403)
            with self.assertRaises(PermissionDenied):
                change_availability(actor=self.users[role], dish_id=self.dish.pk, status="SOLD_OUT", expected_revision=1)
        for status in ("INACTIVE", "INVALID"):
            with self.assertRaises(ValidationError):
                change_availability(actor=self.users["KITCHEN"], dish_id=self.dish.pk, status=status, expected_revision=1)
        dish = self.save(status="INACTIVE")
        with self.assertRaises(ValidationError):
            change_availability(actor=self.users["KITCHEN"], dish_id=dish.pk, status="AVAILABLE", expected_revision=dish.revision)

    def test_permissions_rechecked_after_cached_user_loses_role(self):
        self.assertTrue(self.manager.has_perm("menu.manage_menu"))
        self.manager.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.save()
        kitchen = self.users["KITCHEN"]
        self.assertTrue(kitchen.has_perm("menu.change_availability"))
        kitchen.groups.clear()
        with self.assertRaises(PermissionDenied):
            change_availability(actor=kitchen, dish_id=self.dish.pk, status="SOLD_OUT", expected_revision=1)

    def test_name_and_code_validation_and_duplicates(self):
        for kind in ("category", "unit"):
            obj = self.category if kind == "category" else self.unit
            with self.assertRaises(ValidationError):
                save_catalog(actor=self.manager, kind=kind, name=obj.name.upper(), is_active=True)
            with self.assertRaises(ValidationError):
                save_catalog(actor=self.manager, kind=kind, name=" \t ", is_active=True)
        for field, value in (("code", "bad code"), ("name", "  "), ("description", "a" * 2001), ("status", "BAD")):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.save(**{field: value})
        with self.assertRaises(ValidationError):
            self.save(dish_id=None, code="m001")

    def test_price_validation_at_form_service_and_database(self):
        self.client.force_login(self.manager)
        for value in ("0", "-1", "1.5", "1000000000", "NaN", "Infinity", "abc"):
            with self.subTest(value=value):
                self.assertEqual(self.client.post(self.url("dish_update", self.dish.pk), self.dish_data(price=value)).status_code, 200)
                with self.assertRaises(ValidationError):
                    self.save(price=value)
        self.dish.refresh_from_db()
        self.assertEqual(self.dish.price, 85000)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Dish.objects.filter(pk=self.dish.pk).update(price=0)

    def test_catalog_shutdown_and_reopen_preserve_individual_status(self):
        self.save(status="SOLD_OUT")
        category = save_catalog(actor=self.manager, kind="category", object_id=self.category.pk, name=self.category.name, is_active=False, expected_revision=1)
        dish = dishes().get(pk=self.dish.pk)
        self.assertEqual(dish.availability_label, "Tạm ngừng theo danh mục")
        self.assertFalse(dish.is_orderable)
        self.assertFalse(dishes(status="SOLD_OUT").exists())
        self.assertEqual(dishes(status="paused").count(), 1)
        with self.assertRaises(ValidationError):
            change_availability(actor=self.users["KITCHEN"], dish_id=dish.pk, status="AVAILABLE", expected_revision=dish.revision)
        save_catalog(actor=self.manager, kind="category", object_id=category.pk, name=category.name, is_active=True, expected_revision=category.revision)
        dish = dishes().get(pk=dish.pk)
        self.assertEqual(dish.availability_label, "Hết món")

    def test_inactive_catalog_cannot_receive_new_dishes_or_reactivation(self):
        self.save(status="INACTIVE")
        self.dish.refresh_from_db()
        for kind, obj in (("category", self.category), ("unit", self.unit)):
            save_catalog(actor=self.manager, kind=kind, object_id=obj.pk, name=obj.name, is_active=False, expected_revision=1)
            with self.assertRaises(ValidationError):
                self.save(dish_id=None, code="NEW")
            with self.assertRaises(ValidationError):
                self.save(status="AVAILABLE")

    def test_editing_dish_under_inactive_catalog_keeps_paused_status(self):
        Category.objects.filter(pk=self.category.pk).update(is_active=False)
        dish = self.save(price=90000)
        self.assertEqual(dish.price, 90000)
        self.assertFalse(dish.is_orderable)
        other = Category.objects.create(name="Ngừng", is_active=False)
        with self.assertRaises(ValidationError):
            self.save(category_id=other.pk, expected_revision=dish.revision)

    def test_stale_forms_cannot_overwrite_price_status_or_catalog(self):
        self.client.force_login(self.manager)
        self.save(price=95000)
        response = self.client.post(self.url("dish_update", self.dish.pk), self.dish_data(price="1"))
        self.assertContains(response, "Dữ liệu đã thay đổi")
        with self.assertRaises(ValidationError):
            change_availability(actor=self.users["KITCHEN"], dish_id=self.dish.pk, status="SOLD_OUT", expected_revision=1)
        self.dish.refresh_from_db()
        self.assertEqual(self.dish.price, 95000)
        self.assertEqual(self.dish.status, "AVAILABLE")
        save_catalog(actor=self.manager, kind="unit", object_id=self.unit.pk, name="Phần", is_active=True, expected_revision=1)
        with self.assertRaises(ValidationError):
            save_catalog(actor=self.manager, kind="unit", object_id=self.unit.pk, name="Cũ", is_active=False, expected_revision=1)

    def test_missing_revision_is_rejected_on_edits(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(self.url("dish_update", self.dish.pk), self.dish_data(expected_revision="")).status_code, 200)
        with self.assertRaises(ValidationError):
            self.save(expected_revision=None)
        self.dish.refresh_from_db()
        self.assertEqual(self.dish.revision, 1)

    def test_noop_does_not_create_logs_or_change_revision(self):
        self.save()
        save_catalog(actor=self.manager, kind="unit", object_id=self.unit.pk, name=self.unit.name, is_active=True, expected_revision=1)
        change_availability(actor=self.users["KITCHEN"], dish_id=self.dish.pk, status="AVAILABLE", expected_revision=1)
        self.assertEqual(MenuActivityLog.objects.count(), 3)
        self.dish.refresh_from_db()
        self.assertEqual(self.dish.revision, 1)

    def test_audit_failure_rolls_back_all_types_of_changes(self):
        with patch("apps.menu.services._log", side_effect=RuntimeError("Log failure")):
            with self.assertRaises(RuntimeError):
                self.save(price=1)
            with self.assertRaises(RuntimeError):
                save_catalog(actor=self.manager, kind="unit", object_id=self.unit.pk, name="New", is_active=False, expected_revision=1)
            with self.assertRaises(RuntimeError):
                change_availability(actor=self.users["KITCHEN"], dish_id=self.dish.pk, status="SOLD_OUT", expected_revision=1)
        self.dish.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.dish.price, 85000)
        self.assertEqual(self.dish.status, "AVAILABLE")
        self.assertEqual(self.unit.name, "Đĩa")

    def test_search_filters_pagination_and_invalid_query(self):
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(self.url("dish_list"), {"q": "cơm", "category": self.category.pk, "unit": self.unit.pk, "status": "AVAILABLE"}), "Cơm chiên")
        self.assertNotContains(self.client.get(self.url("dish_list"), {"status": "SOLD_OUT"}), self.dish.get_absolute_url())
        self.assertContains(self.client.get(self.url("dish_list"), {"category": "invalid"}), "không có kết quả")
        Dish.objects.bulk_create([Dish(code=f"X{i}", name=f"Món {i:02}", category=self.category, unit=self.unit, price=1) for i in range(21)])
        response = self.client.get(self.url("dish_list"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 2)
        with self.assertNumQueries(1):
            for dish in dishes():
                str(dish.category)
                str(dish.unit)
                dish.is_orderable

    def test_csrf_and_get_do_not_change_data(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        response = client.get(self.url("dish_update", self.dish.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertEqual(client.post(self.url("dish_update", self.dish.pk), self.dish_data()).status_code, 403)
        self.assertEqual(client.post(self.url("availability", self.dish.pk), self.dish_data()).status_code, 403)
        self.assertEqual(MenuActivityLog.objects.count(), 3)

    def test_protected_catalog_and_log_actor_snapshot(self):
        for obj in (self.category, self.unit):
            with self.assertRaises(ProtectedError):
                obj.delete()
        self.manager.delete()
        self.assertEqual(MenuActivityLog.objects.filter(performed_by__isnull=True, actor_snapshot="manager").count(), 3)

    def test_admin_is_read_only_even_for_superuser(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superuser
        for model in (Category, Unit, Dish, MenuActivityLog):
            admin = admin_site._registry[model]
            self.assertTrue(admin.has_view_permission(request))
            self.assertFalse(admin.has_add_permission(request))
            self.assertFalse(admin.has_change_permission(request))
            self.assertFalse(admin.has_delete_permission(request))
            self.assertEqual(admin.get_actions(request), {})
            with self.assertRaises(PermissionDenied):
                admin.save_model(request, model(), None, False)

    def test_template_escapes_user_content_and_missing_objects(self):
        self.save(name="<script>alert(1)</script>", description="<img src=x onerror=alert(1)>")
        self.client.force_login(self.manager)
        response = self.client.get(self.dish.get_absolute_url())
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
        self.assertEqual(self.client.get(self.url("detail", 999999)).status_code, 404)
        self.assertEqual(self.client.get(self.url("dish_update", 999999)).status_code, 404)
        with self.assertRaises(ValidationError):
            self.save(category_id=999999, expected_revision=2)

    def test_catalog_forms_edit_deactivate_filter_and_reject_stale_submission(self):
        self.client.force_login(self.manager)
        for kind, obj in (("category", self.category), ("unit", self.unit)):
            for route, pk in ((f"{kind}_create", None), (f"{kind}_update", obj.pk)):
                self.assertEqual(self.client.get(self.url(route, pk)).status_code, 200)
            self.assertRedirects(self.client.post(self.url(f"{kind}_update", obj.pk), {"name": obj.name, "expected_revision": 1}), self.url(f"{kind}_list"))
            self.assertContains(self.client.get(self.url(f"{kind}_list"), {"status": "inactive", "q": obj.name}), obj.name)
            response = self.client.post(self.url(f"{kind}_update", obj.pk), {"name": "Old form", "is_active": "on", "expected_revision": 1})
            self.assertContains(response, "Dữ liệu đã thay đổi")
            obj.refresh_from_db()
            self.assertFalse(obj.is_active)
            self.assertEqual(obj.revision, 2)

    def test_database_rejects_duplicate_catalog_and_invalid_dish_fields(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.create(name=self.category.name.upper())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Unit.objects.create(name="   ")
        for field, value in (("name", "  "), ("status", "BAD"), ("code", "lowercase")):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                Dish.objects.filter(pk=self.dish.pk).update(**{field: value})
