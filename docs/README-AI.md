# README: Phần AI gợi ý món đã thực hiện trong ứng dụng quản lý nhà hàng

Cập nhật ngày **30/10/2026**. Tài liệu này giải thích phần AI đã làm, dữ liệu được dùng, các bước xử lý, cách tích hợp vào web, kết quả kiểm tra và cách tự thử lại.

## 1. Đã làm được gì?

Đã xây dựng chức năng **Gợi ý gọi thêm** bằng thuật toán **Apriori**, từ bước chuẩn bị dữ liệu đến hiển thị và thêm món trên ứng dụng.

Ví dụ với bộ luật hiện tại: khi chọn **Cơm sườn nướng**, hệ thống có thể gợi ý **Rau muống xào tỏi** và **Trà chanh**, nếu các món này còn được phép bán. Người dùng bấm **Thêm món** để thêm vào giỏ hoặc đơn bằng luồng gọi món sẵn có.

| Hạng mục | Kết quả đã thực hiện |
| --- | --- |
| Xuất dữ liệu | Có lệnh xuất lịch sử giỏ món đã thanh toán từ database ra CSV |
| Chạy thử thuật toán | Có bộ tạo dữ liệu mô phỏng để kiểm tra toàn bộ quy trình |
| Huấn luyện | Có chương trình đọc CSV, tìm nhóm món thường đi cùng và sinh luật Apriori |
| Đánh giá | Có tập giữ lại để kiểm tra và so sánh với cách gợi ý món phổ biến |
| Google Colab | Có notebook một ô chạy để nhập món, huấn luyện, xem gợi ý và tải kết quả |
| Giải thích code | Có notebook riêng trình bày các hàm xử lý |
| Áp dụng vào web | Có gợi ý trên giỏ khách QR, menu mobile nhân viên và POS desktop |
| Tương tác | Bấm món gợi ý sẽ dùng thao tác thêm món hiện có của từng giao diện |
| Mã nguồn | Phần triển khai đã được push và merge vào `master`, commit `26f9f48` |

**Phần dưới đây mô tả gợi ý món theo các món đang chọn.** Phần dự báo số đơn đã được triển khai thêm với luồng cập nhật hằng ngày; xem [hướng dẫn dự báo](forecast-daily.md). Dự báo hiện dùng dữ liệu mô phỏng để demo.

Thuật toán chấm điểm và đề xuất bàn theo mục 3.5 của đề cương được mô tả trong [hướng dẫn chọn bàn](table-recommendations.md), gồm công thức, điều kiện hợp lệ, kiểm tra đồng thời và kết quả đánh giá. Đây là thuật toán best fit có giải thích, không cần huấn luyện mô hình.

## 2. AI này hoạt động như thế nào?

Apriori tìm những món thường xuất hiện cùng nhau trong lịch sử các giỏ hàng. Từ đó, chương trình tạo luật dạng:

```text
Nếu giỏ đã có món A → có thể đề xuất thêm món B.
Nếu giỏ đã có cả A và B → có thể đề xuất thêm món C.
```

Một **giỏ** ở đây là tập các món trong một lượt ăn đã hoàn tất. Ví dụ:

```text
Lượt 1: Cơm sườn nướng, Rau muống xào tỏi, Trà chanh
Lượt 2: Cơm gà xối mỡ, Chả giò hải sản
Lượt 3: Cơm sườn nướng, Trà chanh
```

Chương trình tự tính mức độ xuất hiện và liên hệ giữa các món để tìm luật. Không viết sẵn trong giao diện rằng chọn món A thì luôn hiện món B.

Có hai giai đoạn riêng:

1. **Học luật:** đọc nhiều giỏ trong CSV, chạy Apriori và lưu bộ luật vào JSON. Bước này thực hiện trên Colab hoặc môi trường Python huấn luyện.
2. **Dùng luật:** web đọc JSON, đối chiếu với các món đang chọn rồi trả về tối đa 3 món phù hợp. Khi khách bấm thêm món, web thực hiện gọi món như bình thường.

Web dùng lại bộ luật đã lưu cho các lượt gọi món. Việc có thêm hóa đơn trong database **chưa tự động huấn luyện lại** mô hình.

## 3. Dataset đã dùng là gì?

**Dataset là bộ dữ liệu đầu vào để chương trình tìm luật và kiểm tra kết quả.** Trong phần này, dataset là lịch sử giỏ món, mỗi dòng CSV mô tả một món trong một giỏ.

Đã sử dụng hai bộ dữ liệu riêng, phục vụ hai bước triển khai:

| Nội dung | Bộ mô phỏng | Bộ xuất từ ứng dụng |
| --- | --- | --- |
| Nguồn trong file | `synthetic_demo` | `application_export` |
| Cách có dữ liệu | Chương trình tự sinh giỏ theo các nhóm món đã thiết kế | Đọc đơn, hóa đơn và món đã phục vụ trong database |
| Số giỏ ở lần chạy đã lưu | 2.000 | 25 |
| Số ngày có giao dịch | 180 | 13 |
| Số món trong dữ liệu | 12 món giả lập, mã `DEMO01` đến `DEMO12` | 15 món xuất hiện trong lịch sử đã xuất |
| Vai trò | Kiểm tra quy trình và thử Colab trước | Tạo bộ luật khớp với danh mục món của ứng dụng |
| Bộ luật đang dùng trên web | Không dùng bộ này | Dùng bộ này |

Danh mục ứng dụng lúc kiểm tra có 16 món; lịch sử xuất ra có 15 món được gọi. CSV của bộ ứng dụng đã lưu có **64 dòng món**, gom thành **25 giỏ**. Vì một giỏ có thể chứa nhiều món, số dòng CSV khác số giỏ.

Chủ dự án đã xác nhận 25 đơn hiện có là các đơn nhập để thử ứng dụng. Chúng có đủ cấu trúc gọi món, phục vụ và thanh toán để kiểm tra kỹ thuật. Metadata của bộ luật lưu thông tin nguồn này bằng `data_provenance = test_orders_confirmed_by_owner`.

Giao diện vẫn hiển thị bình thường là **Gợi ý gọi thêm** theo yêu cầu, không gắn nhãn dữ liệu lên thẻ gợi ý. Tài liệu và file mô hình giữ đúng thông tin nguồn để giải thích kết quả.

### Vì sao chạy dữ liệu mô phỏng trước?

Bộ mô phỏng giúp kiểm tra nhanh các bước tạo CSV, đọc dữ liệu, tìm luật, đánh giá, xuất file và hiển thị gợi ý khi chưa có nhiều lịch sử ứng dụng. Các nhóm món đi cùng được tạo chủ ý nên thuật toán có quan hệ để tìm.

Sau khi quy trình chạy được, đã xuất dữ liệu của ứng dụng và huấn luyện lại bằng mã món của ứng dụng để đưa vào web. File ZIP mô phỏng đã tải từ Colab không được dùng để áp trực tiếp các mã `DEMO...` vào danh mục nhà hàng.

## 4. Đã thực hiện những bước nào?

### Bước 1 — Xác định bài toán cần làm

Chọn phần **gợi ý món bằng Apriori** trong đề cương để triển khai trước. Đầu vào lúc sử dụng là các món đang có trong giỏ hoặc đơn; đầu ra là danh sách món có thể gọi thêm.

Phần gợi ý món này chưa sử dụng thông tin cá nhân để cá nhân hóa theo từng khách. Dự báo số đơn theo ngày được triển khai riêng trong [luồng dự báo](forecast-daily.md).

### Bước 2 — Viết chức năng xuất dữ liệu từ database

Mã xử lý nằm tại [`apps/orders/ai_export.py`](../apps/orders/ai_export.py), được gọi qua lệnh `export_ai_transactions`.

Quy tắc xuất:

- Đơn phải ở trạng thái `COMPLETED`, hóa đơn `PAID` và có thời điểm đóng.
- Chỉ lấy các dòng món ở trạng thái đã phục vụ `SERVED`.
- Các hóa đơn tách từ cùng một lượt ăn được gom về một giỏ để tránh coi một lượt ăn thành nhiều giao dịch độc lập.
- Nếu một phần chưa hủy của lượt ăn còn chưa hoàn tất thanh toán thì chưa xuất cả lượt đó.
- Các dòng cùng món trong giỏ được cộng số lượng.
- Giữ cả giỏ chỉ có một món vì chúng vẫn ảnh hưởng đến tần suất xuất hiện của món.
- Không xuất tên khách, số điện thoại, email hoặc ghi chú của khách.

CSV có các cột:

| Cột | Ý nghĩa |
| --- | --- |
| `schema_version` | Phiên bản cấu trúc dữ liệu, hiện là `1` |
| `data_source` | Nguồn dữ liệu: mô phỏng hoặc xuất từ ứng dụng |
| `basket_id` | Mã giỏ/lượt ăn để gom các dòng món |
| `basket_closed_at` | Thời điểm hoàn tất thanh toán của lượt ăn, có múi giờ |
| `dish_id` | Mã định danh món dùng trong lần huấn luyện |
| `dish_code` | Mã nghiệp vụ của món, ví dụ `MC01` |
| `dish_name` | Tên món để đọc và giải thích kết quả |
| `quantity` | Tổng số lượng món đã phục vụ trong giỏ |

Lệnh xuất chỉ đọc dữ liệu nghiệp vụ. Chương trình từ chối ghi đè CSV đã tồn tại để giữ lại từng bản dữ liệu.

### Bước 3 — Tạo bộ mô phỏng để kiểm tra quy trình

[`ai_tools/demo.py`](../ai_tools/demo.py) tạo 2.000 giỏ trong 180 ngày, gồm 12 món giả lập. Dùng `seed = 42` để có thể tái tạo cùng bộ dữ liệu với cùng cấu hình.

Ví dụ trong bộ này có **Cơm trắng**, **Rau xào**, **Cá kho**. Đây là bộ mà Colab đã hiển thị kết quả:

```text
Đang chọn: Cơm trắng, Rau xào
Gợi ý: Cá kho
```

### Bước 4 — Kiểm tra và chuẩn hóa CSV

Hàm `load_transactions()` trong [`ai_tools/apriori.py`](../ai_tools/apriori.py) thực hiện:

1. Kiểm tra đủ các cột bắt buộc và đúng phiên bản dữ liệu.
2. Kiểm tra mỗi lần chạy chỉ chứa một nguồn dữ liệu.
3. Kiểm tra thời gian có múi giờ, số lượng là số nguyên dương và các trường bắt buộc không trống.
4. Kiểm tra một giỏ có thời điểm đóng nhất quán, một ID món có thông tin món nhất quán.
5. Loại các dòng trùng hoàn toàn rồi gom các món theo giỏ.

Khi đưa giỏ vào Apriori, mỗi món được biểu diễn bằng **có hoặc không có trong giỏ**. Một giỏ gọi 3 phần cơm vẫn chỉ có một dấu hiện diện của món cơm; không biến thành 3 giỏ khác nhau.

### Bước 5 — Chia dữ liệu để học và kiểm tra

Hàm `split_baskets()` sắp giỏ theo thời gian và ngày kinh doanh tại múi giờ `Asia/Ho_Chi_Minh`.

- Khoảng 20% **số ngày kinh doanh cuối** được giữ lại để kiểm tra, gọi là `holdout`.
- Các ngày trước đó dùng để học luật, gọi là `train`.
- Toàn bộ món của một giỏ nằm cùng một tập.
- Không chia ngẫu nhiên từng dòng CSV vì như vậy các món cùng giỏ có thể bị lọt sang cả hai tập.

Do chia theo ngày, tỷ lệ số giỏ không nhất thiết đúng 80/20. Bộ ứng dụng có 25 giỏ, thực tế chia thành **17 giỏ học luật và 8 giỏ kiểm tra**. Ngày bắt đầu tập kiểm tra của bản này là **12/10/2026**.

### Bước 6 — Chạy Apriori và sinh luật kết hợp

Hàm `fit_rules()` chuyển các giỏ thành bảng có/không có món bằng `TransactionEncoder`, sau đó gọi `apriori()` và `association_rules()` của thư viện `mlxtend`.

Các tham số đã dùng:

| Tham số | Giá trị | Cách hiểu |
| --- | --- | --- |
| `min_support` | `0.04` | Nhóm món phải xuất hiện trong ít nhất 4% giỏ học luật |
| `min_confidence` | `0.30` | Với luật A → B, ít nhất 30% giỏ có A cũng có B trong tập học |
| `min_lift` | `1.05` | Tỷ lệ có B khi có A phải cao hơn ít nhất 1,05 lần tần suất có B chung trong tập học |
| `max_len` | `3` | Nhóm món dùng sinh luật có tối đa 3 món |
| `max_rules` | `500` | Lưu tối đa 500 luật đạt điều kiện |
| `k` | `3` | Trả tối đa 3 món khi gợi ý |

Chỉ giữ luật có một món ở vế phải. Luật được xếp theo **confidence**, tiếp theo **lift**, rồi **support**, đều giảm dần.

Ba chỉ số được tính như sau:

```text
support(A → B)    = số giỏ có cả A và B / tổng số giỏ học luật
confidence(A → B) = số giỏ có cả A và B / số giỏ có A
lift(A → B)       = confidence(A → B) / tỷ lệ giỏ có B
```

Ví dụ có thật trong bộ luật ứng dụng đang lưu:

```text
Cơm sườn nướng → Rau muống xào tỏi
support    = 0,0588 ≈ 5,88%
confidence = 0,50   = 50%
lift       = 4,25
```

Trong 17 giỏ học luật, cặp này xuất hiện ở 1 giỏ; món cơm xuất hiện ở 2 giỏ. Vì vậy confidence là 1/2. Con số 50% mô tả quan hệ trong tập học rất nhỏ này, chưa phải xác suất một khách mới sẽ gọi rau.

### Bước 7 — Kiểm tra chất lượng gợi ý

Hàm `evaluate_rules()` lấy từng giỏ trong tập giữ lại:

1. Bỏ qua giỏ chỉ có một món vì không còn món đầu vào sau khi giấu.
2. Giấu một món trong giỏ có từ hai món trở lên.
3. Đưa các món còn lại vào hàm gợi ý.
4. Kiểm tra món đã giấu có nằm trong tối đa 3 gợi ý hay không.
5. So sánh với cách lấy 3 món phổ biến nhất trong tập học, sau khi loại các món đã có trong giỏ.

Món bị giấu được chọn theo SHA-256 của `basket_id`, giúp cùng giỏ cho cùng cách kiểm tra khi chạy lại. Bộ luật và danh sách món phổ biến đều chỉ học từ `train`.

Các chỉ số đọc kết quả:

- **Hit rate @3:** tỷ lệ giỏ tìm lại được món giấu trong tối đa 3 gợi ý.
- **Recommendation coverage:** tỷ lệ giỏ đủ điều kiện mà hệ thống đưa ra được ít nhất một gợi ý.
- **Popularity baseline hit rate @3:** tỷ lệ tìm lại món giấu nếu dùng cách gợi ý món phổ biến để đối chiếu.

Bài kiểm tra này đo khả năng tìm lại món trong một giỏ đã hoàn tất. Nó chưa đo được việc khách thật sẽ bấm gợi ý hay mua thêm khi đang gọi món.

### Bước 8 — Xuất mô hình và kết quả

Sau khi chạy, chương trình lưu các file:

| File | Dùng làm gì? |
| --- | --- |
| `apriori_model.json` | Bộ luật để ứng dụng đọc, kèm danh mục món, nguồn dữ liệu, tham số và kết quả đánh giá |
| `evaluation.json` | Các chỉ số kiểm tra để đọc riêng |
| `association_rules.csv` | Bảng luật A → B, support, confidence và lift |
| `frequent_itemsets.csv` | Các nhóm món phổ biến tìm được |
| `train_baskets.csv` | Các giỏ dùng học luật |
| `holdout_baskets.csv` | Các giỏ giữ lại kiểm tra |
| `suggestions.json` | Các món đầu vào và gợi ý của lần thử trong Colab |

File mô hình còn lưu phiên bản thư viện và mã băm SHA-256 của CSV đầu vào để đối chiếu lần chạy.

**File ZIP tải từ Colab chỉ là gói chứa các kết quả trên.** Web đọc file `apriori_model.json` đã được chọn để triển khai. Chép nguyên ZIP vào một folder không khiến ứng dụng tự nhận hoặc tự đổi bộ luật.

### Bước 9 — Làm Colab dễ chạy hơn

Notebook ban đầu có nhiều ô phụ thuộc nhau. Nếu ô tạo `MODEL` chưa chạy thành công mà chạy ô thử gợi ý thì sẽ gặp `NameError: name 'MODEL' is not defined`.

Đã tạo lại [`notebooks/01_apriori_goi_y_mon.ipynb`](../notebooks/01_apriori_goi_y_mon.ipynb) với **một ô chạy chính**. Người dùng chọn nguồn dữ liệu, nhập món và bấm ▶ để chạy toàn bộ bước cần thiết.

Ô này tự kiểm tra/cài các phiên bản thư viện đã cố định và chạy phần huấn luyện trong một tiến trình Python mới. Mục đích là giảm lỗi do thứ tự chạy ô và tránh dùng lại các thư viện đã nạp ở phiên trước. Tiến độ được in theo từng bước; lỗi xử lý vẫn được hiển thị.

Notebook [`02_apriori_giai_thich_code.ipynb`](../notebooks/02_apriori_giai_thich_code.ipynb) giữ phần giải thích từng hàm để đọc code.

### Bước 10 — Huấn luyện bằng dữ liệu ứng dụng và đưa vào web

Đã xuất 25 giỏ trong database, chạy cùng quy trình học và đánh giá, rồi đưa bộ luật tương ứng vào [`fixtures/ai/apriori_model.json`](../fixtures/ai/apriori_model.json).

File hiện tại chứa **162 luật**, học từ **17 giỏ**; 8 giỏ còn lại dùng kiểm tra. Chưa có bước học lại bằng toàn bộ 25 giỏ sau đánh giá.

Luồng trên web:

```text
Các món đang chọn
    ↓
JavaScript gửi danh sách ID món tới API
    ↓
Django tra mã món hiện tại và đối chiếu danh mục trong mô hình
    ↓
Đọc các luật có đủ món ở vế trái
    ↓
Loại món đã chọn, món trùng và món không còn được phép bán
    ↓
Trả tối đa 3 món với tên, giá và ID hiện tại
    ↓
Hiển thị “Gợi ý gọi thêm”
    ↓
Người dùng bấm thêm → dùng luồng gọi món hiện có
```

Các điểm xử lý khi tích hợp:

- Ghép món bằng `dish_code` để dùng được khi ID database trên máy và hosting khác nhau. Mã món giữa hai nơi vẫn cần khớp.
- Lấy tên và giá từ database đang chạy, không lấy giá cũ từ kết quả huấn luyện.
- Chỉ gợi ý món `AVAILABLE` có nhóm món và đơn vị tính đang hoạt động. Đây là bộ lọc trạng thái bán; các kiểm tra nghiệp vụ và kho vẫn thực hiện khi gửi món như luồng hiện có.
- Lọc món không hợp lệ trước khi lấy top 3 để chúng không chiếm chỗ của gợi ý hợp lệ.
- Không gợi ý lại món đã chọn hoặc lặp cùng một món.
- Không có luật phù hợp thì ẩn phần gợi ý. File mô hình thiếu hoặc không hợp lệ thì ghi log và không hiển thị gợi ý.
- Không dùng mô hình nguồn `synthetic_demo` cho menu ứng dụng.
- Khi giỏ đổi nhanh, JavaScript hủy hoặc bỏ qua phản hồi cũ để tránh hiện gợi ý của giỏ trước.

API đọc gợi ý là `GET /menu/recommendations/?dish=<id>&dish=<id>`. API trả danh sách món, không tự ghi thêm món vào đơn. Thao tác thêm chỉ xảy ra khi người dùng bấm nút tương ứng.

Máy chủ web chỉ cần phần đọc JSON và áp luật bằng Python chuẩn. Các thư viện huấn luyện như pandas, NumPy và mlxtend được cài riêng, không thêm vào bộ dependency chạy web.

## 5. Kết quả đạt được như thế nào?

### 5.1. Kết quả hai lần chạy đã lưu

| Chỉ tiêu | Dữ liệu mô phỏng | Dữ liệu ứng dụng |
| --- | --- | --- |
| Tổng giỏ | 2.000 | 25 |
| Giỏ học luật | 1.600 | 17 |
| Giỏ giữ lại kiểm tra | 400 | 8 |
| Giỏ đủ điều kiện giấu một món | 387 | 4 |
| Giỏ một món được bỏ qua khi đánh giá | 13 | 4 |
| Số luật đạt ngưỡng đã lưu | 50 | 162 |
| Hit rate @3 | **88,63%**, tìm lại được 343/387 món giấu | **25%**, tìm lại được 1/4 món giấu |
| Có ít nhất một gợi ý | **96,64%**, 374/387 giỏ | **100%**, 4/4 giỏ |
| Cách gợi ý món phổ biến để đối chiếu | **40,57%**, 157/387 | **75%**, 3/4 |

Số liệu bộ ứng dụng có thể xem ngay trong trường `training` và `evaluation` của [`fixtures/ai/apriori_model.json`](../fixtures/ai/apriori_model.json). Kết quả mô phỏng đã lưu tại `artifacts/ai/demo-run/`; dữ liệu xuất và kết quả chi tiết của ứng dụng nằm trong `artifacts/ai/application_20261029T155519986234Z/` trên máy làm việc. Các thư mục `artifacts` không đưa vào Git.

### 5.2. Cần hiểu kết quả này ra sao?

**Về chức năng:** đã chạy được luồng đầy đủ từ dữ liệu đến luật và gợi ý có thể bấm trên cả ba giao diện.

**Về chất lượng mô hình:** bộ ứng dụng hiện chỉ tìm lại được 1 trong 4 món giấu, thấp hơn cách gợi ý món phổ biến ở lần kiểm tra này. Mẫu kiểm tra quá nhỏ để kết luận chất lượng dùng cho kinh doanh. Kết quả 88,63% thuộc bộ mô phỏng có các nhóm món được thiết kế sẵn; không dùng số đó làm độ chính xác của hệ thống trên khách thật.

162 luật nhiều hơn 50 luật cũng không có nghĩa là mô hình tốt hơn. Với chỉ 17 giỏ học và support tối thiểu 4%, một nhóm món xuất hiện đúng một lần đã có support khoảng 5,88% và có thể vượt ngưỡng nếu đạt thêm các điều kiện khác.

### 5.3. Đã kiểm tra code và giao diện ra sao?

Trong đợt tích hợp đã chạy các nhóm kiểm tra sau. Các con số dưới đây là kết quả của đợt kiểm tra triển khai, không phải số đo chất lượng AI:

| Nhóm kiểm tra | Kết quả | Phạm vi |
| --- | --- | --- |
| Bộ kiểm tra Django đã chọn | 361 bài đạt | Bao gồm xuất dữ liệu, API gợi ý và các luồng nghiệp vụ liên quan |
| Kiểm tra Python cho phần AI | 19 bài đạt | Xử lý dữ liệu, luật, đọc mô hình và phần chạy Colab |
| Kiểm tra JavaScript đã chọn | 18 bài đạt | Gợi ý, phản hồi cũ, thêm món và các xử lý cập nhật giao diện liên quan |
| Kiểm tra trình duyệt | 54 bước đạt | Luồng mobile/POS/QR và các nghiệp vụ liên quan |
| Notebook một ô | Chạy thành công từ trạng thái chưa có biến | Kiểm tra khả năng tự chuẩn bị và chạy độc lập |

Trong kiểm tra trình duyệt, đã xác nhận menu mobile hiển thị gợi ý, nút thêm món dùng đúng thao tác hiện có, POS hiển thị gợi ý và giỏ QR thêm được món rồi loại món đó khỏi danh sách gợi ý. Kiểm tra tích hợp dùng database riêng và bộ luật kiểm thử có kiểm soát, không thay đổi dữ liệu nghiệp vụ để chạy test.

Mã nguồn đã merge vào `master` tại `26f9f48`. Việc hosting đã triển khai xong bản này cần kiểm tra riêng trên hosting; trạng thái merge Git không tự xác nhận phiên bản đang phục vụ trên Render.

## 6. Muốn tự thử thì làm thế nào?

### 6.1. Thử ngay trên ứng dụng

Khi ứng dụng đang chạy bản có phần tích hợp:

1. **Mobile nhân viên:** mở bàn → Gọi món → thêm **Cơm sườn nướng** → xem **Gợi ý gọi thêm** → bấm thêm một món gợi ý.
2. **POS desktop:** chọn đơn đang phục vụ → mở phần Món → thêm món → xem các gợi ý tương ứng.
3. **Khách QR:** quét mã vào menu → thêm món vào giỏ → mở giỏ → bấm **Thêm món** trên thẻ gợi ý.

Ví dụ bộ luật hiện tại có `MC01` → `RAU01` và `MC01` → `DU02`. Tên tương ứng là Cơm sườn nướng → Rau muống xào tỏi, Trà chanh. Kết quả thực tế còn phụ thuộc các món đã chọn và trạng thái danh mục lúc thử.

Nếu không thấy gợi ý, kiểm tra bản triển khai đã có code mới, file mô hình tồn tại, món có mã khớp mô hình và còn ở trạng thái được phép bán. Không phải món nào cũng có luật phù hợp.

### 6.2. Thử trên Google Colab

1. Mở `notebooks/01_apriori_goi_y_mon.ipynb` từ repository bằng Colab. Nếu dùng bản đã sao chép vào Drive từ trước, cần mở lại bản mới để có ô chạy đã sửa.
2. Chọn `DATA_MODE = demo` để thử bộ mô phỏng, hoặc `csv` để tải CSV xuất từ ứng dụng lên.
3. Nhập tên/mã món ở `MON_DANG_CHON`, cách nhau bằng dấu phẩy. Tên món phải thuộc đúng bộ dữ liệu đang chạy.
4. Bấm ▶ ở ô chạy chính và chờ hoàn tất.
5. Xem dòng **Đang chọn / Gợi ý**, danh mục món và báo cáo kết quả. ZIP được tải xuống để lưu các file đầu ra.

Ở chế độ demo có thể nhập `Cơm trắng, Rau xào`. Ở chế độ CSV ứng dụng, xem danh mục xuất hiện sau lần chạy để nhập đúng tên hoặc mã món của ứng dụng. Không cần chép `.env` hay mật khẩu database lên Colab.

### 6.3. Xuất và huấn luyện lại trên máy

Chạy PowerShell ở thư mục dự án. `.venv` là môi trường chạy Django đã có; thư viện huấn luyện nằm riêng trong `artifacts/ai/venv`.

Nếu máy chưa có môi trường AI thì tạo và cài một lần:

```powershell
.venv/Scripts/python.exe -m venv artifacts/ai/venv
artifacts/ai/venv/Scripts/python.exe -m pip install -r requirements-ai.txt
```

Xuất dữ liệu và huấn luyện bằng tên thư mục mới cho mỗi lần chạy:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$runId = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$csvPath = "artifacts/ai/transactions_$runId.csv"
$resultPath = "artifacts/ai/results_$runId"

.venv/Scripts/python.exe manage.py export_ai_transactions --output $csvPath
artifacts/ai/venv/Scripts/python.exe scripts/train_apriori.py $csvPath --output $resultPath
```

Lệnh xuất đọc database được cấu hình cho môi trường đang chạy. Nếu muốn học từ dữ liệu trên hosting thì cần xuất tại môi trường có quyền đọc đúng database đó; chạy ở máy local không tự lấy dữ liệu Render.

Sau khi chạy, mở `evaluation.json` và `association_rules.csv` trong `$resultPath` để xem kết quả trước khi chọn mô hình triển khai. Có thể trỏ cấu hình `APRIORI_MODEL_PATH` tới file `apriori_model.json` mới, hoặc cập nhật file mặc định `fixtures/ai/apriori_model.json` trong một lần triển khai có kiểm tra. Khi đổi biến môi trường, khởi động lại ứng dụng để nạp cấu hình mới.

Việc xuất và huấn luyện không tự thay bộ luật đang dùng trên web. Với file tải từ Colab, cần giải nén, chọn đúng mô hình nguồn ứng dụng có mã món phù hợp, rồi mới cấu hình ứng dụng dùng file đó.

## 7. Code nào phụ trách việc gì?

| File/thư mục | Trách nhiệm |
| --- | --- |
| [`apps/orders/ai_export.py`](../apps/orders/ai_export.py) | Truy vấn lượt ăn đã hoàn tất và xuất dòng dữ liệu giỏ món |
| [`apps/orders/management/commands/export_ai_transactions.py`](../apps/orders/management/commands/export_ai_transactions.py) | Lệnh Django ghi CSV, có tùy chọn lọc ngày |
| [`ai_tools/schema.py`](../ai_tools/schema.py) | Khai báo cấu trúc CSV và các nguồn dữ liệu hợp lệ |
| [`ai_tools/demo.py`](../ai_tools/demo.py) | Tạo dữ liệu mô phỏng |
| [`ai_tools/apriori.py`](../ai_tools/apriori.py) | Đọc dữ liệu, chia tập, tìm luật, đánh giá và ghi kết quả |
| [`ai_tools/inference.py`](../ai_tools/inference.py) | Kiểm tra JSON mô hình và áp luật để gợi ý bằng Python chuẩn |
| [`ai_tools/colab_runner.py`](../ai_tools/colab_runner.py) | Chuẩn bị môi trường, chạy tiến trình huấn luyện và đóng gói kết quả Colab |
| [`ai_tools/notebook_job.py`](../ai_tools/notebook_job.py) | Xử lý lần chạy notebook, nhận món theo tên/mã/ID và ghi gợi ý |
| [`requirements-ai.txt`](../requirements-ai.txt) | Phiên bản thư viện dùng cho huấn luyện |
| [`scripts/train_apriori.py`](../scripts/train_apriori.py) | Lệnh huấn luyện bằng một file CSV |
| [`scripts/build_easy_apriori_notebook.py`](../scripts/build_easy_apriori_notebook.py) | Tạo notebook một ô chứa đủ mã cần chạy |
| [`scripts/build_apriori_notebook.py`](../scripts/build_apriori_notebook.py) | Tạo notebook giải thích nhiều ô |
| [`notebooks/01_apriori_goi_y_mon.ipynb`](../notebooks/01_apriori_goi_y_mon.ipynb) | Notebook thao tác thử AI |
| [`notebooks/02_apriori_giai_thich_code.ipynb`](../notebooks/02_apriori_giai_thich_code.ipynb) | Notebook đọc và giải thích code |
| [`fixtures/ai/apriori_model.json`](../fixtures/ai/apriori_model.json) | Bộ luật ứng dụng đang được cấu hình dùng mặc định |
| [`apps/menu/recommendations.py`](../apps/menu/recommendations.py) | Ghép mã món, lọc danh mục hiện tại và trả món gợi ý |
| [`apps/customer_portal/recommendation_views.py`](../apps/customer_portal/recommendation_views.py) | API nhận ID món và trả danh sách gợi ý |
| [`templates/includes/menu_recommendations.html`](../templates/includes/menu_recommendations.html) | Khung giao diện dùng chung cho mục gợi ý |
| [`static/js/menu-recommendations.js`](../static/js/menu-recommendations.js) | Theo dõi món đang chọn, gọi API, hiển thị và chuyển thao tác thêm món |
| [`static/css/menu-recommendations.css`](../static/css/menu-recommendations.css) | Giao diện thẻ gợi ý trên các kích thước màn hình |
| [`docs/ai-apriori.md`](ai-apriori.md) | Hướng dẫn kỹ thuật và các lệnh kiểm tra chi tiết |

Các hàm chính để đọc theo thứ tự là `load_transactions()` → `split_baskets()` → `fit_rules()` → `evaluate_rules()`. Hàm `run_experiment()` gọi các bước đó và xuất kết quả. Khi web phục vụ khách, `dish_recommendations()` chuẩn bị danh mục hiện tại và gọi `recommend()` để áp luật đã lưu.

## 8. Những việc còn cần làm tiếp

- Tích lũy thêm lịch sử giỏ món đủ đa dạng để học và đánh giá trên mẫu lớn hơn.
- Huấn luyện lại khi có dữ liệu mới hoặc thay đổi thực đơn; hiện chưa có lịch huấn luyện tự động.
- Đánh giá trên các ngày về sau chưa dùng chọn tham số. Nếu điều chỉnh tham số nhiều lần theo kết quả kiểm tra thì cần một tập đánh giá cuối riêng.
- Đo thêm hành vi sử dụng thực tế như tỷ lệ bấm gợi ý, tỷ lệ thêm món và giá trị đơn; hiện chưa có kết quả đo tác động kinh doanh.
- Đánh giá dự báo số đơn trên dữ liệu bán hàng thực tế; luồng cập nhật demo đã có tại [hướng dẫn dự báo](forecast-daily.md). Bài toán lượng khách cần được xác định và đánh giá riêng.
