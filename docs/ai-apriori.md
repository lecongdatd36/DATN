# Chuẩn bị dữ liệu và chạy Apriori trên Google Colab

Đã có bộ xuất CSV, notebook Apriori và phần **Gợi ý gọi thêm** trên giỏ QR, menu nhân viên mobile và POS.
Mô hình dự báo số đơn theo ngày là phần tiếp theo của đề cương.

## Chạy nhanh bằng Colab — bản dễ dùng v2

1. Mở `notebooks/01_apriori_goi_y_mon.ipynb` trên Colab. Bản mới có đúng **một ô chạy**,
   tiêu đề **▶ BẤM NÚT NÀY ĐỂ CHẠY AI**. Nếu đang dùng bản cũ đã sao chép vào Drive, mở lại bản mới từ GitHub.
2. Giữ `DATA_MODE = demo`, nhập tên món ở `MON_DANG_CHON`, ví dụ **Cơm trắng, Rau xào**.
3. Bấm **▶ bên trái chính ô đó**. Đợi tiến độ 1/4 → 4/4. Lần đầu cần cài thư viện nên có thể mất vài phút.
4. Đọc dòng **ĐANG CHỌN / GỢI Ý** ngay dưới ô. Đổi tên món rồi bấm lại ▶ để thử tiếp.
   Có thể nhập tên, mã món hoặc dish_id, cách nhau bằng dấu phẩy; để trống sẽ lấy một ví dụ từ luật đã tìm được.
5. File ZIP kết quả được tải xuống. Nguồn `synthetic_demo` là dữ liệu mô phỏng, chỉ dùng kiểm tra quy trình.
6. Chọn `DATA_MODE = csv` để tải CSV xuất từ ứng dụng lên. Sau khi chạy, mở **Danh mục món để thử tiếp**
   để xem tên/mã hợp lệ. Tên không tồn tại hoặc trùng nhiều món sẽ được báo rõ, không tự đổi sang món khác.

Notebook tự chứa mã xử lý, không cần tài khoản database, `.env`, mật khẩu hoặc clone repo.
Ô chạy tự kiểm tra/cài thư viện và chạy thuật toán trong một tiến trình Python mới, tránh dùng các thư viện
đã được nạp từ phiên Colab trước đó. Nếu bước chuẩn bị hoặc huấn luyện lỗi, thông báo hiện ngay tại bước đó;
không cần chạy tiếp các ô phụ thuộc `MODEL`.

Bản nhiều ô để đọc/giải thích mã nguồn được giữ ở `notebooks/02_apriori_giai_thich_code.ipynb`.
Dữ liệu ứng dụng xuất ra không tự xác nhận đó là dữ liệu kinh doanh thực; các đơn test vẫn là dữ liệu test.

## Xuất dữ liệu từ ứng dụng

Chạy ở môi trường có database cần xuất; lệnh dưới đây chỉ đọc database:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe manage.py export_ai_transactions --output artifacts/ai/transactions.csv
```

Lọc theo ngày đóng lượt khách trong múi giờ nhà hàng, lấy cả ngày cuối:

```powershell
.venv/Scripts/python.exe manage.py export_ai_transactions --date-from 2026-09-01 --date-to 2026-10-31 --output artifacts/ai/transactions-sep-oct.csv
```

File đã tồn tại sẽ bị từ chối ghi đè; chọn tên mới cho mỗi bản xuất. Đường dẫn mặc định và
môi trường huấn luyện trong `artifacts/ai/` đã được gitignore.

| Cột CSV | Ý nghĩa |
| --- | --- |
| `schema_version` | Phiên bản hợp đồng dữ liệu, hiện là `1` |
| `data_source` | `application_export` hoặc `synthetic_demo` |
| `basket_id` | Mã lượt dùng gom giỏ và kiểm tra tách tập; không phải mã khách |
| `basket_closed_at` | Thời điểm hóa đơn cuối trong lượt được thanh toán, có offset múi giờ |
| `dish_id` | Khóa món dùng cho Apriori; không dùng tên món làm khóa |
| `dish_code`, `dish_name` | Danh mục món hiện tại để giải thích kết quả |
| `quantity` | Tổng số lượng đã phục vụ của món trong lượt |

Quy tắc lấy dữ liệu:

- Chỉ lấy order `COMPLETED`, invoice `PAID` có thời điểm đóng và item `SERVED`.
- Các check cùng `split_root` là một lượt. Một check chưa thanh toán xong thì cả lượt chưa xuất.
  Check đã hủy không tham gia. Lọc ngày sau khi xác định thời điểm đóng cuối của lượt.
- Gộp món trùng, cộng số lượng; Apriori chỉ xét món có/không trong giỏ, không nhân bản giỏ theo số lượng.
- Giữ giỏ một món vì chúng ảnh hưởng mẫu số khi tính support.
- Không xuất tên, số điện thoại, email, ghi chú hoặc mã khách hàng.
- `application_export` chỉ xác nhận nguồn ứng dụng; các đơn test có sẵn vẫn là dữ liệu test.
  Cần xác minh nguồn trước khi trình bày thành dữ liệu kinh doanh thực tế.

## Chạy ở máy cá nhân

Thư viện AI tách khỏi `requirements.txt`; máy chủ web không cần cài pandas/mlxtend ở bước này.
Tạo môi trường riêng một lần:

```powershell
.venv/Scripts/python.exe -m venv artifacts/ai/venv
artifacts/ai/venv/Scripts/python.exe -m pip install -r requirements-ai.txt
```

Tạo CSV mô phỏng rồi chạy thí nghiệm:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe scripts/generate_ai_demo_data.py --baskets 2000 --days 180 --seed 42
artifacts/ai/venv/Scripts/python.exe scripts/train_apriori.py artifacts/ai/demo_transactions.csv --output artifacts/ai/demo-results
```

Chạy bằng bản xuất từ ứng dụng:

```powershell
artifacts/ai/venv/Scripts/python.exe scripts/train_apriori.py artifacts/ai/transactions.csv --output artifacts/ai/application-results
```

Mỗi thư mục kết quả phải là tên mới. Cùng seed cho demo cho kết quả lặp lại được.
Demo có mã món `DEMO01…DEMO12`, tên món giả lập và các nhóm món thường đi cùng được tạo chủ ý;
không đưa trực tiếp các khóa món đó vào gợi ý cho database nhà hàng.

## Chia tập, khai phá và đánh giá

- Giữ khoảng 20% **ngày kinh doanh cuối** làm holdout. Toàn bộ một giỏ nằm trong một tập;
  không chia ngẫu nhiên các dòng món. Múi giờ ngày kinh doanh là `Asia/Ho_Chi_Minh`.
- Apriori và xếp hạng món phổ biến chỉ dùng train. Mặc định support `0.04`, confidence `0.30`,
  lift `1.05`, tập món tối đa dài 3, lưu tối đa 500 luật và chỉ lấy vế phải một món.
- Xếp luật theo confidence, lift, support giảm dần. Chỉ áp dụng luật khi giỏ chứa toàn bộ vế trái;
  không gợi ý lại món đang chọn, không lặp cùng một món.
- Mỗi giỏ holdout có từ hai món được giấu một món bằng SHA-256 cố định của `basket_id`, dùng phần
  còn lại để gợi ý. Báo cáo tỷ lệ tìm lại món giấu trong top 3 và tỷ lệ giỏ có ít nhất một gợi ý.
- So sánh với top 3 món phổ biến trong train, cũng bỏ các món đã có trong giỏ.
- Giỏ holdout một món không đủ điều kiện đánh giá. Nếu không có giỏ đủ điều kiện, các chỉ số là `null`.
  Món chưa từng thấy trong train vẫn được tính khi kiểm tra.
- Không có luật đạt ngưỡng là kết quả hợp lệ; không thêm luật giả hoặc tự hạ ngưỡng sau khi xem holdout.
  Thử nhiều ngưỡng dựa trên holdout làm kết quả mang tính thăm dò; đánh giá cuối cần tập chưa dùng chọn ngưỡng.

Support/confidence/lift là quan hệ trong train, không phải độ chính xác triển khai. Dữ liệu mô phỏng
hoặc dữ liệu ít chỉ chứng minh quy trình; bài kiểm tra giấu món không đo thứ tự chọn món thực tế.

## Kết quả và tích hợp vào web

`apriori_model.json` chứa luật, nguồn dữ liệu, danh mục món, ngưỡng, phiên bản thư viện, hash CSV,
thời điểm chia tập và chỉ số đánh giá. Ngoài ra có `evaluation.json`, `association_rules.csv`,
`frequent_itemsets.csv`, `train_baskets.csv`, `holdout_baskets.csv`. Colab còn có `suggestions.json`.

Ứng dụng đọc bộ luật tại `fixtures/ai/apriori_model.json`, có thể đổi đường dẫn bằng biến môi trường
`APRIORI_MODEL_PATH`. File được kiểm tra schema, catalog, các vế luật và các chỉ số hữu hạn trước khi dùng.
Phần suy luận dùng Python chuẩn; máy chủ web không cần cài pandas, NumPy hay mlxtend.

Bộ luật hiện tại học từ 25 giỏ đã thanh toán trong database ứng dụng. Chủ dự án xác nhận các đơn là đơn test;
metadata ghi `data_provenance = test_orders_confirmed_by_owner`. Giao diện hiển thị chức năng gọi món bình thường,
không đưa các chỉ số đánh giá nhỏ mẫu vào lời giới thiệu cho khách.

Cách thử:

1. Mobile nhân viên: mở bàn → Gọi món → thêm một món. Mục **Gợi ý gọi thêm** xuất hiện khi có luật phù hợp.
2. POS desktop: chọn order → Món → thêm món; gợi ý cập nhật theo các món còn hiệu lực trong order.
3. Khách QR: chọn món vào giỏ → mở giỏ hàng → bấm **Thêm món** ở gợi ý để thêm bằng luồng giỏ hiện có.

Ví dụ với danh mục hiện tại: chọn **Cơm sườn nướng** có thể nhận **Rau muống xào tỏi**, **Trà chanh**,
tùy trạng thái bán hàng lúc truy vấn. Gợi ý không đưa lại món đã chọn, chỉ lấy món AVAILABLE có nhóm và đơn vị
còn hoạt động. Không có luật phù hợp thì ẩn mục gợi ý. Trạng thái món vẫn được kiểm tra lại khi lưu order/gửi bếp.

Endpoint đọc `GET /menu/recommendations/?dish=<id>&dish=<id>` trả tối đa 3 món kèm tên, giá và ID hiện tại.
Mapping bộ luật dùng mã món để dùng được khi PK khác giữa các database. File nguồn `synthetic_demo` không được
áp vào menu ứng dụng. ZIP gốc và giỏ dữ liệu thô được giữ local; repository chỉ chứa bộ luật/catalog cần chạy.

## Kiểm tra và cập nhật notebook

```powershell
$env:DJANGO_SETTINGS_MODULE='QLNH.test_settings'
.venv/Scripts/python.exe scripts/run_tests.py apps.orders.tests.test_ai_export
artifacts/ai/venv/Scripts/python.exe -m unittest discover -s ai_tools/tests -v
.venv/Scripts/python.exe scripts/run_tests.py apps.customer_portal.tests.test_recommendations
node --test scripts/test_menu_recommendations.cjs
.venv/Scripts/python.exe scripts/verify_staff_mobile_browser.py
.venv/Scripts/python.exe scripts/build_apriori_notebook.py
artifacts/ai/venv/Scripts/python.exe scripts/verify_apriori_notebook.py
artifacts/ai/venv/Scripts/python.exe scripts/verify_apriori_notebook.py --csv artifacts/ai/transactions.csv
```

Sau khi sửa mã trong `ai_tools`, chạy builder để hai notebook chứa đúng mã đã kiểm thử.
Notebook lưu không có output dữ liệu. Script kiểm tra chạy ô duy nhất từ một namespace trống và kiểm tra cả
worker Python độc lập; không cần tạo `MODEL`, `Path` hoặc các hàm ở ô khác trước.

Tham khảo: [Apriori](https://rasbt.github.io/mlxtend/user_guide/frequent_patterns/apriori/)
và [Association rules](https://rasbt.github.io/mlxtend/user_guide/frequent_patterns/association_rules/) của mlxtend.
