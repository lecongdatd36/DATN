# Ca làm và chấm công khuôn mặt tại cửa

Phân hệ `apps/workforce`, quản lý `/cham-cong/`, lịch cá nhân `/cham-cong/lich-cua-toi/`. **Trang chung cố định: `/cham-cong/diem-cham-cong/`**, không cần đăng nhập hoặc kích hoạt thiết bị. Lưu bookmark để mở trên máy/điện thoại có camera.

## Luồng sử dụng

1. Quản lý mở **Ca làm & chấm công → Ca làm**, tạo ca, giờ bắt đầu/kết thúc, phút nghỉ không tính công và phút trễ cho phép.
2. **Lịch phân ca**: chọn một hoặc nhiều nhân viên và ngày bắt đầu, lưu nháp rồi công bố từng lịch. Mọi ca chưa hủy, bao gồm ca nháp và ca qua đêm, đều được kiểm tra trùng giờ. Nhân viên chỉ xem lịch của mình đã công bố/đã hủy.
3. **Khuôn mặt**: chọn nhân viên đang làm việc, xác nhận nhân viên đồng ý; bật camera và chụp 3 mẫu riêng (thẳng, quay nhẹ trái/phải), rồi lưu. Mẫu gần trùng nhân viên khác bị chặn. Nút xóa mẫu thu hồi ngay các thử thách đang dùng mẫu đó.
4. Mở **Chấm công** trong menu hoặc truy cập `/cham-cong/diem-cham-cong/`. Trang chung nhận diện người đứng trước camera, không phụ thuộc tài khoản đang đăng nhập. Không có bước đăng ký/kích hoạt máy.
5. Bấm một nút **Chấm công**, nhìn camera. Hệ thống tự chọn **Vào ca** nếu không có ca đang mở, hoặc **Ra ca** nếu đang có giờ vào chưa có giờ ra; vẫn kiểm tra ca đã công bố, cửa sổ giờ, hồ sơ đang hoạt động và tình trạng duyệt. Thiếu ca hoặc có lỗi sẽ báo lý do ngay. Nếu hợp lệ, quay đầu nhẹ theo hướng dẫn rồi nhìn lại camera. Chỉ hiện **Đã ghi công thành công** sau khi DB đã lưu, kèm thao tác vào/ra và giờ máy chủ. Mất kết nối không tự gửi lại POST; kiểm tra bảng công trước khi chấm lại.
6. Quản lý vào **Bảng công**, lọc ngày/nhân viên, mở từng ca để điều chỉnh, ghi vắng hoặc duyệt. Nhân viên xem giờ vào/ra và kết quả duyệt ở lịch cá nhân.

## Trang kiểm thử nhận diện

Quản lý vào **Ca làm & chấm công → Kiểm thử nhận diện**, hoặc `/cham-cong/khuon-mat/kiem-thu/`. Mục Khuôn mặt cũng có liên kết mở trang này. Bố cục gồm camera lớn bên trái, vị trí và thông số khớp mẫu ở dưới, kết quả và hướng dẫn bên phải; dùng điểm nhấn đỏ Cơm Quê và tự xếp một cột trên điện thoại/tablet.

1. Bật camera, nhìn thẳng rồi chọn **Nhận diện thử**. Camera cần HTTPS hoặc localhost và quyền camera của trình duyệt.
2. POST tới `/cham-cong/khuon-mat/kiem-thu/api/` chỉ đối chiếu với mẫu SFace của nhân viên/tài khoản/vị trí đang hoạt động. Kết quả phải vượt ngưỡng và đủ chênh lệch với ứng viên thứ hai theo cấu hình hiện có. Tên/mã nhân viên chỉ trả về khi tìm được khớp hợp lệ. Khi thất bại, giao diện hiển thị lỗi ảnh, thiếu mẫu, không khớp hoặc lỗi kết nối cụ thể.
3. Độ tương đồng là điểm cosine, không phải phần trăm xác suất đúng. Ngưỡng hiện tại là ngưỡng thử nghiệm, chưa hiệu chuẩn trên tập kiểm định của nhà hàng.
4. Đã bỏ phần vị trí; trang kiểm thử và chấm công không yêu cầu GPS.
5. Dừng camera hoặc rời tab sẽ dừng stream, hủy yêu cầu đang chạy và xóa kết quả nhận diện cũ khỏi màn hình. Ảnh xử lý tạm trong bộ nhớ; không tạo mẫu, thử thách, lịch ca, bảng công hoặc nhật ký công.

Trang và API kiểm thử yêu cầu quyền quản lý nhân sự, CSRF và không cache kết quả. Màn kiểm thử không ghi công; **trang chấm công chung đã dùng cùng bố cục camera / kết quả**, với một nút Chấm công tự xác định vào/ra và xác minh động tác như trên. Không thêm biến môi trường. Migration `workforce/0003` bổ sung chế độ AUTO trên lượt xác minh; giữ nguyên giờ công, mẫu khuôn mặt và lượt xác minh cũ.

Khi nhận diện lần đầu, service chọn thao tác từ bảng công và giữ cố định thao tác cùng nhân viên cho cả lượt xác minh. Các frame sau kiểm tra lại để không chuyển nhầm từ vào thành ra khi một thiết bị khác vừa ghi công. Chặn lượt tự động trong 60 giây sau lần ghi công gần nhất của nhân viên, xuyên thiết bị/phiên, nhằm tránh chấm lặp do bấm lại. Ca quá hạn, công đã duyệt, lịch trùng hoặc thiếu lịch vẫn bị chặn theo nghiệp vụ hiện có; hệ thống không đoán ca thay cho quản lý.

Kiểm tra bằng `scripts/verify_attendance_browser.py`: camera giả và vector tổng hợp trên PostgreSQL tạm, không dùng mẫu sinh trắc học hay bảng công thật. Chrome kiểm tra desktop/tablet/mobile, lỗi ảnh, thiếu ca, một nút tự ghi vào, chặn bấm lặp, rồi tự ghi ra sau khi dịch đồng hồ test. Ảnh lưu ở `artifacts/attendance/browser/` (không đưa vào Git).

Kết quả bản một nút ngày 11/11/2026: toàn bộ **612 test Django qua**, Chrome qua luồng tự vào / chặn lặp / tự ra; check, migration consistency và production static manifest qua.

## Quy định công hiện tại

- Ca có giờ kết thúc nhỏ hơn giờ bắt đầu đi qua nửa đêm; thời lượng tối đa 16 giờ. Ngày công là ngày bắt đầu ca. Hai ca liền kề đúng đầu/cuối được phép.
- Mẫu ca thay đổi không làm thay đổi các lịch đã phân: lịch giữ snapshot giờ, tên ca, giờ nghỉ và mức trễ. Muốn đổi lịch chưa có công, hủy lịch cũ rồi phân lại; lịch đã có công không được hủy.
- Chỉ phân từ hôm nay, từ ngày vào làm; nhân viên và tài khoản/vị trí phải đang hoạt động. Không tự sinh hay công bố lịch.
- Vào ca: từ 60 phút trước giờ bắt đầu đến trước giờ kết thúc. Nếu có nhiều ca đủ điều kiện, máy yêu cầu quản lý kiểm tra; không đoán chọn. Phải ra ca trước còn mở trước khi vào ca khác.
- Ra ca: phải có giờ vào và chưa có giờ ra; tối đa 4 giờ sau kết thúc. Ngoài cửa sổ này hoặc quên chấm, nhờ quản lý điều chỉnh có lý do.
- Chỉ công đã duyệt mới cộng vào tổng giờ. Giờ công = khoảng thời gian vào/ra giao với khung ca, trừ số phút nghỉ cố định, chặn dưới 0; chưa tính tăng ca. Phút công lấy phần phút hoàn tất, không làm tròn thành ngày công/lương.
- Phút trễ/về sớm ghi theo phút hoàn tất. Đi trễ được đánh dấu khi số phút trễ lớn hơn mức cho phép; không xóa số phút trễ thực tế khỏi dữ liệu. Mức cho phép không cộng bù giờ công.
- Chỉ duyệt sau khi ca kết thúc và đã đủ giờ vào/ra, hoặc có lý do ghi vắng. Chưa chấm không tự động kết luận nghỉ không phép. Công vắng được quản lý tạo và duyệt.
- Quản lý không tự điều chỉnh, duyệt hoặc mở lại công của chính mình. Công đã duyệt được khóa; muốn sửa phải mở lại và nhập lý do. Duyệt dựa trên công đã lưu; thay đổi giờ phải lưu điều chỉnh trước.
- Mọi thay đổi lịch, thiết bị, đăng ký/xóa mẫu, vào/ra và duyệt/điều chỉnh đều ghi nhật ký cùng transaction. Dùng khóa PostgreSQL chung với nhân sự và revision để chống phân ca/chấm trùng, ghi đè công hoặc thu hồi thiết bị đồng thời.
- Tổng hợp CSV có mã/tên, ca phân, công đã duyệt, phút công, lượt trễ/về sớm/vắng; dữ liệu văn bản được bảo vệ trước công thức CSV.

## Cài nhận diện trên Windows

Chạy tại thư mục dự án:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-attendance.txt
.\.venv\Scripts\python.exe -X utf8 scripts\setup_attendance_models.py
.\.venv\Scripts\python.exe -X utf8 manage.py migrate
```

Thư viện CPU: OpenCV headless và NumPy; tách khỏi requirements web thông thường. Mô hình YuNet phát hiện mặt và SFace tạo vector 128 chiều. Script tải từ OpenCV Zoo, kiểm tra SHA-256 đã cố định và thay file nguyên tử. Không tải mô hình trong request. Không thay đổi bộ thư viện AI huấn luyện riêng.

`ATTENDANCE_MODEL_ROOT` mặc định `artifacts/attendance/models`. Nếu đổi, truyền cùng đường dẫn cho `setup_attendance_models.py --root ...`. `ATTENDANCE_FACE_THRESHOLD=0.45`, `ATTENDANCE_FACE_MARGIN=0.06` là ngưỡng thử nghiệm cấu hình qua môi trường, không phải độ chính xác đã được hiệu chuẩn.

Tài liệu nguồn: [OpenCV FaceDetectorYN/FaceRecognizerSF](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html), [YuNet và giấy phép](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), [SFace và giấy phép](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface). Ngưỡng benchmark 1:1 trong tài liệu OpenCV không phải kết quả đánh giá 1:N trên nhân viên nhà hàng. Giữ giấy phép mô hình khi phân phối; weights không được đưa vào Git.

## Hosting và thiết bị

- Camera trình duyệt cần HTTPS hoặc localhost và quyền camera. HTTP qua địa chỉ LAN thông thường không đủ; dùng HTTPS trên mạng nội bộ hoặc truy cập localhost khi server và trình duyệt cùng máy.
- `build.sh` hỗ trợ `ENABLE_FACE_ATTENDANCE=1`: cài thư viện và tải mô hình trước `collectstatic`/migration. Không tự bật tính năng này trên hosting hiện tại. Docker đang dùng quy trình build khác; nếu dùng Docker cần thêm cài requirements-attendance và mô hình vào quy trình đó.
- Nhận diện chạy trên **máy chủ nhận request**, không mặc nhiên chạy trên máy màn hình. Nếu mở website Render, Render xử lý ảnh. Cần đo RAM/CPU/độ trễ với cấu hình thực; chưa chứng minh phù hợp hosting ít RAM hoặc nhiều worker. Một cache mô hình cho mỗi process, khóa inference trong process để OpenCV không dùng chung buffer đồng thời.
- Trang chung dùng phiên trình duyệt ẩn danh để ràng buộc lượt camera, CSRF và giới hạn nhịp/số lần thử. Challenge chỉ lưu HMAC của khóa phiên. Trình duyệt khác không được tiếp tục hoặc hủy lượt đó. Phiên này không cấp quyền quản trị; trang chung không chứng minh vị trí vật lý tại nhà hàng.
- Luồng thiết bị cũ `/cham-cong/kiosk/` và `/cham-cong/thiet-bi/` còn tương thích dữ liệu trước đây, nhưng không phải bước cần thiết của trang chung. Cookie kích hoạt cũ vẫn giới hạn thời gian, đường dẫn và quyền như trước.
- Ảnh camera chỉ xử lý trong RAM, không lưu ảnh/video vào media, log hoặc Git. Vector và ghi nhận đồng ý lưu trong PostgreSQL; chỉ quản lý truy cập màn đăng ký. Backup DB có chứa vector nên phải được bảo vệ cùng dữ liệu nhân sự. Xóa mẫu bằng chức năng quản lý; bản backup cũ vẫn cần được xử lý theo chính sách lưu trữ.

## Giới hạn nhận diện và kiểm tra thực tế bắt buộc

Hiện có nhận diện 1:N, ngưỡng điểm, khoảng cách với người đứng thứ hai, kiểm tra một mặt, kích thước, sáng/mờ, ba mẫu nhất quán và thử thách thẳng–quay đầu–thẳng. Server lấy vị trí mũi/mắt ở ảnh đầu làm mốc riêng cho lượt đó, đo chuyển động tương đối và yêu cầu trở lại gần mốc. Ngưỡng chuyển động vẫn cần kiểm tra với người thật. UI hiển thị tên, trạng thái đã/chưa ghi công, số bước, hướng dẫn khi quay ngược và thanh mức quay. Lỗi cuối được giữ trên màn hình để đọc.

Server kiểm tra cùng danh tính ở từng ảnh; challenge ràng buộc phiên trình duyệt hoặc thiết bị cũ, hết hạn 90 giây, giới hạn nhịp/số lần thử, không chấp nhận lại một ảnh trong cùng lượt và chỉ dùng một lần. Đổi/xóa hồ sơ làm lượt đó mất hiệu lực. Điều kiện ca được kiểm tra lại lúc ghi công.

**Đây chỉ là thử thách chuyển động cơ bản, chưa phải mô hình chống giả mạo/PAD đã được kiểm chứng.** Ảnh in được di chuyển, màn hình hoặc video chuẩn bị sẵn vẫn có thể vượt qua; trình duyệt bị kiểm soát cũng có thể gửi ảnh giả. Không tuyên bố chống chấm hộ hoàn toàn hoặc có độ chính xác 99%. Nếu triển khai trả lương thực tế, cần đánh giá người thật/ảnh in/video, camera/ánh sáng, người giống nhau, ngưỡng FAR/FRR và bổ sung PAD/thiết bị phù hợp theo kết quả thử.

Chưa triển khai tính lương, xếp lịch AI, tăng ca tự động, GPS, vân tay hoặc đồng bộ máy chấm công phần cứng.

## Kiểm tra phần mềm

```powershell
$env:DJANGO_SETTINGS_MODULE='QLNH.test_settings'
.\.venv\Scripts\python.exe -X utf8 scripts\run_tests.py apps.workforce
.\.venv\Scripts\python.exe -X utf8 scripts\verify_attendance_browser.py
.\.venv\Scripts\python.exe -X utf8 manage.py makemigrations --check --dry-run
node --check static/js/attendance-camera.js
```

Test chạy database PostgreSQL riêng có tên UUID và tự dọn, không sửa đơn/kho/hóa đơn của nhà hàng. Browser dùng Chrome headless profile riêng và camera giả để xác minh các form thật, quyền kiosk và từ chối ảnh không có mặt. Các endpoint tạo session test chỉ tồn tại trong WSGI wrapper của script, không đăng ký trong ứng dụng. Test nhận diện thành công trong service dùng vector giả; không tính là đánh giá camera/người thật. Ảnh thử OpenCV kiểm tra nạp model/trích đặc trưng cũng không chứng minh nhận dạng nhân viên thực tế.

Kịch bản thử tại cửa: đăng ký 2–3 nhân viên có đồng ý → phân/công bố ca đúng giờ → từng người vào/ra → người chưa đăng ký → hai người trong khung → bấm lại → đổi/xóa mẫu → thu hồi máy → kiểm tra giờ và nhật ký. Cần thử ca đêm, ánh sáng yếu, kính/khẩu trang và các mẫu giả mạo trước khi quyết định đưa vào vận hành.

## Kết quả kiểm tra triển khai ngày 10/11/2026

### Cập nhật trang chung

- Trang chung không cần đăng nhập/kích hoạt: `/cham-cong/diem-cham-cong/`. Lượt giữa các trình duyệt được tách bằng phiên ẩn danh.
- Đã đổi phép kiểm tra quay đầu sang mốc tương đối từng người; không hạ ngưỡng khớp danh tính. Nhận đúng tên nhưng thiếu ca/ca nháp/ngoài giờ được báo ngay trước bước quay đầu. Thông báo lỗi cuối không tự xóa.
- **39 test phân hệ qua**, gồm hồi quy mặt có mốc lệch .23, quay ngược có hướng dẫn, thiếu ca, cách ly phiên, API chung ghi vào/ra và chống dùng lại.
- Bộ Django toàn dự án sau cập nhật: **507 test qua**. Django check, migration consistency, cú pháp JavaScript và `git diff --check` đều qua.
- Browser qua với trang chung ẩn danh, camera giả bị từ chối, tên đúng nhưng thiếu ca báo rõ, ghi vào/ra đúng một bản ghi trong DB test. Nhánh nhận diện thành công chỉ thay inference bằng vector/tư thế giả trong WSGI wrapper kiểm thử; phần matching, ca, session, CSRF và ghi công chạy thật. Không phải kết quả đo người thật/PAD.
- Migration `workforce.0002_facechallenge_neutral_yaw_and_more` đã áp dụng trên DB local, giữ nguyên mẫu mặt và dữ liệu ca/công hiện có.

### Kết quả bản đầu

- Đã tạo nhánh `feature/face-attendance-kiosk`; cài thư viện CPU và tải/kiểm tra checksum hai mô hình trên máy phát triển.
- Django check, migration consistency và kiểm tra cú pháp JavaScript: qua. Migration `workforce.0001_initial` đã áp dụng vào PostgreSQL local sau khi kiểm tra host; không triển khai hosting.
- Bộ Django toàn dự án: **498 test qua**. Sau điều chỉnh cuối về điều hướng lịch/mobile, **52 test liên quan qua**. Hai nhóm này có kiểm thử trùng nhau, không cộng thành tổng mới.
- Browser thật: tạo ca, phân/công bố lịch, đăng ký từ camera giả bị từ chối, kích hoạt kiosk và đăng xuất quản lý, kiosk từ chối camera giả; đối chiếu DB không có mẫu mặt hoặc bản ghi công từ camera giả. Đã xem ảnh desktop và mobile; không tràn ngang ở 390 px. Artifact ở `artifacts/attendance/browser/` được Git bỏ qua.
- Smoke test inference với ảnh mẫu OpenCV: phát hiện mặt, trích được 128 đặc trưng, cosine tự so sánh 1.0. Đây là kiểm tra kỹ thuật, không đo FAR/FRR hoặc nhận dạng nhân viên.
- Chưa đăng ký sinh trắc học người dùng, chưa kiểm thử người thật trước camera, chưa đánh giá PAD hoặc khả năng vận hành trên Render.
