import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.orders.models import Order, QRCheckInRequest
from apps.orders.services import confirm_qr_check_in_request, create_qr_check_in_request, reject_qr_check_in_request
from apps.seating.models import Area, DiningTable, DiningTableQRToken


class CustomerQRCheckInTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="qr_checkin_manager", password="Test!123")
        cls.manager.groups.add(Group.objects.get(name="MANAGER"))
        cls.area = Area.objects.create(name="QR Check-in", is_active=True)
        cls.table = DiningTable.objects.create(code="CI01", area=cls.area, capacity=4, is_active=True)
        cls.token = DiningTableQRToken.objects.create(table=cls.table)

    def check_in_url(self):
        return reverse("customer_portal:qr_check_in", args=[self.token.token])

    def state_url(self):
        return reverse("customer_portal:qr_table_state", args=[self.token.token])

    def test_customer_request_waits_for_staff_and_is_idempotent(self):
        response = self.client.post(
            self.check_in_url(),
            data=json.dumps({"guest_count": 3}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        check_in = QRCheckInRequest.objects.get()
        self.assertEqual(check_in.guest_count, 3)
        self.assertEqual(check_in.status, QRCheckInRequest.Status.WAITING_CONFIRMATION)
        self.assertFalse(Order.objects.exists())
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.AVAILABLE)
        second = self.client.post(
            self.check_in_url(),
            data=json.dumps({"guest_count": 3}),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.json()["request_id"], check_in.pk)
        self.assertEqual(QRCheckInRequest.objects.count(), 1)
        state = self.client.get(self.state_url()).json()
        self.assertFalse(state["ready"])
        self.assertEqual(state["request"]["status"], QRCheckInRequest.Status.WAITING_CONFIRMATION)

    def test_guest_count_cannot_exceed_table_capacity(self):
        response = self.client.post(
            self.check_in_url(),
            data=json.dumps({"guest_count": 5}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sức chứa", response.json()["error"])
        self.assertFalse(QRCheckInRequest.objects.exists())

    def test_staff_confirmation_opens_table_and_customer_state(self):
        check_in = create_qr_check_in_request(token=self.token.token, guest_count=2)
        session = self.client.session
        session["qr_check_in_request_ids"] = [str(check_in.pk)]
        session.save()

        confirmed = confirm_qr_check_in_request(actor=self.manager, request_id=check_in.pk)

        self.table.refresh_from_db()
        self.assertEqual(self.table.status, DiningTable.Status.OCCUPIED)
        self.assertEqual(confirmed.status, QRCheckInRequest.Status.CONFIRMED)
        self.assertIsNotNone(confirmed.order_id)
        self.assertEqual(confirmed.order.status, Order.Status.OPEN)
        self.assertEqual(confirmed.order.guest_count, 2)
        self.assertTrue(self.client.get(self.state_url()).json()["ready"])
        menu = self.client.get(reverse("customer_portal:qr_table", args=[self.token.token]))
        self.assertContains(menu, "Gửi yêu cầu gọi món")

    def test_staff_can_reject_with_reason(self):
        check_in = create_qr_check_in_request(token=self.token.token, guest_count=1)

        rejected = reject_qr_check_in_request(
            actor=self.manager,
            request_id=check_in.pk,
            reason="Bàn đang được vệ sinh.",
        )

        self.assertEqual(rejected.status, QRCheckInRequest.Status.REJECTED)
        self.assertEqual(rejected.reject_reason, "Bàn đang được vệ sinh.")
        self.assertFalse(Order.objects.exists())

    def test_staff_action_requires_permission_and_confirm_redirects_to_order(self):
        check_in = create_qr_check_in_request(token=self.token.token, guest_count=2)
        action_url = reverse("sales:qr_check_in_action", args=[check_in.pk, "confirm"])
        self.assertEqual(self.client.post(action_url).status_code, 302)
        check_in.refresh_from_db()
        self.assertEqual(check_in.status, QRCheckInRequest.Status.WAITING_CONFIRMATION)

        self.client.force_login(self.manager)
        response = self.client.post(action_url)
        check_in.refresh_from_db()
        self.assertRedirects(
            response,
            f'{reverse("sales:workspace")}?order={check_in.order_id}#sales-order',
            fetch_redirect_response=False,
        )
