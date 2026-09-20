# Giai đoạn 3 — Nhân viên và hoàn thiện tài khoản

Ngày cập nhật: 20/09/2026.

Đây là báo cáo lịch sử Giai đoạn 3. Khách hàng đã được triển khai tại [Giai đoạn 4](stage-4-report.md).

## Phạm vi

Đã có Accounts và Employees: Custom User, xác thực, đổi/reset mật khẩu, quản lý hồ sơ, vị trí, trạng thái làm việc và nhật ký. Đợt này sửa lỗi rà soát, bổ sung kiểm thử, áp dụng migration quyền; chưa mở module nghiệp vụ mới.

## Các lỗi đã sửa

- Thay điều kiện `change_employeeprofile` bằng quyền riêng `manage_staff`. Chỉ nhóm MANAGER được cấp quyền quản lý; WAITER/CASHIER/KITCHEN/INVENTORY không có quyền quản lý nhân sự. Cờ staff không thay thế quyền này.
- Migration 0008 tạo tường minh quyền cần dùng, hoạt động khi migrate database mới hoàn toàn. Trên database cũ, thu hồi quyền nhân sự cấp nhầm trong năm nhóm mặc định, giữ quyền thuộc module khác. Tăng session_version để phiên dùng quyền cũ hết hiệu lực. Reverse migration không khôi phục bộ quyền sai.
- Thống nhất bảo vệ đối tượng giữa tài khoản và hồ sơ: superuser được quản lý manager và nhân viên; quản lý thường chỉ thao tác nhân viên không có quyền quản lý. Không ai sửa bản thân hoặc bất kỳ superuser nào qua luồng quản lý, kể cả gọi service trực tiếp. Do superuser không thể bị khóa/xóa/hạ quyền qua các luồng này, tài khoản quản trị hệ thống cuối cùng được bảo vệ.
- Sau phản hồi giao diện “Chỉ xem”, sửa điều kiện từng chặn cả superuser quản lý manager và tài khoản thiếu hồ sơ. Tài khoản thiếu hồ sơ vẫn sửa thông tin đăng nhập, khóa/mở khóa và reset mật khẩu được bởi superuser; không tự tạo hồ sơ giả. Hiển thị rõ lý do chỉ xem và phân biệt nhãn superuser với quản lý nhà hàng.
- Service đọc lại actor và dùng khóa giao dịch PostgreSQL chung trước khi ghi dữ liệu nhân sự. Kiểm thử hai kết nối tạo ở hai vị trí khác nhau xác nhận mã tự sinh không trùng. Mã còn trong nhật ký không được tự cấp lại.
- Khóa từ form sửa tài khoản cũng tăng session_version và ghi nhật ký như nút Khóa. Khóa rồi mở lại không khôi phục phiên cũ.
- Nhân viên nghỉ việc không được mở khóa. Đi làm lại xóa ngày nghỉ việc, nhưng cần thao tác mở khóa riêng. Tạo hồ sơ đã nghỉ việc có ngày hợp lệ sẽ tạo tài khoản bị khóa.
- Form tạo có ngày nghỉ việc, kiểm tra username trùng không phân biệt hoa thường và ký tự hợp lệ. Password được kiểm tra trong service với thông tin người dùng. Lỗi model được ánh xạ về trường có trên form, lỗi khác về thông báo chung.
- Sửa hồ sơ đồng bộ nhóm vị trí và cờ staff, không ghi đè cờ superuser. Đổi vị trí vô hiệu hóa phiên cũ. Reset mật khẩu qua form hồ sơ được ghi nhật ký, không lưu password/hash.
- Django Admin của User, vị trí và hồ sơ chuyển sang chỉ xem để không bỏ qua nghiệp vụ; nhật ký tiếp tục chỉ xem. User Admin chỉ hiển thị cho superuser.
- Bổ sung phân trang nhân viên, giữ ID vị trí khi chuyển trang, tìm tài khoản theo tên hồ sơ, hiển thị tên/vị trí đúng sau khi bỏ User.role. Ẩn nút sửa đối tượng được bảo vệ. Danh sách nhân viên tải sẵn User và JobPosition.
- Giới hạn ảnh tải mới 5 MB, dùng kiểm tra ảnh của Django form. Các view nhập mật khẩu che trường nhạy cảm trong báo cáo lỗi khi cấu hình production; trang nhân viên không cache.
- Bổ sung nút Xóa trên danh sách/chi tiết tài khoản và trang xác nhận riêng. Tài khoản chưa có hồ sơ cũng xóa được bởi superuser. GET chỉ xác nhận; POST có CSRF thực hiện xóa User và hồ sơ trong cùng transaction. Luồng Xóa nhân viên gọi chung service, bảo vệ bản thân/superuser và giữ nhật ký; tài khoản đã tạo nhật ký Django hoặc có dữ liệu PROTECT/RESTRICT bị từ chối xóa.
- Đổi nhãn “Quản trị viên / Quản lý” thành “Quản lí” ở form, bộ lọc, danh sách và chi tiết; migration 0009 cập nhật tên JobPosition để các trang nhân viên cũng hiển thị thống nhất. Mã MANAGER và quyền không đổi; superuser hiển thị “Quản trị hệ thống”.

## Kiểm chứng

- 74/74 test đạt trên PostgreSQL trong lần kiểm tra toàn bộ sau các thay đổi nghiệp vụ; bao gồm migrate database mới từ đầu, test tạo đồng thời bằng hai kết nối và tái hiện danh sách ba tài khoản như tình huống người dùng báo. Các test xóa mới kiểm tra hồ sơ/tài khoản thiếu hồ sơ, CSRF, quyền, phiên cũ, giữ lịch sử và rollback khi gặp liên kết được bảo vệ hoặc lỗi ghi log.
- Nhóm test mới kiểm tra từng vị trí với group thực, GET/POST trái quyền, actor bị thu hồi quyền, manager/superuser/bản thân, CSRF, redirect đăng nhập ngoài host, khóa và reset phiên, form lỗi, nhật ký rollback, phân trang và tìm kiếm.
- `manage.py check`: không phát hiện vấn đề.
- `makemigrations --check --dry-run`: model và migration khớp nhau.
- Migration `employees.0008_correct_staff_permissions` đã áp dụng vào database ứng dụng. Không sửa `.env`, không tạo tài khoản demo hoặc thay mật khẩu người dùng.
- Có `scripts/run_tests.py` chạy trên database tên UUID riêng, dọn database sau khi hoàn tất. Không ghi dữ liệu test vào database ứng dụng.
- Chưa xác minh bố cục bằng trình duyệt: Browser không khởi tạo được do lỗi cấu hình công cụ. Các luồng HTTP và render template đã được kiểm tra bằng Django Client.
- Đã đối chiếu ảnh người dùng gửi và render trực tiếp bằng superuser hiện có trong transaction chỉ đọc: danh sách ba tài khoản còn một dòng chỉ xem (bản thân), hai dòng có nút sửa/reset/khóa. Sáu form GET sửa, khóa và reset cho manager/tài khoản thiếu hồ sơ trả 200; không thay dữ liệu tài khoản thật.

## Quy tắc vận hành và phần tiếp theo

- Sau migration quyền, đăng nhập lại. Admin là nơi tra cứu; sửa nhân sự qua giao diện ứng dụng.
- Superuser sửa được tài khoản quản lý nhà hàng qua giao diện nghiệp vụ. Tài khoản superuser vẫn được bảo vệ; không có chức năng cấp hoặc thu hồi cờ superuser trên giao diện này. `/admin/` nhân sự vẫn chỉ xem.
- Xóa nhân viên và xóa tài khoản giữ snapshot EmployeeActivityLog, ghi LogEntry có action_flag DELETION và thông tin tài khoản trước khi xóa. Nếu tài khoản là người thực hiện của một LogEntry sẵn có, từ chối xóa vì FK này dùng CASCADE; dùng khóa để giữ lịch sử. Đối tượng có liên kết PROTECT/RESTRICT bị từ chối; khi triển khai đơn hàng/hóa đơn phải bảo vệ quan hệ này, dùng nghỉ việc để giữ lịch sử nghiệp vụ.
- Khóa giao dịch chung phù hợp phạm vi quản lý nhân sự hiện tại; nếu cần số lượng thao tác ghi lớn, có thể thay bằng cơ chế cấp mã và khóa chi tiết hơn.
- Chưa có dữ liệu demo, sơ đồ thiết kế hoàn chỉnh, cấu hình triển khai production và kiểm tra bố cục trực quan. Đây là phần còn cần hoàn thiện ngoài các lỗi nghiệp vụ đã sửa.
- Module mới đề xuất tiếp theo: Khách hàng, rồi Khu vực/Bàn/Đặt bàn, Thực đơn, Đơn hàng/Bếp/Thanh toán, Kho/Báo cáo và AI.
