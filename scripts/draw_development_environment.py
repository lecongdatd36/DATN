"""Draw thesis figure 3.1 from a credential-free local environment inspection."""
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
STEM = "hinh-3-1-moi-truong-va-cau-truc-du-an"
check = subprocess.run(
    [sys.executable, "manage.py", "check"], cwd=ROOT,
    capture_output=True, text=True, encoding="utf-8", check=True,
).stdout.strip()
with connection.cursor() as cursor:
    cursor.execute("SHOW server_version")
    postgres = cursor.fetchone()[0]
executor = MigrationExecutor(connection)
pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
observations = {
    "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "os": f"{platform.system()} {platform.release()}",
    "python": platform.python_version(), "django": django.get_version(),
    "postgresql": postgres, "database_connection": "OK",
    "django_check": check, "pending_migrations": pending,
    "scope": "Local development environment; no credentials collected.",
}
(OUT / f"{STEM}.verification.json").write_text(
    json.dumps(observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

W, H, S = 1600, 1810, 3
INK, MUTED, BLUE, TEAL = "#172c40", "#586b7b", "#234f75", "#157368"
BORDER, PALE = "#d0dce5", "#f4f7fa"
im = Image.new("RGB", (W*S, H*S), "white")
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">Môi trường phát triển và cấu trúc dự án</title>',
       '<desc id="desc">Cấu trúc thư mục Django thực tế, kết quả kiểm tra môi trường và luồng phân tích dữ liệu tách khỏi yêu cầu web. Không chứa thông tin xác thực.</desc>',
       '<rect width="100%" height="100%" fill="white"/>']


def font(size, bold=False, mono=False):
    name = "consola.ttf" if mono else ("arialbd.ttf" if bold else "arial.ttf")
    return ImageFont.truetype("C:/Windows/Fonts/" + name, round(size*S))


def text(x, y, value, size=27, color=INK, bold=False, mono=False,
         anchor="start", max_width=None, gap=None):
    for i, line in enumerate(value.split("\n")):
        yy = y + i*(gap or size*1.35)
        if max_width:
            assert d.textlength(line, font=font(size, bold, mono)) <= max_width*S, line
        d.text((x*S, yy*S), line, font=font(size, bold, mono), fill=color,
               anchor="lm" if anchor == "start" else "mm")
        svg.append(f'<text x="{x}" y="{yy}" text-anchor="{anchor}" dominant-baseline="central" font-family="{("Consolas, monospace" if mono else "Arial, sans-serif")}" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}" xml:space="preserve">{escape(line)}</text>')


def rect(x, y, w, h, fill="white", stroke=BORDER, radius=16):
    d.rounded_rectangle((x*S, y*S, (x+w)*S, (y+h)*S), radius=radius*S,
                       fill=fill, outline=stroke, width=2*S)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')


def line(x1, y1, x2, y2, color=BORDER, arrow=False):
    d.line((x1*S, y1*S, x2*S, y2*S), fill=color, width=2*S)
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2"/>')
    if arrow:
        pts = [(x2, y2), (x2-10, y2-6), (x2-10, y2+6)]
        d.polygon([(x*S, y*S) for x, y in pts], fill=color)
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{color}"/>')


text(800, 58, "MÔI TRƯỜNG PHÁT TRIỂN VÀ CẤU TRÚC DỰ ÁN", 39,
     bold=True, anchor="middle", max_width=1500)
text(800, 108, "Ứng dụng Django phân mô-đun • Cấu trúc rút gọn từ mã nguồn thực tế", 27,
     color=MUTED, anchor="middle", max_width=1500)

# Source tree: names are checked against the repository before rendering.
rect(44, 156, 846, 1155)
text(76, 198, "01  CẤU TRÚC THƯ MỤC", 29, bold=True, color=BLUE)
line(76, 230, 858, 230)
text(76, 265, "DOANTOTNGHIEP/", 29, bold=True, mono=True)
rows = [
    ("manage.py", "Điểm chạy Django", 0),
    ("QLNH/", "Cấu hình, định tuyến", 0),
    ("core/", "Thành phần dùng chung", 0),
    ("apps/", "Các mô-đun nghiệp vụ", 0),
    ("accounts/", "Tài khoản, phân quyền", 1),
    ("employees/", "Nhân viên", 1),
    ("workforce/", "Ca làm, chấm công", 1),
    ("customers/", "Khách hàng", 1),
    ("customer_portal/", "Cổng khách hàng", 1),
    ("seating/", "Khu vực, bàn", 1),
    ("bookings/", "Lịch đặt bàn", 1),
    ("reservations/", "Đặt chỗ, tiền cọc", 1),
    ("menu/", "Thực đơn", 1),
    ("orders/", "Đơn hàng, thanh toán", 1),
    ("inventory/", "Kho, nguyên liệu", 1),
    ("reports/", "Báo cáo, dự báo", 1),
    ("templates/", "Giao diện HTML", 0),
    ("static/", "CSS, JavaScript, ảnh", 0),
    ("ai_tools/", "Xử lý dữ liệu, mô hình", 0),
    ("scripts/", "Tác vụ chạy riêng", 0),
    ("notebooks/", "Notebook / Google Colab", 0),
    ("artifacts/", "Dữ liệu, kết quả chạy", 0),
    ("fixtures/", "Dữ liệu khởi tạo", 0),
    ("docs/", "Tài liệu, sơ đồ", 0),
    ("requirements*.txt", "Các nhóm phụ thuộc", 0),
]
for i, (name, desc, depth) in enumerate(rows):
    if name != "requirements*.txt":
        actual = ROOT / ("apps" if depth else "") / name
        assert actual.exists(), actual
    yy = 307 + i*37
    prefix = ("│   └── " if name == "reports/" else "│   ├── ") if depth else ("└── " if i == len(rows)-1 else "├── ")
    text(80, yy, prefix + name, 25, mono=True,
         color=BLUE if depth else INK, max_width=423)
    text(518, yy, desc, 25, color=MUTED, max_width=348)
text(78, 1272, "Chỉ hiển thị các thư mục và tệp tiêu biểu.", 24, color=MUTED)

# Actual local environment results, shown as a designed terminal card.
rect(920, 156, 636, 646)
text(950, 198, "02  KIỂM TRA MÔI TRƯỜNG", 29, bold=True, color=BLUE)
text(950, 247, observations["os"] + "  •  Môi trường ảo .venv", 26, color=MUTED)
rect(946, 281, 584, 398, fill="#132b3d", stroke="#132b3d", radius=12)
terminal = [
    ("$ python --version", "#a7d5ee", 25),
    ("Python " + observations["python"], "#ffffff", 27),
    ("$ python -m django --version", "#a7d5ee", 25),
    (observations["django"], "#ffffff", 27),
    ("$ python manage.py check", "#a7d5ee", 25),
    ("System check identified no issues", "#b7edca", 23),
    ("(0 silenced).", "#b7edca", 23),
    ("PostgreSQL " + postgres, "#ffffff", 27),
    ("Kết nối cơ sở dữ liệu: OK", "#b7edca", 27),
]
for i, (value, color, size) in enumerate(terminal):
    text(968, 310+i*40, value, size, color=color, mono=True, max_width=540)
rect(946, 701, 584, 69, fill="#fff7e8", stroke="#e5c795", radius=10)
text(967, 735, f"Migration chưa áp dụng: {pending}", 27, color="#805b1b", bold=True,
     max_width=538)

rect(920, 826, 636, 485)
text(950, 869, "03  NGHIỆP VỤ DÙNG CHUNG", 28, bold=True, color=BLUE)
text(950, 915, "Ví dụ tại apps/orders/", 26, color=MUTED)
for yy, name, desc in [
    (965, "views.py", "Tiếp nhận yêu cầu, trả kết quả"),
    (1048, "services.py", "Xử lý quy tắc nghiệp vụ"),
    (1131, "models.py / selectors.py", "Dữ liệu và truy vấn"),
]:
    text(952, yy, name, 27, mono=True, bold=True, max_width=560)
    text(952, yy+34, desc, 25, color=MUTED, max_width=560)
line(950, 1190, 1525, 1190)
text(950, 1227, "Giao diện gọi lại dịch vụ nghiệp vụ;", 26, max_width=560)
text(950, 1263, "quy tắc được tập trung để dùng chung.", 26, max_width=560)

# The asynchronous/offline analysis route is separate from normal requests.
rect(44, 1340, 1512, 362, fill=PALE)
text(76, 1382, "04  TÁC VỤ PHÂN TÍCH CHẠY RIÊNG", 29, color=BLUE, bold=True)
stages = [
    (76, "1. TRÍCH XUẤT", "Dữ liệu ứng dụng\n→ Tệp CSV"),
    (447, "2. HUẤN LUYỆN", "Notebook / Colab\nHuấn luyện, đánh giá"),
    (818, "3. KIỂM TRA", "Phiên bản, tương thích\nChất lượng dự báo"),
    (1189, "4. CÔNG BỐ", "CSV / JSON đã duyệt\nWeb đọc kết quả"),
]
for x, title, body in stages:
    rect(x, 1420, 335, 145, stroke="#9bbdb8", fill="white", radius=12)
    text(x+167.5, 1451, title, 25, color=TEAL, bold=True, anchor="middle", max_width=310)
    text(x+167.5, 1495, body, 24, anchor="middle", gap=34, max_width=310)
    if x != stages[-1][0]:
        line(x+340, 1492, x+362, 1492, color=TEAL, arrow=True)
text(76, 1610, "Mỗi lần chạy lưu: mã lần chạy • cấu hình • phiên bản mô hình • kết quả đánh giá.",
     26, max_width=1450)
text(76, 1655, "Các bước xử lý dữ liệu và huấn luyện tách khỏi yêu cầu HTTP thông thường.",
     26, color=MUTED, max_width=1450)

date_label = datetime.now().strftime("%d/%m/%Y")
text(50, 1750, f"Đối chiếu mã nguồn và kiểm tra tại máy phát triển: {date_label}.", 24, color=MUTED)
text(50, 1787, "Hình minh họa cấu trúc và kết quả thực tế; không chứa mật khẩu, khóa bí mật hay chuỗi kết nối.",
     23, color=MUTED, max_width=1510)
svg.append("</svg>")
(OUT / f"{STEM}.svg").write_text("\n".join(svg), encoding="utf-8")
im.save(OUT / f"{STEM}.png", dpi=(300, 300), optimize=True)
preview = im.resize((W, H), Image.Resampling.LANCZOS)
preview.save(OUT / f"{STEM}-preview.png", optimize=True)
print(json.dumps({"figure": str(OUT / f"{STEM}.png"), "pixels": im.size,
                  "verification": observations}, ensure_ascii=False, indent=2))
