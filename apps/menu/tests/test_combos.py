from decimal import Decimal
from datetime import timedelta
from uuid import uuid4
import json
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from apps.menu.models import Dish, Combo
from apps.menu.combos import save_combo, allocated_components, expand_selections
from apps.reservations import services
from apps.reservations.forms import OfferForm
from apps.reservations.models import Reservation, ReservationPolicy
from apps.reservations.tests import test_reservations as fixtures


@override_settings(VNPAY_TMN_CODE="TESTCODE",VNPAY_HASH_SECRET="test-only-deposit-secret")
class ComboTests(TestCase):
    at = fixtures.ReservationTests.at
    callback = fixtures.ReservationTests.callback
    pay = fixtures.ReservationTests.pay

    @classmethod
    def setUpTestData(cls):
        fixtures.ReservationTests.setUpTestData.__func__(cls)
        cls.side=Dish.objects.create(code="CBTEA",name="Trà combo",category=cls.category,unit=cls.unit,price=50000)
        cls.parts=[{"dish_id":cls.dish.pk,"quantity":2},{"dish_id":cls.side.pk,"quantity":1}]
        cls.combo=save_combo(actor=cls.manager,code="CB_TEST",name="Combo hai người",description="Cơm và trà",people=2,
            price=Decimal(449999),is_active=True,items=cls.parts)

    def reserve(self,mode="TABLE",items=None):
        return services.create_request(full_name="Khách combo",phone="0912345688",starts_at=self.arrival,party_size=4,
            duration_minutes=120,mode=mode,items=items or [{"combo_id":self.combo.pk,"quantity":1}],
            request_key=uuid4(),source_digest="c"*64)

    def post_cart(self,payload,client=None):
        return (client or self.client).post(reverse("online_reservations:cart"),json.dumps(payload),content_type="application/json")

    def test_catalog_permissions_revisions_and_invalid_composition_are_atomic(self):
        url=reverse("menu:combo_list")
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(url),self.combo.name)
        with self.assertRaises(ValidationError):
            save_combo(actor=self.manager,combo_id=self.combo.pk,expected_revision=999,code="CB_TEST",name="Wrong",description="",people=2,price=400000,is_active=True,items=self.parts)
        with self.assertRaises(ValidationError):
            save_combo(actor=self.manager,combo_id=self.combo.pk,expected_revision=1,code="CB_TEST",name="Wrong",description="",people=2,price=400000,is_active=True,items=self.parts[:1])
        self.combo.refresh_from_db()
        self.assertEqual(self.combo.name,"Combo hai người")
        self.assertEqual(self.combo.items.count(),2)

    def test_whole_dong_allocation_is_exact_and_quantities_preserved(self):
        for price in (3,7,999,100001,399999,449999,450000):
            self.combo.price=Decimal(price)
            parts=allocated_components(self.combo)
            self.assertEqual(sum(quantity*value for dish,quantity,value in parts),price)
            self.assertEqual(sum(quantity for dish,quantity,value in parts),3)
            self.assertTrue(all(1<=value<=dish.price for dish,quantity,value in parts))

    def test_expand_ignores_client_price_and_blocks_duplicate_or_excess_quantities(self):
        parts,snapshots=expand_selections([{"combo_id":self.combo.pk,"quantity":3,"price":1}])
        self.assertEqual(sum(p["quantity"]*p["unit_price"] for p in parts),3*self.combo.price)
        self.assertEqual(sum(p["quantity"] for p in parts if p["dish"].pk==self.dish.pk),6)
        for items in ([{"combo_id":self.combo.pk,"quantity":1}]*2,
                      [{"combo_id":self.combo.pk,"quantity":50},{"dish_id":self.dish.pk,"quantity":1}],
                      [{"combo_id":self.combo.pk,"dish_id":self.dish.pk,"quantity":1}]):
            with self.assertRaises(ValidationError):
                expand_selections(items)

    def test_cart_csrf_isolation_price_checks_and_unavailable_component(self):
        protected=Client(enforce_csrf_checks=True)
        self.assertEqual(self.post_cart({"action":"add","kind":"combo","id":self.combo.pk},protected).status_code,403)
        added=self.post_cart({"action":"add","kind":"combo","id":self.combo.pk,"price":1})
        self.assertEqual(added.status_code,200)
        self.assertEqual(added.json()["cart"]["total"],449999)
        self.assertEqual(Client().get(reverse("online_reservations:cart")).json()["cart"]["count"],0)
        Dish.objects.filter(pk=self.side.pk).update(status="SOLD_OUT")
        blocked=self.post_cart({"action":"add","kind":"combo","id":self.combo.pk})
        self.assertEqual(blocked.status_code,400)
        self.assertFalse(blocked.json()["cart"]["valid"])
        removed=self.post_cart({"action":"remove","kind":"combo","id":self.combo.pk})
        self.assertEqual(removed.status_code,200)
        self.assertEqual(removed.json()["cart"]["count"],0)
        self.assertFalse(Reservation.objects.exists())

    def test_storefront_cart_survives_booking_and_creates_priced_component_snapshots(self):
        with self.at(self.now):
            self.post_cart({"action":"add","kind":"combo","id":self.combo.pk})
            self.post_cart({"action":"add","kind":"dish","id":self.side.pk})
            response=self.client.post(reverse("online_reservations:create"),{
                "step":"details","request_key":str(uuid4()),"full_name":"Khách combo","phone":"0912345688",
                "starts_at":self.arrival.strftime("%Y-%m-%dT%H:%M"),"party_size":"4","duration_minutes":"120"})
            self.assertRedirects(response,reverse("online_reservations:review"))
            review=self.client.get(reverse("online_reservations:review"))
            self.assertContains(review,self.combo.name)
            self.assertEqual(review.context["total"],499999)
            self.client.post(reverse("online_reservations:review"),{"agree":"on"})
        row=Reservation.objects.get()
        self.assertEqual(row.subtotal,499999)
        self.assertEqual(row.combo_snapshot[0]["unit_price"],"449999")
        self.assertEqual(sum(p.total for p in row.items.all()),499999)
        detail=self.client.get(reverse("online_reservations:detail",args=[row.access_token]))
        self.assertContains(detail,"Combo đã đặt")
        self.assertContains(detail,"449.999")
        self.assertNotIn("reservation_draft",self.client.session)

    def test_combo_price_snapshot_survives_catalog_edit_and_receiving(self):
        with self.at(self.now):
            row=self.reserve();self.pay(row)
            save_combo(actor=self.manager,combo_id=self.combo.pk,expected_revision=1,code="CB_TEST",name="Tên combo mới",
                description="Đã sửa",people=2,price=400000,is_active=True,items=self.parts)
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision,accept_prices=True)
        row.refresh_from_db()
        self.assertEqual(row.subtotal,449999)
        self.assertEqual(order.total,449999)
        self.assertEqual(row.combo_snapshot[0]["name"],"Combo hai người")
        self.assertTrue(all("Combo hai người" in item.note for item in order.items.all()))

    def test_ready_combo_uses_components_for_stock_and_does_not_deduct_twice(self):
        ReservationPolicy.objects.get(pk=1).allowed_dishes.add(self.side)
        with self.at(self.now):
            row=self.reserve("READY")
            form=OfferForm(reservation=row)
            self.assertEqual(form.fields[f"cqty_{self.combo.pk}"].initial,1)
            self.assertEqual(form.fields[f"qty_{self.dish.pk}"].initial,0)
            services.review_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="offer",note="Chốt combo",
                starts_at=self.arrival,prep_starts_at=self.arrival-timedelta(minutes=30),ready_by=self.arrival,
                items=[{"combo_id":self.combo.pk,"quantity":1}])
            row.refresh_from_db();services.accept_offer(token=row.access_token,revision=row.revision)
            row.refresh_from_db();self.pay(row)
        with self.at(self.arrival-timedelta(minutes=30)):
            for part in row.items.all():
                for status in ("PENDING","COOKING","READY"):
                    services.kitchen_step(actor=self.manager,item_id=part.pk,target=status)
        self.ingredient.refresh_from_db();self.assertEqual(self.ingredient.stock_quantity,9)
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
        self.ingredient.refresh_from_db();self.assertEqual(self.ingredient.stock_quantity,9)
        self.assertEqual(order.total,449999)

    def test_inactive_combo_cannot_be_ordered_but_can_be_archived_after_dish_retired(self):
        Dish.objects.filter(pk=self.side.pk).update(status="INACTIVE")
        saved=save_combo(actor=self.manager,combo_id=self.combo.pk,expected_revision=1,code="CB_TEST",name=self.combo.name,
            description="",people=2,price=449999,is_active=False,items=self.parts)
        self.assertFalse(saved.is_active)
        with self.at(self.now),self.assertRaises(ValidationError):
            self.reserve()
        self.assertFalse(Reservation.objects.exists())
