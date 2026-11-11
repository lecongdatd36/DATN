import json
from decimal import Decimal
from unittest.mock import patch
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import translation
from apps.menu.models import Dish
from apps.menu.combos import save_combo
from apps.reservations.models import Reservation
from apps.reservations.tests import test_reservations as fixtures
from apps.customer_portal.chatbot_contract import localized_system_instruction


class CustomerLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.ReservationTests.setUpTestData.__func__(cls)
        cls.dish.name_en="Preorder Rice"
        cls.dish.description_en="A comforting rice dish."
        cls.dish.save()
        cls.side=Dish.objects.create(code="LANGTEA",name="Trà chanh",name_en="Lemon Tea",description_en="A refreshing drink.",
            category=cls.category,unit=cls.unit,price=32000)
        cls.combo=save_combo(actor=cls.manager,code="CB_LANG",name="Combo vị nhà",name_en="A Taste of Home Combo",
            description="Cơm và trà",description_en="Rice and tea for two.",people=2,price=210000,is_active=True,
            items=[{"dish_id":cls.dish.pk,"quantity":1},{"dish_id":cls.side.pk,"quantity":1}])

    def setUp(self):
        translation.activate("vi")
        self.addCleanup(translation.activate,"vi")

    def switch(self,lang,next_path="/menu/"):
        return self.client.post(reverse("set_language"),{"language":lang,"next":next_path})

    def add_cart(self):
        return self.client.post(reverse("online_reservations:cart"),json.dumps({"action":"add","kind":"combo","id":self.combo.pk}),content_type="application/json")

    def test_menu_uses_full_width_shared_banner_and_localized_catalog(self):
        self.switch("en")
        response=self.client.get(reverse("customer_portal:menu"))
        self.assertContains(response,'lang="en"')
        self.assertContains(response,'class="cq-welcome"')
        self.assertContains(response,"Pick your favourites.")
        self.assertContains(response,"Preorder Rice")
        self.assertContains(response,"A Taste of Home Combo")
        self.assertContains(response,"210,000")
        self.assertNotContains(response,"cq-page-banner-copy")
        self.assertContains(response,reverse("online_reservations:create"))

    def test_language_switch_preserves_query_cart_and_booking_draft(self):
        self.add_cart()
        session=self.client.session
        session["reservation_draft"]={**session["reservation_draft"],"details":{"full_name":"Tên đã nhập","party_size":"4"}}
        session.save()
        before=dict(self.client.session["reservation_draft"])
        target=reverse("customer_portal:menu")+"?q=tea&category="+str(self.category.pk)
        response=self.switch("en",target)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response["Location"],target)
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value,"en")
        self.assertEqual(self.client.session["reservation_draft"],before)
        english=self.client.get(reverse("online_reservations:cart")).json()["cart"]
        self.assertEqual(english["items"][0]["name"],"A Taste of Home Combo")
        self.assertEqual(english["total"],210000)
        self.switch("vi")
        vietnamese=self.client.get(reverse("online_reservations:cart")).json()["cart"]
        self.assertEqual(vietnamese["items"][0]["name"],"Combo vị nhà")
        self.assertEqual(vietnamese["total"],english["total"])
        self.assertEqual(self.client.session["reservation_draft"],before)
        self.assertFalse(Reservation.objects.exists())

    def test_english_search_remains_public_and_can_find_english_names(self):
        self.switch("en")
        hidden=Dish.objects.create(code="LANGHIDDEN",name="Ẩn",name_en="Secret Tea",category=self.category,unit=self.unit,price=1,status="INACTIVE")
        response=self.client.get(reverse("customer_portal:menu"),{"q":"Tea"})
        self.assertEqual(list(response.context["dishes"].values_list("pk",flat=True)),[self.side.pk])
        self.assertContains(response,"Lemon Tea")
        self.assertNotContains(response,hidden.name_en)

    def test_english_form_labels_hours_and_validation_do_not_create_a_booking(self):
        self.switch("en")
        with patch("django.utils.timezone.now",return_value=self.now):
            response=self.client.post(reverse("online_reservations:create"),{
                "step":"details","full_name":"English guest","phone":"abc","party_size":"4",
                "starts_at":self.arrival.strftime("%Y-%m-%dT%H:%M"),"duration_minutes":"120"})
        self.assertContains(response,"Full name")
        self.assertContains(response,"Phone number")
        self.assertContains(response,"Opening hours:")
        self.assertContains(response,"Enter a Vietnamese phone number")
        self.assertFalse(Reservation.objects.exists())

    def test_javascript_catalog_and_language_post_are_safe(self):
        self.switch("en")
        catalog=self.client.get(reverse("javascript-catalog"))
        self.assertContains(catalog,"Added to your basket.")
        self.assertIn("no-store",catalog["Cache-Control"])
        protected=Client(enforce_csrf_checks=True)
        self.assertEqual(protected.post(reverse("set_language"),{"language":"en","next":"/menu/"}).status_code,403)
        response=self.switch("en","https://outside.example/")
        self.assertNotIn("outside.example",response["Location"])

    def test_unknown_english_translation_falls_back_and_seed_preserves_custom_fields(self):
        self.switch("en")
        self.side.name_en="Custom Lemon Tea"
        self.side.save()
        before=(self.side.name,self.side.price,self.side.status)
        call_command("seed_menu_english",verbosity=0)
        self.side.refresh_from_db()
        self.assertEqual(self.side.name_en,"Custom Lemon Tea")
        self.assertEqual((self.side.name,self.side.price,self.side.status),before)
        self.assertFalse(Reservation.objects.exists())

    def test_chat_instruction_uses_selected_language_without_changing_safety_rules(self):
        with translation.override("en"):
            english=localized_system_instruction()
        with translation.override("vi"):
            vietnamese=localized_system_instruction()
        self.assertIn("Reply in English.",english)
        self.assertIn("Reply in Vietnamese.",vietnamese)
        self.assertIn("Không có quyền đọc tài khoản",english)
