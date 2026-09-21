# Giai đoạn 7 — Thực đơn

Ngày cập nhật: 21/09/2026.

## Chức năng và cách dùng

App `menu` có model, form, selector, service, view, template, migration và kiểm thử riêng. Đường dẫn chính `/thuc-don/`; liên kết xuất hiện trong menu và trang tài khoản theo quyền.

1. Quản lí tạo nhóm món và đơn vị tính đang sử dụng.
2. Thêm món gồm mã, tên, nhóm, đơn vị, giá bán, trạng thái và mô tả tùy chọn. Mã duy nhất, chuẩn hóa chữ hoa, tối đa 20 ký tự; tên tối đa 150 ký tự, mô tả tối đa 2.000 ký tự. Tên nhóm/đơn vị không trùng khi khác chữ hoa/thường và được gộp khoảng trắng.
3. Giá lưu bằng Decimal, đơn vị đồng, từ 1 đến 999.999.999, không chấp nhận phần lẻ, số âm, giá trị vô hạn hoặc NaN. Hiển thị tách hàng nghìn, ví dụ 85.000 đ / Đĩa.
4. Danh sách tìm mã/tên, lọc nhóm/đơn vị/trạng thái phục vụ; phân trang 20 dòng. Chi tiết hiển thị thông tin, mô tả, giá, trạng thái và thời điểm cập nhật.
5. Quản lí sửa thông tin/giá/ngừng bán. Bếp và Quản lí có màn hình riêng cập nhật còn/hết món. Mỗi lần thay đổi có nhật ký; lưu không đổi dữ liệu không tăng phiên bản hoặc tạo nhật ký thừa.

## Trạng thái phục vụ

| Hiển thị | Ý nghĩa |
| --- | --- |
| Còn món | Món còn phục vụ; nhóm và đơn vị đều đang sử dụng |
| Hết món | Tạm hết; Bếp hoặc Quản lí chuyển lại Còn món khi có lại |
| Ngừng bán | Quản lí ngừng bán món; Bếp không được tự mở lại |
| Tạm ngừng theo danh mục | Món chưa ngừng bán riêng nhưng nhóm hoặc đơn vị đã ngừng sử dụng |

Ngừng nhóm/đơn vị không sửa hàng loạt trạng thái riêng của món. Mở lại danh mục giữ món hết ở trạng thái hết, món ngừng bán vẫn ngừng bán. Món mới hoặc chuyển danh mục phải chọn danh mục đang sử dụng; mở bán lại món đã ngừng cũng yêu cầu nhóm/đơn vị hoạt động. Vẫn sửa được giá/thông tin của món hiện có trong danh mục đã ngừng, nhưng món tiếp tục bị tạm ngừng theo danh mục.

Chưa có xóa vĩnh viễn món/danh mục trong giao diện. Nhóm và đơn vị được món tham chiếu bằng PROTECT. Việc đặt món ở giai đoạn sau cần kiểm tra `is_orderable` ở máy chủ, trong cùng giao dịch với thay đổi thực đơn.

## Phân quyền

| Vai trò | Xem món/giá | Nhóm, đơn vị, món và giá | Còn/hết món | Nhật ký |
| --- | --- | --- | --- | --- |
| Superuser đang hoạt động | Có | Có | Có | Có |
| Quản lí (MANAGER) | Có | Có | Có | Có |
| Phục vụ / Thu ngân | Có | Không | Không | Không |
| Bếp (KITCHEN) | Có | Không | Có | Không |
| Kho (INVENTORY) | Không | Không | Không | Không |

- Quyền: `view_dish`, `manage_menu`, `change_availability`, `view_menuactivitylog`; thêm quyền tra cứu Admin `view_category`, `view_unit` cho MANAGER.
- Kiểm tra tại view và đọc lại actor tại service, không dựa riêng vào `is_staff` hoặc dữ liệu quyền đã cache trên đối tượng người dùng cũ.
- Bếp gửi thêm trường giá/tên lên màn hình còn/hết cũng không thay đổi được các trường này. Không cho dùng màn hình này để ngừng bán hoặc mở lại món/danh mục đã ngừng.
- Django Admin chỉ đọc, không cho thêm/sửa/xóa hoặc chạy thao tác hàng loạt để bỏ qua service.

## Nhất quán dữ liệu

- Mọi thay đổi bằng POST có CSRF, GET không ghi dữ liệu; phản hồi riêng tư không lưu cache.
- Form sửa danh mục, món và trạng thái mang `expected_revision`; từ chối form cũ thay vì ghi đè thay đổi mới. Kiểm tra phiên bản cả tại service.
- Khóa giao dịch PostgreSQL riêng cho thực đơn (`81723003`) rồi khóa actor/bản ghi; kiểm tra và lưu dưới cùng transaction. Không dùng khóa bàn/đặt bàn cho danh mục thực đơn.
- Nhật ký ghi đối tượng, người thao tác, thời gian; thay đổi món/giá lưu trước và sau. Xóa tài khoản người thực hiện vẫn giữ tên tại thời điểm thao tác. Lỗi nhật ký rollback dữ liệu.
- Database có ràng buộc mã món, tên không trắng, giá, trạng thái và duy nhất tên danh mục không phân biệt hoa/thường. Quy tắc phân quyền, chuẩn hóa, phiên bản và trạng thái danh mục nằm ở service; SQL/ORM ghi trực tiếp có thể bỏ qua các quy tắc này.

## Kiểm chứng

- **204/204 kiểm thử toàn hệ thống đạt**, trong đó **27 kiểm thử Thực đơn**; chạy trên PostgreSQL kiểm thử có tên UUID riêng, migrate từ đầu và dọn sau khi chạy.
- Kiểm tra ma trận quyền UI/GET/POST/service, thu hồi quyền, tài khoản khóa, superuser không có hồ sơ, CSRF, GET không ghi, Admin chỉ đọc.
- Kiểm tra tạo/sửa/ngừng danh mục và món, mã/tên/giá/mô tả, giá trước/sau trong nhật ký, trạng thái còn/hết, danh mục ngừng/mở lại, bộ lọc/phân trang, chống ghi đè, rollback, bảo vệ quan hệ, snapshot người thao tác và escape nội dung HTML.
- Ba bài kiểm thử dùng kết nối PostgreSQL riêng: tạo trùng mã đồng thời chỉ một lần thành công; sửa giá đồng thời đổi trạng thái không ghi đè; ngừng nhóm đồng thời thêm món không để món tiếp tục có thể phục vụ.
- `manage.py check`, `makemigrations --check --dry-run` và `git diff --check` đạt.
- Đã áp dụng `menu.0001_initial` và `0002_seed_menu_permissions` trên database ứng dụng. Đối chiếu quyền thực tế: MANAGER 6 quyền, WAITER/CASHIER 1 quyền, KITCHEN 2 quyền, INVENTORY 0 quyền thực đơn.
- Render trang chủ, danh sách món, thêm món, danh sách/thêm nhóm, danh sách/thêm đơn vị và nhật ký trả 200 trong transaction chỉ đọc trên database ứng dụng. Không tạo món hay dữ liệu mẫu trên database ứng dụng.
- Browser lỗi khởi tạo trong phiên này; chưa kiểm chứng bố cục trực quan. Kiểm thử HTTP/template không thay thế kiểm tra thao tác và bố cục trên trình duyệt.

## Giai đoạn tiếp theo

Gọi món/Đơn hàng gắn với bàn và lượt khách: thêm món đang phục vụ, số lượng, ghi chú, lưu snapshot tên/đơn vị/giá lúc gọi; chuyển yêu cầu xuống Bếp. Khi có đơn hàng phải chặn hoàn tất lượt khách nếu đơn/hóa đơn chưa được xử lý.

Chưa có ảnh món, nhiều mức giá, combo, thuế/phí, công thức nguyên liệu, trừ kho, tính tiền hay thanh toán. Còn/hết món hiện do nhân viên cập nhật, không suy ra từ tồn kho.
