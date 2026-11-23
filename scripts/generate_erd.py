"""Generate ERD sources from Django metadata without querying business data.

Run: .venv/Scripts/python.exe -X utf8 scripts/generate_erd.py
Render DOT sources using Graphviz or @viz-js/viz.
"""
import json
import os
from pathlib import Path
import sys
from html import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
import django

django.setup()
from django.apps import apps
from django.db.models import UniqueConstraint

OUTPUT = ROOT / "docs" / "erd"
OUTPUT.mkdir(parents=True, exist_ok=True)
DOMAIN = {"accounts", "employees", "customers", "seating", "bookings", "menu", "orders", "inventory"}
models = [m for m in apps.get_models(include_auto_created=True) if m._meta.app_label in DOMAIN or m._meta.label in (
    "auth.Group", "auth.Permission", "auth.Group_permissions", "contenttypes.ContentType",
)]
by_label = {m._meta.label: m for m in models}

TITLES = {
    "User": "Tài khoản", "Group": "Nhóm quyền", "Permission": "Quyền", "ContentType": "Loại đối tượng Django",
    "User_groups": "Tài khoản và nhóm", "User_user_permissions": "Quyền riêng tài khoản", "Group_permissions": "Quyền của nhóm",
    "JobPosition": "Chức vụ", "EmployeeProfile": "Hồ sơ nhân viên", "EmployeeActivityLog": "Nhật ký nhân viên",
    "MembershipTier": "Hạng thành viên", "Customer": "Khách hàng", "CustomerActivityLog": "Nhật ký khách",
    "Area": "Khu vực", "DiningTable": "Bàn", "DiningTableQRToken": "Mã QR bàn", "SeatingActivityLog": "Nhật ký bàn và khu vực",
    "Booking": "Đặt bàn và lượt khách", "BookingSettings": "Cấu hình đặt bàn", "BookingSettingsLog": "Nhật ký cấu hình đặt bàn",
    "BookingActivityLog": "Nhật ký đặt bàn", "Category": "Nhóm món", "Unit": "Đơn vị bán", "Dish": "Món ăn",
    "MenuActivityLog": "Nhật ký thực đơn", "PromotionCode": "Mã khuyến mãi", "Order": "Đơn hàng", "OrderItem": "Dòng món",
    "Invoice": "Hóa đơn", "Payment": "Phiếu thu", "PaymentBatch": "Đợt thu nhiều bàn", "OnlinePayment": "Giao dịch trực tuyến",
    "PaymentRequest": "Yêu cầu thanh toán", "OrderActivityLog": "Nhật ký đơn",
    "QRCheckInRequest": "Yêu cầu nhận bàn QR", "QROrderRequest": "Yêu cầu gọi món QR",
    "QROrderRequestItem": "Dòng yêu cầu QR", "QRServiceRequest": "Yêu cầu phục vụ QR",
    "Supplier": "Nhà cung cấp", "Ingredient": "Nguyên liệu", "InventoryTransaction": "Giao dịch kho",
    "RecipeIngredient": "Định lượng món", "PurchaseReceipt": "Phiếu nhập hàng", "PurchaseReceiptLine": "Dòng nhập hàng",
    "Stocktake": "Phiếu kiểm kê", "StocktakeLine": "Dòng kiểm kê", "WasteRecord": "Hao hụt",
}
GROUPS = {
    "access": ("01  TÀI KHOẢN VÀ NHÂN SỰ", {"accounts", "employees", "auth", "contenttypes"}),
    "customers": ("02  KHÁCH HÀNG", {"customers"}),
    "seating": ("03  BÀN VÀ ĐẶT BÀN", {"seating", "bookings"}),
    "menu": ("04  THỰC ĐƠN", {"menu"}),
    "orders": ("05  PHỤC VỤ VÀ THANH TOÁN", {"orders"}),
    "inventory": ("06  KHO NGUYÊN LIỆU", {"inventory"}),
}
OVERVIEW_OMIT = {"Permission", "ContentType", "User_groups", "User_user_permissions", "Group_permissions"}
overview = [m for m in models if m.__name__ not in OVERVIEW_OMIT and not m.__name__.endswith("Log")]

IMPORTANT = {
    "User": ["username", "is_active"], "Group": ["name"], "JobPosition": ["code", "name"],
    "EmployeeProfile": ["employee_code", "full_name", "employment_status"],
    "MembershipTier": ["name", "minimum_spending", "discount_percent"], "Customer": ["full_name", "phone", "total_spending"],
    "Area": ["name", "is_active"], "DiningTable": ["code", "capacity", "status"],
    "DiningTableQRToken": ["token", "expires_at"], "Booking": ["party_size", "starts_at", "ends_at", "status"],
    "BookingSettings": ["opening_time", "closing_time", "default_duration_minutes", "no_show_grace_minutes"],
    "Category": ["name", "is_active"], "Unit": ["name", "is_active"],
    "Dish": ["code", "name", "price", "tracks_inventory", "status"],
    "Order": ["order_code", "status", "total_amount"], "OrderItem": ["quantity", "unit_price", "unit_cost_snapshot", "status"],
    "Invoice": ["invoice_code", "total", "paid_amount", "status"], "Payment": ["amount", "method"],
    "PaymentBatch": ["total", "method"], "OnlinePayment": ["txn_ref", "amount", "status"],
    "PaymentRequest": ["status", "requested_at"], "PromotionCode": ["code", "discount_type", "value"],
    "QRCheckInRequest": ["guest_count", "status", "expires_at"], "QROrderRequest": ["status", "client_request_id"],
    "QROrderRequestItem": ["quantity", "unit_price_snapshot"], "QRServiceRequest": ["request_type", "status"],
    "Supplier": ["name", "phone"], "Ingredient": ["code", "name", "unit", "stock_quantity", "average_unit_cost"],
    "RecipeIngredient": ["quantity"], "InventoryTransaction": ["transaction_type", "quantity", "stock_before", "stock_after"],
    "PurchaseReceipt": ["receipt_code", "status", "received_at"], "PurchaseReceiptLine": ["quantity", "unit_cost"],
    "Stocktake": ["stocktake_code", "status"], "StocktakeLine": ["system_quantity", "actual_quantity"],
    "WasteRecord": ["quantity", "reason", "total_cost"],
}


def sql_type(f):
    kind = f.get_internal_type()
    if kind in ("ForeignKey", "OneToOneField"):
        return sql_type(f.target_field)
    if kind in ("BigAutoField", "BigIntegerField", "PositiveBigIntegerField"):
        return "bigint"
    if kind in ("AutoField", "IntegerField", "PositiveIntegerField"):
        return "integer"
    if kind in ("SmallIntegerField", "PositiveSmallIntegerField"):
        return "smallint"
    if kind == "DecimalField":
        return f"decimal({f.max_digits},{f.decimal_places})"
    return {"BooleanField": "boolean", "DateTimeField": "timestamptz", "DateField": "date", "TimeField": "time",
            "UUIDField": "uuid", "JSONField": "jsonb", "TextField": "text"}.get(kind, f"varchar({f.max_length})" if f.max_length else "text")


def selected_fields(m, detailed):
    if detailed:
        return list(m._meta.local_fields)
    selected = []
    for f in m._meta.local_fields:
        # Creator/approver links all appear in the complete ERD.
        audit = f.is_relation and f.related_model._meta.label == "accounts.User" and m.__name__ != "EmployeeProfile"
        if f.primary_key or (f.is_relation and not audit) or f.name in IMPORTANT.get(m.__name__, []):
            selected.append(f)
    return selected


def edges_for(selected, detailed):
    allowed = {m._meta.label for m in selected}
    result = []
    for child in selected:
        shown = {f.name for f in selected_fields(child, detailed)}
        for f in child._meta.local_fields:
            if f.is_relation and f.related_model._meta.label in allowed and f.name in shown:
                result.append((f.related_model, child, f))
    return result


def q(value):
    return json.dumps(value, ensure_ascii=False)


def node_id(m):
    return m._meta.label.replace(".", "_")


def dot_source(selected, detailed):
    title = "ERD ĐẦY ĐỦ" if detailed else "ERD TỔNG QUAN"
    subtitle = f"CƠM QUÊ   |   {len(selected)} bảng   |   Khóa và quan hệ lấy từ Django models"
    legend = "PK: khóa chính   FK: khóa ngoại   UK: duy nhất   ?: cho phép NULL   0..N: không hoặc nhiều"
    notes = ("Đầy đủ các cột và khóa ngoại của 47 bảng nghiệp vụ và phân quyền. Không gồm bảng phiên, admin log, migrations và cache kỹ thuật."
             if detailed else "Lược thuộc tính và liên kết người tạo/người duyệt để dễ đọc. Mọi khóa ngoại có trong bản đầy đủ. Nét đứt: M:N qua bảng nối.")
    src = ['digraph ERD {',
           'graph [rankdir=TB, bgcolor="white", pad="0.45", nodesep="0.42", ranksep="1.4", splines=polyline, overlap=false, newrank=true, fontname="Arial", fontsize=24, labelloc=t, labeljust=l, outputorder=edgesfirst, concentrate=false,',
           f'label={q(title + chr(10) + subtitle + chr(10) + legend + chr(10) + notes)}];',
           'node [shape=plain, fontname="Arial", fontsize=12];',
           'edge [fontname="Arial", fontsize=9, color="#667085", fontcolor="#344054", penwidth=1, arrowsize=0.7, labelfloat=false, labeldistance=2.0, labelangle=24];']
    for group, (name, labels) in GROUPS.items():
        members = [m for m in selected if m._meta.app_label in labels]
        src += [f'subgraph cluster_{group} {{', f'label={q(name)}; fontcolor="#881b2d"; fontsize=16; color="#d0d5dd"; style="rounded"; penwidth=1; margin=22;']
        for m in members:
            header = escape(m.__name__)
            local_fields = selected_fields(m, detailed)
            rows = [f'<TR><TD COLSPAN="3" BGCOLOR="#881b2d" ALIGN="LEFT"><FONT COLOR="white" POINT-SIZE="14"><B>{header}</B></FONT><BR ALIGN="LEFT"/><FONT COLOR="white" POINT-SIZE="11">{escape(TITLES[m.__name__])}</FONT></TD></TR>']
            for f in local_fields:
                keys = "/".join(k for k, enabled in (("PK", f.primary_key), ("FK", f.is_relation), ("UK", f.unique and not f.primary_key)) if enabled) or "&#160;"
                color = "#faf5f6" if f.primary_key else "#ffffff"
                rows.append(f'<TR><TD BGCOLOR="{color}" ALIGN="LEFT"><FONT POINT-SIZE="10">{keys}</FONT></TD><TD PORT="{f.column}" ALIGN="LEFT" BGCOLOR="{color}">{escape(f.column)}{" ?" if f.null else ""}</TD><TD ALIGN="LEFT" BGCOLOR="{color}"><FONT COLOR="#667085" POINT-SIZE="10">{escape(sql_type(f))}</FONT></TD></TR>')
            if not detailed:
                rows.append('<TR><TD COLSPAN="3" ALIGN="LEFT"><FONT COLOR="#98a2b3" POINT-SIZE="9">Thuộc tính chính được lược chọn</FONT></TD></TR>')
            src.append(f'{q(node_id(m))} [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5" COLOR="#98a2b3">{"".join(rows)}</TABLE>>];')
        src.append('}')
    for parent, child, f in edges_for(selected, detailed):
        # No arrows imply data flow. Endpoint symbols and numbers express cardinality.
        tail = "0..1" if f.null else "1"
        head = "0..1" if f.unique else "0..N"
        tail_shape = "odottee" if f.null else "teetee"
        head_shape = "teeodot" if f.unique else "crowodot"
        src.append(f'{q(node_id(parent))} -> {q(node_id(child))} [dir=both, arrowtail={q(tail_shape)}, arrowhead={q(head_shape)}, taillabel={q(tail)}, headlabel={q(head)}, tooltip={q(child._meta.db_table+"."+f.column+" → "+parent._meta.db_table+"."+f.target_field.column)}];')
    if not detailed:
        src.append('"auth_Group" -> "accounts_User" [dir=none, style=dashed, color="#881b2d", label="M:N qua accounts_user_groups", constraint=false];')
        # Invisible layout constraints keep independent settings/snapshot tables
        # near their modules without suggesting nonexistent foreign keys.
        src += ['orders_Order -> orders_PromotionCode [style=invis];',
                'orders_Order -> orders_PaymentBatch [style=invis];',
                'seating_DiningTable -> bookings_BookingSettings [style=invis];',
                'inventory_Supplier -> inventory_Stocktake [style=invis];']
    src.append('}')
    return "\n".join(src) + "\n"


def mermaid_source(selected, detailed):
    out = ["erDiagram", "    direction TB"]
    for m in selected:
        out.append(f"    {node_id(m)} {{")
        for f in selected_fields(m, detailed):
            keys = ",".join(k for k, enabled in (("PK", f.primary_key), ("FK", f.is_relation), ("UK", f.unique and not f.primary_key)) if enabled)
            description = "NULL allowed" if f.null else "NOT NULL"
            mermaid_type = "decimal" if f.get_internal_type() == "DecimalField" else sql_type(f)
            out.append(f'        {mermaid_type} {f.column} {keys} "{description}"')
        out.append("    }")
    for parent, child, f in edges_for(selected, detailed):
        left = "|o" if f.null else "||"
        right = "o|" if f.unique else "o{"
        out.append(f'    {node_id(parent)} {left}..{right} {node_id(child)} : "{f.column}"')
    if not detailed:
        out.append('    auth_Group }o..o{ accounts_User : "qua accounts_user_groups"')
    return "\n".join(out) + "\n"


def dbml_source():
    out = ["Project ComQue {", "  database_type: 'PostgreSQL'", "  Note: '47 tables from Django models. Generated 2026-11-08. Excludes framework sessions, admin logs, migration history and cache.'", "}", ""]
    for m in models:
        out.append(f"Table {m._meta.db_table} {{")
        out.append(f"  Note: '{TITLES[m.__name__]} — {m.__name__}'")
        for f in m._meta.local_fields:
            flags = ["pk"] if f.primary_key else ["null" if f.null else "not null"]
            if f.get_internal_type().endswith("AutoField"):
                flags.append("increment")
            if f.unique and not f.primary_key:
                flags.append("unique")
            if f.is_relation:
                flags.append("note: '" + f.remote_field.on_delete.__name__ + "'")
            out.append(f"  {f.column} {sql_type(f)} [{', '.join(flags)}]")
        composite = [tuple(c) for c in m._meta.unique_together]
        composite += [c.fields for c in m._meta.constraints if isinstance(c, UniqueConstraint) and c.fields and not c.condition]
        if composite:
            out.append("  indexes {")
            for cols in composite:
                columns = ", ".join(m._meta.get_field(c).column for c in cols)
                out.append(f"    ({columns}) [unique]")
            out.append("  }")
        out.append("}\n")
    for parent, child, f in edges_for(models, True):
        symbol = "-" if f.unique else ">"
        out.append(f"Ref: {child._meta.db_table}.{f.column} {symbol} {parent._meta.db_table}.{f.target_field.column}")
    return "\n".join(out) + "\n"


schema = []
for m in models:
    schema.append({"model": m._meta.label, "table": m._meta.db_table, "title": TITLES[m.__name__],
                   "unique_together": list(m._meta.unique_together),
                   "constraints": [{"name": c.name, "kind": type(c).__name__, "definition": str(c)} for c in m._meta.constraints],
                   "fields": [{"name": f.column, "type": sql_type(f), "pk": f.primary_key, "unique": f.unique,
                               "nullable": f.null, "reference": f.related_model._meta.db_table if f.is_relation else None}
                              for f in m._meta.local_fields]})
(OUTPUT / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTPUT / "com-que.dbml").write_text(dbml_source(), encoding="utf-8")
for stem, selected, detailed in (("erd-tong-quan", overview, False), ("erd-day-du", models, True)):
    (OUTPUT / f"{stem}.dot").write_text(dot_source(selected, detailed), encoding="utf-8")
    (OUTPUT / f"{stem}.mmd").write_text(mermaid_source(selected, detailed), encoding="utf-8")

edges = edges_for(models, True)
assert len(edges) == sum(f.is_relation for m in models for f in m._meta.local_fields)
assert len({m._meta.db_table for m in models}) == len(models)
print(f"Full ERD: {len(models)} tables, {len(edges)} foreign keys, {sum(len(m._meta.local_fields) for m in models)} columns")
print(f"Overview: {len(overview)} tables, {len(edges_for(overview, False))} foreign keys, 1 summarized many-to-many relation")
print(f"Written to {OUTPUT}")
