# Báo cáo GIAI ĐOẠN 2 — Accounts

Ngày thực hiện: 17/09/2026. Thư mục: `D:\DOANTOTNGHIEP`.

## ĐÃ LÀM

- Tạo app `apps.accounts`, tổ chức riêng model, manager, forms, selectors, services, permissions, views, URL, admin, migration và tests.
- Custom User kế thừa `AbstractUser`, có username, email, role, trạng thái hoạt động, cờ admin, timestamps và password hashing chuẩn Django.
- Hai vai trò hệ thống: `MANAGER` (Quản trị viên / Quản lý) và `EMPLOYEE`. Không tách Admin và Manager thành hai actor; chưa tạo JobPosition.
- Đăng nhập, đăng xuất bằng POST; chuyển hướng `next` tuân thủ cơ chế kiểm tra host của Django.
- Tự đổi mật khẩu với kiểm tra mật khẩu cũ, xác nhận mật khẩu mới và password validators; giữ phiên hiện tại khi đổi thành công.
- Quản lý xem danh sách, tìm kiếm theo username/email/tên, lọc hoạt động/đã khóa, phân trang 20 tài khoản và giữ bộ lọc khi chuyển trang.
- Quản lý khóa/mở khóa và đặt lại mật khẩu nhân viên. Tài khoản quản lý và chính người thao tác không phải đối tượng của các hành động này.
- Khóa đặt `is_active=False`, không xóa tài khoản. `session_version` làm các phiên cũ hết hiệu lực kể cả khi tài khoản đã được mở khóa lại.
- Service thay đổi tài khoản dùng transaction, khóa dòng và kiểm tra lại quyền/trạng thái từ database; đổi mật khẩu chỉ ghi những trường liên quan.
- Permission helper/decorator/mixin dùng chung; sidebar theo quyền, trang 403/404 tiếng Việt, giao diện Bootstrap đáp ứng kích thước màn hình.
- Custom Django Admin chặn nhân viên dù có cờ `is_staff`; chỉ superuser hợp lệ được tạo/chỉnh sửa tài khoản trong User admin; cấm xóa.
- Ghi nhật ký thao tác tài khoản vào `django_admin_log` trong transaction; chỉ xem ở Admin; không ghi mật khẩu hoặc hash.
- Cập nhật README và hướng dẫn tạo tài khoản quản trị ban đầu.

## CẤU TRÚC HIỆN TẠI

```text
QLNH/                         # Settings và URL chính
apps/accounts/
├── __init__.py
├── apps.py
├── models.py                 # Custom User
├── managers.py
├── forms.py
├── selectors.py
├── services.py
├── permissions.py
├── views.py
├── urls.py
├── admin.py
├── migrations/
│   └── 0001_initial.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_permissions.py
    ├── test_services.py
    └── test_views.py
core/
├── constants.py
├── permissions.py
├── decorators.py
├── mixins.py
└── context_processors.py
templates/
├── base.html
├── home.html
├── 403.html
├── 404.html
├── accounts/
└── includes/
static/css/base.css
docs/stage-2-report.md
```

Các thư mục nền tảng từ GIAI ĐOẠN 1 vẫn được giữ. Chưa có app `employees` hoặc app nghiệp vụ tiếp theo.

## FILE ĐÃ TẠO

- Toàn bộ package `apps/accounts/` như cây cấu trúc trên, bao gồm các file `__init__.py` cho migration và tests.
- `core/constants.py`, `permissions.py`, `decorators.py`, `mixins.py`, `context_processors.py`.
- `templates/accounts/login.html`, `workspace.html`, `password_change_form.html`, `password_change_done.html`, `account_list.html`, `account_confirm_status.html`, `account_password_reset.html`.
- `templates/includes/sidebar.html`, `templates/includes/form_fields.html`, `templates/403.html`, `templates/404.html`.
- `docs/stage-2-report.md`.

## FILE ĐÃ SỬA

- `QLNH/settings.py`: đăng ký app Accounts và các thành phần auth/admin/session, Custom User, context processor và URL chuyển hướng.
- `QLNH/urls.py`: thêm URL Accounts và custom Django Admin.
- `templates/base.html`, `templates/home.html`, `static/css/base.css`: điều hướng, sidebar và giao diện tài khoản.
- `requirements.txt`: cập nhật chú thích phạm vi; không thêm dependency.
- `README.md`: trạng thái dự án, cấu trúc, chức năng, quyền, migration và hướng dẫn sử dụng Accounts.
- Giữ nguyên `.env`; không đưa secret vào các file có thể theo dõi bằng Git.

## MIGRATION

- `AUTH_USER_MODEL = 'accounts.User'` đã được đặt trước migration đầu tiên.
- Tạo và áp dụng `accounts.0001_initial` cùng migration chuẩn của auth, contenttypes, admin và sessions; tổng cộng 19 migration đã áp dụng.
- Bảng tài khoản là `accounts_user`; kiểm tra thực tế xác nhận không tồn tại bảng `auth_user`.
- Không sửa migration đã được áp dụng. Nhật ký dùng bảng Django Admin sẵn có, không thêm schema riêng.
- Không thay đổi database khác đã tồn tại. Test runner chỉ tạo rồi dọn database kiểm thử riêng sau khi đã xác nhận tên đó chưa tồn tại.

## TEST

- `python manage.py test --verbosity 1`: **63/63 test đạt**, chạy trong 42,854 giây trên PostgreSQL. Database kiểm thử được dọn sau khi hoàn tất.
- Bộ kiểm thử bao gồm model/DB constraints, password hashing, login/logout, mật khẩu cũ, password validators, CSRF, redirect ngoài host, role và quyền trên đối tượng.
- Kiểm tra nhân viên có cờ staff không được vượt quyền; manager không thể sửa chính mình hoặc quản lý khác qua màn hình quản lý nhân viên.
- Kiểm tra khóa/mở khóa không xóa dữ liệu, phiên cũ không phục hồi, đặt lại mật khẩu vô hiệu hóa phiên, đổi mật khẩu không ghi đè trạng thái từ instance cũ và hỗ trợ secret key fallback.
- Kiểm tra tìm kiếm, lọc, dữ liệu không hợp lệ, phân trang, User admin tạo tài khoản và cấm xóa/nâng quyền ngoài phạm vi.
- Kiểm tra nhật ký đúng người/đối tượng/hành động và không chứa password/hash, không tạo log thành công cho thao tác bị từ chối, rollback thay đổi nếu ghi log thất bại, Admin chỉ cho xem log.
- `check --database default`: không phát hiện vấn đề; `makemigrations --check --dry-run`: không có thay đổi model chưa tạo migration; `migrate --check`: không có migration chờ; `pip check`: không có xung đột dependency.
- Kiểm tra cú pháp Python, khoảng trắng và secret trong các file Git có thể theo dõi: đạt.
- HTTP qua runserver: trang chủ, đăng nhập Accounts/Admin và CSS/JS trả 200; trang bảo vệ chuyển hướng đến đăng nhập; POST đăng nhập thiếu CSRF trả 403.
- Công cụ trình duyệt không khởi động được, nên chưa kiểm tra trực quan bố cục bằng trình duyệt. HTTP và Django client tests không thay thế kiểm tra màn hình thực tế.

## KẾT QUẢ

- Module Accounts đã được triển khai với PostgreSQL, giao diện tiếng Việt, Custom User và chính sách quyền tập trung.
- Database ứng dụng chưa có tài khoản mẫu hoặc tài khoản với mật khẩu mặc định. Tài khoản test chỉ nằm trong database kiểm thử và đã được dọn sau test.
- Phiên server dùng để kiểm tra đã kết thúc. Khi bàn giao, cổng `8000` đang có một tiến trình phục vụ trang đăng nhập QLNH (HTTP 200); tiến trình này được giữ nguyên.
- Có thể tự tạo tài khoản quản trị đầu tiên bằng PowerShell; chỉ chạy lệnh `runserver` nếu chưa có server đang chạy:

```powershell
Set-Location D:\DOANTOTNGHIEP
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Tạo superuser sẽ tự đặt vai trò `MANAGER`. Nhập mật khẩu riêng khi terminal yêu cầu. Sau đó đăng nhập tại `/tai-khoan/dang-nhap/`; dùng `/admin/` để tạo tài khoản nhân viên dùng thử.

## CHƯA LÀM

- JobPosition, EmployeeProfile, EmployeeActivityLog và các chức năng quản lý hồ sơ nhân viên của GIAI ĐOẠN 3.
- Customer, đặt bàn, menu, đơn hàng, kho, thanh toán, báo cáo và AI.
- Seed demo; không tự tạo mật khẩu hoặc tài khoản mẫu trong database ứng dụng.
- Kiểm tra trực quan trên trình duyệt.

## BƯỚC TIẾP THEO

- Dừng ở GIAI ĐOẠN 2 theo phạm vi đã được yêu cầu.
- Chỉ bắt đầu GIAI ĐOẠN 3 — Employees khi người dùng yêu cầu.
