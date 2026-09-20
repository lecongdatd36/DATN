from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.seating.forms import AreaForm, DiningTableForm
from apps.seating.models import Area, DiningTable, SeatingActivityLog
from apps.seating.selectors import tables
from apps.seating.services import save_area, save_table


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SeatingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("MANAGER", "WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            actor = get_user_model().objects.create_user(username=role.lower(), password="Secret!Test123", is_staff=role == "MANAGER")
            actor.groups.add(Group.objects.get(name=role))
            cls.users[role] = actor
        cls.manager = cls.users["MANAGER"]
        cls.superuser = get_user_model().objects.create_superuser(username="root", password="Secret!Test123")
        cls.area = save_area(actor=cls.manager, name="Tầng 1", is_active=True)
        cls.table = save_table(actor=cls.manager, code="B01", area_id=cls.area.pk, capacity=4, is_active=True)

    def route(self, name, pk=None):
        return reverse(f"seating:{name}", args=[pk] if pk is not None else None)

    def test_role_matrix_and_visible_controls(self):
        for role, actor in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(actor)
                allowed = role in ("MANAGER", "WAITER", "CASHIER")
                for route in ("area_list", "table_list"):
                    response = self.client.get(self.route(route))
                    self.assertEqual(response.status_code, 200 if allowed else 403)
                    if allowed:
                        if role == "MANAGER":
                            self.assertContains(response, "Sửa / trạng thái")
                        else:
                            self.assertNotContains(response, "Sửa / trạng thái")
                            self.assertNotContains(response, self.route("logs"))
                self.assertEqual(self.client.get(self.route("logs")).status_code, 200 if role == "MANAGER" else 403)

    def test_nonmanagers_cannot_get_or_post_management_routes(self):
        for role in ("WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            self.client.force_login(self.users[role])
            for name, pk in (("area_create", None), ("area_update", self.area.pk), ("table_create", None), ("table_update", self.table.pk)):
                with self.subTest(role=role, route=name):
                    self.assertEqual(self.client.get(self.route(name, pk)).status_code, 403)
                    self.assertEqual(self.client.post(self.route(name, pk), {"name": "Changed"}).status_code, 403)
        self.assertEqual(SeatingActivityLog.objects.count(), 2)

    def test_manager_create_edit_and_deactivate_from_ui(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.route("area_create"), {"name": "  Phòng   riêng  ", "is_active": "on"})
        self.assertRedirects(response, self.route("area_list"))
        area = Area.objects.get(name="Phòng riêng")
        response = self.client.post(self.route("table_create"), {"code": " vip-01 ", "area": area.pk, "capacity": 8, "is_active": "on"})
        self.assertRedirects(response, self.route("table_list"))
        table = DiningTable.objects.get(code="VIP-01")
        self.assertTrue(table.is_available)
        response = self.client.post(self.route("table_update", table.pk), {"code": "VIP-01", "area": area.pk, "capacity": 10})
        self.assertRedirects(response, self.route("table_list"))
        table.refresh_from_db()
        self.assertFalse(table.is_active)
        self.assertEqual(table.capacity, 10)
        self.assertContains(self.client.get(self.route("logs")), "Phòng riêng")

    def test_superuser_without_profile_can_manage(self):
        self.client.force_login(self.superuser)
        for name, pk in (("area_create", None), ("area_update", self.area.pk), ("table_create", None), ("table_update", self.table.pk), ("logs", None)):
            self.assertEqual(self.client.get(self.route(name, pk)).status_code, 200)
        save_area(actor=self.superuser, area_id=self.area.pk, name="Tầng một", is_active=True)
        save_table(actor=self.superuser, table_id=self.table.pk, code="B01", area_id=self.area.pk, capacity=6, is_active=True)
        self.table.refresh_from_db()
        self.assertEqual(self.table.capacity, 6)

    def test_services_recheck_permissions_and_inactive_account(self):
        for role in ("WAITER", "CASHIER", "KITCHEN", "INVENTORY"):
            with self.assertRaises(PermissionDenied):
                save_area(actor=self.users[role], name="Bad", is_active=True)
            with self.assertRaises(PermissionDenied):
                save_table(actor=self.users[role], code="BAD", area_id=self.area.pk, capacity=4, is_active=True)
        self.assertTrue(self.manager.has_perm("seating.manage_seating"))
        self.manager.groups.clear()
        with self.assertRaises(PermissionDenied):
            save_area(actor=self.manager, name="Bad", is_active=True)
        get_user_model().objects.filter(pk=self.superuser.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            save_area(actor=self.superuser, name="Bad", is_active=True)

    def test_area_shutdown_and_reopen_preserves_individual_table_settings(self):
        off = save_table(actor=self.manager, code="B02", area_id=self.area.pk, capacity=4, is_active=False)
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)
        self.assertFalse(tables(status="active").exists())
        self.assertEqual(tables(status="inactive").count(), 2)
        self.assertFalse(DiningTable.objects.select_related("area").get(pk=self.table.pk).is_available)
        self.assertTrue(DiningTable.objects.get(pk=self.table.pk).is_active)
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=True)
        self.assertTrue(DiningTable.objects.select_related("area").get(pk=self.table.pk).is_available)
        self.assertFalse(DiningTable.objects.select_related("area").get(pk=off.pk).is_available)

    def test_cannot_create_transfer_or_enable_table_in_closed_area(self):
        closed = save_area(actor=self.manager, name="Đóng", is_active=False)
        for table_id in (None, self.table.pk):
            with self.assertRaises(ValidationError) as caught:
                save_table(actor=self.manager, table_id=table_id, code="B03", area_id=closed.pk, capacity=4, is_active=True)
            self.assertIn("area", caught.exception.message_dict)
        save_table(actor=self.manager, table_id=self.table.pk, code="B01", area_id=self.area.pk, capacity=4, is_active=False)
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)
        with self.assertRaises(ValidationError):
            save_table(actor=self.manager, table_id=self.table.pk, code="B01", area_id=self.area.pk, capacity=4, is_active=True)

    def test_existing_table_in_closed_area_can_be_corrected_or_moved_out(self):
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)
        edited = save_table(actor=self.manager, table_id=self.table.pk, code="B01", area_id=self.area.pk, capacity=6, is_active=True)
        self.assertFalse(edited.is_available)
        new_area = save_area(actor=self.manager, name="Tầng 2", is_active=True)
        moved = save_table(actor=self.manager, table_id=self.table.pk, code="B01", area_id=new_area.pk, capacity=6, is_active=True)
        self.assertTrue(moved.is_available)

    def test_form_area_choices_include_only_open_and_current_area(self):
        closed = save_area(actor=self.manager, name="Đóng", is_active=False)
        self.assertNotIn(closed, DiningTableForm().fields["area"].queryset)
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)
        self.table.refresh_from_db()
        self.assertIn(self.area, DiningTableForm(instance=self.table).fields["area"].queryset)

    def test_normalized_unique_names_and_codes(self):
        with self.assertRaises(ValidationError):
            save_area(actor=self.manager, name=" tầng   1 ", is_active=True)
        with self.assertRaises(ValidationError):
            save_table(actor=self.manager, code=" b01 ", area_id=self.area.pk, capacity=2, is_active=True)
        area_form = AreaForm(data={"name": "tầng 1", "is_active": True})
        self.assertFalse(area_form.is_valid())
        table_form = DiningTableForm(data={"code": "b01", "area": self.area.pk, "capacity": 4, "is_active": True})
        self.assertFalse(table_form.is_valid())
        self.assertIn("code", table_form.errors)

    def test_validation_rejects_invalid_capacity_code_and_empty_name(self):
        for capacity in (0, -1, 101, "not-number", None):
            with self.subTest(capacity=capacity), self.assertRaises(ValidationError):
                save_table(actor=self.manager, code="B02", area_id=self.area.pk, capacity=capacity, is_active=True)
        for code in ("", "B 02", "B/02", "<script>", "X" * 21):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                save_table(actor=self.manager, code=code, area_id=self.area.pk, capacity=4, is_active=True)
        with self.assertRaises(ValidationError):
            save_area(actor=self.manager, name="   ", is_active=True)

    def test_database_constraints_and_area_protection(self):
        for code, capacity in (("b02", 4), ("B02", 0), ("B02", 101), ("B01", 4)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                DiningTable.objects.create(code=code, capacity=capacity, area=self.area)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Area.objects.create(name="tầng 1")
        with self.assertRaises(ProtectedError):
            self.area.delete()

    def test_audit_failure_rolls_back_both_area_and_table(self):
        with patch("apps.seating.services._log", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                save_area(actor=self.manager, area_id=self.area.pk, name="Changed", is_active=False)
            with self.assertRaises(RuntimeError):
                save_table(actor=self.manager, code="B02", area_id=self.area.pk, capacity=4, is_active=True)
        self.area.refresh_from_db()
        self.assertTrue(self.area.is_active)
        self.assertEqual(self.area.name, "Tầng 1")
        self.assertEqual(DiningTable.objects.count(), 1)

    def test_unchanged_save_has_no_extra_log_and_actor_snapshot_survives(self):
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=True)
        save_table(actor=self.manager, table_id=self.table.pk, code="b01", area_id=self.area.pk, capacity=4, is_active=True)
        self.assertEqual(SeatingActivityLog.objects.count(), 2)
        self.manager.delete()
        self.assertTrue(all(log.performed_by_id is None and log.actor_snapshot == "manager" for log in SeatingActivityLog.objects.all()))

    def test_filters_pagination_and_closed_area_reason(self):
        self.client.force_login(self.manager)
        for i in range(21):
            DiningTable.objects.create(code=f"X{i:02d}", area=self.area, capacity=2)
        response = self.client.get(self.route("table_list"), {"q": "X", "area": self.area.pk, "page": 2})
        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(response.context["page_obj"]), 1)
        self.assertIn(f"area={self.area.pk}", response.context["query_string"])
        save_area(actor=self.manager, area_id=self.area.pk, name=self.area.name, is_active=False)
        self.assertContains(self.client.get(self.route("table_list"), {"status": "inactive"}), "Khu vực đã ngừng sử dụng")
        response = self.client.get(self.route("area_list"), {"q": "Tầng", "status": "inactive"})
        self.assertEqual(response.context["page_obj"][0].table_count, 22)
        self.assertFalse(self.client.get(self.route("table_list"), {"status": "active"}).context["page_obj"])

    def test_invalid_filter_form_error_and_missing_object(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.route("table_list"), {"area": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filter_form"].errors)
        self.assertEqual(self.client.get(self.route("table_update", 999999)).status_code, 404)
        response = self.client.post(self.route("table_update", self.table.pk), {"code": "B01", "area": self.area.pk, "capacity": 0})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "B01")
        self.assertTrue(response.context["form"].errors)

    def test_anonymous_csrf_get_safety_and_no_delete_endpoint(self):
        self.assertEqual(self.client.get(self.route("table_list")).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        for name, pk in (("area_create", None), ("area_update", self.area.pk), ("table_create", None), ("table_update", self.table.pk)):
            self.assertEqual(client.get(self.route(name, pk)).status_code, 200)
            self.assertEqual(client.post(self.route(name, pk), {}).status_code, 403)
        self.assertEqual(SeatingActivityLog.objects.count(), 2)
        self.assertEqual(client.delete(self.route("table_update", self.table.pk)).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.delete(self.route("table_update", self.table.pk)).status_code, 405)
        self.assertEqual(self.client.post(f"/ban/{self.table.pk}/xoa/").status_code, 404)

    def test_admin_is_readonly_for_superuser(self):
        self.client.force_login(self.superuser)
        for model, pk in (("area", self.area.pk), ("diningtable", self.table.pk), ("seatingactivitylog", SeatingActivityLog.objects.first().pk)):
            url = reverse(f"admin:seating_{model}_change", args=[pk])
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
            self.assertEqual(self.client.get(reverse(f"admin:seating_{model}_add")).status_code, 403)
            self.assertEqual(self.client.post(reverse(f"admin:seating_{model}_delete", args=[pk]), {"post": "yes"}).status_code, 403)
