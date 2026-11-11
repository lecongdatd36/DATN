from django.utils.translation import gettext_lazy as _
"""A CSRF-protected session basket shared by storefront and booking forms."""
import json

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import PreorderCartForm
from .views import private_response
from apps.customer_portal.localization import public_name


def basket_payload(request):
    draft = request.session.get("reservation_draft", {})
    data = draft.get("cart", {})
    form = PreorderCartForm(data, mode=draft.get("details", {}).get("mode", "TABLE"), require_items=False)
    valid = form.is_valid()
    lines, count, total, known = [], 0, 0, set()
    for row in form.item_rows + form.combo_rows:
        field = row["quantity"].name
        known.add(field)
        try:
            quantity = max(0, min(100, int(data.get(field) or 0)))
        except (TypeError, ValueError):
            quantity = 0
        if not quantity:
            continue
        combo = row.get("combo")
        item = combo if combo is not None else row["dish"]
        cover = combo.cover if combo is not None else item
        photo = (cover.thumbnail or cover.image).url if cover and (cover.thumbnail or cover.image) else ""
        price = int(item.price)
        count += quantity
        total += price * quantity
        lines.append({"kind": "combo" if combo is not None else "dish", "id": item.pk,
            "name": public_name(item), "quantity": quantity, "price": price, "total": price * quantity,
            "available": item.is_orderable, "image": photo,
            "description": " · ".join(f"{p.quantity} × {public_name(p.dish)}" for p in combo.components) if combo is not None else public_name(item.unit)})
    for field,value in data.items():
        if field.startswith(("qty_", "cqty_")) and field not in known and str(value or "0") != "0":
            try:
                key,quantity = int(field.split("_",1)[1]),int(value)
            except (ValueError,TypeError):
                continue
            lines.append({"kind":"combo" if field.startswith("cqty_") else "dish","id":key,
                "name":"Lựa chọn không còn trong thực đơn", "quantity":quantity,"price":0,"total":0,"available":False,"image":"","description":"Vui lòng xóa và chọn lại."})
            count += quantity
    errors = [str(message) for values in form.errors.values() for message in values]
    return {"items": lines, "count": count, "total": total, "valid": valid, "errors": errors}


@never_cache
@require_http_methods(["GET", "POST"])
def cart(request):
    error = None
    if request.method == "POST":
        try:
            if len(request.body) > 20000:
                raise ValueError(_("Yêu cầu giỏ hàng quá dài."))
            payload = json.loads(request.body)
            if not isinstance(payload, dict):
                raise ValueError(_("Dữ liệu giỏ hàng không hợp lệ."))
            action = payload.get("action")
            draft = request.session.get("reservation_draft", {})
            data = dict(draft.get("cart", {}))
            if action == "clear":
                data = {}
            else:
                kind, key = payload.get("kind"), payload.get("id")
                if kind not in ("dish", "combo") or type(key) is not int or key <= 0:
                    raise ValueError(_("Món/combo không hợp lệ."))
                field = f"{'cqty' if kind == 'combo' else 'qty'}_{key}"
                previous = int(data.get(field) or 0)
                quantity = payload.get("quantity", 1)
                if type(quantity) is not int or not 0 <= quantity <= 100:
                    raise ValueError(_("Số lượng phải từ 0 đến 100."))
                if action == "add":
                    quantity += previous
                elif action == "decrease":
                    quantity = max(0, previous-1)
                elif action == "remove":
                    quantity = 0
                elif action != "set":
                    raise ValueError(_("Thao tác giỏ hàng không hợp lệ."))
                if quantity > 100:
                    raise ValueError(_("Số lượng tối đa 100."))
                data[field] = str(quantity)
                # Removing an unavailable item is always allowed. Additions must
                # pass the same catalog/stock/component validation as checkout.
                if quantity > previous:
                    form = PreorderCartForm(data, mode=draft.get("details", {}).get("mode", "TABLE"), require_items=False)
                    if not form.is_valid():
                        raise ValueError(" ".join(str(e) for values in form.errors.values() for e in values))
            request.session["reservation_draft"] = {**draft, "cart": data, "from_storefront": True}
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            error = str(exc) or "Không cập nhật được giỏ hàng. Vui lòng thử lại."
    state = basket_payload(request)
    return private_response(JsonResponse({"cart": state, "error": error}, status=400 if error else 200))
