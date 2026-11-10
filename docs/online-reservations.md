# Đặt bàn online, món trước, cọc và chuẩn bị theo giờ

Triển khai trên nhánh `feature/online-booking-preorder`. Bản nghiệp vụ làm căn cứ: [đề xuất đã duyệt](nghiep-vu-dat-ban-dat-mon-va-dat-coc.md). Tính năng đang ở source/local, chưa triển khai hosting hoặc chạy giao dịch ngân hàng thật.

## Điểm vào

| Công việc | URL |
|---|---|
| Nhập thông tin đặt bàn | `/reservations/online/` |
| Hỏi có muốn đặt món trước, sau khi có thông tin cuộc hẹn | `/reservations/online/dat-mon-truoc-khong/` |
| Thực đơn có ảnh và giỏ món riêng | `/reservations/online/chon-mon/` |
| Kiểm tra lịch và giỏ trước khi gửi | `/reservations/online/xac-nhan/` |
| Tra cứu mã OL; mã DB cũ vẫn hỗ trợ | `/reservations/online/tra-cuu/` |
| Theo dõi và trả cọc | Liên kết riêng có UUID được cấp sau khi gửi |
| Tiếp nhận, chốt, nhận khách, hủy/hoàn | `/reservations/online/quan-ly/` |
| Chính sách và danh mục món được chuẩn bị trước | `/reservations/online/chinh-sach/` |
| Bếp chuẩn bị trước khi khách tới | `/reservations/online/bep/` |

Menu Đặt bàn của trang khách và liên kết chatbot chuyển tới luồng mới. Các URL đặt bàn/tra cứu DB cũ vẫn được giữ tương thích. Đặt bàn nội bộ, walk-in và QR tại bàn tiếp tục dùng luồng đang có.

## Cách dùng

1. Quản lý mở Chính sách. Mặc định cọc A 100.000đ, B 50% tiền món, giữ chỗ chờ cọc 10 phút, bản chốt B 30 phút, yêu cầu B trước ít nhất 60 phút. Chọn rõ các món được phép chuẩn bị trước; mặc định chưa tự cho phép món nào. Chính sách được chụp lại trong từng yêu cầu, thay cấu hình không làm thay điều kiện yêu cầu cũ.
2. Khách không cần tài khoản, vào thẳng **form đặt bàn**, nhập lịch/số khách/liên hệ rồi mới được hỏi **“Bạn có muốn đặt món trước không?”**. Chọn **Không** đi tới xác nhận, gọi món khi đến; chọn **Có** đi tới thực đơn có ảnh và giỏ món riêng, bắt buộc chọn ít nhất một món. Cách chuẩn bị món chỉ được chọn ở bước hỏi đặt món trước, mặc định đến mới chế biến. Thực đơn hỗ trợ tìm theo tên/nhóm, tăng/giảm/xóa món, ghi chú và tạm tính. Quay lại sửa giữ dữ liệu trong phiên; đổi sang chỉ đặt bàn xóa giỏ. Trước khi gửi chỉ lưu bản nháp, chưa giữ chỗ/thu cọc. Máy chủ kiểm tra lại lịch, món và giá trước khi tạo yêu cầu; mã gửi theo phiên chống tạo trùng. Hai URL chọn luồng cũ chuyển về cùng form đặt bàn; tab cũ vẫn gửi được qua POST tương thích.

Giao diện đặt bàn dùng Segoe UI/Arial hỗ trợ tiếng Việt. Sau khi thêm/sửa JavaScript hoặc CSS, chạy `manage.py collectstatic --noinput` để máy chủ phục vụ đầy đủ tài nguyên mới. Kiểm thử trình duyệt đọc tài nguyên từ thư mục đã thu thập và bấm nút số lượng bằng sự kiện chuột thực, bao gồm nút +/− ngay trong giỏ trên điện thoại.
3. **A — Đến mới chế biến:** hệ thống giữ bàn ở lịch PENDING có hạn, cấp liên kết để trả cọc. Nhận cọc hợp lệ thì tự xác nhận, chưa mở đơn/nhận khách hoặc trừ kho.
4. **B — Chuẩn bị theo giờ:** chỉ tạo yêu cầu chờ nhà hàng xem, chưa giữ bàn hay thu cọc. Nhân viên có quyền đặt bàn chốt món, giá, giờ bắt đầu và giờ sẵn (trong 10 phút từ giờ hẹn), ghi nội dung trao đổi. Khách phải đồng ý bản chốt; lúc đó hệ thống kiểm tra lại bàn/nguyên liệu và giữ có hạn để trả cọc.
5. Cọc B hợp lệ làm kế hoạch bếp được xác nhận. Trên màn bếp, đúng mốc mới phát hành phiếu; chuyển Chờ → Đang làm → Sẵn sàng. Bàn chưa ở trạng thái đang phục vụ.
6. Khách thực sự tới: nhận khách trên trang quản lý hoặc chọn đúng booking trong POS/mobile. Các lối mở bàn đều kiểm tra cọc và chuyển món đặt trước; chưa trả cọc không thể đi tắt qua POS. A có thay giá thì cần xác nhận đã trao đổi với khách; hết món phải xử lý điều chỉnh trước. B giữ giá, tiến độ, giá vốn và lần trừ kho đã có.
7. Thanh toán qua luồng POS/mobile hiện có. Preview hiển thị khấu trừ cọc; tiền mới cần thu bằng tổng hóa đơn sau ưu đãi trừ phần cọc được phân bổ. Một dòng Payment loại DEPOSIT thể hiện bù trừ, không phải dòng tiền mới. Tiền thực thu trong báo cáo cộng cọc thực nhận, cộng tiền thu cuối, trừ hoàn thực tế và loại DEPOSIT khỏi tiền thu lần hai.

## Tiền cọc và VNPAY

Mã giao dịch cọc bắt đầu `DEP`, tách khỏi giao dịch thanh toán hóa đơn `VNP`. Máy chủ xác minh chữ ký HMAC, mã merchant, số tiền, loại tiền, kết quả thành công, phiên bản bản chốt và hạn giữ chỗ. Return URL chỉ dẫn khách về trang trạng thái, không ghi nhận đã thu tiền. IPN lặp không thu lại; tiền về muộn/khác bản chốt được ghi nhận cần đối soát và tạo phiếu hoàn chờ xử lý, không cấp chồng bàn.

Điền cấu hình sandbox vào `.env` trên máy hoặc biến môi trường hosting, không gửi secret vào chat/Git:

```dotenv
VNPAY_TMN_CODE=<merchant-sandbox-cua-ban>
VNPAY_HASH_SECRET=<secret-sandbox-cua-ban>
VNPAY_PAYMENT_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
```

Khởi động lại ứng dụng khi đổi môi trường. Trên máy hiện tại, merchant/secret chưa được cấu hình tại thời điểm triển khai, nên chưa thể hoàn tất thanh toán trực tiếp qua VNPAY sandbox.

IPN chung hiện có `/sales/payment/vnpay/ipn/` (kiểm tra URL thực bằng `reverse('sales:vnpay_ipn')`) đã phân tuyến cả `DEP` và `VNP`. Ngoài ra có `/reservations/online/vnpay/ipn/` riêng cho cọc. Dùng URL HTTPS công khai đúng cấu hình merchant và kiểm tra cả thanh toán hóa đơn/cọc trước khi vận hành. Return của cọc dùng `/reservations/online/vnpay/return/`, không lấy Return URL hóa đơn ghi đè sang đối tượng cọc.

Nguồn đối chiếu: [tài liệu thanh toán VNPAY](https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html), [phân biệt Return và IPN](https://sandbox.vnpayment.vn/apis/docs/faqs/). Tích hợp hiện không tự gọi API hoàn tiền ngân hàng.

## Giữ nguyên liệu, kế thừa món và chi phí

- B chỉ cam kết từ tồn thực tế đủ dùng. Lượng giữ làm giảm phần có thể hứa/tiêu dùng cho đơn khác nhưng không làm giảm tồn vật lý. Giữ tạm hết hạn được bỏ qua trong kiểm tra khả dụng và được giải phóng khi tác vụ hết hạn chạy.
- Lúc phát hành phiếu bếp, chuyển lượng giữ thành xuất SALE_USAGE theo công thức đã chốt. Các lần gửi/nhận khách sau không tạo lần xuất nữa. Giao dịch kho giữ liên kết về món đặt trước và được nối sang OrderItem khi khách tới.
- Hủy trước chế biến hoàn đúng lượng đã xuất. Hủy khi đã bắt đầu làm không hoàn thực phẩm thành nguyên liệu; chi phí món chuẩn bị bị hủy được cộng riêng vào hao hụt báo cáo theo thời điểm hủy.
- Bếp/thu ngân không có quyền tự nâng trạng thái cọc thành đã trả. Các service đọc lại quyền, dùng transaction, revision và cùng thứ tự khóa seating → menu → actor với POS để bảo vệ thay đổi đồng thời.

## Đổi/hủy, không đến và hoàn tiền

- Khách gửi yêu cầu qua liên kết riêng; chỉ biết mã/SĐT không cho phép sửa lịch, xem giỏ/chi tiết tiền hay lấy lại capability URL. Tra cứu OL trên phiên đã tạo lịch hoặc từng mở liên kết riêng hiển thị món, lịch hẹn, bàn, cọc, tình trạng chuẩn bị và nút mở lại chi tiết. Phiên ghi nhớ tối đa 20 liên kết riêng gần nhất; phiên tạo lịch được đối chiếu bằng HMAC. Nhân viên có quyền quản lý đặt bàn cũng xem được thông tin và nút mở hồ sơ quản lý. Trình duyệt khác chỉ có mã/SĐT vẫn chỉ nhận trạng thái tổng quát; mất liên kết cần nhà hàng xác minh. Chưa có OTP/SMS/email thật.
- Quản lý có thể chốt điều chỉnh sau cọc khi chưa gửi bếp, không còn phiếu hoàn đang mở, đã trao đổi và xác minh khách đồng ý. Bản đầu chỉ thay khi tiền cọc hiện có đủ điều kiện của bản mới; chưa thu thêm cọc cho bản điều chỉnh thiếu tiền. Nếu kiểm tra/giữ bàn/nguyên liệu thất bại, transaction giữ nguyên toàn bộ lịch cũ. Món cũ được lưu lại ở dạng bản trước để đối chiếu, không xóa lịch sử thu cọc.
- Quản lý xác minh trước khi hủy/ghi không đến. Không đến chỉ từ giờ hẹn cộng thời gian chờ cấu hình. Online có món/cọc không bị tác vụ cũ tự đánh dấu vắng mà chưa xử lý bếp/tiền. Khách đang phục vụ phải xử lý qua đơn hiện có; kết thúc/hủy đơn đồng bộ lại trạng thái online.
- Hủy đúng hạn, chưa làm tạo phiếu hoàn chờ xử lý. Hủy muộn, đã làm hoặc không đến vẫn giữ số dư để quản lý đối soát theo chính sách đã chấp nhận; không tự ghi số dư thành doanh thu món.
- Phiếu hoàn: REQUESTED → APPROVED → COMPLETED; có thể từ chối trước hoàn. Duyệt chưa có nghĩa đã trả tiền. Hoàn tất yêu cầu mã/bằng chứng hoàn thực tế và xác nhận phương thức/người nhận gốc. Không hoàn vượt số dư hay khấu trừ cùng một khoản hai lần. Không sửa trực tiếp giao dịch nhận tiền hoặc xóa phiếu thu.
- Cọc dư sau chốt hóa đơn được tạo yêu cầu hoàn. Cọc gắn hóa đơn gốc, không nhân bản sang hóa đơn tách hoặc chuyển sang lượt đặt khác.

## Vận hành và kiểm tra

Màn **Món chuẩn bị trước** hiển thị cả món đặt trước của lịch TABLE và READY đã xác nhận cọc, chưa chuyển sang đơn phục vụ. TABLE hiển thị rõ “chờ khách đến”, không có nút phát hành bếp; nhận cọc không tự đổi chế độ hoặc xuất kho. READY vẫn chỉ phát hành theo mốc chuẩn bị đã chốt. Thẻ hiển thị giờ hẹn, tên khách, số người, bàn, ghi chú và cọc đã nhận. Lịch chưa cọc và món đã gắn đơn phục vụ không nằm trong danh sách này. Không thay đổi dữ liệu lịch cũ để bổ sung hiển thị.

Migration đã được tạo cho orders và reservations. Lệnh trên môi trường được xác nhận đúng DB:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py migrate
.\.venv\Scripts\python.exe -X utf8 manage.py expire_reservation_holds
```

Nên cấu hình lịch gọi tác vụ hết hạn mỗi phút trên môi trường triển khai. Luồng khách và polling vận hành cũng dọn giữ chỗ hết hạn; truy vấn khả dụng không chặn bàn vì một lượt chờ cọc đã quá hạn. Không tự đăng ký cron hoặc triển khai Render trong thay đổi này.

```powershell
$env:DJANGO_SETTINGS_MODULE='QLNH.test_settings'
.\.venv\Scripts\python.exe -X utf8 scripts\run_tests.py apps.reservations
.\.venv\Scripts\python.exe -X utf8 scripts\verify_reservations_browser.py
```

Tests dùng PostgreSQL riêng, UUID và tự dọn; không ghi đơn giả vào DB nhà hàng. Browser chạy Chrome headless profile riêng với cổng ngân hàng mô phỏng trên localhost: checkout/Return/IPN có chữ ký, matching khoản tiền, điều kiện ca, xử lý trạng thái, bếp, nhận khách và ghi kho là code ứng dụng thực. Không gửi request ngân hàng hoặc tạo giao dịch thật. Đồng hồ chỉ được thay trong wrapper kiểm thử để kiểm tra mốc chuẩn bị/nhận khách. Artifact hình/test ở `artifacts/reservations/`, Git bỏ qua.

Đã kiểm tra trực quan giao diện khách desktop/mobile, bản chốt, kết quả cọc, bếp sẵn sàng và POS hiển thị khấu trừ. Đã sửa lỗi Referrer-Policy khiến trình duyệt gửi Origin null: dùng same-origin để giữ CSRF cùng site và không chuyển capability URL ra ngoài.

## Giới hạn hiện tại

Kết quả kiểm tra ngày 10/11/2026: **534 test Django toàn dự án qua**. Sau chỉnh sửa cuối về trạng thái, các lối mở bàn và thông báo cổng chưa cấu hình, **28 test phân hệ mới qua**; các nhóm này có trùng test, không cộng thành tổng mới. Browser guest A/B → bản chốt → đồng ý/cọc → chuẩn bị → nhận khách/POS qua; đối chiếu DB có đúng hai khoản cọc, một đơn/món được nhận và một lần tiêu hao nguyên liệu. Django check, migration consistency, cú pháp JS và kiểm tra whitespace qua. Migrations được áp dụng vào DB local đã xác minh, không tạo dữ liệu đặt/cọc giả trong DB nhà hàng.

- Chưa thử giao dịch end-to-end trên VNPAY sandbox/production vì thiếu cấu hình merchant/secret thật và URL IPN công khai đã kiểm chứng.
- Hoàn tiền là quy trình xác minh/duyệt/ghi bằng chứng thực tế, chưa tự chuyển qua API ngân hàng.
- Chưa có cọc bổ sung cho điều chỉnh vượt số dư, nhiều bàn cho một lịch, tự chuyển cọc sang lượt khác hoặc dựa vào hàng chưa nhập để cam kết nguyên liệu.
- Không tự chuẩn bị chỉ do đồng hồ đến giờ; bếp xác nhận phát hành phiếu. Khi nhà hàng không đáp ứng cam kết hoặc khách trễ, nhân viên trao đổi và xử lý theo quy trình, không tự hứa làm lại miễn phí.
- OTP, thông báo SMS/email và kiểm thử tải/chống spam ở quy mô vận hành cần triển khai riêng; không coi CSRF hoặc UUID là xác minh số điện thoại.
