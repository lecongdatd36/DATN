# Giai đoạn 8 — Gọi món, Đơn hàng và Bếp

Ngày cập nhật: 23/09/2026.

## Phạm vi

App `orders` cung cấp danh sách/chi tiết đơn, mở đơn theo lượt khách đã nhận, nhận khách không đặt trước, thêm/sửa/hủy món, gửi Bếp, tiến độ làm món, xác nhận phục vụ, tổng tiền tạm tính và nhật ký. Menu, trang tài khoản, chi tiết lượt khách và trang Bàn đều có liên kết theo quyền.

Đây là phần gọi món đến chờ thanh toán. Chưa có hóa đơn, thu tiền hoặc trạng thái đã thanh toán. Không thể giải phóng bàn còn đơn đang phục vụ/chờ thanh toán. Bước tiếp theo cần triển khai thanh toán để đóng đơn hợp lệ.

## Luồng nghiệp vụ

1. Khách có lịch: nhận khách ở Đặt bàn, sau đó mở đơn cho lượt đang phục vụ. Mở lại cùng lượt trả về cùng một đơn, không tạo trùng.
2. Khách trực tiếp: chọn bàn và số khách; tên/số điện thoại không bắt buộc, thời lượng lấy mặc định của Đặt bàn nếu bỏ trống. Kiểm tra bàn/khu vực, sức chứa, lịch trùng trong khoảng dự kiến và khách chưa rời bàn kể cả quá giờ. Nhận khách và mở đơn cùng giao dịch; nếu tạo đơn/nhật ký lỗi thì không giữ bàn.
3. Thêm món còn phục vụ, số lượng 1–100, ghi chú tối đa 500 ký tự. Lưu mã, tên, đơn vị và đơn giá lúc thêm; sửa thực đơn sau không sửa các dòng đã gọi. Gọi thêm tạo dòng riêng để giữ từng đợt và ghi chú. Chỉ sửa số lượng/ghi chú khi chưa gửi Bếp.
4. Gửi tất cả dòng chưa gửi xuống Bếp. Màn hình xác nhận liệt kê món/số lượng/ghi chú. Kiểm tra lại món và danh mục còn phục vụ; một món không hợp lệ thì chưa gửi cả đợt. Không tự thay giá snapshot khi gửi.
5. Bếp xem các dòng đã gửi/đang làm/đã xong theo thứ tự giờ gửi, lọc món/mã đơn/bàn/trạng thái. Chọn Bắt đầu làm rồi Đã xong; Phục vụ xác nhận Đã phục vụ. Không tự nhảy trạng thái, không sửa số lượng/ghi chú sau gửi.
6. Khi mọi món chưa hủy đã phục vụ xong, chuyển Chờ thanh toán. Có thể Tiếp tục gọi món để mở lại đơn trước khi thanh toán. Không coi thao tác này là đã thu tiền.
7. Hủy món luôn cần lý do. Hủy toàn đơn chỉ khi không còn món chưa hủy, cũng phải có lý do. Đơn hủy là trạng thái cuối; muốn phục vụ lượt mới cần hoàn tất lượt cũ trước.

## Trạng thái

| Đối tượng | Luồng |
| --- | --- |
| Món | Chưa gửi Bếp → Đã gửi Bếp → Đang làm → Đã xong → Đã phục vụ |
| Hủy món | Có lý do; quyền tùy món đã bắt đầu làm hay chưa; giữ dòng lịch sử |
| Đơn | Đang phục vụ → Chờ thanh toán; Chờ thanh toán → Đang phục vụ nếu gọi thêm |
| Đơn không còn món | Đang phục vụ → Đã hủy, có lý do |

Món hủy không cộng vào tạm tính; dòng hủy vẫn hiển thị tiền đã gạch và lý do. Giá tạm tính chưa có giảm giá, thuế hoặc phí. Các mốc gửi Bếp, bắt đầu làm, làm xong, phục vụ và hủy được lưu.

## Phân quyền

| Vai trò | Xem đơn/tiền | Mở đơn, gọi món, gửi Bếp, phục vụ | Xử lý Bếp | Hủy món đã bắt đầu làm | Nhật ký |
| --- | --- | --- | --- | --- | --- |
| Superuser/Quản lí | Có | Có | Có | Có | Có |
| Phục vụ/Thu ngân | Có | Có | Không | Không | Không |
| Bếp | Không | Không | Có | Không | Không |
| Kho | Không | Không | Không | Không | Không |

- Phục vụ/Thu ngân hủy được món chưa gửi hoặc đã gửi nhưng chưa làm. Chỉ Quản lí được hủy món đang làm/đã xong/đã phục vụ. Mọi hủy món đều ghi lý do và người thực hiện.
- Bếp không được xem món chưa gửi, liên hệ khách hoặc chi tiết tiền đơn; không được dùng endpoint Bếp để sửa giá, phục vụ hoặc hủy món.
- Kiểm tra quyền ở view và đọc lại actor tại service. `is_staff` riêng lẻ không cấp quyền; tài khoản khóa hoặc vừa mất quyền bị từ chối.
- POST có CSRF; GET không đổi dữ liệu. Admin chỉ đọc, không cho thêm/sửa/xóa/bulk action.

## Dữ liệu và đồng bộ

- `Order.booking` là OneToOne PROTECT, một đơn cho mỗi lượt khách; mã đơn `DH...`.
- Khách trực tiếp dùng `Booking.is_walk_in`, mã `LK...`, trạng thái đang phục vụ/hoàn tất; có thể không gắn Customer, không tạo hồ sơ giả. Nếu cung cấp số điện thoại trùng khách đã lưu thì liên kết hồ sơ đó. Lịch đặt trước vẫn bắt buộc Customer và mã `DB...`.
- Dùng chung Booking cho lượt khách giúp trang Bàn, tra lịch trùng và bảo vệ bàn/khu vực phản ánh cả khách trực tiếp. Đã bổ sung tìm mã LK trong danh sách lượt khách.
- Hoàn tất lượt được chặn tại service nếu có đơn khác trạng thái Đã hủy; giao diện ẩn nút Hoàn tất và dẫn đến đơn. Kiểm tra nằm dưới cùng khóa giao dịch với mở đơn để không có đơn mở trên lượt vừa hoàn tất.
- OrderItem dùng PROTECT tới Order/Dish; đơn bảo vệ lượt khách và tài khoản người mở bằng PROTECT. Tài khoản đã mở đơn cần khóa/nghỉ việc thay vì xóa. Nhật ký giữ tên người thao tác nếu tài khoản chỉ thao tác về sau được xóa.
- Khóa nhất quán: bàn/lịch (`81723002`) → thực đơn (`81723003`) → actor → bản ghi. Tách `core/menu_lock.py` dùng chung với service Thực đơn, tránh vừa báo hết món vừa gửi món không được kiểm tra lại.
- Mỗi thay đổi tăng phiên bản đơn, form mang `expected_revision`; từ chối dữ liệu cũ/gửi lặp, kể cả cập nhật từ Bếp. Kiểm tra món thuộc đúng đơn trước khi thao tác.
- Thay đổi và nhật ký cùng transaction; lỗi nhật ký rollback cả dữ liệu và phiên bản. Lưu không đổi số lượng/ghi chú không tạo log thừa.
- Database bảo vệ một đơn/lượt, giá/số lượng/trạng thái và lý do/thời gian hủy. Quyền, trình tự trạng thái và snapshot chỉ được duy trì khi ghi qua service; SQL/ORM trực tiếp có thể bỏ qua quy tắc nghiệp vụ.

## Kiểm chứng

- **239/239 kiểm thử toàn hệ thống đạt**. Có 35 kiểm thử mới cho Orders: 30 bài nghiệp vụ/giao diện và 5 bài đồng thời bằng kết nối PostgreSQL riêng.
- Bao phủ phân quyền GET/POST/service, thu hồi quyền, CSRF, Admin chỉ đọc, khách trực tiếp/khách có lịch, sức chứa, quá giờ, lịch trùng, rollback nhận khách/mở đơn, snapshot giá/tên/đơn vị, gọi nhiều đợt, giả mạo giá từ POST, ghi chú, sửa/hủy món, hàng đợi Bếp, tiền tạm tính, form cũ và ràng buộc quan hệ.
- Năm bài đồng thời: mở cùng lượt chỉ một đơn; khách trực tiếp cùng bàn chỉ một lượt; hoàn tất lượt cạnh tranh với mở đơn; hủy món cạnh tranh với bắt đầu làm; báo hết món cạnh tranh với gửi Bếp.
- Danh sách đơn dùng prefetch dòng món, Bếp select_related bàn/lượt/đơn; kiểm thử số truy vấn tránh tải riêng từng quan hệ cho từng dòng.
- Kiểm thử chạy trên database UUID riêng, migrate từ đầu và dọn khi xong; không tạo dữ liệu nghiệp vụ mẫu trong database ứng dụng.
- Đã áp dụng `bookings.0007_booking_is_walk_in_alter_booking_customer_and_more`, `orders.0001_initial`, `orders.0002_seed_order_permissions` trên database ứng dụng. Quyền thực tế: MANAGER 5 quyền, WAITER/CASHIER 2, KITCHEN 1, INVENTORY 0 quyền orders.
- Render trang chủ, danh sách/mở đơn/khách trực tiếp/Bếp, Bàn, Đặt bàn, Thực đơn và chi tiết lượt có sẵn đều trả 200 trong transaction chỉ đọc. Database ứng dụng chưa có đơn mẫu; trang chi tiết/chuyển trạng thái được kiểm chứng bằng dữ liệu kiểm thử riêng.
- `manage.py check`, `makemigrations --check --dry-run` và kiểm tra diff đạt.
- Công cụ Browser lỗi khởi tạo; chưa xác minh bố cục trực quan. Kiểm thử Django xác minh phản hồi, template và nghiệp vụ, không thay thế thao tác trình duyệt.

## Giới hạn và phần tiếp theo

- Trang Bếp, danh sách/chi tiết đơn cập nhật bằng nút tải lại; chưa có đẩy thông báo, âm thanh hoặc cập nhật nền. Trang Bàn tiếp tục tự cập nhật mỗi 15 giây như trước.
- Chưa có tách/ghép/chuyển bàn, gộp đơn, chia số lượng một dòng thành nhiều đợt phục vụ, xuất phiếu Bếp, thanh toán, trừ kho hoặc báo cáo.
- Giai đoạn 9: hóa đơn/thu tiền, phương thức thanh toán, chống thu trùng, lưu số tiền được chốt và chỉ đóng đơn/giải phóng bàn sau khi thanh toán thành công. Không dùng nút hủy món/đơn để thay thế nghiệp vụ thu tiền.
