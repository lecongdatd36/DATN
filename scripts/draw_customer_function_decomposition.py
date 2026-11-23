"""Render the implemented customer/membership functional decomposition locally."""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'phan-ra-chuc-nang'
OUT.mkdir(parents=True, exist_ok=True)
STEM = 'phan-ra-khach-hang-hang-thanh-vien'
W, H, S = 2160, 1220, 2
INK, MUTED, RED = '#25303c', '#5d6874', '#881b2d'
im = Image.new('RGB',(W*S,H*S),'white')
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">Phân rã chức năng khách hàng và hạng thành viên</title>',
       '<desc id="desc">Cây phân rã gồm một chức năng tổng, bốn nhóm chức năng và mười sáu chức năng chi tiết, theo ứng dụng Cơm Quê.</desc>',
       '<rect width="100%" height="100%" fill="white"/>']


def font(size,bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),round(size*S))


def text(x,y,value,size=26,bold=False,color=INK,max_width=None):
    rows=value.split('\n')
    gap=size*1.35
    for i,row in enumerate(rows):
        if max_width: assert d.textlength(row,font=font(size,bold))<=max_width*S,row
        yy=y+(i-(len(rows)-1)/2)*gap
        d.text((x*S,yy*S),row,font=font(size,bold),fill=color,anchor='mm')
        svg.append(f'<text x="{x}" y="{yy}" dominant-baseline="central" text-anchor="middle" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(row)}</text>')


def connector(points):
    d.line([(x*S,y*S) for x,y in points],fill=MUTED,width=4,joint='curve')
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{MUTED}" stroke-width="2"/>')


def box(key,x,y,w,h,label,root=False,group=False):
    fill=RED if root else '#faf0f2' if group else 'white'
    stroke=RED if root or group else '#a6b1bd'
    d.rounded_rectangle((x*S,y*S,(x+w)*S,(y+h)*S),radius=10*S,fill=fill,outline=stroke,width=3)
    svg.append(f'<g id="node-{key}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    text(x+w/2,y+h/2,label,size=30 if root else 27 if group else 25,bold=root or group,color='white' if root else RED if group else INK,max_width=w-24)
    svg.append('</g>')


GROUPS = [
    ('1. Quản lý hồ sơ\nkhách hàng',[
        '1.1 Thêm hồ sơ khách hàng',
        '1.2 Cập nhật thông tin\nkhách hàng',
        '1.3 Tìm kiếm khách hàng\ntheo mã, tên, số điện thoại',
        '1.4 Xóa hồ sơ khách hàng\nkhi đủ điều kiện',
    ]),
    ('2. Tra cứu và theo dõi\nkhách hàng',[
        '2.1 Xem chi tiết hồ sơ',
        '2.2 Xem tổng chi tiêu\nvà hạng hiện tại',
        '2.3 Xem lịch sử tiêu dùng\nqua hóa đơn đã thanh toán',
        '2.4 Tra cứu nhật ký\nthao tác khách hàng',
    ]),
    ('3. Quản lý\nhạng thành viên',[
        '3.1 Xem danh sách hạng',
        '3.2 Thêm hạng thành viên',
        '3.3 Sửa tên, ngưỡng chi tiêu\nvà tỷ lệ giảm giá',
        '3.4 Bật / tắt áp dụng hạng',
    ]),
    ('4. Xếp hạng và\náp dụng ưu đãi',[
        '4.1 Cộng chi tiêu khi\nhóa đơn thanh toán đủ',
        '4.2 Xác định hạng\ntheo tổng chi tiêu',
        '4.3 Tính lại hạng khi\nquy tắc hạng thay đổi',
        '4.4 Tính giảm giá\ntheo hạng khi thanh toán',
    ]),
]

text(W/2,49,'SƠ ĐỒ PHÂN RÃ CHỨC NĂNG',size=34,bold=True)
text(W/2,94,'HỆ THỐNG QUẢN LÝ NHÀ HÀNG CƠM QUÊ',size=25,color=MUTED)
centers=[285,815,1345,1875]
connector([(1080,240),(1080,310)])
connector([(centers[0],310),(centers[-1],310)])
for cx in centers: connector([(cx,310),(cx,360)])

for i,(heading,leaves) in enumerate(GROUPS):
    x=50+i*530
    cx=x+235
    spine=x+15
    connector([(cx,460),(cx,495),(spine,495),(spine,1012)])
    for j in range(4):
        yy=530+j*145
        connector([(spine,yy+47),(x+40,yy+47)])

box('0',650,140,860,100,'0. Quản lý khách hàng\nvà hạng thành viên',root=True)
for i,(heading,leaves) in enumerate(GROUPS):
    x=50+i*530
    box(str(i+1),x,360,470,100,heading,group=True)
    for j,label in enumerate(leaves): box(f'{i+1}-{j+1}',x+40,530+j*145,430,95,label)

text(W/2,1127,'Nhánh 1–3: chức năng thao tác / tra cứu theo phân quyền. Nhánh 4: xử lý tự động của hệ thống.',size=22,color=MUTED)
text(W/2,1167,'Các đường nối thể hiện phân cấp chức năng, không biểu diễn trình tự xử lý hoặc quan hệ include / extend.',size=21,color=MUTED)
svg.append('</svg>')
(OUT/f'{STEM}.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/f'{STEM}.png',dpi=(300,300))
im.resize((W,H),Image.Resampling.LANCZOS).save(OUT/f'{STEM}-preview.png')

mermaid=['flowchart TB','  F0["0. Quản lý khách hàng và hạng thành viên"]']
for i,(heading,leaves) in enumerate(GROUPS,1):
    label=heading.replace('\n',' ')
    mermaid += [f'  F{i}["{label}"]',f'  F0 --- F{i}']
    for j,label in enumerate(leaves,1):
        label=label.replace('\n',' ')
        mermaid += [f'  F{i}{j}["{label}"]',f'  F{i} --- F{i}{j}']
(OUT/f'{STEM}.mmd').write_text('\n'.join(mermaid)+'\n',encoding='utf-8')
print('Created SVG, PNG 4320x2440, preview and Mermaid: '+str(OUT/STEM))
