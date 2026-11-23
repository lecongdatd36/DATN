"""UML use cases for the implemented customer and membership subsystem."""
from pathlib import Path
from html import escape
import math
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'use-case'
OUT.mkdir(parents=True,exist_ok=True)
STEM='use-case-khach-hang-hang-thanh-vien'
W,H,S=2400,1630,2
INK,GRAY,RED='#25303c','#66717c','#881b2d'
im=Image.new('RGB',(W*S,H*S),'white'); d=ImageDraw.Draw(im)
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title">',
     '<title id="title">Use Case phân hệ khách hàng và hạng thành viên</title>','<rect width="100%" height="100%" fill="white"/>']


def font(size,bold=False,italic=False):
    name='arialbi.ttf' if bold and italic else 'arialbd.ttf' if bold else 'ariali.ttf' if italic else 'arial.ttf'
    return ImageFont.truetype('C:/Windows/Fonts/'+name,round(size*S))


def text(x,y,value,size=25,bold=False,color=INK,italic=False):
    rows=value.split('\n'); gap=size*1.3
    for i,row in enumerate(rows):
        yy=y+(i-(len(rows)-1)/2)*gap
        d.text((x*S,yy*S),row,font=font(size,bold,italic),fill=color,anchor='mm')
        svg.append(f'<text x="{x}" y="{yy}" text-anchor="middle" dominant-baseline="central" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" font-style="{"italic" if italic else "normal"}" fill="{color}">{escape(row)}</text>')


def line(points,color=INK,dashed=False):
    pts=[(x*S,y*S) for x,y in points]
    if not dashed: d.line(pts,fill=color,width=4,joint='curve')
    else:
        for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
            length=math.hypot(x2-x1,y2-y1)
            for k in range(0,round(length),20):
                a=k/length;b=min(k+11,length)/length
                d.line([(x1+(x2-x1)*a,y1+(y2-y1)*a),(x1+(x2-x1)*b,y1+(y2-y1)*b)],fill=color,width=4)
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="2"'+(' stroke-dasharray="6 5"' if dashed else '')+'/>')


def ellipse(x,y,rx,ry):
    d.ellipse(((x-rx)*S,(y-ry)*S,(x+rx)*S,(y+ry)*S),fill='white',outline=INK,width=4)
    svg.append(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="white" stroke="{INK}" stroke-width="2"/>')


def actor(key,x,y,label,abstract=False):
    svg.append(f'<g id="actor-{key}">')
    ellipse(x,y-50,14,14)
    line([(x,y-36),(x,y+20)])
    line([(x-31,y-14),(x+31,y-14)])
    line([(x-28,y+58),(x,y+20),(x+28,y+58)])
    text(x,y+92,label,size=24,bold=not abstract,italic=abstract)
    svg.append('</g>')


def generalization(points):
    tip=points[-1];before=points[-2]
    angle=math.atan2(tip[1]-before[1],tip[0]-before[0])
    base=(tip[0]-18*math.cos(angle),tip[1]-18*math.sin(angle))
    line(points[:-1]+[base],color=GRAY)
    tri=[tip,(base[0]+9*math.sin(angle),base[1]-9*math.cos(angle)),(base[0]-9*math.sin(angle),base[1]+9*math.cos(angle))]
    d.polygon([(x*S,y*S) for x,y in tri],fill='white',outline=GRAY,width=4)
    svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in tri)}" fill="white" stroke="{GRAY}" stroke-width="2"/>')


def include(points,label_at):
    line(points,color=RED,dashed=True)
    x,y=points[-1];px,py=points[-2];angle=math.atan2(y-py,x-px)
    line([(x-14*math.cos(angle)+6*math.sin(angle),y-14*math.sin(angle)-6*math.cos(angle)),(x,y),
          (x-14*math.cos(angle)-6*math.sin(angle),y-14*math.sin(angle)+6*math.cos(angle))],color=RED)
    text(*label_at,'«include»',size=21,color=RED)


text(1200,39,'USE CASE PHÂN HỆ KHÁCH HÀNG VÀ HẠNG THÀNH VIÊN',size=32,bold=True)
text(1200,79,'Hệ thống quản lý nhà hàng Cơm Quê',size=24,color=GRAY)
d.rectangle((350*S,350*S,2050*S,1490*S),outline=RED,width=4)
svg.append(f'<rect x="350" y="350" width="1700" height="1140" fill="none" stroke="{RED}" stroke-width="2"/>')
text(1200,385,'QUẢN LÝ KHÁCH HÀNG VÀ HẠNG THÀNH VIÊN',size=25,bold=True,color=RED)

CASES=[
 ('KH01','Xem danh sách và\ntìm kiếm khách hàng',750,500),
 ('KH02','Xem chi tiết hồ sơ\nvà hạng khách hàng',750,650),
 ('KH03','Thêm hồ sơ khách hàng',750,800),
 ('KH04','Cập nhật thông tin\nkhách hàng',750,950),
 ('KH05','Xem lịch sử tiêu dùng',750,1100),
 ('KH06','Xóa hồ sơ khách hàng\nkhi đủ điều kiện',1700,500),
 ('KH07','Tra cứu nhật ký\nthao tác khách hàng',1700,650),
 ('TV01','Xem danh sách\nhạng thành viên',1700,800),
 ('TV02','Thêm hạng thành viên',1700,950),
 ('TV03','Sửa quy tắc / bật, tắt\nhạng thành viên',1700,1100),
 ('TV04','Tính lại hạng khách hàng',1200,1370),
]

# The shared abstract actor supplies the five customer-profile use cases.
line([(1240,161),(2010,161),(2010,420),(1200,420)])
for _,_,_,cy in CASES[:5]: line([(1200,420),(1200,cy),(1000,cy)])
for _,_,_,cy in CASES[5:10]: line([(2220,786),(2110,786),(2110,cy),(1950,cy)])

# Specialization arrows point to the common actor, outside the system boundary.
generalization([(140,530),(140,310),(950,310),(950,161),(1160,161)])
generalization([(140,880),(280,880),(280,330),(910,330),(910,161),(1160,161)])
generalization([(2260,730),(2260,310),(1490,310),(1490,161),(1240,161)])

include([(1450,950),(1280,950),(1280,1270),(1100,1270),(1100,1320)],(1360,924))
include([(1450,1100),(1360,1100),(1360,1270),(1300,1270),(1300,1320)],(1380,1050))

for cid,label,x,y in CASES:
    ellipse(x,y,250,55)
    text(x,y-33,cid,size=17,bold=True,color=GRAY)
    for row in label.split('\n'):
        assert d.textlength(row,font=font(25))<440*S,(cid,row)
    text(x,y+10,label,size=25)

actor('staff',1200,175,'Nhân viên có quyền\nquản lý hồ sơ khách hàng',abstract=True)
actor('waiter',140,600,'Nhân viên\nphục vụ')
actor('cashier',140,950,'Thu ngân')
actor('manager',2260,800,'Quản lý')
text(1200,1532,'Tên tác nhân in nghiêng: vai trò chung. Tam giác rỗng hướng về vai trò cha; nét đứt có mũi tên hở là «include».',size=21,color=GRAY)
text(1200,1570,'Đăng nhập và quyền phù hợp là tiền điều kiện. Tích lũy chi tiêu / giảm theo hạng được thực hiện trong luồng thanh toán.',size=20,color=GRAY)
svg.append('</svg>')
(OUT/f'{STEM}.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/f'{STEM}.png',dpi=(300,300))
im.resize((W,H),Image.Resampling.LANCZOS).save(OUT/f'{STEM}-preview.png')

puml=['@startuml','left to right direction','skinparam monochrome true','skinparam shadowing false',
      'title Use Case khách hàng và hạng thành viên',
      'actor "Nhân viên có quyền\\nquản lý hồ sơ khách hàng" as Staff <<abstract>>',
      'actor "Nhân viên phục vụ" as Waiter','actor "Thu ngân" as Cashier','actor "Quản lý" as Manager',
      'Waiter --|> Staff','Cashier --|> Staff','Manager --|> Staff',
      'rectangle "Quản lý khách hàng và hạng thành viên" {']
for cid,label,_,_ in CASES:
    puml.append(' usecase "'+cid+'\\n'+label.replace('\n','\\n')+'" as '+cid)
puml.append('}')
for cid,*_ in CASES[:5]: puml.append('Staff -- '+cid)
for cid,*_ in CASES[5:10]: puml.append('Manager -- '+cid)
puml += ['TV02 ..> TV04 : <<include>>','TV03 ..> TV04 : <<include>>',
         'note bottom of KH06 : Chỉ xóa khi không có liên kết nghiệp vụ bảo vệ.',
         'legend bottom','Đăng nhập và quyền tương ứng là tiền điều kiện.',
         'Tích lũy chi tiêu, xác định ưu đãi theo hạng được gọi từ luồng thanh toán.',
         'endlegend','@enduml']
(OUT/f'{STEM}.puml').write_text('\n'.join(puml)+'\n',encoding='utf-8')
print('Created customer/membership UML: PNG 4800x3260, SVG and PlantUML.')
