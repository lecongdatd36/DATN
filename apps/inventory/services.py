from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Ingredient, InventoryTransaction, PurchaseReceipt, PurchaseReceiptLine,
    RecipeIngredient, Stocktake, StocktakeLine, Supplier, WasteRecord,
)
from .permissions import has_inventory_permission


@transaction.atomic
def record_inventory_transaction(*, actor, ingredient_id, transaction_type, quantity, unit_cost=0, supplier_id=None, note=""):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not has_inventory_permission(actor, "manage_inventory"):
        raise PermissionDenied("Bạn không có quyền cập nhật kho.")
    if transaction_type not in (
        InventoryTransaction.Type.IMPORT,
        InventoryTransaction.Type.EXPORT,
        InventoryTransaction.Type.ADJUSTMENT,
    ):
        raise ValidationError({"transaction_type": "Loại giao dịch không hợp lệ."})
    try:
        quantity = Decimal(str(quantity))
        unit_cost = Decimal(str(unit_cost or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Số lượng hoặc đơn giá không hợp lệ.") from exc
    if quantity < 0 or (transaction_type != InventoryTransaction.Type.ADJUSTMENT and quantity == 0) or unit_cost < 0:
        raise ValidationError("Số lượng không hợp lệ hoặc đơn giá bị âm.")
    if transaction_type == InventoryTransaction.Type.IMPORT and unit_cost <= 0:
        raise ValidationError({"unit_cost": "Nhập kho phải có đơn giá lớn hơn 0 để tính đúng giá vốn."})

    ingredient = Ingredient.objects.select_for_update().get(pk=ingredient_id)
    before = ingredient.stock_quantity
    average_cost = ingredient.average_unit_cost
    if transaction_type == InventoryTransaction.Type.IMPORT:
        after = before + quantity
        if unit_cost > 0:
            average_cost = (
                ((before * ingredient.average_unit_cost) + (quantity * unit_cost)) / after
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif transaction_type == InventoryTransaction.Type.EXPORT:
        after = before - quantity
    else:
        after = quantity
    if after < 0:
        raise ValidationError("Tồn kho không đủ để xuất số lượng này.")
    supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first() if supplier_id else None
    ingredient.stock_quantity = after
    ingredient.average_unit_cost = average_cost
    ingredient.save(update_fields=("stock_quantity", "average_unit_cost", "updated_at"))
    return InventoryTransaction.objects.create(
        ingredient=ingredient,
        transaction_type=transaction_type,
        quantity=quantity,
        stock_before=before,
        stock_after=after,
        unit_cost=unit_cost,
        supplier=supplier,
        note=(note or "").strip(),
        performed_by=actor,
    )


def consume_order_items(*, actor, items):
    """Atomically deduct recipe quantities and snapshot cost for draft order items."""
    items = [item for item in items if item.inventory_deducted_at is None]
    if not items:
        return
    recipes = list(
        RecipeIngredient.objects.filter(dish_id__in={item.dish_id for item in items})
        .select_related("ingredient")
        .order_by("ingredient_id", "dish_id", "pk")
    )
    recipes_by_dish = defaultdict(list)
    for recipe in recipes:
        recipes_by_dish[recipe.dish_id].append(recipe)

    required = defaultdict(Decimal)
    for item in items:
        for recipe in recipes_by_dish[item.dish_id]:
            required[recipe.ingredient_id] += recipe.quantity * item.quantity

    ingredients = {
        ingredient.pk: ingredient
        for ingredient in Ingredient.objects.select_for_update().filter(pk__in=sorted(required)).order_by("pk")
    }
    shortages = []
    for ingredient_id, quantity in required.items():
        ingredient = ingredients[ingredient_id]
        if not ingredient.is_active:
            shortages.append(f"{ingredient.name} đã ngừng sử dụng")
        elif ingredient.stock_quantity < quantity:
            shortages.append(
                f"{ingredient.name} thiếu {(quantity - ingredient.stock_quantity):.3f} {ingredient.unit}"
            )
    if shortages:
        raise ValidationError("Không đủ tồn kho để gửi Bếp: " + "; ".join(shortages) + ".")

    now = timezone.now()
    for item in items:
        unit_cost = Decimal("0")
        for recipe in recipes_by_dish[item.dish_id]:
            ingredient = ingredients[recipe.ingredient_id]
            quantity = (recipe.quantity * item.quantity).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            before = ingredient.stock_quantity
            ingredient.stock_quantity = before - quantity
            ingredient.save(update_fields=("stock_quantity", "updated_at"))
            InventoryTransaction.objects.create(
                ingredient=ingredient,
                transaction_type=InventoryTransaction.Type.SALE_USAGE,
                quantity=quantity,
                stock_before=before,
                stock_after=ingredient.stock_quantity,
                unit_cost=ingredient.average_unit_cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                note=f"Tự động trừ kho khi gửi Bếp · {item.order.order_code} · {item.dish_name}",
                performed_by=actor,
                order_item_reference=item.pk,
            )
            unit_cost += recipe.quantity * ingredient.average_unit_cost
        item.unit_cost_snapshot = unit_cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        item.inventory_deducted_at = now
        item.save(update_fields=("unit_cost_snapshot", "inventory_deducted_at"))


def return_order_item_inventory(*, actor, item):
    """Return the exact quantities deducted for an item cancelled before cooking starts."""
    if item.inventory_deducted_at is None or item.inventory_returned_at is not None:
        return False
    usages = list(
        InventoryTransaction.objects.filter(
            transaction_type=InventoryTransaction.Type.SALE_USAGE,
            order_item_reference=item.pk,
        ).order_by("ingredient_id", "pk")
    )
    ingredient_ids = sorted({usage.ingredient_id for usage in usages})
    ingredients = {
        ingredient.pk: ingredient
        for ingredient in Ingredient.objects.select_for_update().filter(pk__in=ingredient_ids).order_by("pk")
    }
    now = timezone.now()
    for usage in usages:
        ingredient = ingredients[usage.ingredient_id]
        before = ingredient.stock_quantity
        ingredient.stock_quantity = before + usage.quantity
        ingredient.save(update_fields=("stock_quantity", "updated_at"))
        InventoryTransaction.objects.create(
            ingredient=ingredient,
            transaction_type=InventoryTransaction.Type.SALE_RETURN,
            quantity=usage.quantity,
            stock_before=before,
            stock_after=ingredient.stock_quantity,
            unit_cost=usage.unit_cost,
            note=f"Tự động hoàn kho do hủy trước chế biến · {item.order.order_code} · {item.dish_name}",
            performed_by=actor,
            order_item_reference=item.pk,
        )
    item.inventory_returned_at = now
    item.save(update_fields=("inventory_returned_at",))
    return True


@transaction.atomic
def save_recipe_line(*, actor, dish_id, ingredient_id, quantity):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not has_inventory_permission(actor, "manage_inventory"):
        raise PermissionDenied("Bạn không có quyền cập nhật công thức món.")
    from apps.menu.models import Dish
    dish = Dish.objects.select_for_update().get(pk=dish_id)
    ingredient = Ingredient.objects.select_for_update().get(pk=ingredient_id, is_active=True)
    line, _ = RecipeIngredient.objects.update_or_create(
        dish=dish,
        ingredient=ingredient,
        defaults={"quantity": quantity},
    )
    line.full_clean()
    line.save()
    return line


@transaction.atomic
def delete_recipe_line(*, actor, dish_id, line_id):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not has_inventory_permission(actor, "manage_inventory"):
        raise PermissionDenied("Bạn không có quyền cập nhật công thức món.")
    line = RecipeIngredient.objects.select_for_update().get(pk=line_id, dish_id=dish_id)
    line.delete()


def _document_code(prefix):
    return f"{prefix}{timezone.now():%y%m%d}{uuid4().hex[:6].upper()}"


def _lock_inventory_actor(actor):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not has_inventory_permission(actor, "manage_inventory"):
        raise PermissionDenied("Bạn không có quyền thực hiện nghiệp vụ kho.")
    return actor


def _weighted_cost(before_quantity, before_cost, added_quantity, added_cost):
    after = before_quantity + added_quantity
    return (((before_quantity * before_cost) + (added_quantity * added_cost)) / after).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


@transaction.atomic
def create_purchase_receipt(*, actor, supplier_id, invoice_number="", note=""):
    actor = _lock_inventory_actor(actor)
    supplier = Supplier.objects.select_for_update().get(pk=supplier_id, is_active=True)
    return PurchaseReceipt.objects.create(
        receipt_code=_document_code("PN"), supplier=supplier,
        invoice_number=(invoice_number or "").strip(), note=(note or "").strip(), created_by=actor,
    )


@transaction.atomic
def add_purchase_line(*, actor, receipt_id, ingredient_id, quantity, unit_cost):
    _lock_inventory_actor(actor)
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id)
    if receipt.status != PurchaseReceipt.Status.DRAFT:
        raise ValidationError("Chỉ sửa được phiếu nhập đang ở trạng thái nháp.")
    ingredient = Ingredient.objects.select_for_update().get(pk=ingredient_id, is_active=True)
    if quantity <= 0 or unit_cost <= 0:
        raise ValidationError("Số lượng và đơn giá nhập phải lớn hơn 0.")
    line, _ = PurchaseReceiptLine.objects.update_or_create(
        receipt=receipt, ingredient=ingredient,
        defaults={"quantity": quantity, "unit_cost": unit_cost},
    )
    return line


@transaction.atomic
def remove_purchase_line(*, actor, receipt_id, line_id):
    _lock_inventory_actor(actor)
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id, status=PurchaseReceipt.Status.DRAFT)
    PurchaseReceiptLine.objects.select_for_update().get(pk=line_id, receipt=receipt).delete()


@transaction.atomic
def confirm_purchase_receipt(*, actor, receipt_id):
    actor = _lock_inventory_actor(actor)
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id)
    if receipt.status != PurchaseReceipt.Status.DRAFT:
        raise ValidationError("Phiếu nhập không còn ở trạng thái nháp.")
    lines = list(receipt.lines.select_for_update().select_related("ingredient").order_by("ingredient_id"))
    if not lines:
        raise ValidationError("Phiếu nhập phải có ít nhất một nguyên liệu.")
    ingredients = {
        obj.pk: obj for obj in Ingredient.objects.select_for_update().filter(
            pk__in=[line.ingredient_id for line in lines]
        ).order_by("pk")
    }
    for line in lines:
        ingredient = ingredients[line.ingredient_id]
        before = ingredient.stock_quantity
        ingredient.average_unit_cost = _weighted_cost(before, ingredient.average_unit_cost, line.quantity, line.unit_cost)
        ingredient.stock_quantity = before + line.quantity
        ingredient.save(update_fields=("stock_quantity", "average_unit_cost", "updated_at"))
        InventoryTransaction.objects.create(
            ingredient=ingredient, transaction_type=InventoryTransaction.Type.PURCHASE,
            quantity=line.quantity, stock_before=before, stock_after=ingredient.stock_quantity,
            unit_cost=line.unit_cost, supplier=receipt.supplier,
            note=f"Nhận hàng theo {receipt.receipt_code}", performed_by=actor,
            source_type="PURCHASE", source_id=receipt.pk,
        )
    receipt.status = PurchaseReceipt.Status.RECEIVED
    receipt.confirmed_by = actor
    receipt.received_at = timezone.now()
    receipt.save(update_fields=("status", "confirmed_by", "received_at", "updated_at"))
    return receipt


@transaction.atomic
def cancel_purchase_receipt(*, actor, receipt_id):
    _lock_inventory_actor(actor)
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id)
    if receipt.status != PurchaseReceipt.Status.DRAFT:
        raise ValidationError("Chỉ hủy được phiếu nhập nháp.")
    receipt.status = PurchaseReceipt.Status.CANCELLED
    receipt.save(update_fields=("status", "updated_at"))
    return receipt


@transaction.atomic
def create_stocktake(*, actor, note=""):
    actor = _lock_inventory_actor(actor)
    if Stocktake.objects.select_for_update().filter(status=Stocktake.Status.DRAFT).exists():
        raise ValidationError("Đang có một phiếu kiểm kê chưa chốt. Hãy hoàn tất hoặc hủy phiếu đó trước.")
    stocktake = Stocktake.objects.create(
        stocktake_code=_document_code("KK"), note=(note or "").strip(), created_by=actor,
    )
    StocktakeLine.objects.bulk_create([
        StocktakeLine(stocktake=stocktake, ingredient=ingredient, system_quantity=ingredient.stock_quantity)
        for ingredient in Ingredient.objects.filter(is_active=True).order_by("pk")
    ])
    if not stocktake.lines.exists():
        raise ValidationError("Chưa có nguyên liệu đang sử dụng để kiểm kê.")
    return stocktake


@transaction.atomic
def post_stocktake(*, actor, stocktake_id, actual_quantities):
    actor = _lock_inventory_actor(actor)
    stocktake = Stocktake.objects.select_for_update().get(pk=stocktake_id)
    if stocktake.status != Stocktake.Status.DRAFT:
        raise ValidationError("Phiếu kiểm kê không còn ở trạng thái đang kiểm.")
    lines = list(stocktake.lines.select_for_update().order_by("ingredient_id"))
    ingredients = {
        obj.pk: obj for obj in Ingredient.objects.select_for_update().filter(
            pk__in=[line.ingredient_id for line in lines]
        ).order_by("pk")
    }
    for line in lines:
        if line.pk not in actual_quantities:
            raise ValidationError("Phải nhập tồn thực tế cho tất cả nguyên liệu.")
        actual = Decimal(str(actual_quantities[line.pk]))
        if actual < 0:
            raise ValidationError("Tồn thực tế không được âm.")
        ingredient = ingredients[line.ingredient_id]
        before = ingredient.stock_quantity
        line.system_quantity = before
        line.actual_quantity = actual
        line.save(update_fields=("system_quantity", "actual_quantity"))
        if actual != before:
            ingredient.stock_quantity = actual
            ingredient.save(update_fields=("stock_quantity", "updated_at"))
            InventoryTransaction.objects.create(
                ingredient=ingredient, transaction_type=InventoryTransaction.Type.STOCKTAKE,
                quantity=abs(actual - before), stock_before=before, stock_after=actual,
                unit_cost=ingredient.average_unit_cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                note=f"Chốt kiểm kê {stocktake.stocktake_code}", performed_by=actor,
                source_type="STOCKTAKE", source_id=stocktake.pk,
            )
    stocktake.status = Stocktake.Status.POSTED
    stocktake.posted_by = actor
    stocktake.posted_at = timezone.now()
    stocktake.save(update_fields=("status", "posted_by", "posted_at"))
    return stocktake


@transaction.atomic
def cancel_stocktake(*, actor, stocktake_id):
    _lock_inventory_actor(actor)
    stocktake = Stocktake.objects.select_for_update().get(pk=stocktake_id)
    if stocktake.status != Stocktake.Status.DRAFT:
        raise ValidationError("Chỉ hủy được phiếu kiểm kê chưa chốt.")
    stocktake.status = Stocktake.Status.CANCELLED
    stocktake.save(update_fields=("status",))
    return stocktake


@transaction.atomic
def record_waste(*, actor, ingredient_id, quantity, reason, note=""):
    actor = _lock_inventory_actor(actor)
    ingredient = Ingredient.objects.select_for_update().get(pk=ingredient_id, is_active=True)
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValidationError("Số lượng hao hụt phải lớn hơn 0.")
    if reason not in WasteRecord.Reason.values:
        raise ValidationError("Nguyên nhân hao hụt không hợp lệ.")
    if ingredient.stock_quantity < quantity:
        raise ValidationError(f"{ingredient.name} không đủ tồn để ghi nhận hao hụt.")
    before = ingredient.stock_quantity
    ingredient.stock_quantity = before - quantity
    ingredient.save(update_fields=("stock_quantity", "updated_at"))
    record = WasteRecord.objects.create(
        waste_code=_document_code("HH"), ingredient=ingredient, quantity=quantity, reason=reason,
        unit_cost_snapshot=ingredient.average_unit_cost,
        total_cost=(quantity * ingredient.average_unit_cost).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
        note=(note or "").strip(), recorded_by=actor,
    )
    InventoryTransaction.objects.create(
        ingredient=ingredient, transaction_type=InventoryTransaction.Type.WASTE,
        quantity=quantity, stock_before=before, stock_after=ingredient.stock_quantity,
        unit_cost=ingredient.average_unit_cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
        note=f"{record.get_reason_display()} · {record.waste_code}" + (f" · {record.note}" if record.note else ""),
        performed_by=actor, source_type="WASTE", source_id=record.pk,
    )
    return record
