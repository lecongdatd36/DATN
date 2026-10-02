from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.seating.models import DiningTableQRToken
from apps.seating.services import save_table


class TableQRManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="qr_manager", password="Test!123", is_staff=True)
        cls.manager.groups.add(Group.objects.get(name="MANAGER"))
        from apps.seating.models import Area
        cls.area = Area.objects.create(name="QR Area", is_active=True)
        cls.table = save_table(actor=cls.manager, code="QR01", area_id=cls.area.pk, capacity=4, is_active=True)

    def test_staff_can_view_printable_qr_page(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("seating:table_qr"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bàn QR01")
        self.assertContains(response, "data:image/png;base64,")
        self.assertEqual(DiningTableQRToken.objects.filter(table=self.table).count(), 1)

    def test_anonymous_cannot_view_staff_qr_page(self):
        response = self.client.get(reverse("seating:table_qr"))
        self.assertEqual(response.status_code, 302)

    def test_new_table_gets_one_token(self):
        self.assertEqual(DiningTableQRToken.objects.filter(table=self.table).count(), 1)
        save_table(actor=self.manager, table_id=self.table.pk, code="QR01", area_id=self.area.pk, capacity=4, is_active=True)
        self.assertEqual(DiningTableQRToken.objects.filter(table=self.table).count(), 1)