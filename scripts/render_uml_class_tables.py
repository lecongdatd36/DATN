"""Render the inspected UML snapshot as tables, PlantUML, and local DOT sources."""
from pathlib import Path
from html import escape
import json

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "uml"
data = json.loads((OUT / "mo-hinh.json").read_text(encoding="utf-8"))
classes = data["classes"]
relations = data["relationships"]
by_name = {c["name"]: c for c in classes}
keys = {
    "TaiKhoan": "username is_active is_staff is_superuser",
    "HoSoNhanVien": "employee_code full_name phone employment_status join_date",
    "KhachHang": "full_name phone total_spending",
    "KhuVuc": "name is_active",
    "Ban": "code capacity status is_active",
    "LichDat": "customer_name customer_phone party_size starts_at ends_at is_walk_in status",
    "DonHang": "order_code guest_count subtotal discount_amount total_amount status",
    "ChiTietDon": "quantity unit_price total_price status note",
    "HoaDon": "invoice_code total_amount paid_amount refunded_amount status",
    "ThanhToan": "amount method reference created_at",
    "DanhMucMon": "name is_active",
    "MonAn": "code name price tracks_inventory status",
    "DinhMuc": "quantity",
    "NhaCungCap": "name phone address is_active",
    "NguyenLieu": "code name unit stock_quantity average_unit_cost low_stock_threshold",
    "PhieuNhap": "receipt_code invoice_number status created_at received_at",
    "ChiTietPhieuNhap": "quantity unit_cost",
    "PhieuKiemKe": "stocktake_code status created_at posted_at",
    "ChiTietKiemKe": "system_quantity actual_quantity",
    "PhieuHaoHut": "waste_code quantity reason unit_cost_snapshot total_cost",
    "GiaoDichKho": "transaction_type quantity stock_before stock_after unit_cost source_type source_id order_item_reference",
}
groups = {
    "Đặt bàn và bán hàng": ["KhachHang", "KhuVuc", "Ban", "LichDat", "DonHang", "ChiTietDon", "HoaDon", "ThanhToan"],
    "Thực đơn và định mức": ["DanhMucMon", "MonAn", "DinhMuc", "NguyenLieu"],
    "Nhân sự và kho": ["TaiKhoan", "HoSoNhanVien", "NhaCungCap", "PhieuNhap", "ChiTietPhieuNhap", "PhieuKiemKe", "ChiTietKiemKe", "PhieuHaoHut", "GiaoDichKho"],
}


def selected(c, full=False):
    fields = {f["name"]: f for f in c["fields"]}
    return c["fields"] if full else [fields[n] for n in keys[c["name"]].split()]


def type_name(f):
    return f["type"] + (" [0..1]" if f["null"] else "")


def relation_code(r):
    if r["kind"] == "composition":
        return f'{r["to"]} "{r["target_mult"]}" *-- "{r["source_mult"]}" {r["from"]} : {r["role"]} / {r["field"]}'
    return f'{r["from"]} "{r["source_mult"]}" --> "{r["target_mult"]}" {r["to"]} : {r["role"]} / {r["field"]}'


def plantuml(full=False):
    lines = ["@startuml", "' Generated from model metadata; no database records are exported.",
             "hide methods", "hide circle", "skinparam shadowing false", "skinparam classAttributeIconSize 0",
             "skinparam linetype polyline", "skinparam defaultFontName Arial", "skinparam classBackgroundColor #F8FAFC",
             "skinparam classHeaderBackgroundColor #E8EFF7", "skinparam ArrowColor #475569",
             'title Sơ đồ lớp nghiệp vụ — 21 lớp trong hình, 34 quan hệ nội bộ']
    enums = []
    for title, names in groups.items():
        lines.append(f'package "{title}" {{')
        for name in names:
            c = by_name[name]
            lines.append(f"class {name} {{")
            for f in selected(c, full):
                typ = type_name(f)
                if f["choices"]:
                    enum_name = name + "_" + f["name"]
                    typ = enum_name + (" [0..1]" if f["null"] else "")
                    enums.append((enum_name, f["choices"]))
                lines.append(f'  + {f["name"]} : {typ}')
            lines.append("}")
        lines.append("}")
    lines += [relation_code(r) for r in relations]
    lines += ['note bottom of LichDat : Đặt trước bắt buộc có khách; lượt vãng lai có thể không có hồ sơ.',
              'note bottom of DonHang : split_root là đơn gốc; mỗi đơn tách có chi tiết và hóa đơn riêng.',
              'note bottom of GiaoDichKho : order_item_reference và source_type/source_id là mã tham chiếu, không phải ForeignKey.',
              'note as ScopeNote\nCác bảng thuộc tính dùng tên field thật trong code.\nBội số 0..* bao gồm trạng thái đơn/phiếu nháp chưa có chi tiết.\n5 liên kết đến lớp ngoài phạm vi được liệt kê trong tài liệu bảng.\nend note']
    if full:
        lines.append('package "Kiểu liệt kê" {')
        for name, choices in enums:
            lines.append(f"enum {name} {{")
            lines += ["  " + value for value, _ in choices]
            lines.append("}")
        lines.append("}")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


legend = [
    ("Liên kết", "Association", "`A -- B`", "Đường liền, không đầu mũi tên; chưa chỉ định hướng điều hướng."),
    ("Liên kết có hướng", "Navigable association", "`A --> B`", "Đường liền, đầu mũi tên mở tại B; A tham chiếu B."),
    ("Hợp thành", "Composition", "`A *-- B`", "Đường liền, hình thoi đen tại A là toàn thể; B là thành phần có vòng đời thuộc A."),
    ("Kết tập chia sẻ", "Shared aggregation", "`A o-- B`", "Đường liền, hình thoi rỗng tại A; chỉ dùng khi mô hình thực sự cần ý nghĩa kết tập."),
    ("Kế thừa", "Generalization", "`Con --|> Cha`", "Đường liền, tam giác rỗng trỏ về lớp cha."),
    ("Phụ thuộc", "Dependency", "`A ..> B`", "Đường đứt, đầu mũi tên mở tại B; A sử dụng B, không phải liên kết dữ liệu lưu trữ."),
    ("Hiện thực giao diện", "Realization", "`Lop ..|> GiaoDien`", "Đường đứt, tam giác rỗng trỏ về giao diện."),
]
md = ["# Bảng chi tiết sơ đồ lớp UML", "", data["scope"], "",
      "Phạm vi này không phải toàn bộ hệ thống. Không đưa model ngoài 21 lớp vào hình một cách ngầm định. "
      "Tài liệu liệt kê 202 thuộc tính vô hướng, 34 quan hệ giữa các lớp trong hình và 5 quan hệ ra ngoài phạm vi. "
      "Tên lớp tiếng Việt là bí danh; tên field giữ nguyên code để dễ đối chiếu. Không chứa dữ liệu khách hàng hoặc giao dịch.", "",
      "## 1. Quy ước UML", "", "| Quan hệ | Tên UML | Cú pháp PlantUML | Cách vẽ |", "|---|---|---|---|"]
md += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in legend]
md += ["", "Đặt bội số sát đầu lớp tương ứng. Ví dụ `Ban \"1\" -- \"0..*\" LichDat`: một lịch gắn đúng một bàn; một bàn có nhiều lịch qua thời gian. "
       "Đầu mũi tên biểu thị khả năng điều hướng, không phải chiều xử lý nghiệp vụ. `0..1`: có thể không có hoặc tối đa một; "
       "`1`: đúng một; `0..*`: không hoặc nhiều; `1..*`: ít nhất một.", "",
       "Bản nguồn chọn association có hướng từ lớp giữ tham chiếu sang lớp được tham chiếu. Có thể bỏ đầu mũi tên để dùng association "
       "không chỉ định hướng. Không dùng tam giác kế thừa hoặc hình thoi cho mọi ForeignKey. "
       "Ba composition được chọn cho định mức của món, dòng phiếu nhập và dòng kiểm kê vì chúng là thành phần thuộc riêng đối tượng cha; "
       "CASCADE trong code là bằng chứng hỗ trợ, không phải quy tắc mọi CASCADE đều là composition. "
       "Đơn hàng–chi tiết đơn và hóa đơn–thanh toán giữ association để mô tả các bản ghi nghiệp vụ được bảo vệ, lưu lịch sử. "
       "Không thêm phương thức như datBan() vào entity khi code thực hiện nghiệp vụ qua service.", "",
       "Nguồn ký pháp: [OMG UML 2.5.1](https://www.omg.org/spec/UML/2.5.1/PDF), "
       "[PlantUML Class Diagram](https://plantuml.com/class-diagram).", "",
       "## 2. Thuộc tính chính để đưa lên hình", "", "| Lớp | Model | Thuộc tính chính |", "|---|---|---|"]
for c in classes:
    fields = "; ".join(f'`{f["name"]}: {type_name(f)}`' for f in selected(c))
    md.append(f'| {c["name"]} | `{c["model"]}` | {fields} |')
md += ["", "Các quan hệ đối tượng nằm trong bảng 3; không cần lặp lại mã khóa ngoại trong ngăn thuộc tính.", "",
       "## 3. Toàn bộ quan hệ nội bộ của 21 lớp", "", "| STT | Lớp A giữ tham chiếu | Field / vai trò | Lớp B được tham chiếu | Bội số sát A | Bội số sát B | Loại | Cú pháp vẽ |", "|---|---|---|---|---|---|---|---|"]
for i, r in enumerate(relations, 1):
    md.append(f'| {i} | {r["from"]} | `{r["field"]}` / {r["role"]} | {r["to"]} | `{r["source_mult"]}` | `{r["target_mult"]}` | {r["kind"]} | `{relation_code(r)}` |')
md += ["", "LichDat.customer chỉ được bỏ trống với lượt vãng lai theo ràng buộc Booking. "
       "Bội số 0..* tính cả trạng thái nháp, không có nghĩa phiếu được phép chốt mà không có dòng hợp lệ. "
       "Các vai trò nguoiLap, nguoiDuyet và nguoiChot là các đường riêng, dù cùng nối hai lớp.", "",
       "## 4. Quan hệ tới lớp ngoài hình", "", "| Lớp A | Field | Lớp B ngoài phạm vi | Sát A | Sát B |", "|---|---|---|---|---|"]
for r in data["outside_scope"]:
    md.append(f'| {r["from"]} | `{r["field"]}` | `{r["to"]}` | `{r["source_mult"]}` | `{r["target_mult"]}` |')
md += ["", "Ngoài ra TaiKhoan kế thừa AbstractUser và có quan hệ nhiều–nhiều với nhóm/quyền của Django. "
       "Nếu mở rộng ra toàn bộ hệ thống cần thêm các model đặt bàn online, đặt cọc, thanh toán online, tài chính, chấm công, ca làm và nhật ký; "
       "không gọi hình 21 lớp là toàn bộ mô hình triển khai.", "",
       "## 5. Danh mục đầy đủ thuộc tính vô hướng", "", "`null=True` là cho phép NULL; `blank=True` là cho phép bỏ trống ở bước validation, hai khái niệm không đồng nhất. "
       "Các trường khóa ngoại đã thể hiện ở bảng quan hệ. id là khóa định danh tự sinh."]
for c in classes:
    md += ["", "### " + c["name"] + " — " + c["model"], "", "| Field | Nhãn | Kiểu UML | Ràng buộc / tập giá trị |", "|---|---|---|---|"]
    for f in c["fields"]:
        rules = []
        if f["primary_key"]: rules.append("PK")
        elif f["unique"]: rules.append("unique")
        if f["null"]: rules.append("NULL được phép")
        if f["blank"]: rules.append("blank=True")
        if f["max_length"]: rules.append("max_length=" + str(f["max_length"]))
        if f["precision"]: rules.append("Decimal(" + ",".join(map(str, f["precision"])) + ")")
        if f["choices"]: rules.append("; ".join(value + " = " + label for value, label in f["choices"]))
        md.append(f'| `{f["name"]}` | {f["label"]} | `{type_name(f)}` | {"; ".join(rules) or "—"} |')
md += ["", "## 6. Những điểm cần lưu ý khi vẽ lại", "",
       "- ThanhToan không có status; trạng thái giao dịch online nằm ở model khác.",
       "- PhieuHaoHut đã là một bản ghi cho một nguyên liệu, không tạo thêm lớp chi tiết hao hụt nếu code chưa có.",
       "- GiaoDichKho.order_item_reference là số nguyên tham chiếu, không phải ForeignKey. source_type/source_id cũng là tham chiếu nghiệp vụ; không suy ra association có ràng buộc CSDL.",
       "- DinhMuc liên kết một món và một nguyên liệu; cặp này là duy nhất. Tương tự, mỗi nguyên liệu chỉ có một dòng trong cùng phiếu nhập hoặc phiếu kiểm kê.",
       "- split_root nối DonHang với chính DonHang, đầu donGoc là 0..1, đầu các đơn tách là 0..*. Không vẽ ChiTietHoaDon vì code không có lớp đó.",
       "- password của TaiKhoan là trường băm được kế thừa, không phải mật khẩu rõ; trên hình tổng quan có thể lược bỏ các trường kỹ thuật.",
       "- Ngăn thứ ba của lớp dành cho operations; có thể lược bỏ khi sơ đồ chỉ mô tả entity và quan hệ. Không bịa các phương thức CRUD cho đủ ba ngăn.",
       "", "## 7. Tệp đính kèm", "", "- so-do-lop-day-du.puml: 21 lớp, 202 thuộc tính và toàn bộ 34 quan hệ nội bộ.",
       "- so-do-lop-tong-quan.puml: cùng quan hệ, chỉ giữ các thuộc tính chính để hình dễ đọc.",
       "- Các tệp SVG/DOT tách nhóm phục vụ xem và chèn báo cáo.", ""]
(OUT / "bang-chi-tiet-uml.md").write_text("\n".join(md), encoding="utf-8")
(OUT / "so-do-lop-day-du.puml").write_text(plantuml(True), encoding="utf-8")
(OUT / "so-do-lop-tong-quan.puml").write_text(plantuml(), encoding="utf-8")


def dot(stem, names, audit=True):
    lines = ['digraph UML {', 'graph [rankdir=LR, bgcolor="white", pad="0.45", nodesep="0.75", ranksep="1.4", splines=polyline, overlap=false];',
             'node [shape=plain, fontname="Arial"];',
             'edge [fontname="Arial", fontsize=10, color="#52647A", fontcolor="#334155", labeldistance=2.0, labelangle=25, arrowsize=0.8];']
    for name in names:
        fields = "".join('<TR><TD ALIGN="LEFT">+ ' + escape(f['name'] + ': ' + type_name(f)) + '</TD></TR>' for f in selected(by_name[name]))
        label = f'<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="8" COLOR="#52647A"><TR><TD BGCOLOR="#E8EFF7"><B>{name}</B></TD></TR><HR/>{fields}</TABLE>'
        lines.append(f'{name} [label=<{label}>];')
    for r in relations:
        if r["from"] not in names or r["to"] not in names: continue
        role = r["field"]
        if r["kind"] == "composition":
            lines.append(f'{r["to"]} -> {r["from"]} [dir=both, arrowtail=diamond, arrowhead=none, taillabel="{r["target_mult"]}", headlabel="{r["source_mult"]}", label="{role}"];')
        else:
            lines.append(f'{r["from"]} -> {r["to"]} [arrowhead=vee, taillabel="{r["source_mult"]}", headlabel="{r["target_mult"]}", label="{role}"];')
    lines.append('}')
    (OUT / (stem + '.dot')).write_text('\n'.join(lines), encoding='utf-8')


dot('so-do-lop-tong-quan', list(by_name))
dot('dat-ban-ban-hang', groups['Đặt bàn và bán hàng'] + ['MonAn', 'TaiKhoan', 'HoSoNhanVien'])
dot('thuc-don-dinh-muc', groups['Thực đơn và định mức'])
dot('nhan-su-kho', groups['Nhân sự và kho'] + ['NguyenLieu'])
print(f'Generated tables, PlantUML and DOT for {len(classes)} classes / {len(relations)} relationships.')
