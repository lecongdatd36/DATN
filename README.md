# QLNH — Ứng dụng quản lý nhà hàng tích hợp AI

Đồ án tốt nghiệp xây dựng bằng Django Templates và PostgreSQL tại `D:\DOANTOTNGHIEP`. Project Django chính là `QLNH`; mã nguồn được khởi tạo mới.

**Trạng thái: VẬN HÀNH TÍCH HỢP, cập nhật ngày 30/09/2026.** Có quản lý tài khoản, nhân sự, khách hàng, hạng thành viên, khu vực, bàn, đặt bàn, thực đơn, gọi món, Bếp, kho, hóa đơn, thanh toán VNPAY sandbox và báo cáo; giao diện tiếng Việt. [Báo cáo Giai đoạn 9](docs/stage-9-report.md) được giữ làm tài liệu lịch sử của luồng hóa đơn ban đầu.

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

Giao diện quản lý dùng bộ layout tự xây trên Bootstrap: sidebar theo quyền có thể thu gọn, topbar tài khoản, chế độ sáng/tối, menu mobile và dashboard thao tác nhanh. Thiết kế tham khảo phong cách admin dashboard hiện đại nhưng không sao chép hoặc phụ thuộc tài nguyên của template bên ngoài; toàn bộ CSS, JavaScript và SVG icon nằm trong mã nguồn dự án để dễ bảo trì.

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
│   ├── bookings/              # Lịch đặt, nhận khách và nhật ký
│   ├── menu/                  # Nhóm món, đơn vị tính, món, giá và trạng thái
│   └── orders/                # Gọi món, Bếp, hóa đơn và thanh toán
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
│   ├── menu/
│   ├── orders/
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

Các app `accounts`, `employees`, `customers`, `seating`, `bookings`, `menu` và `orders` tách model, form/validation, truy vấn đọc (`selectors.py`), nghiệp vụ thay đổi dữ liệu (`services.py`), quyền và request/response. `core/` cung cấp chính sách quyền, khóa giao dịch bàn/lịch đặt, khóa thực đơn và xử lý lỗi form dùng chung. Các module còn lại được tạo khi tới giai đoạn tương ứng.

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
- Nếu tài khoản đã thực hiện thao tác có nhật ký Django (`LogEntry.user`), hệ thống yêu cầu khóa thay vì xóa để tránh Django xóa dây chuyền lịch sử của người đó. Tài khoản đã mở đơn hàng được bảo vệ bằng `PROTECT`; ưu tiên khóa/nghỉ việc để giữ lịch sử. Quan hệ nhân viên với hóa đơn khi bổ sung cũng cần được bảo vệ.

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
- Xóa giữ mã/tên khách và tên đăng nhập người thực hiện trong nhật ký; từ chối nếu có liên kết `PROTECT`/`RESTRICT`. Khách đã có lịch đặt bàn được bảo vệ, kể cả lịch đã hủy. Đơn hàng bảo vệ lượt khách bằng `PROTECT`, giữ liên kết lịch sử này.
- `/khach-hang/nhat-ky/` tìm theo mã/tên khách/người thực hiện và lọc hành động, xem được cả khách đã xóa. Django Admin chỉ tra cứu; thêm/sửa/xóa qua màn hình Khách hàng.
- Migration `customers.0002_seed_customer_permissions` cấp quyền cho các nhóm có sẵn, hoạt động cả trên database mới. Quyền nhân sự không thay đổi.
- Quản lí cấu hình **Hạng thành viên** bằng mức chi tiêu tối thiểu, phần trăm giảm và trạng thái áp dụng. Khi lập phiếu tạm tính, hệ thống chọn hạng đang hoạt động cao nhất theo tổng chi tiêu đã chốt; mức giảm được snapshot vào hóa đơn khi thanh toán.
- Sau thanh toán thành công, số tiền thực trả được cộng đúng một lần vào `total_spending` và hạng khách được tính lại. Lịch sử hóa đơn đã thanh toán hiển thị tại chi tiết khách hàng.
- Database mới có sẵn bốn hạng **Đồng, Bạc, Vàng, Kim cương**; Quản lí có thể sửa ngưỡng và phần trăm tại menu **Hạng khách hàng**. Phục vụ và Thu ngân được xem bảng hạng nhưng không được sửa.

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
- Trang Bàn dùng lưới thẻ kiểu web app, tối ưu thao tác cảm ứng trên điện thoại: bàn có khách phát sáng và hiện thông tin lượt khách, bàn trống có icon bàn cùng nhãn **Đang trống**, bàn giữ chỗ màu vàng và bàn ngừng dùng được làm mờ. Trạng thái nghiệp vụ vẫn ưu tiên **Đang phục vụ** nếu có lượt khách đã nhận, kể cả quá giờ dự kiến; **Đang giữ chỗ** nếu lịch chờ/đã xác nhận đang trong giờ hẹn; **Ngừng sử dụng** khi bàn/khu vực đóng. Nếu dữ liệu bất thường vừa đóng vừa có khách, trạng thái có khách vẫn được ưu tiên để không che mất khách đang ngồi.
- Lịch trong tương lai không làm bàn bị chiếm ngay; hiển thị riêng giờ của lịch kế tiếp và liên kết chi tiết theo quyền. Trang Bàn tự lấy trạng thái mới mỗi 15 giây khi đang xem, giữ bộ lọc và có nút **Cập nhật ngay**. Tạm dừng khi tab bị ẩn hoặc đang thao tác bộ lọc/liên kết trong bảng. Nếu mất kết nối, giữ dữ liệu cũ và thông báo; hết phiên hoặc mất quyền thì yêu cầu tải lại trang. Tắt JavaScript vẫn có liên kết tải lại.
- Nhật ký và thay đổi dữ liệu cùng transaction; quyền được kiểm tra ở view/service, POST có CSRF. Django Admin chỉ xem.
- Migration `seating.0002_seed_seating_permissions` cấp quyền riêng cho các nhóm hiện có, không sửa quyền nhân sự/khách hàng.

Từ Giai đoạn 6, ngừng khu vực/bàn, chuyển khu vực hoặc giảm số chỗ còn được kiểm tra với lịch đặt đang hiệu lực. Bàn có khách đã nhận vẫn được bảo vệ dù quá giờ kết thúc dự kiến.

## Đặt bàn

1. Tạo hồ sơ khách (họ tên và số điện thoại) nếu chưa có.
2. Vào **Đặt bàn → Tìm bàn phù hợp**, nhập giờ đến và số khách. Hệ thống tự dùng thời lượng mặc định (ban đầu 120 phút); chỉ mở **Điều chỉnh thời lượng dự kiến** khi cần thay đổi. Chọn bàn, điền số điện thoại khách rồi lưu. Có thể tạo trực tiếp từ **Thêm đặt bàn** hoặc từ trang chi tiết khách hàng.
3. Lịch mới ở trạng thái **Chờ xác nhận**, đã giữ chỗ. Sau khi thống nhất với khách, chọn **Xác nhận đặt bàn**.
4. Chọn **Nhận khách & gọi món** khi khách thực sự đến. Hệ thống chuyển lượt sang **Đang phục vụ**, tự mở đơn và đưa nhân viên thẳng tới màn hình chọn món; không cần xác nhận/mở đơn thêm lần nữa. Có thể nhận sớm trong ngày hẹn nếu bàn trống và không vướng lịch khác. **Hoàn tất** chỉ cho phép khi khách rời bàn và không còn đơn đang phục vụ/chờ thanh toán; hệ thống lưu giờ nhận/giờ rời thực tế.
5. Lịch chưa nhận khách có thể hủy, hoặc đánh dấu **Không đến** từ giờ hẹn trở đi. Hai trạng thái này giải phóng lịch, giữ hồ sơ và nhật ký.

- `/dat-ban/`: tìm theo mã đặt, tên/điện thoại khách, mã bàn; lọc ngày đến, trạng thái, bàn và phân trang.
- Trang **Đặt bàn** mặc định chỉ hiện khách đặt trước (`DB...`). Chọn bộ lọc **Khách trực tiếp** hoặc **Tất cả** khi cần tra cứu lượt `LK...`; trong ca phục vụ, lượt trực tiếp được thao tác chủ yếu tại màn hình **Bàn**.
- `/dat-ban/ban-phu-hop/`: tìm bàn đang sử dụng, đủ chỗ và không trùng lịch. Kết quả tra cứu chưa giữ bàn; hệ thống kiểm tra lại khi lưu.
- `/dat-ban/cau-hinh/`: Quản lí/Superuser cấu hình thời lượng mặc định, từ 1 đến 1440 phút, có lịch sử thay đổi. Chỉ áp dụng cho lịch mới; lịch đã lưu giữ nguyên thời gian dự kiến và thời lượng riêng khi mở form sửa.
- Form không nhập giờ kết thúc. Máy chủ tính giờ đến + thời lượng; JavaScript chỉ giúp xem trước khoảng giờ (kể cả qua nửa đêm). Tắt JavaScript vẫn lưu và kiểm tra lịch bình thường. Nhân viên được chỉnh thời lượng từng lịch mà không được đổi cấu hình chung.
- Mỗi lịch gắn **một khách hàng và một bàn**. Chưa có ghép bàn, đặt nhiều bàn trong một phiếu hoặc thu tiền cọc.
- Quản lí/Superuser và Phục vụ/Thu ngân được xem, tạo, sửa và xử lý trạng thái. Chỉ Quản lí/Superuser xem nhật ký; Bếp/Kho không truy cập.
- Giờ nhập/hiển thị theo Việt Nam. Giờ đến mới phải ở tương lai; kết thúc phải sau giờ đến. Hai lịch liên tiếp được phép nếu giờ kết thúc lịch trước bằng giờ bắt đầu lịch sau.
- Chỉ sửa lịch chờ xác nhận/đã xác nhận. Sửa lịch đã xác nhận đưa về chờ xác nhận lại; form cũ bị từ chối nếu người khác đã sửa hoặc chuyển trạng thái.
- Chỉ nhận khách sau xác nhận và trước giờ kết thúc dự kiến. Nhận sớm chỉ trong cùng ngày hẹn theo giờ Việt Nam, kiểm tra cả khoảng chiếm bàn phát sinh thêm; giữ nguyên giờ hẹn và giờ kết thúc dự kiến. Khách quá giờ dự kiến vẫn giữ trạng thái đã nhận cho đến khi nhân viên hoàn tất; chặn nhận lượt sau nếu bàn còn khách.
- Chi tiết lịch hiển thị giờ nhận khách và giờ khách rời bàn thực tế khi có dữ liệu. Lịch cũ chưa ghi các mốc này để trống, không suy đoán từ giờ dự kiến.
- Danh sách cảnh báo tối đa 10 lượt đang phục vụ quá giờ, kèm liên kết tới lịch kế tiếp cùng bàn nếu có; chi tiết lịch cũng cảnh báo để nhân viên đổi bàn hoặc trao đổi lại giờ đến. Cảnh báo không tự đổi lịch hay hoàn tất lượt khách.
- Không xóa lịch; lưu tên/điện thoại lúc đặt và nhật ký. Khách/bàn có lịch được bảo vệ khỏi xóa vĩnh viễn. Django Admin chỉ tra cứu.
- Chống trùng lịch dùng transaction và khóa PostgreSQL chung với thay đổi danh mục bàn; mọi thao tác ghi phải qua service. Chưa có constraint chống chồng khoảng thời gian cho lệnh SQL ghi trực tiếp ngoài ứng dụng.

### Chuyển bàn đang phục vụ

Tại thẻ bàn có khách, chi tiết lượt khách hoặc chi tiết đơn, chọn **Chuyển bàn**. Hệ thống chỉ hiển thị bàn đang hoạt động, đủ số chỗ, không có khách và không vướng lịch trong thời gian phục vụ còn lại; lượt quá giờ dùng thêm khoảng an toàn 30 phút để tránh chiếm bàn sắp có khách. Khi xác nhận, bàn cũ được giải phóng, bàn mới sáng trạng thái có khách, còn đơn hàng, món, hóa đơn và thanh toán giữ nguyên. Nhật ký lưu rõ bàn cũ, bàn mới, thời gian và nhân viên thực hiện.

Nếu khách đã nhận bàn nhưng đổi ý, chọn **Hủy bàn**, nhập lý do và xác nhận. Hệ thống hủy các món/đơn chưa thanh toán, chuyển lượt khách sang **Đã hủy** và giải phóng bàn trong một thao tác. Không cho hủy khi đã thu một phần hoặc toàn bộ; món đã bắt đầu làm, đã xong hay đã phục vụ chỉ Quản lí được hủy. Nhật ký đơn và lượt khách đều lưu lý do; Báo cáo tính lượt này vào nhóm hủy thay vì hoàn tất.

## Thực đơn

Vào **Thực đơn** hoặc `/thuc-don/`.

1. Quản lí tạo **Nhóm món** (ví dụ Món chính, Đồ uống) và **Đơn vị tính** (Phần, Đĩa, Ly, Chai).
2. Chọn **Thêm món**: mã món, tên, nhóm, đơn vị, giá bán theo đơn vị, trạng thái và mô tả tùy chọn. Mã tự đổi sang chữ hoa và duy nhất; giá từ 1 đến 999.999.999 đồng, không nhập phần lẻ.
3. Phục vụ/Thu ngân tra cứu món, giá và trạng thái; tìm theo mã/tên, lọc nhóm, đơn vị, trạng thái. Danh sách phân trang 20 món.
4. Bếp hoặc Quản lí chọn **Còn / hết món** khi tạm hết hoặc đã có lại. Bếp không sửa giá, danh mục hoặc mở lại món ngừng bán.
5. Quản lí dùng **Sửa món** để đổi giá, thông tin hoặc chọn **Ngừng bán**. Mở bán lại cần nhóm và đơn vị đang sử dụng.

- **Còn món** chỉ áp dụng khi cả nhóm và đơn vị đang hoạt động. Ngừng danh mục khiến món hiển thị **Tạm ngừng theo danh mục**; mở lại danh mục giữ nguyên trạng thái riêng của món, không tự chuyển món hết sang còn.
- Superuser/Quản lí quản lý danh mục, giá và xem nhật ký; Phục vụ/Thu ngân chỉ xem; Bếp xem và đổi còn/hết; Kho chưa có quyền thực đơn. Quyền kiểm tra cả giao diện, GET/POST và service; cờ `is_staff` riêng lẻ không cấp quyền.
- Form cũ bị từ chối nếu dữ liệu đã thay đổi. Thay đổi giá ghi cả trước/sau; thao tác và nhật ký cùng transaction. Không có thao tác xóa vĩnh viễn; danh mục có món được bảo vệ bằng PROTECT. Admin chỉ xem.
- Món hỗ trợ ảnh JPEG, PNG hoặc WebP; máy chủ chuẩn hóa ảnh và tạo thumbnail, có ảnh thay thế khi chưa tải lên. Đơn hàng lưu riêng tên, mã, đơn vị và giá tại lúc thêm món. Chưa có trừ kho, combo, nhiều mức giá hoặc thuế/phí. Trạng thái hết món do nhân viên cập nhật, chưa suy ra từ tồn kho.

## Gọi món, đơn hàng và Bếp

1. Khách đặt trước: chọn **Nhận khách & gọi món**, hệ thống tự nhận bàn, mở đơn và chuyển thẳng tới chọn món. Khách trực tiếp: tại **Bàn → Nhận khách & gọi món** hoặc **Đơn hàng → Khách không đặt trước**; nhập bàn, số khách và thời lượng dự kiến, tên/số điện thoại không bắt buộc. Hệ thống kiểm tra lịch, nhận khách và mở đơn trong cùng luồng.
2. **Thêm món** mở giao diện POS dạng lưới ảnh: tìm tức thời theo tên/mã món, lọc nhóm món, chạm để tích nhiều món, chỉnh số lượng bằng `+ / −` và nhập ghi chú riêng cho từng món. Một lần xác nhận thêm toàn bộ món đã chọn vào đơn. Có thể sửa số lượng/ghi chú khi chưa gửi Bếp; mỗi lần gọi thêm vẫn tạo dòng riêng và giữ giá tại thời điểm gọi, kể cả giá thực đơn thay đổi sau đó.
3. **Gửi Bếp**: xem lại danh sách món rồi xác nhận gửi tất cả dòng chưa gửi. Kiểm tra lại món/danh mục còn phục vụ; nếu một món không hợp lệ thì chưa gửi cả đợt.
4. **Bếp** xem hàng đợi theo giờ gửi, bàn, món, số lượng và ghi chú; chọn **Bắt đầu làm → Đã xong**. Phục vụ tại chi tiết đơn chọn **Đã phục vụ** khi giao cho khách. Trang Bếp/đơn có nút cập nhật thủ công.
5. Sau khi phục vụ xong tất cả món chưa hủy, chuyển đơn **Chờ thanh toán**. Nếu chưa thu khoản nào có thể **Tiếp tục gọi món**; sau khi đã thu một phần, đơn bị khóa gọi thêm để giữ nguyên tổng hóa đơn.
6. Thu ngân hoặc Quản lí thu tiền mặt/chuyển khoản xác nhận tại quầy, hoặc chuyển khách sang cổng VNPAY. Với VNPAY, trình duyệt quay về chỉ hiển thị kết quả; hệ thống chỉ chốt hóa đơn khi nhận IPN có terminal, chữ ký HMAC-SHA512 và số tiền hợp lệ. IPN lặp không cộng doanh thu hay tích lũy lần hai.
7. Chỉ hoàn tất lượt khách và giải phóng bàn khi đơn đã hủy hợp lệ hoặc đơn cùng hóa đơn đều ở trạng thái **Đã thanh toán**.

Tại trang **Bàn**, mỗi bàn có đơn đang hoạt động hiển thị nút **Thanh toán nhanh bàn ...** cho Thu ngân/Quản lí. Hộp thoại cho nhập mã giảm giá, chọn tiền mặt/chuyển khoản và chốt theo đúng bàn; hệ thống từ chối nếu còn món chưa phục vụ. Quản lí tạo mã tại menu **Mã giảm giá**, gồm giảm theo phần trăm hoặc số tiền, đơn tối thiểu, mức giảm tối đa và thời hạn. Ưu đãi hạng được tính trước, mã giảm giá tính trên phần tiền còn lại và cả hai được snapshot riêng trên hóa đơn.

Khi đơn đã chờ thanh toán, Thu ngân/Quản lí có thể chọn **Tách hóa đơn theo món**, nhập số lượng của từng món cần chuyển và tạo hóa đơn con để thu riêng. Có thể tách tiếp, chuyển nhanh giữa các hóa đơn cùng bàn hoặc ghép hóa đơn con chưa phát sinh giao dịch về hóa đơn gốc. Mã giảm giá được xóa khi tách/ghép để từng hóa đơn tính lại minh bạch; ưu đãi hạng khách vẫn được tính trên từng phần. Thanh toán một hóa đơn con không đóng bàn nếu còn hóa đơn khác chưa trả; lượt khách và bàn chỉ hoàn tất sau hóa đơn cuối cùng.

Màn hình **Thu nhiều phương thức** cho ghi nhận nhiều lần thu trên cùng hóa đơn bằng tiền mặt, chuyển khoản, thẻ hoặc phương thức khác. Có nút chia nhanh số tiền còn lại thành 2, 3 hoặc 4 phần. Sau lần thu đầu tiên, hệ thống khóa thay đổi mã giảm giá, tách/ghép và VNPAY để giữ nguyên tổng hóa đơn; chỉ lần thu đủ cuối cùng mới cộng tích lũy khách, hoàn tất đơn và cập nhật trạng thái bàn.

- Quản lí/Superuser có toàn bộ quyền; Phục vụ/Thu ngân mở đơn, gọi/sửa món chưa gửi, gửi Bếp và xác nhận phục vụ. Chỉ Thu ngân/Quản lí có quyền thu tiền. Bếp chỉ xem hàng đợi và cập nhật tiến độ làm món; Kho chưa có quyền đơn hàng.
- Hủy món luôn cần lý do. Phục vụ/Thu ngân hủy món chưa gửi hoặc đã gửi nhưng chưa bắt đầu làm; món đang làm/đã xong/đã phục vụ chỉ Quản lí hủy. Món hủy giữ lịch sử và không cộng tiền tạm tính.
- Chỉ hủy đơn khi không còn món chưa hủy và có lý do; sau hủy đơn mới được hoàn tất lượt khách để giải phóng bàn. Không xóa đơn/món hoặc giả lập thanh toán để bỏ qua bước thu tiền.
- Mỗi lượt có một đơn duy nhất. Lượt khách trực tiếp dùng mã `LK...`, khách đặt trước dùng `DB...`, đơn dùng `DH...`. Không tạo khách hàng giả cho khách vãng lai; nếu cung cấp số điện thoại trùng khách đã lưu thì liên kết hồ sơ đó.
- Form có phiên bản chống ghi đè/gửi lặp; quyền kiểm tra ở giao diện và service. Thay đổi và nhật ký cùng transaction. Khóa theo thứ tự bàn/lịch → thực đơn → tài khoản → bản ghi, giúp việc nhận khách/gọi món đồng bộ với bàn và thực đơn.
- Tên, mã, đơn vị, giá trong dòng món là snapshot; giá sửa sau không đổi món đã gọi. Hóa đơn không gồm món hủy và snapshot cả phần trăm lẫn số tiền ưu đãi thành viên. Mã hóa đơn dựa trên mã bản ghi đơn nên không tranh chấp khi nhiều quầy thu đồng thời. Chưa có tách/ghép đơn, gọi món theo phần nhỏ hoặc hoàn/hủy giao dịch qua giao diện.

### Cấu hình VNPAY

Đăng ký tài khoản thử nghiệm tại cổng VNPAY sandbox, sau đó điền `VNPAY_TMN_CODE`, `VNPAY_HASH_SECRET` và `VNPAY_RETURN_URL` trong `.env`. URL IPN khai báo với VNPAY là `https://<ten-mien>/sales/payment/vnpay/ipn/`; cả Return URL và IPN phải là HTTPS công khai khi kiểm thử từ hệ thống VNPAY. Nếu chưa điền mã terminal/secret, lựa chọn VNPAY được ẩn và thanh toán tại quầy vẫn hoạt động bình thường.

## Báo cáo quản trị

Vào **Báo cáo** hoặc `/bao-cao/`. Chỉ Superuser và nhóm Quản lí được truy cập.

- Chọn khoảng ngày tối đa 367 ngày; mặc định là từ đầu tháng hiện tại đến hôm nay.
- Tổng quan gồm doanh thu hóa đơn đã thanh toán, tiền thực thu theo phiếu thu, giá trị hóa đơn trung bình và công nợ đang chờ thu.
- Báo cáo vận hành gồm doanh thu từng ngày, cơ cấu phương thức thanh toán, lượt đặt bàn, số khách, lượt khách trực tiếp, hủy/không đến và khách hàng mới.
- Bảng xếp hạng hiển thị 10 món bán chạy, 10 bàn tạo doanh thu và 10 hóa đơn gần nhất. Món đã hủy không được tính vào doanh thu món.
- **Xuất CSV** tải danh sách hóa đơn đã chốt trong đúng khoảng ngày đang xem, gồm bàn, khu vực, khách hàng, tổng tiền và phương thức thanh toán.
- “Doanh thu đã chốt” tính theo ngày hóa đơn được thanh toán đủ; “tiền thực thu” tính theo thời điểm từng phiếu thu nên hai số có thể khác nhau nếu một hóa đơn được thu qua nhiều kỳ.

### Thanh toán nhiều bàn

Từ **Bàn → Thanh toán bàn**, Thu ngân hoặc Quản lí có thể lọc theo khu vực, chọn một hay nhiều bàn rồi bấm **Thanh toán & trả bàn**. Hệ thống chỉ cho chọn bàn có đơn còn tiền cần thu và toàn bộ món chưa hủy đã phục vụ xong. Một thao tác sẽ tạo mã thanh toán chung `TT...`, chốt hóa đơn riêng của từng bàn, ghi phiếu thu, hoàn tất lượt khách, giải phóng bàn và cập nhật Báo cáo. Hóa đơn từng bàn vẫn được giữ riêng để không mất lịch sử món, khách và hiệu suất bàn; mã `TT...` liên kết các hóa đơn đã thu cùng lúc. Thanh toán một phần vẫn thực hiện tại chi tiết đơn như trước.

## Kiểm tra và chạy ứng dụng

Từ thư mục gốc, với môi trường ảo đã kích hoạt và `.env` đã điền:

```powershell
python manage.py check
python scripts/run_tests.py
python manage.py runserver 127.0.0.1:8000
```

Mở [http://127.0.0.1:8000/](http://127.0.0.1:8000/) để kiểm tra trang nền tảng. Dừng server bằng `Ctrl+C`.

`check` kiểm tra cấu hình Django. Chạy riêng phần khách hàng và thanh toán bằng `python scripts/run_tests.py apps.customers apps.orders`. Bộ kiểm thử này bao gồm giảm giá theo hạng, thanh toán tại quầy, chữ ký/số tiền IPN VNPAY và chống xử lý trùng. Có thêm 6 kiểm thử logic tự cập nhật bằng Node: `node --test scripts/test_table_live.cjs`; không cần cài thêm thư viện và không thay thế kiểm tra bố cục trên trình duyệt.

`scripts/run_tests.py` tạo database kiểm thử PostgreSQL với tên UUID riêng mỗi lần chạy, chạy toàn bộ migration từ đầu và dọn database khi hoàn tất. Tài khoản PostgreSQL cần quyền tạo database. Lệnh chuẩn `manage.py test` vẫn dùng tên mặc định `test_QLNH_DB`; nếu tên đó tồn tại mà không rõ nguồn gốc, không chấp nhận yêu cầu xóa của test runner.

Thư mục `templates/` chứa template dùng chung; `static/` chứa CSS, JavaScript và ảnh giao diện; `media/` dành cho tệp tải lên. Bootstrap được lưu trong `static/vendor/` để giao diện không phụ thuộc CDN khi chạy. Server phát triển phục vụ static và media khi `DEBUG=True`.

## Git và phạm vi triển khai

Repository Git đã có lịch sử commit. `.gitignore` loại trừ `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `media/`, `.idea/` và `.vscode/` cùng các tệp phát sinh cục bộ.

Phạm vi hiện tại đã gồm **Hóa đơn, Thanh toán và Báo cáo quản trị**. Báo cáo chỉ dùng dữ liệu nghiệp vụ đã được ghi nhận; chưa hiển thị giá vốn, chi phí hay lợi nhuận vì hệ thống chưa có phân hệ Kho/Chi phí. Đề xuất tiếp theo là triển khai Kho, nhập/xuất tồn và chi phí để bổ sung báo cáo lãi gộp.

Lịch sử: [Giai đoạn 1](docs/stage-1-report.md), [Giai đoạn 2](docs/stage-2-report.md), [Giai đoạn 3](docs/stage-3-report.md), [Giai đoạn 4](docs/stage-4-report.md), [Giai đoạn 5](docs/stage-5-report.md), [Giai đoạn 6](docs/stage-6-report.md), [Giai đoạn 7](docs/stage-7-report.md), [Giai đoạn 8](docs/stage-8-report.md), [Giai đoạn 9](docs/stage-9-report.md). Hiện trạng vận hành mới nhất được mô tả trực tiếp trong README này.
