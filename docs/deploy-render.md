# Deploy Cơm Quê lên Render với SQL Server SmarterASP.NET

Service `qlnh-web` dùng nhánh `master` của `lecongdatd36/DATN`, runtime Python 3, region Oregon. Bản tích hợp này gồm cấu hình SQL Server 2022 SmarterASP.NET, backend `core/db/backends/sqlserver`, migration và các sửa đổi khóa dữ liệu. Phải deploy toàn bộ bản tích hợp, không chỉ chép một file settings.

Mã nguồn, migration, template và static phải cùng phiên bản. Không đưa `.env`, database local, ảnh người dùng, mẫu khuôn mặt, file Word cá nhân hoặc artifact kiểm thử lên Git. Mật khẩu SQL Server chỉ nhập trong **Render → qlnh-web → Environment**.

## Cấu hình service hiện có

Trong Render Dashboard, mở **Web Service đang chạy**:

| Mục | Giá trị |
| --- | --- |
| Repository | `lecongdatd36/DATN` |
| Service / Region | `qlnh-web` / Oregon |
| Branch | `master` |
| Runtime | Python |
| Build Command | `bash build.sh` |
| Start Command | `bash start.sh` |
| Python | `.python-version` chọn nhánh 3.12; nếu service có `PYTHON_VERSION` thì biến đó được ưu tiên, cần dùng bản 3.12.x phù hợp |

`start.sh` chạy Gunicorn, bind vào `$PORT`, mặc định 2 worker, 2 thread/worker và timeout 120 giây; có thể chỉnh `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`. Không dùng Django `runserver` trên hosting. Service Python không sử dụng Dockerfile.

Auto-Deploy phải theo nhánh `master`; nếu tắt thì dùng **Manual Deploy → Deploy latest commit** sau khi push. Đối chiếu commit trong log Render và đợi service Live trước khi kết luận deploy thành công. `render.yaml` mô tả cùng cấu hình cho Blueprint, không tự thay đổi một service đã tạo thủ công: cập nhật service hiện tại trong Dashboard, không tạo service trùng tên.

Nguồn: [Render Django](https://render.com/docs/deploy-django), [Auto-Deploy](https://render.com/docs/deploys), [Python version](https://render.com/docs/python-version).

## Biến môi trường

Đặt giá trị thật trong **Environment** của Render. `.env.example` chỉ là mẫu, không tự đồng bộ biến từ máy local lên Render.

| Biến | Cách cấu hình |
| --- | --- |
| `SECRET_KEY` | Giữ khóa bí mật ổn định của môi trường đang chạy |
| `DJANGO_SETTINGS_MODULE` | `QLNH.sqlserver_settings` |
| `SQLSERVER_HOST` | `sql5106.site4now.net` |
| `SQLSERVER_PORT` | `1433` |
| `SQLSERVER_DB` | `db_ad182b_comque` |
| `SQLSERVER_USER` | `db_ad182b_comque_admin` |
| `SQLSERVER_PASSWORD` | Nhập mật khẩu tài khoản SQL Server trực tiếp vào Render; không ghi vào repo |
| `SQLSERVER_EXTRA_PARAMS` | `Encrypt=yes;TrustServerCertificate=no` |
| `SQLSERVER_CONNECTION_TIMEOUT` | `15` (giây, mặc định) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Hostname website, không có `https://`; hostname Render được code tự thêm |
| `CSRF_TRUSTED_ORIGINS` | Origin HTTPS website; thêm custom domain nếu có, phân cách bằng dấu phẩy |
| `PUBLIC_BASE_URL` | URL HTTPS website; để trống dùng `RENDER_EXTERNAL_URL` của Render; không dùng localhost hoặc IP LAN |
| `CLOUDINARY_URL` | Cấu hình Cloudinary cho ảnh tải lên; hoặc giữ bộ `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` hiện có |
| `ZALOPAY_APP_ID`, `ZALOPAY_KEY1`, `ZALOPAY_KEY2` | Bộ thông tin **Sandbox** của cùng một ứng dụng |
| `ZALOPAY_ENDPOINT` | `https://sb-openapi.zalopay.vn/v2/create` |
| `ZALOPAY_CALLBACK_URL` | `https://<hostname-website>/payments/zalopay/callback/`; để trống dùng origin request, URL phải truy cập được từ ZaloPay |
| `ENABLE_FACE_ATTENDANCE` | `0` nếu chưa bật nhận diện; `1` để build cài requirements-attendance và tải mô hình đã kiểm checksum |

Không cần `DATABASE_URL` hoặc các biến `DB_*` của PostgreSQL. Có thể xóa chúng khỏi service khi chuyển xong; profile SQL Server trên Render bỏ qua cả PostgreSQL và các file `.env`/`.env.sqlserver` local. Render tự đặt `RENDER=true`, `RENDER_EXTERNAL_HOSTNAME` và `RENDER_EXTERNAL_URL`; giữ các biến này do nền tảng quản lý. Không sao chép `.env` local lên hosting.

`requirements.txt` đã gồm `mssql-django==2.0.0` và `mssql-python==1.18.0`; `requirements-sqlserver.txt` dùng lại danh sách này. Vì vậy Build Command cũ bắt đầu bằng `pip install -r requirements.txt` vẫn cài đủ driver SQL Server. Lệnh khuyến nghị là `bash build.sh` để có thêm biên dịch bản dịch và preflight kết nối. Driver native được cài qua dependencies Python, không dùng cấu hình `pyodbc` yêu cầu tự cài ODBC Driver Manager bằng `apt` trong Build Command. Microsoft liệt kê thư viện Linux cần thiết là `libltdl7`, `libkrb5-3`, `libgssapi-krb5-2`; nếu log báo thiếu thư viện native, cần bổ sung chúng trong một runtime Docker thay vì bỏ mã hóa kết nối. Xem [Microsoft mssql-python](https://github.com/microsoft/mssql-python), [Render native runtime](https://render.com/docs/native-runtimes).

Thanh toán mới dùng ZaloPay; VNPAY đã bỏ khỏi giao diện đặt cọc và POS. Giữ khóa VNPAY cũ nếu còn cần xác minh IPN/return của giao dịch đã tạo trước đó. Giữ cấu hình chatbot, dự báo và thông tin nhà hàng hiện có nếu dùng. Thanh toán ZaloPay vẫn là Sandbox. Callback/Query đã xác thực mới xác nhận thu tiền; redirect chỉ đưa khách về màn trạng thái.

Nếu trang hiển thị **ZaloPay (chưa cấu hình)**, kiểm tra Environment của đúng Web Service: `ZALOPAY_APP_ID` phải là số nguyên dương, `ZALOPAY_KEY1` và `ZALOPAY_KEY2` đều có giá trị, endpoint đúng Sandbox v2 như bảng trên. Đây là kiểm tra cấu hình nội bộ, chưa gọi API ZaloPay; không phải lỗi callback hay giao dịch bị từ chối. Các giá trị trong `.env` local không được Git/deploy chuyển lên Render. Lưu các biến trên Render rồi chờ service khởi động lại với cấu hình mới. Không đưa khóa vào Git hoặc gửi trong ảnh chụp/log.

Nguồn: [Render Environment](https://render.com/docs/configure-environment-variables). Chi tiết thanh toán trong [ZaloPay Sandbox](zalopay-sandbox.md).

## Database và dữ liệu

Sao lưu database hosting theo quy trình đang dùng trước đợt migration. `build.sh` cài `requirements-sqlserver.txt`, cài bộ nhận diện nếu bật, rồi chạy:

```sh
python scripts/compile_translations.py
python manage.py check
python manage.py collectstatic --no-input
python manage.py check_sqlserver_connection
python manage.py migrate --no-input
python manage.py createcachetable qlnh_chatbot_cache
```

Lệnh `check_sqlserver_connection` chỉ đọc tên database và phiên bản SQL Server; nếu không kết nối được hoặc database không khớp, build dừng trước migration. Lệnh không in mật khẩu hoặc chuỗi kết nối. `migrate` tạo/cập nhật schema trong database được cấu hình, không tự chuyển khách hàng, tài khoản, món ăn hay đơn hàng từ PostgreSQL/local lên SmarterASP.NET. Không chạy `flush`, nạp fixture mẫu hoặc reset database để deploy.

Nếu database SmarterASP.NET còn trống, sau build cần chuyển dữ liệu bằng quy trình riêng hoặc tạo tài khoản quản trị bằng `python manage.py createsuperuser` trong Render Shell. Lệnh copy PostgreSQL local trong [hướng dẫn SQL Server](sqlserver.md) chỉ dùng khi cấu hình nguồn local và database đích chưa có dữ liệu nghiệp vụ; không chạy trên service đang phục vụ khách. Sao lưu SQL Server shared hosting dùng cơ chế backup của SmarterASP.NET; đường dẫn `.bak` local không tự truy cập được trên máy chủ hosting.

Các migration của đặt bàn online, món đặt trước và chấm công được giữ nguyên lịch sử. Chạy toàn bộ migration còn thiếu, không dùng `--fake` để vượt lỗi.

Nhánh giao diện/giỏ/combo bổ sung `menu/0006` và `reservations/0005`, font cùng asset banner trong `static/customer/`. Chạy migrate/collectstatic theo `build.sh` khi triển khai nhánh này. Combo là dữ liệu riêng từng môi trường: quản lý tạo tại `/thuc-don/combo/` hoặc chạy `python manage.py seed_combos --actor <username-quan-ly>` để thêm ba combo khởi tạo nếu thực đơn có đủ món; lệnh giữ nguyên mã combo đã tồn tại. Xem [giỏ và combo](homepage-refresh.md).

Chấm công một nút tự xác định vào/ra bổ sung migration `workforce/0003`; `migrate` giữ nguyên công và mẫu khuôn mặt cũ. Trang chấm công chung dùng bố cục camera / kết quả mới, bỏ GPS, chặn chấm lặp 60 giây. Dashboard quản lý `/tai-khoan/` và theme dùng static mới, không thêm biến môi trường. Xem [chấm công](attendance-kiosk.md) và [dashboard](management-dashboard.md).

Tiếng Anh bổ sung `menu/0007`, nút VI / EN và catalog `locale/en/LC_MESSAGES/`. Build tự biên dịch `.po` thành `.mo`; không cần biến môi trường mới. Sau migrate, quản lý điền tên/giới thiệu tiếng Anh trong catalog hoặc chạy `python manage.py seed_menu_english` để điền những ô còn trống của các món/combo đã biết. Lệnh giữ nguyên bản dịch tùy chỉnh, tên Việt, giá và dữ liệu giao dịch. Kiểm tra chuyển VI / EN ở trang chủ, `/menu/`, giỏ món và form đặt bàn sau deploy.

Ảnh trong `media/` local và dữ liệu đăng ký khuôn mặt không đi theo Git. Dùng dữ liệu/Cloudinary của đúng môi trường. Sau deploy, quản lý kiểm tra chính sách cọc, món được phép chuẩn bị trước, ca làm và cấu hình điểm chấm công; các cấu hình này lưu trong database của từng môi trường.

Nếu bật nhận diện, inference chạy trên server Render và cần đủ RAM/CPU. Chạy thử với tài khoản/điểm chấm công của môi trường kiểm thử trước; việc cài mô hình không tự đăng ký khuôn mặt nhân viên. Xem [chấm công](attendance-kiosk.md).

## Tác vụ định kỳ

Các lệnh sau cần chạy trên cùng database và cùng cấu hình với web service:

```sh
python manage.py expire_reservation_holds
python manage.py query_pending_zalopay
```

Có thể cấu hình scheduler mỗi phút để giải phóng giữ chỗ hết hạn và truy vấn giao dịch Sandbox chưa nhận callback. Lệnh truy vấn có giới hạn tần suất và idempotency. Repo không tự tạo hoặc thanh toán dịch vụ cron. Giữ tác vụ `expire_bookings` hiện có nếu môi trường đã cấu hình.

## Kiểm tra sau deploy

1. Log build có `SQL Server 16...: database db_ad182b_comque; connection OK (read-only).`, collectstatic và migration thành công; commit deploy trùng commit vừa push. Kiểm tra `python manage.py check` trong môi trường nếu có Shell.
2. Trang chủ, `/reservations/online/`, `/reservations/online/tra-cuu/` và static tải được, không lỗi manifest/CSRF. Truy cập màn quản lý/bếp bằng tài khoản có quyền.
3. Tạo lịch kiểm thử riêng, chọn giờ đủ xa để giữ chỗ còn ít nhất 5 phút khi yêu cầu ZaloPay. Xác nhận đúng số tiền, nhãn Sandbox, return về hostname Render, callback hoặc Query cập nhật cọc một lần.
4. Đối chiếu món trên hồ sơ và màn món đặt trước. Lịch TABLE hiển thị chờ khách đến; lịch READY có mốc chuẩn bị và nút bếp theo giờ đã chốt. Tra cứu chi tiết cần phiên khách sở hữu liên kết hoặc nhân viên có quyền; mã/SĐT trên thiết bị lạ chỉ hiện trạng thái.
5. Theo dõi log callback, giao dịch pending/review và lỗi server. Chưa kiểm tra trên hosting thì chỉ báo đã push mã nguồn, chưa xác nhận môi trường vận hành đầy đủ.

## Khi kết nối SQL Server thất bại

- Kiểm tra đúng `DJANGO_SETTINGS_MODULE`, host, port, tên database, user và mật khẩu trong Environment của `qlnh-web`. Nhập mật khẩu nguyên văn, không URL-encode và không đặt thêm dấu nháy.
- SSMS kết nối được từ máy cá nhân chưa xác nhận đường mạng từ Oregon. Nếu tài khoản hosting giới hạn IP nguồn, cho phép các outbound IP của service Render trong phần cấu hình database/firewall tương ứng.
- Giữ `Encrypt=yes;TrustServerCertificate=no`. Nếu gặp lỗi chứng chỉ, xác nhận hostname và chuỗi CA với SmarterASP.NET; không tự chuyển sang `Encrypt=no`.
- `Encryption not supported on the client` có thể do môi trường Windows bị hạn chế. Kiểm tra driver/quyền chạy ở máy đó và đối chiếu lại bằng `check_sqlserver_connection` trên Render trước khi kết luận máy chủ SQL bị lỗi.

Kiểm chứng ngày 25/11/2026: lệnh preflight từ máy phát triển, ngoài sandbox, kết nối mã hóa và xác thực chứng chỉ thành công tới `db_ad182b_comque`, trả phiên bản `16.0.4145.4` (SQL Server 2022). Sau khi xác nhận database đích trống, đã chạy đủ 100 migration và chuyển 2.092 bản ghi thuộc 74 bảng từ SQL Server local `QLNH_SQLSERVER`; số dòng và SHA-256 toàn bộ nội dung khớp bản chụp nguồn trước khi commit. Bảng cache dùng chung cũng đã được tạo. Nguồn local chỉ được đọc. Báo cáo tại `artifacts/sqlserver/smarterasp-copy-report.json` và bản chụp dữ liệu nguồn được giữ local trong thư mục đã Git-ignore.

Database hosting hiện có 7 tài khoản, 7 nhân viên, 15 khách hàng, 17 món ăn, 49 đơn hàng và 35 hóa đơn. Dùng tài khoản/mật khẩu cũ; không cần tạo quản trị viên mới cho bản sao này. Các lần deploy sau chỉ chạy migration còn thiếu, không chạy lại lệnh copy hoặc nạp fixture. Việc chuyển dữ liệu từ máy phát triển chưa xác nhận build/deploy web từ Render.

Kiểm tra mã nguồn cùng đợt: 725 kiểm thử hồi quy SQL Server local và 6 kiểm thử cấu hình deploy đều qua; Django check, pip check, cú pháp Bash và collectstatic production đều qua (215 tệp static, có manifest). Kiểm tra `--deploy` còn hai khuyến nghị HSTS về subdomain/preload, cần đánh giá theo tên miền thực tế trước khi bật.
