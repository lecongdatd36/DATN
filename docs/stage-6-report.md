# Giai đoạn 6 — Đặt bàn

Ngày cập nhật: 20/09/2026.

## Chức năng

- App `bookings`: Booking và BookingActivityLog, form/service/selector/view riêng; tích hợp menu, trang cá nhân và nút Đặt bàn từ chi tiết khách hàng.
- Một lịch gồm khách hàng đã lưu (tra theo số điện thoại), một bàn, số khách và giờ đến. Thời lượng được điền mặc định, chỉ mở mục điều chỉnh khi cần; hệ thống tự tính giờ kết thúc dự kiến. Không thêm trường email. Chưa có ghép bàn hoặc nhiều bàn trong cùng phiếu.
- Mã tự sinh dạng `DB000001`. Lưu tên/điện thoại khách tại thời điểm đặt để lịch sử không thay đổi khi hồ sơ khách đổi thông tin.
- Danh sách tìm theo mã đặt, tên/điện thoại khách (có chuẩn hóa +84), mã bàn; lọc ngày đến theo giờ Việt Nam, bàn, trạng thái; phân trang 20 dòng.
- Tìm bàn phù hợp theo khoảng giờ và số khách; kết quả loại bàn/khu vực ngừng sử dụng, thiếu chỗ hoặc trùng lịch. Nút chọn bàn điền sẵn dữ liệu vào form đặt. Tra cứu không giữ chỗ; service kiểm tra lại khi lưu.
- Khách mới được thêm ở trang Khách hàng (tab mới), sau đó điền số điện thoại để đặt; không tạo trùng hồ sơ qua một luồng khách khác.

## Vòng đời

| Trạng thái hiện tại | Thao tác được phép |
| --- | --- |
| Chờ xác nhận | Sửa, xác nhận, hủy, đánh dấu không đến từ giờ hẹn |
| Đã xác nhận | Sửa, nhận khách trong giờ hẹn, hủy, đánh dấu không đến từ giờ hẹn |
| Đang phục vụ | Hoàn tất khi khách rời bàn |
| Hoàn tất / Đã hủy / Không đến | Chỉ xem |

Lịch mới chờ xác nhận cũng giữ chỗ. Sửa thông tin lịch đã xác nhận đưa về chờ xác nhận lại; lưu không đổi thông tin không ghi log mới và không thay trạng thái. Khi thông tin khách hiện tại đã đổi, lưu lại sẽ cập nhật snapshot và cần xác nhận lại.

Giờ đến mới phải ở tương lai, kết thúc sau giờ đến. Có thể chỉnh một lịch đang trong giờ hẹn nếu giữ nguyên giờ đến và chưa hết giờ. Nhận khách chỉ từ giờ đến đến trước giờ kết thúc; khách đến sớm cần sửa giờ và xác nhận lại. Không tự chuyển quá hạn sang không đến, không tự hoàn tất khách đang ngồi.

Hai lịch được nối tiếp đúng mốc kết thúc/bắt đầu. Lịch đã hủy/không đến/hoàn tất giải phóng khung giờ. Nếu khách đã nhận vẫn ngồi quá giờ dự kiến, lượt sau chưa được nhận khách cho đến khi lượt trước hoàn tất. Thông báo quá giờ hiện ở chi tiết lịch; hoàn tất chưa đồng nghĩa thanh toán vì module thanh toán chưa có.

## Điều chỉnh thời lượng theo phản hồi người dùng

- Bỏ trường nhập `ends_at` khỏi form đặt/tìm bàn; dùng `duration_minutes`, ban đầu 120 phút. Thời lượng riêng của lịch có thể điều chỉnh từ 1–1440 phút; máy chủ tính thời điểm kết thúc và vẫn kiểm tra trùng lịch. Trường ends_at giả trong POST không được dùng để thay đổi khoảng giờ.
- JavaScript xem trước giờ đến–kết thúc theo múi giờ Việt Nam, không phụ thuộc múi giờ máy người dùng. Đây chỉ là xem trước; backend hoạt động khi không có JavaScript.
- `BookingSettings` là cấu hình một bản ghi, có kiểm tra phạm vi tại database. Trang `/dat-ban/cau-hinh/` dành cho quyền `configure_bookings`, cấp cho MANAGER và superuser. Nhân viên vẫn chỉnh thời lượng từng lịch qua quyền đặt bàn hiện có.
- Lưu cấu hình có phiên bản chống ghi đè từ form cũ, kiểm tra lại quyền, nhật ký và transaction. GET không ghi; lỗi nhật ký rollback cấu hình. Chỉ lịch mới nhận mặc định mới, lịch đã lưu giữ giờ kết thúc và dùng lại thời lượng riêng khi sửa.
- Đổi nhãn `SEATED` thành **Đang phục vụ**, giữ mã trạng thái và dữ liệu lịch hiện có.
- Danh sách hiển thị tối đa 10 lượt quá giờ; kèm lịch kế tiếp cùng bàn nếu có. Chi tiết lượt quá giờ và lịch kế tiếp đều có cảnh báo, để nhân viên đổi bàn hoặc trao đổi lại giờ đến. Không tự hoàn tất khách, tự kéo dài lịch hoặc tự dời lịch sau.

## Phân quyền và lịch sử

- Superuser đang hoạt động, Quản lí, Phục vụ và Thu ngân: xem/tạo/sửa/chuyển trạng thái đặt bàn.
- Chỉ Superuser/Quản lí xem nhật ký; Bếp/Kho không truy cập đặt bàn.
- Quyền `bookings.view_booking`, `manage_booking`, `view_bookingactivitylog`; kiểm tra tại view và actor được đọc lại từ database tại service.
- Thay đổi bằng POST có CSRF; GET xác nhận không ghi dữ liệu. Form sửa/chuyển trạng thái mang phiên bản lịch để từ chối dữ liệu cũ, kể cả người khác sửa một lịch vẫn đang chờ xác nhận.
- Thay đổi và log cùng transaction, lỗi log rollback dữ liệu. Snapshot tên đăng nhập người thao tác còn lại sau khi tài khoản bị xóa.
- Không có xóa lịch. Quan hệ lịch → khách, lịch → bàn và log → lịch dùng PROTECT; khách/bàn có lịch vẫn được bảo vệ cả khi lịch đã hủy. Admin chỉ đọc.

## Đồng bộ với khu vực/bàn

`core/seating_lock.py` tập trung khóa giao dịch PostgreSQL dùng chung cho service danh mục và lịch đặt. Nhờ cùng thứ tự khóa, hai người không thể cùng nhận một khung giờ còn trống; thao tác ngừng khu vực không chen giữa kiểm tra và lưu lịch.

Khu vực/bàn có lịch chờ xác nhận/đã xác nhận chưa hết giờ hoặc lịch đã nhận khách bị chặn ngừng sử dụng. Bàn có các lịch này không chuyển khu vực, không giảm số chỗ xuống dưới số khách đã hẹn. Lịch đã nhận vẫn bảo vệ dù quá giờ dự kiến. Khi hủy/hoàn tất/không đến, hoặc lịch chưa nhận đã hết giờ, ràng buộc danh mục được giải phóng.

Database có check constraints thời gian, số khách và trạng thái, cùng index tra lịch. Chống trùng khoảng thời gian nằm ở service và khóa giao dịch; ghi trực tiếp bằng SQL/ORM ngoài service chưa có exclusion constraint bảo vệ. Admin bị chặn ghi để không bỏ qua service. Khóa chung phù hợp quy mô hiện tại, có thể tách khóa theo bàn khi lưu lượng tăng và vẫn phải bảo đảm thứ tự khóa với khu vực.

## Kiểm chứng

- **157/157 test đạt** trên PostgreSQL: 118 test module khác và 39 test Đặt bàn. Chạy trên database tên riêng, migrate từ đầu, dọn sau khi xong.
- Kiểm tra quyền ở UI/GET/POST/service, thu hồi quyền, khóa actor, superuser không có hồ sơ, CSRF và Admin chỉ đọc.
- Kiểm tra các dạng chồng giờ và hai lịch nối tiếp; khác bàn; bàn/khu vực ngừng; sức chứa; giờ sai/quá khứ; khách/bàn không tồn tại.
- Kiểm tra vòng đời, nhận khách sớm/trễ, không đến trước giờ, khách ngồi quá giờ chặn nhận lượt sau, sửa cần xác nhận lại, trạng thái cuối không sửa, form cũ không ghi đè.
- Kiểm tra tìm/lọc/phân trang, datetime-local theo giờ Việt Nam, tìm bàn và điền sẵn form, lỗi nghiệp vụ hiển thị đúng, bảo vệ khách/bàn, giữ lịch sử, rollback.
- Hai bài dùng các kết nối PostgreSQL riêng: đặt đồng thời cùng bàn/giờ chỉ một lần thành công; đặt bàn đồng thời ngừng khu vực chỉ một thao tác phù hợp được thực hiện.
- 11 test thời lượng/cấu hình mới bao phủ mặc định, tùy chỉnh, qua nửa đêm, trùng lịch, giữ thời lượng cũ, POST giả giờ kết thúc, quyền cấu hình, CSRF, form cũ, rollback, ràng buộc database và cảnh báo quá giờ không tự đổi trạng thái.
- Kiểm tra script xem trước bằng Node với múi giờ máy giả lập America/New_York: hiển thị giờ Việt Nam đúng, qua nửa đêm, ô thời lượng trống dùng mặc định và giá trị sai có thông báo. Đây là kiểm tra logic script, không phải kiểm chứng bố cục trình duyệt.
- `manage.py check` không báo vấn đề; `makemigrations --check --dry-run` không có thay đổi thiếu migration.
- Migrations `bookings.0001_initial`, `0002_seed_booking_permissions`, `0003_booking_revision` đã áp dụng trên database ứng dụng. MANAGER có 3 quyền, WAITER/CASHIER có 2 quyền, KITCHEN/INVENTORY không có quyền bookings.
- Bổ sung và áp dụng `0004_alter_booking_status_bookingsettings_and_more`, `0005_seed_booking_settings`: cấu hình mặc định 120 phút, log cấu hình, nhãn trạng thái và quyền configure_bookings riêng cho MANAGER. Không thay đổi giờ của các lịch cũ. Sau bổ sung, MANAGER có thêm quyền cấu hình; các nhóm nhân viên không có quyền này.
- Render trong transaction chỉ đọc: danh sách/tạo/tìm bàn phù hợp, danh sách bàn/khu vực/khách và trang cá nhân đều trả 200. Không tạo lịch thử hay sửa dữ liệu người dùng trên database ứng dụng.
- Sau đổi thời lượng, render danh sách/tạo/tìm bàn/cấu hình đều trả 200; form tạo và tìm bàn có duration_minutes, không có input ends_at, nạp script xem trước. Kiểm tra cấu hình và quyền trên database ứng dụng bằng transaction chỉ đọc.
- Chưa kiểm chứng bố cục bằng trình duyệt trực quan; công cụ Browser đã lỗi khởi tạo trong phiên làm việc. Các kiểm tra HTTP/template không thay thế kiểm chứng bố cục.

## Sửa đồng bộ trạng thái trang Bàn

- Lỗi: trang Bàn dùng cờ cấu hình `is_active` của bàn/khu vực để hiển thị “Có thể sử dụng”, nên không phản ánh lượt khách đang phục vụ.
- Đã đổi sang trạng thái suy ra từ Booking khi truy vấn danh sách: có SEATED luôn là Đang phục vụ, không tự trống khi quá ends_at; lịch PENDING/CONFIRMED đang trong khoảng giờ là Đang giữ chỗ; ngoài ra bàn mở là Trống hiện tại. Bàn/khu vực đóng hiển thị Ngừng sử dụng, nhưng vẫn ưu tiên báo khách đang ngồi nếu có dữ liệu bất thường.
- Hiển thị lịch tương lai gần nhất riêng, không coi đặt trước cho ngày sau là đang chiếm bàn. Có liên kết xem lượt khách/lịch đặt cho người có quyền xem đặt bàn.
- Bộ lọc có Trống hiện tại/Đang phục vụ/Đang giữ chỗ/Ngừng sử dụng và Đang mở (mọi trạng thái). Giữ phân trang và bộ lọc khu vực; subquery tránh tải từng lịch bằng truy vấn riêng cho mỗi bàn.
- Không đổi cờ vận hành, không thêm trạng thái lưu trùng, không sửa dữ liệu lịch thật và không cần migration. Trang hiển thị thời điểm kiểm tra và liên kết cập nhật; tab đang mở chưa tự nhận thay đổi nền.
- Thêm 8 kiểm thử hồi quy; **67/67 test Seating + Bookings đạt** sau sửa. Bao phủ nhận khách/hoàn tất qua service, quá giờ, lịch tương lai, giữ chỗ, hết giờ, lịch hủy/không đến/hoàn tất, ưu tiên trạng thái, lọc/phân trang, quyền liên kết và số truy vấn. Trước khi đưa lên GitHub, đã chạy lại toàn bộ dự án: **165/165 test đạt** trên database PostgreSQL kiểm thử riêng.
- Đối chiếu đọc trực tiếp database ứng dụng: lúc kiểm tra không có lịch SEATED, một bàn trả trạng thái empty; render `/ban/` trả 200 và không còn nhãn “Có thể sử dụng”. Trường hợp đang phục vụ được xác minh bằng kiểm thử trên database riêng. `manage.py check`, kiểm tra model/migration và diff đều đạt.

## Phần tiếp theo

Thực đơn (nhóm món, món, đơn vị, giá bán, trạng thái phục vụ), rồi gọi món/đơn hàng gắn với bàn và lượt khách. Khi có đơn hàng cần liên kết việc hoàn tất lượt khách với tình trạng đơn và thanh toán; không cho thao tác hoàn tất bỏ qua hóa đơn chưa xử lý. Chưa có ghép bàn, cọc, thông báo SMS/email hoặc tác vụ tự động hết hạn.
