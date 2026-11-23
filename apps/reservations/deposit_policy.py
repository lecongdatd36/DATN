"""One deposit calculation shared by public, staff and payment previews."""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

SEATING_NEEDS = (
    ("STANDARD", _("Bàn thông thường")),
    ("MULTIPLE", _("Cần ghép nhiều bàn")),
    ("PRIVATE", _("Phòng riêng")),
)

DEPOSIT_RULES = (
    ("SMALL_GROUP", _("Nhóm nhỏ, không yêu cầu cọc giữ bàn")),
    ("GROUP", _("Cọc giữ chỗ cho nhóm đông khách")),
    ("MULTIPLE", _("Cọc cho yêu cầu ghép nhiều bàn")),
    ("PRIVATE", _("Cọc cho yêu cầu phòng riêng")),
    ("READY", _("Cọc món yêu cầu chuẩn bị trước")),
    ("LEGACY", _("Chính sách đã chốt trước khi cập nhật")),
)


def deposit_quote(*, policy, party_size, mode="TABLE", subtotal=0, seating_need="STANDARD"):
    if type(party_size) is not int or not 1 <= party_size <= 100 or seating_need not in dict(SEATING_NEEDS):
        raise ValidationError(_("Số khách hoặc nhu cầu bố trí bàn không hợp lệ."))
    if mode == "READY":
        amount = (Decimal(subtotal) * Decimal(policy["ready_percent"]) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        rule = "READY"
    elif mode != "TABLE":
        raise ValidationError(_("Cách chuẩn bị món không hợp lệ."))
    elif policy.get("deposit_policy_version", 1) < 2:
        amount, rule = Decimal(policy["table_deposit"]), "LEGACY"
    else:
        if seating_need == "PRIVATE" and policy.get("require_private_room_deposit", True):
            rule = "PRIVATE"
        elif seating_need == "MULTIPLE" and policy.get("require_multiple_tables_deposit", True):
            rule = "MULTIPLE"
        elif policy.get("require_group_deposit", True) and party_size >= policy.get("deposit_min_guests", 6):
            rule = "GROUP"
        else:
            rule = "SMALL_GROUP"
        amount = Decimal(0) if rule == "SMALL_GROUP" else Decimal(policy["table_deposit"])
    return {"amount": amount, "rule": rule, "label": dict(DEPOSIT_RULES)[rule],
        "needs_review": mode == "READY" or seating_need != "STANDARD"}
