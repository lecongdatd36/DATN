from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.seating_lock import lock_seating_schedule
from core.menu_lock import lock_menu
from apps.bookings.models import Booking, BookingActivityLog
from apps.bookings.permissions import has_booking_permission
from apps.bookings.services import seat_walk_in
from apps.menu.models import Dish
from apps.customers.models import Customer
from apps.customers.services import tier_for_spending
from apps.seating.models import DiningTable, DiningTableQRToken
from .models import (
    Invoice, OnlinePayment, Order, OrderItem, OrderActivityLog, Payment, PaymentBatch,
    PaymentRequest, PromotionCode, QRCheckInRequest, QROrderRequest, QROrderRequestItem,
    QRServiceRequest,
)
from .permissions import has_order_permission
from .vnpay import payment_url


def _lock_actor(actor, permission="manage_order"):
    # Consistent order across bookings, menu, orders: seating -> menu -> actor -> rows.
    lock_seating_schedule()
    lock_menu()
    if not actor.is_authenticated or not actor.pk:
        raise PermissionDenied("Bạn không có quyền thực hiện thao tác đơn hàng này.")
    actor = get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
    if actor is None or not has_order_permission(actor, permission):
        raise PermissionDenied("Bạn không có quyền thực hiện thao tác đơn hàng này.")
    return actor


def _log(actor, order, action, description, actor_snapshot=""):
    OrderActivityLog.objects.create(
        order=order,
        action=action,
        description=description,
        performed_by=actor,
        actor_snapshot=actor_snapshot or (actor.username if actor else "Hệ thống"),
    )


def _save(actor, order, action, description):
    order.revision += 1
    order.save(update_fields=("status", "subtotal", "discount_amount", "total_amount", "revision", "updated_at"))
    _log(actor, order, action, description)


def _invoice_code_for(order):
    # Mỗi lượt chỉ có một đơn và mỗi đơn chỉ có một hóa đơn, nên mã dựa trên
    # khóa chính của đơn vừa ổn định vừa không tranh chấp khi thu tiền đồng thời.
    return f"HD{order.pk:06d}"


def payment_preview(order, promotion_code=None):
    """Return the authoritative member and promotion discount preview."""
    subtotal = order.total
    customer = order.customer
    tier = None
    if customer:
        tier = tier_for_spending(customer.total_spending)
    discount_percent = tier.discount_percent if tier else Decimal("0")
    membership_discount = (subtotal * discount_percent / Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    promotion = None
    promotion_snapshot = order.promotion_code_snapshot
    promotion_discount = order.promotion_discount_amount
    if promotion_code is not None:
        promotion_snapshot = (promotion_code or "").strip().upper()
        promotion_discount = Decimal("0")
        if promotion_snapshot:
            promotion = PromotionCode.objects.filter(code__iexact=promotion_snapshot).first()
            now = timezone.now()
            if promotion is None or not promotion.is_active:
                raise ValidationError({"promotion_code": "Mã giảm giá không tồn tại hoặc đã ngừng áp dụng."})
            if not promotion.starts_at <= now < promotion.ends_at:
                raise ValidationError({"promotion_code": "Mã giảm giá chưa đến thời gian áp dụng hoặc đã hết hạn."})
            if subtotal < promotion.minimum_order:
                raise ValidationError({"promotion_code": f"Đơn hàng phải từ {promotion.minimum_order:.0f} đồng để dùng mã này."})
            eligible = max(Decimal("0"), subtotal - membership_discount)
            if promotion.discount_type == PromotionCode.DiscountType.PERCENT:
                if promotion.value > 100:
                    raise ValidationError({"promotion_code": "Mức giảm phần trăm của mã không hợp lệ."})
                promotion_discount = (eligible * promotion.value / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            else:
                promotion_discount = promotion.value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if promotion.maximum_discount:
                promotion_discount = min(promotion_discount, promotion.maximum_discount)
            promotion_discount = min(promotion_discount, eligible)
    total_discount = membership_discount + promotion_discount
    return {
        "subtotal": subtotal,
        "tier": tier,
        "discount_percent": discount_percent,
        "membership_discount": membership_discount,
        "promotion": promotion,
        "promotion_code": promotion_snapshot,
        "promotion_discount": promotion_discount,
        "discount": total_discount,
        "due": max(Decimal("0"), subtotal - total_discount),
    }


def _store_promotion(order, preview):
    order.promotion_code_snapshot = preview["promotion_code"]
    order.promotion_discount_amount = preview["promotion_discount"]
    order.discount_amount = preview["discount"]
    order.total_amount = preview["due"]


@transaction.atomic
def apply_promotion(*, actor, order_id, promotion_code):
    actor = _lock_actor(actor, "collect_payment")
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAYMENT_REQUESTED:
        raise ValidationError("Chỉ áp dụng mã khi đơn đang chờ thanh toán.")
    if Invoice.objects.filter(order=order, paid_amount__gt=0).exists():
        raise ValidationError("Hóa đơn đã thu một phần nên không thể thay đổi mã giảm giá.")
    preview = payment_preview(order, promotion_code=promotion_code)
    _store_promotion(order, preview)
    order.revision += 1
    order.save(update_fields=("promotion_code_snapshot", "promotion_discount_amount", "discount_amount", "total_amount", "revision", "updated_at"))
    action = "Áp mã giảm giá" if preview["promotion_code"] else "Bỏ mã giảm giá"
    _log(actor, order, action, f"{preview['promotion_code'] or 'Không dùng mã'}; giảm {preview['promotion_discount']:.0f} đồng.")
    return preview


def _order(order_id, expected_revision, *, require_open=True):
    # PostgreSQL không cho FOR UPDATE đi qua phía nullable của OUTER JOIN.
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.revision != expected_revision:
        raise ValidationError("Đơn đã thay đổi. Hãy tải lại trang trước khi thao tác.")
    if order.booking_id and order.booking.status != Booking.Status.SEATED:
        raise ValidationError("Lượt khách không còn ở trạng thái đang phục vụ.")
    if require_open and order.status not in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        raise ValidationError("Đơn đã hủy hoặc đang chờ thanh toán; không thể thay đổi món.")
    return order


def _recalculate_order(order):
    subtotal = sum(
        (item.subtotal for item in order.items.all() if item.status != OrderItem.Status.CANCELLED),
        Decimal("0"),
    )
    order.subtotal = subtotal
    order.total_amount = max(Decimal("0"), subtotal - order.discount_amount)
    return order


def _available_dish(dish_id):
    dish = Dish.objects.select_related("category", "unit").filter(pk=dish_id).first()
    if dish is None or not dish.is_orderable:
        raise ValidationError({"dish": "Món đã hết, ngừng bán hoặc danh mục đã ngừng sử dụng. Hãy chọn món khác."})
    return dish


def _validate_quantity(quantity):
    if type(quantity) is not int or not 1 <= quantity <= 100:
        raise ValidationError({"quantity": "Số lượng phải là số nguyên từ 1 đến 100."})


def _normalize_seat_number(order, seat_number):
    if seat_number in (None, ""):
        return None
    try:
        seat_number = int(seat_number)
    except (TypeError, ValueError) as error:
        raise ValidationError({"seat_number": "Vị trí khách phải là một số nguyên."}) from error
    if not 1 <= seat_number <= order.guest_count:
        raise ValidationError({
            "seat_number": f"Vị trí khách phải từ 1 đến {order.guest_count} theo số khách của bàn."
        })
    return seat_number


def _create_order(actor, booking):
    employee = getattr(actor, "employee_profile", None)
    order = Order.objects.create(
        booking=booking,
        table=booking.table,
        customer=booking.customer,
        employee=employee,
        guest_count=booking.party_size,
        created_by=actor,
        opened_at=timezone.now(),
    )
    order.order_code = f"DH{order.pk:06d}"
    order.save(update_fields=("order_code",))
    if booking.table.status != DiningTable.Status.OCCUPIED:
        booking.table.status = DiningTable.Status.OCCUPIED
        booking.table.save(update_fields=("status", "updated_at"))
    _log(actor, order, "Mở đơn", f"Lượt {booking.booking_code}; bàn {booking.table.code}; {booking.party_size} khách.")
    return order


@transaction.atomic
def open_order(*, actor, booking_id):
    actor = _lock_actor(actor)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status != Booking.Status.SEATED:
        raise ValidationError("Hãy nhận khách vào bàn trước khi mở đơn.")
    # Repeated requests for this visit return its single existing order.
    existing = Order.objects.filter(booking=booking).first()
    return existing if existing else _create_order(actor, booking)


@transaction.atomic
def open_walk_in_order(*, actor, **visit_data):
    actor = _lock_actor(actor)
    booking = seat_walk_in(actor=actor, **visit_data)
    return _create_order(actor, booking)


@transaction.atomic
def add_item(*, actor, order_id, expected_revision, dish_id, quantity, note="", seat_number=None):
    actor = _lock_actor(actor)
    _validate_quantity(quantity)
    order = _order(order_id, expected_revision)
    seat_number = _normalize_seat_number(order, seat_number)
    dish = _available_dish(dish_id)
    item = OrderItem(order=order, dish=dish, dish_code=dish.code, dish_name=dish.name, unit_name=dish.unit.name,
                     unit_price=dish.price, quantity=quantity, seat_number=seat_number,
                     note=note.strip() if isinstance(note, str) else "")
    item.full_clean()
    item.save()
    _recalculate_order(order)
    seat_description = f"; vị trí khách {item.seat_number}" if item.seat_number else "; món dùng chung"
    _save(actor, order, "Thêm món", f"Dòng #{item.pk}: {item}; {item.unit_price} đồng/{item.unit_name}{seat_description}; ghi chú: {item.note}")
    return item


@transaction.atomic
def add_items(*, actor, order_id, expected_revision, items):
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision)
    if not isinstance(items, list) or not items or len(items) > 50:
        raise ValidationError("Hãy chọn từ 1 đến 50 món trong mỗi lần thêm.")

    dish_ids = [item.get("dish_id") for item in items if isinstance(item, dict)]
    if len(dish_ids) != len(items) or len(set(dish_ids)) != len(dish_ids):
        raise ValidationError("Danh sách món đã chọn không hợp lệ.")
    dishes = {
        dish.pk: dish
        for dish in Dish.objects.select_related("category", "unit").filter(pk__in=dish_ids)
    }
    if len(dishes) != len(dish_ids):
        raise ValidationError("Một món không còn tồn tại. Hãy tải lại thực đơn.")

    created = []
    for data in items:
        dish = dishes[data["dish_id"]]
        if not dish.is_orderable:
            raise ValidationError(f"{dish.name} đã hết hoặc ngừng phục vụ. Hãy chọn món khác.")
        quantity = data.get("quantity")
        _validate_quantity(quantity)
        seat_number = _normalize_seat_number(order, data.get("seat_number"))
        note = data.get("note", "").strip() if isinstance(data.get("note", ""), str) else ""
        if len(note) > 500:
            raise ValidationError(f"Ghi chú của {dish.name} không được dài quá 500 ký tự.")
        item = OrderItem(
            order=order,
            dish=dish,
            dish_code=dish.code,
            dish_name=dish.name,
            unit_name=dish.unit.name,
            unit_price=dish.price,
            quantity=quantity,
            seat_number=seat_number,
            note=note,
        )
        item.full_clean()
        item.save()
        created.append(item)

    _recalculate_order(order)

    description = "; ".join(
        f"#{item.pk} {item.dish_name} × {item.quantity} {item.unit_name}"
        + (f" · khách {item.seat_number}" if item.seat_number else " · dùng chung")
        + (f" ({item.note})" if item.note else "")
        for item in created
    )
    _save(actor, order, f"Thêm {len(created)} món", description)
    return created


def expire_qr_check_in_requests(*, at=None):
    now = at or timezone.now()
    return QRCheckInRequest.objects.filter(
        status=QRCheckInRequest.Status.WAITING_CONFIRMATION,
        expires_at__lte=now,
    ).update(status=QRCheckInRequest.Status.EXPIRED)


@transaction.atomic
def create_qr_check_in_request(*, token, guest_count):
    token = DiningTableQRToken.objects.select_for_update().select_related("table__area").filter(token=token).first()
    if token is None or not token.is_valid:
        raise ValidationError("Mã QR không hợp lệ hoặc đã hết hiệu lực.")
    table = DiningTable.objects.select_for_update().select_related("area").get(pk=token.table_id)
    _validate_quantity(guest_count)
    if guest_count > table.capacity:
        raise ValidationError({"guest_count": "Số khách vượt quá sức chứa của bàn."})
    expire_qr_check_in_requests()
    active_orders = Order.objects.select_for_update().filter(
        table=table, status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
    )
    if table.status == DiningTable.Status.OCCUPIED and active_orders.count() == 1:
        raise ValidationError("Bàn đã được nhận. Hãy tải lại trang để gọi món.")
    if table.status not in (DiningTable.Status.AVAILABLE, DiningTable.Status.RESERVED):
        raise ValidationError("Bàn đang được dọn hoặc chưa sẵn sàng. Vui lòng gọi nhân viên.")
    existing = QRCheckInRequest.objects.filter(
        table=table, status=QRCheckInRequest.Status.WAITING_CONFIRMATION,
    ).first()
    if existing:
        return existing
    return QRCheckInRequest.objects.create(table=table, guest_count=guest_count)


@transaction.atomic
def confirm_qr_check_in_request(*, actor, request_id):
    actor = _lock_actor(actor)
    check_in = QRCheckInRequest.objects.select_for_update().select_related("table__area").get(pk=request_id)
    if check_in.status != QRCheckInRequest.Status.WAITING_CONFIRMATION:
        raise ValidationError("Yêu cầu nhận bàn này đã được xử lý.")
    if check_in.expires_at <= timezone.now():
        check_in.status = QRCheckInRequest.Status.EXPIRED
        check_in.save(update_fields=("status",))
        raise ValidationError("Yêu cầu nhận bàn đã hết hạn. Khách cần gửi lại từ mã QR.")
    table = DiningTable.objects.select_for_update().get(pk=check_in.table_id)
    active_orders = list(Order.objects.select_for_update().filter(
        table=table, status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
    ).order_by("-opened_at", "-pk")[:2])
    if table.status == DiningTable.Status.OCCUPIED and len(active_orders) == 1:
        order = active_orders[0]
    elif table.status == DiningTable.Status.AVAILABLE:
        order = open_table(
            actor=actor,
            table_id=table.pk,
            guest_count=check_in.guest_count,
            note=f"Nhận bàn từ yêu cầu QR {check_in}",
        )
    elif table.status == DiningTable.Status.RESERVED:
        raise ValidationError("Bàn đang giữ cho lịch đặt. Hãy nhận khách từ lịch đặt bàn; trang QR sẽ tự mở sau đó.")
    else:
        raise ValidationError("Bàn hiện chưa sẵn sàng để nhận khách.")
    check_in.status = QRCheckInRequest.Status.CONFIRMED
    check_in.order = order
    check_in.confirmed_by = actor
    check_in.confirmed_at = timezone.now()
    check_in.save(update_fields=("status", "order", "confirmed_by", "confirmed_at"))
    _log(actor, order, "Xác nhận nhận bàn QR", f"{check_in}; bàn {table.code}; {check_in.guest_count} khách.")
    return check_in


@transaction.atomic
def reject_qr_check_in_request(*, actor, request_id, reason):
    actor = _lock_actor(actor)
    check_in = QRCheckInRequest.objects.select_for_update().get(pk=request_id)
    if check_in.status != QRCheckInRequest.Status.WAITING_CONFIRMATION:
        raise ValidationError("Yêu cầu nhận bàn này đã được xử lý.")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 500:
        raise ValidationError({"reason": "Vui lòng nhập lý do từ chối, tối đa 500 ký tự."})
    check_in.status = QRCheckInRequest.Status.REJECTED
    check_in.rejected_by = actor
    check_in.rejected_at = timezone.now()
    check_in.reject_reason = reason
    check_in.save(update_fields=("status", "rejected_by", "rejected_at", "reject_reason"))
    return check_in


def _client_request_uuid(value):
    if value in (None, ""):
        return uuid4()
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError("Mã chống gửi trùng không hợp lệ. Hãy tải lại trang và thử lại.") from exc


@transaction.atomic
def create_qr_order_request(*, token, items, customer=None, note="", client_request_id=None):
    """Capture a customer QR cart without mutating the active Order or inventory."""
    token = DiningTableQRToken.objects.select_for_update().select_related("table__area").filter(token=token).first()
    if token is None or not token.is_valid:
        raise ValidationError("Mã QR không hợp lệ hoặc đã hết hiệu lực.")
    table = DiningTable.objects.select_for_update().select_related("area").get(pk=token.table_id)
    if table.status != DiningTable.Status.OCCUPIED:
        raise ValidationError("Bàn hiện chưa được mở. Vui lòng liên hệ nhân viên.")
    active_orders = list(Order.objects.select_for_update().filter(
        table=table, status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
    ).order_by("-opened_at", "-pk")[:2])
    if len(active_orders) != 1:
        raise ValidationError("Bàn chưa có đúng một đơn đang phục vụ.")
    client_request_id = _client_request_uuid(client_request_id)
    existing = QROrderRequest.objects.filter(client_request_id=client_request_id).first()
    if existing is not None:
        if existing.table_id != table.pk:
            raise ValidationError("Mã gửi yêu cầu đã được sử dụng ở bàn khác.")
        existing.was_created = False
        return existing
    if not isinstance(items, list) or not items or len(items) > 50:
        raise ValidationError("Giỏ hàng phải có từ 1 đến 50 món.")
    dish_ids = [item.get("dish_id") for item in items if isinstance(item, dict)]
    if len(dish_ids) != len(items) or len(set(dish_ids)) != len(dish_ids):
        raise ValidationError("Danh sách món trong giỏ không hợp lệ.")
    dishes = {
        dish.pk: dish
        for dish in Dish.objects.select_related("category", "unit").filter(pk__in=dish_ids)
    }
    if len(dishes) != len(dish_ids):
        raise ValidationError("Một món không còn tồn tại. Hãy tải lại menu.")
    request_note = note.strip() if isinstance(note, str) else ""
    if len(request_note) > 500:
        raise ValidationError("Ghi chú yêu cầu không được dài quá 500 ký tự.")
    request = QROrderRequest.objects.create(
        table=table,
        order=active_orders[0],
        customer=customer,
        note=request_note,
        client_request_id=client_request_id,
    )
    request_items = []
    for data in items:
        dish = dishes[data["dish_id"]]
        if not dish.is_orderable:
            raise ValidationError(f"{dish.name} đã hết hoặc ngừng phục vụ. Hãy chọn món khác.")
        quantity = data.get("quantity")
        _validate_quantity(quantity)
        item_note = data.get("note", "")
        if not isinstance(item_note, str) or len(item_note.strip()) > 500:
            raise ValidationError(f"Ghi chú của {dish.name} không được dài quá 500 ký tự.")
        request_items.append(QROrderRequestItem(
            request=request, dish=dish, quantity=quantity,
            note=item_note.strip(), unit_price_snapshot=dish.price,
        ))
    QROrderRequestItem.objects.bulk_create(request_items)
    _log(None, active_orders[0], "Khách gửi yêu cầu gọi món QR", "; ".join(
        f"{dish.name} × {data['quantity']}" for dish, data in ((dishes[item["dish_id"]], item) for item in items)
    ))
    request.was_created = True
    return request


@transaction.atomic
def create_qr_service_request(*, token, request_type, note="", client_request_id=None):
    token = DiningTableQRToken.objects.select_for_update().filter(token=token).first()
    if token is None or not token.is_valid:
        raise ValidationError("Mã QR không hợp lệ hoặc đã hết hiệu lực.")
    table = DiningTable.objects.select_for_update().get(pk=token.table_id)
    if table.status != DiningTable.Status.OCCUPIED:
        raise ValidationError("Bàn không còn trong trạng thái phục vụ.")
    orders = list(
        Order.objects.select_for_update()
        .filter(table=table, status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS))
        .order_by("-opened_at", "-pk")[:2]
    )
    if len(orders) != 1:
        raise ValidationError("Không xác định được Order đang phục vụ của bàn.")
    if request_type not in QRServiceRequest.RequestType.values:
        raise ValidationError("Loại yêu cầu phục vụ không hợp lệ.")
    note = note.strip() if isinstance(note, str) else ""
    if len(note) > 300:
        raise ValidationError("Ghi chú yêu cầu phục vụ tối đa 300 ký tự.")

    client_request_id = _client_request_uuid(client_request_id)
    existing = QRServiceRequest.objects.filter(client_request_id=client_request_id).first()
    if existing is not None:
        if existing.table_id != table.pk:
            raise ValidationError("Mã gửi yêu cầu đã được sử dụng ở bàn khác.")
        existing.was_created = False
        return existing
    existing = QRServiceRequest.objects.filter(
        table=table,
        request_type=request_type,
        status=QRServiceRequest.Status.WAITING,
    ).first()
    if existing is not None:
        existing.was_created = False
        return existing

    service_request = QRServiceRequest.objects.create(
        table=table,
        order=orders[0],
        request_type=request_type,
        note=note,
        client_request_id=client_request_id,
    )
    _log(None, orders[0], "Khách gọi phục vụ qua QR", service_request.get_request_type_display())
    service_request.was_created = True
    return service_request


@transaction.atomic
def complete_qr_service_request(*, actor, request_id):
    actor = _lock_actor(actor, "manage_order")
    service_request = QRServiceRequest.objects.select_for_update().select_related("order", "table").get(
        pk=request_id
    )
    if service_request.status != QRServiceRequest.Status.WAITING:
        raise ValidationError("Yêu cầu phục vụ này đã được xử lý.")
    service_request.status = QRServiceRequest.Status.COMPLETED
    service_request.completed_by = actor
    service_request.completed_at = timezone.now()
    service_request.save(update_fields=("status", "completed_by", "completed_at"))
    _log(
        actor,
        service_request.order,
        "Hoàn tất yêu cầu QR",
        f"{service_request.get_request_type_display()} tại bàn {service_request.table.code}.",
    )
    return service_request


@transaction.atomic
def confirm_qr_order_request(*, actor, request_id):
    actor = _lock_actor(actor, "manage_order")
    qr_request = QROrderRequest.objects.select_for_update().select_related("table").get(pk=request_id)
    order = Order.objects.select_for_update().get(pk=qr_request.order_id)
    if qr_request.status != QROrderRequest.Status.WAITING_CONFIRMATION:
        raise ValidationError("Yêu cầu này đã được xử lý.")
    if qr_request.table_id != order.table_id or order.status not in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        raise ValidationError("Bàn hoặc Order hiện tại không còn hợp lệ.")
    if qr_request.table.status != DiningTable.Status.OCCUPIED:
        raise ValidationError("Bàn hiện không còn đang phục vụ.")
    items = list(qr_request.items.select_related("dish__category", "dish__unit").select_for_update())
    if not items:
        raise ValidationError("Yêu cầu không có món.")
    for item in items:
        if not item.dish.is_orderable:
            raise ValidationError(f"{item.dish.name} hiện không còn phục vụ.")
    created_order_items = []
    for request_item in items:
        order_item = OrderItem(
            order=order,
            dish=request_item.dish,
            dish_code=request_item.dish.code,
            dish_name=request_item.dish.name,
            unit_name=request_item.dish.unit.name,
            unit_price=request_item.unit_price_snapshot,
            quantity=request_item.quantity,
            note=request_item.note,
            status=OrderItem.Status.DRAFT,
        )
        order_item.full_clean()
        order_item.save()
        request_item.order_item = order_item
        request_item.save(update_fields=("order_item",))
        created_order_items.append(order_item)
    _recalculate_order(order)
    order.revision += 1
    order.save(update_fields=("subtotal", "total_amount", "revision", "updated_at"))
    _send_items_to_kitchen(actor=actor, order=order, items=created_order_items)
    qr_request.status = QROrderRequest.Status.CONFIRMED
    qr_request.confirmed_by = actor
    qr_request.confirmed_at = timezone.now()
    qr_request.save(update_fields=("status", "confirmed_by", "confirmed_at"))
    _log(actor, order, "Xác nhận yêu cầu QR", f"{qr_request}: {', '.join(f'{item.dish.name} × {item.quantity}' for item in items)}; đã gửi Bếp.")
    return qr_request


@transaction.atomic
def reject_qr_order_request(*, actor, request_id, reason):
    actor = _lock_actor(actor, "manage_order")
    qr_request = QROrderRequest.objects.select_for_update().select_related("order").get(pk=request_id)
    if qr_request.status != QROrderRequest.Status.WAITING_CONFIRMATION:
        raise ValidationError("Yêu cầu này đã được xử lý.")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 500:
        raise ValidationError({"reason": "Vui lòng nhập lý do từ chối, tối đa 500 ký tự."})
    qr_request.status = QROrderRequest.Status.REJECTED
    qr_request.rejected_by = actor
    qr_request.rejected_at = timezone.now()
    qr_request.reject_reason = reason
    qr_request.save(update_fields=("status", "rejected_by", "rejected_at", "reject_reason"))
    _log(actor, qr_request.order, "Từ chối yêu cầu QR", f"{qr_request}: {reason}")
    return qr_request


@transaction.atomic
def edit_item(*, actor, order_id, item_id, expected_revision, quantity, note="", seat_number=None):
    actor = _lock_actor(actor)
    _validate_quantity(quantity)
    order = _order(order_id, expected_revision)
    seat_number = _normalize_seat_number(order, seat_number)
    item = order.items.select_for_update().get(pk=item_id)
    if item.status != OrderItem.Status.DRAFT:
        raise ValidationError("Chỉ sửa số lượng hoặc ghi chú của món chưa gửi Bếp. Muốn gọi thêm, hãy thêm dòng món mới.")
    _available_dish(item.dish_id)
    before = (item.quantity, item.seat_number, item.note)
    item.quantity, item.seat_number, item.note = quantity, seat_number, note.strip() if isinstance(note, str) else ""
    item.full_clean()
    if before != (item.quantity, item.seat_number, item.note):
        item.save(update_fields=("quantity", "seat_number", "note"))
        _recalculate_order(order)
        _save(actor, order, "Sửa món chưa gửi", f"Dòng #{item.pk} {item.dish_name}; trước: {before}; sau: ({item.quantity}, {item.seat_number}, {item.note}).")
    return item


@transaction.atomic
def remove_draft_item(*, actor, order_id, item_id, expected_revision):
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision)
    item = order.items.select_for_update().get(pk=item_id)
    if item.status != OrderItem.Status.DRAFT:
        raise ValidationError("Chỉ xóa được món chưa gửi Bếp.")
    description = f"Xóa dòng #{item.pk}: {item.dish_name} × {item.quantity}."
    item.delete()
    _recalculate_order(order)
    _save(actor, order, "Xóa món DRAFT", description)
    return order


@transaction.atomic
def open_table(*, actor, table_id, guest_count, customer_id=None, reservation_id=None, note=""):
    actor = _lock_actor(actor)
    _validate_quantity(guest_count)
    table = DiningTable.objects.select_for_update().select_related("area").get(pk=table_id)
    if not table.is_active or not table.area.is_active:
        raise ValidationError("Bàn hoặc khu vực đã ngừng sử dụng.")
    if table.status not in (DiningTable.Status.AVAILABLE, DiningTable.Status.RESERVED):
        raise ValidationError("Bàn không còn sẵn sàng để mở.")
    if guest_count > table.capacity:
        raise ValidationError({"guest_count": "Số khách vượt quá sức chứa của bàn."})
    reservation = None
    if reservation_id:
        reservation = Booking.objects.select_for_update().filter(pk=reservation_id, table=table).first()
        if reservation is None or reservation.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.SEATED):
            raise ValidationError("Đặt bàn không còn hợp lệ.")
    elif table.status == DiningTable.Status.RESERVED:
        raise ValidationError("Bàn đang được giữ chỗ; hãy chọn đúng lượt đặt bàn.")
    else:
        from apps.bookings.duration import planned_end
        from apps.bookings.selectors import default_duration_minutes, overlapping_bookings
        now = timezone.now()
        if overlapping_bookings(
            table_id=table.pk,
            starts_at=now,
            ends_at=planned_end(now, default_duration_minutes()),
        ).exists():
            raise ValidationError("Bàn sắp có lịch đặt trong thời gian phục vụ dự kiến. Hãy chọn bàn khác hoặc nhận đúng lịch đặt.")
    customer = Customer.objects.filter(pk=customer_id).first() if customer_id else None
    order = Order.objects.create(
        booking=reservation,
        table=table,
        customer=customer or (reservation.customer if reservation else None),
        employee=getattr(actor, "employee_profile", None),
        guest_count=guest_count,
        status=Order.Status.OPEN,
        note=(note or "").strip(),
        created_by=actor,
        opened_at=timezone.now(),
    )
    order.order_code = f"DH{order.pk:06d}"
    order.save(update_fields=("order_code",))
    if reservation and reservation.status != Booking.Status.SEATED:
        reservation.status = Booking.Status.SEATED
        reservation.seated_at = order.opened_at
        reservation.revision += 1
        reservation.save(update_fields=("status", "seated_at", "revision", "updated_at"))
    table.status = DiningTable.Status.OCCUPIED
    table.save(update_fields=("status", "updated_at"))
    _log(actor, order, "Mở bàn", f"{actor.username} mở bàn {table.code} cho {guest_count} khách.")
    return order


@transaction.atomic
def request_payment(*, actor, order_id, expected_revision, note=""):
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision, require_open=False)
    if order.status not in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        raise ValidationError("Đơn không thể gửi yêu cầu thanh toán.")
    if not order.items.exclude(status=OrderItem.Status.CANCELLED).exists():
        raise ValidationError("Đơn chưa có món để thanh toán.")
    if order.items.exclude(status__in=(OrderItem.Status.SERVED, OrderItem.Status.CANCELLED)).exists():
        raise ValidationError("Còn món chưa phục vụ xong.")
    payment_request, created = PaymentRequest.objects.select_for_update().get_or_create(
        order=order,
        status=PaymentRequest.Status.WAITING,
        defaults={"requested_by": actor, "note": (note or "").strip()},
    )
    if not created:
        raise ValidationError("Đơn đã có yêu cầu thanh toán đang chờ.")
    order.status = Order.Status.PAYMENT_REQUESTED
    _recalculate_order(order)
    _save(actor, order, "Yêu cầu thanh toán", f"{actor.username} gửi yêu cầu thanh toán cho bàn {order.table.code}.")
    return payment_request


def _assert_check_can_be_rearranged(order):
    if order.status != Order.Status.PAYMENT_REQUESTED:
        raise ValidationError("Chỉ tách hoặc ghép khi hóa đơn đang chờ thanh toán.")
    if Invoice.objects.filter(order=order).exists():
        raise ValidationError("Hóa đơn đã phát sinh giao dịch nên không thể tách hoặc ghép.")
    if order.online_payments.filter(status=OnlinePayment.Status.PENDING).exists():
        raise ValidationError("Đơn đang có giao dịch trực tuyến chờ xử lý.")


def _clear_order_discounts(order):
    order.discount_amount = Decimal("0")
    order.promotion_code_snapshot = ""
    order.promotion_discount_amount = Decimal("0")
    _recalculate_order(order)


@transaction.atomic
def split_order(*, actor, order_id, expected_revision, quantities):
    """Move selected served item quantities into a separately payable check."""
    actor = _lock_actor(actor, "collect_payment")
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.revision != expected_revision:
        raise ValidationError("Đơn đã thay đổi. Hãy tải lại trang trước khi tách hóa đơn.")
    _assert_check_can_be_rearranged(order)

    items = list(OrderItem.objects.select_for_update().filter(order=order).exclude(status=OrderItem.Status.CANCELLED))
    if not items or any(item.status != OrderItem.Status.SERVED for item in items):
        raise ValidationError("Chỉ tách hóa đơn sau khi tất cả món đã được phục vụ.")
    normalized = {}
    for raw_item_id, raw_quantity in (quantities or {}).items():
        try:
            item_id, quantity = int(raw_item_id), int(raw_quantity)
        except (TypeError, ValueError) as error:
            raise ValidationError("Món hoặc số lượng tách không hợp lệ.") from error
        if quantity > 0:
            normalized[item_id] = quantity
    selected = {item.pk: item for item in items if item.pk in normalized}
    if not selected:
        raise ValidationError("Hãy chọn ít nhất một món để tách.")
    if set(normalized) - set(selected):
        raise ValidationError("Một món đã thay đổi hoặc không còn thuộc hóa đơn.")
    for item_id, quantity in normalized.items():
        if quantity > selected[item_id].quantity:
            raise ValidationError({"quantities": f"Số lượng tách của {selected[item_id].dish_name} vượt quá số lượng hiện có."})
    if sum(item.quantity - normalized.get(item.pk, 0) for item in items) <= 0:
        raise ValidationError("Hóa đơn gốc phải còn ít nhất một món.")

    root = Order.objects.select_for_update().get(pk=order.split_root_id) if order.split_root_id else order
    child = Order.objects.create(
        split_root=root,
        table=order.table,
        customer=order.customer,
        employee=order.employee,
        guest_count=1,
        status=Order.Status.PAYMENT_REQUESTED,
        note=f"Hóa đơn tách từ {order.order_code}",
        created_by=actor,
        opened_at=order.opened_at or timezone.now(),
    )
    child.order_code = f"DH{child.pk:06d}"
    child.save(update_fields=("order_code",))

    moved_descriptions = []
    for item_id, quantity in normalized.items():
        item = selected[item_id]
        moved_descriptions.append(f"{quantity} × {item.dish_name}")
        if quantity == item.quantity:
            item.order = child
            item.save(update_fields=("order", "updated_at"))
        else:
            item.quantity -= quantity
            item.save(update_fields=("quantity", "updated_at"))
            OrderItem.objects.create(
                order=child,
                dish=item.dish,
                dish_code=item.dish_code,
                dish_name=item.dish_name,
                unit_name=item.unit_name,
                unit_price=item.unit_price,
                quantity=quantity,
                seat_number=item.seat_number,
                unit_cost_snapshot=item.unit_cost_snapshot,
                note=item.note,
                status=item.status,
                inventory_deducted_at=item.inventory_deducted_at,
                inventory_returned_at=item.inventory_returned_at,
                sent_at=item.sent_at,
                started_at=item.started_at,
                ready_at=item.ready_at,
                served_at=item.served_at,
            )

    _clear_order_discounts(order)
    order.revision += 1
    order.save(update_fields=("subtotal", "discount_amount", "promotion_code_snapshot", "promotion_discount_amount", "total_amount", "revision", "updated_at"))
    _clear_order_discounts(child)
    child.save(update_fields=("subtotal", "discount_amount", "promotion_code_snapshot", "promotion_discount_amount", "total_amount", "updated_at"))
    PaymentRequest.objects.create(order=child, requested_by=actor, note=f"Tách từ {order.order_code}")
    description = f"Tách sang {child.order_code}: {', '.join(moved_descriptions)}. Mã giảm giá được xóa để tính riêng từng hóa đơn."
    _log(actor, order, "Tách hóa đơn", description)
    _log(actor, child, "Nhận hóa đơn tách", f"Tách từ {order.order_code}: {', '.join(moved_descriptions)}.")
    return child


@transaction.atomic
def merge_split_order(*, actor, order_id, expected_revision):
    """Merge an unpaid child check back into its active root check."""
    actor = _lock_actor(actor, "collect_payment")
    source = Order.objects.select_for_update().get(pk=order_id)
    if source.revision != expected_revision:
        raise ValidationError("Đơn đã thay đổi. Hãy tải lại trang trước khi ghép hóa đơn.")
    if not source.split_root_id:
        raise ValidationError("Đây không phải hóa đơn được tách.")
    target = Order.objects.select_for_update().get(pk=source.split_root_id)
    _assert_check_can_be_rearranged(source)
    _assert_check_can_be_rearranged(target)
    if source.table_id != target.table_id:
        raise ValidationError("Hai hóa đơn không còn thuộc cùng một bàn.")

    moved_items = list(OrderItem.objects.select_for_update().filter(order=source))
    if not moved_items:
        raise ValidationError("Hóa đơn tách không còn món để ghép.")
    OrderItem.objects.filter(pk__in=[item.pk for item in moved_items]).update(order=target, updated_at=timezone.now())
    _clear_order_discounts(target)
    target.revision += 1
    target.save(update_fields=("subtotal", "discount_amount", "promotion_code_snapshot", "promotion_discount_amount", "total_amount", "revision", "updated_at"))
    PaymentRequest.objects.filter(order=source, status__in=(PaymentRequest.Status.WAITING, PaymentRequest.Status.PROCESSING)).update(
        status=PaymentRequest.Status.CANCELLED, processed_at=timezone.now()
    )
    source.status = Order.Status.CANCELLED
    source.subtotal = Decimal("0")
    source.discount_amount = Decimal("0")
    source.promotion_code_snapshot = ""
    source.promotion_discount_amount = Decimal("0")
    source.total_amount = Decimal("0")
    source.closed_at = timezone.now()
    source.revision += 1
    source.save()
    _log(actor, target, "Ghép hóa đơn", f"Nhận lại {len(moved_items)} dòng món từ {source.order_code}.")
    _log(actor, source, "Ghép về hóa đơn gốc", f"Đã ghép toàn bộ món về {target.order_code}.")
    return target


@transaction.atomic
def prepare_quick_payment(*, actor, order_id):
    """Move a fully served table to payment from the table overview."""
    actor = _lock_actor(actor, "collect_payment")
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == Order.Status.PAYMENT_REQUESTED:
        return order
    if order.status not in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        raise ValidationError("Đơn không còn ở trạng thái có thể thanh toán.")
    items = list(order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED))
    if not items:
        raise ValidationError("Bàn chưa có món để thanh toán.")
    if any(item.status != OrderItem.Status.SERVED for item in items):
        raise ValidationError("Cần phục vụ xong tất cả món trước khi thanh toán nhanh.")
    PaymentRequest.objects.select_for_update().get_or_create(
        order=order,
        status=PaymentRequest.Status.WAITING,
        defaults={"requested_by": actor, "note": "Thanh toán nhanh từ sơ đồ bàn"},
    )
    order.status = Order.Status.PAYMENT_REQUESTED
    _recalculate_order(order)
    _save(actor, order, "Yêu cầu thanh toán nhanh", f"{actor.username} mở thanh toán nhanh cho bàn {order.table.code}.")
    return order


@transaction.atomic
def process_payment(*, actor, order_id, payment_method, transaction_code="", promotion_code=None):
    actor = _lock_actor(actor, "collect_payment")
    if payment_method not in (Payment.Method.CASH, Payment.Method.BANK_TRANSFER):
        raise ValidationError({"payment_method": "Chỉ hỗ trợ tiền mặt hoặc chuyển khoản."})
    transaction_code = (transaction_code or "").strip()
    if len(transaction_code) > 100:
        raise ValidationError({"transaction_code": "Mã giao dịch không được dài quá 100 ký tự."})
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAYMENT_REQUESTED:
        raise ValidationError("Đơn chưa ở trạng thái yêu cầu thanh toán.")
    items = list(order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED))
    if not items:
        raise ValidationError("Đơn không có món để thanh toán.")
    preview = payment_preview(order, promotion_code=promotion_code)
    _store_promotion(order, preview)
    subtotal = preview["subtotal"]
    discount_percent = preview["discount_percent"]
    discount_amount = preview["discount"]
    total = preview["due"]
    return _complete_payment(
        order=order,
        subtotal=subtotal,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        membership_discount_amount=preview["membership_discount"],
        promotion_code=preview["promotion_code"],
        promotion_discount_amount=preview["promotion_discount"],
        total=total,
        payment_method=payment_method,
        reference=transaction_code,
        actor=actor,
        actor_snapshot=actor.username,
    )


def _complete_payment(*, order, subtotal, discount_percent, discount_amount, total,
                      membership_discount_amount=Decimal("0"), promotion_code="", promotion_discount_amount=Decimal("0"),
                      payment_method, reference, actor=None, actor_snapshot=""):
    """Finalize an already locked order exactly once inside the caller's transaction."""
    customer = Customer.objects.select_for_update().filter(pk=order.customer_id).first()
    invoice, _ = Invoice.objects.select_for_update().get_or_create(
        order=order,
        defaults={"invoice_code": _invoice_code_for(order)},
    )
    if invoice.status == Invoice.Status.PAID:
        raise ValidationError("Hóa đơn đã được thanh toán.")
    if invoice.paid_amount > 0:
        raise ValidationError("Hóa đơn đã thu một phần. Hãy tiếp tục bằng chức năng thu nhiều phương thức.")
    now = timezone.now()
    invoice.customer = customer
    invoice.subtotal = subtotal
    invoice.discount_percent = discount_percent
    invoice.discount_amount = discount_amount
    invoice.membership_discount_amount = membership_discount_amount
    invoice.promotion_code = promotion_code
    invoice.promotion_discount_amount = promotion_discount_amount
    invoice.total_amount = total
    invoice.total = total
    invoice.paid_amount = total
    invoice.payment_method = payment_method
    invoice.status = Invoice.Status.PAID
    invoice.closed_at = now
    invoice.save()
    if total > 0:
        Payment.objects.create(
            invoice=invoice,
            amount=total,
            method=payment_method,
            reference=reference,
            performed_by=actor,
            actor_snapshot=actor_snapshot,
        )
    return _finalize_paid_invoice(
        order=order, invoice=invoice, customer=customer, actor=actor,
        actor_snapshot=actor_snapshot, now=now,
    )


def _finalize_paid_invoice(*, order, invoice, customer, actor, actor_snapshot, now):
    """Close the order/table only after an invoice has actually been paid in full."""
    table = DiningTable.objects.select_for_update().get(pk=order.table_id)
    PaymentRequest.objects.select_for_update().filter(
        order=order, status__in=(PaymentRequest.Status.WAITING, PaymentRequest.Status.PROCESSING),
    ).update(status=PaymentRequest.Status.COMPLETED, processed_at=now)
    order.subtotal = invoice.subtotal
    order.discount_amount = invoice.discount_amount
    order.promotion_code_snapshot = invoice.promotion_code
    order.promotion_discount_amount = invoice.promotion_discount_amount
    order.total_amount = invoice.total
    order.status = Order.Status.COMPLETED
    order.closed_at = now
    order.revision += 1
    order.save()
    other_open_checks = Order.objects.select_for_update().filter(
        table_id=order.table_id,
        status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS, Order.Status.PAYMENT_REQUESTED),
    ).exclude(pk=order.pk)
    has_other_open_checks = other_open_checks.exists()
    if not has_other_open_checks:
        QRServiceRequest.objects.select_for_update().filter(
            table_id=order.table_id,
            status=QRServiceRequest.Status.WAITING,
        ).update(status=QRServiceRequest.Status.CANCELLED)
    table.status = DiningTable.Status.OCCUPIED if has_other_open_checks else DiningTable.Status.CLEANING
    table.save(update_fields=("status", "updated_at"))
    root_order = order.split_root or order
    if root_order.booking_id and not has_other_open_checks:
        booking = Booking.objects.select_for_update().get(pk=root_order.booking_id)
        booking.status = Booking.Status.COMPLETED
        booking.completed_at = now
        booking.revision += 1
        booking.save(update_fields=("status", "completed_at", "revision", "updated_at"))
    if customer:
        customer.total_spending += invoice.total
        tier = tier_for_spending(customer.total_spending)
        customer.membership_tier = tier
        customer.save(update_fields=("total_spending", "membership_tier", "updated_at"))
    _log(
        actor,
        order,
        "Thanh toán",
        f"{actor_snapshot} thanh toán hóa đơn {invoice.invoice_code}; bàn {table.code} "
        + ("vẫn phục vụ vì còn hóa đơn chưa thanh toán." if has_other_open_checks else "chuyển sang cần dọn."),
        actor_snapshot=actor_snapshot,
    )
    return invoice


@transaction.atomic
def create_vnpay_payment(*, actor, order_id, return_url, ip_address, promotion_code=None):
    actor = _lock_actor(actor, "collect_payment")
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAYMENT_REQUESTED:
        raise ValidationError("Đơn chưa ở trạng thái yêu cầu thanh toán.")
    if Invoice.objects.filter(order=order, paid_amount__gt=0).exists():
        raise ValidationError("Hóa đơn đã thu một phần nên không thể chuyển sang VNPAY.")
    if not order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED).exists():
        raise ValidationError("Đơn không có món để thanh toán.")
    preview = payment_preview(order, promotion_code=promotion_code)
    _store_promotion(order, preview)
    order.save(update_fields=("promotion_code_snapshot", "promotion_discount_amount", "discount_amount", "total_amount", "updated_at"))
    if preview["due"] <= 0:
        raise ValidationError("Hóa đơn 0 đồng không thể gửi sang cổng thanh toán.")

    now = timezone.now()
    txn_ref = f"VNP{order.pk}-{now:%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
    online_payment = OnlinePayment.objects.create(
        order=order,
        txn_ref=txn_ref,
        amount=preview["due"],
        subtotal=preview["subtotal"],
        discount_percent=preview["discount_percent"],
        discount_amount=preview["discount"],
        membership_discount_amount=preview["membership_discount"],
        promotion_code=preview["promotion_code"],
        promotion_discount_amount=preview["promotion_discount"],
    )
    local_now = timezone.localtime(now)
    params = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_Amount": str(int(online_payment.amount * 100)),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": f"Thanh toan hoa don {order.order_code}",
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": settings.VNPAY_RETURN_URL or return_url,
        "vnp_IpAddr": ip_address or "127.0.0.1",
        "vnp_CreateDate": local_now.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": (local_now + timedelta(minutes=15)).strftime("%Y%m%d%H%M%S"),
    }
    return online_payment, payment_url(params)


@transaction.atomic
def process_vnpay_ipn(*, params):
    """Apply a verified VNPAY IPN and return its protocol response code/message."""
    txn_ref = str(params.get("vnp_TxnRef", ""))
    online_payment = OnlinePayment.objects.select_for_update().select_related("order").filter(txn_ref=txn_ref).first()
    if online_payment is None:
        return "01", "Order not found"
    if online_payment.status == OnlinePayment.Status.PAID:
        return "02", "Order already confirmed"
    try:
        callback_amount = Decimal(str(params.get("vnp_Amount", ""))) / Decimal("100")
    except Exception:
        return "04", "Invalid amount"
    if callback_amount != online_payment.amount:
        return "04", "Invalid amount"

    online_payment.response_code = str(params.get("vnp_ResponseCode", ""))[:10]
    online_payment.provider_transaction_no = str(params.get("vnp_TransactionNo", ""))[:30]
    online_payment.bank_code = str(params.get("vnp_BankCode", ""))[:30]
    online_payment.raw_response = dict(params)
    successful = (
        online_payment.response_code == "00"
        and str(params.get("vnp_TransactionStatus", "")) == "00"
    )
    if not successful:
        online_payment.status = OnlinePayment.Status.FAILED
        online_payment.save()
        return "00", "Confirm success"

    order = Order.objects.select_for_update().get(pk=online_payment.order_id)
    if order.status != Order.Status.PAYMENT_REQUESTED:
        if Invoice.objects.filter(order=order, status=Invoice.Status.PAID).exists():
            return "02", "Order already confirmed"
        return "99", "Invalid order status"
    _complete_payment(
        order=order,
        subtotal=online_payment.subtotal,
        discount_percent=online_payment.discount_percent,
        discount_amount=online_payment.discount_amount,
        membership_discount_amount=online_payment.membership_discount_amount,
        promotion_code=online_payment.promotion_code,
        promotion_discount_amount=online_payment.promotion_discount_amount,
        total=online_payment.amount,
        payment_method=Payment.Method.VNPAY,
        reference=online_payment.provider_transaction_no or online_payment.txn_ref,
        actor=None,
        actor_snapshot="VNPAY",
    )
    now = timezone.now()
    online_payment.status = OnlinePayment.Status.PAID
    online_payment.paid_at = now
    online_payment.save()
    OnlinePayment.objects.filter(
        order=order, status=OnlinePayment.Status.PENDING
    ).exclude(pk=online_payment.pk).update(status=OnlinePayment.Status.CANCELLED, updated_at=now)
    return "00", "Confirm success"


@transaction.atomic
def move_table(*, actor, order_id, target_table_id):
    actor = _lock_actor(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
        raise ValidationError("Đơn đã kết thúc, không thể chuyển bàn.")
    root_id = order.split_root_id or order.pk
    if Order.objects.filter(Q(pk=root_id) | Q(split_root_id=root_id)).exclude(status=Order.Status.CANCELLED).count() > 1:
        raise ValidationError("Hãy thanh toán hoặc ghép các hóa đơn đã tách trước khi chuyển bàn.")
    source = DiningTable.objects.select_for_update().get(pk=order.table_id)
    target = DiningTable.objects.select_for_update().select_related("area").get(pk=target_table_id)
    if target.pk == source.pk:
        raise ValidationError("Đơn đang ở bàn này.")
    if target.status != DiningTable.Status.AVAILABLE or not target.is_active or not target.area.is_active:
        raise ValidationError("Bàn đích không còn trống.")
    now = timezone.now()
    booking = Booking.objects.select_for_update().filter(pk=order.booking_id).first() if order.booking_id else None
    if booking is not None:
        if booking.status != Booking.Status.SEATED:
            raise ValidationError("Lượt khách không còn ở trạng thái đang phục vụ.")
        from apps.bookings.selectors import available_transfer_tables
        if not available_transfer_tables(booking, at=now).filter(pk=target.pk).exists():
            raise ValidationError("Bàn đích có khách, không đủ chỗ hoặc vướng lịch đặt trong thời gian còn lại.")
    elif Booking.objects.filter(
        table=target, status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED), starts_at__lte=now,
    ).exists():
        raise ValidationError("Bàn đích đang có lịch giữ chỗ.")
    else:
        from apps.bookings.duration import planned_end
        from apps.bookings.selectors import default_duration_minutes, overlapping_bookings
        if overlapping_bookings(
            table_id=target.pk,
            starts_at=now,
            ends_at=planned_end(now, default_duration_minutes()),
        ).exists():
            raise ValidationError("Bàn đích sắp có lịch đặt trong thời gian phục vụ dự kiến.")
    order.table = target
    order.revision += 1
    order.save(update_fields=("table", "revision", "updated_at"))
    if booking is not None:
        booking.table = target
        booking.revision += 1
        booking.save(update_fields=("table", "revision", "updated_at"))
        BookingActivityLog.objects.create(
            booking=booking,
            action="Chuyển bàn",
            description=f"Đồng bộ đơn {order.order_code}: bàn {source.code} → {target.code}.",
            performed_by=actor,
            actor_snapshot=actor.username,
        )
    target.status = DiningTable.Status.OCCUPIED
    target.save(update_fields=("status", "updated_at"))
    source.status = DiningTable.Status.CLEANING
    source.save(update_fields=("status", "updated_at"))
    _log(actor, order, "Chuyển bàn", f"Chuyển từ bàn {source.code} sang {target.code}; bàn cũ cần dọn.")
    return order


@transaction.atomic
def finish_cleaning(*, actor, table_id):
    actor = _lock_actor(actor)
    table = DiningTable.objects.select_for_update().get(pk=table_id)
    if table.status != DiningTable.Status.CLEANING:
        raise ValidationError("Bàn không ở trạng thái cần dọn.")
    table.status = DiningTable.Status.AVAILABLE
    table.save(update_fields=("status", "updated_at"))
    last_order = Order.objects.filter(table=table).order_by("-opened_at", "-pk").first()
    if last_order:
        _log(actor, last_order, "Hoàn tất dọn bàn", f"{actor.username} đã dọn xong bàn {table.code}.")
    return table


def _send_items_to_kitchen(*, actor, order, items):
    if not items:
        raise ValidationError("Không có món chưa gửi Bếp.")
    for item in items:
        _available_dish(item.dish_id)
    from apps.inventory.services import consume_order_items
    consume_order_items(actor=actor, items=items)
    now = timezone.now()
    order.items.filter(pk__in=[item.pk for item in items]).update(status=OrderItem.Status.PENDING, sent_at=now)
    order.status = Order.Status.IN_PROGRESS
    _save(actor, order, "Gửi Bếp", "; ".join(f"#{item.pk} {item}" for item in items))
    return order


@transaction.atomic
def send_to_kitchen(*, actor, order_id, expected_revision, item_ids=None):
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision)
    items_query = order.items.select_for_update().select_related("dish").filter(status=OrderItem.Status.DRAFT)
    selected_ids = None
    if item_ids is not None:
        try:
            selected_ids = {int(item_id) for item_id in item_ids}
        except (TypeError, ValueError) as exc:
            raise ValidationError("Danh sách món gửi Bếp không hợp lệ.") from exc
        if not selected_ids:
            raise ValidationError("Không có món được chọn để gửi Bếp.")
        items_query = items_query.filter(pk__in=selected_ids)
    items = list(items_query)
    if selected_ids is not None and len(items) != len(selected_ids):
        raise ValidationError("Một món được duyệt không còn ở trạng thái chưa gửi Bếp.")
    return _send_items_to_kitchen(actor=actor, order=order, items=items)


@transaction.atomic
def transition_item(*, actor, order_id, item_id, expected_revision, target, reason=""):
    permission = "work_kitchen" if target in (OrderItem.Status.COOKING, OrderItem.Status.READY) else "manage_order"
    actor = _lock_actor(actor, permission)
    order = _order(order_id, expected_revision)
    item = order.items.select_for_update().get(pk=item_id)
    previous_status = item.status
    transitions = {"PENDING": "COOKING", "COOKING": "READY", "READY": "SERVED"}
    if target == OrderItem.Status.CANCELLED:
        if item.status == OrderItem.Status.CANCELLED:
            raise ValidationError("Món đã được hủy.")
        if item.status in (OrderItem.Status.COOKING, OrderItem.Status.READY, OrderItem.Status.SERVED) and not has_order_permission(actor, "cancel_prepared_item"):
            raise PermissionDenied("Chỉ Quản lí được hủy món đã bắt đầu làm hoặc đã làm xong.")
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason:
            raise ValidationError({"reason": "Vui lòng ghi lý do hủy món."})
        item.cancellation_reason = reason
        item.cancelled_at = timezone.now()
        if previous_status == OrderItem.Status.PENDING:
            from apps.inventory.services import return_order_item_inventory
            return_order_item_inventory(actor=actor, item=item)
    elif transitions.get(item.status) != target:
        raise ValidationError("Không thể chuyển trạng thái món theo cách này.")
    else:
        setattr(item, {"COOKING": "started_at", "READY": "ready_at", "SERVED": "served_at"}[target], timezone.now())
    before = item.get_status_display()
    item.status = target
    item.full_clean()
    item.save()
    _save(actor, order, item.get_status_display(), f"Dòng #{item.pk} {item}: {before} → {item.get_status_display()}." + (f" Lý do: {reason}" if target == OrderItem.Status.CANCELLED else ""))
    return item


@transaction.atomic
def change_order_status(*, actor, order_id, expected_revision, target, reason=""):
    target = {"AWAITING_PAYMENT": Order.Status.PAYMENT_REQUESTED, "VOID": Order.Status.CANCELLED}.get(target, target)
    if target == Order.Status.CANCELLED:
        return cancel_table_order(
            actor=actor,
            order_id=order_id,
            expected_revision=expected_revision,
            reason=reason,
        )
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision, require_open=False)
    live = order.items.exclude(status=OrderItem.Status.CANCELLED)
    if target == Order.Status.PAYMENT_REQUESTED and order.status in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        if not live.exists() or live.exclude(status=OrderItem.Status.SERVED).exists():
            raise ValidationError("Cần phục vụ xong tất cả món chưa hủy trước khi chuyển chờ thanh toán.")
    elif target == Order.Status.OPEN and order.status == Order.Status.PAYMENT_REQUESTED:
        invoice = Invoice.objects.select_for_update().filter(order=order).first()
        if invoice is not None and invoice.paid_amount > 0:
            raise ValidationError("Đơn đã thu một phần nên không thể gọi thêm món. Hãy thu đủ số tiền còn lại.")
    else:
        raise ValidationError("Không thể chuyển trạng thái đơn theo cách này.")
    order.status = target
    _save(actor, order, order.get_status_display(), reason if target == Order.Status.CANCELLED else "Cập nhật trạng thái đơn; chưa ghi nhận thanh toán.")
    return order


@transaction.atomic
def record_payment(*, actor, order_id, expected_revision, amount, payment_method="CASH", reference=""):
    actor = _lock_actor(actor, "collect_payment")
    order = _order(order_id, expected_revision, require_open=False)
    if order.status != Order.Status.PAYMENT_REQUESTED:
        raise ValidationError("Chỉ thanh toán cho đơn đang ở trạng thái chờ thanh toán.")

    try:
        amount_decimal = Decimal(str(amount))
    except Exception as exc:  # pragma: no cover - defensive conversion
        raise ValidationError({"amount": "Số tiền thanh toán không hợp lệ."}) from exc

    if not amount_decimal.is_finite() or amount_decimal != amount_decimal.to_integral_value() or amount_decimal <= 0:
        raise ValidationError({"amount": "Số tiền thanh toán phải là số nguyên lớn hơn 0."})

    if payment_method not in (Payment.Method.CASH, Payment.Method.CARD, Payment.Method.BANK_TRANSFER, Payment.Method.OTHER):
        raise ValidationError({"payment_method": "Phương thức thanh toán không hợp lệ."})
    reference = reference.strip() if isinstance(reference, str) else ""
    if len(reference) > 100:
        raise ValidationError({"reference": "Ghi chú / mã giao dịch không được dài quá 100 ký tự."})

    invoice = Invoice.objects.select_for_update().filter(order=order).first()
    if invoice is None:
        preview = payment_preview(order)
        total = preview["due"]
        if total <= 0:
            raise ValidationError("Đơn hiện không có giá trị thanh toán.")
        customer = Customer.objects.select_for_update().filter(pk=order.customer_id).first()
        _store_promotion(order, preview)
        invoice = Invoice.objects.create(
            order=order,
            invoice_code=_invoice_code_for(order),
            customer=customer,
            subtotal=preview["subtotal"],
            discount_percent=preview["discount_percent"],
            discount_amount=preview["discount"],
            membership_discount_amount=preview["membership_discount"],
            promotion_code=preview["promotion_code"],
            promotion_discount_amount=preview["promotion_discount"],
            total_amount=total,
            total=total,
            status=Invoice.Status.UNPAID,
            payment_method=payment_method,
        )

    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError("Hóa đơn đã bị hủy, không thể thu thêm tiền.")

    remaining = invoice.total - invoice.paid_amount
    if amount_decimal > remaining:
        raise ValidationError({"amount": f"Số tiền thanh toán vượt quá số tiền còn lại ({remaining})."})

    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount_decimal,
        method=payment_method,
        reference=reference,
        performed_by=actor,
        actor_snapshot=actor.username,
    )

    invoice.paid_amount += amount_decimal
    invoice.payment_method = payment_method
    invoice.status = Invoice.Status.PAID if invoice.paid_amount >= invoice.total else Invoice.Status.UNPAID
    if invoice.status == Invoice.Status.PAID:
        now = timezone.now()
        invoice.closed_at = now
    invoice.save(update_fields=("total", "paid_amount", "status", "payment_method", "updated_at", "closed_at"))
    description = f"Thu {amount_decimal} đồng bằng {payment.get_method_display()}. Hóa đơn còn lại {invoice.total - invoice.paid_amount} đồng."
    _log(actor, order, "Thanh toán", description)
    if invoice.status == Invoice.Status.PAID:
        customer = Customer.objects.select_for_update().filter(pk=order.customer_id).first()
        return _finalize_paid_invoice(
            order=order, invoice=invoice, customer=customer, actor=actor,
            actor_snapshot=actor.username, now=now,
        )
    order.revision += 1
    order.save(update_fields=("subtotal", "discount_amount", "promotion_code_snapshot", "promotion_discount_amount", "total_amount", "revision", "updated_at"))
    return invoice


@transaction.atomic
def pay_tables(*, actor, order_ids, payment_method="CASH", reference="", promotion_code=None):
    """Settle several ready tables atomically and link their receipts in one batch."""
    try:
        order_ids = sorted({int(order_id) for order_id in order_ids})
    except (TypeError, ValueError) as exc:
        raise ValidationError({"orders": "Danh sách bàn thanh toán không hợp lệ."}) from exc
    if not order_ids:
        raise ValidationError({"orders": "Hãy chọn ít nhất một bàn cần thanh toán."})
    if len(order_ids) > 50:
        raise ValidationError({"orders": "Mỗi lần chỉ thanh toán tối đa 50 bàn."})
    if payment_method == "TRANSFER":
        payment_method = Payment.Method.BANK_TRANSFER
    if payment_method not in (Payment.Method.CASH, Payment.Method.BANK_TRANSFER):
        raise ValidationError({"payment_method": "Phương thức thanh toán không hợp lệ."})
    reference = reference.strip() if isinstance(reference, str) else ""
    if len(reference) > 100:
        raise ValidationError({"reference": "Ghi chú / mã giao dịch không được dài quá 100 ký tự."})

    existing_ids = list(Order.objects.filter(pk__in=order_ids).values_list("pk", flat=True))
    if len(existing_ids) != len(order_ids):
        raise ValidationError({"orders": "Một đơn hàng không còn tồn tại. Hãy tải lại danh sách."})

    invoices = []
    payments = []
    table_codes = []
    grand_total = Decimal("0")
    for order_id in order_ids:
        prepare_quick_payment(actor=actor, order_id=order_id)
        invoice = process_payment(
            actor=actor,
            order_id=order_id,
            payment_method=payment_method,
            transaction_code=reference,
            promotion_code=promotion_code,
        )
        payment = invoice.payments.order_by("-pk").first()
        invoices.append(invoice)
        if payment:
            payments.append(payment)
        table_codes.append(invoice.order.table.code)
        grand_total += invoice.total_amount

    batch = PaymentBatch.objects.create(
        total=grand_total,
        method="TRANSFER" if payment_method == Payment.Method.BANK_TRANSFER else payment_method,
        reference=reference,
        performed_by=actor,
        actor_snapshot=actor.username,
    )
    if payments:
        Payment.objects.filter(pk__in=[payment.pk for payment in payments]).update(batch=batch)

    return batch, table_codes


def _cancel_locked_order(*, actor, order, table, reason, now):
    """Cancel an unpaid order while its row is locked by the caller."""
    if order.status == Order.Status.COMPLETED:
        raise ValidationError("Đơn đã thanh toán. Hãy dùng Hoàn tất để trả bàn, không thể hủy bàn.")
    if order.status == Order.Status.CANCELLED:
        raise ValidationError("Đơn đã được hủy trước đó.")
    invoice = Invoice.objects.select_for_update().filter(order=order).first()
    if invoice is not None and invoice.paid_amount > 0:
        raise ValidationError("Đơn đã thu một phần. Cần xử lý hoàn tiền trước khi hủy bàn.")

    items = list(order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED))
    if any(item.status != OrderItem.Status.DRAFT for item in items):
        raise ValidationError(
            "Đơn đã có món gửi xuống Bếp nên không thể hủy thẳng cả bàn. "
            "Hãy xử lý từng món theo đúng quyền, sau đó thanh toán hoặc đóng đơn."
        )
    if items:
        order.items.filter(pk__in=[item.pk for item in items]).update(
            status=OrderItem.Status.CANCELLED,
            cancellation_reason=reason,
            cancelled_at=now,
        )
    if invoice is not None:
        invoice.status = Invoice.Status.CANCELLED
        invoice.closed_at = now
        invoice.save(update_fields=("status", "closed_at", "updated_at"))
    order.status = Order.Status.CANCELLED
    order.closed_at = now
    order.revision += 1
    order.save(update_fields=("status", "closed_at", "revision", "updated_at"))
    QRServiceRequest.objects.select_for_update().filter(
        order=order,
        status=QRServiceRequest.Status.WAITING,
    ).update(status=QRServiceRequest.Status.CANCELLED)
    _log(actor, order, "Hủy bàn", f"Hủy đơn và giải phóng bàn {table.code}. Lý do: {reason}")


@transaction.atomic
def cancel_table_order(*, actor, order_id, expected_revision, reason):
    """Cancel a table opened directly from POS, or its linked seated visit."""
    actor = _lock_actor(actor, "manage_order")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 500:
        raise ValidationError({"reason": "Lý do hủy bàn phải có từ 1 đến 500 ký tự."})

    order = Order.objects.select_for_update().get(pk=order_id)
    if order.revision != expected_revision:
        raise ValidationError("Đơn đã thay đổi. Hãy tải lại trang trước khi hủy bàn.")
    if order.table_id is None:
        raise ValidationError("Đơn không gắn với bàn nên không thể dùng thao tác hủy bàn.")
    if order.booking_id and not has_booking_permission(actor, "manage_booking"):
        raise PermissionDenied("Bạn không có quyền hủy lượt khách đang phục vụ.")

    table = DiningTable.objects.select_for_update().get(pk=order.table_id)
    now = timezone.now()
    _cancel_locked_order(actor=actor, order=order, table=table, reason=reason, now=now)

    booking = Booking.objects.select_for_update().filter(pk=order.booking_id).first() if order.booking_id else None
    if booking is not None:
        if booking.status != Booking.Status.SEATED:
            raise ValidationError("Bàn không còn ở trạng thái đang phục vụ.")
        booking.status = Booking.Status.CANCELLED
        booking.completed_at = now
        booking.revision += 1
        booking.save(update_fields=("status", "completed_at", "revision", "updated_at"))
        BookingActivityLog.objects.create(
            booking=booking,
            action="Hủy bàn",
            description=f"Khách không tiếp tục sử dụng bàn {table.code}. Lý do: {reason}",
            performed_by=actor,
            actor_snapshot=actor.username,
        )

    table.status = DiningTable.Status.CLEANING
    table.save(update_fields=("status", "updated_at"))
    return table


@transaction.atomic
def cancel_table_visit(*, actor, booking_id, expected_revision, reason):
    actor = _lock_actor(actor, "manage_order")
    if not has_booking_permission(actor, "manage_booking"):
        raise PermissionDenied("Bạn không có quyền hủy lượt khách đang phục vụ.")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 500:
        raise ValidationError({"reason": "Lý do hủy bàn phải có từ 1 đến 500 ký tự."})

    booking = Booking.objects.select_for_update().select_related("table").get(pk=booking_id)
    if booking.status != Booking.Status.SEATED:
        raise ValidationError("Bàn không còn ở trạng thái đang phục vụ.")
    if booking.revision != expected_revision:
        raise ValidationError("Lượt khách đã thay đổi. Hãy tải lại trang trước khi hủy bàn.")

    order = Order.objects.select_for_update().filter(booking=booking).first()
    now = timezone.now()
    if order is not None:
        _cancel_locked_order(actor=actor, order=order, table=booking.table, reason=reason, now=now)

    table_code = booking.table.code
    booking.status = Booking.Status.CANCELLED
    booking.completed_at = now
    booking.revision += 1
    booking.save(update_fields=("status", "completed_at", "revision", "updated_at"))
    BookingActivityLog.objects.create(
        booking=booking,
        action="Hủy bàn",
        description=f"Khách không tiếp tục sử dụng bàn {table_code}. Lý do: {reason}",
        performed_by=actor,
        actor_snapshot=actor.username,
    )
    booking.table.status = DiningTable.Status.CLEANING
    booking.table.save(update_fields=("status", "updated_at"))
    return booking, table_code
