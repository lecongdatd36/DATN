from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from core.menu_lock import lock_menu

from .models import Category, Unit, Dish, MenuActivityLog
from .permissions import has_menu_permission
from .images import prepare_dish_image, delete_unreferenced_images


CATALOG_MODELS = {"category": Category, "unit": Unit}


def _lock_actor(actor, permission="manage_menu"):
    # One lock for the catalog: closing a category cannot race adding a dish.
    lock_menu()
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
    inventory_label = "quản lý kho theo công thức" if dish.tracks_inventory else "không theo dõi kho"
    return f"{dish}; nhóm {dish.category.name}; đơn vị {dish.unit.name}; giá {dish.price} đồng; {dish.get_status_display()}; {inventory_label}; mô tả: {dish.description}; ảnh: {dish.image.name or 'chưa có'}"


def save_dish(*, actor, code, name, category_id, unit_id, price, status, tracks_inventory=False, description="", dish_id=None, expected_revision=None, image=None):
    written = []
    try:
        with transaction.atomic():
            return _save_dish(actor=actor, code=code, name=name, category_id=category_id, unit_id=unit_id, price=price,
                status=status, tracks_inventory=tracks_inventory, description=description, dish_id=dish_id,
                expected_revision=expected_revision, image=image, written=written)
    except Exception:
        # Files do not participate in DB rollback. Remove only this attempt's UUID files.
        storage = Dish._meta.get_field("image").storage
        for filename in written:
            storage.delete(filename)
        raise


def _save_dish(*, actor, code, name, category_id, unit_id, price, status, tracks_inventory, description, dish_id, expected_revision, image, written):
    actor = _lock_actor(actor)
    dish = Dish.objects.select_for_update().get(pk=dish_id) if dish_id is not None else Dish()
    _check_revision(dish, expected_revision)
    created = dish.pk is None
    previous_status = dish.status if not created else None
    old_images = (dish.image.name, dish.thumbnail.name)
    old = None if created else (dish.code, dish.name, dish.category_id, dish.unit_id, dish.price, dish.status, dish.tracks_inventory, dish.description, *old_images)
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
    dish.price, dish.status, dish.tracks_inventory = price, status, bool(tracks_inventory)
    if not dish.tracks_inventory or (previous_status is not None and previous_status != status):
        dish.inventory_sold_out_at = None
    dish.full_clean()
    if image is False:
        dish.image, dish.thumbnail = "", ""
    elif image is not None:
        prepared = prepare_dish_image(image)
        storage = Dish._meta.get_field("image").storage
        for filename, content in prepared:
            written.append(storage.save(filename, content))
        dish.image, dish.thumbnail = written
    new = (dish.code, dish.name, dish.category_id, dish.unit_id, dish.price, dish.status, dish.tracks_inventory, dish.description, dish.image.name, dish.thumbnail.name)
    if created or old != new:
        if not created:
            dish.revision += 1
        dish.save()
        _log(actor, dish, "DISH", "Thêm mới" if created else "Cập nhật", (f"Trước: {before}\nSau: " if before else "") + _snapshot(dish))
        if old_images != (dish.image.name, dish.thumbnail.name):
            transaction.on_commit(lambda: delete_unreferenced_images(old_images), robust=True)
    from apps.inventory.services import sync_dish_availability
    sync_dish_availability(actor=actor, dish_ids=(dish.pk,))
    dish.refresh_from_db()
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
    if status == Dish.Status.AVAILABLE and dish.tracks_inventory:
        from apps.inventory.services import dish_inventory_state
        dish = Dish.objects.prefetch_related("recipe_ingredients__ingredient").get(pk=dish.pk)
        state = dish_inventory_state(dish)
        if not state["can_prepare"]:
            raise ValidationError(
                "Kho chưa đủ nguyên liệu hoạt động để làm 1 phần. Hãy nhập kho hoặc cập nhật công thức trước."
            )
    if dish.status != status:
        before = dish.get_status_display()
        dish.status = status
        dish.inventory_sold_out_at = None
        dish.revision += 1
        dish.save(update_fields=("status", "inventory_sold_out_at", "revision", "updated_at"))
        _log(actor, dish, "DISH", "Cập nhật còn / hết món", f"{before} → {dish.get_status_display()}.")
    return dish
