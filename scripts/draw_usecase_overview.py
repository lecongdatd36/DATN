"""Draw a report-ready overview locally as SVG, PNG and editable PlantUML."""
from html import escape
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'use-case'
OUT.mkdir(parents=True, exist_ok=True)
STEM = 'use-case-tong-quat-cap-nhat'
W, H, SCALE = 2000, 1580, 2
INK, MUTED, ACCENT = '#25303c', '#626b75', '#881b2d'
image = Image.new('RGB', (W * SCALE, H * SCALE), 'white')
draw = ImageDraw.Draw(image)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title description">',
       '<title id="title">Use case tổng quát — Hệ thống quản lý nhà hàng Cơm Quê</title>',
       '<desc id="description">Sáu tác nhân, mười sáu nhóm ca sử dụng; thanh toán VNPAY và ZaloPay, chấm công, kho, báo cáo và AI.</desc>',
       '<rect width="100%" height="100%" fill="white"/>']


def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/' + ('arialbd.ttf' if bold else 'arial.ttf'), round(size * SCALE))


def text(x, y, lines, size=25, bold=False, color=INK, anchor='middle', spacing=None):
    lines = lines.split('\n') if isinstance(lines, str) else lines
    gap = spacing or size * 1.3
    start = y - (len(lines) - 1) * gap / 2
    for i, line in enumerate(lines):
        yy = start + gap * i
        draw.text((x * SCALE, yy * SCALE), line, font=font(size, bold), fill=color,
                  anchor={'middle': 'mm', 'start': 'lm', 'end': 'rm'}[anchor])
        svg.append(f'<text x="{x}" y="{yy}" text-anchor="{anchor}" dominant-baseline="central" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(line)}</text>')


def line(points, color=INK, width=1.8):
    draw.line([(round(x * SCALE), round(y * SCALE)) for x, y in points], fill=color, width=round(width * SCALE), joint='curve')
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"/>')


def curve(start, c1, c2, end, color=INK):
    points = []
    for i in range(61):
        t = i / 60
        points.append(tuple((1-t)**3*start[j] + 3*(1-t)**2*t*c1[j] + 3*(1-t)*t*t*c2[j] + t**3*end[j] for j in (0,1)))
    draw.line([(round(x*SCALE), round(y*SCALE)) for x,y in points], fill=color, width=round(1.8*SCALE), joint='curve')
    svg.append(f'<path d="M{start[0]} {start[1]} C{c1[0]} {c1[1]}, {c2[0]} {c2[1]}, {end[0]} {end[1]}" fill="none" stroke="{color}" stroke-width="1.8"/>')


def ellipse(cx, cy, rx, ry, fill='white', outline=INK, width=1.8):
    draw.ellipse(tuple(round(v*SCALE) for v in (cx-rx, cy-ry, cx+rx, cy+ry)), fill=fill, outline=outline, width=round(width*SCALE))
    svg.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{outline}" stroke-width="{width}"/>')


def actor(key, name, x, y, subtitle=()):
    svg.append(f'<g id="actor-{key}">')
    ellipse(x, y-50, 14, 14, width=2)
    line([(x,y-36),(x,y+20)], width=2)
    line([(x-31,y-14),(x+31,y-14)], width=2)
    line([(x-28,y+58),(x,y+20),(x+28,y+58)], width=2)
    text(x,y+92,name,size=24,bold=True)
    if subtitle:
        text(x,y+150,subtitle,size=18,color=MUTED,spacing=25)
    svg.append('</g>')


CASES = [
    ('UC01', 'Xem thực đơn và\nnhận gợi ý món', 640, 220),
    ('UC02', 'Đặt bàn, đặt món trước\nvà tra cứu lịch', 640, 320),
    ('UC03', 'Gọi món QR và\nyêu cầu phục vụ', 640, 420),
    ('UC04', 'Trao đổi với chatbot', 640, 520),
    ('UC05', 'Tiếp nhận khách\nvà điều phối bàn', 640, 700),
    ('UC06', 'Quản lý gọi món\nvà duyệt yêu cầu QR', 640, 810),
    ('UC07', 'Chế biến và xác nhận\nphục vụ món', 640, 920),
    ('UC08', 'Lập hóa đơn\nvà thanh toán', 640, 1030),
    ('UC09', 'Quản lý kho, công thức\nvà cảnh báo tồn', 640, 1140),
    ('UC10', 'Quản lý thực đơn\nvà combo', 1360, 700),
    ('UC11', 'Quản lý khách hàng,\nhạng và khuyến mãi', 1360, 810),
    ('UC12', 'Quản lý nhân sự\nvà tài khoản', 1360, 920),
    ('UC13', 'Phân ca, duyệt công\nvà quản lý khuôn mặt', 1360, 1030),
    ('UC14', 'Xem báo cáo và\ndự báo số đơn', 1360, 1140),
    ('UC15', 'Quản trị quyền\nvà bảo vệ tài khoản', 1360, 1300),
    ('UC16', 'Xem lịch làm việc\nvà chấm công', 640, 1300),
]
by_id = {c[0]: c for c in CASES}
ACTORS = {
    'customer': ('Khách hàng', 130, 345),
    'staff': ('Nhân viên\nnội bộ', 130, 955),
    'manager': ('Quản lý', 1870, 955),
    'admin': ('Quản trị\nhệ thống', 1870, 1305),
    'payment': ('Cổng thanh toán', 1870, 260),
    'ai': ('Dịch vụ AI\nhội thoại', 1870, 520),
}
ASSOCIATIONS = {
    'customer': ['UC01','UC02','UC03','UC04'],
    'staff': ['UC05','UC06','UC07','UC08','UC09','UC16'],
    'manager': ['UC10','UC11','UC12','UC13','UC14'],
    'admin': ['UC15'],
    'payment': ['UC02','UC08'],
    'ai': ['UC04'],
}

# Heading and system boundary. Associations are drawn before nodes and labels.
text(1000,42,'SƠ ĐỒ USE CASE TỔNG QUÁT',size=34,bold=True)
text(1000,88,'HỆ THỐNG QUẢN LÝ NHÀ HÀNG CƠM QUÊ',size=26,color=ACCENT)
draw.rectangle((280*SCALE,130*SCALE,1720*SCALE,1440*SCALE),outline=ACCENT,width=2*SCALE)
svg.append('<rect x="280" y="130" width="1440" height="1310" fill="none" stroke="#881b2d" stroke-width="2"/>')
text(1000,158,'Cơm Quê',size=24,bold=True,color=ACCENT)
text(390,625,'VẬN HÀNH',size=19,bold=True,color=MUTED,anchor='start')
text(1110,625,'QUẢN LÝ',size=19,bold=True,color=MUTED,anchor='start')

for key, ids in ASSOCIATIONS.items():
    _, ax, ay = ACTORS[key]
    if key == 'payment':
        line([(1830,246),(1770,246),(1770,320),(890,320)])
        line([(1830,246),(1790,246),(1790,602),(1000,602),(1000,1030),(890,1030)])
        continue
    if key == 'ai':
        line([(1830,506),(1770,506),(1770,520),(890,520)])
        continue
    for cid in ids:
        _, label, cx, cy = by_id[cid]
        if ax < 280:
            curve((170,ay-14),(270,ay-14),(300,cy),(390,cy))
        else:
            curve((1830,ay-14),(1760,ay-14),(1700,cy),(1610,cy))

# Admin specializes manager. The route stays outside the system boundary.
line([(1905,1291),(1970,1291),(1970,941),(1921,941)],color=MUTED)
triangle = [(1905,941),(1921,932),(1921,950)]
draw.polygon([(x*SCALE,y*SCALE) for x,y in triangle],fill='white',outline=MUTED,width=2*SCALE)
svg.append('<polygon points="1905,941 1921,932 1921,950" fill="white" stroke="#626b75" stroke-width="1.8"/>')

for cid, label, cx, cy in CASES:
    ellipse(cx,cy,250,45)
    text(cx,cy-30,cid,size=15,bold=True,color=MUTED)
    # Keep the complete use-case label inside the ellipse, without truncation.
    for row in label.split('\n'):
        assert draw.textlength(row,font=font(25)) < 440*SCALE, (cid,row)
    text(cx,cy+9,label,size=25,spacing=29)

for key,(label,x,y) in ACTORS.items():
    subtitles = {
        'staff': ['Phục vụ · Thu ngân','Bếp · Kho'],
        'payment': ['VNPAY / ZaloPay'],
    }.get(key, [])
    actor(key,label,x,y,subtitles)

text(1000,1488,'Nét liền: liên kết tham gia. Tam giác rỗng: kế thừa vai trò.',size=20,color=MUTED)
text(1000,1520,'Nhân viên nội bộ được gom ở mức tổng quát; từng nghiệp vụ yêu cầu đúng quyền. Đăng nhập là tiền điều kiện nội bộ.',size=19,color=MUTED)
text(1000,1550,'Quản lý tham gia nghiệp vụ vận hành theo phân quyền; các liên kết quản lý ở đây nhấn mạnh mục tiêu quản trị.',size=19,color=MUTED)
svg.append('</svg>')
(OUT / f'{STEM}.svg').write_text('\n'.join(svg),encoding='utf-8')
image.save(OUT / f'{STEM}.png',dpi=(300,300))
image.resize((W,H),Image.Resampling.LANCZOS).save(OUT / f'{STEM}-preview.png')

puml = ['@startuml','left to right direction','skinparam monochrome true','skinparam shadowing false',
        'skinparam defaultFontName Arial','title Use case tổng quát — Cơm Quê']
for key,(label,_,_) in ACTORS.items():
    if key == 'staff': label += '\n(Phục vụ / Thu ngân / Bếp / Kho)'
    if key == 'payment': label += '\n(VNPAY / ZaloPay)'
    puml.append('actor ' + json.dumps(label,ensure_ascii=False) + ' as A_' + key)
puml.append('rectangle "Hệ thống quản lý nhà hàng Cơm Quê" {')
for cid,label,_,_ in CASES:
    puml.append('  usecase ' + json.dumps(cid+'\n'+label,ensure_ascii=False) + ' as ' + cid)
puml.append('}')
for key,ids in ASSOCIATIONS.items():
    for cid in ids: puml.append(f'A_{key} -- {cid}')
puml += ['A_admin --|> A_manager','legend bottom',
         'Các liên kết biểu diễn nhóm mục tiêu và vai trò tham gia chính, không thay thế ma trận phân quyền.',
         'Nhân viên nội bộ gồm phục vụ, thu ngân, bếp và kho; từng người chỉ thực hiện chức năng được cấp quyền.',
         'Đăng nhập là tiền điều kiện nội bộ. Quản lý có thể tham gia nghiệp vụ vận hành theo phân quyền.',
         'endlegend','@enduml']
(OUT / f'{STEM}.puml').write_text('\n'.join(puml)+'\n',encoding='utf-8')
print(f'Created {STEM}: SVG, PNG 4000x3160, preview and PlantUML; {len(CASES)} use cases / {len(ACTORS)} actors.')
