# Báo cáo trạng thái hệ thống QLNH

**Thời điểm ghi nhận:** 02/10/2026  
**Loại ứng dụng:** Hệ thống quản lý nhà hàng dạng Django monolith  
**Ngôn ngữ giao diện:** Tiếng Việt

## 1. Tổng quan

QLNH là hệ thống quản lý hoạt động nhà hàng, được xây dựng trên Django và PostgreSQL. Hệ thống có hai nhóm sử dụng chính:

- Nhân viên/quản lý: quản lý tài khoản, nhân sự, khách hàng, bàn, thực đơn, đơn hàng, bếp, kho và báo cáo.
- Khách hàng: xem trang chủ, xem thực đơn, xem chi tiết món, đặt bàn, tra cứu đặt bàn và gọi món thông qua QR tại bàn.

Kiến trúc hiện tại là Django monolith, tổ chức theo các app nghiệp vụ. Mỗi app thường tách model, form, selector, service, permission, view, URL và test.

Các file nền tảng chính là [manage.py](../manage.py), [QLNH/settings.py](../QLNH/settings.py), [QLNH/urls.py](../QLNH/urls.py), [README.md](../README.md) và thư mục [apps](../apps).

## 2. Công nghệ đang sử dụng

- Python 3.12.
- Django 5.2.17.
- PostgreSQL với `psycopg[binary]`.
- `python-dotenv` để đọc cấu hình `.env`.
- Pillow để xử lý ảnh món ăn.
- `qrcode[pil]` để tạo mã QR.
- Bootstrap được lưu cục bộ trong `static/vendor`.
- Django Templates, CSS và JavaScript cho giao diện.
- Cấu hình ngôn ngữ tiếng Việt và múi giờ `Asia/Ho_Chi_Minh`.

## 3. Chức năng đã hoàn thành

### 3.1. Tài khoản và nhân sự

Hệ thống đã có:

- Tài khoản người dùng tùy chỉnh.
- Đăng nhập, đăng xuất, đổi mật khẩu và đặt lại mật khẩu.
- Khóa/mở khóa tài khoản và vô hiệu hóa các phiên đăng nhập cũ.
- Hồ sơ nhân viên, mã nhân viên, ảnh đại diện, điện thoại, ngày sinh, giới tính và trạng thái làm việc.
- Chức vụ và nhóm quyền: quản lý, phục vụ, thu ngân, bếp và kho.
- Nhật ký thao tác nhân sự.
- Cơ chế bảo vệ tài khoản superuser.

Các phần này nằm chủ yếu trong [apps/accounts](../apps/accounts), [apps/employees](../apps/employees) và [core/permissions.py](../core/permissions.py).

Chưa có chấm công, xếp ca, tính lương hoặc quản lý hợp đồng lao động.

### 3.2. Khách hàng và thành viên

Đã có:

- Tạo, sửa, xem và tìm kiếm khách hàng.
- Mã khách tự sinh dạng `KH000001`.
- Chuẩn hóa và chống trùng số điện thoại.
- Hạng thành viên và mức giảm giá theo hạng.
- Theo dõi tổng chi tiêu và lịch sử hóa đơn.
- Phân trang và nhật ký thay đổi.

Chưa có tài khoản đăng nhập riêng cho khách, xác minh OTP, email, địa chỉ hoặc chương trình tích điểm độc lập.

### 3.3. Khu vực, bàn và QR

Đã có:

- Quản lý khu vực và bàn.
- Mã bàn, sức chứa và trạng thái sử dụng.
- QR token cho từng bàn.
- Trạng thái bàn: trống, giữ chỗ, đang phục vụ, cần dọn.
- Trang theo dõi bàn có cập nhật định kỳ.
- Chuyển bàn và hoàn tất dọn bàn.
- Nhật ký thay đổi bàn.
- QR menu riêng theo từng bàn.

Chưa có sơ đồ mặt bằng trực quan, ghép bàn hoặc tách bàn vật lý. Cập nhật trạng thái hiện chủ yếu dùng polling, chưa dùng WebSocket.

### 3.4. Đặt bàn

Đã có:

- Đặt bàn theo khách, số người, thời gian đến và thời lượng.
- Kiểm tra và chống trùng lịch bằng transaction và khóa dữ liệu.
- Các trạng thái: chờ xác nhận, đã xác nhận, đang phục vụ, hoàn tất, hủy và không đến.
- Nhận khách sớm trong ngày đặt.
- Hỗ trợ khách walk-in.
- Chuyển bàn và hủy lượt đang phục vụ.
- Lưu snapshot tên và số điện thoại khách.
- Trang công khai để tạo và tra cứu đặt bàn.

Chưa có tiền cọc, gửi SMS/email, đặt nhiều bàn trong một lần hoặc tác vụ nền tự động xử lý booking quá hạn.

### 3.5. Thực đơn và món ăn

Đã có:

- Quản lý nhóm món và đơn vị tính.
- Thêm, sửa và xem món ăn.
- Mã món, giá bán, mô tả và trạng thái còn món/hết món/ngừng bán.
- Upload ảnh món và tạo thumbnail.
- Tìm kiếm, lọc món và xem chi tiết món.
- Phân quyền quản lý menu và quyền cập nhật trạng thái còn/hết của bếp.
- Lưu nhật ký thay đổi.
- Kiểm tra trạng thái hoạt động của món, nhóm món và đơn vị tính.

Trang khách hàng tại [templates/home.html](../templates/home.html) và [templates/customer](../templates/customer) đã có:

- Trang chủ công khai.
- Khu vực món nổi bật lấy dữ liệu từ database.
- Hero image lấy ảnh món từ database và tự chuyển ảnh mỗi 5 giây.
- Các nút danh mục có thể nhấn để lọc thực đơn.
- Hiển thị ảnh placeholder nếu chưa có ảnh món.

Chưa có combo, nhiều bảng giá, thuế/phí hoặc tự động đồng bộ trạng thái hết món hoàn toàn theo tồn kho.

### 3.6. Đơn hàng, POS và bếp

Đã có:

- Mở đơn cho khách đặt bàn hoặc khách walk-in.
- Gọi món nhiều đợt, ghi chú món và gán vị trí khách.
- Lưu snapshot tên món, đơn vị và giá tại thời điểm gọi.
- Gửi món xuống bếp.
- Quy trình bếp `PENDING -> COOKING -> READY`.
- Phục vụ xác nhận món đã phục vụ.
- Hủy món có lý do và kiểm tra quyền theo trạng thái.
- Hủy toàn đơn trong điều kiện hợp lệ.
- Yêu cầu thanh toán.
- Hóa đơn, phiếu thu và thanh toán nhiều lần.
- Thanh toán tiền mặt, thẻ, chuyển khoản và phương thức khác.
- Tách hóa đơn theo món và ghép hóa đơn chưa thanh toán.
- Khuyến mãi theo phần trăm hoặc số tiền.
- Giảm giá theo hạng thành viên.
- Thanh toán nhiều bàn với mã giao dịch chung.
- In phiếu tạm tính và hóa đơn.
- Tích hợp VNPAY sandbox với HMAC-SHA512, IPN server-to-server và chống xử lý lặp.
- QR request để khách gửi yêu cầu gọi món, nhân viên xác nhận hoặc từ chối.

Chưa có hoàn tiền, chargeback, thuế/phí đầy đủ, thông báo realtime cho bếp hoặc chia một dòng món thành nhiều đợt phục vụ độc lập.

### 3.7. Kho và nguyên liệu

Đã có:

- Quản lý nhà cung cấp, nguyên liệu và tồn kho.
- Tính giá vốn bình quân gia quyền.
- Công thức món.
- Nhập hàng, xuất kho, điều chỉnh, bán hàng, hoàn kho, kiểm kê và hao hụt.
- Phiếu nhập ở trạng thái nháp, đã nhận hoặc đã hủy.
- Tự động trừ kho khi gửi món xuống bếp.
- Hoàn kho khi hủy món trước chế biến.
- Cảnh báo nguyên liệu sắp hết.
- Cảnh báo món thiếu công thức.
- Tính số phần có thể chế biến.
- Management command tạo dữ liệu kho mẫu.

Chưa có quản lý lô hàng, hạn sử dụng, truy xuất batch, workflow phê duyệt nhiều cấp hoặc lịch sử giá nhập chi tiết theo từng nhà cung cấp.

### 3.8. Báo cáo

Khu vực báo cáo tại `/bao-cao/` đã có:

- Doanh thu hóa đơn đã thanh toán.
- Tiền thực thu theo phiếu thu.
- Giá vốn, lãi gộp và biên lợi nhuận.
- Công nợ chưa thu.
- Doanh thu theo ngày.
- Cơ cấu phương thức thanh toán.
- Số lượng booking, khách, walk-in, hủy và không đến.
- Khách hàng mới.
- Top 10 món bán chạy.
- Top 10 bàn có doanh thu cao.
- Danh sách hóa đơn gần nhất.
- Xuất dữ liệu doanh thu dạng CSV.

Chưa có dashboard biểu đồ chuyên sâu, báo cáo theo ca/nhân viên/bếp, dự báo doanh thu hoặc phân tích AI.

### 3.9. Customer portal

Các route công khai chính:

- `/`: trang chủ khách hàng.
- `/menu/`: thực đơn.
- `/menu/<id>/`: chi tiết món.
- `/reservations/`: tạo và tra cứu đặt bàn.
- `/menu/table/<token>/`: QR menu theo bàn.
- `/menu/table/<token>/request/`: gửi yêu cầu gọi món.
- `/menu/table/<token>/status/`: theo dõi yêu cầu QR.

Customer portal đã hỗ trợ tìm kiếm/lọc món, xem chi tiết, đặt bàn, tra cứu trạng thái đặt bàn, QR menu và gửi yêu cầu gọi món.

Chưa có tài khoản khách, thanh toán online trực tiếp từ portal hoặc thông báo SMS/email/push.

## 4. Phân quyền và an toàn nghiệp vụ

Hệ thống đã áp dụng:

- Kiểm tra quyền ở view và service.
- Đọc lại actor từ database trước nghiệp vụ quan trọng.
- Từ chối tài khoản inactive.
- Không tự cấp quyền nghiệp vụ chỉ vì tài khoản có `is_staff`.
- CSRF cho các request POST.
- GET confirmation không làm thay đổi dữ liệu.
- Audit log trong nhiều nghiệp vụ ghi dữ liệu.
- Transaction, khóa dữ liệu và revision để chống ghi đè cạnh tranh.
- `PROTECT`, `SET_NULL` và snapshot để bảo vệ lịch sử nghiệp vụ.

Các điểm cần tăng cường khi triển khai thật:

- Rate limiting cho đăng nhập, đặt bàn công khai và QR endpoint.
- HSTS, secure cookie, CSP và cấu hình trusted proxy.
- Audit tập trung cho toàn bộ thao tác kho và báo cáo.
- Giới hạn việc ghi ORM trực tiếp bỏ qua service nghiệp vụ.

## 5. Kiểm thử

Các app có thư mục test gồm accounts, employees, customers, seating, bookings, menu, orders, inventory và customer portal.

Test hiện bao phủ:

- Ma trận quyền theo vai trò.
- CSRF và vô hiệu hóa session.
- Optimistic revision.
- Tranh chấp đặt bàn và concurrency PostgreSQL.
- Order, POS, bếp, thanh toán, giảm giá và VNPAY.
- QR request.
- Trừ/hoàn kho.
- JavaScript cập nhật trạng thái bàn qua [scripts/test_table_live.cjs](../scripts/test_table_live.cjs).

Trong lần kiểm tra gần đây, customer portal đã chạy đạt **16/16 test**; Django system check không phát hiện lỗi. Con số trong các báo cáo stage cũ là kết quả lịch sử, không nên xem là kết quả chạy mới nhất.

Cần lưu ý script test mặc định chưa bao gồm đầy đủ inventory và reports trong mọi lần chạy. Các giao diện cũng cần được kiểm thử trực tiếp trên nhiều trình duyệt và kích thước màn hình.

## 6. Dữ liệu, backup và triển khai

Đã có:

- Migration cho các app.
- Cấu hình WSGI/ASGI.
- `.env.example` và cấu hình qua biến môi trường.
- Static/media configuration.
- PostgreSQL test database riêng.
- Management command tạo dữ liệu mẫu.
- Fixture tại [backups/pre_reset_20261001.json](../backups/pre_reset_20261001.json).

Fixture trên là dữ liệu Django dạng JSON, không phải backup PostgreSQL vật lý. Hiện chưa thấy backup PostgreSQL tự động, backup media, lịch backup định kỳ, backup off-site hoặc quy trình restore được kiểm thử.

Cũng chưa thấy đầy đủ Dockerfile, CI/CD, production settings tách biệt, Gunicorn/Uvicorn/Nginx, health check, monitoring, metrics, object storage cho media, quy trình deploy/rollback và HTTPS production.

## 7. Danh sách route nghiệp vụ chính

- `/tai-khoan/`: tài khoản và đăng nhập.
- `/nhan-vien/`: nhân sự.
- `/khach-hang/`: khách hàng và thành viên.
- `/ban/`: khu vực, bàn và QR bàn.
- `/dat-ban/`: booking và cấu hình thời lượng.
- `/thuc-don/`: nhóm món, đơn vị và món ăn.
- `/don-hang/`: đơn hàng, hóa đơn và thanh toán.
- `/sales/`: POS, thanh toán nhanh, VNPAY, khuyến mãi và QR request.
- `/staff/kitchen/`: màn hình bếp.
- `/staff/inventory/`: kho.
- `/bao-cao/`: báo cáo.
- `/admin/`: Django Admin tùy chỉnh.

## 8. Kết luận

Ở thời điểm lập báo cáo, QLNH đã vượt qua mức CRUD cơ bản và có một quy trình nhà hàng tương đối hoàn chỉnh từ đặt bàn, mở bàn, gọi món, chế biến, thanh toán, trừ kho đến báo cáo. Phần customer portal cũng đã có luồng công khai riêng và giao diện trang chủ/menu.

Các khoảng trống quan trọng nhất trước khi xem là sản phẩm production-ready:

1. Hoàn thiện triển khai production và CI/CD.
2. Thiết lập backup/restore tự động cho database và media.
3. Kiểm thử giao diện bằng browser thật trên desktop/mobile.
4. Bổ sung realtime notification cho bếp và nhân viên.
5. Bổ sung refund, thuế/phí, tiền cọc và ghép/tách bàn.
6. Tăng cường security hardening và rate limiting.
7. Xác định rõ phạm vi AI, vì hiện source chưa có pipeline AI thực tế dù một số mô tả dự án có nhắc đến AI.
