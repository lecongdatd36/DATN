# QLNH — Ứng dụng quản lý nhà hàng tích hợp AI

Đồ án tốt nghiệp xây dựng bằng Django Templates và PostgreSQL tại `D:\DOANTOTNGHIEP`. Project Django chính là `QLNH`; mã nguồn được khởi tạo mới.

**Trạng thái: GIAI ĐOẠN 6 — Đặt bàn, cập nhật ngày 20/09/2026.** Có quản lý tài khoản, nhân sự, khách hàng, khu vực, bàn và đặt bàn; giao diện tiếng Việt. Khách hàng chỉ nhập họ tên và số điện thoại. Các nghiệp vụ thực đơn, đơn hàng, kho, thanh toán, báo cáo và AI chưa triển khai. Chi tiết kiểm chứng: [báo cáo Giai đoạn 6](docs/stage-6-report.md).

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
│   ├── accounts/              # Xác thực, tài khoản và chính sách thao tác
│   ├── employees/             # Vị trí, hồ sơ, nhật ký, migrations và tests
│   ├── customers/             # Khách hàng, phân quyền và nhật ký
│   ├── seating/               # Khu vực, bàn, phân quyền và nhật ký
│   └── bookings/              # Lịch đặt, nhận khách và nhật ký
├── core/
│   ├── permissions.py
│   ├── decorators.py
│   ├── mixins.py
│   └── context_processors.py
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── accounts/
│   ├── employees/
│   ├── customers/
│   ├── seating/
│   ├── bookings/
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

Các app `accounts`, `employees`, `customers`, `seating` và `bookings` tách model, form/validation, truy vấn đọc (`selectors.py`), nghiệp vụ thay đổi dữ liệu (`services.py`), quyền và request/response. `core/` cung cấp chính sách quyền, khóa giao dịch bàn/lịch đặt và xử lý lỗi form dùng chung. Các module còn lại được tạo khi tới giai đoạn tương ứng.

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

Tạo tài khoản quản trị đầu tiên bằng lệnh tương tác dưới đây. Lệnh đặt cờ superuser/staff và gán nhóm `MANAGER`; bạn tự nhập tên đăng nhập, email và mật khẩu. Không có mật khẩu quản trị mặc định. Superuser khởi tạo bằng CLI không bắt buộc có hồ sơ nhân viên.

```powershell
python manage.py createsuperuser
```

Đăng nhập tại `/tai-khoan/dang-nhap/`. **Nhân sự → Thêm nhân viên** dẫn đến cùng form **Tài khoản → Thêm tài khoản**. Trang Nhân sự gồm hồ sơ Quản lí và nhân viên. Form tạo đồng thời User, hồ sơ và nhóm vị trí trong một transaction; không tạo User nhân viên độc lập. Cờ `is_staff` chỉ phục vụ quyền vào Django Admin, không cấp quyền quản lý nhân sự.

Migration `employees.0008_correct_staff_permissions` sửa nhóm quyền trên database cũ và tự tạo quyền cần thiết trên database mới. Migration tăng phiên bản phiên đăng nhập để mọi tài khoản đăng nhập lại. Không sửa migration cũ; đảo ngược migration này không khôi phục bộ quyền sai trước đó.

Hiện chưa có command `seed_demo` hoặc dữ liệu demo. Lệnh `python manage.py seed_demo` chỉ sử dụng sau khi command được triển khai ở giai đoạn dữ liệu demo.

## Chức năng và quyền tài khoản

| Chức năng | Quản lí / Superuser | Phục vụ / Thu ngân / Bếp / Kho |
| --- | --- | --- |
| Đăng nhập, đăng xuất và không gian làm việc | Có, khi tài khoản hoạt động | Có, khi tài khoản hoạt động |
| Tự đổi mật khẩu | Có, cần mật khẩu cũ | Có, cần mật khẩu cũ |
| Danh sách, tìm kiếm, lọc và phân trang tài khoản | Có | Không |
| Khóa/mở khóa tài khoản nhân viên | Có | Không |
| Đặt lại mật khẩu nhân viên | Có | Không |
| Tạo nhân viên kèm tài khoản đăng nhập | Có | Không |
| Truy cập Django Admin | Cần thêm `is_staff` | Không |
| Xem vị trí, hồ sơ, nhật ký trong Django Admin | Cần thêm `is_staff` | Không |
| Xem User trong Django Admin | Cần thêm `is_superuser` | Không |
| Thêm/sửa/xóa dữ liệu nhân sự qua Django Admin | Không; dùng giao diện nghiệp vụ | Không |

`User` không còn trường `role`. `JobPosition` liên kết với nhóm Django: `MANAGER`, `WAITER`, `CASHIER`, `KITCHEN`, `INVENTORY`. Chỉ nhóm `MANAGER` có quyền `employees.manage_staff`; superuser đang hoạt động cũng được quản lý. Quyền cũ `change_employeeprofile` không đủ để mở chức năng quản lý. Khách hàng là nghiệp vụ riêng, không cần tài khoản nội bộ.

Tên hiển thị vị trí `MANAGER` là **Quản lí**; superuser hiển thị **Quản trị hệ thống**. Migration `employees.0009_rename_manager_position` cập nhật tên vị trí trên database cũ, không thay đổi mã hoặc quyền.

- `/tai-khoan/dang-nhap/`: đăng nhập bằng username và mật khẩu.
- `/tai-khoan/`: không gian làm việc sau đăng nhập.
- `/tai-khoan/doi-mat-khau/`: tự đổi mật khẩu, xác thực mật khẩu cũ và giữ phiên hiện tại khi thành công.
- `/tai-khoan/quan-ly/`: quản lý danh sách, tìm theo username/email/tên, lọc trạng thái và phân trang 20 tài khoản/trang.
- `/nhan-vien/`: tìm theo mã/tên/điện thoại/username, lọc vị trí và trạng thái, phân trang 20 hồ sơ/trang.
- Superuser được quản lý tài khoản quản lý khác và nhân viên, kể cả tài khoản cũ chưa có hồ sơ. Quản lý thường chỉ thao tác nhân viên có hồ sơ và không có quyền quản lý. Các luồng quản lý không sửa chính người đăng nhập hoặc bất kỳ superuser nào; tự đổi mật khẩu vẫn được phép.
- Dòng “Chỉ xem” giải thích nguyên nhân: tài khoản đang đăng nhập, superuser được bảo vệ hoặc cần quyền superuser. Tài khoản superuser hiển thị loại “Quản trị hệ thống” và không cần hồ sơ nhân sự để sử dụng.
- Khóa tài khoản đặt `is_active=False`, không xóa bản ghi. Phiên đăng nhập cũ bị vô hiệu hóa và không có hiệu lực trở lại khi mở khóa.
- Đặt lại mật khẩu không cần mật khẩu cũ của nhân viên, nhưng phải qua các bộ kiểm tra mật khẩu của Django; phiên cũ của nhân viên hết hiệu lực.
- Đăng xuất và thao tác thay đổi dữ liệu dùng POST có CSRF. Trang xác nhận khóa/mở khóa không thay đổi dữ liệu khi chỉ mở bằng GET.
- Quyền được kiểm tra tại view và service; service đọc lại actor từ database. Sidebar và nút thao tác theo quyền. Django Admin chỉ tra cứu dữ liệu nhân sự.
- Khóa/mở khóa và đổi/đặt lại mật khẩu được ghi vào nhật ký Django (`LogEntry`) trong cùng transaction với thay đổi. Nhật ký chỉ xem tại Django Admin; không lưu mật khẩu hay password hash.
- Chuyển sang nghỉ việc yêu cầu ngày nghỉ hợp lệ và khóa tài khoản. Khi đi làm lại, tài khoản vẫn khóa cho đến khi quản lý mở khóa riêng; không thể mở khóa khi hồ sơ vẫn đã nghỉ việc.
- Đổi vị trí đồng bộ nhóm quyền và cờ staff, vô hiệu hóa phiên cũ. Reset mật khẩu từ form hồ sơ cũng được ghi nhật ký.
- Ảnh tải lên được kiểm tra định dạng bởi form và giới hạn 5 MB. Không yêu cầu đọc lại file ảnh cũ khi sửa các trường khác.
- Các service ghi nhân sự dùng transaction và khóa PostgreSQL dùng chung để tránh cấp trùng mã khi tạo đồng thời. Mã tự sinh không sử dụng lại mã còn trong nhật ký.
- Nút **Xóa** có trên danh sách và chi tiết tài khoản, dẫn tới trang xác nhận `/tai-khoan/quan-ly/<id>/xoa/`. Chỉ POST có CSRF mới xóa; GET không thay đổi dữ liệu. Xóa được tài khoản thiếu hồ sơ trong phạm vi quyền của superuser.
- Xóa tài khoản và Xóa nhân viên dùng chung service: xóa User cùng hồ sơ liên kết trong một transaction, ghi nhật ký xóa tài khoản và giữ snapshot lịch sử nhân viên. Từ chối đối tượng được bảo vệ hoặc có liên kết `PROTECT`/`RESTRICT`; rollback nếu ghi nhật ký hoặc xóa thất bại.
- Nếu tài khoản đã thực hiện thao tác có nhật ký Django (`LogEntry.user`), hệ thống yêu cầu khóa thay vì xóa để tránh Django xóa dây chuyền lịch sử của người đó. Khi thêm đơn hàng/hóa đơn, quan hệ nhân viên phải dùng `PROTECT`; ưu tiên nghỉ việc để giữ lịch sử.

## Khách hàng

Vào menu **Khách hàng** hoặc `/khach-hang/`. Form thêm/sửa chỉ gồm **Họ tên** và **Số điện thoại**, không có email, địa chỉ hoặc ghi chú. Mã `KH000001` và thời gian được tạo tự động; khách hàng không có tài khoản đăng nhập.

| Chức năng | Quản lí / Superuser | Phục vụ / Thu ngân | Bếp / Kho |
| --- | --- | --- | --- |
| Xem, tìm kiếm, phân trang | Có | Có | Không |
| Thêm, sửa khách hàng | Có | Có | Không |
| Xóa qua trang xác nhận | Có | Không | Không |
| Xem nhật ký khách hàng | Có | Không | Không |

- Tìm theo mã khách, họ tên hoặc số điện thoại; 20 kết quả/trang.
- Chuẩn hóa số điện thoại nhập có dấu cách, dấu chấm, ngoặc, gạch ngang hoặc mã `+84` về dạng bắt đầu bằng `0`, dài 10–11 chữ số. Một số điện thoại chỉ có một hồ sơ; chặn trùng tại form, service và database, kể cả tạo đồng thời.
- Thêm/sửa/xóa dùng POST có CSRF và kiểm tra quyền lại ở service. Thay đổi dữ liệu và nhật ký nằm trong cùng transaction; lưu lại mà không đổi thông tin không tạo thêm nhật ký.
- Xóa giữ mã/tên khách và tên đăng nhập người thực hiện trong nhật ký; từ chối nếu có liên kết `PROTECT`/`RESTRICT`. Khách đã có lịch đặt bàn được bảo vệ, kể cả lịch đã hủy. Khi triển khai đơn hàng cũng cần khai báo liên kết bảo vệ.
- `/khach-hang/nhat-ky/` tìm theo mã/tên khách/người thực hiện và lọc hành động, xem được cả khách đã xóa. Django Admin chỉ tra cứu; thêm/sửa/xóa qua màn hình Khách hàng.
- Migration `customers.0002_seed_customer_permissions` cấp quyền cho các nhóm có sẵn, hoạt động cả trên database mới. Quyền nhân sự không thay đổi.

## Khu vực và bàn

1. Vào **Khu vực → Thêm khu vực**, nhập tên (tầng, phòng, khu phục vụ), để chọn **Đang sử dụng**.
2. Vào **Bàn → Thêm bàn**, nhập mã bàn duy nhất, chọn khu vực và số chỗ (1–100).
3. Dùng **Sửa / trạng thái** để đổi thông tin hoặc bỏ chọn **Đang sử dụng** khi bảo trì/ngừng dùng. Không có thao tác xóa vĩnh viễn trong giai đoạn này.

- `/ban/`: danh sách bàn, tìm theo mã/khu vực, lọc khu vực và trạng thái hiện tại, phân trang 20 dòng.
- `/ban/khu-vuc/`: danh sách khu vực, số bàn, tìm tên và lọc trạng thái.
- `/ban/nhat-ky/`: nhật ký thay đổi, chỉ Quản lí/Superuser xem.
- Quản lí/Superuser thêm, sửa, ngừng và mở lại khu vực/bàn. Phục vụ/Thu ngân chỉ xem. Bếp/Kho không truy cập.
- Tên khu vực không trùng khi khác chữ hoa/thường; mã bàn tự chuyển thành chữ hoa và duy nhất toàn nhà hàng.
- Ngừng khu vực khiến mọi bàn bên trong không sử dụng được; trạng thái riêng của từng bàn vẫn giữ. Mở lại khu vực cho phép dùng các bàn đang bật, không tự bật bàn vốn đã ngừng.
- Không thêm/chuyển bàn vào khu vực đã ngừng. Bàn hiện có trong khu vực đã ngừng vẫn sửa thông tin, tắt hoặc chuyển ra được; không thể bật lại bàn đã tắt trước khi mở khu vực.
- Trang Bàn hiển thị **Đang phục vụ** nếu có lượt khách đã nhận, kể cả quá giờ dự kiến; **Đang giữ chỗ** nếu lịch chờ/đã xác nhận đang trong giờ hẹn; **Trống hiện tại** khi không có hai trường hợp trên; **Ngừng sử dụng** khi bàn/khu vực đóng. Nếu dữ liệu bất thường vừa đóng vừa có khách, vẫn hiển thị Đang phục vụ kèm cảnh báo đóng để không che mất khách đang ngồi.
- Lịch trong tương lai không làm bàn bị chiếm ngay; hiển thị riêng giờ của lịch kế tiếp và liên kết chi tiết theo quyền. Nhận khách/hoàn tất/hủy được phản ánh khi mở hoặc cập nhật trang Bàn; có thời điểm cập nhật và nút tải lại, chưa tự đẩy thay đổi đến tab đang mở.
- Nhật ký và thay đổi dữ liệu cùng transaction; quyền được kiểm tra ở view/service, POST có CSRF. Django Admin chỉ xem.
- Migration `seating.0002_seed_seating_permissions` cấp quyền riêng cho các nhóm hiện có, không sửa quyền nhân sự/khách hàng.

Từ Giai đoạn 6, ngừng khu vực/bàn, chuyển khu vực hoặc giảm số chỗ còn được kiểm tra với lịch đặt đang hiệu lực. Bàn có khách đã nhận vẫn được bảo vệ dù quá giờ kết thúc dự kiến.

## Đặt bàn

1. Tạo hồ sơ khách (họ tên và số điện thoại) nếu chưa có.
2. Vào **Đặt bàn → Tìm bàn phù hợp**, nhập giờ đến và số khách. Hệ thống tự dùng thời lượng mặc định (ban đầu 120 phút); chỉ mở **Điều chỉnh thời lượng dự kiến** khi cần thay đổi. Chọn bàn, điền số điện thoại khách rồi lưu. Có thể tạo trực tiếp từ **Thêm đặt bàn** hoặc từ trang chi tiết khách hàng.
3. Lịch mới ở trạng thái **Chờ xác nhận**, đã giữ chỗ. Sau khi thống nhất với khách, chọn **Xác nhận đặt bàn**.
4. Trong khoảng giờ hẹn, chọn **Nhận khách** khi khách thực sự đến, trạng thái chuyển **Đang phục vụ**. Chọn **Hoàn tất** khi khách rời bàn; chưa có thanh toán ở bước này.
5. Lịch chưa nhận khách có thể hủy, hoặc đánh dấu **Không đến** từ giờ hẹn trở đi. Hai trạng thái này giải phóng lịch, giữ hồ sơ và nhật ký.

- `/dat-ban/`: tìm theo mã đặt, tên/điện thoại khách, mã bàn; lọc ngày đến, trạng thái, bàn và phân trang.
- `/dat-ban/ban-phu-hop/`: tìm bàn đang sử dụng, đủ chỗ và không trùng lịch. Kết quả tra cứu chưa giữ bàn; hệ thống kiểm tra lại khi lưu.
- `/dat-ban/cau-hinh/`: Quản lí/Superuser cấu hình thời lượng mặc định, từ 1 đến 1440 phút, có lịch sử thay đổi. Chỉ áp dụng cho lịch mới; lịch đã lưu giữ nguyên thời gian dự kiến và thời lượng riêng khi mở form sửa.
- Form không nhập giờ kết thúc. Máy chủ tính giờ đến + thời lượng; JavaScript chỉ giúp xem trước khoảng giờ (kể cả qua nửa đêm). Tắt JavaScript vẫn lưu và kiểm tra lịch bình thường. Nhân viên được chỉnh thời lượng từng lịch mà không được đổi cấu hình chung.
- Mỗi lịch gắn **một khách hàng và một bàn**. Chưa có ghép bàn, đặt nhiều bàn trong một phiếu hoặc thu tiền cọc.
- Quản lí/Superuser và Phục vụ/Thu ngân được xem, tạo, sửa và xử lý trạng thái. Chỉ Quản lí/Superuser xem nhật ký; Bếp/Kho không truy cập.
- Giờ nhập/hiển thị theo Việt Nam. Giờ đến mới phải ở tương lai; kết thúc phải sau giờ đến. Hai lịch liên tiếp được phép nếu giờ kết thúc lịch trước bằng giờ bắt đầu lịch sau.
- Chỉ sửa lịch chờ xác nhận/đã xác nhận. Sửa lịch đã xác nhận đưa về chờ xác nhận lại; form cũ bị từ chối nếu người khác đã sửa hoặc chuyển trạng thái.
- Chỉ nhận khách sau xác nhận, trong khoảng giờ đã đặt. Khách đến sớm cần sửa giờ hẹn và xác nhận lại. Khách quá giờ dự kiến vẫn giữ trạng thái đã nhận cho đến khi nhân viên hoàn tất; chặn nhận lượt sau nếu bàn còn khách.
- Danh sách cảnh báo tối đa 10 lượt đang phục vụ quá giờ, kèm liên kết tới lịch kế tiếp cùng bàn nếu có; chi tiết lịch cũng cảnh báo để nhân viên đổi bàn hoặc trao đổi lại giờ đến. Cảnh báo không tự đổi lịch hay hoàn tất lượt khách.
- Không xóa lịch; lưu tên/điện thoại lúc đặt và nhật ký. Khách/bàn có lịch được bảo vệ khỏi xóa vĩnh viễn. Django Admin chỉ tra cứu.
- Chống trùng lịch dùng transaction và khóa PostgreSQL chung với thay đổi danh mục bàn; mọi thao tác ghi phải qua service. Chưa có constraint chống chồng khoảng thời gian cho lệnh SQL ghi trực tiếp ngoài ứng dụng.

## Kiểm tra và chạy ứng dụng

Từ thư mục gốc, với môi trường ảo đã kích hoạt và `.env` đã điền:

```powershell
python manage.py check
python scripts/run_tests.py
python manage.py runserver 127.0.0.1:8000
```

Mở [http://127.0.0.1:8000/](http://127.0.0.1:8000/) để kiểm tra trang nền tảng. Dừng server bằng `Ctrl+C`.

`check` kiểm tra cấu hình Django. Có 165 test cho Accounts, Employees, Customers, Seating và Bookings, gồm phân quyền, form, thời lượng mặc định/tùy chỉnh, cấu hình, trạng thái bàn theo lượt khách/lịch đặt, cảnh báo quá giờ, phiên đăng nhập, nhật ký, rollback và thao tác đồng thời bằng các kết nối PostgreSQL riêng. Chạy riêng module: `python scripts/run_tests.py apps.bookings`.

`scripts/run_tests.py` tạo database kiểm thử PostgreSQL với tên UUID riêng mỗi lần chạy, chạy toàn bộ migration từ đầu và dọn database khi hoàn tất. Tài khoản PostgreSQL cần quyền tạo database. Lệnh chuẩn `manage.py test` vẫn dùng tên mặc định `test_QLNH_DB`; nếu tên đó tồn tại mà không rõ nguồn gốc, không chấp nhận yêu cầu xóa của test runner.

Thư mục `templates/` chứa template dùng chung; `static/` chứa CSS, JavaScript và ảnh giao diện; `media/` dành cho tệp tải lên. Bootstrap được lưu trong `static/vendor/` để giao diện không phụ thuộc CDN khi chạy. Server phát triển phục vụ static và media khi `DEBUG=True`.

## Git và phạm vi triển khai

Repository Git đã có lịch sử commit. `.gitignore` loại trừ `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `media/`, `.idea/` và `.vscode/` cùng các tệp phát sinh cục bộ.

Phạm vi hiện tại là **GIAI ĐOẠN 6 — Đặt bàn**. Đề xuất module mới tiếp theo: Thực đơn, rồi Đơn hàng/Bếp/Thanh toán, Kho/Báo cáo và AI. Chưa triển khai các module này.

Lịch sử: [Giai đoạn 1](docs/stage-1-report.md), [Giai đoạn 2](docs/stage-2-report.md), [Giai đoạn 3](docs/stage-3-report.md), [Giai đoạn 4](docs/stage-4-report.md), [Giai đoạn 5](docs/stage-5-report.md). Hiện trạng và kiểm chứng mới nhất: [Giai đoạn 6](docs/stage-6-report.md). Chưa hoàn tất kiểm tra bố cục trực quan do công cụ Browser lỗi khởi tạo.
