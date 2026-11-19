# Notebook Random Forest dự báo số đơn trên Colab

Notebook: [`notebooks/03_random_forest_du_bao_so_don.ipynb`](../notebooks/03_random_forest_du_bao_so_don.ipynb).
Nhánh triển khai: `feat/random-forest-colab`. Đây là phần trình diễn quy trình huấn luyện theo mục 3.6 của đề cương.

## Cách chạy trên Google Colab

1. Mở [Google Colab](https://colab.research.google.com/), chọn **File → Upload notebook** và tải file `.ipynb` lên.
2. Dùng Python >= 3.12. Giữ cấu hình mặc định `DATA_MODE="demo"`, `DATA_SOURCE="mo_phong"` để thử dữ liệu mô phỏng.
3. Chọn **Runtime → Run all**. Notebook tự chuẩn bị thư viện, dữ liệu, chạy huấn luyện và tạo báo cáo. CPU đủ để chạy; không cần GPU hoặc API key.
4. Xem 4 lượt đánh giá, chỉ số MAE/RMSE, bảng dự báo 7 ngày, 5 biểu đồ và tải ZIP ở ô cuối.

Các bước mở notebook được mô tả trong [FAQ chính thức của Colab](https://research.google.com/colaboratory/faq.html).
Notebook dùng API [upload/download chính thức](https://github.com/googlecolab/colabtools/blob/main/google/colab/files.py).
Không cần đăng nhập database hay clone repository vào Colab.

### Sử dụng CSV có sẵn

CSV có ba cột:

```csv
ngay,so_don,nguon_du_lieu
2026-07-01,42,application_export
2026-07-02,39,application_export
```

Ví dụ trên chỉ minh họa cấu trúc, chưa đủ số ngày để huấn luyện. Dữ liệu cần ít nhất **120 ngày liên tục**, đúng thứ tự,
không thiếu/trùng ngày; số đơn nguyên không âm và toàn bộ file cùng một nguồn.

- Đặt `DATA_MODE="csv"`.
- Chọn `DATA_SOURCE="application_export"` nếu CSV xuất từ ứng dụng; chọn `mo_phong` nếu CSV demo.
- Để trống `CSV_PATH` để hiện hộp chọn đúng một file CSV trên Colab. Hoặc điền đường dẫn file đã tải lên.
- `REFERENCE_DATE=""` dùng ngày hiện tại ở Việt Nam. Dữ liệu huấn luyện phải kết thúc hết hôm qua.
- Với CSV lịch sử, đặt ngày tham chiếu là ngày ngay sau ngày cuối dữ liệu. Ví dụ dữ liệu đến 11/12/2026,
  đặt `REFERENCE_DATE="2026-12-12"` để dự báo 12/12–18/12/2026.

Không tự vá ngày bị thiếu, không đổi nguồn và không chuyển sang demo khi CSV ứng dụng không hợp lệ.
Những dòng từ ngày tham chiếu trở đi bị loại trước khi tạo snapshot; các cột phụ không được đưa vào ZIP kết quả.
Nguồn `application_export` chỉ mô tả nguồn cấu trúc, không chứng minh đây là dữ liệu kinh doanh thật.

CSV ứng dụng có thể xuất bằng `scripts/export_daily_orders.py` (xem [hướng dẫn dự báo hằng ngày](forecast-daily.md)).
Ngày bắt đầu phải thuộc khoảng dữ liệu đã được quan sát/xác nhận; không kéo dài khoảng xuất hoặc bổ sung ngày giả chỉ để đủ 120 ngày.

## Nội dung và cách đánh giá

16 ô gồm cấu hình, chuẩn bị thư viện, đọc/kiểm tra CSV, giải thích đặc trưng và mã model, huấn luyện,
đánh giá, biểu đồ, dự báo và đóng gói. Các ô code chạy theo thứ tự từ namespace mới; không cần chuẩn bị biến ở notebook khác.

Mã `forecast_training.py`, `forecast_store.py` và `forecast_demo.py` được nhúng từ cùng nguồn đang dùng cho dự báo của ứng dụng:

- RandomForestRegressor: 200 cây, độ sâu tối đa 8, tối thiểu 3 mẫu ở lá, seed 42.
- 9 đặc trưng từ lịch và số đơn trễ/trung bình lịch sử. Giá trị của ngày cần dự báo không được đưa vào đặc trưng.
- 28 ngày cuối chia thành 4 lượt × 7 ngày. Mỗi lượt học lại chỉ bằng dữ liệu trước lượt đó.
- Dự báo nhiều bước dùng kết quả dự báo trước đó cho những giá trị trễ chưa có thực tế.
- Baseline: cùng thứ tuần trước. Chỉ số tính trên dự báo chưa làm tròn; bảng dự báo sử dụng số nguyên không âm.
- Sau đánh giá, model cuối học lại toàn bộ snapshot để dự báo 7 ngày mới.

Kết luận phụ thuộc số đo: có thể tốt hơn, bằng hoặc kém baseline. Nếu baseline MAE bằng 0, không tính phần trăm cải thiện bằng phép chia cho 0.
Không tự thay ngưỡng hoặc tham số sau khi xem tập kiểm tra rồi dùng lại tập đó để khẳng định đánh giá độc lập.

Thư viện được khóa trong [`requirements-forecast.txt`](../requirements-forecast.txt), tách khỏi môi trường Django và khỏi bộ Apriori.
Huấn luyện/vẽ chạy trong worker Python mới để tránh dùng các thư viện số đã nạp ở kernel Colab trước khi cài phiên bản yêu cầu.
Matplotlib được bổ sung vào `artifacts/ai/forecast_venv`; không cài pandas, NumPy, sklearn hoặc matplotlib vào `.venv` web.

## Kết quả tải xuống

Mỗi lần tạo snapshot có run ID và thư mục mới; không ghi đè model của run trước. ZIP gồm:

- `input.csv`, `dataset.json`: snapshot trước ngày tham chiếu, thông tin nguồn, cutoff và checksum.
- `forecast_demo.joblib`: model cuối và các thông tin cần tái sử dụng. Tên giữ tương thích; nguồn xác định bằng metadata.
- `du_bao_7_ngay.csv`, `kiem_tra_du_bao.csv`, `evaluation.json`: dự báo 7 ngày và 28 ngày đánh giá.
- `mae_theo_luot.csv`, `mae_theo_buoc.csv`, `feature_importance.csv`.
- 5 PNG: lịch sử, thực tế–dự báo–baseline, MAE theo bước, dự báo mới và mức quan trọng đặc trưng.
- `notebook_report.json`: tham số, phiên bản Python/thư viện, chỉ số, kết luận và hạn chế.
- `README_KET_QUA.md`, `manifest.json`: mô tả và checksum từng file trong ZIP.

Đã mở và xem cả 5 biểu đồ của run kiểm tra; chữ tiếng Việt, chú giải và mốc ngày hiển thị rõ.
Feature importance MDI mô tả mô hình cuối, không phải quan hệ nhân quả hoặc chất lượng ngoài tập học.
Không tạo khoảng tin cậy vì pipeline chưa ước lượng đại lượng này.

ZIP không chứa CSV gốc có cột phụ, không chứa cấu hình `.env`, bản sao lưu database hoặc hồ sơ khách hàng.
Chỉ mở joblib từ nguồn tin cậy và dùng phiên bản thư viện tương thích.

## Quan hệ với Dashboard

Notebook là quy trình offline, không thay thế scheduler, không tạo `current.json`, không công bố hoặc ghi đè bộ dự báo trên website.
Các yêu cầu kiểm tra/công bố nguyên tử vẫn thuộc [luồng cập nhật hằng ngày](forecast-daily.md).
Không chép rời từng file trong ZIP vào thư mục đang được web sử dụng; không tự sửa thời gian hệ thống để thử notebook.

## Chạy và kiểm tra cục bộ

```powershell
# Chỉ khi tạo môi trường AI mới; không cài vào môi trường Django:
.\.venv\Scripts\python.exe -m venv artifacts\ai\forecast_venv
.\artifacts\ai\forecast_venv\Scripts\python.exe -m pip install -r requirements-forecast.txt

# Dựng lại notebook khi sửa nguồn:
.\.venv\Scripts\python.exe -X utf8 scripts\build_forecast_notebook.py

# Kiểm thử chuẩn bị dữ liệu, đồng bộ mã nhúng:
.\.venv\Scripts\python.exe -X utf8 -m unittest ai_tools.tests.test_forecast_notebook ai_tools.tests.test_forecast_update

# Kiểm thử logic huấn luyện và trường hợp mọi ngày có 0 đơn:
.\artifacts\ai\forecast_venv\Scripts\python.exe -X utf8 -m unittest scripts.test_order_forecast_training scripts.test_forecast_notebook_training

# Chạy mọi code cell, gồm worker thật và ZIP/PNG:
.\artifacts\ai\forecast_venv\Scripts\python.exe -X utf8 scripts\verify_forecast_notebook.py
```

Không chạy lại lệnh tạo venv lên môi trường đang dùng chỉ để mở notebook. Có thể thực thi notebook bằng môi trường AI đã có.
Chạy local lưu tại `artifacts/ai/forecast_notebook/`; verifier lưu run/log tại `artifacts/ai/forecast_notebook_validation/`.
Các artifact không được đưa vào Git; notebook trong repo không có output huấn luyện hoặc dữ liệu người dùng.

Verifier chạy demo và CSV **fixture mô phỏng gắn schema ứng dụng**, không xuất hoặc tạo đơn giả trong database.
Nó kiểm tra 7 ngày, cutoff, 4 lượt/28 dòng đánh giá, loại dữ liệu tương lai, loại cột phụ, checksum ZIP,
đọc PNG và adapter upload/download Colab bằng mock. Đây là thực thi các ô cục bộ, **chưa phải chạy trong phiên Google Colab thật**.

Đã chạy qua 24 kiểm thử chuẩn bị dữ liệu/cập nhật và 4 kiểm thử trong môi trường AI, gồm dữ liệu mọi ngày có 0 đơn,
dự báo 01/01–07/01/2027, tránh chia cho 0, giữ run cũ và từ chối model sai checksum. Django check không có lỗi;
đã xác nhận `.venv` web vẫn không có NumPy, pandas, sklearn và matplotlib.

Phần mặc định vẫn là **demo dữ liệu mô phỏng, chưa chứng minh chất lượng dự báo trên dữ liệu bán hàng thực tế**.
