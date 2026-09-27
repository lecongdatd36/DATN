from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.seating_lock import lock_seating_schedule
from core.menu_lock import lock_menu
from apps.bookings.models import Booking
from apps.bookings.services import seat_walk_in
from apps.menu.models import Dish
from .models import Invoice, Order, OrderItem, OrderActivityLog, Payment
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
    order.save(update_fields=("status", "revision", "updated_at"))
    _log(actor, order, action, description)


def _invoice_code_for(order):
    # Mỗi lượt chỉ có một đơn và mỗi đơn chỉ có một hóa đơn, nên mã dựa trên
    # khóa chính của đơn vừa ổn định vừa không tranh chấp khi thu tiền đồng thời.
    return f"HD{order.pk:06d}"


def _order(order_id, expected_revision, *, require_open=True):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.revision != expected_revision:
        raise ValidationError("Đơn đã thay đổi. Hãy tải lại trang trước khi thao tác.")
    if order.booking.status != Booking.Status.SEATED:
        raise ValidationError("Lượt khách không còn ở trạng thái đang phục vụ.")
    if require_open and order.status != Order.Status.OPEN:
        raise ValidationError("Đơn đã hủy hoặc đang chờ thanh toán; không thể thay đổi món.")
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
    order = Order.objects.create(booking=booking, created_by=actor)
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
    _save(actor, order, "Thêm món", f"Dòng #{item.pk}: {item}; {item.unit_price} đồng/{item.unit_name}; ghi chú: {item.note}")
    return item


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
        _save(actor, order, "Sửa món chưa gửi", f"Dòng #{item.pk} {item.dish_name}; trước: {before[0]}, {before[1]}; sau: {item.quantity}, {item.note}.")
    return item


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
    order.items.filter(pk__in=[item.pk for item in items]).update(status=OrderItem.Status.SENT, sent_at=now)
    _save(actor, order, "Gửi Bếp", "; ".join(f"#{item.pk} {item}" for item in items))
    return order


@transaction.atomic
def transition_item(*, actor, order_id, item_id, expected_revision, target, reason=""):
    permission = "work_kitchen" if target in (OrderItem.Status.COOKING, OrderItem.Status.READY) else "manage_order"
    actor = _lock_actor(actor, permission)
    order = _order(order_id, expected_revision)
    item = order.items.select_for_update().get(pk=item_id)
    transitions = {"SENT": "COOKING", "COOKING": "READY", "READY": "SERVED"}
    if target == OrderItem.Status.CANCELLED:
        if item.status == OrderItem.Status.CANCELLED:
            raise ValidationError("Món đã được hủy.")
        if item.status in (OrderItem.Status.COOKING, OrderItem.Status.READY, OrderItem.Status.SERVED) and not has_order_permission(actor, "cancel_prepared_item"):
            raise PermissionDenied("Chỉ Quản lí được hủy món đã bắt đầu làm hoặc đã phục vụ.")
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
    if target == Order.Status.AWAITING_PAYMENT and order.status == Order.Status.OPEN:
        if not live.exists() or live.exclude(status=OrderItem.Status.SERVED).exists():
            raise ValidationError("Cần phục vụ xong tất cả món chưa hủy trước khi chuyển chờ thanh toán.")
    elif target == Order.Status.OPEN and order.status == Order.Status.AWAITING_PAYMENT:
        invoice = Invoice.objects.select_for_update().filter(order=order).first()
        if invoice is not None and invoice.paid_amount > 0:
            raise ValidationError("Đơn đã thu một phần nên không thể gọi thêm món. Hãy thu đủ số tiền còn lại.")
    elif target == Order.Status.VOID and order.status == Order.Status.OPEN:
        if live.exists():
            raise ValidationError("Hãy hủy từng món và ghi lý do trước khi hủy đơn.")
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason or len(reason) > 500:
            raise ValidationError({"reason": "Lý do hủy đơn phải có từ 1 đến 500 ký tự."})
    else:
        raise ValidationError("Không thể chuyển trạng thái đơn theo cách này.")
    order.status = target
    _save(actor, order, order.get_status_display(), reason if target == Order.Status.VOID else "Cập nhật trạng thái đơn; chưa ghi nhận thanh toán.")
    return order


@transaction.atomic
def record_payment(*, actor, order_id, expected_revision, amount, payment_method="CASH", reference=""):
    actor = _lock_actor(actor, "collect_payment")
    order = _order(order_id, expected_revision, require_open=False)
    if order.status != Order.Status.AWAITING_PAYMENT:
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
            status=Invoice.Status.PENDING,
            payment_method=payment_method,
        )

    if invoice.status == Invoice.Status.VOID:
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
    invoice.status = Invoice.Status.PAID if invoice.paid_amount >= invoice.total else Invoice.Status.PENDING
    order.revision += 1
    if invoice.status == Invoice.Status.PAID:
        invoice.closed_at = timezone.now()
        order.status = Order.Status.PAID
    order.save(update_fields=("status", "revision", "updated_at"))
    if invoice.status == Invoice.Status.PAID:
        _log(actor, order, "Đã thanh toán", f"Đơn đã thanh toán đủ, đóng hóa đơn {invoice.invoice_code} và có thể hoàn tất lượt khách.")
    invoice.save(update_fields=("total", "paid_amount", "status", "payment_method", "updated_at", "closed_at"))

    description = f"Thu {amount_decimal} đồng bằng {payment.get_method_display()}. Hóa đơn còn lại {invoice.total - invoice.paid_amount} đồng."
    _log(actor, order, "Thanh toán", description)
    return invoice
