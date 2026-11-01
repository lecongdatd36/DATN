# Chấm điểm và đề xuất bàn phù hợp

Hoàn thiện ngày 01/11/2026 trên nhánh `feat/table-recommendations`, đáp ứng mục 3.5 của đề cương: kiểm tra bàn trống, thời gian, số khách, tính điểm và đề xuất bàn. Đây là thuật toán best fit có giải thích, không phải mô hình học máy hoặc độ tin cậy dự báo.

## Cách sử dụng

- Nhân viên có quyền Đặt bàn: mở **Đặt bàn → Tìm bàn phù hợp**, nhập giờ đến, số khách và thời lượng. Kết quả có đề xuất hàng đầu, thứ hạng, điểm và số chỗ dư. **Chọn bàn** chuyển sang form tạo đặt bàn với thông tin đã điền.
- Khách hàng: mở **Đặt bàn → Kiểm tra bàn** (`/reservations/check/`), nhập thông tin và khu vực mong muốn nếu có. Hiển thị tối đa 3 bàn. **Tiếp tục đặt bàn** giữ lại giờ đến, số khách, thời lượng và khu vực đã chọn.
- Kết quả tìm kiếm chỉ tham khảo. Khi khách gửi yêu cầu, server tìm lại bàn theo cùng thuật toán trong transaction có khóa, rồi kiểm tra và lưu. Không giữ chỗ khi chỉ mở trang tìm kiếm; không tin điểm hoặc mã bàn do trình duyệt gửi lên.

## Điều kiện bắt buộc trước khi chấm điểm

1. Bàn và khu vực còn hoạt động; số chỗ lớn hơn hoặc bằng số khách.
2. Trạng thái bàn là `AVAILABLE` hoặc `RESERVED`; loại `OCCUPIED` và `CLEANING`.
3. Không có đặt bàn `PENDING`, `CONFIRMED` hoặc lượt `SEATED` chồng lấn khoảng thời gian yêu cầu. Khoảng được xét theo `[giờ đến, giờ kết thúc)`: lượt trước kết thúc đúng lúc lượt sau bắt đầu không bị coi là chồng lấn.
4. Lượt khách vẫn `SEATED` thì tiếp tục loại bàn đó, kể cả đã quá giờ dự kiến hoặc trạng thái bàn chưa đồng bộ. Không tự coi khách đã rời bàn chỉ vì hết giờ dự kiến.
5. Nếu chọn khu vực, chỉ xếp bàn thuộc khu vực đó.

Chính sách đề xuất hiện ưu tiên bàn đã sẵn sàng: bàn đang có khách hoặc cần dọn chưa được đề xuất kể cả khi tìm cho giờ tương lai. Không tự ước đoán giờ khách rời bàn hoặc thời gian dọn. Việc cho phép nhân viên đặt thủ công vẫn tuân theo các kiểm tra nghiệp vụ hiện có.

Múi giờ giao diện theo cấu hình nhà hàng `Asia/Ho_Chi_Minh`; thời điểm so sánh là datetime có múi giờ. Sử dụng cùng logic chồng lấn hiện có của đặt bàn; không thay đổi thời lượng mặc định, thời gian chờ khách hoặc quyền nhân viên.

## Điểm và cách xếp hạng

```text
điểm = số khách / số chỗ × 100
chỗ dư = số chỗ − số khách
```

Ví dụ 3 khách:

| Bàn | Số chỗ | Điểm | Chỗ dư |
|---|---:|---:|---:|
| B04 | 4 | 75,00 | 1 |
| B08 | 8 | 37,50 | 5 |

Bàn đủ đúng số chỗ được 100 điểm. Với cùng một nhóm khách, ưu tiên sức chứa nhỏ nhất đủ chỗ tương đương tối đa hóa tỷ lệ lấp đầy. Điểm tính bằng Decimal và làm tròn 2 chữ số để hiển thị; thứ tự dựa trên sức chứa gốc, không dựa vào điểm đã làm tròn.

Nếu nhiều bàn cùng sức chứa, thứ tự ổn định theo tên khu vực, mã bàn và khóa chính. Độ phức tạp xếp hạng `O(n log n)` trên các bàn hợp lệ; truy vấn danh sách và khu vực dùng một SQL, không truy vấn từng bàn. Không cần pandas, scikit-learn, API AI hoặc huấn luyện.

Lý do mẫu: **Đủ 3 khách, dư 1 chỗ; không trùng lịch trong thời gian đã chọn.** Điểm là tỷ lệ sử dụng ghế, không phải xác suất bàn còn trống hay mức độ hài lòng của khách.

## Tránh hai yêu cầu cùng nhận một bàn

`create_public_booking()` giữ khóa đặt bàn hiện có bằng PostgreSQL advisory transaction lock. Sau khi lấy khóa mới tính lại đề xuất, lấy bàn hạng 1, kiểm tra lịch và lưu đặt bàn. Transaction tiếp theo đọc trạng thái đã cập nhật, chọn bàn khác hoặc báo không còn bàn. Nhật ký đặt online lưu điểm và lý do tại thời điểm phân bàn.

Nếu ghi nhật ký hoặc lưu thất bại, transaction rollback cả đặt bàn và khách hàng vừa tạo. Không thêm bảng, migration, background worker hoặc thay đổi luồng thanh toán/kho.

## Mã nguồn

- `apps/bookings/table_ranking.py`: tính điểm, thứ hạng và lý do cho các bàn hợp lệ.
- `apps/bookings/selectors.py:recommended_tables`: lọc bàn, trạng thái, khu vực và khoảng thời gian.
- `apps/bookings/services.py:create_public_booking`: tính lại đề xuất trong khóa khi phân bàn online.
- `apps/bookings/views.py`, `templates/bookings/availability.html`, `templates/customer/table_check.html`: kết quả nhân viên và khách; giữ thông tin khi chuyển sang form đặt bàn.
- `apps/bookings/tests/test_recommendations.py`: 23 kiểm thử mới, bao gồm hai kiểm thử chạy đồng thời.
- `scripts/evaluate_table_recommendations.py`: đánh giá xếp hạng bằng các tình huống tổng hợp, không truy cập database.
- `scripts/verify_table_recommendations_browser.py` và runner Chrome: kiểm tra trang thật với database PostgreSQL tạm; các endpoint phục vụ kiểm thử không đăng ký trong URL ứng dụng.

## Đánh giá đã chạy

### Kiểm thử nghiệp vụ và giao diện

81 kiểm thử Đặt bàn, đặt bàn công khai và trang chủ đã qua. Bao gồm: đúng công thức và thứ tự, bàn thiếu chỗ, hòa điểm, khu vực ngừng hoạt động, trạng thái vận hành, lịch kề nhau/qua nửa đêm, khách còn ngồi quá giờ, khu vực yêu cầu, kết quả rỗng, form sai, phân trang, phân quyền, query count, thông tin điền sẵn và rollback khi lỗi.

Lượt kiểm tra cuối trên toàn bộ các phân hệ tài khoản, nhân viên, khách hàng, bàn, đặt bàn, thực đơn, đơn hàng, kho, báo cáo và khách tự phục vụ: **448 kiểm thử qua**. `manage.py check` không có lỗi; không có thay đổi model cần migration.

Hai yêu cầu đồng thời với hai bàn nhận hai bàn khác nhau; nếu chỉ còn một bàn, chỉ một yêu cầu thành công. Kiểm thử đổi trạng thái bàn/khu vực và chống tranh lịch hiện có của phân hệ vẫn qua.

Chrome cục bộ: 8 kiểm tra qua trên giao diện thật, gồm kết quả nhân viên/khách, điểm và thứ tự, liên kết giữ thông tin, kết quả rỗng và không tràn ngang toàn trang ở chiều rộng 390 px. Đã mở và xem ảnh desktop/mobile. Database kiểm thử được xóa sau khi chạy; preview và chuyển form không tạo đặt bàn. Trình duyệt tích hợp của công cụ gặp lỗi kết nối, nên sử dụng Chrome chạy nền với profile riêng; không dùng phiên đăng nhập hoặc dữ liệu production.

### Đánh giá xếp hạng tái lập

200 tình huống tổng hợp, seed 42; mỗi tình huống có sức chứa bàn thuộc 2/4/6/8/10/12 chỗ và nhóm 1–14 khách:

| Chỉ số | Kết quả |
|---|---:|
| Tình huống có bàn đủ chỗ | 158 |
| Tình huống không có bàn đủ chỗ, trả rỗng đúng | 42 |
| Số chỗ dư trung bình của đề xuất | 1,1646 |
| Baseline chọn bàn đầu tiên đủ chỗ trong đầu vào | 2,9114 |
| Cách chọn sức chứa nhỏ nhất của hệ thống trước đây | 1,1646 |

Trong 158 tình huống có bàn, đề xuất luôn có số chỗ dư nhỏ nhất và không đổi khi đảo thứ tự đầu vào. Thuật toán cho cùng lựa chọn với cách best fit đã có ở bước phân bàn online trước đây; chức năng mới bổ sung điểm, lý do, hiển thị và thống nhất nơi áp dụng, không tuyên bố cải thiện so với chính baseline best fit đó.

Đây là kiểm tra tổng hợp về xếp hạng các ứng viên; điều kiện lịch, trạng thái và tranh chấp được kiểm tra riêng bằng Django. Chưa đo mức hài lòng hoặc hiệu quả kinh doanh trên dữ liệu vận hành thực tế. Thuật toán tối ưu chỗ dư cho một lượt, chưa tối ưu toàn bộ lịch tương lai hoặc ghép nhiều bàn.

## Chạy lại

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py test apps.bookings apps.customer_portal.tests.test_reservations apps.customer_portal.tests.test_home --settings=QLNH.test_settings --noinput
.\.venv\Scripts\python.exe -X utf8 scripts\evaluate_table_recommendations.py
.\.venv\Scripts\python.exe -X utf8 scripts\verify_table_recommendations_browser.py
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Kết quả benchmark được lưu thành file tên mới trong `artifacts/ai/table-recommendations/`; ảnh và kết quả trình duyệt ở thư mục con `browser/`. Các artifact được gitignore. Script trình duyệt hiện dùng Chrome và Node trên Windows; không cần cài thư viện vào môi trường AI. Chưa push, merge hoặc triển khai hosting trong lần thực hiện này.
