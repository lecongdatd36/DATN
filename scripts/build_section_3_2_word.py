"""Create the thesis-ready section using the managed artifact Python runtime."""
import html
import json
from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "section-3-2"
FIG = OUT / "word-figures"
FIG.mkdir(exist_ok=True)
SCHEMA = json.loads((OUT / "postgresql-schema-evidence.json").read_text(encoding="utf-8"))
TABLES = {t["name"]: t for t in SCHEMA["tables"]}


def compact_erd(stem, selection, direction):
    lines = [f'digraph G {{ graph [rankdir={direction}, bgcolor=white, pad=0.1, nodesep=0.25, ranksep=0.35, splines=polyline, outputorder=edgesfirst];',
        'node [shape=plain, fontname="Times New Roman"];',
        'edge [fontname="Times New Roman", fontsize=12, color="#526373", arrowhead=vee, arrowsize=0.55];']
    for name, chosen in selection.items():
        table = TABLES[name]
        columns = {c["name"]: c for c in table["columns"]}
        fk = {f["column"] for f in table.get("fields", []) if "target" in f}
        unique = {f["column"] for f in table.get("fields", []) if f.get("unique")}
        rows = []
        for col in chosen:
            assert col in columns, (name, col)
            flags = "PK" if col == "id" else ("FK/UK" if col in fk & unique else "FK" if col in fk else "UK" if col in unique else "")
            nullable = " ?" if columns[col]["nullable"] else ""
            rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="13">{flags or " "}</FONT></TD><TD ALIGN="LEFT"><FONT POINT-SIZE="13">{html.escape(col+nullable)}</FONT></TD></TR>')
        label = f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5" COLOR="#777777"><TR><TD COLSPAN="2" BGCOLOR="#eeeeee"><FONT POINT-SIZE="13"><B>{name}</B></FONT></TD></TR>{"".join(rows)}</TABLE>>'
        lines.append(f'"{name}" [label={label}];')
    for child, chosen in selection.items():
        table = TABLES[child]
        columns = {c["name"]: c for c in table["columns"]}
        for constraint in table.get("constraints", []):
            if constraint["kind"] != "f":
                continue
            field, parent, target = re.match(r'FOREIGN KEY \(([^)]+)\) REFERENCES (\w+)\(([^)]+)\)', constraint["definition"]).groups()
            if parent not in selection or field not in chosen:
                continue
            unique = any(f["column"]==field and f.get("unique") for f in table.get("fields", []))
            a = "0..1" if columns[field]["nullable"] else "1"
            b = "0..1" if unique else "0..N"
            lines.append(f'"{parent}" -> "{child}" [label="{a} : {b}"];')
    lines.append("}")
    (FIG / (stem + ".dot")).write_text("\n".join(lines), encoding="utf-8")


compact_erd("word-3-2a", {
    "seating_area": ["id"], "seating_diningtable": ["id", "area_id"],
    "customers_customer": ["id"], "bookings_booking": ["id", "table_id", "customer_id"],
    "orders_order": ["id", "booking_id", "table_id", "customer_id"],
    "menu_dish": ["id"], "orders_orderitem": ["id", "order_id", "dish_id"],
    "orders_invoice": ["id", "order_id", "customer_id"], "orders_payment": ["id", "invoice_id"],
}, "TB")
compact_erd("word-3-2b", {
    "menu_dish": ["id"],
    "inventory_recipeingredient": ["id", "dish_id", "ingredient_id", "quantity"],
    "inventory_ingredient": ["id", "unit", "stock_quantity"],
}, "LR")
compact_erd("word-3-2c", {
    "bookings_booking": ["id"], "reservations_reservation": ["id", "booking_id"],
    "menu_dish": ["id"], "reservations_preorderitem": ["id", "reservation_id", "dish_id"],
    "reservations_depositpayment": ["id", "reservation_id"],
    "reservations_depositrefund": ["id", "reservation_id"],
    "reservations_depositallocation": ["id", "reservation_id", "invoice_id"],
    "orders_invoice": ["id"],
}, "LR")

(FIG / "word-3-3.dot").write_text('''digraph G {
graph [rankdir=TB, bgcolor=white, pad=0.08, nodesep=0.3, ranksep=0.25];
node [shape=box, style="rounded", fontname="Times New Roman", fontsize=14, margin="0.12,0.08", color="#666666"];
edge [fontname="Times New Roman", fontsize=13, color="#666666", arrowsize=0.6];
a [label="Bắt đầu giao dịch"];
b [label="Lấy khóa tư vấn lịch bàn"];
c [label="Khóa dòng liên quan\\nKiểm tra quyền và phiên bản"];
d [shape=diamond, label="Lịch còn phù hợp?"];
e [label="Ghi lịch và nhật ký\\nCOMMIT"];
f [label="ROLLBACK\\nThông báo điều kiện không hợp lệ"];
a -> b -> c -> d;
d -> e [label="Có"];
d -> f [label="Không"];
}''', encoding="utf-8")

if not (FIG / "word-3-2a.png").exists():
    print("Diagram sources created; render them, then run this builder again.")
    raise SystemExit(0)

doc = Document()
section = doc.sections[0]
# Match the available thesis reference's Letter page and 3 cm / 2 cm side margins.
section.page_width, section.page_height = Inches(8.5), Inches(11)
section.left_margin, section.right_margin = Inches(1.1811), Inches(0.7874)
section.top_margin = section.bottom_margin = Inches(0.88)
section.header_distance = section.footer_distance = Inches(0.4)

for name in ["Normal", "Title", "Heading 1", "Heading 2", "Heading 3", "Caption"]:
    style = doc.styles[name]
    style.font.name = "Times New Roman"
    style.font.color.rgb = RGBColor(0, 0, 0)
    rf = style.element.get_or_add_rPr().rFonts
    for key in ["asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"]:
        rf.attrib.pop(qn("w:" + key), None)
    for key in ["ascii", "hAnsi", "eastAsia", "cs"]:
        rf.set(qn("w:" + key), "Times New Roman")
normal = doc.styles["Normal"]
normal.font.size = Pt(13)
normal.paragraph_format.line_spacing = 1.3
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.first_line_indent = Inches(0.3)
for name, size in [("Heading 1", 15), ("Heading 2", 14), ("Heading 3", 13)]:
    style = doc.styles[name]
    style.font.size = Pt(size)
    style.font.bold = True
    style.paragraph_format.first_line_indent = Inches(0)
    style.paragraph_format.space_before = Pt(10)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.keep_with_next = True
caption_style = doc.styles["Caption"]
caption_style.font.size = Pt(12)
caption_style.font.italic = False
caption_style.paragraph_format.first_line_indent = Inches(0)
caption_style.paragraph_format.line_spacing = 1.1
caption_style.paragraph_format.space_before = Pt(5)
caption_style.paragraph_format.space_after = Pt(7)

footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
footer.paragraph_format.first_line_indent = Inches(0)
run = footer.add_run()
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
run._r.append(field)


def p(text):
    para = doc.add_paragraph(text)
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    para.paragraph_format.widow_control = True
    previous = para._p.getprevious()
    if previous is not None and previous.tag == qn("w:tbl"):
        para.paragraph_format.space_before = Pt(7)
    if text.startswith("Trong các hình,"):
        para.paragraph_format.keep_together = True
    return para


def heading(text, level=2):
    return doc.add_heading(text, level=level)


def lead(text):
    para = doc.add_paragraph()
    para.paragraph_format.first_line_indent = Inches(0)
    para.paragraph_format.keep_with_next = True
    para.add_run(text).bold = True


def table(caption, headers, rows, widths):
    cap = doc.add_paragraph(caption, "Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.keep_with_next = True
    tb = doc.add_table(rows=1, cols=len(headers))
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    tb.autofit = False
    for col, width in zip(tb.columns, widths):
        col.width = Inches(width)
    for i, text in enumerate(headers):
        tb.rows[0].cells[i].text = text
    repeat = OxmlElement("w:tblHeader")
    tb.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for cell, text in zip(tb.add_row().cells, row):
            cell.text = text
    for ri, row in enumerate(tb.rows):
        pr = row._tr.get_or_add_trPr()
        pr.append(OxmlElement("w:cantSplit"))
        for ci, cell in enumerate(row.cells):
            cell.width = Inches(widths[ci])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = cell._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for side in ["top", "left", "bottom", "right"]:
                border = OxmlElement("w:" + side)
                for key, value in [("val", "single"), ("sz", "5"), ("color", "D9D9D9")]:
                    border.set(qn("w:" + key), value)
                borders.append(border)
            tcpr.append(borders)
            margins = OxmlElement("w:tcMar")
            for side in ["top", "left", "bottom", "right"]:
                el = OxmlElement("w:" + side)
                el.set(qn("w:w"), "85")
                el.set(qn("w:type"), "dxa")
                margins.append(el)
            tcpr.append(margins)
            if ri == 0:
                fill = OxmlElement("w:shd")
                fill.set(qn("w:fill"), "E7E6E6")
                tcpr.append(fill)
            for para in cell.paragraphs:
                para.paragraph_format.first_line_indent = Inches(0)
                para.paragraph_format.line_spacing = 1.12
                para.paragraph_format.space_after = Pt(1)
                para.paragraph_format.space_before = Pt(1)
                para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                if ri < 2:
                    para.paragraph_format.keep_with_next = True
                for r in para.runs:
                    r.font.size = Pt(11.5)
                    r.font.bold = ri == 0


def figure(path, caption, max_height=6.6, width=6.25):
    with Image.open(path) as im:
        w, h = im.size
    image_width = min(width, max_height * w / h)
    para = doc.add_paragraph()
    para.paragraph_format.first_line_indent = Inches(0)
    para.paragraph_format.space_after = Pt(2)
    para.paragraph_format.keep_with_next = True
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = para.add_run()
    shape = r.add_picture(str(path), width=Inches(image_width))
    shape._inline.docPr.set("descr", caption)
    cap = doc.add_paragraph(caption, "Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER


heading("3.2. Xây dựng cơ sở dữ liệu", 1)
p("Cơ sở dữ liệu của hệ thống quản lý nhà hàng Cơm Quê được xây dựng trên PostgreSQL 17.3, sử dụng Django ORM để ánh xạ các thực thể nghiệp vụ thành bảng dữ liệu. Quá trình cài đặt kế thừa mô hình đã phân tích trong Chương 2, đồng thời bổ sung các trường trạng thái, thông tin lịch sử và cơ chế kiểm soát giao dịch phục vụ hoạt động thực tế. Các yêu cầu trọng tâm gồm bảo đảm toàn vẹn tham chiếu, duy trì giá trị giao dịch đã phát sinh và xử lý nhất quán khi nhiều người dùng cùng thao tác.")
p("Lược đồ sau cài đặt gồm 76 bảng, 729 cột và 130 khóa ngoại, bao gồm bảng nghiệp vụ, bảng trung gian và bảng kỹ thuật của Django. Các số liệu được đối chiếu trực tiếp với lược đồ public trên PostgreSQL ngày 20/11/2026. Để thuận tiện trình bày, phần này tập trung vào các nhóm dữ liệu gắn với đặt bàn, gọi món, thanh toán và quản lý kho.")

heading("3.2.1. Cài đặt các mô hình dữ liệu")
p("Các mô hình được tổ chức theo từng phân hệ. Dữ liệu danh mục mô tả đối tượng dùng chung như khu vực, bàn, món và nguyên liệu; dữ liệu phát sinh phản ánh lịch phục vụ, đơn hàng, hóa đơn và chứng từ kho. Nhật ký được lưu riêng nhằm ghi nhận thời điểm, người thao tác và nội dung thay đổi. Cách tổ chức này làm rõ trách nhiệm của từng nhóm bảng và hạn chế việc trộn lẫn thông tin danh mục với thông tin giao dịch.")
table("Bảng 3.2. Các nhóm mô hình dữ liệu chính", ["Nhóm dữ liệu", "Mô hình tiêu biểu", "Vai trò"], [
    ("Tài khoản và nhân sự", "User, EmployeeProfile, JobPosition", "Lưu tài khoản nội bộ, hồ sơ nhân viên và chức vụ."),
    ("Khách hàng", "Customer, MembershipTier", "Quản lý hồ sơ, chi tiêu và hạng thành viên."),
    ("Bàn và lịch phục vụ", "Area, DiningTable, Booking", "Lưu khu vực, sức chứa, lịch và lượt phục vụ tại bàn."),
    ("Đặt chỗ trực tuyến", "Reservation, PreorderItem", "Lưu yêu cầu đặt chỗ, nội dung chốt và món đặt trước."),
    ("Thực đơn", "Dish, Category, Unit, Combo", "Quản lý món, nhóm món, đơn vị bán và combo."),
    ("Đơn và thanh toán", "Order, OrderItem, Invoice, Payment", "Ghi nhận gọi món, hóa đơn và khoản thu."),
    ("Tiền cọc", "DepositPayment, DepositAllocation, DepositRefund", "Theo dõi nhận cọc, khấu trừ và hoàn cọc."),
    ("Kho nguyên liệu", "Ingredient, RecipeIngredient, PurchaseReceipt, InventoryTransaction", "Quản lý định mức, nhập hàng, tồn và biến động kho."),
], [1.30, 2.50, 2.73])
p("Trong phân hệ đặt bàn, Booking biểu diễn lịch hoặc lượt phục vụ gắn với một bàn cụ thể, còn Reservation biểu diễn yêu cầu đặt chỗ trực tuyến. Một yêu cầu trực tuyến có thể trải qua các bước xem xét, chốt nội dung và chờ tiền cọc trước khi được phục vụ. Việc tách hai mô hình giúp phân biệt rõ yêu cầu của khách với lịch bố trí bàn; nhận tiền cọc không đồng nghĩa với khách đã nhận bàn hoặc đã phát sinh đơn gọi món.")
lead("Lựa chọn kiểu dữ liệu")
p("Khóa chính của phần lớn bảng nghiệp vụ sử dụng kiểu số nguyên lớn. Các trường mã và tên sử dụng chuỗi có giới hạn độ dài; trạng thái được biểu diễn bằng các giá trị xác định trước. Các giá trị tiền sử dụng DecimalField ở Django và numeric ở PostgreSQL để phù hợp với phép tính thập phân. Độ chính xác và số chữ số thập phân được xác định theo từng loại dữ liệu, thay vì sử dụng chung một kiểu cho cả tiền và số lượng.")
table("Bảng 3.3. Một số kiểu dữ liệu được sử dụng", ["Thuộc tính đại diện", "Kiểu PostgreSQL", "Ý nghĩa"], [
    ("Booking.id, Order.id", "bigint", "Định danh và liên kết bản ghi."),
    ("Dish.price, OrderItem.unit_price", "numeric(9,0)", "Lưu đơn giá món theo đồng Việt Nam."),
    ("Invoice.total_amount", "numeric(12,0)", "Lưu tổng tiền hóa đơn."),
    ("Ingredient.stock_quantity, RecipeIngredient.quantity", "numeric(14,3)", "Lưu tồn và định lượng với ba chữ số thập phân."),
    ("Ingredient.average_unit_cost", "numeric(14,2)", "Lưu giá vốn bình quân."),
    ("Booking.starts_at, Booking.ends_at", "timestamp with time zone", "Lưu thời điểm có hỗ trợ chuyển đổi múi giờ."),
], [2.50, 1.55, 2.48])
p("Ứng dụng bật USE_TZ và sử dụng múi giờ Asia/Ho_Chi_Minh; kết nối PostgreSQL được đặt ở UTC. Các thời điểm được chuyển sang giờ địa phương khi hiển thị hoặc lập báo cáo. Khi tổng hợp theo ngày kinh doanh, khoảng đầu ngày và đầu ngày kế tiếp phải được xác định theo giờ Việt Nam để tránh phân loại sai giao dịch gần thời điểm chuyển ngày (Django Software Foundation, tài liệu Time zones).")
lead("Lưu thông tin giao dịch tại thời điểm phát sinh")
p("Thông tin danh mục có thể thay đổi sau khi phát sinh giao dịch. Do đó, OrderItem vừa liên kết với món hiện tại, vừa lưu các trường dish_code, dish_name, unit_name và unit_price. Các trường unit_cost_snapshot và total_cost lưu giá vốn phục vụ theo dõi chi phí. Ví dụ, khi giá món trong danh mục thay đổi từ 85.000 đồng lên 95.000 đồng, dòng món đã ghi nhận trước đó vẫn giữ đơn giá 85.000 đồng.")
p("Hóa đơn lưu riêng tổng trước giảm giá, tỷ lệ giảm, tiền giảm theo hạng thành viên, mã khuyến mãi và tiền giảm khuyến mãi. Yêu cầu đặt chỗ lưu bản chụp nội dung và chính sách đã chốt. Việc lưu các giá trị này là sự lặp dữ liệu có chủ đích nhằm tái hiện giao dịch lịch sử; tính hợp lệ của việc ghi và sửa được kiểm soát tại các hàm nghiệp vụ.")

heading("3.2.2. Thiết lập quan hệ và ràng buộc")
p("Quan hệ một–nhiều được cài đặt bằng khóa ngoại, điển hình là khu vực–bàn, bàn–lịch phục vụ, đơn–dòng món và phiếu nhập–dòng nhập. Quan hệ giữa đơn và hóa đơn sử dụng khóa ngoại duy nhất: mỗi hóa đơn thuộc một đơn, trong khi một đơn có thể chưa có hóa đơn. Trường booking_id của Order cũng có tính duy nhất và cho phép NULL, thể hiện một lịch có tối đa một đơn liên kết trực tiếp, đồng thời vẫn hỗ trợ đơn không gắn lịch.")
p("Hình 3.2a trình bày các bảng và khóa trong chuỗi nghiệp vụ đặt bàn, gọi món và thanh toán. Sơ đồ được dựng từ khóa ngoại thực tế; các cột mô tả và một số liên kết ngoài phạm vi hình được lược bỏ để giữ khả năng đọc.")
figure(FIG / "word-3-2a.png", "Hình 3.2a. Lược đồ đặt bàn, gọi món và thanh toán", 7.2)
p("Quan hệ nhiều–nhiều giữa món và nguyên liệu được cài đặt bằng mô hình trung gian RecipeIngredient. Mỗi dòng lưu món, nguyên liệu và lượng nguyên liệu cần cho một đơn vị món. Cặp món–nguyên liệu được ràng buộc duy nhất và lượng định mức phải lớn hơn không. Khi chế biến nhiều món, nhu cầu của một nguyên liệu được tính bằng tổng tích giữa số phần món và định mức tương ứng.")
figure(FIG / "word-3-2b.png", "Hình 3.2b. Quan hệ giữa món, định mức và nguyên liệu", 2.1)
p("Đối với đặt chỗ trực tuyến, Reservation có thể liên kết một–một với Booking và liên kết một–nhiều với món đặt trước, giao dịch cọc và hoàn cọc. DepositAllocation liên kết yêu cầu đặt chỗ với hóa đơn để ghi nhận tiền cọc được khấu trừ. Việc tách khoản cọc, khoản thu hóa đơn và khoản hoàn giúp xác định rõ nguồn tiền và mục đích xử lý.")
figure(FIG / "word-3-2c.png", "Hình 3.2c. Lược đồ đặt trước và phân bổ tiền cọc", 4.7)
p("Trong các hình, PK là khóa chính, FK là khóa ngoại, UK là thuộc tính duy nhất và dấu ? chỉ cột cho phép NULL. Mũi tên đi từ bảng được tham chiếu đến bảng chứa khóa ngoại; nhãn biểu diễn số lượng bản ghi ở hai phía. Nguồn hình: trích xuất lược đồ PostgreSQL của hệ thống ngày 20/11/2026.")
lead("Ràng buộc dữ liệu và kiểm tra nghiệp vụ")
p("Dữ liệu được kiểm tra tại biểu mẫu, hàm nghiệp vụ và cơ sở dữ liệu. Biểu mẫu hỗ trợ phát hiện lỗi nhập; hàm nghiệp vụ kiểm tra quyền, trạng thái và điều kiện liên quan nhiều bản ghi; PostgreSQL thực thi các ràng buộc khóa, tính duy nhất và CHECK. Các tầng kiểm tra bổ sung cho nhau, bởi dữ liệu hợp lệ tại thời điểm mở biểu mẫu có thể không còn phù hợp tại thời điểm xác nhận.")
table("Bảng 3.4. Các ràng buộc dữ liệu tiêu biểu", ["Đối tượng", "Điều kiện ràng buộc", "Cơ chế"], [
    ("Bàn", "Sức chứa từ 1 đến 100; mã bàn không trùng.", "CHECK và UNIQUE"),
    ("Lịch phục vụ", "Số khách từ 1 đến 100; giờ kết thúc dự kiến sau giờ bắt đầu.", "CHECK"),
    ("Thời gian thực tế", "Khi có đủ hai thời điểm, giờ rời bàn không trước giờ nhận khách.", "CHECK"),
    ("Món và dòng món", "Giá từ 1 đến 999.999.999 đồng; số lượng dòng món từ 1 đến 100.", "CHECK"),
    ("Định mức", "Không trùng cặp món–nguyên liệu; lượng định mức dương.", "UNIQUE và CHECK"),
    ("Tồn kho", "Số lượng tồn không âm.", "CHECK"),
    ("Chi tiết nhập hàng", "Không trùng nguyên liệu trong cùng phiếu; số lượng và đơn giá dương.", "UNIQUE và CHECK"),
    ("Hoàn tiền hóa đơn", "Tiền đã hoàn không âm và không vượt số tiền đã thu.", "CHECK"),
    ("Ca thu ngân", "Mỗi thu ngân chỉ có tối đa một ca đang mở.", "Chỉ mục duy nhất có điều kiện"),
], [1.35, 3.50, 1.68])
p("Không phải mọi điều kiện nghiệp vụ đều được biểu diễn bằng CHECK. Chẳng hạn, số khách không vượt sức chứa cần đối chiếu lịch với bàn; xung đột lịch cần so sánh nhiều bản ghi. Trong phiên bản hiện tại, chống lịch chồng lấn được xử lý bằng truy vấn nghiệp vụ trong cơ chế khóa, chưa có EXCLUDE constraint tại PostgreSQL (PostgreSQL Global Development Group, tài liệu Constraints).")
p("Để bảo toàn lịch sử, nhiều quan hệ tới danh mục sử dụng PROTECT ở Django, chẳng hạn lịch–bàn, dòng món–món và giao dịch kho–nguyên liệu. Danh mục đã sử dụng được chuyển sang trạng thái ngừng hoạt động khi cần thiết. SET_NULL được dùng ở một số liên kết người thực hiện; CASCADE được dùng cho một số thành phần phụ thuộc như dòng nhập thuộc phiếu nhập. Chính sách on_delete này được Django ORM thực hiện, cần phân biệt với hành động ON DELETE của khóa ngoại SQL.")
p("Các trường order_item_reference, source_type và source_id của InventoryTransaction là tham chiếu nguồn nghiệp vụ ở tầng ứng dụng, chưa phải khóa ngoại trực tiếp. Vì vậy, chúng không được trình bày như các quan hệ FK do PostgreSQL bảo đảm.")

heading("3.2.3. Bảo vệ dữ liệu khi có thao tác đồng thời")
p("Khi nhiều phiên cùng truy cập, việc đọc thấy một đối tượng còn khả dụng không bảo đảm đối tượng vẫn khả dụng tại thời điểm lưu. Kết nối PostgreSQL hiện sử dụng mức cô lập Read Committed. Ở mức này, mỗi câu lệnh đọc thấy dữ liệu đã được xác nhận trước khi câu lệnh bắt đầu, nhưng hai phiên vẫn có thể cùng đọc thấy một bàn trống nếu chưa có cơ chế đồng bộ (PostgreSQL Global Development Group, tài liệu Transaction Isolation).")
lead("Kiểm soát cập nhật lịch đặt bàn")
p("Hệ thống sử dụng transaction.atomic() để bao các thay đổi liên quan trong một giao dịch. Trước khi cập nhật lịch bàn, hàm lock_seating_schedule() lấy khóa tư vấn theo giao dịch bằng pg_advisory_xact_lock(81723002). Các thao tác cùng sử dụng khóa phải chờ nhau; khóa được giải phóng khi giao dịch kết thúc. Sau đó, ứng dụng khóa các dòng liên quan bằng select_for_update(), kiểm tra lại dữ liệu và mới thực hiện ghi nhận.")
p("Khóa tư vấn nêu trên có phạm vi chung cho lịch bàn, không được tách riêng theo từng mã bàn. Cách tổ chức này đơn giản hóa việc phối hợp giữa tạo lịch, chuyển bàn, nhận khách và cập nhật trạng thái khu vực. Khi sửa lịch, trường revision còn được đối chiếu để từ chối biểu mẫu dựa trên phiên bản đã cũ.")
figure(FIG / "word-3-3.png", "Hình 3.3. Quy trình kiểm soát đồng thời khi ghi lịch đặt bàn", 3.6)
p("Hai khoảng thời gian được xác định là giao nhau khi thời điểm bắt đầu của mỗi khoảng nhỏ hơn thời điểm kết thúc của khoảng còn lại. Quy tắc sử dụng khoảng nửa mở cho phép lịch sau bắt đầu đúng lúc lịch trước kết thúc. Tuy nhiên, hệ thống còn phải xét trạng thái lịch, thời hạn giữ chỗ và việc khách đã thực sự rời bàn. Khách đang được phục vụ không được xem là đã rời bàn chỉ vì hết thời gian dự kiến.")
p("Khi hai người cùng đặt một khoảng trên một bàn, giao dịch lấy khóa trước được kiểm tra và ghi nhận trước. Giao dịch còn lại chờ, đọc lại lịch đã lưu và bị từ chối nếu phát hiện xung đột. Hiệu lực của cơ chế phụ thuộc việc các luồng ghi cạnh tranh cùng tuân thủ quy tắc lấy khóa; khóa nghiệp vụ không tự bảo vệ một lệnh SQL tùy ý bên ngoài ứng dụng.")
lead("Kiểm soát biến động kho")
p("Khi xác nhận phiếu nhập, hệ thống khóa phiếu, kiểm tra trạng thái nháp, đọc các dòng nhập và khóa các nguyên liệu theo thứ tự khóa chính. Tồn kho, giá vốn bình quân, sổ biến động và trạng thái phiếu được cập nhật trong cùng giao dịch. Việc xác nhận lại phiếu đã nhận bị từ chối để ngăn cộng tồn lặp.")
p("Khi gửi món xuống bếp, ứng dụng tổng hợp nhu cầu từ định mức, xét lượng nguyên liệu đang được giữ cho đặt trước và kiểm tra phần tồn có thể sử dụng. Những dòng món đã ghi nhận inventory_deducted_at không tiếp tục bị trừ kho như một lần gửi mới. Nếu thiếu nguyên liệu, lỗi nghiệp vụ làm hoàn tác phần cập nhật trong giao dịch. Khi hủy món, hoàn nguyên liệu phụ thuộc giai đoạn chế biến; món đã chế biến không được mặc nhiên hoàn về kho dưới dạng nguyên liệu ban đầu.")
p("Định mức và số lượng kho được quản lý theo đơn vị của từng nguyên liệu. Hệ thống hiện chưa có mô hình quy đổi đơn vị tự động, vì vậy dữ liệu nhập phải được chuẩn hóa về cùng đơn vị trước khi tính toán. Điều này đặc biệt cần thiết với các cặp đơn vị như kilôgam–gam hoặc lít–mililít.")
lead("Kiểm soát thanh toán và thông báo lặp")
p("Nghiệp vụ thanh toán khóa các bản ghi liên quan, kiểm tra trạng thái đơn, số tiền và phiên bản trước khi ghi hóa đơn hoặc phiếu thu. Quan hệ duy nhất giữa hóa đơn và đơn hỗ trợ ngăn tạo nhiều hóa đơn cho cùng một đơn; việc ngăn thu lặp còn dựa vào mã giao dịch và kiểm tra trạng thái trong hàm xử lý.")
p("Thông báo từ cổng thanh toán có thể được gửi lại hoặc đến đồng thời. Vì vậy, hệ thống nhận diện giao dịch đã xử lý và không tạo thêm tác động thu tiền cho cùng kết quả. Với ZaloPay, trường hợp đã xác minh có tiền nhưng đơn hoặc lịch đã thay đổi được đưa sang trạng thái cần đối soát khi phù hợp. Cơ chế này bảo đảm việc áp dụng kết quả nghiệp vụ vào cơ sở dữ liệu, không giả định mạng chỉ chuyển thông báo đúng một lần.")
p("Nếu xảy ra lỗi trong phạm vi giao dịch cơ sở dữ liệu, các thay đổi liên quan được hoàn tác. Tuy nhiên, hoàn tác cơ sở dữ liệu không đảo ngược khoản tiền đã được xử lý tại nhà cung cấp bên ngoài; trường hợp đó cần quy trình đối soát hoặc hoàn tiền riêng. Giao diện phải lấy trạng thái hiện tại từ máy chủ thay vì suy luận kết quả chỉ từ thao tác nhấn nút hoặc việc chuyển trang (Django Software Foundation, tài liệu Database transactions).")

heading("3.2.4. Migration và dữ liệu thử")
p("Migration được sử dụng để quản lý cấu trúc cơ sở dữ liệu theo phiên bản mô hình. Mỗi thay đổi về bảng, trường, khóa, chỉ mục hoặc ràng buộc được mô tả trong lịch sử migration. Quy trình thực hiện gồm cập nhật mô hình, tạo migration, kiểm tra ảnh hưởng tới dữ liệu đang có và áp dụng trên môi trường phù hợp. Đối với thay đổi làm chặt điều kiện hợp lệ, dữ liệu cũ phải được kiểm tra trước khi thêm ràng buộc.")
p("Tại lần đối chiếu ngày 20/11/2026, cơ sở dữ liệu đã ghi nhận áp dụng 100 migration, bao gồm các ứng dụng Django; không có migration đang chờ. Lệnh kiểm tra thay đổi mô hình ở chế độ chỉ đọc không phát hiện thay đổi cần tạo migration mới. Kết quả này xác nhận trạng thái phiên bản cấu trúc, còn tính đúng của các quy tắc nghiệp vụ tiếp tục được đánh giá bằng dữ liệu thử và kiểm thử giao dịch.")
p("Dữ liệu thử được xây dựng theo các điều kiện biên, trạng thái và khả năng gửi lặp. Mỗi nhóm dữ liệu gắn với một kết quả mong đợi cụ thể, giúp phát hiện sai lệch trước khi sử dụng dữ liệu vận hành.")
table("Bảng 3.5. Nhóm dữ liệu phục vụ kiểm thử nghiệp vụ", ["Nhóm", "Dữ liệu cần chuẩn bị", "Mục tiêu kiểm tra"], [
    ("Tài khoản", "Tài khoản theo vai trò; tài khoản bị khóa hoặc thu hồi quyền.", "Xác thực và kiểm tra lại quyền khi ghi dữ liệu."),
    ("Bàn và lịch", "Bàn vừa đủ, dư hoặc thiếu chỗ; lịch sát biên và chồng lấn.", "Sức chứa, khoảng thời gian và lịch còn hiệu lực."),
    ("Món và đơn", "Món còn bán, ngừng bán; thay đổi giá sau khi đã ghi dòng món.", "Giữ giá lịch sử và kiểm soát chuyển trạng thái."),
    ("Kho", "Tồn đủ, thiếu; phiếu nháp, đã nhận; thao tác xác nhận lặp.", "Định mức, tồn khả dụng và ngăn ghi biến động lặp."),
    ("Đặt trước và cọc", "Giữ chỗ còn hạn, hết hạn; yêu cầu thay đổi sau khi tạo giao dịch.", "Quan hệ giữa lịch, món đặt trước và tiền cọc."),
    ("Thanh toán", "Đơn chưa trả, đã trả; thông báo lặp hoặc đến đồng thời.", "Tính tiền và chỉ áp dụng một lần tác động thu tiền."),
    ("Hoàn tác", "Lỗi trong nghiệp vụ cập nhật nhiều bản ghi, chẳng hạn thiếu nguyên liệu.", "Không để dữ liệu cập nhật dở dang trong giao dịch."),
], [1.10, 2.90, 2.53])
p("Đối với kiểm thử đồng thời, các thao tác cần chạy trên những kết nối PostgreSQL độc lập, thay vì chỉ gửi tuần tự nhiều yêu cầu. Dự án sử dụng TransactionTestCase và các luồng thực thi để kiểm tra các tình huống cạnh tranh như đặt cùng bàn, mở đơn cho cùng lượt phục vụ và xử lý đồng thời thông báo thanh toán. Cơ sở dữ liệu kiểm thử được tách riêng nhằm không làm thay đổi dữ liệu vận hành.")
p("Các chỉ mục được bổ sung theo nhu cầu truy vấn. Trong đó, booking_slot_idx hỗ trợ tra cứu lịch theo bàn, trạng thái và khoảng thời gian; booking_expiry_idx và booking_no_show_idx hỗ trợ xử lý lịch hết hạn hoặc khách không đến; order_kitchen_queue_idx phục vụ danh sách món tại bếp. Chỉ mục hỗ trợ truy vấn nhưng không thay thế khóa, ràng buộc và kiểm tra nghiệp vụ.")

heading("Tài liệu tham khảo cho mục 3.2", 2)
references = [
    "Django Software Foundation. Django 5.2 documentation: Model field reference. https://docs.djangoproject.com/en/5.2/ref/models/fields/",
    "Django Software Foundation. Django 5.2 documentation: Time zones. https://docs.djangoproject.com/en/5.2/topics/i18n/timezones/",
    "Django Software Foundation. Django 5.2 documentation: Database transactions. https://docs.djangoproject.com/en/5.2/topics/db/transactions/",
    "Django Software Foundation. Django 5.2 documentation: Migrations. https://docs.djangoproject.com/en/5.2/topics/migrations/",
    "PostgreSQL Global Development Group. PostgreSQL 17 documentation: Constraints. https://www.postgresql.org/docs/17/ddl-constraints.html",
    "PostgreSQL Global Development Group. PostgreSQL 17 documentation: Transaction Isolation. https://www.postgresql.org/docs/17/transaction-iso.html",
    "PostgreSQL Global Development Group. PostgreSQL 17 documentation: Explicit Locking. https://www.postgresql.org/docs/17/explicit-locking.html",
]
for text in references:
    para = p(text)
    para.paragraph_format.first_line_indent = Inches(0)
    para.paragraph_format.line_spacing = 1.1
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for r in para.runs:
        r.font.size = Pt(11)
p("Nguồn đối chiếu triển khai: mã nguồn mô hình, migration, dịch vụ nghiệp vụ và lược đồ PostgreSQL của hệ thống quản lý nhà hàng Cơm Quê; trích xuất ngày 20/11/2026.")

doc.core_properties.title = "Mục 3.2 Xây dựng cơ sở dữ liệu"
doc.core_properties.subject = "Nội dung báo cáo tốt nghiệp đối chiếu với hệ thống Cơm Quê"
doc.core_properties.author = ""
doc.core_properties.keywords = "PostgreSQL, Django, cơ sở dữ liệu, giao dịch"
target = OUT / "Muc_3_2_Xay_dung_co_so_du_lieu.docx"
doc.save(target)
print(target)
print("Paragraphs:", len(doc.paragraphs), "Tables:", len(doc.tables), "Images:", len(doc.inline_shapes))
