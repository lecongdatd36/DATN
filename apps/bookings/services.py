from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.customers.models import Customer
from apps.customers.validators import normalize_phone
from apps.seating.models import DiningTable
from core.seating_lock import lock_seating_schedule
from .models import Booking, BookingActivityLog, BookingSettings, BookingSettingsLog
from .duration import planned_end
from .permissions import has_booking_permission
from .selectors import available_tables, available_transfer_tables, overlapping_bookings, default_duration_minutes


TRANSITIONS = {
    Booking.Status.PENDING: (Booking.Status.CONFIRMED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW),
    Booking.Status.CONFIRMED: (Booking.Status.SEATED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW),
    Booking.Status.SEATED: (Booking.Status.COMPLETED,),
}


def _reconcile_table_statuses(*, at, table_ids):
    """Derive operational table state from live visits and reservations."""
    table_ids = sorted({table_id for table_id in table_ids if table_id})
    if not table_ids:
        return
    tables = list(DiningTable.objects.select_for_update().filter(pk__in=table_ids).order_by("pk"))
    seated_table_ids = set(
        Booking.objects.filter(table_id__in=table_ids, status=Booking.Status.SEATED)
        .values_list("table_id", flat=True)
    )
    reserved_table_ids = set(
        Booking.objects.filter(
            table_id__in=table_ids,
            status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED),
            starts_at__lte=at,
        ).values_list("table_id", flat=True)
    )
    # Direct POS orders do not always have a Booking, but still occupy the table.
    from apps.orders.models import Order
    live_order_table_ids = set(
        Order.objects.filter(
            table_id__in=table_ids,
            status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS, Order.Status.PAYMENT_REQUESTED),
        ).values_list("table_id", flat=True)
    )
    changed = []
    for table in tables:
        if table.status == DiningTable.Status.CLEANING:
            continue
        if table.pk in seated_table_ids or table.pk in live_order_table_ids:
            next_status = DiningTable.Status.OCCUPIED
        elif table.pk in reserved_table_ids:
            next_status = DiningTable.Status.RESERVED
        else:
            next_status = DiningTable.Status.AVAILABLE
        if table.status != next_status:
            table.status = next_status
            table.updated_at = at
            changed.append(table)
    if changed:
        DiningTable.objects.bulk_update(changed, ("status", "updated_at"))


@transaction.atomic
def expire_overdue_bookings(*, at=None):
    """Mark unattended reservations as no-shows and reconcile their tables.

    The grace period is measured from the promised arrival time. The seating
    advisory lock keeps this sweep ordered with check-in, table opening and
    booking edits. This function also activates reservations whose start time
    has just arrived, so the persisted table state follows the actual clock.
    """
    lock_seating_schedule()
    now = at or timezone.now()
    grace_minutes = BookingSettings.objects.only("no_show_grace_minutes").get(pk=1).no_show_grace_minutes
    cutoff = now - timedelta(minutes=grace_minutes)
    expired = list(
        Booking.objects.select_for_update()
        .filter(
            status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED),
            starts_at__lte=cutoff,
        )
        .order_by("table_id", "pk")
    )
    for booking in expired:
        booking.status = Booking.Status.NO_SHOW
        booking.revision += 1
        booking.updated_at = now
    if expired:
        Booking.objects.bulk_update(expired, ("status", "revision", "updated_at"))

    active_table_ids = set(
        Booking.objects.filter(
            status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED), starts_at__lte=now,
        ).values_list("table_id", flat=True)
    )
    table_ids = active_table_ids | {booking.table_id for booking in expired} | set(
        DiningTable.objects.filter(status=DiningTable.Status.RESERVED).values_list("pk", flat=True)
    )
    table_codes = dict(DiningTable.objects.filter(pk__in=table_ids).values_list("pk", "code"))
    if expired:
        BookingActivityLog.objects.bulk_create(
            [
                BookingActivityLog(
                    booking=booking,
                    action="Tự động ghi nhận không đến",
                    description=(
                        f"Khách chưa được nhận bàn sau {grace_minutes} phút tính từ giờ hẹn; "
                        f"bàn {table_codes.get(booking.table_id, booking.table_id)} được hệ thống giải phóng."
                    ),
                    performed_by=None,
                    actor_snapshot="Hệ thống",
                )
                for booking in expired
            ]
        )
    _reconcile_table_statuses(at=now, table_ids=table_ids)
    return len(expired)


def _lock_actor(actor, permission="manage_booking"):
    lock_seating_schedule()
    if not actor.is_authenticated or not actor.pk:
        raise PermissionDenied("Bạn không có quyền thao tác đặt bàn.")
    actor = get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
    if actor is None or not has_booking_permission(actor, permission):
        raise PermissionDenied("Bạn không có quyền thao tác đặt bàn.")
    return actor


def validate_period(starts_at, ends_at):
    if starts_at is None or ends_at is None:
        raise ValidationError("Vui lòng nhập đầy đủ giờ đến và giờ kết thúc.")
    if timezone.is_naive(starts_at) or timezone.is_naive(ends_at):
        raise ValidationError("Thời gian đặt bàn phải có múi giờ.")
    if ends_at <= starts_at:
        raise ValidationError({"ends_at": "Giờ kết thúc phải sau giờ đến."})


def _validate_slot(booking, *, starts_at=None):
    table = booking.table
    if not table.is_available:
        raise ValidationError({"table": "Bàn hoặc khu vực đã ngừng sử dụng."})
    if booking.party_size > table.capacity:
        raise ValidationError({"party_size": f"Bàn {table.code} chỉ có {table.capacity} chỗ."})
    if overlapping_bookings(table_id=table.pk, starts_at=starts_at or booking.starts_at, ends_at=booking.ends_at, exclude_id=booking.pk).exists():
        raise ValidationError({"table": "Bàn đã có lịch đặt trong khoảng thời gian này. Hãy đổi giờ hoặc chọn bàn khác."})


def _snapshot(booking):
    start = timezone.localtime(booking.starts_at).strftime("%d/%m/%Y %H:%M")
    end = timezone.localtime(booking.ends_at).strftime("%d/%m/%Y %H:%M")
    return f"{booking.customer_name} ({booking.customer_phone}); bàn {booking.table.code}; {booking.party_size} khách; {start} đến {end}."


def _log(actor, booking, action, description):
    BookingActivityLog.objects.create(
        booking=booking,
        action=action,
        description=description,
        performed_by=actor,
        actor_snapshot=actor.username if actor else "Khách đặt bàn online",
    )


@transaction.atomic
def save_booking(*, actor, customer_phone, table_id, party_size, starts_at, ends_at=None, duration_minutes=None, booking_id=None, expected_revision=None):
    actor = _lock_actor(actor)
    booking = Booking.objects.select_for_update().get(pk=booking_id) if booking_id is not None else Booking()
    created = booking_id is None
    if not created and expected_revision != booking.revision:
        raise ValidationError("Lịch đã thay đổi. Hãy tải lại trang trước khi sửa.")
    if not created and not booking.can_edit:
        raise ValidationError("Chỉ sửa được lịch chờ xác nhận hoặc đã xác nhận.")
    if duration_minutes is not None:
        if ends_at is not None:
            raise ValidationError("Chỉ truyền thời lượng hoặc giờ kết thúc, không truyền cả hai.")
        ends_at = planned_end(starts_at, duration_minutes)
    elif ends_at is None:
        # Existing schedules retain their own duration when defaults change.
        duration_minutes = default_duration_minutes() if created else booking.duration_minutes
        ends_at = planned_end(starts_at, duration_minutes)
    validate_period(starts_at, ends_at)
    now = timezone.now()
    if (created or starts_at != booking.starts_at) and starts_at < now:
        raise ValidationError({"starts_at": "Giờ đến mới phải ở tương lai."})
    if ends_at <= now:
        raise ValidationError({"ends_at": "Lịch đã hết giờ; hãy hủy hoặc đánh dấu khách không đến."})
    try:
        phone = normalize_phone(customer_phone)
    except ValidationError as error:
        raise ValidationError({"customer_phone": error.messages}) from error
    customer = Customer.objects.select_for_update().filter(phone=phone).first()
    if customer is None:
        raise ValidationError({"customer_phone": "Chưa có khách hàng với số điện thoại này. Hãy thêm khách hàng trước."})
    table = DiningTable.objects.select_for_update().select_related("area").filter(pk=table_id).first()
    if table is None:
        raise ValidationError({"table": "Bàn không còn tồn tại."})
    before = _snapshot(booking) if not created else ""
    old_table_id = booking.table_id
    old = (booking.customer_id, booking.table_id, booking.party_size, booking.starts_at, booking.ends_at, booking.customer_name, booking.customer_phone)
    booking.customer = customer
    booking.table = table
    booking.party_size = party_size
    booking.starts_at = starts_at
    booking.ends_at = ends_at
    booking.customer_name = customer.full_name
    booking.customer_phone = customer.phone
    if created:
        booking.created_by = actor
    booking.full_clean()
    _validate_slot(booking)
    new = (booking.customer_id, booking.table_id, booking.party_size, booking.starts_at, booking.ends_at, booking.customer_name, booking.customer_phone)
    if created or old != new:
        # Any edited confirmed booking must be confirmed again with the customer.
        booking.status = Booking.Status.PENDING
        if not created:
            booking.revision += 1
        booking.save()
        _reconcile_table_statuses(at=now, table_ids=(old_table_id, table.pk))
        _log(actor, booking, "Tạo đặt bàn" if created else "Sửa đặt bàn", (f"Trước: {before}\nSau: " if before else "") + _snapshot(booking))
    return booking


@transaction.atomic
def create_public_booking(*, full_name, phone, starts_at, party_size, area_id=None, duration_minutes=None, note=""):
    """Create a pending booking from the anonymous customer web flow."""
    lock_seating_schedule()
    try:
        phone = normalize_phone(phone)
    except ValidationError as error:
        raise ValidationError({"phone": error.messages}) from error
    full_name = " ".join(full_name.split()) if isinstance(full_name, str) else ""
    if not full_name:
        raise ValidationError({"full_name": "Vui lòng nhập họ tên."})
    if not isinstance(party_size, int) or not 1 <= party_size <= 100:
        raise ValidationError({"party_size": "Số khách phải từ 1 đến 100."})
    if starts_at is None or timezone.is_naive(starts_at) or starts_at < timezone.now():
        raise ValidationError({"starts_at": "Giờ đến phải ở tương lai."})
    try:
        ends_at = planned_end(starts_at, duration_minutes or default_duration_minutes())
    except ValidationError as error:
        raise ValidationError({"duration_minutes": error.messages}) from error

    customer = Customer.objects.select_for_update().filter(phone=phone).first()
    if customer is None:
        from apps.customers.models import MembershipTier
        customer = Customer(full_name=full_name, phone=phone, membership_tier=MembershipTier.objects.filter(is_active=True, minimum_spending=0).order_by("pk").first())
        customer.full_clean()
        try:
            with transaction.atomic():
                customer.save()
        except IntegrityError as error:
            customer = Customer.objects.select_for_update().filter(phone=phone).first()
            if customer is None:
                raise error

    tables = available_tables(starts_at=starts_at, ends_at=ends_at, party_size=party_size).filter(
        status__in=(DiningTable.Status.AVAILABLE, DiningTable.Status.RESERVED)
    )
    if area_id:
        tables = tables.filter(area_id=area_id)
    table = tables.order_by("capacity", "area__name", "code", "pk").first()
    if table is None:
        raise ValidationError({"starts_at": "Hiện không có bàn phù hợp trong thời gian này."})
    booking = Booking(
        customer=customer,
        table=table,
        customer_name=full_name,
        customer_phone=phone,
        party_size=party_size,
        starts_at=starts_at,
        ends_at=ends_at,
        status=Booking.Status.PENDING,
    )
    booking.full_clean()
    _validate_slot(booking)
    booking.save()
    _reconcile_table_statuses(at=timezone.now(), table_ids=(table.pk,))
    note = " ".join(note.split()) if isinstance(note, str) else ""
    description = _snapshot(booking) + (f" Ghi chú khách: {note}." if note else "")
    _log(None, booking, "Khách tạo đặt bàn online", description)
    return booking


@transaction.atomic
def update_booking_settings(*, actor, default_duration_minutes, expected_revision, no_show_grace_minutes=None):
    actor = _lock_actor(actor, "configure_bookings")
    settings = BookingSettings.objects.select_for_update().get(pk=1)
    if settings.revision != expected_revision:
        raise ValidationError("Cấu hình đã thay đổi. Hãy tải lại trang trước khi lưu.")
    planned_end(timezone.now(), default_duration_minutes)
    if no_show_grace_minutes is None:
        no_show_grace_minutes = settings.no_show_grace_minutes
    if not isinstance(no_show_grace_minutes, int) or not 0 <= no_show_grace_minutes <= 240:
        raise ValidationError({"no_show_grace_minutes": "Thời gian chờ phải từ 0 đến 240 phút."})
    previous = settings.default_duration_minutes
    previous_grace = settings.no_show_grace_minutes
    if previous != default_duration_minutes or previous_grace != no_show_grace_minutes:
        settings.default_duration_minutes = default_duration_minutes
        settings.no_show_grace_minutes = no_show_grace_minutes
        settings.revision += 1
        settings.full_clean()
        settings.save()
        BookingSettingsLog.objects.create(
            previous_minutes=previous,
            new_minutes=default_duration_minutes,
            previous_no_show_grace_minutes=previous_grace,
            new_no_show_grace_minutes=no_show_grace_minutes,
            performed_by=actor,
            actor_snapshot=actor.username,
        )
    return settings


@transaction.atomic
def transition_booking(*, actor, booking_id, target, expected_status, expected_revision, reason=""):
    actor = _lock_actor(actor)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status != expected_status or booking.revision != expected_revision:
        raise ValidationError("Lịch hoặc trạng thái đã thay đổi. Hãy tải lại trang trước khi thao tác.")
    if target not in TRANSITIONS.get(booking.status, ()):
        raise ValidationError("Không thể chuyển sang trạng thái này.")
    reason = reason.strip() if isinstance(reason, str) else ""
    if target in (Booking.Status.CANCELLED, Booking.Status.NO_SHOW) and not reason:
        reason = "Không cung cấp lý do"
    now = timezone.now()
    if target == Booking.Status.CONFIRMED:
        if booking.ends_at <= now:
            raise ValidationError("Lịch đã hết giờ, không thể xác nhận.")
        _validate_slot(booking)
    elif target == Booking.Status.SEATED:
        if now >= booking.ends_at:
            raise ValidationError("Lịch đã hết giờ dự kiến. Hãy điều chỉnh lịch và xác nhận lại trước khi nhận khách.")
        if now < booking.starts_at and timezone.localdate(now) != timezone.localdate(booking.starts_at):
            raise ValidationError("Chỉ nhận khách đến sớm trong ngày hẹn. Nếu khách đổi ngày, hãy sửa lịch trước.")
        _validate_slot(booking, starts_at=min(now, booking.starts_at))
        if Booking.objects.filter(table_id=booking.table_id, status=Booking.Status.SEATED).exclude(pk=booking.pk).exists():
            raise ValidationError("Bàn vẫn đang có khách. Hãy hoàn tất lượt trước hoặc chuyển sang bàn khác.")
        booking.seated_at = now
    elif target == Booking.Status.COMPLETED:
        from apps.orders.models import Invoice, Order
        blocking_orders = Order.objects.filter(booking=booking).exclude(status=Order.Status.CANCELLED).exclude(
            status=Order.Status.COMPLETED, invoice__status=Invoice.Status.PAID)
        if blocking_orders.exists():
            raise ValidationError("Lượt khách còn đơn đang phục vụ hoặc chờ thanh toán. Hãy xử lý đơn trước khi giải phóng bàn.")
        if booking.seated_at and now < booking.seated_at:
            raise ValidationError("Giờ hoàn tất không thể trước giờ nhận khách.")
        booking.completed_at = now
    elif target == Booking.Status.NO_SHOW and now < booking.starts_at:
        raise ValidationError("Chỉ đánh dấu không đến từ giờ hẹn trở đi.")
    before = booking.get_status_display()
    booking.status = target
    booking.revision += 1
    booking.save(update_fields=("status", "revision", "updated_at", "seated_at", "completed_at"))
    if target == Booking.Status.SEATED:
        table = DiningTable.objects.select_for_update().get(pk=booking.table_id)
        table.status = DiningTable.Status.OCCUPIED
        table.save(update_fields=("status", "updated_at"))
    elif target == Booking.Status.COMPLETED:
        table = DiningTable.objects.select_for_update().get(pk=booking.table_id)
        table.status = DiningTable.Status.CLEANING
        table.save(update_fields=("status", "updated_at"))
    else:
        _reconcile_table_statuses(at=now, table_ids=(booking.table_id,))
    reason_note = f" Lý do: {reason}." if reason else ""
    _log(actor, booking, booking.get_status_display(), f"{before} → {booking.get_status_display()}.{reason_note} " + _snapshot(booking))
    return booking


@transaction.atomic
def transfer_table(*, actor, booking_id, table_id, expected_revision):
    actor = _lock_actor(actor)
    booking = Booking.objects.select_for_update().select_related("table", "table__area").get(pk=booking_id)
    if booking.status != Booking.Status.SEATED:
        raise ValidationError("Chỉ chuyển bàn cho lượt khách đang phục vụ.")
    if booking.revision != expected_revision:
        raise ValidationError("Lượt khách đã thay đổi. Hãy tải lại trang trước khi chuyển bàn.")
    from apps.orders.models import Order, OrderActivityLog
    order = Order.objects.select_for_update().filter(booking=booking).first()
    if order is not None and order.status == Order.Status.COMPLETED:
        raise ValidationError("Đơn đã thanh toán nên không thể chuyển bàn. Hãy trả bàn để hoàn tất lượt khách.")
    if order is not None:
        root_id = order.split_root_id or order.pk
        if Order.objects.filter(Q(pk=root_id) | Q(split_root_id=root_id)).exclude(status=Order.Status.CANCELLED).count() > 1:
            raise ValidationError("Hãy thanh toán hoặc ghép các hóa đơn đã tách trước khi chuyển bàn.")

    target = DiningTable.objects.select_related("area").filter(pk=table_id).first()
    if target is None:
        raise ValidationError({"table": "Bàn mới không còn tồn tại."})
    if target.pk == booking.table_id:
        raise ValidationError({"table": "Khách đang ngồi tại bàn này."})
    if not available_transfer_tables(booking).filter(pk=target.pk).exists():
        raise ValidationError({"table": "Bàn mới đang có khách, không đủ chỗ, đã ngừng sử dụng hoặc vướng lịch đặt."})

    old_table = booking.table
    booking.table = target
    booking.revision += 1
    booking.save(update_fields=("table", "revision", "updated_at"))
    if order is not None and order.status != Order.Status.CANCELLED:
        order.table = target
        order.revision += 1
        order.save(update_fields=("table", "revision", "updated_at"))
        OrderActivityLog.objects.create(
            order=order,
            action="Chuyển bàn",
            description=f"Đồng bộ lượt {booking.booking_code}: bàn {old_table.code} → {target.code}.",
            performed_by=actor,
            actor_snapshot=actor.username,
        )
    old_table.status = DiningTable.Status.CLEANING
    old_table.save(update_fields=("status", "updated_at"))
    target.status = DiningTable.Status.OCCUPIED
    target.save(update_fields=("status", "updated_at"))
    _log(
        actor,
        booking,
        "Chuyển bàn",
        f"Bàn {old_table.code} / {old_table.area.name} → bàn {target.code} / {target.area.name}; giữ nguyên đơn hàng, món và hóa đơn.",
    )
    return booking, old_table


@transaction.atomic
def seat_walk_in(*, actor, table_id, party_size, duration_minutes=None, customer_name="", customer_phone=""):
    """Reuse the visit/occupancy rules without creating a fake customer record."""
    actor = _lock_actor(actor)
    table = DiningTable.objects.select_related("area").filter(pk=table_id).first()
    if table is None:
        raise ValidationError({"table": "Bàn không còn tồn tại."})
    if Booking.objects.filter(table=table, status=Booking.Status.SEATED).exists():
        raise ValidationError({"table": "Bàn vẫn đang có khách, kể cả khi đã quá giờ dự kiến."})
    now = timezone.now()
    phone = normalize_phone(customer_phone) if customer_phone else ""
    customer = Customer.objects.filter(phone=phone).first() if phone else None
    name = " ".join(customer_name.split()) if isinstance(customer_name, str) else ""
    booking = Booking(table=table, customer=customer, is_walk_in=True,
        customer_name=name or (customer.full_name if customer else "Khách vãng lai"), customer_phone=phone,
        party_size=party_size, starts_at=now, ends_at=planned_end(now, default_duration_minutes() if duration_minutes is None else duration_minutes),
        seated_at=now, status=Booking.Status.SEATED, created_by=actor)
    booking.full_clean()
    _validate_slot(booking)
    booking.save()
    _log(actor, booking, "Nhận khách không đặt trước", _snapshot(booking))
    table.status = DiningTable.Status.OCCUPIED
    table.save(update_fields=("status", "updated_at"))
    return booking
