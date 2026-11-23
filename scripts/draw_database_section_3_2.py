"""Build ERD panels exclusively from the read-only PostgreSQL evidence."""
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "section-3-2"
snapshot = json.loads((OUT / "postgresql-schema-evidence.json").read_text(encoding="utf-8"))
tables = {t["name"]: t for t in snapshot["tables"]}

PANELS = [
    ("hinh-3-2a-dat-ban-goi-mon-thanh-toan", "Hình 3.2a  Lược đồ đặt bàn, gọi món và thanh toán", [
        "seating_area", "seating_diningtable", "customers_customer", "bookings_booking",
        "menu_dish", "orders_order", "orders_orderitem", "orders_invoice", "orders_payment",
    ], {
        "seating_area": ["id", "name"],
        "seating_diningtable": ["id", "code", "area_id", "capacity"],
        "customers_customer": ["id", "full_name"],
        "bookings_booking": ["id", "table_id", "customer_id", "starts_at", "ends_at", "status"],
        "menu_dish": ["id", "code", "name", "price"],
        "orders_order": ["id", "booking_id", "table_id", "customer_id", "status"],
        "orders_orderitem": ["id", "order_id", "dish_id", "dish_name", "unit_price", "quantity"],
        "orders_invoice": ["id", "order_id", "customer_id", "total_amount", "paid_amount"],
        "orders_payment": ["id", "invoice_id", "amount", "method"],
    }),
    ("hinh-3-2b-kho-va-dinh-muc", "Hình 3.2b  Lược đồ kho nguyên liệu và định mức món", [
        "menu_dish", "inventory_ingredient", "inventory_recipeingredient", "inventory_supplier",
        "inventory_purchasereceipt", "inventory_purchasereceiptline", "inventory_inventorytransaction",
        "inventory_stocktake", "inventory_stocktakeline", "inventory_wasterecord",
    ], {
        "menu_dish": ["id", "code", "tracks_inventory"],
        "inventory_ingredient": ["id", "code", "unit", "stock_quantity", "average_unit_cost"],
        "inventory_recipeingredient": ["id", "dish_id", "ingredient_id", "quantity"],
        "inventory_supplier": ["id", "name"],
        "inventory_purchasereceipt": ["id", "supplier_id", "receipt_code", "status"],
        "inventory_purchasereceiptline": ["id", "receipt_id", "ingredient_id", "quantity", "unit_cost"],
        "inventory_inventorytransaction": ["id", "ingredient_id", "supplier_id", "quantity", "stock_before", "stock_after"],
        "inventory_stocktake": ["id", "status"],
        "inventory_stocktakeline": ["id", "stocktake_id", "ingredient_id", "system_quantity", "actual_quantity"],
        "inventory_wasterecord": ["id", "ingredient_id", "quantity"],
    }),
    ("hinh-3-2c-dat-truoc-va-tien-coc", "Hình 3.2c  Lược đồ đặt trước và phân bổ tiền cọc", [
        "bookings_booking", "reservations_reservation", "reservations_preorderitem", "menu_dish",
        "reservations_depositpayment", "reservations_depositrefund", "reservations_depositallocation", "orders_invoice",
    ], {
        "bookings_booking": ["id", "table_id", "status"],
        "reservations_reservation": ["id", "booking_id", "request_key", "status", "deposit_required"],
        "reservations_preorderitem": ["id", "reservation_id", "dish_id", "quantity", "unit_price"],
        "menu_dish": ["id", "code", "name"],
        "reservations_depositpayment": ["id", "reservation_id", "txn_ref", "amount", "status"],
        "reservations_depositrefund": ["id", "reservation_id", "amount", "status"],
        "reservations_depositallocation": ["id", "reservation_id", "invoice_id", "amount"],
        "orders_invoice": ["id", "order_id", "total_amount"],
    }),
]


def edges_for(names):
    edges = []
    for child in names:
        table = tables[child]
        columns = {c["name"]: c for c in table["columns"]}
        for c in table.get("constraints", []):
            if c["kind"] != "f":
                continue
            match = re.match(r'FOREIGN KEY \(([^)]+)\) REFERENCES (\w+)\(([^)]+)\)', c["definition"])
            if not match:
                raise ValueError(c["definition"])
            field, parent, key = match.groups()
            if parent not in names:
                continue
            unique = any(x["kind"] in ("u", "p") and re.search(r'\(' + re.escape(field) + r'\)', x["definition"]) for x in table.get("constraints", []))
            edges.append((parent, child, field, "0..1" if columns[field]["nullable"] else "1", "0..1" if unique else "0..N"))
    return edges


def diagram(stem, title, names, fields=None, full=False):
    edges = edges_for(names)
    if fields:
        edges = [e for e in edges if e[2] in fields.get(e[1], [])]
    direction = "TB" if stem.startswith("hinh-3-2a") else "LR"
    legend = "PK: khóa chính | FK: khóa ngoại | UK: duy nhất | ?: cho phép NULL"
    note = "Mũi tên: bảng cha → bảng chứa FK | Nhãn: số lượng phía cha : phía con"
    source = "Nguồn: PostgreSQL 17.3, 20/11/2026. Chỉ vẽ FK thật trong phạm vi hình; lược bớt cột."
    graph_label = f'<<B>{html.escape(title)}</B><BR/><FONT POINT-SIZE="11">{legend}<BR/>{note}<BR/>{source}</FONT>>'
    lines = ["digraph G {", f"graph [rankdir={direction}, bgcolor=white, pad=0.35, nodesep=0.42, ranksep=0.85, splines=polyline, outputorder=edgesfirst, fontname=Arial, fontsize=19, labelloc=t, label=" + graph_label + "];",
             'node [shape=plain, fontname=Arial];',
             'edge [color="#64748b", fontname=Arial, fontsize=10, arrowsize=0.6, arrowhead=vee];']
    for name in names:
        table = tables[name]
        columns = {c["name"]: c for c in table["columns"]}
        pk = {x.strip() for c in table.get("constraints", []) if c["kind"] == "p" for x in re.search(r'\(([^)]+)\)', c["definition"])[1].split(",")}
        fk = {f["column"] for f in table.get("fields", []) if "target" in f}
        uk = {f["column"] for f in table.get("fields", []) if f.get("unique")}
        chosen = fields.get(name, []) if fields else [c["name"] for c in table["columns"] if c["name"] in pk | fk]
        if not chosen:
            chosen = [table["columns"][0]["name"]]
        if fields:
            missing = set(chosen) - columns.keys()
            if missing:
                raise ValueError((name, missing))
        rows = []
        for i, col in enumerate(chosen):
            data = columns[col]
            flags = "/".join(k for k, group in [("PK", pk), ("FK", fk), ("UK", uk - pk)] if col in group)
            dtype = data["type"].replace("character varying", "varchar").replace("timestamp with time zone", "timestamptz")
            nullable = " ?" if data["nullable"] else ""
            bg = "#f1f5f9" if i % 2 == 0 else "white"
            rows.append(f'<TR><TD BGCOLOR="{bg}" ALIGN="LEFT"><FONT POINT-SIZE="10" COLOR="#334155">{flags or " "}</FONT></TD><TD BGCOLOR="{bg}" ALIGN="LEFT"><FONT POINT-SIZE="11">{html.escape(col + nullable)}</FONT></TD><TD BGCOLOR="{bg}" ALIGN="LEFT"><FONT POINT-SIZE="10" COLOR="#475569">{html.escape(dtype)}</FONT></TD></TR>')
        header = html.escape(name)
        label = f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="7" COLOR="#b6c4d4"><TR><TD COLSPAN="3" BGCOLOR="#243f5d"><FONT COLOR="white" POINT-SIZE="12"><B>{header}</B></FONT></TD></TR>{"".join(rows)}</TABLE>>'
        lines.append(f'"{name}" [label={label}];')
    for parent, child, field, pcard, ccard in edges:
        lines.append(f'"{parent}" -> "{child}" [label="{pcard} : {ccard}", tooltip="{child}.{field} references {parent}"];')
    lines.append("}")
    (OUT / (stem + ".dot")).write_text("\n".join(lines), encoding="utf-8")
    print(stem, len(names), "tables", len(edges), "foreign keys")


for panel in PANELS:
    diagram(*panel)
diagram("phu-luc-erd-76-bang", "Lược đồ vật lý PostgreSQL sau cài đặt  76 bảng và 130 khóa ngoại", sorted(tables), full=True)

flow = '''digraph G {
graph [rankdir=TB, bgcolor=white, pad=0.35, nodesep=0.4, ranksep=0.38, fontname=Arial, fontsize=20, labelloc=t, label="Hình 3.3  Kiểm soát đồng thời khi ghi lịch đặt bàn"];
node [shape=box, style="rounded,filled", fillcolor="#f1f5f9", color="#94a3b8", fontname=Arial, fontsize=13, margin="0.2,0.12"];
edge [fontname=Arial, fontsize=11, color="#64748b", arrowsize=0.7];
start [label="Nhận yêu cầu và bắt đầu transaction.atomic()", fillcolor="#dbeafe"];
advisory [label="Lấy pg_advisory_xact_lock(81723002)\nChờ nếu giao dịch khác đang giữ khóa lịch bàn"];
actor [label="Kiểm tra lại quyền và trạng thái người thao tác\nKhóa dòng lịch cũ nếu sửa; đối chiếu revision"];
table [label="Khóa dòng bàn bằng select_for_update()\nĐọc lại sức chứa, trạng thái bàn và khu vực"];
query [label="Đọc lại lịch còn hiệu lực sau khi đã lấy khóa\nKiểm tra khoảng thời gian, sức chứa và điều kiện phục vụ"];
valid [shape=diamond, label="Thỏa điều kiện?", fillcolor="#fff7ed"];
write [label="Ghi lịch, tăng revision khi sửa\nGhi nhật ký và cập nhật trạng thái bàn trong cùng giao dịch"];
commit [label="COMMIT\nGiải phóng khóa; trả kết quả đã lưu", fillcolor="#dcfce7"];
rollback [label="Phát sinh ValidationError hoặc lỗi dữ liệu\nROLLBACK phần thay đổi trong giao dịch\nGiải phóng khóa; trả thông báo phù hợp", fillcolor="#fee2e2"];
start -> advisory -> actor -> table -> query -> valid;
valid -> write [label="Có"]; write -> commit;
valid -> rollback [label="Không"];
}
'''
(OUT / "hinh-3-3-giao-dich-dat-ban.dot").write_text(flow, encoding="utf-8")
