# Giai đoạn 9 — Hóa đơn và Thanh toán

Ngày cập nhật: 27/09/2026.

## Phạm vi

Giai đoạn này nối tiếp luồng gọi món bằng hóa đơn, các lần thu tiền và trạng thái đơn đã thanh toán. Bàn chỉ được giải phóng sau khi đơn bị hủy hợp lệ hoặc đơn và hóa đơn đều đã thanh toán.

## Luồng nghiệp vụ

1. Phục vụ hoàn tất món và chuyển đơn sang **Chờ thanh toán**.
2. Nếu chưa thu tiền, đơn có thể mở lại để gọi thêm. Khi đã thu một phần, tổng hóa đơn được chốt và chức năng gọi thêm bị khóa.
3. Thu ngân hoặc Quản lí ghi nhận tiền mặt, thẻ, chuyển khoản hay phương thức khác. Hệ thống lưu từng phiếu thu, người thực hiện, thời gian và ghi chú/mã giao dịch.
4. Mỗi lần thu tăng phiên bản đơn để từ chối form cũ hoặc thao tác gửi lặp. Không cho thu số âm, số lẻ, vượt số còn lại hoặc dùng phương thức không hợp lệ.
5. Thu đủ chuyển cả hóa đơn và đơn sang **Đã thanh toán**. Trạng thái **Đã hủy** không được dùng thay cho thanh toán.
6. Trang chi tiết giữ lại mã hóa đơn, tổng tiền, đã thu, còn lại và lịch sử các lần thu sau khi đóng đơn; từ đó dẫn về lượt khách để hoàn tất và giải phóng bàn.

## Phân quyền và dữ liệu

- Quyền `orders.collect_payment` chỉ cấp cho nhóm `MANAGER` và `CASHIER`; superuser đang hoạt động được phép theo cơ chế chuẩn.
- Phục vụ vẫn được gọi món và chuyển chờ thanh toán nhưng không được gọi endpoint thu tiền.
- `Invoice` là quan hệ một-một với `Order`; `Payment` là các phiếu thu bất biến được bảo vệ bằng `PROTECT`.
- Mã hóa đơn `HD...` dựa trên khóa chính duy nhất của đơn, không phụ thuộc việc đọc bản ghi hóa đơn cuối cùng.
- Hoàn tất lượt khách kiểm tra đồng thời trạng thái đơn và hóa đơn, không chỉ dựa vào giao diện.

## Migration

- `menu.0003_dish_image_dish_thumbnail` bổ sung ảnh gốc và thumbnail của món.
- `orders.0003_invoice_payment` bổ sung bảng hóa đơn và phiếu thu.
- `orders.0004_order_paid_and_payment_permission` bổ sung trạng thái đơn **Đã thanh toán**, ràng buộc trạng thái và quyền thu tiền. Migration được tách riêng vì `orders.0003` đã được áp dụng trên database hiện tại.

## Trạng thái kiểm tra

Theo yêu cầu của chủ dự án, lần cập nhật này không tạo test mới và không chạy bộ test. Các test thanh toán đã tồn tại được chỉnh lại để phản ánh trạng thái `PAID` và vai trò Thu ngân, nhưng chưa được thực thi. Cần áp dụng migration và kiểm tra vận hành khi có yêu cầu riêng.

## Chưa triển khai

Chưa có hoàn tiền, hủy phiếu thu/hóa đơn qua giao diện, giảm giá, thuế/phí, in hóa đơn, tích hợp cổng thanh toán, kho, báo cáo hoặc AI.
