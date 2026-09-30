from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import Ingredient, InventoryTransaction, Supplier
from .permissions import has_inventory_permission


@transaction.atomic
def record_inventory_transaction(*, actor, ingredient_id, transaction_type, quantity, unit_cost=0, supplier_id=None, note=""):
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    if not has_inventory_permission(actor, "manage_inventory"):
        raise PermissionDenied("Bạn không có quyền cập nhật kho.")
    if transaction_type not in InventoryTransaction.Type.values:
        raise ValidationError({"transaction_type": "Loại giao dịch không hợp lệ."})
    try:
        quantity = Decimal(str(quantity))
        unit_cost = Decimal(str(unit_cost or 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Số lượng hoặc đơn giá không hợp lệ.") from exc
    if quantity <= 0 or unit_cost < 0:
        raise ValidationError("Số lượng phải lớn hơn 0 và đơn giá không được âm.")

    ingredient = Ingredient.objects.select_for_update().get(pk=ingredient_id)
    before = ingredient.stock_quantity
    if transaction_type == InventoryTransaction.Type.IMPORT:
        after = before + quantity
    elif transaction_type == InventoryTransaction.Type.EXPORT:
        after = before - quantity
    else:
        after = quantity
    if after < 0:
        raise ValidationError("Tồn kho không đủ để xuất số lượng này.")
    supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first() if supplier_id else None
    ingredient.stock_quantity = after
    ingredient.save(update_fields=("stock_quantity", "updated_at"))
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
