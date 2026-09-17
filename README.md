# QLNH — Ứng dụng quản lý nhà hàng tích hợp AI

Đồ án tốt nghiệp xây dựng bằng Django Templates và PostgreSQL tại `D:\DOANTOTNGHIEP`. Project Django chính là `QLNH`; mã nguồn được khởi tạo mới.

**Trạng thái: GIAI ĐOẠN 2 — Accounts.** Dự án có Custom User, đăng nhập/đăng xuất, đổi mật khẩu, quản lý tài khoản nhân viên và bộ kiểm tra quyền dùng chung. Giao diện bằng tiếng Việt. Chưa triển khai hồ sơ nhân viên và các module nghiệp vụ tiếp theo.

## Công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Môi trường phát triển | Windows, Python 3.12.8, virtual environment `.venv` |
| Backend | Django 5.2.17 |
| Database | PostgreSQL 17, driver `psycopg[binary]` 3.3.5 |
| Cấu hình | `python-dotenv` 1.2.3, file `.env` tại thư mục gốc |
| Giao diện | Django Templates, HTML5, CSS3, Bootstrap 5.3.8, JavaScript |
| Ngôn ngữ và thời gian | `vi`, `Asia/Ho_Chi_Minh`, `USE_I18N=True`, `USE_TZ=True` |

Phiên bản dependency cụ thể được cố định trong `requirements.txt`. `tzdata` 2026.4 cung cấp dữ liệu múi giờ cho môi trường Windows. Các thư viện xử lý dữ liệu và Machine Learning sẽ được bổ sung ở giai đoạn AI.

## Cấu trúc hiện tại

```text
D:\DOANTOTNGHIEP/
├── manage.py
├── requirements.txt
├── .env                       # Cấu hình máy cá nhân; Git bỏ qua
├── .env.example               # Mẫu cấu hình không chứa mật khẩu thật
├── .gitignore
├── README.md
├── .venv/                     # Môi trường Python; Git bỏ qua
├── QLNH/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   └── accounts/              # Model, forms, services, selectors, views, tests
├── core/
│   ├── constants.py
│   ├── permissions.py
│   ├── decorators.py
│   ├── mixins.py
│   └── context_processors.py
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── accounts/
│   └── includes/
├── static/
│   ├── css/
│   ├── js/
│   ├── images/
│   └── vendor/                # Bootstrap 5.3.8 phục vụ từ máy cục bộ
├── media/                     # Tệp người dùng tải lên; Git bỏ qua
│   ├── employees/
│   ├── dishes/
│   └── restaurant/
├── fixtures/
├── scripts/
├── notebooks/
└── docs/
    ├── erd/
    ├── usecase/
    ├── activity/
    └── sequence/
```

`apps/accounts/` tách model, form/validation, truy vấn đọc (`selectors.py`), nghiệp vụ thay đổi dữ liệu (`services.py`), quyền và request/response. `core/` cung cấp chính sách quyền dùng chung cho views và điều hướng. Các app `employees`, `customers` và app khác chỉ được tạo khi tới giai đoạn tương ứng.

## Chuẩn bị Python và môi trường ảo

Cài Python **3.12** cho Windows, kèm Python Launcher (`py`). Kiểm tra bằng:

```powershell
py -3.12 --version
```

Nếu dùng thư mục dự án đã được chuẩn bị trên máy này, `.venv` đã tồn tại; chỉ cần kích hoạt. Trên máy mới hoặc khi chưa có `.venv`, tạo môi trường bằng:

```powershell
Set-Location D:\DOANTOTNGHIEP
py -3.12 -m venv .venv
```

Kích hoạt trong **PowerShell**:

```powershell
.\.venv\Scripts\Activate.ps1
```

Hoặc dùng **Command Prompt**:

```bat
cd /d D:\DOANTOTNGHIEP
.venv\Scripts\activate.bat
```

Nếu PowerShell chặn script kích hoạt, có thể dùng Command Prompt hoặc gọi trực tiếp `.\.venv\Scripts\python.exe` thay cho `python` trong các lệnh dưới đây, không cần đổi execution policy.

Sau khi kích hoạt, cài dependency:

```powershell
python -m pip install -r requirements.txt
python --version
python -m django --version
```

## Cấu hình `.env`

File `.env` nằm cạnh `manage.py` và được đọc từ thư mục gốc dự án, ưu tiên hơn các biến cùng tên trong môi trường terminal (chẳng hạn `DEBUG`). Giữ nguyên file đã được cấu hình trên máy hiện tại. Khi thiết lập máy mới, chỉ sao chép mẫu nếu chưa có `.env`.

PowerShell:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Command Prompt:

```bat
if not exist .env copy .env.example .env
```

Tạo một secret key mới nếu `.env` chưa có khóa hợp lệ:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Điền giá trị vừa tạo vào `SECRET_KEY` và mật khẩu PostgreSQL của máy vào `DB_PASSWORD`. Dùng dấu nháy đơn bao quanh secret key để ký tự đặc biệt được giữ nguyên. Cấu hình mẫu:

```dotenv
SECRET_KEY='thay-bang-secret-key-vua-tao'
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,[::1]

DB_NAME=QLNH_DB
DB_USER=postgres
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=5432
```

`DB_PASSWORD` phải được điền trong `.env` thực tế. `.env.example` giữ giá trị này trống. Không đưa secret key hoặc mật khẩu thật vào mã nguồn, README hay Git. `DEBUG=True` dành cho phát triển cục bộ.

## PostgreSQL 17 và database `QLNH_DB`

PostgreSQL 17 đã được cài trên máy làm việc. Đường dẫn công cụ mặc định là `C:\Program Files\PostgreSQL\17\bin`; điều chỉnh nếu máy dùng vị trí khác.

Kiểm tra dịch vụ và khả năng nhận kết nối trong PowerShell:

```powershell
Get-Service -Name '*postgresql*'
& 'C:\Program Files\PostgreSQL\17\bin\pg_isready.exe' -h 127.0.0.1 -p 5432
```

Nếu dịch vụ đang dừng, mở Windows Services và khởi động dịch vụ PostgreSQL 17 bằng tài khoản có quyền phù hợp. Kiểm tra database đã tồn tại bằng lệnh chỉ đọc:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h 127.0.0.1 -p 5432 -U postgres -d postgres -W -tAc "SELECT 1 FROM pg_database WHERE datname = 'QLNH_DB';"
```

Nhập mật khẩu khi được hỏi. Nếu kết nối thành công và kết quả có `1`, database đã tồn tại. Chỉ khi kết nối thành công nhưng truy vấn không trả dòng nào, tạo database:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\createdb.exe' -h 127.0.0.1 -p 5432 -U postgres -W -E UTF8 QLNH_DB
```

Trong Command Prompt, gọi công cụ tương tự, bỏ ký tự `&` và dùng dấu nháy kép quanh đường dẫn:

```bat
"C:\Program Files\PostgreSQL\17\bin\pg_isready.exe" -h 127.0.0.1 -p 5432
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres -W -tAc "SELECT 1 FROM pg_database WHERE datname = 'QLNH_DB';"
```

Các bước này chỉ kiểm tra hoặc tạo `QLNH_DB`; không xóa hay thay đổi database khác. Nếu đã có dữ liệu trong `QLNH_DB`, giữ nguyên và kiểm tra trước khi thực hiện migration.

Kiểm tra Django kết nối đúng database với cấu hình `.env`:

```powershell
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Database:', connection.settings_dict['NAME']); print('Vendor:', connection.vendor)"
```

Kết quả mong đợi là `Database: QLNH_DB` và `Vendor: postgresql`.

## Migration, tài khoản quản trị và dữ liệu demo

Custom User là `accounts.User`, được khai báo bằng `AUTH_USER_MODEL` trước migration đầu tiên. GIAI ĐOẠN 1 chưa chạy migration, vì vậy không có bước chuyển đổi từ bảng User mặc định. Tham khảo [tài liệu Custom User của Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#using-a-custom-user-model-when-starting-a-project).

Trên máy mới, áp dụng các migration đã có trong source:

```powershell
python manage.py migrate
```

Tạo tài khoản quản trị đầu tiên bằng lệnh tương tác dưới đây. Lệnh tự đặt vai trò `MANAGER`; bạn tự nhập tên đăng nhập, email và mật khẩu. Không có mật khẩu quản trị mặc định.

```powershell
python manage.py createsuperuser
```

Đăng nhập tại `/tai-khoan/dang-nhap/`. Tạo nhân viên từ màn hình **Nhân viên → Thêm nhân viên**; thao tác này tạo đồng thời tài khoản đăng nhập và hồ sơ nhân viên trong một transaction. Màn hình **Tài khoản** chỉ dùng để khóa/mở khóa, sửa thông tin đăng nhập và đặt lại mật khẩu, không tạo User độc lập. Cờ `is_staff` chỉ phục vụ quyền vào Django Admin; nó không thay thế vai trò hệ thống.

Hiện chưa có command `seed_demo` hoặc dữ liệu demo. Lệnh `python manage.py seed_demo` chỉ sử dụng sau khi command được triển khai ở giai đoạn dữ liệu demo.

## Chức năng và quyền tài khoản

| Chức năng | Quản trị viên / Quản lý (`MANAGER`) | Nhân viên (`EMPLOYEE`) |
| --- | --- | --- |
| Đăng nhập, đăng xuất và không gian làm việc | Có, khi tài khoản hoạt động | Có, khi tài khoản hoạt động |
| Tự đổi mật khẩu | Có, cần mật khẩu cũ | Có, cần mật khẩu cũ |
| Danh sách, tìm kiếm, lọc và phân trang tài khoản | Có | Không |
| Khóa/mở khóa tài khoản nhân viên | Có | Không |
| Đặt lại mật khẩu nhân viên | Có | Không |
| Tạo nhân viên kèm tài khoản đăng nhập | Có | Không |
| Truy cập Django Admin | Cần thêm `is_staff` | Không |
| Xem/chỉnh sửa hồ sơ nhân viên trong Django Admin | Cần thêm `is_staff` | Không |
| Tạo/chỉnh sửa User trong Django Admin | Cần thêm `is_superuser` | Không |

Hệ thống chỉ có hai vai trò đăng nhập; Quản trị viên và Quản lý là cùng một actor. Khách hàng không cần tài khoản và sẽ được triển khai ở giai đoạn riêng. Mỗi nhân viên có đúng một User và một `EmployeeProfile`; không tạo tài khoản nhân viên độc lập từ màn hình Tài khoản.

- `/tai-khoan/dang-nhap/`: đăng nhập bằng username và mật khẩu.
- `/tai-khoan/`: không gian làm việc sau đăng nhập.
- `/tai-khoan/doi-mat-khau/`: tự đổi mật khẩu, xác thực mật khẩu cũ và giữ phiên hiện tại khi thành công.
- `/tai-khoan/quan-ly/`: quản lý danh sách, tìm theo username/email/tên, lọc trạng thái và phân trang 20 tài khoản/trang.
- Khóa/mở khóa và đặt lại mật khẩu chỉ áp dụng cho tài khoản nhân viên; màn hình này không thao tác tài khoản quản lý hoặc chính người đang đăng nhập.
- Khóa tài khoản đặt `is_active=False`, không xóa bản ghi. Phiên đăng nhập cũ bị vô hiệu hóa và không có hiệu lực trở lại khi mở khóa.
- Đặt lại mật khẩu không cần mật khẩu cũ của nhân viên, nhưng phải qua các bộ kiểm tra mật khẩu của Django; phiên cũ của nhân viên hết hiệu lực.
- Đăng xuất và thao tác thay đổi dữ liệu dùng POST có CSRF. Trang xác nhận khóa/mở khóa không thay đổi dữ liệu khi chỉ mở bằng GET.
- Quyền được kiểm tra tại view và service; sidebar chỉ hiện chức năng được phép. Không có chức năng xóa tài khoản trong giao diện hoặc Django Admin.
- Khóa/mở khóa và đổi/đặt lại mật khẩu được ghi vào nhật ký Django (`LogEntry`) trong cùng transaction với thay đổi. Nhật ký chỉ xem tại Django Admin; không lưu mật khẩu hay password hash.

## Kiểm tra và chạy ứng dụng

Từ thư mục gốc, với môi trường ảo đã kích hoạt và `.env` đã điền:

```powershell
python manage.py check
python manage.py test
python manage.py runserver 127.0.0.1:8000
```

Mở [http://127.0.0.1:8000/](http://127.0.0.1:8000/) để kiểm tra trang nền tảng. Dừng server bằng `Ctrl+C`.

`check` kiểm tra cấu hình Django. Các kiểm thử Accounts sử dụng `Django TestCase` trên PostgreSQL, bao gồm đăng nhập, mật khẩu, phân quyền, service khóa/mở khóa và danh sách tài khoản. Chạy riêng module bằng `python manage.py test apps.accounts`.

Django tạo database kiểm thử riêng (mặc định `test_QLNH_DB`) và xóa nó khi hoàn tất; tài khoản PostgreSQL cần quyền tạo database. Không sử dụng SQLite. Nếu tên database kiểm thử đã tồn tại từ trước và không rõ nguồn gốc, không chấp nhận yêu cầu xóa của test runner; kiểm tra nguồn gốc hoặc cấu hình tên test database riêng trước khi chạy.

Thư mục `templates/` chứa template dùng chung; `static/` chứa CSS, JavaScript và ảnh giao diện; `media/` dành cho tệp tải lên. Bootstrap được lưu trong `static/vendor/` để giao diện không phụ thuộc CDN khi chạy. Server phát triển phục vụ static và media khi `DEBUG=True`.

## Git và phạm vi triển khai

Repository Git đã được khởi tạo, chưa tạo commit. `.gitignore` loại trừ `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `media/`, `.idea/` và `.vscode/` cùng các tệp phát sinh cục bộ.

Phạm vi hiện tại kết thúc ở **GIAI ĐOẠN 2 — Accounts**. Bước tiếp theo là **GIAI ĐOẠN 3 — Employees: JobPosition, EmployeeProfile và EmployeeActivityLog**, chỉ bắt đầu khi người dùng yêu cầu.

Lịch sử nền tảng: [báo cáo GIAI ĐOẠN 1](docs/stage-1-report.md). Kết quả Accounts: [báo cáo GIAI ĐOẠN 2](docs/stage-2-report.md).
