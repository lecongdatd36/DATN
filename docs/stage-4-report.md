# Giai đoạn 4 — Khách hàng

Ngày cập nhật: 20/09/2026.

Báo cáo lịch sử Giai đoạn 4. Khu vực và Bàn đã triển khai tại [Giai đoạn 5](stage-5-report.md).

## Nghiệp vụ đã triển khai

- Hồ sơ khách hàng chỉ nhập họ tên và số điện thoại. Không có email, địa chỉ, ghi chú, mật khẩu hoặc tài khoản đăng nhập cho khách.
- Mã khách tự sinh theo khóa chính, hiển thị dạng `KH000001`; ngày tạo và cập nhật tự động.
- Danh sách, chi tiết, tìm kiếm mã/tên/điện thoại, phân trang 20 dòng, thêm/sửa và xóa có xác nhận.
- Chuẩn hóa số điện thoại về đầu `0`, dài 10–11 chữ số; chấp nhận đầu `+84` và các ký tự phân cách thông dụng. Đây là kiểm tra định dạng, chưa có xác minh số điện thoại bằng OTP.
- Một số điện thoại tương ứng một hồ sơ. Ràng buộc unique và định dạng ở database bảo vệ cả trường hợp nhiều người tạo cùng lúc.
- Họ tên bắt buộc và thu gọn khoảng trắng. Form báo lỗi tại trường; dữ liệu tên hiển thị qua cơ chế escape của template.
- Ghi nhật ký thêm/sửa/xóa trong cùng transaction. Không tạo log khi lưu thông tin không đổi. Nhật ký giữ mã/tên khách và username người thao tác sau khi khách hoặc người thao tác bị xóa.
- Nhật ký toàn bộ tại `/khach-hang/nhat-ky/`, có tìm kiếm, lọc hành động và phân trang; lịch sử riêng tại trang chi tiết khách.
- Đổi tiêu đề và menu “Nhân viên” thành “Nhân sự”, giải thích trang chứa cả hồ sơ Quản lí và nhân viên. URL `/nhan-vien/` giữ nguyên.

## Phân quyền

| Vai trò | Xem / tìm | Thêm / sửa | Xóa | Nhật ký |
| --- | --- | --- | --- | --- |
| Superuser đang hoạt động | Có | Có | Có | Có |
| Quản lí | Có | Có | Có | Có |
| Phục vụ / Thu ngân | Có | Có | Không | Không |
| Bếp / Kho | Không | Không | Không | Không |

Quyền dùng `customers.view_customer`, `add_customer`, `change_customer`, `delete_customer` và `view_customeractivitylog`. Sidebar/nút theo quyền; gọi URL hoặc POST trực tiếp vẫn bị kiểm tra. Service khóa và đọc lại tài khoản thao tác để không dùng quyền đã cache sau khi tài khoản bị khóa hoặc đổi vị trí. Quyền khách hàng không cấp quyền quản lý nhân sự.

Django Admin của khách hàng và nhật ký chỉ xem, kể cả superuser. Thao tác thay đổi đi qua giao diện nghiệp vụ để bảo đảm validation và nhật ký. Mọi POST yêu cầu CSRF; GET trang xóa chỉ hiển thị xác nhận.

## Dữ liệu và migration

- `customers.0001_initial`: bảng Customer và CustomerActivityLog, unique/check constraints và khóa ngoại giữ lịch sử.
- `customers.0002_seed_customer_permissions`: tạo quyền tường minh trước post_migrate và cấp cho nhóm hiện có. Phụ thuộc employees.0009; không sửa quyền nhân sự.
- Hai migration đã áp dụng trên database ứng dụng. Kiểm tra đọc sau migration: MANAGER có 5 quyền; WAITER/CASHIER có 3 quyền; KITCHEN/INVENTORY không có quyền khách hàng.
- Không thêm dữ liệu demo vào database ứng dụng. Dữ liệu test được tạo và dọn trong database kiểm thử riêng.
- Xóa sẽ bị từ chối khi có quan hệ `PROTECT` hoặc `RESTRICT`; giao dịch rollback cả nhật ký nếu xóa thất bại. Hiện chưa có đặt bàn/đơn hàng để liên kết; các module sau phải định nghĩa khóa ngoại bảo vệ này, không dùng CASCADE cho lịch sử nghiệp vụ.

## Kiểm chứng

- **98/98 test đạt**, gồm 74 test tài khoản/nhân sự và 24 test khách hàng trên PostgreSQL.
- Kiểm tra form hai trường, chuẩn hóa/trùng/sai số điện thoại, họ tên trống, ràng buộc database, phân quyền từng nhóm ở GET/POST/service, actor bị thu hồi quyền, CSRF, escape tên khách, tìm kiếm và phân trang.
- Kiểm tra thêm/sửa/xóa, GET không xóa, giữ snapshot sau xóa khách/người thao tác, rollback khi log lỗi hoặc gặp liên kết bảo vệ, Admin chỉ xem.
- Test đồng thời dùng hai actor và hai kết nối PostgreSQL, đồng bộ sau bước validation: một lần tạo thành công, một lần nhận lỗi trùng tại trường điện thoại, chỉ một hồ sơ và một nhật ký được lưu.
- `manage.py check` không phát hiện vấn đề; `makemigrations --check --dry-run` không có model thiếu migration.
- Render GET trên database ứng dụng trong transaction chỉ đọc với superuser hiện có: danh sách/thêm/nhật ký khách hàng, trang cá nhân và nhân sự trả 200; form khách hàng có tên/điện thoại, không có email.
- **Giới hạn:** chưa kiểm tra bố cục trực quan bằng Browser vì công cụ không khởi tạo được (`missing field sandboxPolicy`). Các luồng HTTP và template đã kiểm tra bằng Django Client/RequestFactory; không coi đó là kiểm chứng bố cục trình duyệt.

## Phần tiếp theo đề xuất

Khu vực và bàn, sau đó đặt bàn sử dụng khách hàng vừa triển khai. Khi làm đặt bàn cần xác định số khách, thời gian đến, thời lượng giữ bàn, chống trùng lịch và trạng thái hủy/đến/hoàn tất. Khách vãng lai ở nghiệp vụ bán hàng sau này có thể không gắn hồ sơ, không cần tạo khách giả có số điện thoại dùng chung.
