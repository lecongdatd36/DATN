"""Generate the repository's logical architecture as SVG, PNG and Mermaid."""
from html import escape
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'architecture'
OUT.mkdir(parents=True, exist_ok=True)
STEM = 'kien-truc-he-thong-com-que'
W, H, S = 2400, 1970, 2
INK, MUTED, BLUE, RED = '#263442', '#5c6b78', '#325774', '#881b2d'
im = Image.new('RGB', (W*S, H*S), 'white')
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">Kiến trúc hệ thống quản lý nhà hàng Cơm Quê</title>',
       '<desc id="desc">Ứng dụng Django nguyên khối theo module, trình duyệt desktop và mobile, PostgreSQL, dịch vụ thanh toán, chatbot, Cloudinary và luồng AI ngoại tuyến.</desc>',
       '<rect width="100%" height="100%" fill="white"/>']


def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'), round(size*S))


def text(x, y, value, size=23, bold=False, color=INK, anchor='middle', gap=None, max_width=None):
    lines = value.split('\n') if isinstance(value,str) else value
    step = gap or size*1.3
    top = y-(len(lines)-1)*step/2
    for i,t in enumerate(lines):
        if max_width:
            assert d.textlength(t,font=font(size,bold)) <= max_width*S, t
        yy = top+i*step
        d.text((x*S,yy*S),t,font=font(size,bold),fill=color,anchor={'middle':'mm','start':'lm'}[anchor])
        svg.append(f'<text x="{x}" y="{yy}" text-anchor="{anchor}" dominant-baseline="central" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(t)}</text>')


def rect(x,y,w,h,fill='white',stroke='#bac6ce',radius=12,width=1.6):
    d.rounded_rectangle((x*S,y*S,(x+w)*S,(y+h)*S),radius=radius*S,fill=fill,outline=stroke,width=round(width*S))
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')


def arrow(points, label=None, label_at=None, two_way=False, color=BLUE):
    d.line([(round(x*S),round(y*S)) for x,y in points],fill=color,width=round(2*S),joint='curve')
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
    def head(tip, before):
        import math
        angle=math.atan2(tip[1]-before[1],tip[0]-before[0])
        pts=[tip,(tip[0]-12*math.cos(angle)+5*math.sin(angle),tip[1]-12*math.sin(angle)-5*math.cos(angle)),
             (tip[0]-12*math.cos(angle)-5*math.sin(angle),tip[1]-12*math.sin(angle)+5*math.cos(angle))]
        d.polygon([(round(x*S),round(y*S)) for x,y in pts],fill=color)
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{color}"/>')
    head(points[-1],points[-2])
    if two_way: head(points[0],points[1])
    if label:
        label_lines=label.split('\n')
        bw=max(d.textlength(t,font=font(19)) for t in label_lines)/S+14
        bh=len(label_lines)*25+6
        rect(label_at[0]-bw/2,label_at[1]-bh/2,bw,bh,fill='white',stroke='white',radius=3,width=0)
        text(*label_at,label,size=19,color=color)


def card(x,y,w,h,title,body='',fill='white',color=BLUE):
    rect(x,y,w,h,fill=fill)
    text(x+w/2,y+29,title,size=24,bold=True,color=color,max_width=w-24)
    if body: text(x+w/2,y+(h+35)/2,body,size=20,gap=28,max_width=w-24)


text(1200,45,'KIẾN TRÚC HỆ THỐNG QUẢN LÝ NHÀ HÀNG CƠM QUÊ',size=35,bold=True)
text(1200,94,'Mô hình 3 tầng · Django MTV · Ứng dụng nguyên khối phân mô-đun',size=25,color=RED)

# Client tier: all three surfaces are browsers, not native mobile applications.
rect(80,150,1670,250,fill='#f5f8fb',stroke='#91a8bb',width=2)
text(120,187,'01  TẦNG TRÌNH BÀY — TRÌNH DUYỆT WEB',size=25,bold=True,color=BLUE,anchor='start')
card(120,220,490,110,'Trang khách — desktop/mobile','Thực đơn · Đặt bàn · Giỏ món / QR')
card(650,220,490,110,'Ứng dụng nội bộ','Quản lý · Phục vụ · Thu ngân · Bếp · Kho')
card(1180,220,530,110,'Điểm chấm công','Camera trình duyệt → ảnh gửi máy chủ (*)')
text(915,366,'HTML/CSS · Bootstrap · JavaScript Fetch / polling · Giao diện VI/EN',size=22,color=MUTED)
arrow([(915,400),(915,530)],'HTTP(S) · HTML / JSON · Cookie phiên', (915,465),two_way=True)

# Django process boundary. Modules below share the deployment and database.
rect(80,530,1670,720,fill='#fffdf9',stroke='#aa7c87',width=2)
text(120,565,'02  TẦNG ỨNG DỤNG — DJANGO / PYTHON',size=25,bold=True,color=RED,anchor='start')
card(120,600,1590,85,'Middleware → URLconf → Views / Templates',
     'Xác thực · Phân quyền · CSRF · Session · i18n · Render HTML / trả JSON',fill='#f8f0f1',color=RED)
rect(120,735,1110,345,fill='#f8fafb',stroke='#c0cbd3')
text(675,760,'DỊCH VỤ NGHIỆP VỤ VÀ THUẬT TOÁN NỘI BỘ',size=22,bold=True,color=BLUE)
modules = [
    ('Nhân sự & chấm công','Tài khoản · Quyền · Lịch ca'),
    ('Bàn & đặt bàn','Khách · Giữ chỗ · Món đặt trước'),
    ('Thực đơn & combo','Món · Danh mục · Giá bán'),
    ('Đơn hàng & bếp','QR · Phục vụ · Hóa đơn'),
    ('Kho nguyên liệu','Định lượng · Nhập xuất · Kiểm kê'),
    ('Báo cáo & gợi ý món','Dự báo số đơn · Luật Apriori'),
]
for i,(title,body) in enumerate(modules):
    card(140+(i%3)*360,790+(i//3)*125,350,105,title,body)
text(675,1053,'(*) Nhận diện khuôn mặt: OpenCV YuNet/SFace, xử lý trên server khi được cài và bật.',size=18,color=MUTED)
arrow([(675,685),(675,735)])
arrow([(675,1080),(675,1120)])
card(120,1120,1110,90,'Django Models / ORM','Giao dịch nguyên tử · Khóa dữ liệu · Ràng buộc / snapshot',fill='#edf3f7')

text(1500,712,'BỘ TÍCH HỢP',size=21,bold=True,color=BLUE)
card(1290,740,420,100,'Thanh toán','Tạo / truy vấn · IPN / callback',fill='#faf4ed')
card(1290,870,420,100,'Chatbot','Bối cảnh · Hội thoại · Giới hạn gọi',fill='#faf4ed')
card(1290,1000,420,100,'Django Storage','Lưu ảnh · Nhận URL ảnh',fill='#faf4ed')
card(1290,1140,420,70,'Cache RAM theo tiến trình',color=BLUE)
text(915,1230,'Static CSS / JS / font: phục vụ qua WhiteNoise trong cấu hình production.',size=19,color=MUTED)

# External dependencies; callbacks are server-to-server, not browser proof of payment.
text(2095,688,'DỊCH VỤ BÊN NGOÀI',size=25,bold=True,color=BLUE)
card(1850,740,490,100,'Cổng thanh toán','VNPAY / ZaloPay (Sandbox)',fill='#faf4ed')
card(1850,870,490,100,'AI hội thoại','Groq hoặc Gemini — theo cấu hình',fill='#faf4ed')
card(1850,1000,490,100,'Cloudinary','Ảnh món / ảnh tải lên',fill='#faf4ed')
for yy,caption in [(790,'HTTPS'),(920,'HTTPS'),(1050,'SDK / HTTPS')]:
    arrow([(1710,yy),(1850,yy)],caption,(1780,yy-22),two_way=True)
text(2095,1160,'Cổng thanh toán trả kết quả để server xác minh.\nChatbot chỉ gọi nhà cung cấp đang được chọn.',size=20,color=MUTED,gap=29)

# Persistence tier: business records and shared cache in PostgreSQL; file artifacts separate.
text(80,1305,'03  TẦNG DỮ LIỆU VÀ TỆP',size=25,bold=True,color=BLUE,anchor='start')
card(120,1360,690,190,'PostgreSQL',
     'Dữ liệu nghiệp vụ · Tài khoản · Nhật ký\nSession cached_db\nDatabase cache: hội thoại / giới hạn tần suất',fill='#edf3f7')
card(880,1360,830,190,'Kho tệp / artifact trên máy chủ',
     'Luật Apriori (JSON) · Dự báo công bố (CSV / JSON)\nMô hình nhận diện khuôn mặt (*)\nMỗi môi trường cần đúng tệp và cấu hình tương ứng',fill='#edf3f7')
arrow([(465,1210),(465,1360)],'SQL qua ORM',(555,1282),two_way=True)
arrow([(1450,1360),(1450,1250)],'Đọc luật / kết quả',(1552,1305))

# Offline training/publication is not part of an HTTP request and is not a microservice.
rect(80,1650,1670,230,fill='#f9f7ef',stroke='#b7a77b',width=2)
text(120,1683,'LUỒNG AI NGOẠI TUYẾN — SCRIPT / COLAB / LỊCH CẬP NHẬT',size=23,bold=True,color='#75603c',anchor='start')
card(120,1730,420,105,'Chuẩn bị dữ liệu','CSV xuất từ ứng dụng\nhoặc dữ liệu mô phỏng',color='#75603c')
card(650,1730,500,105,'Huấn luyện / đánh giá','Apriori · Random Forest\nMôi trường AI riêng',color='#75603c')
card(1260,1730,450,105,'Xuất và công bố','Luật món / kết quả dự báo\nJSON / CSV',color='#75603c')
arrow([(540,1782),(650,1782)],color='#75603c')
arrow([(1150,1782),(1260,1782)],color='#75603c')
arrow([(1485,1730),(1485,1550)],'Công bố tệp',(1575,1600),color='#75603c')

text(1200,1920,'Web đọc luật và kết quả đã công bố; huấn luyện Random Forest không chạy trong request.',size=21,color=MUTED)
text(1200,1952,'Kiến trúc logic theo mã nguồn · Triển khai tham chiếu: Render HTTPS → Gunicorn → Django; PostgreSQL theo cấu hình.',size=19,color=MUTED)
svg.append('</svg>')
(OUT/f'{STEM}.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/f'{STEM}.png',dpi=(300,300))
im.resize((W,H),Image.Resampling.LANCZOS).save(OUT/f'{STEM}-preview.png')

mermaid = '''flowchart TB
  subgraph Client["01. TẦNG TRÌNH BÀY — TRÌNH DUYỆT WEB"]
    C["Trang khách desktop/mobile · QR · Đặt bàn"]
    Staff["Ứng dụng quản lý · Phục vụ · Thu ngân · Bếp · Kho"]
    Kiosk["Điểm chấm công · Camera trình duyệt"]
  end
  subgraph App["02. DJANGO / PYTHON — ỨNG DỤNG NGUYÊN KHỐI PHÂN MODULE"]
    Entry["Middleware / URLconf / Views / Templates\nAuth · RBAC · CSRF · Session · i18n"]
    Services["Dịch vụ nghiệp vụ\nTài khoản / Nhân sự / Workforce\nKhách hàng / Bàn / Đặt bàn / Đặt món trước\nThực đơn / Combo / Đơn hàng / Bếp / Kho / Báo cáo"]
    InternalAI["AI nội bộ: Apriori / kết quả dự báo\nFace: OpenCV YuNet/SFace khi cài và bật"]
    ORM["Django Models / ORM\nGiao dịch / khóa / ràng buộc dữ liệu"]
    RAM["LocMemCache theo process"]
    Pay["Tích hợp thanh toán"]
    Chat["Chatbot / giới hạn gọi"]
    Storage["Django Storage"]
    Static["WhiteNoise: CSS / JS / font"]
    Entry --> Services
    Services --> ORM
    Services --> InternalAI
    Services --> Pay
    Services --> Chat
    Services --> Storage
    Entry --> RAM
    Entry --> Static
  end
  C <-->|HTTP / HTTPS · HTML / JSON| Entry
  Staff <-->|Fetch / polling| Entry
  Kiosk -->|Ảnh camera qua HTTPS| Entry
  ORM <-->|SQL| PG[("PostgreSQL\nNghiệp vụ / nhật ký / phiên\nDatabase cache hội thoại và rate limit")]
  Pay <-->|HTTPS · callback / IPN| Gateway["VNPAY / ZaloPay Sandbox"]
  Chat <-->|HTTPS · chọn một provider| LLM["Groq hoặc Gemini"]
  Storage <-->|SDK / HTTPS| Cloud["Cloudinary"]
  Files["Tệp server: luật JSON / dự báo CSV-JSON / model face"] -->|Đọc tệp| InternalAI
  subgraph Offline["LUỒNG AI NGOẠI TUYẾN — NGOÀI REQUEST"]
    CSV["CSV ứng dụng hoặc mô phỏng"] --> Train["Apriori / Random Forest\nMôi trường AI riêng"]
    Train --> Publish["Xuất / công bố luật và dự báo"]
  end
  Publish --> Files
'''
(OUT/f'{STEM}.mmd').write_text(mermaid,encoding='utf-8')
print(f'Created architecture SVG, PNG {W*S}x{H*S}, preview and Mermaid in {OUT}')
