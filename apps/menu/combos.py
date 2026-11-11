from django.utils.translation import gettext_lazy as _
"""Combo catalog and authoritative expansion into ordinary kitchen/stock lines."""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_FLOOR

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch

from .models import Combo, ComboItem, Dish


def combo_catalog(*, active_only=True):
    rows = Combo.objects.all()
    if active_only:
        rows = rows.filter(is_active=True)
    return rows.prefetch_related(Prefetch("items", queryset=ComboItem.objects.select_related("dish__category", "dish__unit")))


@transaction.atomic
def save_combo(*, actor, code, name, description, people, price, is_active, items, combo_id=None, expected_revision=None, name_en=None, description_en=None):
    from .services import _lock_actor, _check_revision, _log
    actor = _lock_actor(actor)
    row = Combo.objects.select_for_update().get(pk=combo_id) if combo_id else Combo()
    _check_revision(row, expected_revision)
    if not isinstance(items, list) or not 2 <= len(items) <= 12:
        raise ValidationError(_("Combo cần từ 2 đến 12 món khác nhau."))
    seen, regular, units = set(), Decimal(0), 0
    for item in items:
        if type(item.get("dish_id")) is not int or item["dish_id"] in seen or type(item.get("quantity")) is not int or not 1 <= item["quantity"] <= 10:
            raise ValidationError(_("Mỗi món chỉ xuất hiện một lần, số lượng từ 1 đến 10."))
        seen.add(item["dish_id"])
        dish = Dish.objects.select_related("category", "unit").filter(pk=item["dish_id"]).first()
        if not dish or (is_active and (dish.status == "INACTIVE" or not dish.category.is_active or not dish.unit.is_active)):
            raise ValidationError(_("Có món/ngành hàng đã ngừng bán; hãy chọn lại thành phần combo."))
        regular += dish.price * item["quantity"]
        units += item["quantity"]
    row.code = code.strip().upper()
    row.name = " ".join(name.split())
    row.description = description.strip()
    if name_en is not None:
        row.name_en = " ".join(name_en.split())
    if description_en is not None:
        row.description_en = description_en.strip()
    row.people, row.price, row.is_active = people, price, is_active
    row.full_clean()
    if row.is_active and not units <= row.price <= regular:
        raise ValidationError(_("Giá combo phải đủ phân bổ cho các phần món và không cao hơn tổng giá lẻ."))
    creating = not row.pk
    if not creating:
        row.revision += 1
    row.save()
    row.items.all().delete()  # Catalog composition only; historical order snapshots are separate.
    ComboItem.objects.bulk_create([ComboItem(combo=row, **item) for item in items])
    _log(actor, row, "COMBO", "Thêm combo" if creating else "Sửa combo",
         f"{row.code}: {row.price}đ, {row.people} người; thành phần {items}; mở bán {row.is_active}.")
    return row


def allocated_components(combo):
    """Allocate whole VND exactly, with a positive price for every sold portion.

    The customer pays the fixed combo price; kitchen and invoices keep component
    lines. Largest remainders avoid losing a dong when quantities do not divide.
    """
    units = [part.dish for part in combo.components for _ in range(part.quantity)]
    if not units or combo.price < len(units):
        raise ValidationError(_("Giá combo không hợp lệ."))
    regular = sum(dish.price for dish in units)
    values = [combo.price * dish.price / regular for dish in units]
    prices = [max(1, int(value.to_integral_value(rounding=ROUND_FLOOR))) for value in values]
    while sum(prices) > int(combo.price):
        eligible = [i for i, price in enumerate(prices) if price > 1]
        index = max(eligible, key=lambda i: prices[i]-values[i])
        prices[index] -= 1
    left = int(combo.price) - sum(prices)
    ranked = sorted((i for i in range(len(units)) if prices[i] < units[i].price), key=lambda i: (-(values[i] % 1), units[i].pk, i))
    for index in ranked[:left]:
        prices[index] += 1
    grouped = Counter((dish.pk, price) for dish, price in zip(units, prices))
    dishes = {dish.pk: dish for dish in units}
    return [(dishes[dish_id], quantity, Decimal(price)) for (dish_id, price), quantity in grouped.items()]


def expand_selections(items):
    """Ignore client prices; resolve sellable dishes/combos from the catalog."""
    if not isinstance(items, list) or len(items) > 50:
        raise ValidationError(_("Giỏ hàng tối đa 50 món/combo khác nhau."))
    expanded, snapshots, seen, quantities = [], [], set(), defaultdict(int)
    for data in items:
        if not isinstance(data, dict) or type(data.get("quantity")) is not int or not 1 <= data["quantity"] <= 100:
            raise ValidationError(_("Số lượng phải từ 1 đến 100."))
        is_combo = "combo_id" in data
        kind, key = ("combo", data.get("combo_id")) if is_combo else ("dish", data.get("dish_id"))
        if type(key) is not int or (kind, key) in seen or (is_combo and "dish_id" in data):
            raise ValidationError(_("Món/combo không hợp lệ hoặc bị lặp."))
        seen.add((kind, key))
        quantity = data["quantity"]
        note = str(data.get("note", "")).strip()
        if len(note) > (300 if is_combo else 500):
            raise ValidationError(_("Ghi chú tối đa 500 ký tự."))
        if is_combo:
            combo = combo_catalog().filter(pk=key).first()
            if not combo or not combo.is_orderable:
                raise ValidationError(_("Combo đã thay đổi, hết thành phần hoặc ngừng bán. Vui lòng chọn lại."))
            parts = allocated_components(combo)
            snapshots.append({"id": combo.pk, "name": combo.name, "name_en": combo.name_en, "quantity": quantity, "unit_price": str(combo.price),
                "revision": combo.revision, "note": note,
                "items": [{"dish_id": part.dish_id, "name": part.dish.name, "name_en": part.dish.name_en, "quantity": part.quantity} for part in combo.components]})
        else:
            combo = None
            dish = Dish.objects.select_related("category", "unit").filter(pk=key).first()
            if not dish or not dish.is_orderable:
                raise ValidationError(_("Một món đã hết/ngừng bán. Hãy chọn lại thực đơn."))
            parts = [(dish, 1, dish.price)]
        for dish, count, price in parts:
            count *= quantity
            quantities[dish.pk] += count
            if quantities[dish.pk] > 100:
                from apps.customer_portal.localization import public_name
                raise ValidationError(_("%(dish)s: tổng số phần trong món lẻ và combo không được vượt 100.") % {"dish":public_name(dish)})
            expanded.append({"dish": dish, "quantity": count, "unit_price": price, "note": note, "combo": combo})
    if len(expanded) > 200:
        raise ValidationError(_("Giỏ có quá nhiều dòng thành phần. Vui lòng giảm số combo."))
    return expanded, snapshots
