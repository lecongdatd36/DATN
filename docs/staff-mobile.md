# Giao diện mobile nội bộ đã tích hợp

Đường dẫn thật: `/sales/mobile/`. Dùng cùng tài khoản, order, phân quyền và database với desktop; không phải bản mẫu trong `design/staff-mobile`.

## Luồng chung theo bàn

1. **Bàn**: lọc khu vực/trạng thái, nhận khách ở bàn trống. Số khách bắt buộc; SĐT tùy chọn. Có SĐT thì tra cứu, chỉ hiện tên đăng ký khi chưa có hồ sơ. Không bắt nhân viên phân loại khách cũ/mới.
2. **Gọi món**: tìm tên/mã không dấu, lọc nhóm, thêm món bằng nút tròn bên cạnh từng món. Danh sách dùng ảnh thu nhỏ thật nếu có; món chưa có ảnh hiện biểu tượng. Ghi chú chế biến riêng từng món. Thêm món không tải lại menu hoặc tự bật bàn phím.
3. **Order**: xem khách/ghi chú bàn, sửa món mới, gửi bếp, xác nhận món đã mang ra. Chỉ một nút chính ở đáy màn hình, thay đổi theo trạng thái công việc.
4. **Thanh toán**: phục vụ gửi yêu cầu; người có `orders.collect_payment` thu trực tiếp từ cùng order khi tất cả món còn hiệu lực đã phục vụ. Không phải chọn một quy trình thu ngân khác.

Điều hướng phục vụ: **Bàn · Việc cần làm · Cá nhân**. Thu ngân: **Bàn · Chờ thanh toán · Hóa đơn · Cá nhân**, theo bản mẫu `?view=cashier`. Màn `/sales/mobile/?page=payments` đưa hóa đơn đủ điều kiện lên trước; hóa đơn còn món chưa phục vụ hoặc giao dịch online chờ chỉ có nút kiểm tra order. Việc cần làm vẫn truy cập từ sơ đồ bàn và danh sách thanh toán, gom món chờ mang, QR nhận bàn/gọi món/phục vụ, lịch đặt hôm nay. Yêu cầu phục vụ không phải bước bắt buộc trước gửi bếp.

Giao diện dùng phong cách bản mẫu `design/staff-mobile`: header trắng, nền sáng, xanh ngọc, thẻ bo góc, bàn hai cột và danh sách món có ảnh. Không đưa bộ chọn vai trò, số liệu minh họa hoặc ca làm giả từ bản mẫu vào ứng dụng thật.

Thu ngân có cả `manage_order` và `collect_payment`: vẫn nhận bàn/gọi món được. Các nút lấy từ quyền tài khoản thật; không có bộ chọn vai trò trong ứng dụng.

## Vào màn mobile

- Form đăng nhập nhận diện chiều rộng điện thoại và đưa phục vụ/thu ngân đến `/sales/mobile/`.
- Nếu mở `/sales/` trên điện thoại, giao diện bán hàng chuyển sang mobile, giữ bàn/order đang chọn.
- Desktop tiếp tục dùng giao diện cũ. Cá nhân → Mở giao diện desktop dùng `/sales/?desktop=1` để chủ động xem bản desktop trên điện thoại.
- Quản lý, bếp và kho vẫn giữ điểm vào làm việc hiện tại. Quản lý có thể mở mobile bán hàng bằng quyền được cấp.

## Thanh toán và an toàn dữ liệu

- Mobile chỉ nhận **CASH / BANK_TRANSFER**. Không có VNPAY trong lựa chọn mobile; backend VNPAY desktop vẫn giữ nguyên. Nếu cùng order đang có giao dịch online chờ ở desktop, mobile chặn thu thêm để không thu trùng.
- Server khóa theo thứ tự seating → menu → actor → order, kiểm tra `expected_revision`, quyền thu và trạng thái món.
- Mã ưu đãi được xem trước qua endpoint quote có quyền thu. Khi chốt, server tính lại và so sánh `reviewed_total`; giá trị từ trình duyệt không quyết định số tiền hóa đơn.
- Tiền mặt phải đủ số cần thu, nguyên đồng và hữu hạn; chuyển khoản bắt buộc xác nhận đã nhận đủ tiền. Số tiền khách đưa/tiền thừa được giữ trong session cho màn kết quả; sổ thu vẫn ghi đúng tiền thực thu cho hóa đơn.
- Chuẩn bị chờ thanh toán và ghi nhận tiền nằm trong cùng transaction mobile. Lỗi chốt không để lại thao tác chuẩn bị dở dang.
- Tách/ghép dùng services hiện có. Chỉ hóa đơn chưa phát sinh giao dịch được sắp xếp lại; mỗi hóa đơn tách thu độc lập, bàn chỉ cần dọn sau hóa đơn cuối.
- Hóa đơn cũ đã thu một phần: giữ điều kiện đã khóa, chỉ thu phần còn lại. Không đổi mã ưu đãi hoặc số tiền gốc.
- Mở bàn + tạo khách mới, hoặc mở bàn + xác nhận QR, đều atomic. Nếu nhận bàn thất bại, hồ sơ khách/order mới cũng rollback.
- Khách đặt trước: kiểm tra mã/tên/SĐT và phiên bản lịch, dùng services nhận khách, giữ liên kết khách. Ghi chú phục vụ được nhập rõ lúc nhận khách; không giả định `Booking` có cột note.

## Mất mạng, đồng bộ và hiệu năng

- Không tự thử lại POST. Nếu chưa rõ kết quả, khóa thao tác mới và yêu cầu cập nhật để kiểm tra trước khi tiếp tục.
- Poll ETag dùng chung với POS/bếp; tab ẩn dừng thăm dò. Chỉ cập nhật khi state thay đổi.
- Không thay nội dung khi đang nhập, có hộp xác nhận hoặc đang thanh toán; hiện nút cập nhật. Giữ ghi chú chưa lưu và tiền đang nhập khi cập nhật cùng order, đồng thời yêu cầu xác nhận lại chuyển khoản.
- Trang menu/order/checkout không tải toàn bộ dữ liệu bàn và danh sách công việc. Menu dùng thumbnail khi có, ảnh tải lazy và cache chuỗi tìm kiếm.
- Chưa có PWA hoặc hàng đợi offline. Tải lại toàn bộ trình duyệt không đảm bảo giữ phần nhập chưa gửi.

## Kiểm tra

```powershell
$env:DJANGO_SETTINGS_MODULE='QLNH.test_settings'
.venv/Scripts/python.exe scripts/run_tests.py apps.orders apps.accounts apps.bookings apps.customers
node --test scripts/test_staff_polling.cjs scripts/test_table_live.cjs scripts/test_audio_notify.cjs
.venv/Scripts/python.exe scripts/verify_staff_mobile_browser.py
```

Hai script Python tạo database thử nghiệm với tên riêng, không dùng dữ liệu nhà hàng đang vận hành.
Script browser chạy Chrome headless và kiểm tra luồng thật (không mock API), sau đó đối chiếu số order/payment/invoice trong database thử nghiệm. Các endpoint session/fixture chỉ có trong WSGI wrapper của script, không đăng ký trong `QLNH.urls`.

Ảnh và kết quả kiểm tra nằm ở `artifacts/staff-mobile/` (đã gitignore). Chạy deploy như quy trình Django hiện có và `collectstatic` để đưa CSS/JS mới lên máy chủ; chưa thực hiện triển khai production trong thay đổi này.
