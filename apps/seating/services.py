from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from core.seating_lock import lock_seating_schedule

from .models import Area, DiningTable, SeatingActivityLog
from .permissions import has_seating_permission


def _lock_actor(actor):
    # Serializes catalog changes, including area shutdown versus table assignment.
    lock_seating_schedule()
    if not actor.is_authenticated or not actor.pk:
        raise PermissionDenied("Bạn không có quyền quản lý khu vực và bàn.")
    fresh = get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
    if fresh is None or not has_seating_permission(fresh, "manage_seating"):
        raise PermissionDenied("Bạn không có quyền quản lý khu vực và bàn.")
    return fresh


def _log(actor, obj, entity, created, changes):
    SeatingActivityLog.objects.create(
        entity=entity, object_id=obj.pk, label_snapshot=str(obj),
        action=SeatingActivityLog.Action.CREATE if created else SeatingActivityLog.Action.UPDATE,
        description=changes, performed_by=actor, actor_snapshot=actor.username,
    )


@transaction.atomic
def save_area(*, actor, name, is_active, area_id=None):
    actor = _lock_actor(actor)
    area = Area.objects.select_for_update().get(pk=area_id) if area_id is not None else Area()
    created = area_id is None
    old = (area.name, area.is_active)
    area.name = " ".join(name.split()) if isinstance(name, str) else ""
    area.is_active = is_active
    area.full_clean()
    if not created and old[1] and not area.is_active:
        from apps.bookings.selectors import protected_bookings
        if protected_bookings().filter(table__area=area).exists():
            raise ValidationError({"is_active": "Khu vực còn lịch đặt hiệu lực hoặc khách đang ngồi. Hãy xử lý các lịch trước khi ngừng sử dụng."})
    if created or old != (area.name, area.is_active):
        area.save()
        description = f"Tên: {area.name}. Trạng thái: {'đang sử dụng' if area.is_active else 'ngừng sử dụng'}."
        if not created:
            description = f"Trước: {old[0]}, {'đang sử dụng' if old[1] else 'ngừng sử dụng'}. " + description
        _log(actor, area, SeatingActivityLog.Entity.AREA, created, description)
    return area


@transaction.atomic
def save_table(*, actor, code, area_id, capacity, is_active, table_id=None):
    actor = _lock_actor(actor)
    area = Area.objects.select_for_update().filter(pk=area_id).first()
    if area is None:
        raise ValidationError({"area": "Khu vực không còn tồn tại."})
    table = DiningTable.objects.select_for_update().get(pk=table_id) if table_id is not None else DiningTable()
    created = table_id is None
    if not area.is_active and (created or table.area_id != area.pk):
        raise ValidationError({"area": "Không thể thêm hoặc chuyển bàn vào khu vực đã ngừng sử dụng."})
    if not area.is_active and is_active and not table.is_active:
        raise ValidationError({"is_active": "Hãy mở lại khu vực trước khi bật sử dụng bàn."})
    old = (table.code, table.area_id, table.capacity, table.is_active)
    old_area_name = table.area.name if not created else ""
    table.code = code.strip().upper() if isinstance(code, str) else ""
    table.area = area
    table.capacity = capacity
    table.is_active = is_active
    table.full_clean()
    if not created:
        from apps.bookings.selectors import protected_bookings
        bookings = protected_bookings().filter(table=table)
        if (old[1] != table.area_id or not table.is_active) and bookings.exists():
            raise ValidationError("Bàn còn lịch đặt hiệu lực hoặc khách đang ngồi, không thể chuyển khu vực hay ngừng sử dụng.")
        if bookings.filter(party_size__gt=table.capacity).exists():
            raise ValidationError({"capacity": "Số chỗ mới không đủ cho lịch đặt đang hiệu lực."})
    if created or old != (table.code, table.area_id, table.capacity, table.is_active):
        table.save()
        description = f"Bàn {table.code}; khu vực {area.name}; {table.capacity} chỗ; {'đang sử dụng' if table.is_active else 'ngừng sử dụng'}."
        if not created:
            description = f"Trước: mã {old[0]}, khu vực {old_area_name}, {old[2]} chỗ, {'đang sử dụng' if old[3] else 'ngừng sử dụng'}. " + description
        _log(actor, table, SeatingActivityLog.Entity.TABLE, created, description)
    return table
