"""Write UML use case diagram sources for the current restaurant workflows."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "use-case"
OUT.mkdir(parents=True, exist_ok=True)

ACTORS = {
    "customer": "Khách hàng", "manager": "Quản lý", "waiter": "Nhân viên\nphục vụ",
    "cashier": "Nhân viên\nthu ngân", "kitchen": "Nhân viên bếp", "inventory": "Nhân viên kho",
    "admin": "Quản trị\nhệ thống", "staff": "Nhân viên\nnội bộ", "vnpay": "Cổng VNPAY",
    "ai": "Nhà cung cấp\nAI hội thoại",
}
EXTERNAL_RIGHT = {"vnpay", "ai"}


def diagram(stem, title, actors, cases, associations, relations=(), generalizations=(), note=""):
    return dict(stem=stem, title=title, actors=actors, cases=dict(cases), associations=associations,
                relations=relations, generalizations=generalizations, note=note)


DIAGRAMS = [
    diagram("use-case-tong-quat", "USE CASE TỔNG QUÁT", ["customer", "waiter", "cashier", "kitchen", "inventory", "manager", "admin", "vnpay", "ai"], [
        ("TQ01", "Xem thực đơn"), ("TQ02", "Đặt và tra cứu bàn"), ("TQ03", "Gửi yêu cầu QR\nvà gọi phục vụ"),
        ("TQ04", "Trò chuyện với chatbot"), ("TQ05", "Nhận gợi ý món"), ("TQ06", "Tiếp nhận khách\nvà điều phối bàn"),
        ("TQ07", "Quản lý đơn\nvà gọi món"), ("TQ08", "Xác nhận yêu cầu QR"), ("TQ09", "Chế biến và báo món xong"),
        ("TQ10", "Cập nhật còn hoặc hết món"), ("TQ11", "Tính tiền và thanh toán"), ("TQ12", "Tra cứu và cập nhật\nhồ sơ khách hàng"),
        ("TQ13", "Quản lý thực đơn"), ("TQ14", "Quản lý kho nguyên liệu"), ("TQ15", "Xem sử dụng hôm nay"),
        ("TQ16", "Xem báo cáo\nvà dự báo số đơn"), ("TQ17", "Quản lý nhân sự\nvà tài khoản"), ("TQ18", "Quản trị đặc quyền"),
        ("TQ19", "Quản lý hạng thành viên\nvà khuyến mãi"),
    ], [
        ("customer", "TQ01 TQ02 TQ03 TQ04 TQ05"), ("waiter", "TQ05 TQ06 TQ07 TQ08 TQ12"),
        ("cashier", "TQ05 TQ06 TQ07 TQ08 TQ11 TQ12"), ("kitchen", "TQ09 TQ10"),
        ("inventory", "TQ14 TQ15"), ("manager", "TQ05 TQ06 TQ07 TQ08 TQ09 TQ10 TQ11 TQ12 TQ13 TQ14 TQ15 TQ16 TQ17 TQ19"),
        ("admin", "TQ18"), ("vnpay", "TQ11"), ("ai", "TQ04"),
    ], generalizations=[("admin", "manager")], note="Các thao tác nội bộ yêu cầu đăng nhập và quyền tương ứng. Chi tiết từng nghiệp vụ ở các sơ đồ phân hệ."),

    diagram("01-tai-khoan-nhan-su", "TÀI KHOẢN VÀ NHÂN SỰ", ["staff", "manager", "admin"], [
        ("TK01", "Đăng nhập"), ("TK02", "Đăng xuất"), ("TK03", "Đổi mật khẩu cá nhân"),
        ("TK04", "Tạo nhân viên"), ("TK05", "Tạo tài khoản\nvà gán chức vụ"), ("TK06", "Cập nhật hồ sơ\nvà trạng thái làm việc"),
        ("TK07", "Đổi chức vụ"), ("TK08", "Khóa hoặc mở tài khoản"), ("TK09", "Đặt lại mật khẩu nhân viên"),
        ("TK10", "Xem nhật ký nhân sự"), ("TK11", "Quản lý tài khoản\nđược bảo vệ"),
    ], [("staff", "TK01 TK02 TK03"), ("manager", "TK04 TK06 TK07 TK08 TK09 TK10"), ("admin", "TK11")],
        relations=[("TK04", "include", "TK05", "")], generalizations=[("manager", "staff"), ("admin", "manager")],
        note="Mọi thao tác quản lý tuân thủ chính sách bảo vệ tài khoản. Mở khóa không phục hồi phiên cũ; chức vụ quyết định nhóm quyền."),

    diagram("02-khach-hang-dat-ban", "KHÁCH HÀNG VÀ ĐẶT BÀN", ["customer", "waiter", "cashier", "manager"], [
        ("DB01", "Xem và tìm khách hàng"), ("DB02", "Tạo hoặc sửa hồ sơ khách"), ("DB03", "Quản lý hạng thành viên"),
        ("DB04", "Tìm và đề xuất bàn"), ("DB05", "Gửi đặt bàn trực tuyến"), ("DB06", "Tra cứu đặt bàn"),
        ("DB07", "Tạo hoặc sửa đặt bàn nội bộ"), ("DB08", "Kiểm tra giờ phục vụ\nsức chứa và lịch bàn"),
        ("DB09", "Xác nhận đặt bàn"), ("DB10", "Nhận khách đặt trước"), ("DB11", "Nhận khách trực tiếp"),
        ("DB12", "Hủy lịch hoặc\nghi nhận không đến"), ("DB13", "Chuyển và dọn bàn"),
        ("DB14", "Quản lý khu vực và bàn"), ("DB15", "Cấu hình giờ\nvà thời lượng đặt bàn"),
    ], [("customer", "DB04 DB05 DB06"), ("waiter", "DB01 DB02 DB04 DB07 DB09 DB10 DB11 DB12 DB13"),
        ("cashier", "DB01 DB02 DB04 DB07 DB09 DB10 DB11 DB12 DB13"),
        ("manager", "DB01 DB02 DB03 DB04 DB07 DB09 DB10 DB11 DB12 DB13 DB14 DB15")],
        relations=[("DB04", "include", "DB08", ""), ("DB05", "include", "DB08", ""), ("DB07", "include", "DB08", "")],
        note="Đặt trước: giờ đến từ 09:00 và trước 22:00; dùng bàn kết thúc chậm nhất 22:00. Tìm bàn chưa tạo giữ chỗ."),

    diagram("03-thuc-don-goi-mon-bep", "THỰC ĐƠN GỌI MÓN VÀ BẾP", ["waiter", "cashier", "kitchen", "manager"], [
        ("GM01", "Mở đơn cho lượt khách"), ("GM02", "Thêm món và ghi chú"), ("GM03", "Sửa món chưa gửi bếp"),
        ("GM04", "Gửi món xuống bếp"), ("GM05", "Xuất nguyên liệu\ntheo định lượng"), ("GM06", "Bắt đầu chế biến"),
        ("GM07", "Báo món đã xong"), ("GM08", "Xác nhận đã phục vụ"), ("GM09", "Hủy món"),
        ("GM10", "Hoàn nguyên liệu\nchưa chế biến"), ("GM11", "Cập nhật còn hoặc hết món"),
        ("GM12", "Quản lý món giá\nnhóm món và đơn vị"), ("GM13", "Xem nhật ký đơn"),
    ], [("waiter", "GM01 GM02 GM03 GM04 GM08 GM09"), ("cashier", "GM01 GM02 GM03 GM04 GM08 GM09"),
        ("kitchen", "GM06 GM07 GM11"), ("manager", "GM01 GM02 GM03 GM04 GM06 GM07 GM08 GM09 GM11 GM12 GM13")],
        relations=[("GM05", "extend", "GM04", "Món bật theo dõi tồn kho"),
                   ("GM10", "extend", "GM09", "Món chờ làm đã xuất kho và chưa hoàn")],
        note="Bếp: chờ làm → đang làm → đã xong; phục vụ xác nhận đã phục vụ. Hủy món đã bắt đầu làm cần quyền riêng và không tự hoàn kho."),

    diagram("04-khach-qr", "KHÁCH TỰ PHỤC VỤ QUA QR", ["customer", "waiter", "cashier", "manager"], [
        ("QR01", "Xem menu và trạng thái bàn"), ("QR02", "Gửi yêu cầu nhận bàn"), ("QR03", "Xác nhận nhận bàn"),
        ("QR04", "Mở hoặc liên kết đơn"), ("QR05", "Gửi giỏ gọi món"), ("QR06", "Xác nhận giỏ gọi món"),
        ("QR07", "Tạo dòng món\nvà gửi bếp"), ("QR08", "Từ chối yêu cầu\nkèm lý do"),
        ("QR09", "Gửi yêu cầu phục vụ"), ("QR10", "Hoàn tất yêu cầu phục vụ"), ("QR11", "Quản lý mã QR bàn"),
    ], [("customer", "QR01 QR02 QR05 QR09"), ("waiter", "QR03 QR06 QR08 QR10"),
        ("cashier", "QR03 QR06 QR08 QR10"), ("manager", "QR03 QR06 QR08 QR10 QR11")],
        relations=[("QR03", "include", "QR04", ""), ("QR06", "include", "QR07", "")],
        note="Khách gửi giỏ chưa làm phát sinh xuất kho. Nhân viên duyệt mới tạo món và gửi bếp; bước này vẫn kiểm tra tồn và chống xử lý lặp."),

    diagram("05-hoa-don-thanh-toan", "HÓA ĐƠN VÀ THANH TOÁN", ["waiter", "cashier", "manager", "vnpay"], [
        ("TT01", "Yêu cầu thanh toán"), ("TT02", "Xem số phải thanh toán"), ("TT03", "Áp dụng mã khuyến mãi"),
        ("TT04", "Thu tiền trực tiếp"), ("TT05", "Ghi phiếu thu\nvà chốt hóa đơn"), ("TT06", "Tách hóa đơn"),
        ("TT07", "Ghép lại hóa đơn tách"), ("TT08", "Thanh toán nhiều bàn"), ("TT09", "Tạo giao dịch VNPAY"),
        ("TT10", "Xử lý thông báo IPN"), ("TT11", "Xác minh chữ ký\ntham chiếu và số tiền"),
        ("TT12", "In và tra cứu hóa đơn"), ("TT13", "Quản lý mã khuyến mãi"),
    ], [("waiter", "TT01"), ("cashier", "TT01 TT02 TT03 TT04 TT06 TT07 TT08 TT09 TT12"),
        ("manager", "TT01 TT02 TT03 TT04 TT06 TT07 TT08 TT09 TT12 TT13"), ("vnpay", "TT09 TT10")],
        relations=[("TT04", "include", "TT05", ""), ("TT10", "include", "TT11", ""),
                   ("TT03", "extend", "TT02", "Người dùng chọn mã hợp lệ")],
        note="Thu đủ số còn lại trong một lần. IPN chỉ chốt khi xác minh và kết quả thành công hợp lệ; trang quay về không tự chứng minh đã thu tiền."),

    diagram("06-kho-nguyen-lieu", "KHO VÀ NGUYÊN LIỆU", ["inventory", "manager"], [
        ("KH01", "Quản lý nguyên liệu\nvà nhà cung cấp"), ("KH02", "Quản lý định lượng món"),
        ("KH03", "Lập phiếu nhập nháp"), ("KH04", "Xác nhận nhận hàng"), ("KH05", "Cập nhật tồn\nvà giá vốn bình quân"),
        ("KH06", "Nhập xuất điều chỉnh\ntrực tiếp"), ("KH07", "Lập và nhập kiểm kê"), ("KH08", "Chốt kiểm kê"),
        ("KH09", "Ghi nhận chênh lệch tồn"), ("KH10", "Ghi nhận hao hụt"),
        ("KH11", "Xem tồn và cảnh báo"), ("KH12", "Xem sử dụng hôm nay"), ("KH13", "Xem lịch sử giao dịch kho"),
    ], [("inventory", "KH01 KH02 KH03 KH04 KH06 KH07 KH08 KH10 KH11 KH12 KH13"),
        ("manager", "KH01 KH02 KH03 KH04 KH06 KH07 KH08 KH10 KH11 KH12 KH13")],
        relations=[("KH04", "include", "KH05", ""), ("KH08", "include", "KH09", "")],
        note="Sử dụng thuần hôm nay = xuất theo món + xuất thủ công − hoàn. Hao hụt trình bày riêng; không cộng các đơn vị kg lít hoặc cái với nhau."),

    diagram("07-bao-cao-ai", "BÁO CÁO VÀ HỖ TRỢ QUYẾT ĐỊNH", ["customer", "waiter", "cashier", "manager", "ai"], [
        ("BC01", "Xem báo cáo kinh doanh"), ("BC02", "Xuất doanh thu CSV"), ("BC03", "Xem dự báo số đơn"),
        ("BC04", "Nhận gợi ý gọi thêm"), ("BC05", "Trò chuyện và hỏi\nthông tin công khai"),
    ], [("customer", "BC04 BC05"), ("waiter", "BC04"), ("cashier", "BC04"),
        ("manager", "BC01 BC02 BC03 BC04"), ("ai", "BC05")],
        note="Apriori dùng luật lưu tại hệ thống; dự báo đọc bộ kết quả được cập nhật ngoài request. Nhà cung cấp AI hội thoại chỉ tham gia chatbot."),
]


def quoted(value):
    return json.dumps(value, ensure_ascii=False)


def dot_source(d):
    out = ['digraph UseCase {',
           'graph [rankdir=LR, bgcolor=white, pad=0.35, nodesep=0.26, ranksep=1.45, splines=spline, outputorder=edgesfirst, fontname="Arial", fontsize=21, labelloc=t, labeljust=c,',
           f'label={quoted(d["title"] + chr(10) + "HỆ THỐNG QUẢN LÝ NHÀ HÀNG CƠM QUÊ")}];',
           'node [fontname="Arial", fontsize=13];',
           'edge [fontname="Arial", fontsize=10, color="#344054", fontcolor="#344054", penwidth=1.1, arrowsize=0.8];']
    left = [a for a in d["actors"] if a not in EXTERNAL_RIGHT]
    right = [a for a in d["actors"] if a in EXTERNAL_RIGHT]
    for actor in d["actors"]:
        # Renderer replaces these reserved boxes with proper UML stick actors.
        out.append(f'actor__{actor} [id="actor__{actor}", shape=box, fixedsize=true, width=1.5, height=1.6, style=filled, color=white, fillcolor=white, label={quoted(ACTORS[actor])}];')
    out.append('{rank=same; ' + '; '.join('actor__' + a for a in left) + ';}')
    if right:
        out.append('{rank=same; ' + '; '.join('actor__' + a for a in right) + ';}')
    out += ['subgraph cluster_system {', 'label="Cơm Quê"; fontname="Arial"; fontsize=17; color="#881b2d"; penwidth=1.3; margin=24;']
    for code, name in d["cases"].items():
        out.append(f'{code} [shape=ellipse, style=filled, fillcolor=white, color="#344054", penwidth=1.15, margin="0.22,0.12", width=2.75, label={quoted(code + chr(10) + name)}];')
    # Keep primary goals in one column and obligatory/optional sub-behaviors in another.
    supports = {target for source, kind, target, condition in d["relations"] if kind == "include"}
    supports |= {source for source, kind, target, condition in d["relations"] if kind == "extend"}
    main = [c for c in d["cases"] if c not in supports]
    if main:
        out.append('{rank=same; ' + '; '.join(main) + ';}')
    if supports:
        out.append('{rank=same; ' + '; '.join(c for c in d["cases"] if c in supports) + ';}')
    out.append('}')
    for actor, text in d["associations"]:
        for code in text.split():
            assert code in d["cases"] and actor in d["actors"]
            source, target = (code, 'actor__' + actor) if actor in EXTERNAL_RIGHT else ('actor__' + actor, code)
            out.append(f'{source} -> {target} [dir=none];')
    for relation_index, (source, kind, target, condition) in enumerate(d["relations"]):
        assert source in d["cases"] and target in d["cases"]
        label = f'«{kind}»' + ("\n[" + condition + "]" if condition else "")
        # Extend arrows point from optional behavior to the base use case.
        out.append(f'{source} -> {target} [style=dashed, arrowhead=vee, label={quoted(label)}, color="#881b2d", fontcolor="#881b2d", constraint={"false" if kind == "extend" else "true"}];')
        if kind == 'extend':
            out.append(f'{target} [group="extension_{relation_index}"]; {source} [group="extension_{relation_index}"];')
            out.append(f'{target} -> {source} [style=invis, weight=100];')
    for child, parent in d["generalizations"]:
        out.append(f'actor__{child} -> actor__{parent} [arrowhead=empty, constraint=false, penwidth=1.4];')
    out.append('}')
    return '\n'.join(out) + '\n'


def plantuml_source(d):
    out = ['@startuml', 'left to right direction', 'skinparam monochrome true', 'skinparam shadowing false',
           'skinparam defaultFontName Arial', 'title ' + d['title']]
    for actor in d['actors']:
        out.append(f'actor {quoted(ACTORS[actor])} as A_{actor}')
    out.append('rectangle "Hệ thống quản lý nhà hàng Cơm Quê" {')
    for code, name in d['cases'].items():
        out.append(f'  usecase {quoted(code + chr(10) + name)} as {code}')
    out.append('}')
    for actor, codes in d['associations']:
        for code in codes.split():
            out.append(f'A_{actor} -- {code}')
    for source, kind, target, condition in d['relations']:
        out.append(f'{source} ..> {target} : <<{kind}>>' + ('\\n[' + condition + ']' if condition else ''))
    for child, parent in d['generalizations']:
        out.append(f'A_{child} --|> A_{parent}')
    out += ['legend bottom', d['note'], 'endlegend', '@enduml']
    return '\n'.join(out) + '\n'


for d in DIAGRAMS:
    (OUT / (d['stem'] + '.dot')).write_text(dot_source(d), encoding='utf-8')
    (OUT / (d['stem'] + '.puml')).write_text(plantuml_source(d), encoding='utf-8')
(OUT / 'manifest.json').write_text(json.dumps(DIAGRAMS, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Generated {len(DIAGRAMS)} diagrams: 1 overview and 7 module diagrams in {OUT}')
