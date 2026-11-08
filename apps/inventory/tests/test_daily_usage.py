from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import Ingredient, InventoryTransaction
from apps.inventory.selectors import daily_ingredient_usage


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DailyUsageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="daily-inventory")
        cls.user.groups.add(Group.objects.get(name="INVENTORY"))
        cls.rice = Ingredient.objects.create(code="RICE", name="Gạo", unit="kg", is_active=False)
        cls.day = timezone.localdate()
        cls.start = timezone.make_aware(datetime.combine(cls.day, time.min))

    def entry(self, kind, quantity, at=None, ingredient=None):
        entry = InventoryTransaction.objects.create(ingredient=ingredient or self.rice, transaction_type=kind,
                                                    quantity=quantity, stock_before=100, stock_after=90)
        InventoryTransaction.objects.filter(pk=entry.pk).update(created_at=at or self.start + timedelta(hours=12))
        return entry

    def test_aggregates_all_entries_with_returns_and_waste_separate(self):
        for _ in range(35):
            self.entry("SALE_USAGE", 1)
        self.entry("EXPORT", 2)
        self.entry("SALE_RETURN", 3)
        self.entry("WASTE", Decimal("0.5"))
        self.entry("IMPORT", 80)
        self.entry("STOCKTAKE", 60)
        report = daily_ingredient_usage(day=self.day)
        row = report["usage_rows"][0]
        self.assertEqual(row["used_quantity"], Decimal(34))
        self.assertEqual(row["waste_quantity"], Decimal("0.5"))
        self.assertEqual(report["used_ingredient_count"], 1)
        self.assertEqual(report["usage_transaction_count"], 38)
        self.client.force_login(self.user)
        response = self.client.get(reverse("inventory:daily_usage"))
        self.assertContains(response, "Gạo")
        self.assertEqual(response.context["page_obj"].paginator.count, 38)
        self.assertEqual(len(response.context["page_obj"]), 25)

    def test_vietnam_day_boundaries_and_other_units(self):
        self.entry("EXPORT", 1, self.start - timedelta(microseconds=1))
        self.entry("EXPORT", 2, self.start)
        self.entry("EXPORT", 3, self.start + timedelta(days=1) - timedelta(microseconds=1))
        self.entry("EXPORT", 4, self.start + timedelta(days=1))
        eggs = Ingredient.objects.create(code="EGGS", name="Trứng", unit="quả")
        self.entry("SALE_USAGE", 10, ingredient=eggs)
        rows = daily_ingredient_usage(day=self.day)["usage_rows"]
        self.assertEqual(rows[0]["used_quantity"], Decimal(5))
        self.assertEqual(rows[1]["used_quantity"], Decimal(10))
        self.assertEqual(rows[1]["ingredient__unit"], "quả")

    def test_return_only_is_shown_as_negative_net(self):
        self.entry("SALE_RETURN", 2)
        report = daily_ingredient_usage(day=self.day)
        self.assertEqual(report["usage_rows"][0]["used_quantity"], Decimal(-2))
        self.assertEqual(report["used_ingredient_count"], 0)

    def test_empty_state_permissions_and_no_writes(self):
        url = reverse("inventory:daily_usage")
        self.assertEqual(self.client.get(url).status_code, 302)
        denied = get_user_model().objects.create_user(username="daily-denied")
        denied.groups.add(Group.objects.get(name="WAITER"))
        self.client.force_login(denied)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), "Hôm nay chưa có giao dịch")
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(InventoryTransaction.objects.count(), 0)
