# Báo cáo GIAI ĐOẠN 1

Ngày thực hiện: 17/09/2026. Thư mục: `D:\DOANTOTNGHIEP`.

## ĐÃ LÀM

- Xác nhận Python 3.12.8, Git 2.48.1 và PostgreSQL 17.3 trên máy.
- Tạo `.venv`, kích hoạt qua CMD và cài Django 5.2.17 cùng dependency ban đầu; cố định phiên bản trong `requirements.txt`.
- Tạo mới Django project `QLNH`. Thư mục ban đầu chỉ có `.git`; không tái sử dụng source code cũ.
- Tạo `.env` với SECRET_KEY ngẫu nhiên và thông tin PostgreSQL được cung cấp; `.env.example` không có secret thực tế.
- Cấu hình PostgreSQL, tiếng Việt, `Asia/Ho_Chi_Minh`, i18n, timezone, templates, static và media.
- PostgreSQL đang hoạt động; `QLNH_DB` đã tồn tại và không có bảng ứng dụng. Kết nối Django thành công. Không tạo lại, xóa hoặc sửa database nào.
- Tạo trang nền tiếng Việt, base template có các block mở rộng, Django Messages dùng cookie và Bootstrap 5.3.8 lưu cục bộ kèm giấy phép MIT.
- Giữ repository Git sẵn có, thêm `.gitignore`, chưa tạo commit.
- Viết README hướng dẫn thiết lập và chạy trên Windows.

## CẤU TRÚC HIỆN TẠI

```text
D:\DOANTOTNGHIEP/
├── .git/
├── .venv/
├── .env
├── .env.example
├── .gitignore
├── manage.py
├── requirements.txt
├── README.md
├── QLNH/
├── apps/
├── core/
├── templates/
│   └── includes/
├── static/
│   ├── css/
│   ├── js/
│   ├── images/
│   └── vendor/bootstrap/
├── media/
│   ├── employees/
│   ├── dishes/
│   └── restaurant/
├── fixtures/
├── scripts/
├── notebooks/
└── docs/
    ├── stage-1-report.md
    ├── erd/
    ├── usecase/
    ├── activity/
    └── sequence/
```

`apps/` và `core/` chỉ là package nền. Chưa có app nghiệp vụ; thư mục dự phòng được giữ trong Git bằng `.gitkeep`. `.venv/` và `media/` chỉ tồn tại cục bộ, được Git bỏ qua.

## FILE ĐÃ TẠO

- Gốc: `manage.py`, `requirements.txt`, `.env`, `.env.example`, `.gitignore`, `README.md`.
- Project: `QLNH/__init__.py`, `QLNH/settings.py`, `QLNH/urls.py`, `QLNH/asgi.py`, `QLNH/wsgi.py`.
- Package nền: `apps/__init__.py`, `core/__init__.py`.
- Template: `templates/base.html`, `templates/home.html`, `templates/includes/messages.html`.
- Giao diện: `static/css/base.css`, `static/js/base.js`.
- Bootstrap: `static/vendor/bootstrap/css/bootstrap.min.css`, `static/vendor/bootstrap/js/bootstrap.bundle.min.js`, `static/vendor/bootstrap/LICENSE`.
- Tài liệu: `docs/stage-1-report.md`.
- `.gitkeep` tại `static/images`, `fixtures`, `scripts`, `notebooks`, `docs/erd`, `docs/usecase`, `docs/activity`, `docs/sequence`.
- Các tệp môi trường Python nằm trong `.venv/`, không đưa vào Git.

## FILE ĐÃ SỬA

- `QLNH/settings.py` và `QLNH/urls.py` được cấu hình lại sau khi Django sinh scaffold mới.
- `README.md` được cập nhật theo kết quả kiểm tra thực tế.
- Không sửa source code cũ.

## MIGRATION

- Chưa tạo hoặc chạy migration; database vẫn không có bảng ứng dụng, không có `auth_user` hay `django_migrations`.
- Giai đoạn 1 chỉ bật `django.contrib.messages` và `django.contrib.staticfiles`; chưa bật Accounts, auth, admin, contenttypes, sessions.
- Việc hoãn migration phù hợp yêu cầu “chạy migration ban đầu nếu phù hợp”: GIAI ĐOẠN 2 phải tạo Custom User và cấu hình `AUTH_USER_MODEL` trước migration đầu tiên. Xem [tài liệu Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#using-a-custom-user-model-when-starting-a-project).

## TEST

| Kiểm tra đã thực hiện | Kết quả |
| --- | --- |
| `python manage.py check --database default` | Không phát hiện vấn đề |
| `python manage.py test --verbosity 2` | Lệnh chạy thành công; 0 test; không tạo test database |
| `python -m pip check` | Không có dependency bị thiếu hoặc xung đột |
| Kết nối bằng Django database backend | Đúng `QLNH_DB`, PostgreSQL 17.3, 0 bảng ứng dụng |
| Locale và timezone | `vi`, `Asia/Ho_Chi_Minh`; đọc được dữ liệu múi giờ |
| Render trang `/` bằng Django client | HTTP 200, HTML tiếng Việt UTF-8, 0 truy vấn database |
| HTTP thực tế qua `runserver` | `/` trả 200 |
| Tải CSS/JS thực tế | Cả 4 tài nguyên cục bộ trả 200 |
| Phục vụ media khi DEBUG=True | Tệp kiểm tra tạm trả 200; đã xóa tệp sau kiểm tra |
| `/admin/` | Trả 404 đúng phạm vi: chưa triển khai Accounts/Admin |
| Tệp Bootstrap tải về | SHA-384 CSS/JS khớp thông tin nhà phát hành |
| Quy tắc Git ignore | `.env`, `.venv/`, `media/` bị bỏ qua; `.env.example` được giữ |
| Kiểm tra secret trong các tệp Git có thể theo dõi | Không chứa DB_PASSWORD hoặc SECRET_KEY thực tế |
| Review mã nguồn độc lập | Không phát hiện lỗi chặn hoặc triển khai vượt GIAI ĐOẠN 1 |

Chưa có kiểm thử nghiệp vụ. Chưa kiểm tra trực quan bằng trình duyệt do công cụ trình duyệt không khởi động được; kiểm tra HTTP không thay thế kiểm tra bố cục trên màn hình thực tế.

## KẾT QUẢ

- Hoàn thành nền tảng GIAI ĐOẠN 1; Django đã kết nối được PostgreSQL và chạy trang nền.
- Đã xử lý việc PowerShell chặn `Activate.ps1` bằng CMD hoặc gọi trực tiếp Python trong `.venv`, không thay đổi execution policy của máy.
- Đã xử lý biến môi trường `DEBUG=release` của terminal bằng cách ưu tiên `.env` của dự án; vẫn kiểm tra chặt giá trị boolean.
- Server đã được chạy thử tại `127.0.0.1:8000` và dừng sau kiểm tra.

Để khởi động lại bằng PowerShell, không cần kích hoạt `.venv`:

```powershell
Set-Location D:\DOANTOTNGHIEP
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## CHƯA LÀM

- Accounts, Custom User, đăng nhập/đăng xuất, Role và Permission.
- Migration, tài khoản quản trị, dữ liệu demo và các module nghiệp vụ.
- Các thư viện/pipeline AI và mọi nội dung thuộc GIAI ĐOẠN 2–15.
- Kiểm tra trực quan giao diện trong trình duyệt.

## BƯỚC TIẾP THEO

- Dừng tại GIAI ĐOẠN 1 theo yêu cầu.
- Chỉ bắt đầu GIAI ĐOẠN 2 — Accounts khi người dùng yêu cầu rõ ràng.
