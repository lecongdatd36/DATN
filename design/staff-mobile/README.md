# Bản mẫu mobile nhân viên · Concept 04

Giao diện thật đã được tích hợp riêng tại `/sales/mobile/`; xem [tài liệu ứng dụng](../../docs/staff-mobile.md). Thư mục này giữ bản mẫu độc lập để tham khảo thiết kế.

Bản HTML/CSS/JavaScript độc lập để duyệt bố cục trước khi tích hợp Django.
Dữ liệu minh họa chỉ tồn tại trong bộ nhớ; tải lại hoặc bấm “Đặt lại bản mẫu” để khôi phục.
Không gửi yêu cầu tới backend, không tạo order hoặc thanh toán thật.

Mở `index.html` trực tiếp hoặc phục vụ thư mục này bằng HTTP. Trên desktop hiển thị ba màn hình tương tác; chọn “Dùng thử” để xem một màn. Trên điện thoại hiển thị toàn màn hình.

Luồng có thể thử:

- Chọn bàn trống, nhập số khách, mở màn gọi món.
- Nhập số khách và SĐT tùy chọn; hệ thống tự tra hồ sơ khi bấm Tìm. Có hồ sơ thì hiện tên/hạng; chưa có thì hiện ô đăng ký tên. Không nhập SĐT vẫn mở bàn, không phải chọn loại khách. Thông tin đi theo màn gọi món, order và khi chuyển/tách hóa đơn.
- Tìm món không dấu, lọc nhóm, thêm món và ghi chú.
- Xem order, tăng/giảm món mới, xác nhận gửi bếp.
- Món đã gửi không cho sửa số lượng.
- Xem yêu cầu phục vụ, nhận xử lý hoặc chuyển thu ngân (minh họa).
- Màn Mang món: xem món READY, ghi chú nổi bật và xác nhận SERVED.
- Màn Đặt bàn: đối chiếu khách trước khi nhận bàn đã giữ chỗ.
- QR nhận bàn, duyệt gọi món gửi riêng xuống bếp, từ chối bắt buộc lý do.
- Chuyển order sang bàn trống đủ chỗ; bàn cũ cần dọn trước khi nhận khách.
- Hủy món / order, lưu lý do và lịch sử; chặn hủy cả bàn khi đã gửi món bếp.
- Yêu cầu thanh toán chỉ khi tất cả món còn hiệu lực đã phục vụ; khóa gọi thêm món.
- Thu ngân tách số lượng món ra hóa đơn riêng, ghép về gốc cùng bàn; không cho tách hết món khỏi hóa đơn gốc.
- Mất mạng, lỗi gửi và xung đột phiên bản: giữ dữ liệu nhập, chưa áp dụng thao tác, yêu cầu kiểm tra trước khi thử lại.
- Thu ngân có thanh điều hướng Bàn / Chờ thanh toán / Hóa đơn / Cá nhân, đồng thời vẫn mở bàn, gọi món, gửi bếp và xác nhận phục vụ như nghiệp vụ hiện có.
- Thu tiền mặt: nhập khách đưa, tính tiền thừa, kiểm tra và xác nhận trước khi chốt.
- Chuyển khoản: tham chiếu tùy chọn, bắt buộc xác nhận đã nhận đủ tiền vào tài khoản nhà hàng.
- Thu ngân xem/in bản hóa đơn đã chốt; số tiền, khách, phương thức và ưu đãi được giữ theo thời điểm thanh toán. Chỉ cộng chi tiêu khách khi thu tiền thành công, không cộng lại khi thử lại.
- Thanh toán từng hóa đơn tách; bàn chỉ sang Cần dọn sau hóa đơn cuối cùng. Không cho ghép hóa đơn đã thu.

Chọn **Xem nghiệp vụ bổ sung** hoặc mở `?view=operations` để xem Mang món / Đặt bàn / QR cùng lúc.
Chọn **Xem nhận bàn & thông tin khách** hoặc mở `?view=reception` để xem bước nhận khách cùng thông tin liên kết trên gọi món/order.
Chọn **Xem giao diện thu ngân** hoặc mở `?view=cashier` để xem danh sách cần thu, form thanh toán và danh sách hóa đơn. Thử thu tiền để hóa đơn xuất hiện ở màn thứ ba.
Mục **Thử nghiệp vụ & tình huống** cho phép đổi vai trò minh họa (phục vụ, thu ngân, quản lý), giả lập món đã phục vụ, lỗi mạng, lỗi gửi và người khác cập nhật order. Các vai trò chỉ là cấu hình trình diễn; không thay thế quyền của backend.

## Đối chiếu nghiệp vụ hiện có

| Luồng | Nghiệp vụ Django dùng khi tích hợp |
| --- | --- |
| Mở bàn, thêm/sửa món, gửi bếp, chuyển bàn, hủy bàn | `apps/orders/sales_views.py`, `SalesActionView` |
| Mang món: READY → SERVED | `apps/orders/services.py`, `transition_item` |
| QR nhận bàn / gọi món / từ chối | `QRCheckInActionView`, `QRRequestActionView` |
| Khách đặt trước | Nghiệp vụ bookings và quyền `manage_booking` |
| Tách / ghép hóa đơn chờ thanh toán | `split_order`, `merge_split_order`, quyền `collect_payment` |
| Hủy món đã chế biến | Quyền riêng `cancel_prepared_item` |

Tách / ghép chỉ áp dụng hóa đơn chưa phát sinh giao dịch và cùng nhóm tách. Theo yêu cầu, mobile chỉ có tiền mặt và chuyển khoản; VNPAY được bỏ khỏi bản mẫu. Backend VNPAY hiện tại không thay đổi. Hoàn tiền và dữ liệu thanh toán một phần từ hệ thống cũ không nằm trong bản mẫu.
Các kiểm tra đặt bàn trùng giờ, khả dụng món, tồn kho, phân quyền và khóa giao dịch vẫn cần do backend thực hiện khi tích hợp.

## Kiểm tra

Mở `verify.html` qua HTTP để chạy các kiểm tra giao diện thật trong iframe: luồng chính, QR, mang món, đặt bàn, chuyển/hủy, tách/ghép, phân quyền mẫu, lỗi mạng và xung đột; kiểm tra tràn ngang tại 320, 360, 390 và 430px.
Mở `verify-cashier.html` để kiểm tra quyền thu ngân, tiền mặt/tiền thừa, chuyển khoản, ưu đãi, hóa đơn, lỗi gửi/mất mạng/xung đột và việc chỉ đóng bàn sau hóa đơn cuối cùng. Có kiểm tra bố cục và nút thu tiền tại 320–430px.

Các màn trong chế độ tổng thể dùng chung bàn đang chọn và order để dễ so sánh.
Ảnh minh họa là bản sao thumbnail từ tài nguyên món hiện có trong dự án.

Phạm vi cần chốt: mobile phục vụ, thu ngân và các luồng nghiệp vụ bổ sung. Màn bếp nhận/chế biến món, PWA và tích hợp API/đăng nhập thực tế chưa nằm trong bản mẫu này. Bộ chọn vai trò chỉ để duyệt thiết kế; quyền trong ứng dụng thật phải lấy từ tài khoản đăng nhập.
Trạng thái và nội dung nhập chỉ được giữ trong phiên trang đang mở; tải lại trang sẽ đặt lại dữ liệu, không có hàng đợi gửi offline.

Đối chiếu riêng nghiệp vụ khách và các điểm còn phải xử lý khi tích hợp: [customer-business-review.md](customer-business-review.md).

## Lưu ý tích hợp thanh toán

- Nghiệp vụ tham chiếu: `PaymentActionView`, `prepare_quick_payment`, `process_payment`, `_finalize_paid_invoice`, `split_order` và `merge_split_order` trong `apps/orders`.
- Tiền mặt và chuyển khoản vẫn cần `orders.collect_payment` tại view/service. Thu ngân có cả `manage_order`; phục vụ chỉ gửi yêu cầu thanh toán.
- GIAM10 và các mốc hạng trong mẫu là dữ liệu trình diễn. Backend phải trả kết quả tạm tính cuối cùng; không tin số tiền/ưu đãi gửi từ trình duyệt.
- Backend thu phần còn lại của hóa đơn cũ đã thu một phần; prototype chỉ mô phỏng hóa đơn mới thu đủ một lần.
- Bước chuẩn bị chờ thanh toán và ghi nhận thu tiền trên backend là các lời gọi riêng; khi tích hợp cần phân biệt đã chuẩn bị, đã thu thành công và chưa rõ kết quả để tránh thu lặp.
