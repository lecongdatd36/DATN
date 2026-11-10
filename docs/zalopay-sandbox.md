# ZaloPay Sandbox v2

Tích hợp dựa trên [API v2 chính thức](https://developer.zalopay.vn/v2/general/overview.html) và [callback Key2](https://docs.zalopay.vn/docs/developer-tools/knowledge-base/callback/). Chỉ kết nối Sandbox; client từ chối endpoint production và không theo HTTP redirect sang máy chủ khác.

## Cấu hình

Các giá trị được đọc từ `.env` qua `QLNH.settings`. Không ghi khóa vào source, trình duyệt, log hoặc dữ liệu giao dịch.

```dotenv
ZALOPAY_APP_ID=<sandbox-app-id>
ZALOPAY_KEY1=<sandbox-key1>
ZALOPAY_KEY2=<sandbox-key2>
ZALOPAY_ENDPOINT=https://sb-openapi.zalopay.vn/v2/create
# Optional: public HTTPS endpoint when the browser opens localhost/LAN.
ZALOPAY_CALLBACK_URL=
```

`ZALOPAY_ENDPOINT` cũng chấp nhận base `https://sb-openapi.zalopay.vn/v2`. API query được suy ra trên cùng endpoint đã xác minh. URL quay về dùng đúng origin của request trình duyệt, không dùng `PUBLIC_BASE_URL` của mã QR bàn để tránh IP LAN cũ. Callback mặc định cũng dùng origin hiện tại; có thể đặt riêng `ZALOPAY_CALLBACK_URL=https://<sandbox-public-host>/payments/zalopay/callback/` để ZaloPay gọi qua HTTPS công khai. Callback LAN/localhost không nhận được từ máy chủ ZaloPay; trang kết quả chủ động truy vấn khi mở và sau mỗi 30 giây khi pending. Không triển khai lên production trong thay đổi này.

## API và giao diện

| Endpoint | Quyền và chức năng |
|---|---|
| `POST /payments/zalopay/create/` | Đăng nhập và quyền `collect_payment`; nhận `order_id`, `promotion_code` tùy chọn, `quick_payment` tùy chọn. Máy chủ tính tiền; không nhận số tiền từ client. |
| `POST /payments/zalopay/deposit/<reservation-access-token>/` | Liên kết riêng của lịch; bắt buộc `revision` hiện tại và `agree=yes`. |
| `POST /payments/zalopay/callback/` | Callback JSON `type=1`, `data` là chuỗi JSON gốc và `mac`; miễn CSRF để máy chủ ZaloPay gọi, bắt buộc xác minh Key2. |
| `GET /payments/zalopay/result/<transaction-token>/` | Trang kết quả đọc trạng thái đã lưu. Query string redirect không thay đổi đơn hay giao dịch. |
| `GET /payments/zalopay/status/<transaction-token>/` | Đọc trạng thái; token UUID là capability riêng tư, không trả thông tin cá nhân khách. |
| `POST /payments/zalopay/query/<transaction-token>/` | Truy vấn server-to-server có MAC Key1, bảo vệ CSRF, giới hạn một lần/30 giây. |

API create nhận JSON hoặc form và trả `app_trans_id`, `amount`, `status`, `order_url`, `result_url`, `state_url`, `query_url`, `sandbox=true`. Trả `201` khi đã ghi nhận một yêu cầu; cần đọc `status`, vì tạo giao dịch thành công không có nghĩa thanh toán thành công. Giao dịch bị cổng từ chối có trạng thái `FAILED`; timeout/không rõ kết quả giữ `PENDING` để truy vấn, không tạo giao dịch khác. Gửi lại cùng đơn đang pending trả mã hiện tại.

POS có lựa chọn **ZaloPay Sandbox**. Mobile có nút chuyển cổng riêng, sử dụng form chuyển trang để không bị AJAX nội bộ giữ lại. Trang lịch đặt bàn có nút ZaloPay Sandbox bên cạnh VNPAY. Khi thiếu cấu hình, lựa chọn bị vô hiệu hóa. Trang kết quả cập nhật trạng thái từ DB mỗi 5 giây và chủ động query mỗi 30 giây khi còn pending; người dùng cũng có thể bấm Kiểm tra lại.

Để đối chiếu giao dịch khi khách đã đóng trình duyệt, chạy theo lịch mỗi phút:

```powershell
.\.venv\Scripts\python.exe manage.py query_pending_zalopay
```

Lệnh xử lý tối đa 100 giao dịch pending/lần, giữ nguyên giao dịch nếu kết nối lỗi. Chưa tự đăng ký lịch chạy trên hosting.

## Xác minh và bảo toàn dữ liệu

- `app_trans_id` gồm ngày `yyMMdd` theo `Asia/Ho_Chi_Minh` và UUID, dài 39 ký tự, có ràng buộc unique.
- Create MAC: Key1 trên `app_id|app_trans_id|app_user|amount|app_time|embed_data|item` với đúng chuỗi JSON đã gửi. Query MAC: Key1 trên `app_id|app_trans_id|key1`. Callback MAC: Key2 trên nguyên chuỗi `data`, so sánh constant-time.
- Bảng `ZaloPayTransaction` liên kết đúng một `OnlinePayment` hoặc `DepositPayment`, lưu pending trước khi gọi mạng. Không giữ khóa DB trong lúc gọi HTTP.
- Callback kiểm tra app ID, mã giao dịch, số tiền nguyên VND, mã đơn trong `embed_data` và `zp_trans_id`. Mã ZaloPay không thể dùng cho hai giao dịch.
- Callback/query đồng thời được tuần tự hóa trong transaction PostgreSQL theo khóa seating → menu → dữ liệu giao dịch. Callback trùng không tạo thêm hóa đơn, phiếu thu, điểm chi tiêu hoặc phiếu hoàn.
- Hóa đơn dùng snapshot giá/ưu đãi và revision của đơn, đối chiếu cọc trước khi chốt. Chỉ thu phần còn thiếu sau cọc. Trong lúc ZaloPay còn pending, chặn thu tiền mặt/chuyển khoản/VNPAY và đổi ưu đãi cho cùng đơn.
- Cọc về sau hạn giữ chỗ được ghi `REVIEW` và tạo yêu cầu hoàn để đối soát; không xác nhận chồng bàn. Hóa đơn đã thay đổi hoặc đã được trả qua giao dịch khác chuyển `REVIEW`, không ghi đè hóa đơn cũ.
- API ZaloPay yêu cầu thời hạn giao dịch mới ít nhất 300 giây. Khi giữ chỗ còn dưới 5 phút, trang lịch giải thích rõ và vô hiệu hóa tạo giao dịch ZaloPay mới; server vẫn kiểm tra lại khi POST. Không tự gia hạn giữ bàn hay đổi giờ hẹn. Giao dịch đã tạo trước đó vẫn có liên kết tiếp tục/truy vấn đến đúng hạn hiện có. Các lỗi đồng ý điều kiện, revision và hạn thanh toán được báo cụ thể, không gộp thành lỗi cấu hình chung.
- Hoàn tiền vẫn theo quy trình đối soát hiện có; chưa tích hợp API hoàn tiền ZaloPay. Không xử lý hóa đơn đã có khoản thu một phần qua cổng mới.

## Migration và kiểm tra

Migration `orders.0022_zalopay_sandbox` tạo bảng mới; thay đổi choices của `Payment.method` không phát sinh SQL sửa dữ liệu. Đã áp dụng trên PostgreSQL local sau khi kiểm tra kế hoạch chỉ có migration này. Fingerprint toàn bộ hàng của các bảng order, order item, invoice, payment, online payment, reservation, deposit và refund trước/sau không đổi. Không chạy migration trên DB remote/production.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
$env:DJANGO_SETTINGS_MODULE='QLNH.test_settings'
.\.venv\Scripts\python.exe scripts/run_tests.py apps.orders apps.reservations
```

Test settings bỏ thông tin ZaloPay trong `.env`; các unit test chỉ bật dummy credentials và mock HTTP. Bao gồm thành công/thất bại/chưa thanh toán, chữ ký sai, sai tiền/mã đơn, callback trùng, mất callback/query, timeout, chặn production, cọc về muộn, khấu trừ cọc và ba ca đồng thời.

Kết quả tích hợp ban đầu: **551 test** trong bộ kiểm thử mặc định qua, gồm **25 test ZaloPay**. Bản sửa URL quay về thêm hai test; bản sửa thời gian giữ chỗ thêm hai test. Nhóm ZaloPay hiện có **29 test**; lượt kiểm tra mới nhất gồm ZaloPay và reservations có **67 test qua**. Django check, kiểm tra migration consistency và cú pháp JavaScript đều qua.

Kiểm tra với API Sandbox chính thức, dùng DB PostgreSQL kiểm thử riêng rồi dọn:

```powershell
$env:DJANGO_SETTINGS_MODULE='QLNH.settings'
.\.venv\Scripts\python.exe scripts/verify_zalopay_sandbox.py
```

Kết quả thực tế: create trả `return_code=1`, nhận checkout URL Sandbox; query trả `return_code=3` (chưa trả tiền/đang xử lý). Không thanh toán hoặc tạo hóa đơn. Thông tin kết nối lấy từ `.env`; artifact chỉ lưu mã kết quả đã lược bỏ thông tin nhạy cảm ở `artifacts/zalopay/sandbox-smoke.json`.

Kiểm tra trình duyệt với HTTP provider giả lập, callback và chốt hóa đơn của ứng dụng thật, DB dùng một lần:

```powershell
$env:DJANGO_SETTINGS_MODULE='QLNH.settings'
.\.venv\Scripts\python.exe scripts/verify_zalopay_sandbox.py --browser
```

Đã kiểm tra lựa chọn POS desktop, nút mobile chuyển trang, redirect còn pending, query chưa trả tiền và callback xác nhận đúng một hóa đơn. Ảnh ở `artifacts/zalopay/browser/`. Chưa thực hiện một lượt trả tiền trọn vẹn qua ứng dụng ZaloPay Sandbox và callback đi từ máy chủ ZaloPay tới website công khai; cần triển khai callback trước khi kiểm thử bước đó.

## Các file được bổ sung hoặc sửa cho tích hợp này

- Cấu hình/route: `.env.example`, `QLNH/settings.py`, `QLNH/test_settings.py`, `QLNH/urls.py`.
- Dữ liệu: `apps/orders/models.py`, `apps/orders/migrations/0022_zalopay_sandbox.py`.
- API/client/service: `apps/orders/zalopay.py`, `apps/orders/zalopay_services.py`, `apps/orders/zalopay_views.py`, `apps/orders/zalopay_urls.py`.
- Kết nối luồng cũ: `apps/orders/services.py`, `apps/orders/sales_views.py`, `apps/reservations/services.py`, `apps/reservations/views.py`.
- Đối soát: `apps/orders/management/commands/query_pending_zalopay.py`.
- Giao diện: `templates/staff/sales/index.html`, `templates/staff/sales/zalopay_result.html`, `templates/staff/mobile/checkout.html`, `templates/reservations/detail.html`, `templates/reservations/_zalopay_deposit_button.html`, `static/js/staff-mobile.js`, `static/js/zalopay-status.js`.
- Kiểm thử: `apps/orders/tests/test_zalopay.py`, `scripts/verify_zalopay_sandbox.py`, `scripts/run_zalopay_chrome.cjs`.
- Tài liệu: `docs/zalopay-sandbox.md`.

Các thay đổi khác đã có trong workspace được giữ nguyên.
