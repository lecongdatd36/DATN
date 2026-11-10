from datetime import datetime,time,timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from django.test import TestCase,override_settings,Client
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.bookings.models import Booking
from apps.bookings.services import transition_booking
from apps.inventory.models import Ingredient,RecipeIngredient,InventoryTransaction
from apps.menu.models import Category,Unit,Dish
from apps.orders.models import Order,OrderItem,Payment,Invoice
from apps.orders import services as orders
from apps.orders.vnpay import sign
from apps.seating.models import Area,DiningTable
from apps.reservations import services
from apps.reservations.models import Reservation,ReservationPolicy,DepositPayment,DepositRefund,IngredientHold


@override_settings(VNPAY_TMN_CODE="TESTCODE",VNPAY_HASH_SECRET="test-only-deposit-secret")
class ReservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager=get_user_model().objects.create_superuser(username="reserve_manager",password="Testing-123!only")
        cls.staff=get_user_model().objects.create_user(username="reserve_staff")
        cls.area=Area.objects.create(name="Khu online")
        cls.table=DiningTable.objects.create(code="OL01",area=cls.area,capacity=8)
        cls.category=Category.objects.create(name="Món online")
        cls.unit=Unit.objects.create(name="Đĩa OL")
        cls.dish=Dish.objects.create(code="ONLINE01",name="Cơm đặt trước",category=cls.category,unit=cls.unit,price=200000,tracks_inventory=True)
        cls.ingredient=Ingredient.objects.create(code="OLTHIT",name="Thịt OL",unit="kg",stock_quantity=10,average_unit_cost=100000)
        RecipeIngredient.objects.create(dish=cls.dish,ingredient=cls.ingredient,quantity=Decimal(".5"))
        policy,_=ReservationPolicy.objects.get_or_create(pk=1)
        policy.allowed_dishes.add(cls.dish)
        cls.now=timezone.make_aware(datetime.combine(timezone.localdate()+timedelta(days=1),time(12)))
        cls.arrival=cls.now+timedelta(hours=3)

    def at(self,moment):
        return patch("apps.reservations.services.timezone.now",return_value=moment)

    def create_row(self,mode="TABLE",quantity=2,**kwargs):
        return services.create_request(full_name="Khách online",phone="0912345688",starts_at=self.arrival,party_size=4,duration_minutes=120,
            mode=mode,items=[{"dish_id":self.dish.pk,"quantity":quantity}],request_key=kwargs.pop("request_key",uuid4()),source_digest=kwargs.pop("source_digest","a"*64),**kwargs)

    def callback(self,payment,**extra):
        params={"vnp_TmnCode":settings.VNPAY_TMN_CODE,"vnp_TxnRef":payment.txn_ref,"vnp_Amount":str(int(payment.amount*100)),
            "vnp_ResponseCode":"00","vnp_TransactionStatus":"00","vnp_TransactionNo":"TEST-"+str(payment.pk),**extra}
        params["vnp_SecureHash"]=sign(params)
        return params

    def pay(self,row):
        payment,url=services.checkout(token=row.access_token,revision=row.revision,return_url="https://example.test/return",ip_address="127.0.0.1")
        self.assertIn("vnp_SecureHash",url)
        self.assertEqual(services.deposit_ipn(self.callback(payment))[0],"00")
        row.refresh_from_db()
        return payment

    def ready_row(self):
        row=self.create_row("READY")
        services.review_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="offer",note="Món sẵn theo giờ hẹn",
            starts_at=self.arrival,prep_starts_at=self.arrival-timedelta(minutes=30),ready_by=self.arrival,
            items=[{"dish_id":self.dish.pk,"quantity":2}])
        row.refresh_from_db()
        services.accept_offer(token=row.access_token,revision=row.revision)
        row.refresh_from_db()
        self.pay(row)
        return row

    def test_a_hold_and_payment_do_not_open_table_order_or_consume_stock(self):
        with self.at(self.now):
            row=self.create_row()
            self.assertEqual(row.status,"WAITING")
            self.assertEqual(row.deposit_required,100000)
            payment=self.pay(row)
            self.assertEqual(row.status,"CONFIRMED")
            self.assertEqual(row.booking.status,"CONFIRMED")
            self.assertEqual(services.deposit_ipn(self.callback(payment))[0],"02")
        self.table.refresh_from_db()
        self.ingredient.refresh_from_db()
        self.assertEqual(self.table.status,"AVAILABLE")
        self.assertEqual(self.ingredient.stock_quantity,10)
        self.assertFalse(Order.objects.exists())

    def test_booking_hold_blocks_other_request_and_expiration_releases_it(self):
        with self.at(self.now):
            row=self.create_row()
            with self.assertRaises(ValidationError):
                self.create_row()
        with self.at(self.now+timedelta(minutes=11)):
            services.expire_holds()
            other=self.create_row()
        row.refresh_from_db()
        self.assertEqual(row.status,"EXPIRED")
        self.assertEqual(other.booking.table_id,self.table.pk)

    def test_checkout_idempotent_and_signed_return_does_not_confirm(self):
        with self.at(self.now):
            row=self.create_row()
            one,_=services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
            two,_=services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
            self.assertEqual(one.pk,two.pk)
            response=self.client.get(reverse("online_reservations:payment_return"),self.callback(one))
            self.assertEqual(response.status_code,302)
        row.refresh_from_db()
        self.assertEqual(row.status,"WAITING")

    def test_invalid_signature_amount_and_failed_payment_do_not_confirm(self):
        with self.at(self.now):
            row=self.create_row()
            payment,_=services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
            params=self.callback(payment)
            params["vnp_SecureHash"]="bad"
            self.assertEqual(services.deposit_ipn(params)[0],"97")
            self.assertEqual(services.deposit_ipn(self.callback(payment,vnp_Amount="100"))[0],"04")
            services.deposit_ipn(self.callback(payment,vnp_ResponseCode="24"))
        row.refresh_from_db()
        self.assertEqual(row.status,"WAITING")

    def test_late_success_is_received_for_review_not_double_booking(self):
        with self.at(self.now):
            row=self.create_row()
            payment,_=services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
        with self.at(self.now+timedelta(minutes=11)):
            other=self.create_row()
            self.assertEqual(services.deposit_ipn(self.callback(payment))[0],"00")
        row.refresh_from_db();payment.refresh_from_db()
        self.assertEqual(row.status,"EXPIRED")
        self.assertEqual(payment.status,"REVIEW")
        self.assertEqual(row.received,100000)
        self.assertEqual(row.refunds.count(),1)
        self.assertEqual(other.status,"WAITING")

    def test_b_offer_requires_customer_acceptance_before_hold_and_payment(self):
        with self.at(self.now):
            row=self.create_row("READY")
            self.assertIsNone(row.booking_id)
            with self.assertRaises(ValidationError):
                services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
            services.review_request(actor=self.manager,reservation_id=row.pk,revision=1,action="offer",note="Đồng ý",
                starts_at=self.arrival,prep_starts_at=self.arrival-timedelta(minutes=30),ready_by=self.arrival,items=[{"dish_id":self.dish.pk,"quantity":2}])
            row.refresh_from_db()
            self.assertEqual(row.status,"OFFER")
            self.assertIsNone(row.booking_id)
            services.accept_offer(token=row.access_token,revision=row.revision)
            row.refresh_from_db()
            self.assertEqual(row.deposit_required,200000)
            self.assertEqual(services.held_quantities()[self.ingredient.pk],1)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,10)

    def test_preparation_before_arrival_and_attach_do_not_deduct_twice(self):
        with self.at(self.now):
            row=self.ready_row()
        line=row.items.get()
        with self.at(self.arrival-timedelta(minutes=31)),self.assertRaises(ValidationError):
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="PENDING")
        with self.at(self.arrival-timedelta(minutes=30)):
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="PENDING")
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="COOKING")
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="READY")
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,9)
        self.assertFalse(Order.objects.exists())
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,9)
        item=order.items.get()
        self.assertEqual(item.status,"READY")
        self.assertEqual(item.unit_cost_snapshot,50000)
        self.assertEqual(InventoryTransaction.objects.filter(order_item_reference=item.pk,transaction_type="SALE_USAGE").count(),1)

    def test_deposit_applied_once_and_only_remainder_is_new_cash(self):
        with self.at(self.now):
            row=self.create_row()
            self.pay(row)
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
            OrderItem.objects.filter(order=order).update(status="SERVED")
            order.refresh_from_db()
            orders.prepare_quick_payment(actor=self.manager,order_id=order.pk)
            quote=orders.payment_preview(order)
            self.assertEqual(quote["invoice_total"],400000)
            self.assertEqual(quote["due"],300000)
            invoice=orders.process_payment(actor=self.manager,order_id=order.pk,payment_method="CASH")
            self.assertEqual(invoice.total,400000)
            self.assertEqual(invoice.paid_amount,400000)
            self.assertEqual(invoice.payments.get(method="DEPOSIT").amount,100000)
            self.assertEqual(invoice.payments.get(method="CASH").amount,300000)
            self.assertEqual(row.allocations.count(),1)
            with self.assertRaises(ValidationError):
                orders.process_payment(actor=self.manager,order_id=order.pk,payment_method="CASH")

    def test_a_price_change_requires_explicit_customer_agreement(self):
        with self.at(self.now):
            row=self.create_row()
            self.pay(row)
        Dish.objects.filter(pk=self.dish.pk).update(price=210000)
        with self.at(self.arrival):
            with self.assertRaises(ValidationError):
                services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
            row.booking.refresh_from_db()
            self.assertEqual(row.booking.status,"CONFIRMED")
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision,accept_prices=True)
        self.assertEqual(order.items.get().unit_price,210000)

    def test_cancellation_and_refund_require_real_completion_proof(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
            services.close_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="cancel",reason="Khách hủy đúng hạn",verified=True)
            refund=row.refunds.get()
            self.assertEqual(row.refunded,0)
            services.manage_refund(actor=self.manager,reservation_id=row.pk,refund_id=refund.pk,action="approve",reason="Đã xác minh",verified=True)
            with self.assertRaises(ValidationError):
                services.manage_refund(actor=self.manager,reservation_id=row.pk,refund_id=refund.pk,action="complete",reason="Hoàn",verified=True)
            services.manage_refund(actor=self.manager,reservation_id=row.pk,refund_id=refund.pk,action="complete",reason="Hoàn về nguồn",bank_reference="BANK-PROOF",verified=True)
            self.assertEqual(row.refunded,100000)
            with self.assertRaises(ValidationError):
                services.manage_refund(actor=self.manager,reservation_id=row.pk,action="request",amount=1,reason="Lặp")

    def test_unpaid_cannot_be_confirmed_or_seated_by_old_booking_ui(self):
        with self.at(self.now):
            row=self.create_row()
            with self.assertRaises(ValidationError):
                transition_booking(actor=self.manager,booking_id=row.booking_id,target="CONFIRMED",expected_status="PENDING",expected_revision=1)

    def test_request_key_does_not_create_duplicates_or_leak_other_session(self):
        key=uuid4()
        with self.at(self.now):
            one=self.create_row(request_key=key)
            two=self.create_row(request_key=key)
            self.assertEqual(one.pk,two.pk)
            with self.assertRaises(PermissionDenied):
                self.create_row(request_key=key,source_digest="b"*64)

    def test_public_and_manager_pages_render_with_permissions_and_csrf(self):
        with self.at(self.now):
            row=self.create_row("READY")
            self.assertEqual(self.client.get(reverse("online_reservations:create")).status_code,200)
            self.assertEqual(self.client.get(reverse("online_reservations:detail",args=[row.access_token])).status_code,200)
        self.client.force_login(self.manager)
        for url in (reverse("online_reservations:manage"),reverse("online_reservations:manage_detail",args=[row.pk]),reverse("online_reservations:policy"),reverse("online_reservations:kitchen")):
            self.assertEqual(self.client.get(url).status_code,200,url)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("online_reservations:manage")).status_code,403)
        self.assertEqual(self.client.post(reverse("online_reservations:kitchen"),{}).status_code,403)
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("online_reservations:detail",args=[row.access_token]),{"action":"accept"}).status_code,403)

    def test_reserved_ingredients_cannot_be_consumed_by_another_order(self):
        from apps.inventory.services import consume_order_items
        with self.at(self.now):
            row=self.ready_row()
            self.ingredient.stock_quantity=Decimal(1)
            self.ingredient.save()
            order=Order.objects.create(table=self.table,guest_count=1,created_by=self.manager)
            item=OrderItem.objects.create(order=order,dish=self.dish,dish_code=self.dish.code,dish_name=self.dish.name,unit_name=self.unit.name,unit_price=self.dish.price,quantity=1)
            from django.db import transaction
            with transaction.atomic(), self.assertRaises(ValidationError):
                consume_order_items(actor=self.manager,items=[item])
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,1)

    def test_pending_preparation_cancellation_returns_stock_but_cooked_does_not(self):
        with self.at(self.now):
            row=self.ready_row()
        line=row.items.get()
        with self.at(row.prep_starts_at):
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="PENDING")
            services.close_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="cancel",reason="Khách hủy",verified=True)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,10)
        line.refresh_from_db()
        self.assertIsNotNone(line.inventory_returned_at)

    def test_cooked_cancellation_keeps_cost_and_does_not_return_food_as_raw_stock(self):
        with self.at(self.now):
            row=self.ready_row()
        line=row.items.get()
        with self.at(row.prep_starts_at):
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="PENDING")
            services.kitchen_step(actor=self.manager,item_id=line.pk,target="COOKING")
            services.close_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="cancel",reason="Hủy sau chế biến",verified=True)
        self.ingredient.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,9)
        self.assertIsNone(line.inventory_returned_at)
        self.assertEqual(line.unit_cost,50000)

    def test_excess_deposit_leaves_refundable_balance_and_no_fake_cash(self):
        Dish.objects.filter(pk=self.dish.pk).update(price=50000)
        with self.at(self.now):
            row=self.create_row(quantity=1);self.pay(row)
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
            OrderItem.objects.filter(order=order).update(status="SERVED")
            orders.prepare_quick_payment(actor=self.manager,order_id=order.pk)
            invoice=orders.process_payment(actor=self.manager,order_id=order.pk,payment_method="CASH")
            self.assertEqual(invoice.total,50000)
            self.assertEqual(invoice.payments.filter(method="CASH").count(),0)
            self.assertEqual(row.balance,50000)
            refund=services.manage_refund(actor=self.manager,reservation_id=row.pk,action="request",amount=50000,reason="Cọc dư")
            self.assertEqual(refund.amount,50000)

    def test_final_vnpay_charges_only_remainder_and_records_gross_invoice(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
            OrderItem.objects.filter(order=order).update(status="SERVED")
            orders.prepare_quick_payment(actor=self.manager,order_id=order.pk)
            payment,url=orders.create_vnpay_payment(actor=self.manager,order_id=order.pk,return_url="https://test/",ip_address="127.0.0.1")
            self.assertEqual(payment.amount,300000)
            self.assertEqual(payment.deposit_amount,100000)
            params={"vnp_TxnRef":payment.txn_ref,"vnp_Amount":str(int(payment.amount*100)),"vnp_ResponseCode":"00","vnp_TransactionStatus":"00"}
            self.assertEqual(orders.process_vnpay_ipn(params=params)[0],"00")
            self.assertEqual(Invoice.objects.get(order=order).total,400000)

    def test_paid_amendment_preserves_old_booking_on_failure_and_archives_on_success(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
            old_booking_id=row.booking_id
            original_item=row.items.get()
            with self.assertRaises(ValidationError):
                services.amend_confirmed(actor=self.manager,reservation_id=row.pk,revision=row.revision,starts_at=self.arrival+timedelta(minutes=30),
                    prep_starts_at=None,ready_by=None,items=[{"dish_id":999999,"quantity":1}],note="Khách đồng ý",verified=True)
            self.assertEqual(Booking.objects.get(pk=old_booking_id).status,"CONFIRMED")
            services.amend_confirmed(actor=self.manager,reservation_id=row.pk,revision=row.revision,starts_at=self.arrival+timedelta(minutes=30),
                prep_starts_at=None,ready_by=None,items=[{"dish_id":self.dish.pk,"quantity":1}],note="Khách đồng ý đổi giờ và còn 1 phần",verified=True)
            row.refresh_from_db();original_item.refresh_from_db()
            self.assertFalse(original_item.is_active)
            self.assertEqual(row.items.count(),1)
            self.assertEqual(row.status,"CONFIRMED")
            self.assertNotEqual(row.booking_id,old_booking_id)
            self.assertEqual(row.deposits.count(),1)
            self.assertEqual(row.received,100000)

    def test_shared_vnpay_ipn_dispatches_deposit_without_login(self):
        with self.at(self.now):
            row=self.create_row()
            payment,_=services.checkout(token=row.access_token,revision=row.revision,return_url="https://test/",ip_address="127.0.0.1")
            response=self.client.get(reverse("sales:vnpay_ipn"),self.callback(payment))
        self.assertEqual(response.json()["RspCode"],"00")
        row.refresh_from_db()
        self.assertEqual(row.status,"CONFIRMED")

    def test_cancelling_seated_draft_order_keeps_deposit_available_for_review(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
            orders.cancel_table_order(actor=self.manager,order_id=order.pk,expected_revision=order.revision,reason="Khách đổi kế hoạch")
            row.refresh_from_db()
            self.assertEqual(row.status,"CANCELLED")
            self.assertEqual(row.balance,100000)
            refund=services.manage_refund(actor=self.manager,reservation_id=row.pk,action="request",amount=100000,reason="Quản lý xử lý ngoại lệ")
            self.assertEqual(refund.amount,100000)

    def test_code_and_phone_lookup_does_not_disclose_private_link_or_payment(self):
        with self.at(self.now):
            row=self.create_row()
            response=self.client.post(reverse("online_reservations:lookup"),{"reservation_code":row.code,"phone":row.phone})
        self.assertContains(response,row.get_status_display())
        self.assertNotContains(response,str(row.access_token))
        self.assertNotContains(response,row.full_name)
        self.assertNotContains(response,self.dish.name)
        self.assertIsNone(response.context["reservation"])

    def test_lookup_original_session_shows_items_deposit_and_private_link(self):
        session=self.client.session
        session.save()
        digest=salted_hmac("reservation.source",session.session_key,algorithm="sha256").hexdigest()
        with self.at(self.now):
            row=self.create_row(source_digest=digest);self.pay(row)
            response=self.client.post(reverse("online_reservations:lookup"),{"reservation_code":row.code,"phone":row.phone})
        self.assertContains(response,self.dish.name)
        self.assertContains(response,"Cọc đã nhận")
        self.assertContains(response,"100.000")
        self.assertContains(response,reverse("online_reservations:detail",args=[row.access_token]))
        self.assertContains(response,"Món đã được ghi nhận, chờ khách đến.")
        self.assertEqual(response["Referrer-Policy"],"same-origin")
        self.assertIn("no-store",response["Cache-Control"])

    def test_lookup_after_private_visit_is_scoped_to_that_browser(self):
        with self.at(self.now):
            row=self.create_row()
            self.client.get(reverse("online_reservations:detail",args=[row.access_token]))
            data={"reservation_code":row.code,"phone":row.phone}
            own=self.client.post(reverse("online_reservations:lookup"),data)
            stranger=Client().post(reverse("online_reservations:lookup"),data)
        self.assertContains(own,str(row.access_token))
        self.assertNotContains(stranger,str(row.access_token))
        self.assertNotContains(stranger,self.dish.name)

    def test_lookup_staff_details_require_booking_permission(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
            data={"reservation_code":row.code,"phone":row.phone}
            self.client.force_login(self.staff)
            denied=self.client.post(reverse("online_reservations:lookup"),data)
            self.client.force_login(self.manager)
            allowed=self.client.post(reverse("online_reservations:lookup"),data)
        self.assertNotContains(denied,row.full_name)
        self.assertContains(allowed,self.dish.name)
        self.assertContains(allowed,reverse("online_reservations:manage_detail",args=[row.pk]))
        self.assertNotContains(allowed,str(row.access_token))

    def test_paid_table_preorders_visible_without_allowing_early_cooking(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
            self.client.force_login(self.manager)
            response=self.client.get(reverse("online_reservations:kitchen"))
            line=row.items.get()
            self.assertContains(response,f'data-preorder-item="{line.pk}"')
            self.assertContains(response,"Chờ khách đến · chưa phát hành phiếu bếp")
            self.assertContains(response,"100.000")
            self.assertContains(response,self.table.code)
            self.assertNotContains(response,'name="target"')
            # Forging the form must not bypass the preparation policy.
            self.client.post(reverse("online_reservations:kitchen"),{"item_id":line.pk,"target":"PENDING"})
        line.refresh_from_db();self.ingredient.refresh_from_db()
        self.assertEqual(line.status,"SCHEDULED")
        self.assertIsNone(line.sent_at)
        self.assertEqual(self.ingredient.stock_quantity,10)
        self.assertFalse(Order.objects.exists())

    def test_kitchen_hides_unpaid_preorders_and_items_after_receiving_guests(self):
        self.client.force_login(self.manager)
        with self.at(self.now):
            row=self.create_row()
            line=row.items.get()
            before=self.client.get(reverse("online_reservations:kitchen"))
            self.assertNotContains(before,f'data-preorder-item="{line.pk}"')
            self.pay(row)
            confirmed=self.client.get(reverse("online_reservations:kitchen"))
            self.assertContains(confirmed,f'data-preorder-item="{line.pk}"')
        with self.at(self.arrival):
            order=services.receive(actor=self.manager,reservation_id=row.pk,revision=row.revision)
            after=self.client.get(reverse("online_reservations:kitchen"))
        self.assertNotContains(after,f'data-preorder-item="{line.pk}"')
        self.assertEqual(order.items.count(),1)

    def test_ready_preorder_kitchen_controls_still_respect_preparation_time(self):
        with self.at(self.now):
            row=self.ready_row()
            self.client.force_login(self.manager)
            before=self.client.get(reverse("online_reservations:kitchen"))
        self.assertContains(before,'value="PENDING" disabled')
        with self.at(self.arrival-timedelta(minutes=30)):
            self.client.post(reverse("online_reservations:kitchen"),{"item_id":row.items.get().pk,"target":"PENDING"})
            after=self.client.get(reverse("online_reservations:kitchen"))
        self.assertContains(after,'value="COOKING"')
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.stock_quantity,9)

    def test_no_show_respects_grace_and_releases_unconsumed_ingredients(self):
        with self.at(self.now):
            row=self.ready_row()
        with self.at(self.arrival),self.assertRaises(ValidationError):
            services.close_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="no_show",reason="Chưa tới",verified=True)
        with self.at(self.arrival+timedelta(minutes=16)):
            services.close_request(actor=self.manager,reservation_id=row.pk,revision=row.revision,action="no_show",reason="Đã liên hệ, không tới",verified=True)
            self.assertNotIn(self.ingredient.pk,services.held_quantities())
        row.refresh_from_db()
        self.assertEqual(row.status,"NO_SHOW")
        self.assertEqual(row.balance,200000)

    def test_confirmed_management_page_exposes_verified_amendment_form(self):
        with self.at(self.now):
            row=self.create_row();self.pay(row)
        self.client.force_login(self.manager)
        response=self.client.get(reverse("online_reservations:manage_detail",args=[row.pk]))
        self.assertContains(response,'value="amend"')
        self.assertContains(response,"Điều chỉnh sau cọc")

    def test_mobile_open_table_cannot_bypass_unpaid_deposit_and_imports_paid_items(self):
        with self.at(self.now):
            row=self.create_row()
            with self.assertRaises(ValidationError):
                orders.open_table(actor=self.manager,table_id=self.table.pk,guest_count=4,reservation_id=row.booking_id)
            self.assertFalse(Order.objects.exists())
            row.booking.refresh_from_db()
            self.assertEqual(row.booking.status,"PENDING")
            self.pay(row)
        with self.at(self.arrival):
            order=orders.open_table(actor=self.manager,table_id=self.table.pk,guest_count=4,reservation_id=row.booking_id)
        self.assertEqual(order.items.count(),1)
        row.refresh_from_db()
        self.assertEqual(row.status,"SEATED")

    def test_unconfigured_gateway_is_explained_without_exposing_server_settings(self):
        with self.at(self.now):
            row=self.create_row()
            with override_settings(VNPAY_TMN_CODE="",VNPAY_HASH_SECRET=""):
                response=self.client.get(reverse("online_reservations:detail",args=[row.access_token]))
                self.assertContains(response,"đang thiết lập thanh toán online")
                self.assertNotContains(response,"VNPAY_HASH_SECRET")
                self.client.post(reverse("online_reservations:detail",args=[row.access_token]),{"action":"pay","revision":row.revision,"agree":"yes"})
                self.assertEqual(row.deposits.count(),0)
