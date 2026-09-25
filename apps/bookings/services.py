from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.customers.models import Customer
from apps.customers.validators import normalize_phone
from apps.seating.models import DiningTable
from core.seating_lock import lock_seating_schedule
from .models import Booking, BookingActivityLog, BookingSettings, BookingSettingsLog
from .duration import planned_end
from .permissions import has_booking_permission
from .selectors import overlapping_bookings, default_duration_minutes


TRANSITIONS = {
    Booking.Status.PENDING: (Booking.Status.CONFIRMED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW),
    Booking.Status.CONFIRMED: (Booking.Status.SEATED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW),
    Booking.Status.SEATED: (Booking.Status.COMPLETED,),
}


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
    BookingActivityLog.objects.create(booking=booking, action=action, description=description, performed_by=actor, actor_snapshot=actor.username)


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
    table = DiningTable.objects.select_related("area").filter(pk=table_id).first()
    if table is None:
        raise ValidationError({"table": "Bàn không còn tồn tại."})
    before = _snapshot(booking) if not created else ""
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
        _log(actor, booking, "Tạo đặt bàn" if created else "Sửa đặt bàn", (f"Trước: {before}\nSau: " if before else "") + _snapshot(booking))
    return booking


@transaction.atomic
def update_booking_settings(*, actor, default_duration_minutes, expected_revision):
    actor = _lock_actor(actor, "configure_bookings")
    settings = BookingSettings.objects.select_for_update().get(pk=1)
    if settings.revision != expected_revision:
        raise ValidationError("Cấu hình đã thay đổi. Hãy tải lại trang trước khi lưu.")
    planned_end(timezone.now(), default_duration_minutes)
    previous = settings.default_duration_minutes
    if previous != default_duration_minutes:
        settings.default_duration_minutes = default_duration_minutes
        settings.revision += 1
        settings.full_clean()
        settings.save()
        BookingSettingsLog.objects.create(previous_minutes=previous, new_minutes=default_duration_minutes, performed_by=actor, actor_snapshot=actor.username)
    return settings


@transaction.atomic
def transition_booking(*, actor, booking_id, target, expected_status, expected_revision):
    actor = _lock_actor(actor)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status != expected_status or booking.revision != expected_revision:
        raise ValidationError("Lịch hoặc trạng thái đã thay đổi. Hãy tải lại trang trước khi thao tác.")
    if target not in TRANSITIONS.get(booking.status, ()):
        raise ValidationError("Không thể chuyển sang trạng thái này.")
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
        from apps.orders.models import Order
        if Order.objects.filter(booking=booking).exclude(status=Order.Status.VOID).exists():
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
    _log(actor, booking, booking.get_status_display(), f"{before} → {booking.get_status_display()}. " + _snapshot(booking))
    return booking


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
    return booking
