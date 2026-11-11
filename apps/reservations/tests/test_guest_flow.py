from uuid import uuid4

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.menu.models import Dish
from apps.reservations.models import Reservation
from .test_reservations import ReservationTests


class GuestReservationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ReservationTests.setUpTestData.__func__(cls)

    def details(self, mode="TABLE", next_step="menu", flow=None):
        flow = flow or ("table" if mode == "TABLE" and next_step == "review" else "preorder")
        response = self.client.post(reverse("online_reservations:create"), {
            "step": "details", "next_step": next_step, "request_key": str(uuid4()),
            "full_name": "Khách đặt bàn", "phone": "0912345688",
            "starts_at": self.arrival.strftime("%Y-%m-%dT%H:%M"),
            "party_size": "4", "duration_minutes": "120", "mode": mode,
            "area": str(self.area.pk), "note": "Ghế trẻ em",
        })
        if response.status_code == 302:
            return self.client.post(reverse("online_reservations:choice"), {
                "decision": "no" if flow == "table" else "yes", "mode": mode,
            })
        return response

    def test_booking_page_has_photo_and_no_dish_inputs(self):
        response = self.client.get(reverse("online_reservations:create"))
        self.assertContains(response, "or-booking-photo")
        self.assertNotContains(response, 'name="mode"')
        self.assertNotContains(response, "Tiếp tục chọn món")
        self.assertNotContains(response, 'name="qty_')
        self.assertNotContains(response, 'data-preorder-cart')
        self.assertContains(response, 'name="full_name"')
        self.assertNotContains(response, 'data-booking-choice')

    def test_homepage_shortcut_prefills_without_creating_or_holding_a_reservation(self):
        arrival=timezone.localtime(self.arrival)
        response=self.client.get(reverse("online_reservations:create"),{
            "booking_date":arrival.strftime("%Y-%m-%d"),"booking_time":arrival.strftime("%H:%M"),"party_size":"6"})
        self.assertEqual(response.context["form"].initial["starts_at"],self.arrival)
        self.assertEqual(response.context["form"].initial["party_size"],6)
        self.assertFalse(response.context["form"].is_bound)
        self.assertFalse(Reservation.objects.exists())
        self.assertFalse(self.client.session.get("reservation_draft"))

    def test_homepage_shortcut_ignores_invalid_values_and_preserves_saved_details(self):
        session=self.client.session
        session["reservation_draft"]={"details":{"party_size":"4","full_name":"Tên đã nhập"}}
        session.save()
        response=self.client.get(reverse("online_reservations:create"),{
            "booking_date":"invalid","booking_time":"25:99","party_size":"9999","mode":"READY"})
        form=response.context["form"]
        self.assertEqual(form.initial["party_size"],"4")
        self.assertEqual(form.initial["full_name"],"Tên đã nhập")
        self.assertNotIn("starts_at",form.initial)
        self.assertNotIn("mode",form.fields)
        self.assertFalse(Reservation.objects.exists())

    def test_booking_details_are_required_before_the_preorder_question(self):
        self.assertRedirects(self.client.get(reverse("online_reservations:choice")), reverse("online_reservations:create"))
        response = self.client.post(reverse("online_reservations:create"), {
            "step": "details", "request_key": str(uuid4()), "full_name": "Khách đặt bàn",
            "phone": "0912345688", "starts_at": self.arrival.strftime("%Y-%m-%dT%H:%M"),
            "party_size": "4", "duration_minutes": "120",
        })
        self.assertRedirects(response, reverse("online_reservations:choice"))
        response = self.client.get(reverse("online_reservations:choice"))
        self.assertContains(response, "Bạn có muốn đặt món trước không?")
        self.assertContains(response, 'name="decision" value="yes"')
        self.assertContains(response, 'name="decision" value="no"')
        for route in ("menu", "review"):
            self.assertRedirects(self.client.get(reverse("online_reservations:" + route)), reverse("online_reservations:choice"))
        self.assertFalse(Reservation.objects.exists())

    def test_old_flow_bookmarks_redirect_to_the_same_booking_form(self):
        for route in ("table", "preorder"):
            self.assertRedirects(self.client.get(reverse("online_reservations:" + route)), reverse("online_reservations:create"))

    def test_table_flow_never_shows_or_submits_cart_or_preparation_mode(self):
        self.assertRedirects(self.details(mode="READY", flow="table"), reverse("online_reservations:review"))
        session = self.client.session
        draft = session["reservation_draft"]
        draft["details"]["mode"] = "READY"
        draft["cart"] = {f"qty_{self.dish.pk}": "4"}
        session["reservation_draft"] = draft
        session.save()
        response = self.client.get(reverse("online_reservations:review"))
        self.assertNotContains(response, "Giỏ món")
        self.assertNotContains(response, "Cách chuẩn bị")
        self.assertNotContains(response, reverse("online_reservations:menu"))
        self.assertEqual(response.context["details"]["mode"], "TABLE")
        self.assertRedirects(self.client.post(reverse("online_reservations:menu"), {f"qty_{self.dish.pk}": "3"}), reverse("online_reservations:review"))
        self.client.post(reverse("online_reservations:review"), {"agree": "on", "mode": "READY", f"qty_{self.dish.pk}": "3"})
        row = Reservation.objects.get()
        self.assertEqual(row.mode, "TABLE")
        self.assertFalse(row.items.exists())

    def test_preorder_requires_items_even_when_cooking_on_arrival(self):
        self.details()
        response = self.client.post(reverse("online_reservations:menu"), {})
        self.assertContains(response, "Vui lòng chọn ít nhất một món để đặt món trước")
        self.assertRedirects(self.client.get(reverse("online_reservations:review")), reverse("online_reservations:menu"))
        self.assertFalse(Reservation.objects.exists())

    def test_details_cart_review_only_create_after_explicit_consent(self):
        self.assertRedirects(self.details(), reverse("online_reservations:menu"))
        response = self.client.get(reverse("online_reservations:menu"))
        self.assertContains(response, "or-product-photo")
        self.assertContains(response, "Giỏ món của bạn")
        self.assertNotContains(response, 'name="full_name"')
        self.assertRedirects(self.client.post(reverse("online_reservations:menu"), {
            f"qty_{self.dish.pk}": "2", f"note_{self.dish.pk}": "Ít cay", "action": "review",
        }), reverse("online_reservations:review"))
        response = self.client.get(reverse("online_reservations:review"))
        self.assertEqual(response.context["total"], 400000)
        self.assertContains(response, "Ít cay")
        self.assertFalse(response.context["agree_checked"])
        self.assertFalse(Reservation.objects.exists())
        self.client.post(reverse("online_reservations:review"), {})
        self.assertFalse(Reservation.objects.exists())
        response = self.client.post(reverse("online_reservations:review"), {"agree": "on"})
        row = Reservation.objects.get()
        self.assertRedirects(response, reverse("online_reservations:detail", args=[row.access_token]))
        self.assertEqual(row.items.get().quantity, 2)
        self.assertEqual(row.items.get().note, "Ít cay")
        self.assertNotIn("reservation_draft", self.client.session)
        self.client.post(reverse("online_reservations:review"), {"agree": "on"})
        self.assertEqual(Reservation.objects.count(), 1)

    def test_back_preserves_draft_and_table_only_clears_cart(self):
        self.details()
        self.assertRedirects(self.client.post(reverse("online_reservations:menu"), {
            "action": "back", f"qty_{self.dish.pk}": "3", f"note_{self.dish.pk}": "Không hành",
        }), reverse("online_reservations:create"))
        response = self.client.get(reverse("online_reservations:create"))
        self.assertEqual(response.context["form"]["full_name"].value(), "Khách đặt bàn")
        self.assertEqual(response.context["form"]["area"].value(), str(self.area.pk))
        self.details()
        response = self.client.get(reverse("online_reservations:menu"))
        self.assertEqual(response.context["form"][f"qty_{self.dish.pk}"].value(), "3")
        self.assertEqual(response.context["form"][f"note_{self.dish.pk}"].value(), "Không hành")
        self.assertRedirects(self.details(next_step="review"), reverse("online_reservations:review"))
        response = self.client.get(reverse("online_reservations:review"))
        self.assertEqual(response.context["selected_rows"], [])
        self.client.post(reverse("online_reservations:review"), {"agree": "on"})
        self.assertFalse(Reservation.objects.get().items.exists())

    def test_ready_requires_items_and_rejects_ineligible_or_sold_out(self):
        self.assertRedirects(self.details(mode="READY", next_step="review"), reverse("online_reservations:menu"))
        response = self.client.post(reverse("online_reservations:menu"), {})
        self.assertContains(response, "Vui lòng chọn ít nhất một món")
        other = Dish.objects.create(code="NOADVANCE", name="Chỉ làm khi đến", category=self.category,
            unit=self.unit, price=50000)
        response = self.client.post(reverse("online_reservations:menu"), {f"qty_{other.pk}": "1"})
        self.assertContains(response, "Món này chỉ chế biến khi khách đến")
        Dish.objects.filter(pk=self.dish.pk).update(status="SOLD_OUT")
        response = self.client.post(reverse("online_reservations:menu"), {f"qty_{self.dish.pk}": "1"})
        self.assertContains(response, "Món hiện đã hết")
        self.assertFalse(Reservation.objects.exists())

    def test_review_rechecks_live_menu_and_ignores_posted_price(self):
        self.details()
        self.client.post(reverse("online_reservations:menu"), {f"qty_{self.dish.pk}": "1"})
        Dish.objects.filter(pk=self.dish.pk).update(price=250000)
        response = self.client.get(reverse("online_reservations:review"))
        self.assertEqual(response.context["total"], 250000)
        self.client.post(reverse("online_reservations:review"), {"agree": "on", "total": "1", f"qty_{self.dish.pk}": "100"})
        line = Reservation.objects.get().items.get()
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.unit_price, 250000)

    def test_direct_navigation_requires_valid_details_and_rechecks_cart(self):
        for name in ("menu", "review"):
            self.assertRedirects(self.client.get(reverse("online_reservations:" + name)), reverse("online_reservations:create"))
        self.details()
        self.client.post(reverse("online_reservations:menu"), {f"qty_{self.dish.pk}": "1"})
        Dish.objects.filter(pk=self.dish.pk).update(status="INACTIVE")
        response = self.client.post(reverse("online_reservations:review"), {"agree": "on"})
        self.assertRedirects(response, reverse("online_reservations:menu"))
        self.assertFalse(Reservation.objects.exists())
