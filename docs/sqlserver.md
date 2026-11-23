# SQL Server trên nhánh feature/sqlserver

Nhánh này dùng SQL Server 2022 cho ứng dụng local. `master` và web Render vẫn dùng PostgreSQL. Snapshot mã local trước khi chuyển là commit `d046ea7`.

## Chạy ứng dụng

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-sqlserver.txt
# Chỉ copy khi chưa có file cấu hình thật:
Copy-Item .env.sqlserver.example .env.sqlserver
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createcachetable qlnh_chatbot_cache
.\.venv\Scripts\python.exe manage.py runserver
```

Trên máy hiện tại đã có `.env.sqlserver`, schema và dữ liệu chuyển đổi; không cần copy lại hay nạp demo. Profile SQL Server là mặc định của manage.py/WSGI/ASGI trên nhánh này. Profile PostgreSQL vẫn có thể chọn bằng `--settings=QLNH.settings`. `.env` cũ tiếp tục cung cấp SECRET_KEY, ZaloPay, chatbot và cấu hình nguồn PostgreSQL.

Cấu hình local: `SQLSERVER_HOST=localhost`, `SQLSERVER_DB=QLNH_SQLSERVER`, Windows Authentication (USER/PASSWORD trống). Python phải chạy bằng tài khoản Windows được cấp quyền SQL Server. Named instance dùng `SERVER\INSTANCE`; SQL Authentication cần điền cả `SQLSERVER_USER` và `SQLSERVER_PASSWORD`.

`mssql-python` đi kèm driver native. `TrustServerCertificate=yes` chỉ dành cho Developer instance local; máy chủ thật cần chứng chỉ tin cậy và `Encrypt=yes`. Nhánh này chưa triển khai SQL Server lên Render. Để triển khai cần một endpoint SQL Server/Azure SQL truy cập được từ hosting và kiểm chứng riêng môi trường đó.

## Chuyển dữ liệu

Tạo database SQL Server đích mới, migrate, rồi:

```powershell
.\.venv\Scripts\python.exe manage.py copy_postgres_to_sqlserver --confirm-target QLNH_SQLSERVER
```

Lệnh chỉ chấp nhận nguồn PostgreSQL local và đích chưa có dữ liệu nghiệp vụ. Nguồn được đọc bằng REPEATABLE READ/READ ONLY. Lệnh giữ PK, quan hệ, mật khẩu hash, UUID, tiền và timestamp đến microsecond. Nếu FK/CHECK, số dòng hoặc SHA256 toàn bộ bản ghi không khớp, giao dịch đích rollback. Fixture tạm tự xóa; báo cáo chỉ chứa số dòng/hash tại `artifacts/sqlserver/copy-report.json`. Không chạy lại trên database đang sử dụng; lệnh từ chối ghi đè dữ liệu nghiệp vụ.

## Tương thích

- Khóa giao dịch dùng `sp_getapplock` trên SQL Server, giữ thứ tự khóa và tự nhả khi commit/rollback. Khóa phiên chatbot cũng được hỗ trợ; PostgreSQL vẫn dùng advisory lock.
- Khóa hàng được giữ; tùy chọn `of` chỉ gửi tới backend có hỗ trợ.
- Ba regex kiểm tra dữ liệu của dự án được chuyển thành CHECK T-SQL, gồm whitespace Unicode, mã và SĐT. Pattern khác bị từ chối rõ ràng. Không bật CLR hay bỏ CHECK.
- Unique `LOWER(name)` dùng computed column PERSISTED và UNIQUE INDEX. Điều kiện chỉ mục `NOT(x=y)` chuyển thành `x<>y`.
- Giữ toàn bộ lịch sử migration; không fake migration hay bỏ FK.

Các script ERD/tài liệu PostgreSQL và lệnh reset demo PostgreSQL vẫn dành cho PostgreSQL. Tài liệu đồ án/Word hiện có chưa được đổi nội dung sang SQL Server.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
# Đối chiếu PostgreSQL:
$env:DJANGO_SETTINGS_MODULE='QLNH.test_settings'
.\.venv\Scripts\python.exe scripts/run_tests.py
Remove-Item Env:DJANGO_SETTINGS_MODULE
```

Mỗi lượt tạo database `test_qlnh_<uuid>` riêng và tự xóa sau khi xong. `scripts/run_sqlserver_tests.py` luôn chọn SQL Server dù terminal còn cấu hình settings PostgreSQL.

Đã kiểm chứng ngày 23/11/2026: 719 test SQL Server qua, 408 test đối chiếu PostgreSQL qua (4 test riêng SQL Server được bỏ qua), thêm 6 kiểm tra riêng về CHECK/UNIQUE, session lock và microsecond qua. Kiểm tra lại copy từ database trống đối chiếu toàn bộ nội dung và chặn lần ghi đè thứ hai đều qua. Web SQL Server local trả 200 cho trang chủ, thực đơn, đặt bàn, tra cứu, đăng nhập và static. Django check, migration consistency, collectstatic và pip check đều qua.

## Sao lưu

```powershell
.\.venv\Scripts\python.exe manage.py backup_database --directory D:/DOANTOTNGHIEP/artifacts/backups/sqlserver --verify-restore
```

SQL Server tạo `.bak` COPY_ONLY/CHECKSUM, kiểm tra VERIFYONLY, lưu SHA256 và thử RESTORE vào database UUID riêng. Kiểm chứng schema xong chỉ xóa database thử của lượt đó. SQL Server service và ứng dụng cần cùng truy cập được thư mục backup; máy chủ SQL Server ở nơi khác cần cấu hình đường dẫn dùng chung thích hợp.

Nguồn: [Microsoft mssql-django](https://github.com/microsoft/mssql-django), [sp_getapplock](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql).
