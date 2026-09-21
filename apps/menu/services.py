from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction

from .models import Category, Unit, Dish, MenuActivityLog
from .permissions import has_menu_permission


CATALOG_MODELS = {"category": Category, "unit": Unit}


def _lock_actor(actor, permission="manage_menu"):
    # One lock for the catalog: closing a category cannot race adding a dish.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [81723003])
    if not actor.is_authenticated or not actor.pk:
        raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")
    actor = get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
    if actor is None or not has_menu_permission(actor, permission):
        raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")
    return actor


def _check_revision(obj, expected_revision):
    if obj.pk and obj.revision != expected_revision:
        raise ValidationError("Dữ liệu đã thay đổi. Hãy tải lại trang trước khi lưu.")


def _log(actor, obj, entity, action, description):
    MenuActivityLog.objects.create(entity=entity, object_id=obj.pk, label_snapshot=str(obj), action=action,
        description=description, performed_by=actor, actor_snapshot=actor.username)


def _text(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


@transaction.atomic
def save_catalog(*, actor, kind, name, is_active, object_id=None, expected_revision=None):
    actor = _lock_actor(actor)
    model = CATALOG_MODELS[kind]
    obj = model.objects.select_for_update().get(pk=object_id) if object_id is not None else model()
    _check_revision(obj, expected_revision)
    old = (obj.name, obj.is_active)
    obj.name, obj.is_active = _text(name), is_active
    obj.full_clean()
    created = obj.pk is None
    if created or old != (obj.name, obj.is_active):
        if not created:
            obj.revision += 1
        obj.save()
        before = f"Trước: {old[0]}, {'đang sử dụng' if old[1] else 'ngừng sử dụng'}. " if not created else ""
        _log(actor, obj, kind.upper(), "Thêm mới" if created else "Cập nhật",
             before + f"Sau: {obj.name}, {'đang sử dụng' if obj.is_active else 'ngừng sử dụng'}.")
    return obj


def _snapshot(dish):
    return f"{dish}; nhóm {dish.category.name}; đơn vị {dish.unit.name}; giá {dish.price} đồng; {dish.get_status_display()}; mô tả: {dish.description}"


@transaction.atomic
def save_dish(*, actor, code, name, category_id, unit_id, price, status, description="", dish_id=None, expected_revision=None):
    actor = _lock_actor(actor)
    dish = Dish.objects.select_for_update().get(pk=dish_id) if dish_id is not None else Dish()
    _check_revision(dish, expected_revision)
    created = dish.pk is None
    old = None if created else (dish.code, dish.name, dish.category_id, dish.unit_id, dish.price, dish.status, dish.description)
    before = "" if created else _snapshot(dish)
    for field, model, pk in (("category", Category, category_id), ("unit", Unit, unit_id)):
        parent = model.objects.filter(pk=pk).first()
        if parent is None:
            raise ValidationError({field: "Danh mục không còn tồn tại."})
        if not parent.is_active and (created or getattr(dish, f"{field}_id") != pk or (dish.status == Dish.Status.INACTIVE and status != Dish.Status.INACTIVE)):
            raise ValidationError({field: "Hãy chọn danh mục đang sử dụng trước khi thêm, chuyển hoặc mở bán lại món."})
        setattr(dish, field, parent)
    dish.code = code.strip().upper() if isinstance(code, str) else ""
    dish.name, dish.description = _text(name), description.strip() if isinstance(description, str) else ""
    dish.price, dish.status = price, status
    dish.full_clean()
    new = (dish.code, dish.name, dish.category_id, dish.unit_id, dish.price, dish.status, dish.description)
    if created or old != new:
        if not created:
            dish.revision += 1
        dish.save()
        _log(actor, dish, "DISH", "Thêm mới" if created else "Cập nhật", (f"Trước: {before}\nSau: " if before else "") + _snapshot(dish))
    return dish


@transaction.atomic
def change_availability(*, actor, dish_id, status, expected_revision):
    actor = _lock_actor(actor, "change_availability")
    dish = Dish.objects.select_for_update().select_related("category", "unit").get(pk=dish_id)
    _check_revision(dish, expected_revision)
    if status not in (Dish.Status.AVAILABLE, Dish.Status.SOLD_OUT):
        raise ValidationError({"status": "Chỉ được chọn Còn món hoặc Hết món."})
    if not dish.can_toggle_availability:
        raise ValidationError("Món hoặc danh mục đã ngừng sử dụng. Hãy liên hệ Quản lí để mở lại.")
    if dish.status != status:
        before = dish.get_status_display()
        dish.status = status
        dish.revision += 1
        dish.save(update_fields=("status", "revision", "updated_at"))
        _log(actor, dish, "DISH", "Cập nhật còn / hết món", f"{before} → {dish.get_status_display()}.")
    return dish
