# Chatbot Gemini ở trang chủ khách hàng

**Trạng thái mới nhất:** sau khi chủ dự án cập nhật key thuộc project khác hiển thị Free level, đã nhận được phản hồi JSON thật từ `gemini-3.1-flash-lite`. Đã gọi trọn luồng `/menu/chat/` với CSRF và nhận **HTTP 200, câu trả lời hợp lệ, 5 thẻ món công khai từ database**. API đang dùng là **Gemini**. Các kết luận Free Tier bị chặn phía dưới là lịch sử kiểm tra project cũ, không áp dụng cho key mới hiện tại.

Đã mở hội thoại thông thường thay cho giới hạn chỉ hỏi về nhà hàng. Gemini được trả lời toán, giải thích kiến thức và câu hỏi tiếp nối. Câu hỏi về nhà hàng dùng dữ liệu hiện tại: thực đơn có mô tả công khai và chính sách các hạng thành viên đang áp dụng. Đã gọi API thật qua endpoint có CSRF: câu `1+1` trả lời `1 + 1 bằng 2.`, câu hỏi điều kiện/ưu đãi hạng thành viên trả lời đủ **4 hạng đang áp dụng**, cả hai đều HTTP 200. Không tạo dữ liệu bán hàng để thử.

Đã bổ sung lựa chọn **Groq API** theo yêu cầu dùng nhà cung cấp API miễn phí khác. Đây là API chạy trên máy chủ Groq, không cài mô hình trên máy. Groq chưa được kiểm tra bằng key thật; Gemini đang hoạt động và không tự đổi sang Groq khi lỗi.

## Chọn nhà cung cấp API

Gemini hiện tại (mặc định):

```dotenv
CHATBOT_PROVIDER=gemini
GEMINI_MODEL=gemini-3.1-flash-lite
```

Giữ `GEMINI_API_KEY` thực tế riêng trong `.env`, không dán vào tài liệu/chat. Chỉ khi muốn chủ động dùng Groq, tạo key tại [Groq Console](https://console.groq.com/keys), đặt `GROQ_API_KEY` trong `.env`, rồi chọn:

```dotenv
CHATBOT_PROVIDER=groq
GROQ_MODEL=qwen/qwen3.8-27b
```

Groq có [Free Plan](https://console.groq.com/docs/rate-limits); tài khoản cần giữ ở Free Plan, không nâng cấp Developer để bảo đảm ý định dùng miễn phí. Quota thực tế phụ thuộc tài khoản, có cả giới hạn request và token. Model được chọn nằm trong danh sách Free Plan và hỗ trợ [JSON Schema](https://console.groq.com/docs/structured-outputs). Không nạp tiền, không bật billing, không chọn model khác hoặc nhà cung cấp khác tự động. OpenRouter cũng có [model miễn phí](https://openrouter.ai/collections/free-models), nhưng chưa tích hợp vào dự án.

Sau khi đổi `.env`, restart Django. Kiểm tra API đang chọn bằng **một yêu cầu thật**:

```powershell
.\.venv\Scripts\python.exe manage.py check_chatbot_connection
```

Lệnh cũ `check_gemini_connection` chỉ kiểm tra riêng Gemini, không phụ thuộc lựa chọn Groq. Cả hai lệnh xử lý console Windows UTF-8 và không in key. Lần kiểm tra Gemini mới đã gọi API thành công nhưng phát hiện console cp1252 không in được thông báo tiếng Việt; lỗi console đã được sửa, endpoint web không bị ảnh hưởng.

Các file bổ sung: `chatbot_contract.py` chứa prompt/kiểm tra JSON dùng chung; `chatbot_groq.py` gọi HTTPS cố định bằng httpx, không redirect/retry; `chatbot_service.py` chọn một provider; `check_chatbot_connection.py` kiểm tra provider đang chọn; `test_chatbot_providers.py` kiểm thử hai provider bằng mock. Endpoint, lưu lịch sử, CSRF, rate limit, phân quyền và các quy tắc thực đơn giữ nguyên. Dòng thông tin khách hàng tự hiển thị đúng tên nhà cung cấp đang chọn.

Kiểm tra cuối: **52 test Django và 2 test JavaScript qua**, `manage.py check` và `git diff --check` qua. Các test mới xác nhận câu hỏi thông thường được gửi đến AI, hạng đang áp dụng/ưu đãi lấy từ database và cập nhật theo thay đổi cấu hình, không gửi hồ sơ/hạng cá nhân hay tổng chi tiêu của khách. Thư viện `httpx==0.28.1` đã có trong môi trường, được khai báo trực tiếp vì adapter Groq sử dụng nó. Chưa kiểm tra trực quan desktop/mobile; chưa thử Groq với key thật; không commit/push/deploy.

Chatbot nằm tại `/`, template `templates/home.html`, không nằm trên Dashboard quản trị. Nút **Hỏi QLNH** ở góc phải dưới mở khung tư vấn tiếng Việt. Có đóng/mở, lịch sử trong phiên, Trò chuyện mới, trạng thái đang trả lời, chặn gửi lặp, gợi ý câu hỏi và đường dẫn đến thực đơn/form đặt bàn thật.

## Cấu hình và khởi động

SDK đã có trong `.venv`: `google-genai==2.34.0`, được ghim trong `requirements.txt`. Mã đọc `.env` qua cơ chế `load_dotenv` hiện có; không chuyển key xuống trình duyệt.

Các biến cần có:

- `GEMINI_API_KEY`: giữ key riêng của bạn trong `.env`; không sao chép vào mã, HTML, JavaScript, log hoặc Git.
- `GEMINI_MODEL`: nên đặt rõ `gemini-3.1-flash-lite`. Nếu để trống, mã cũng dùng model này. Allowlist hiện gồm `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite` và `gemini-3.8-flash` (các model có Free Tier theo bảng giá đã kiểm tra); model khác trả thông báo chưa cấu hình, không tự gọi thử hoặc chuyển model. Allowlist không chứng minh key có quyền sinh nội dung với model.

Theo [bảng giá chính thức Google](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite), Gemini 3.1 Flash-Lite có Free Tier cho input/output văn bản tại thời điểm kiểm tra 30/10/2026. Việc một model có Free Tier không chứng minh key/project của bạn còn quota hoặc có quyền dùng model. Dùng project Free Tier trong AI Studio; cùng một model cũng có bảng giá cho project trả phí. Không có tham số SDK biến một project đã bật billing thành Free Tier. Triển khai này không bật billing, không gọi công cụ trả phí, không fallback khi lỗi quota.

Thông tin công khai tùy chọn, để trống nếu chưa xác minh:

```dotenv
RESTAURANT_ADDRESS=
RESTAURANT_OPENING_HOURS=
RESTAURANT_PHONE=
RESTAURANT_EMAIL=
RESTAURANT_PUBLIC_POLICY=
```

Không tái sử dụng địa chỉ/số điện thoại/giờ mở cửa mẫu từng ghi cứng trong template. Trang chủ/footer và chatbot hiện đọc cùng cấu hình. Thiếu thông tin sẽ báo chưa cập nhật. Không thêm model hoặc migration nghiệp vụ.

Tại `D:\DOANTOTNGHIEP`:

```powershell
# Chỉ cần ở môi trường chưa có dependencies:
# .\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Tạo bảng cache dùng chung cho chat/rate limit, chạy lại được an toàn:
.\.venv\Scripts\python.exe manage.py createcachetable qlnh_chatbot_cache
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver
```

Trong workspace hiện tại đã tạo bảng cache này. Đây là bảng kỹ thuật riêng, không tạo/sửa đơn, đặt bàn, thanh toán hoặc dữ liệu bán hàng. Sau khi thay `.env`, khởi động lại Django. Mở `http://127.0.0.1:8000/`, tải lại trang và bấm **Hỏi QLNH**.

## Các file

| File | Vai trò |
| --- | --- |
| `apps/customer_portal/chatbot_data.py` | Đọc trường công khai qua selector cũ, thông tin cấu hình, gọi service Apriori cũ, quy tắc đặt bàn/dị ứng/dữ liệu nội bộ |
| `apps/customer_portal/chatbot_gemini.py` | SDK Gemini, chỉ dẫn hệ thống, structured JSON, allowlist model, timeout và lỗi đã lọc |
| `apps/customer_portal/chatbot_storage.py` | Lịch sử cache dùng chung, giới hạn lượt và khóa PostgreSQL |
| `apps/customer_portal/chatbot_views.py` | POST endpoint, kiểm tra JSON/CSRF, lấy ngữ cảnh, đọc lại thực đơn sau phản hồi |
| `apps/customer_portal/urls.py` | URL reverse `customer_portal:chat`, endpoint `/menu/chat/` |
| `apps/customer_portal/views.py` | Trang chủ cấp CSRF cookie |
| `templates/customer/includes/chatbot.html` | Khung chat và các liên kết nội bộ cố định |
| `static/customer/js/chatbot.js` | Lịch sử hiển thị, gọi cùng nguồn, khóa gửi, trạng thái/lỗi; dùng text node/textContent |
| `static/customer/css/chatbot.css` | Giao diện theo màu trang khách hàng, kích thước responsive và safe area |
| `templates/home.html`, `templates/customer/base_customer.html` | Chỉ include chatbot trên trang chủ; thay dữ kiện mẫu bằng cấu hình công khai |
| `QLNH/settings.py`, `.env.example`, `requirements.txt` | Cấu hình, giá trị mẫu trống và dependency |
| `apps/customer_portal/tests/test_chatbot.py`, `scripts/test_chatbot_ui.cjs` | Kiểm thử backend/SDK mock và logic DOM mô phỏng |

## Dữ liệu và giới hạn

- Chỉ gửi `id`, tên, giá VND, nhóm, đơn vị, trạng thái và mô tả công khai tối đa 400 ký tự/món, với tối đa 100 món theo `customer_dishes()`. Món `AVAILABLE` được tư vấn; `SOLD_OUT` chỉ thông báo tạm hết; `INACTIVE`, nhóm/đơn vị không hoạt động không được gửi. Không gửi công thức, tồn kho, giá vốn, doanh thu, thông tin tài khoản/nhân viên/khách hàng. Danh mục lớn hoặc ngữ cảnh bị rút gọn được đánh dấu; khách luôn có nút Xem thực đơn để xem đầy đủ.
- Hạng thành viên: chỉ gửi tên, `minimum_spending` và `discount_percent` của tối đa 50 bản ghi `MembershipTier` đang áp dụng. Quy tắc khớp service hiện có: chi tiêu tích lũy cộng từ tổng tiền hóa đơn đã thanh toán gắn với khách, chọn hạng có ngưỡng cao nhất đã đạt; hạng ở thời điểm tính hóa đơn quyết định ưu đãi. Không truy vấn `Customer`, không gửi tên/số điện thoại/tổng chi tiêu/hạng của người cụ thể. Chatbot có thể tính ví dụ từ dữ liệu khách tự nêu, không xác nhận hạng thực tế hoặc tự nâng hạng.
- Giá và trạng thái trên thẻ món được truy vấn lại sau lúc chờ Gemini. Nếu thực đơn thay đổi giữa hai lần đọc, bỏ phần tư vấn cũ và thông báo thay đổi. ID không tồn tại/không còn bán bị loại khỏi thẻ.
- Nếu khách hỏi gọi thêm và đã nhắc món, gọi `dish_recommendations()` sẵn có; chỉ khi service trả kết quả mới có phần **Gợi ý gọi thêm từ Apriori**. Gemini không tạo nhãn Apriori cho lời khuyên của riêng mình. Bộ Apriori hiện có vẫn cần được đánh giá chất lượng riêng.
- Câu hỏi về đặt bàn, dị ứng/thành phần, thông tin nội bộ và thông tin nhà hàng thiếu dữ kiện được xử lý bằng quy tắc phía máy chủ. Chatbot không xác nhận đặt thành công, số bàn trống hoặc món an toàn với dị ứng. Không thực hiện thao tác nghiệp vụ.
- Endpoint chỉ nhận `action` (`message`, `state`, `reset`) và `message`. Không nhận lịch sử, system instruction, tool hoặc role từ trình duyệt. Giới hạn 1.000 ký tự/câu hỏi, 6KB request, mặc định 12 lần thử/cuộc trò chuyện. Lỗi API cũng tính một lần thử; Trò chuyện mới không xóa hạn mức theo phiên/IP/toàn hệ thống.
- Lịch sử lưu máy chủ trong cache 2 giờ từ lần cập nhật, gắn với ID ngẫu nhiên trong Django session. Gửi tối đa 6 cặp hội thoại gần nhất lên Gemini, rút gọn theo ngân sách tổng ngữ cảnh. Không log hội thoại mặc định. Không nhập thông tin nhạy cảm; thông báo điều này có ngay trong khung chat.
- JSON đầu ra Gemini được kiểm tra kiểu, giới hạn độ dài và ID. Không render HTML/Markdown thô; URL chỉ là các đường dẫn template lấy bằng reverse. Các URL do model sinh trong văn bản không trở thành liên kết điều hướng.

Các biến giới hạn tùy chọn:

| Biến | Mặc định |
| --- | --- |
| `CHATBOT_TIMEOUT_SECONDS` | 20 giây, SDK timeout theo mili giây |
| `CHATBOT_MAX_OUTPUT_TOKENS` | 1000, tối đa cấu hình 1200 |
| `CHATBOT_MAX_TURNS` | 12, tối đa cấu hình 20 |
| `CHATBOT_CONTEXT_CHARS` | 24000, tối đa cấu hình 40000 |
| `CHATBOT_SESSION_RPM` | 4 lần Gemini/phút/phiên |
| `CHATBOT_IP_RPM` | 8 lần Gemini/phút/nguồn |
| `CHATBOT_GLOBAL_RPM` | 10 lần Gemini/phút/toàn ứng dụng |
| `CHATBOT_GLOBAL_RPD` | 100 lần Gemini/ngày UTC/toàn ứng dụng |

Rate limit dùng cửa sổ phút/ngày cố định, đếm cả lần gọi lỗi. `state/reset` có hạn mức riêng 60 lần/phút/phiên và 120 lần/phút/nguồn. Cửa sổ phút cố định có thể nhận hai cụm yêu cầu ở ranh giới phút; quota nhà cung cấp vẫn là giới hạn cuối cùng. SDK được đặt `attempts=1`, không retry tự động và không gọi API để lấy danh sách model hoặc count token. Theo [SDK chính thức](https://googleapis.github.io/python-genai/), dùng `Client`, `models.generate_content`, `HttpOptions`, `GenerateContentConfig`; không dùng SDK cũ `google-generativeai`.

Cache dùng PostgreSQL và khóa advisory nên chia sẻ được giữa các web worker trên cùng database. Giới hạn lấy nguồn từ `REMOTE_ADDR`, không tin `X-Forwarded-For`. Sau reverse proxy, các khách có thể dùng chung hạn mức IP nếu ứng dụng chỉ nhìn thấy IP proxy; muốn phân biệt cần cấu hình proxy đáng tin ở tầng triển khai trước, không tự nhận header khách gửi. Khóa hội thoại dùng session advisory lock, cần kết nối PostgreSQL trực tiếp hoặc pooling theo session; không dùng PgBouncer transaction pooling cho luồng này nếu chưa đổi cơ chế khóa. Khi cache/khóa không sẵn sàng, chatbot dừng an toàn, không gọi Gemini ngoài hạn mức. Không tự thay đổi hosting.

## Kiểm thử và lịch sử kết quả của project cũ

```powershell
.\.venv\Scripts\python.exe manage.py check
$env:DJANGO_SETTINGS_MODULE = 'QLNH.test_settings'
.\.venv\Scripts\python.exe scripts/run_tests.py apps.customer_portal.tests.test_chatbot apps.customer_portal.tests.test_menu apps.customer_portal.tests.test_recommendations
node --test scripts/test_chatbot_ui.cjs
# Chỉ chạy sau khi chủ động muốn gửi một yêu cầu thử API thật:
.\.venv\Scripts\python.exe manage.py check_gemini_connection
```

Ngày 30/10/2026: Django check không lỗi; **34 test Django** chatbot/thực đơn/Apriori qua trên database kiểm thử UUID riêng, được xóa sau test; **2 test JavaScript** qua. Bao gồm JSON lỗi, CSRF, cache/history, chặn chèn role, giới hạn phiên/IP/toàn cục, không tin forwarded header, khóa đồng thời, menu đổi trạng thái khi chờ API, lỗi xác thực/quota/network/phản hồi rỗng, escape văn bản và khôi phục ô nhập khi lỗi. Các yêu cầu API trong test đều mock, không sửa dữ liệu bán hàng.

Đã xác nhận `.env` được Git bỏ qua và không được track; không đọc/in giá trị key. Ở lần triển khai đầu, một yêu cầu thật với `gemini-2.5-flash-lite` nhận HTTP 404. Sau yêu cầu tiếp theo của chủ dự án về kết nối trực tiếp, đã gọi thử endpoint có CSRF thật với `gemini-3.1-flash-lite`: Google trả HTTP 403. Kiểm tra bổ sung xác nhận đọc được danh sách model, nhưng sinh nội dung với `gemini-3.1-flash-lite` và `gemini-3.8-flash` đều bị 403; một lời gọi văn bản tối thiểu với `gemini-2.5-flash` trả 404. Không bật billing hoặc fallback tự động.

**Kết nối chat thật bị chặn vì Google xác nhận Free Tier không khả dụng với project đang dùng.** Sau khi chủ dự án cho phép kiểm tra sâu hơn, đã kiểm tra phản hồi Google sau khi lọc credentials: HTTP 403 kèm giải thích Free Tier không có cho project này. Không cần suy đoán từ việc có key hoặc đọc được danh sách model. Không bật billing, không thay key và không thay quyền tài khoản Google.

Google cũng ghi rõ: endpoint danh sách model chỉ kiểm tra key tồn tại, không xác nhận project có đủ điều kiện Free Tier hoặc quyền inference. Trong AI Studio, cần xem project có trạng thái **Restricted / Free tier unavailable / Payment needed / Unavailable** hay không. Nếu project bị chặn Free Tier, tạo key mới trong cùng project không giải quyết được. Yêu cầu của dự án là chỉ dùng miễn phí, nên không nâng cấp billing để vượt chặn; cần project có quyền Free Tier hợp lệ hoặc chủ tài khoản giải quyết hạn chế với Google.

Đã bổ sung `provider_failure_reason()` chỉ trả mã chẩn đoán trong allowlist, không log raw error/response/key; website báo Google đang từ chối quyền thay vì gộp lỗi mơ hồ. Lệnh `manage.py check_gemini_connection` gửi đúng một yêu cầu tối thiểu, không retry và chỉ in kết quả/mã lỗi an toàn. Chạy lại lệnh này sau khi đã sửa quyền/key; không gửi key vào chat. Sau bổ sung: **36 test Django + 2 test JavaScript qua**, Django check không lỗi. Chưa xác nhận chat Gemini thật thành công.

Chẩn đoán mới `project_free_tier_unavailable` nhận diện đúng phản hồi thực tế, website thông báo AI tạm ngưng vì Free Tier chưa khả dụng, lệnh kiểm tra giải thích cần project được Google cho dùng miễn phí. Không khuyên thay key trong cùng project để sửa lỗi điều kiện Free Tier. Sau sửa chẩn đoán, chạy lại **24 test chatbot: qua**, `manage.py check` và `git diff --check`: qua. Key đã xuất hiện trong ảnh gửi vào hội thoại cần được chủ tài khoản thu hồi/thay sau khi xử lý; ứng dụng không tự thu hồi hoặc sao chép key từ ảnh.

Trình duyệt tích hợp lỗi kết nối môi trường (`sandboxPolicy`); Chrome headless cũng bị ngắt kết nối điều khiển. **Chưa kiểm tra trực quan desktop/mobile**. Test JavaScript chạy trên DOM mô phỏng, không thay thế trình duyệt thật. CSS có giới hạn theo viewport và breakpoint điện thoại, cần tự mở để xác nhận bố cục. Không commit, push hoặc deploy.

## Năm câu hỏi để thử

1. Có món nào dưới 100.000 đồng?
2. Nhà hàng có món gì?
3. Tôi muốn đặt bàn.
4. Nhà hàng mở cửa mấy giờ?
5. Tôi đã chọn một món đang bán trên thực đơn, nên gọi thêm món gì? (Thay bằng tên món thật để dùng Apriori.)

Gemini vẫn là mô hình sinh văn bản, có thể trả lời sai hoặc thiếu. Tên/giá/trạng thái trên thẻ và các liên kết được ứng dụng kiểm soát; tư vấn không thay cho xác nhận của nhân viên. Thiếu cấu hình/quota/API lỗi thì thông báo rõ, thực đơn và form đặt bàn vẫn dùng bình thường.
