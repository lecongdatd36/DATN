# Đối chiếu thông tin khách trong mobile

Tài liệu đối chiếu từ giai đoạn bản mẫu. Giao diện thật hiện đã tích hợp tại `/sales/mobile/`, dùng `MobileActionView` và các services hiện có; xem [trạng thái tích hợp](../../docs/staff-mobile.md). Bản mẫu trong thư mục này vẫn dùng dữ liệu minh họa riêng.

| Trường hợp | Nguồn backend hiện tại | Bản mẫu sau chỉnh |
| --- | --- | --- |
| Khách vãng lai | `SalesActionView._perform(open)` để trống SĐT thì `customer=None` | Để trống SĐT; chỉ bắt buộc số khách, ghi chú bàn tùy chọn. Không tạo tên/hồ sơ giả và không bắt nhân viên phân loại khách. |
| Khách cũ | `CustomerLookupView`, tra cứu SĐT đã chuẩn hóa | Hiện tên, SĐT, hạng, % ưu đãi và chi tiêu; chọn hồ sơ hiện có. Không sửa tên khách cũ hoặc tạo trùng. Đổi SĐT phải tra cứu lại. |
| Khách mới | View tra cứu trước, gọi `create_customer` nếu chưa có | Sau tra cứu không thấy hồ sơ thì tự hiện ô tên; không chọn loại khách. Bắt buộc SĐT + tên để đăng ký; tên tối đa 150 ký tự, không trắng; kiểm tra riêng quyền `customers.add_customer`. Hồ sơ chỉ tạo khi thao tác mở bàn trong bản mẫu thành công. |
| Khách đặt trước | `Booking.customer`, `customer_name`, `customer_phone`, `Order.customer`, `open_table(reservation_id)` | Đối chiếu thông tin đặt, giữ liên kết khách. Yêu cầu khách từng gửi được đưa ra để nhân viên xác nhận và nhập thành ghi chú lượt khách. Không mở hồ sơ mới thay khách của lịch đặt. |
| Nhận bàn QR | `create_qr_check_in_request(token, guest_count)`, `confirm_qr_check_in_request` | Nói rõ QR nhận bàn chỉ có số khách. Xác nhận mặc định là vãng lai; không tự suy đoán tên/SĐT. |
| QR nhưng khách muốn cung cấp thông tin | Có thể mở bàn trực tiếp với khách trước, rồi confirm QR để dùng order đang có | Cho chuyển sang form nhận trực tiếp với SĐT. Khi tích hợp cần thực hiện đúng chuỗi hai bước và xử lý lỗi từng bước; không giả định endpoint QR nhận thêm trường khách. |
| Duyệt món QR | `QROrderRequest.customer` là người gửi; `confirm_qr_order_request` không thay `Order.customer` | Luôn giữ khách của order khi duyệt món, không gán lại hồ sơ chỉ vì khách gửi QR. |
| Thông tin khi gọi món | `Order.customer`, `guest_count`, `note` | Thẻ khách ở màn gọi món/order, mở được chi tiết. Ghi chú bàn theo lượt khách; ghi chú món riêng cho bếp. |
| Chuyển/tách hóa đơn | `move_table` giữ order; `split_order` sao chép `customer` | Giữ liên kết khách, ghi chú lượt khách khi chuyển bàn và cùng chính sách thành viên khi tách/ghép. |
| Tạm tính thành viên | `payment_preview`, lấy hạng theo chi tiêu, ROUND_HALF_UP đến đồng | Hiện tiền món, giảm thành viên và tạm tính. Tỷ lệ/hạng trong bản mẫu là dữ liệu minh họa; API/backend là nguồn quyết định khi tích hợp. |

## Ràng buộc đã đối chiếu

- SĐT: `apps/customers/validators.py`: bỏ dấu cách, `(`, `)`, `.`, `-`; `+84` đổi về `0`; sau chuẩn hóa phải khớp `0[0-9]{9,10}`. Không nhận SĐT sai hoặc tự xóa mọi ký tự lạ để biến thành hợp lệ.
- Tên khách: `Customer.full_name` tối đa 150 ký tự; gom khoảng trắng, không được để toàn khoảng trắng.
- Ghi chú bàn: `Order.note` tối đa 1000; ghi chú món: `OrderItem.note` tối đa 500. Không biến ghi chú bàn thành ghi chú cho tất cả món.
- Nhận bàn còn phải kiểm tra sức chứa, trạng thái bàn, lịch đặt, quyền order và quyền đặt bàn. Bản mẫu không thay thế khóa và kiểm tra lịch theo giờ của backend.
- Không tự cập nhật tổng chi tiêu khi mở bàn hoặc gửi bếp. Backend cập nhật khi thanh toán hoàn tất.

## Điểm cần xử lý ở bước tích hợp

1. Đã xử lý transaction: luồng mobile khóa và tạo khách + mở bàn trong cùng transaction. `SalesActionView.post` desktop cũng hiện bao `_perform` trong `transaction.atomic()`. Kiểm thử xác nhận mở bàn thất bại không để lại hồ sơ khách mới.
2. Các action POS hiện không có API đổi khách hoặc sửa ghi chú bàn sau khi mở order. Bản mẫu chỉ cho nhập khi nhận bàn và xem sau đó; không dựng nút Lưu thay đổi giả. Muốn bổ sung sau mở bàn cần endpoint, quyền, expected_revision và quy tắc khóa sau thanh toán.
3. Lịch đặt có snapshot tên/SĐT và liên kết hồ sơ riêng. Khi tích hợp phải dùng cả hai để đối chiếu, tránh ghi đè dữ liệu lịch sử bằng tên/SĐT hồ sơ đã thay đổi.
4. Quyền `manage_order`, `manage_booking`, `add_customer`, `collect_payment` độc lập. Bộ chọn vai trò và checkbox quyền ở bản mẫu chỉ phục vụ duyệt; tài khoản thật phải lấy quyền từ backend.
5. Đã xử lý QR nhận bàn kèm khách: mobile mở bàn trực tiếp và confirm QR trong cùng transaction; kiểm tra request thuộc đúng bàn và chưa xử lý. QR hết hạn hoặc confirm lỗi sẽ rollback cả khách/order mới, không tạo order thứ hai.
6. `Booking` hiện không có cột `note`: ghi chú từ đặt bàn công khai được ghi vào `BookingActivityLog.description` trong `create_public_booking`. Luồng chuẩn `transition_booking` → `open_order` chưa chuyển ghi chú này sang `Order.note`. Mẫu `requestNote` là thông tin yêu cầu trong nhật ký để minh họa bước nhân viên đối chiếu; khi tích hợp cần cung cấp nguồn ghi chú có cấu trúc và lưu rõ `visit_note` lúc nhận bàn, không giả định có `Booking.note` hay đã tự sao chép.

## Xem và kiểm tra

- `?view=reception`: ba màn nhận bàn, gọi món và order có thông tin khách.
- SĐT mẫu: `0901234567` (Trần Thảo, Vàng, 5%); `0912344821` (Nguyễn Minh, khách đặt trước).
- `verify.html`: kiểm tra khách cũ/mới/vãng lai, SĐT +84, SĐT sai/đã đổi, chống ghi đè khách cũ, quyền thêm khách, lỗi/mất mạng, ghi chú, booking, QR, chuyển bàn và ưu đãi khi tách/ghép.
