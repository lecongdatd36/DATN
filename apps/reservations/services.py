from django.utils.translation import gettext_lazy as _
"""Online reservations use the same seating -> menu -> actor lock order as POS.

No seating or inventory consumption follows from merely receiving a deposit.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.permissions import can_manage_accounts
from core.seating_lock import lock_seating_schedule
from core.menu_lock import lock_menu
from apps.bookings.models import Booking
from apps.bookings.permissions import has_booking_permission
from apps.bookings.services import create_public_booking, transition_booking
from apps.bookings.duration import planned_end
from apps.bookings.hours import validate_booking_hours
from apps.customers.validators import normalize_phone
from apps.menu.models import Dish
from apps.orders.permissions import has_order_permission
from .models import (DepositAllocation, DepositPayment, DepositRefund, IngredientHold, PreorderItem,
                     Reservation, ReservationLog, ReservationMessage, ReservationPolicy)


def locks():
    lock_seating_schedule()
    lock_menu()


def actor_for(actor, kind="booking"):
    locks()
    actor = get_user_model().objects.filter(pk=getattr(actor, "pk", None), is_active=True).first()
    allowed = actor and (can_manage_accounts(actor) if kind == "manager" else
        has_order_permission(actor, "work_kitchen") if kind == "kitchen" else has_booking_permission(actor, "manage_booking"))
    if not allowed:
        raise PermissionDenied(_("Bạn không có quyền thực hiện thao tác này."))
    return actor


def log(reservation, action, description, actor=None):
    ReservationLog.objects.create(reservation=reservation, action=action, description=description,
        actor=actor, actor_snapshot=actor.username if actor else "Khách / Hệ thống")


def money(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 999999999999:
            raise ValueError
        return value
    except (ValueError, InvalidOperation, TypeError):
        raise ValidationError(_("Số tiền phải là số nguyên đồng hợp lệ.")) from None


def policy_snapshot():
    policy, policy_created = ReservationPolicy.objects.get_or_create(pk=1)
    return {**{key:getattr(policy,key) for key in ("table_deposit", "ready_percent", "hold_minutes", "offer_minutes", "minimum_lead_minutes", "free_cancel_hours")},"allowed_dish_ids":list(policy.allowed_dishes.values_list("pk",flat=True))}


def validate_request(*, full_name, phone, starts_at, duration_minutes, party_size, mode):
    name = " ".join(full_name.split()) if isinstance(full_name, str) else ""
    if not name or len(name) > 150 or type(party_size) is not int or not 1 <= party_size <= 100:
        raise ValidationError(_("Tên khách hoặc số người không hợp lệ."))
    if mode not in Reservation.Mode.values or not starts_at or timezone.is_naive(starts_at) or starts_at <= timezone.now():
        raise ValidationError(_("Chế độ hoặc thời gian đặt bàn không hợp lệ."))
    validate_booking_hours(starts_at, planned_end(starts_at, duration_minutes))
    return name, normalize_phone(phone)


def capture_items(reservation, items):
    from apps.menu.combos import expand_selections
    if reservation.mode == "READY" and not items:
        raise ValidationError(_("Chọn từ 1 đến 50 món để yêu cầu chuẩn bị sẵn."))
    expanded, snapshots = expand_selections(items)
    reservation.combo_snapshot = snapshots
    total = Decimal(0)
    for data in expanded:
        dish = data["dish"]
        if reservation.mode == "READY" and dish.pk not in reservation.policy_snapshot.get("allowed_dish_ids",[]):
            raise ValidationError(f"{dish.name} chưa được nhà hàng cho phép chuẩn bị trước. Chọn món khác hoặc Đến mới chế biến.")
        line = PreorderItem.objects.create(reservation=reservation, dish=dish, dish_name=dish.name, dish_code=dish.code,
            unit_name=dish.unit.name, quantity=data["quantity"], unit_price=data["unit_price"], note=data["note"],
            combo=data["combo"], combo_name=data["combo"].name if data["combo"] else "")
        total += line.total
    reservation.subtotal = total
    reservation.deposit_required = (total*Decimal(reservation.policy_snapshot["ready_percent"])/100).quantize(Decimal(1), rounding=ROUND_HALF_UP) if reservation.mode == "READY" else Decimal(reservation.policy_snapshot["table_deposit"])


def held_quantities(*, exclude_reservation=None):
    now = timezone.now()
    query = IngredientHold.objects.filter(state="HELD",item__is_active=True).filter(
        Q(item__reservation__status__in=("CONFIRMED","SEATED")) |
        Q(item__reservation__status="WAITING", item__reservation__hold_expires_at__gt=now))
    if exclude_reservation:
        query = query.exclude(item__reservation_id=exclude_reservation)
    return dict(query.values("ingredient_id").annotate(quantity=Sum("quantity")).values_list("ingredient_id","quantity"))


def reserve_ingredients(reservation):
    from apps.inventory.models import Ingredient
    reserved = held_quantities(exclude_reservation=reservation.pk)
    demands = defaultdict(Decimal)
    recipes = {}
    for item in reservation.items.select_related("dish").all():
        if not item.dish.tracks_inventory:
            continue
        rows = list(item.dish.recipe_ingredients.all())
        if not rows:
            raise ValidationError(f"{item.dish_name} chưa có công thức để cam kết chuẩn bị trước.")
        recipes[item.pk] = rows
        for row in rows:
            demands[row.ingredient_id] += (row.quantity*item.quantity).quantize(Decimal(".001"), rounding=ROUND_HALF_UP)
    for ingredient in Ingredient.objects.select_for_update().filter(pk__in=sorted(demands)).order_by("pk"):
        if not ingredient.is_active or ingredient.stock_quantity-reserved.get(ingredient.pk,0)<demands[ingredient.pk]:
            raise ValidationError(f"Không đủ nguyên liệu có thể cam kết: {ingredient.name}.")
    for item_id, rows in recipes.items():
        item = reservation.items.get(pk=item_id)
        for recipe in rows:
            IngredientHold.objects.create(item=item, ingredient_id=recipe.ingredient_id, quantity=(recipe.quantity*item.quantity).quantize(Decimal(".001"),rounding=ROUND_HALF_UP))


def release_holds(reservation):
    IngredientHold.objects.filter(item__reservation=reservation,state="HELD").update(state="RELEASED")


def hold_table(reservation, already_funded=False):
    now = timezone.now()
    lead=0 if already_funded else reservation.policy_snapshot["hold_minutes"]
    if reservation.mode == "READY" and (not reservation.prep_starts_at or reservation.prep_starts_at <= now+timedelta(minutes=lead)):
        raise ValidationError(_("Không còn đủ thời gian trả cọc và chuẩn bị. Nhà hàng cần chốt lại giờ mới."))
    booking = create_public_booking(full_name=reservation.full_name, phone=reservation.phone, starts_at=reservation.starts_at,
        party_size=reservation.party_size, area_id=reservation.area_id, duration_minutes=reservation.duration_minutes, note=reservation.note)
    reservation.booking = booking
    reservation.status = "WAITING"
    reservation.hold_expires_at = min(now+timedelta(minutes=reservation.policy_snapshot["hold_minutes"]),reservation.starts_at)
    reservation.free_cancel_until = reservation.prep_starts_at if reservation.mode == "READY" else reservation.starts_at-timedelta(hours=reservation.policy_snapshot["free_cancel_hours"])
    if reservation.mode == "READY":
        reserve_ingredients(reservation)
    reservation.accepted_at = now
    reservation.save()


@transaction.atomic
def expire_holds(*, now=None):
    locks()
    now = now or timezone.now()
    rows = Reservation.objects.select_for_update().filter(Q(status="WAITING",hold_expires_at__lte=now)|Q(status="OFFER",offer_expires_at__lte=now))
    count = 0
    table_ids=[]
    for row in rows:
        row.status="EXPIRED"
        row.revision+=1
        row.save()
        release_holds(row)
        if row.booking_id:
            Booking.objects.filter(pk=row.booking_id,status="PENDING").update(status="CANCELLED")
            table_ids.append(row.booking.table_id)
        log(row,"Hết hạn", "Giải phóng giữ chỗ và nguyên liệu; không xác nhận đã thu tiền.")
        count+=1
    if table_ids:
        from apps.bookings.services import _reconcile_table_statuses
        _reconcile_table_statuses(at=now,table_ids=table_ids)
    return count


@transaction.atomic
def create_request(*, full_name, phone, starts_at, party_size, duration_minutes, mode, items, request_key, source_digest, area_id=None, note=""):
    locks()
    expire_holds()
    existing = Reservation.objects.filter(request_key=request_key).first()
    if existing:
        if existing.source_digest != source_digest:
            raise PermissionDenied(_("Mã gửi yêu cầu đã được sử dụng."))
        return existing
    name,phone = validate_request(full_name=full_name,phone=phone,starts_at=starts_at,duration_minutes=duration_minutes,party_size=party_size,mode=mode)
    policy = policy_snapshot()
    if mode == "READY" and starts_at < timezone.now()+timedelta(minutes=policy["minimum_lead_minutes"]):
        raise ValidationError(_("Yêu cầu món sẵn phải đặt trước ít nhất 60 phút và chờ nhà hàng xác nhận."))
    if len(note)>500:
        raise ValidationError(_("Ghi chú tối đa 500 ký tự."))
    reservation = Reservation.objects.create(full_name=name,phone=phone,starts_at=starts_at,party_size=party_size,
        duration_minutes=duration_minutes,mode=mode,policy_snapshot=policy,request_key=request_key,source_digest=source_digest,area_id=area_id,note=note)
    capture_items(reservation,items)
    reservation.requested_snapshot={"starts_at":starts_at.isoformat(),"items":items,"subtotal":str(reservation.subtotal)}
    reservation.save()
    if mode=="TABLE":
        hold_table(reservation)
    log(reservation,"Khách gửi yêu cầu",f"Chế độ {reservation.get_mode_display()}; {party_size} khách.")
    return reservation


def locked_reservation(pk,revision=None):
    row = Reservation.objects.select_for_update().get(pk=pk)
    if revision is not None and row.revision != revision:
        raise ValidationError(_("Yêu cầu đã thay đổi. Hãy tải lại trang."))
    return row


@transaction.atomic
def review_request(*, actor, reservation_id, revision, action, note, starts_at=None, prep_starts_at=None, ready_by=None, items=None):
    actor = actor_for(actor)
    row = locked_reservation(reservation_id,revision)
    if row.status not in ("REVIEW","OFFER") or row.received>0 or row.mode!="READY":
        raise ValidationError(_("Không thể thay bản chốt của yêu cầu đã nhận tiền hoặc đang phục vụ."))
    if action=="reject":
        if not note.strip():
            raise ValidationError(_("Cần lý do từ chối."))
        row.status="REJECTED"
    elif action=="offer":
        if not all((starts_at,prep_starts_at,ready_by)) or not timezone.now()+timedelta(minutes=row.policy_snapshot["hold_minutes"])<prep_starts_at<starts_at<=ready_by<=starts_at+timedelta(minutes=10):
            raise ValidationError(_("Cần đủ thời gian cọc trước khi làm; giờ sẵn nằm trong 10 phút từ giờ hẹn."))
        validate_booking_hours(starts_at,planned_end(starts_at,row.duration_minutes))
        if row.booking_id:
            Booking.objects.filter(pk=row.booking_id,status="PENDING").update(status="CANCELLED")
            row.booking=None
        release_holds(row)
        row.items.all().delete()
        row.starts_at=starts_at
        row.prep_starts_at=prep_starts_at
        row.ready_by=ready_by
        capture_items(row,items)
        row.status="OFFER"
        row.offer_expires_at=min(timezone.now()+timedelta(minutes=row.policy_snapshot["offer_minutes"]),prep_starts_at-timedelta(minutes=row.policy_snapshot["hold_minutes"]))
    else:
        raise ValidationError(_("Thao tác không hợp lệ."))
    row.staff_note=note.strip()
    row.revision+=1
    row.save()
    log(row,"Nhà hàng phản hồi",f"{row.get_status_display()}: {row.staff_note}; tiền món {row.subtotal}, cọc {row.deposit_required}.",actor)
    return row


@transaction.atomic
def accept_offer(*, token, revision):
    locks()
    expire_holds()
    row=Reservation.objects.select_for_update().get(access_token=token)
    if row.revision!=revision or row.status!="OFFER" or row.offer_expires_at<=timezone.now():
        raise ValidationError(_("Bản chốt đã thay đổi hoặc hết hạn. Nhờ nhà hàng kiểm tra lại."))
    hold_table(row)
    row.revision+=1
    row.save()
    log(row,"Khách đồng ý bản chốt","Bắt đầu giữ chỗ và nguyên liệu có hạn để thanh toán cọc.")
    return row


@transaction.atomic
def amend_confirmed(*, actor, reservation_id, revision, starts_at, prep_starts_at, ready_by, items, note, verified=False):
    """Replace an untouched confirmed plan atomically after staff verify consent.

    The previous table and ingredient promises survive any failed replacement.
    Old item snapshots remain archived for audit; deposits are never recreated.
    """
    actor=actor_for(actor,"manager")
    row=locked_reservation(reservation_id,revision)
    if not verified or not note.strip() or row.status!="CONFIRMED" or row.booking.status!="CONFIRMED":
        raise ValidationError(_("Cần xác minh khách đồng ý và lịch còn chưa nhận khách."))
    if row.items.exclude(status="SCHEDULED").exists() or row.refunds.filter(status__in=("REQUESTED","APPROVED")).exists():
        raise ValidationError(_("Món đã gửi bếp hoặc cọc đang xử lý hoàn; không đổi thẳng cam kết."))
    validate_request(full_name=row.full_name,phone=row.phone,starts_at=starts_at,duration_minutes=row.duration_minutes,party_size=row.party_size,mode=row.mode)
    if row.mode=="READY" and not (prep_starts_at and ready_by and timezone.now()<prep_starts_at<starts_at<=ready_by<=starts_at+timedelta(minutes=10)):
        raise ValidationError(_("Thời điểm chuẩn bị/sẵn sàng chưa hợp lệ."))
    old_booking=row.booking
    release_holds(row)
    row.items.update(is_active=False)
    Booking.objects.filter(pk=old_booking.pk).update(status="CANCELLED",revision=old_booking.revision+1)
    row.booking=None
    row.starts_at=starts_at
    row.prep_starts_at=prep_starts_at if row.mode=="READY" else None
    row.ready_by=ready_by if row.mode=="READY" else None
    capture_items(row,items)
    if row.deposit_required>available_balance(row):
        raise ValidationError(_("Cọc hiện có chưa đủ bản điều chỉnh. Bản đầu chưa thu cọc bổ sung; hãy thống nhất phương án khác với khách. Lịch cũ được giữ nguyên."))
    hold_table(row,already_funded=True)
    row.status="CONFIRMED"
    row.hold_expires_at=None
    row.staff_note=note.strip()
    row.revision+=1
    row.save()
    Booking.objects.filter(pk=row.booking_id).update(status="CONFIRMED")
    row.messages.filter(resolved=False).update(resolved=True)
    log(row,"Điều chỉnh sau cọc",f"Đã xác minh khách đồng ý: {note}. Thay lịch {old_booking.booking_code}; giữ nguyên sổ tiền cọc và lưu món cũ.",actor)
    return row


@transaction.atomic
def checkout(*, token, revision, return_url, ip_address):
    from apps.orders.vnpay import payment_url
    locks()
    expire_holds()
    row=Reservation.objects.select_for_update().get(access_token=token)
    if row.status!="WAITING" or row.revision!=revision or row.hold_expires_at<=timezone.now():
        raise ValidationError(_("Yêu cầu không còn trong thời gian thanh toán cọc."))
    if row.deposits.filter(status="PENDING",zalopay_transaction__isnull=False).exists():
        raise ValidationError(_("Cọc đang có giao dịch ZaloPay chờ kết quả. Hãy kiểm tra giao dịch đó trước."))
    pending=row.deposits.filter(status="PENDING",revision=row.revision).first()
    payment=pending or DepositPayment.objects.create(reservation=row,txn_ref=f"DEP{row.pk}-{uuid4().hex[:16]}",amount=row.deposit_required,revision=row.revision)
    now=timezone.localtime()
    params={"vnp_Version":"2.1.0","vnp_Command":"pay","vnp_Amount":str(int(payment.amount*100)),"vnp_CurrCode":"VND",
        "vnp_TxnRef":payment.txn_ref,"vnp_OrderInfo":f"Dat coc {row.code}","vnp_OrderType":"other","vnp_Locale":"vn",
        "vnp_ReturnUrl":return_url,"vnp_IpAddr":ip_address or "127.0.0.1","vnp_CreateDate":now.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate":timezone.localtime(row.hold_expires_at).strftime("%Y%m%d%H%M%S")}
    return payment,payment_url(params)


@transaction.atomic
def deposit_ipn(params):
    from apps.orders.vnpay import verify
    if not verify(params) or str(params.get("vnp_TmnCode",""))!=settings.VNPAY_TMN_CODE:
        return "97","Invalid signature"
    locks()
    expire_holds()
    payment=DepositPayment.objects.select_for_update(of=("self",)).filter(txn_ref=str(params.get("vnp_TxnRef","")),zalopay_transaction__isnull=True).first()
    if not payment:
        return "01","Order not found"
    try:
        amount=Decimal(str(params.get("vnp_Amount","")))/100
    except InvalidOperation:
        return "04","Invalid amount"
    if not amount.is_finite() or amount!=payment.amount or params.get("vnp_CurrCode","VND")!="VND":
        return "04","Invalid amount"
    if payment.status in ("PAID","REVIEW"):
        return "02","Order already confirmed"
    if str(params.get("vnp_ResponseCode"))!="00" or str(params.get("vnp_TransactionStatus"))!="00":
        payment.status="FAILED"
        payment.save()
        return "00","Confirm success"
    confirm_deposit_payment(payment,provider_reference=str(params.get("vnp_TransactionNo","")))
    return "00","Confirm success"


def confirm_deposit_payment(payment, *, provider_reference):
    """Apply an already verified provider receipt inside a locked transaction."""
    if payment.status in ("PAID","REVIEW"):
        return payment.status=="PAID"
    row=locked_reservation(payment.reservation_id)
    now=timezone.now()
    payment.paid_at=now
    payment.provider_ref=provider_reference[:100]
    accepted=(row.status=="WAITING" and row.revision==payment.revision and row.hold_expires_at>now and
              row.booking_id and row.booking.status=="PENDING" and not row.deposits.exclude(pk=payment.pk).filter(status="PAID").exists())
    payment.status="PAID" if accepted else "REVIEW"
    payment.save()
    if accepted:
        row.status="CONFIRMED"
        row.revision+=1
        row.save()
        Booking.objects.filter(pk=row.booking_id).update(status="CONFIRMED")
        log(row,"Nhận cọc hợp lệ",f"Đã nhận {payment.amount} đồng; xác nhận giữ chỗ, chưa nhận khách.")
    else:
        log(row,"Cọc cần đối soát",f"Đã nhận {payment.amount} đồng sau khi lịch/bản chốt mất hiệu lực; không tự cấp lại bàn.")
        DepositRefund.objects.create(reservation=row,amount=payment.amount,reason="Giao dịch cọc cần đối soát; hoàn về phương thức gốc nếu không có phương án khách đồng ý.")
    return accepted


@transaction.atomic
def customer_message(*, token, kind, text):
    locks()
    row=Reservation.objects.select_for_update().get(access_token=token)
    if kind not in ("CHANGE","CANCEL") or not text.strip() or len(text)>1000:
        raise ValidationError(_("Nhập yêu cầu và lý do từ 1 đến 1000 ký tự."))
    if row.status in ("REJECTED","CANCELLED","NO_SHOW","COMPLETED"):
        raise ValidationError(_("Lịch đã kết thúc; liên hệ nhà hàng để đối soát tiền nếu cần."))
    if not row.messages.filter(kind=kind,resolved=False).exists():
        ReservationMessage.objects.create(reservation=row,kind=kind,text=text.strip())
        log(row,"Khách yêu cầu "+kind,text.strip())


@transaction.atomic
def close_request(*, actor, reservation_id, revision, action, reason, verified=False):
    actor=actor_for(actor,"manager")
    row=locked_reservation(reservation_id,revision)
    if action not in ("cancel","no_show") or not reason.strip() or not verified:
        raise ValidationError(_("Cần xác minh yêu cầu và nhập lý do."))
    if row.status in ("SEATED", "COMPLETED", "CANCELLED", "NO_SHOW") or (row.booking_id and row.booking.status in ("SEATED","COMPLETED")):
        raise ValidationError(_("Lượt đang phục vụ/đã đóng cần xử lý qua đơn và đối soát, không hủy lại lịch."))
    if action=="no_show" and timezone.now()<row.starts_at:
        raise ValidationError(_("Chưa tới giờ hẹn để ghi không đến."))
    if action=="no_show":
        from apps.bookings.models import BookingSettings
        grace=BookingSettings.objects.get(pk=1).no_show_grace_minutes
        if timezone.now()<row.starts_at+timedelta(minutes=grace):
            raise ValidationError(f"Cần chờ đủ {grace} phút sau giờ hẹn trước khi ghi không đến.")
    now=timezone.now()
    started=row.items.filter(started_at__isnull=False).exists()
    free=action=="cancel" and row.free_cancel_until and now<row.free_cancel_until and not started
    for line in row.items.filter(order_item__isnull=True):
        if line.status=="PENDING":
            return_preorder_stock(line,actor)
        line.status="CANCELLED"
        line.cancelled_at=now
        line.save()
    release_holds(row)
    row.status="NO_SHOW" if action=="no_show" else "CANCELLED"
    row.revision+=1
    row.save()
    if row.booking_id:
        Booking.objects.filter(pk=row.booking_id).update(status=row.status,revision=row.booking.revision+1)
    row.messages.filter(resolved=False).update(resolved=True)
    if free and row.balance>0 and not row.refunds.filter(status__in=("REQUESTED","APPROVED")).exists():
        DepositRefund.objects.create(reservation=row,amount=row.balance,reason="Hủy trong thời hạn miễn phí; chờ quản lý xác minh và hoàn thực tế.")
    log(row,"Đóng lịch",f"{row.get_status_display()}; {reason}; chính sách miễn phí: {bool(free)}; phần đã làm không tự hoàn kho.",actor)


@transaction.atomic
def manage_refund(*, actor, reservation_id, action, amount=0, reason="", refund_id=None, bank_reference="", verified=False):
    actor=actor_for(actor,"manager")
    row=locked_reservation(reservation_id)
    if row.booking_id and row.booking.status=="SEATED":
        raise ValidationError(_("Lượt đang phục vụ: chốt hóa đơn trước khi hoàn phần cọc dư."))
    terminal=row.status in ("CANCELLED","NO_SHOW","EXPIRED","REJECTED","COMPLETED") or (row.booking_id and row.booking.status in ("COMPLETED","CANCELLED"))
    limit=row.balance if terminal else max(Decimal(0),sum((p.amount for p in row.deposits.all() if p.status=="REVIEW"),Decimal(0))-row.refunded)
    if action=="request":
        amount=money(amount)
        if not reason.strip() or amount<=0 or amount>min(available_balance(row),limit):
            raise ValidationError(_("Lý do hoặc số tiền hoàn vượt số dư có thể hoàn."))
        refund=DepositRefund.objects.create(reservation=row,amount=amount,reason=reason.strip())
    else:
        refund=row.refunds.select_for_update().get(pk=refund_id)
        if not verified or not reason.strip():
            raise ValidationError(_("Cần xác minh người nhận/phương thức gốc và ghi lý do xử lý."))
        if action=="approve" and refund.status=="REQUESTED":
            if refund.amount>min(row.balance,limit):
                raise ValidationError(_("Khoản hoàn vượt số dư."))
            refund.status="APPROVED"
        elif action=="reject" and refund.status in ("REQUESTED","APPROVED"):
            refund.status="REJECTED"
        elif action=="complete" and refund.status=="APPROVED":
            if not bank_reference.strip() or refund.amount>min(row.balance,limit):
                raise ValidationError(_("Cần mã/bằng chứng hoàn thực tế và số dư đủ."))
            refund.status="COMPLETED"
            refund.bank_reference=bank_reference.strip()[:100]
            refund.completed_at=timezone.now()
        else:
            raise ValidationError(_("Trạng thái hoàn tiền đã thay đổi hoặc thao tác không hợp lệ."))
        refund.reviewed_by=actor
        refund.save()
    log(row,"Hoàn cọc",f"Phiếu {refund.pk}: {refund.status}, {refund.amount} đồng; {reason}. Không tự chuyển tiền qua ngân hàng.",actor)
    return refund


def available_balance(row):
    pending=sum((refund.amount for refund in row.refunds.all() if refund.status in ("REQUESTED","APPROVED")),Decimal(0))
    return max(Decimal(0),row.balance-pending)


def deposit_for_order(order):
    if not order.booking_id:
        return Decimal(0)
    row=Reservation.objects.filter(booking_id=order.booking_id).first()
    if not row or row.status not in ("CONFIRMED","SEATED"):
        return Decimal(0)
    return available_balance(row)


def allocate_deposit(order,invoice,total,expected=None):
    """Caller holds seating/menu locks. This records a credit, never new cash."""
    existing=DepositAllocation.objects.filter(invoice=invoice).first()
    if existing:
        return existing.amount
    row=Reservation.objects.select_for_update().filter(booking_id=order.booking_id).first() if order.booking_id else None
    credit=min(total,available_balance(row)) if row and row.status in ("CONFIRMED","SEATED") else Decimal(0)
    if expected is not None and credit!=expected:
        raise ValidationError(_("Số dư cọc thay đổi. Cần đối soát giao dịch thanh toán cuối bữa."))
    if credit>0:
        DepositAllocation.objects.create(reservation=row,invoice=invoice,amount=credit)
        log(row,"Khấu trừ cọc",f"{credit} đồng vào hóa đơn {invoice.invoice_code}; không ghi thêm tiền mặt.")
    return credit


def consume_preorder(line,actor):
    from apps.inventory.models import Ingredient,InventoryTransaction
    holds=list(line.ingredient_holds.filter(state="HELD").order_by("ingredient_id","pk"))
    if line.dish.tracks_inventory and not holds:
        raise ValidationError(_("Món chưa có phần nguyên liệu được giữ. Nhờ quản lý kiểm tra."))
    if line.inventory_deducted_at:
        return
    cost=Decimal(0)
    for hold in holds:
        ingredient=Ingredient.objects.select_for_update().get(pk=hold.ingredient_id)
        if ingredient.stock_quantity<hold.quantity:
            raise ValidationError(f"Tồn thực tế thiếu {ingredient.name}; không thể bắt đầu chuẩn bị.")
        before=ingredient.stock_quantity
        ingredient.stock_quantity-=hold.quantity
        ingredient.save(update_fields=("stock_quantity","updated_at"))
        InventoryTransaction.objects.create(ingredient=ingredient,transaction_type="SALE_USAGE",quantity=hold.quantity,
            stock_before=before,stock_after=ingredient.stock_quantity,unit_cost=ingredient.average_unit_cost,
            source_type="PREORDER",source_id=hold.pk,note=f"Chuẩn bị trước {line.reservation.code} · {line.dish_name}",performed_by=actor)
        cost+=hold.quantity*ingredient.average_unit_cost
        hold.state="CONSUMED"
        hold.save(update_fields=("state",))
    line.unit_cost=(cost/line.quantity).quantize(Decimal(1),rounding=ROUND_HALF_UP)
    line.inventory_deducted_at=timezone.now()


def return_preorder_stock(line,actor):
    from apps.inventory.models import Ingredient,InventoryTransaction
    for hold in line.ingredient_holds.filter(state="CONSUMED").order_by("ingredient_id","pk"):
        ingredient=Ingredient.objects.select_for_update().get(pk=hold.ingredient_id)
        before=ingredient.stock_quantity
        ingredient.stock_quantity+=hold.quantity
        ingredient.save(update_fields=("stock_quantity","updated_at"))
        InventoryTransaction.objects.create(ingredient=ingredient,transaction_type="SALE_RETURN",quantity=hold.quantity,stock_before=before,
            stock_after=ingredient.stock_quantity,unit_cost=ingredient.average_unit_cost,source_type="PREORDER_RETURN",source_id=hold.pk,note=f"Hủy trước chế biến {line.reservation.code}",performed_by=actor)
        hold.state="RELEASED"
        hold.save(update_fields=("state",))
    line.inventory_returned_at=timezone.now()


@transaction.atomic
def kitchen_step(*, actor, item_id, target):
    actor=actor_for(actor,"kitchen")
    line=PreorderItem.objects.select_for_update().select_related("reservation","dish").get(pk=item_id)
    row=line.reservation
    if row.status!="CONFIRMED" or row.mode!="READY" or line.order_item_id:
        raise ValidationError(_("Phiếu không còn ở luồng chuẩn bị trước; kiểm tra đơn đang phục vụ."))
    now=timezone.now()
    if target=="PENDING" and line.status=="SCHEDULED":
        if now<row.prep_starts_at:
            raise ValidationError(_("Chưa đến mốc chuẩn bị đã thông báo cho khách."))
        consume_preorder(line,actor)
        line.sent_at=now
    elif target=="COOKING" and line.status=="PENDING":
        line.started_at=now
    elif target=="READY" and line.status=="COOKING":
        line.ready_at=now
    else:
        raise ValidationError(_("Món đã thay đổi hoặc bước chế biến không hợp lệ."))
    line.status=target
    line.save()
    log(row,"Bếp chuẩn bị trước",f"{line.dish_name} × {line.quantity}: {target}.",actor)


def attach_items(order,actor):
    """Called once when a real seated order is created; preserve preparation usage."""
    from apps.orders.models import OrderItem
    from apps.orders.services import _recalculate_order
    from apps.inventory.models import InventoryTransaction
    row=Reservation.objects.select_for_update().filter(booking_id=order.booking_id).first()
    if not row:
        return
    if row.status!="CONFIRMED" or row.balance<row.deposit_required or row.refunds.filter(status__in=("REQUESTED","APPROVED")).exists():
        raise ValidationError(_("Cọc hoặc yêu cầu hoàn còn cần đối soát. Xử lý tại Đặt bàn online trước khi nhận khách."))
    for line in row.items.select_for_update().select_related("dish").all():
        if line.order_item_id or line.status=="CANCELLED":
            continue
        if row.mode=="TABLE" and (not line.dish.is_orderable or (not line.combo_id and line.unit_price!=line.dish.price)):
            raise ValidationError(_("Món dự kiến đã đổi giá/hết món. Xác nhận lại với khách tại trang đặt bàn online trước khi nhận."))
        item=OrderItem.objects.create(order=order,dish=line.dish,dish_code=line.dish_code,dish_name=line.dish_name,
            unit_name=line.unit_name,quantity=line.quantity,unit_price=line.unit_price,
            note=(f"Combo {line.combo_name}. " if line.combo_id else "")+line.note,
            status="DRAFT" if line.status=="SCHEDULED" else line.status,sent_at=line.sent_at,started_at=line.started_at,
            ready_at=line.ready_at,inventory_deducted_at=line.inventory_deducted_at,unit_cost_snapshot=line.unit_cost)
        line.order_item=item
        line.save(update_fields=("order_item",))
        InventoryTransaction.objects.filter(source_type="PREORDER",source_id__in=line.ingredient_holds.values("pk")).update(order_item_reference=item.pk)
    row.status="SEATED"
    row.revision+=1
    row.save()
    _recalculate_order(order)
    if order.items.exclude(status="DRAFT").exists():
        order.status="IN_PROGRESS"
    order.save()
    log(row,"Nhận khách",f"Liên kết món vào {order.order_code}; không trừ kho lần hai.",actor)


@transaction.atomic
def receive(*, actor, reservation_id, revision, accept_prices=False):
    from apps.orders.services import open_order
    actor=actor_for(actor)
    row=locked_reservation(reservation_id,revision)
    if row.status!="CONFIRMED" or not row.booking_id:
        raise ValidationError(_("Chỉ nhận khách cho lịch đã cọc và xác nhận."))
    if row.mode=="TABLE" and accept_prices:
        total=Decimal(0)
        for line in row.items.select_related("dish"):
            if not line.dish.is_orderable:
                raise ValidationError(_("Có món hết/ngừng bán; xử lý yêu cầu thay đổi trước khi nhận khách."))
            if not line.combo_id:
                line.unit_price=line.dish.price
            line.save(update_fields=("unit_price",))
            total+=line.total
        row.subtotal=total
        row.save()
        log(row,"Xác nhận giá khi đến","Nhân viên xác nhận đã trao đổi giá hiện tại với khách.",actor)
    booking=row.booking
    transition_booking(actor=actor,booking_id=booking.pk,target="SEATED",expected_status=booking.status,expected_revision=booking.revision)
    return open_order(actor=actor,booking_id=booking.pk)
