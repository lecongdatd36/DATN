from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.seating_lock import lock_seating_schedule
from core.menu_lock import lock_menu
from apps.bookings.models import Booking, BookingActivityLog
from apps.bookings.permissions import has_booking_permission
from apps.bookings.services import seat_walk_in
from apps.menu.models import Dish
from apps.customers.models import Customer, MembershipTier
from apps.seating.models import DiningTable
from .models import Invoice, Order, OrderItem, OrderActivityLog, Payment, PaymentBatch, PaymentRequest
from .permissions import has_order_permission


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


def _log(actor, order, action, description):
    OrderActivityLog.objects.create(order=order, action=action, description=description, performed_by=actor, actor_snapshot=actor.username)


def _save(actor, order, action, description):
    order.revision += 1
    order.save(update_fields=("status", "subtotal", "discount_amount", "total_amount", "revision", "updated_at"))
    _log(actor, order, action, description)


def _invoice_code_for(order):
    # Mỗi lượt chỉ có một đơn và mỗi đơn chỉ có một hóa đơn, nên mã dựa trên
    # khóa chính của đơn vừa ổn định vừa không tranh chấp khi thu tiền đồng thời.
    return f"HD{order.pk:06d}"


def payment_preview(order):
    """Return the authoritative loyalty discount preview for an order."""
    subtotal = order.total
    customer = order.customer
    tier = None
    if customer:
        tier = MembershipTier.objects.filter(
            is_active=True,
            minimum_spending__lte=customer.total_spending,
        ).order_by("-minimum_spending", "-pk").first()
    discount_percent = tier.discount_percent if tier else Decimal("0")
    discount = (subtotal * discount_percent / Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return {
        "subtotal": subtotal,
        "tier": tier,
        "discount_percent": discount_percent,
        "discount": discount,
        "due": subtotal - discount,
    }


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
def add_item(*, actor, order_id, expected_revision, dish_id, quantity, note=""):
    actor = _lock_actor(actor)
    _validate_quantity(quantity)
    order = _order(order_id, expected_revision)
    dish = _available_dish(dish_id)
    item = OrderItem(order=order, dish=dish, dish_code=dish.code, dish_name=dish.name, unit_name=dish.unit.name,
                     unit_price=dish.price, quantity=quantity, note=note.strip() if isinstance(note, str) else "")
    item.full_clean()
    item.save()
    _recalculate_order(order)
    _save(actor, order, "Thêm món", f"Dòng #{item.pk}: {item}; {item.unit_price} đồng/{item.unit_name}; ghi chú: {item.note}")
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
            note=note,
        )
        item.full_clean()
        item.save()
        created.append(item)

    _recalculate_order(order)

    description = "; ".join(
        f"#{item.pk} {item.dish_name} × {item.quantity} {item.unit_name}"
        + (f" ({item.note})" if item.note else "")
        for item in created
    )
    _save(actor, order, f"Thêm {len(created)} món", description)
    return created


@transaction.atomic
def edit_item(*, actor, order_id, item_id, expected_revision, quantity, note=""):
    actor = _lock_actor(actor)
    _validate_quantity(quantity)
    order = _order(order_id, expected_revision)
    item = order.items.select_for_update().get(pk=item_id)
    if item.status != OrderItem.Status.DRAFT:
        raise ValidationError("Chỉ sửa số lượng hoặc ghi chú của món chưa gửi Bếp. Muốn gọi thêm, hãy thêm dòng món mới.")
    _available_dish(item.dish_id)
    before = (item.quantity, item.note)
    item.quantity, item.note = quantity, note.strip() if isinstance(note, str) else ""
    item.full_clean()
    if before != (item.quantity, item.note):
        item.save(update_fields=("quantity", "note"))
        _recalculate_order(order)
        _save(actor, order, "Sửa món chưa gửi", f"Dòng #{item.pk} {item.dish_name}; trước: {before[0]}, {before[1]}; sau: {item.quantity}, {item.note}.")
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


@transaction.atomic
def process_payment(*, actor, order_id, payment_method, transaction_code=""):
    actor = _lock_actor(actor, "collect_payment")
    if payment_method not in (Payment.Method.CASH, Payment.Method.BANK_TRANSFER):
        raise ValidationError({"payment_method": "Chỉ hỗ trợ tiền mặt hoặc chuyển khoản."})
    transaction_code = (transaction_code or "").strip()
    if len(transaction_code) > 100:
        raise ValidationError({"transaction_code": "Mã giao dịch không được dài quá 100 ký tự."})
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAYMENT_REQUESTED:
        raise ValidationError("Đơn chưa ở trạng thái yêu cầu thanh toán.")
    table = DiningTable.objects.select_for_update().get(pk=order.table_id)
    customer = Customer.objects.select_for_update().filter(pk=order.customer_id).first()
    items = list(order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED))
    if not items:
        raise ValidationError("Đơn không có món để thanh toán.")
    preview = payment_preview(order)
    subtotal = preview["subtotal"]
    discount_percent = preview["discount_percent"]
    discount_amount = preview["discount"]
    total = preview["due"]
    invoice, _ = Invoice.objects.select_for_update().get_or_create(
        order=order,
        defaults={"invoice_code": _invoice_code_for(order)},
    )
    if invoice.status == Invoice.Status.PAID:
        raise ValidationError("Hóa đơn đã được thanh toán.")
    now = timezone.now()
    invoice.customer = customer
    invoice.subtotal = subtotal
    invoice.discount_percent = discount_percent
    invoice.discount_amount = discount_amount
    invoice.total_amount = total
    invoice.total = total
    invoice.paid_amount = total
    invoice.payment_method = payment_method
    invoice.status = Invoice.Status.PAID
    invoice.closed_at = now
    invoice.save()
    Payment.objects.create(
        invoice=invoice,
        amount=total,
        method=payment_method,
        reference=transaction_code,
        performed_by=actor,
        actor_snapshot=actor.username,
    )
    PaymentRequest.objects.select_for_update().filter(
        order=order, status__in=(PaymentRequest.Status.WAITING, PaymentRequest.Status.PROCESSING),
    ).update(status=PaymentRequest.Status.COMPLETED, processed_at=now)
    order.subtotal = subtotal
    order.discount_amount = discount_amount
    order.total_amount = total
    order.status = Order.Status.COMPLETED
    order.closed_at = now
    order.revision += 1
    order.save()
    table.status = DiningTable.Status.CLEANING
    table.save(update_fields=("status", "updated_at"))
    if order.booking_id:
        booking = Booking.objects.select_for_update().get(pk=order.booking_id)
        booking.status = Booking.Status.COMPLETED
        booking.completed_at = now
        booking.revision += 1
        booking.save(update_fields=("status", "completed_at", "revision", "updated_at"))
    if customer:
        customer.total_spending += total
        tier = MembershipTier.objects.filter(is_active=True, minimum_spending__lte=customer.total_spending).order_by("-minimum_spending", "-pk").first()
        customer.membership_tier = tier
        customer.save(update_fields=("total_spending", "membership_tier", "updated_at"))
    _log(actor, order, "Thanh toán", f"{actor.username} thanh toán hóa đơn {invoice.invoice_code}; bàn {table.code} chuyển sang cần dọn.")
    return invoice


@transaction.atomic
def move_table(*, actor, order_id, target_table_id):
    actor = _lock_actor(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
        raise ValidationError("Đơn đã kết thúc, không thể chuyển bàn.")
    source = DiningTable.objects.select_for_update().get(pk=order.table_id)
    target = DiningTable.objects.select_for_update().select_related("area").get(pk=target_table_id)
    if target.status != DiningTable.Status.AVAILABLE or not target.is_active or not target.area.is_active:
        raise ValidationError("Bàn đích không còn trống.")
    now = timezone.now()
    if Booking.objects.filter(table=target, status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED), starts_at__lte=now, ends_at__gt=now).exists():
        raise ValidationError("Bàn đích đang có lịch giữ chỗ.")
    order.table = target
    order.revision += 1
    order.save(update_fields=("table", "revision", "updated_at"))
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


@transaction.atomic
def send_to_kitchen(*, actor, order_id, expected_revision):
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision)
    items = list(order.items.select_for_update().filter(status=OrderItem.Status.DRAFT))
    if not items:
        raise ValidationError("Không có món chưa gửi Bếp.")
    for item in items:
        _available_dish(item.dish_id)
    now = timezone.now()
    order.items.filter(pk__in=[item.pk for item in items]).update(status=OrderItem.Status.PENDING, sent_at=now)
    order.status = Order.Status.IN_PROGRESS
    _save(actor, order, "Gửi Bếp", "; ".join(f"#{item.pk} {item}" for item in items))
    return order


@transaction.atomic
def transition_item(*, actor, order_id, item_id, expected_revision, target, reason=""):
    permission = "work_kitchen" if target in (OrderItem.Status.COOKING, OrderItem.Status.READY) else "manage_order"
    actor = _lock_actor(actor, permission)
    order = _order(order_id, expected_revision)
    item = order.items.select_for_update().get(pk=item_id)
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
    actor = _lock_actor(actor)
    order = _order(order_id, expected_revision, require_open=False)
    live = order.items.exclude(status=OrderItem.Status.CANCELLED)
    target = {"AWAITING_PAYMENT": Order.Status.PAYMENT_REQUESTED, "VOID": Order.Status.CANCELLED}.get(target, target)
    if target == Order.Status.PAYMENT_REQUESTED and order.status in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        if not live.exists() or live.exclude(status=OrderItem.Status.SERVED).exists():
            raise ValidationError("Cần phục vụ xong tất cả món chưa hủy trước khi chuyển chờ thanh toán.")
    elif target == Order.Status.OPEN and order.status == Order.Status.PAYMENT_REQUESTED:
        invoice = Invoice.objects.select_for_update().filter(order=order).first()
        if invoice is not None and invoice.paid_amount > 0:
            raise ValidationError("Đơn đã thu một phần nên không thể gọi thêm món. Hãy thu đủ số tiền còn lại.")
    elif target == Order.Status.CANCELLED and order.status in (Order.Status.OPEN, Order.Status.IN_PROGRESS):
        if live.exists():
            raise ValidationError("Hãy hủy từng món và ghi lý do trước khi hủy đơn.")
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason or len(reason) > 500:
            raise ValidationError({"reason": "Lý do hủy đơn phải có từ 1 đến 500 ký tự."})
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

    if payment_method not in Payment.Method.values:
        raise ValidationError({"payment_method": "Phương thức thanh toán không hợp lệ."})
    reference = reference.strip() if isinstance(reference, str) else ""
    if len(reference) > 100:
        raise ValidationError({"reference": "Ghi chú / mã giao dịch không được dài quá 100 ký tự."})

    total = order.total
    if total <= 0:
        raise ValidationError("Đơn hiện không có giá trị thanh toán.")

    invoice = Invoice.objects.select_for_update().filter(order=order).first()
    if invoice is None:
        invoice = Invoice.objects.create(
            order=order,
            invoice_code=_invoice_code_for(order),
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
    order.revision += 1
    if invoice.status == Invoice.Status.PAID:
        invoice.closed_at = timezone.now()
        order.status = Order.Status.COMPLETED
    order.save(update_fields=("status", "revision", "updated_at"))
    if invoice.status == Invoice.Status.PAID:
        _log(actor, order, "Đã thanh toán", f"Đơn đã thanh toán đủ, đóng hóa đơn {invoice.invoice_code} và có thể hoàn tất lượt khách.")
    invoice.save(update_fields=("total", "paid_amount", "status", "payment_method", "updated_at", "closed_at"))

    description = f"Thu {amount_decimal} đồng bằng {payment.get_method_display()}. Hóa đơn còn lại {invoice.total - invoice.paid_amount} đồng."
    _log(actor, order, "Thanh toán", description)
    return invoice


@transaction.atomic
def pay_tables(*, actor, order_ids, payment_method="CASH", reference=""):
    """Backward-compatible batch wrapper around the canonical payment flow.

    The standalone batch checkout UI is retired, but this service can still be
    called safely by old integrations. Each order must already have a payment
    request and every order is settled through ``process_payment``.
    """
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
        invoice = process_payment(
            actor=actor,
            order_id=order_id,
            payment_method=payment_method,
            transaction_code=reference,
        )
        payment = invoice.payments.order_by("-pk").first()
        invoices.append(invoice)
        payments.append(payment)
        table_codes.append(invoice.order.table.code)
        grand_total += payment.amount

    batch = PaymentBatch.objects.create(
        total=grand_total,
        method="TRANSFER" if payment_method == Payment.Method.BANK_TRANSFER else payment_method,
        reference=reference,
        performed_by=actor,
        actor_snapshot=actor.username,
    )
    Payment.objects.filter(pk__in=[payment.pk for payment in payments]).update(batch=batch)

    return batch, table_codes


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
        if order.status == Order.Status.COMPLETED:
            raise ValidationError("Đơn đã thanh toán. Hãy dùng Hoàn tất để trả bàn, không thể hủy bàn.")
        if order.status == Order.Status.CANCELLED:
            raise ValidationError("Đơn đã được hủy trước đó.")
        invoice = Invoice.objects.select_for_update().filter(order=order).first()
        if invoice is not None and invoice.paid_amount > 0:
            raise ValidationError("Đơn đã thu một phần. Cần xử lý hoàn tiền trước khi hủy bàn.")

        items = list(order.items.select_for_update().exclude(status=OrderItem.Status.CANCELLED))
        if any(item.status == OrderItem.Status.SERVED for item in items):
            raise ValidationError("Bàn đã có món được phục vụ nên không thể hủy. Hãy chuyển đơn sang thanh toán.")
        has_prepared_items = any(item.status in (OrderItem.Status.COOKING, OrderItem.Status.READY) for item in items)
        if has_prepared_items and not has_order_permission(actor, "cancel_prepared_item"):
            raise PermissionDenied("Món đã bắt đầu làm hoặc đã làm xong; chỉ Quản lý được hủy bàn này.")
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
        order.revision += 1
        order.save(update_fields=("status", "revision", "updated_at"))
        _log(actor, order, "Hủy bàn", f"Hủy đơn và giải phóng bàn {booking.table.code}. Lý do: {reason}")

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
