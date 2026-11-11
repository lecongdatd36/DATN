# Tổng quan quản lý Cơm Quê

Trang `/tai-khoan/` hiển thị dashboard vận hành cho tài khoản có quyền `reports.view_report`; nhân viên chưa có quyền báo cáo vẫn giữ màn không gian làm việc và các liên kết đúng quyền. Theme quản lý dùng xanh dương #2563eb, nền trắng/xanh nhạt, sidebar sáng và banner ảnh dùng chung với website khách. Dark mode và menu mobile vẫn hoạt động.

Menu bên trái cuộn độc lập trong vùng giữa logo và tài khoản. Có thanh cuộn mảnh và nút lên/xuống, tự khóa nút ở hai đầu; con lăn không kéo trang chính theo. Giữ vị trí cuộn trong phiên, theo từng tài khoản; khi chuyển mục, đưa liên kết đang hoạt động vào vùng nhìn thấy. Khi quay về mục tổng quan lần đầu, menu về đầu. Hỗ trợ Tab, Home / End, giảm chuyển động theo thiết lập hệ điều hành và nhãn khi thu gọn thành icon. Menu chỉ gồm chức năng và quyền thực sự có trong dự án.

Chrome đã kiểm tra con lăn, nút lên/xuống, logo/trang chính đứng yên, giữ vị trí sau tải lại, Home và chế độ thu gọn; ảnh ở `artifacts/attendance/browser/sidebar-*.png`.

- Doanh thu: tổng `Invoice.total` của hóa đơn PAID, theo `closed_at` trong ngày Việt Nam; không cộng lại tiền cọc hay tính hóa đơn chưa thanh toán.
- Số đơn: đơn tạo trong ngày, gồm các trạng thái để đối chiếu với biểu đồ trạng thái.
- Lịch đặt: lượt không phải walk-in, loại hủy/không đến; bao gồm booking được tạo từ quy trình online. Lịch sắp tới là PENDING/CONFIRMED từ hiện tại trở đi.
- Bàn đang phục vụ: bàn và khu vực đang hoạt động, trạng thái OCCUPIED.
- Top món: số lượng từ hóa đơn đã thanh toán trong 30 ngày, loại món bị hủy.
- Nguyên liệu: lượng SALE_USAGE trừ SALE_RETURN trong 30 ngày, xếp theo giá trị xuất ròng để không so trực tiếp số lượng khác đơn vị. Chỉ là xuất theo món, chưa bao gồm xuất tay hoặc hao hụt.
- Kho sắp hết: nguyên liệu hoạt động có tồn nhỏ hơn hoặc bằng ngưỡng theo dõi.
- Đơn gần đây: đơn tạo hôm nay. Hoạt động: nhật ký đơn gần đây, có cả ngày để tránh nhầm bản ghi cũ với hôm nay.

Hai thẻ **Gợi ý bàn phù hợp** và **Dự báo số đơn · 7 ngày** nằm ngay dưới các ô thống kê; menu cũng có hai mục riêng trong nhóm Gợi ý & phân tích. Gợi ý bàn mở `/dat-ban/ban-phu-hop/`, nhập giờ đến và số khách để xem xếp hạng. Dự báo có trang riêng `/bao-cao/du-bao-don/`, biểu đồ 7 ngày, tổng đơn trong kỳ, bảng chi tiết và nguồn dữ liệu. Trạng thái dữ liệu cũ/chưa có kết quả vẫn hiển thị rõ, không tạo số liệu hoặc tự huấn luyện khi mở trang. Liên kết gợi ý bàn yêu cầu quyền xem Booking; dự báo yêu cầu quyền Báo cáo, như endpoint cũ.

Kiểm tra điều hướng bổ sung: 36 test Reports / gợi ý bàn / dashboard qua; Chrome bấm từ thẻ dashboard đến biểu đồ dự báo (fixture UI) và nhập form tìm bàn để nhận đúng bàn khớp sức chứa. Desktop/mobile, phân quyền, trạng thái thiếu dữ liệu và static production đều qua.

Mỗi nhóm dữ liệu đơn / bàn / booking / kho / nhật ký được kiểm tra quyền riêng trong selector và ẩn panel khi tài khoản không có quyền. Endpoint không cache và chỉ đọc dữ liệu. Biểu đồ SVG và donut dùng JavaScript nội bộ, có bảng số liệu theo ngày, bộ lọc 7/14/30 ngày; không tải dịch vụ biểu đồ bên ngoài. Không thêm dữ liệu mẫu vào database thật và không cần migration cho dashboard.

Kiểm tra: test doanh thu theo giờ chốt, hóa đơn chưa thanh toán, điểm chuyển ngày Việt Nam, ngày không có dữ liệu, phân quyền và GET không ghi đơn; Chrome với dữ liệu tổng hợp trong PostgreSQL tạm ở desktop/tablet/mobile. Ảnh kiểm tra `artifacts/attendance/browser/management-dashboard-*.png`.

Kết quả ngày 11/11/2026: **612 test Django qua**, Chrome dashboard và tự chấm vào / chặn lặp / tự chấm ra qua; `manage.py check`, kiểm tra migration và collectstatic với manifest production đều qua. Không thay đổi đơn, hóa đơn, mẫu mặt hay công thật; dữ liệu browser test chỉ ở PostgreSQL UUID tạm.
