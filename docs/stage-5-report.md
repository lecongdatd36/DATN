# Giai đoạn 5 — Khu vực và Bàn

Ngày cập nhật: 20/09/2026.

Báo cáo lịch sử Giai đoạn 5. Đặt bàn và ràng buộc lịch với khu vực/bàn đã được bổ sung ở [Giai đoạn 6](stage-6-report.md).

## Phạm vi đã làm

- App `seating`: Area, DiningTable, SeatingActivityLog; model/form/selector/service/view riêng, tích hợp menu và trang cá nhân.
- Khu vực: tên bắt buộc, không trùng khác hoa/thường; thêm, sửa, ngừng/mở sử dụng. Danh sách có số bàn, tìm tên, lọc trạng thái, phân trang 20 dòng theo thứ tự ổn định.
- Bàn: mã duy nhất toàn nhà hàng (tự chuyển hoa, tối đa 20 ký tự A–Z/số/gạch ngang/gạch dưới), khu vực bắt buộc, số chỗ 1–100 và trạng thái sử dụng. Có thêm/sửa/chuyển khu vực/ngừng/mở, tìm mã hoặc khu vực, lọc và phân trang.
- Không xóa vĩnh viễn khu vực/bàn trong giai đoạn này. Quan hệ bàn → khu vực dùng PROTECT.
- Nhật ký ghi người thao tác, đối tượng, thông tin thay đổi và thời gian. Lưu cả tên/mã tại thời điểm thao tác; giữ username khi người thực hiện bị xóa. Không ghi thêm log khi lưu không đổi thông tin.
- Nhật ký và dữ liệu thay đổi trong cùng transaction; lỗi log rollback dữ liệu. Dùng khóa giao dịch PostgreSQL riêng cho các thao tác danh mục để xử lý tạo trùng mã và ngừng khu vực đồng thời với tạo/chuyển bàn.

## Quy tắc trạng thái

Bàn có thể sử dụng khi **bàn đang bật và khu vực đang bật**. Ngừng khu vực không thay cờ của các bàn con; mở lại khu vực chỉ phục hồi khả năng sử dụng cho bàn vốn đang bật. Bàn bị ngừng riêng vẫn ngừng.

Không tạo hoặc chuyển bàn vào khu vực đã ngừng. Với bàn đang ở khu vực đã ngừng, được sửa mã/số chỗ, ngừng bàn hoặc chuyển sang khu vực khác. Không bật lại bàn đã tắt khi khu vực vẫn ngừng. Form chỉ liệt kê khu vực đang dùng và khu vực hiện tại của bàn; service kiểm tra lại trạng thái sau khi khóa giao dịch.

Trạng thái hiện tại chỉ là cấu hình cho phép sử dụng. Chưa có lịch đặt bàn, bàn trống/đang có khách, đơn hàng hoặc cơ chế nhận khách.

## Phân quyền

| Vai trò | Xem khu vực/bàn | Thêm/sửa/ngừng/mở | Xem nhật ký |
| --- | --- | --- | --- |
| Superuser đang hoạt động | Có | Có | Có |
| Quản lí | Có | Có | Có |
| Phục vụ / Thu ngân | Có | Không | Không |
| Bếp / Kho | Không | Không | Không |

Quyền riêng: `seating.view_area`, `view_diningtable`, `manage_seating`, `view_seatingactivitylog`. Kiểm tra tại view và đọc lại actor tại service; không dựa riêng vào việc ẩn nút. POST cần CSRF, GET không ghi dữ liệu. Django Admin chỉ tra cứu, kể cả superuser.

## Migration và kiểm chứng

- `seating.0001_initial` tạo ba bảng cùng ràng buộc tên, mã, số chỗ và khóa ngoại.
- `seating.0002_seed_seating_permissions` tạo quyền tường minh, chạy được trên database mới, cấp quyền cho MANAGER/WAITER/CASHIER; không sửa quyền module khác.
- Hai migration đã áp dụng vào database ứng dụng. Đối chiếu nhóm thực: MANAGER có 4 quyền, WAITER/CASHIER có 2 quyền xem, KITCHEN/INVENTORY không có quyền seating.
- **118/118 kiểm thử đạt** trên PostgreSQL: 98 test cũ và 20 test Seating. Database kiểm thử riêng, chạy migrations từ đầu và dọn sau khi xong.
- Kiểm tra ma trận quyền ở GET/POST/service, actor bị thu hồi quyền/khóa, superuser thiếu hồ sơ, form và ràng buộc database, CSRF, Admin chỉ xem, tìm/lọc/phân trang, ngừng/mở khu vực và giữ cờ bàn, sửa/chuyển bàn, rollback nhật ký, bảo vệ khu vực còn bàn.
- Hai bài kiểm thử nhiều kết nối PostgreSQL: hai actor tạo cùng mã chỉ lưu một bàn; ngừng khu vực cùng lúc tạo bàn kết thúc với khu vực đã ngừng và không còn bàn có thể sử dụng.
- `manage.py check` đạt; model/migration đồng bộ. Cảnh báo thứ tự phân trang từ phép đếm số bàn đã được sửa bằng sắp xếp tường minh.
- Render GET trong transaction chỉ đọc trên database ứng dụng: danh sách/thêm bàn, danh sách/thêm khu vực, nhật ký và trang cá nhân đều trả 200; không thêm dữ liệu demo hoặc đổi tài khoản thật.
- Chưa kiểm chứng bố cục trực quan trên Browser: công cụ đã lỗi khởi tạo trong phiên làm việc (`missing field sandboxPolicy`). Kiểm thử HTTP/template không thay thế việc xem bố cục trực tiếp.

## Tiếp theo

Đặt bàn liên kết khách hàng và bàn. Cần bổ sung khung thời gian giữ bàn, kiểm tra số khách so với sức chứa, chống trùng lịch, xác nhận/nhận khách/hủy/không đến. Khi đó, thao tác giảm số chỗ, chuyển hoặc ngừng bàn/khu vực phải kiểm tra các lịch đặt đang hiệu lực; chưa có những ràng buộc này vì module đặt bàn chưa được triển khai.
