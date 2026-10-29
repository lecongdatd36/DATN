"""Build a Colab notebook containing the same tested code as ai_tools."""

import json
from build_easy_apriori_notebook import build_easy_notebook
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def cell(kind, source):
    result = {"cell_type": kind, "metadata": {}, "source": source.strip().splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def embedded(name):
    lines = (BASE / "ai_tools" / name).read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(line for line in lines if not line.startswith("from ai_tools."))


def main():
    dependencies = " ".join(line.strip() for line in (BASE / "requirements-ai.txt").read_text().splitlines()
                            if line.strip() and not line.startswith("#"))
    cells = [
        cell("markdown", """
# QLNH — Gợi ý món ăn bằng Apriori

Notebook chạy độc lập trên Google Colab, không cần kết nối database hoặc clone repository.
**Mặc định: dữ liệu mô phỏng `synthetic_demo`.** Các cặp món trong demo được tạo chủ ý;
kết quả chỉ chứng minh quy trình chạy được, không chứng minh độ chính xác kinh doanh thực tế.

Với CSV xuất từ ứng dụng, đổi `DATA_MODE` thành `csv` ở ô cấu hình. Nguồn
`application_export` không tự khẳng định đó là dữ liệu nhà hàng thật.

Quy trình: kiểm tra CSV → gom giỏ → chia theo ngày kinh doanh → Apriori trên train →
kiểm tra trên holdout mới hơn → so sánh món phổ biến → lưu luật và báo cáo JSON/CSV.
"""),
        cell("code", f"%pip install -q {dependencies}"),
        cell("markdown", """
## Mã xử lý

Bốn ô dưới đây được tạo từ `ai_tools/schema.py`, `inference.py`, `demo.py`, `apriori.py` và được kiểm thử
cùng mã CLI. Chạy lần lượt; thông thường bạn chỉ cần sửa ô cấu hình bên dưới.
"""),
        cell("code", embedded("schema.py")),
        cell("code", embedded("inference.py")),
        cell("code", embedded("demo.py")),
        cell("code", embedded("apriori.py")),
        cell("markdown", """
## Cấu hình và chọn dữ liệu

- `DATA_MODE = "demo"`: tạo 2.000 giỏ giả lập trong 180 ngày, không ghi database.
- `DATA_MODE = "csv"`: dùng CSV từ `manage.py export_ai_transactions`. Trên Colab sẽ
  hiện hộp chọn file nếu `CSV_PATH` chưa tồn tại. File không chứa tên/SĐT khách.
- Chọn ngưỡng trước khi xem kết quả holdout. Không trộn dữ liệu giả lập vào dữ liệu ứng dụng.
"""),
        cell("code", """
DATA_MODE = "demo"  # "demo" hoặc "csv"
CSV_PATH = Path("transactions.csv")
DEMO_BASKETS = 2000
DEMO_DAYS = 180
SEED = 42
MIN_SUPPORT = 0.04
MIN_CONFIDENCE = 0.30
MIN_LIFT = 1.05
TOP_K = 3
TEST_FRACTION = 0.20
DOWNLOAD_RESULTS = True
"""),
        cell("code", """
import shutil
try:
    from IPython.display import display
except ImportError:
    display = print

try:
    from google.colab import files
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
WORK_DIR = Path("/content/qlnh_apriori") if IN_COLAB else Path("artifacts/ai/notebook")
WORK_DIR.mkdir(parents=True, exist_ok=True)
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

if DATA_MODE == "demo":
    INPUT_CSV = write_demo_csv(WORK_DIR / f"synthetic_demo_{RUN_ID}.csv",
                               baskets=DEMO_BASKETS, days=DEMO_DAYS, seed=SEED)
elif DATA_MODE == "csv":
    INPUT_CSV = CSV_PATH
    if not INPUT_CSV.is_file() and IN_COLAB:
        from google.colab import files
        uploaded = files.upload()
        csv_names = [name for name in uploaded if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError("Chọn đúng một file CSV giao dịch.")
        INPUT_CSV = Path(csv_names[0])
    if not INPUT_CSV.is_file():
        raise FileNotFoundError("Chưa có CSV. Xuất dữ liệu rồi đặt CSV_PATH đúng vị trí file.")
else:
    raise ValueError("DATA_MODE chỉ nhận demo hoặc csv.")

transactions = load_transactions(INPUT_CSV)
if DATA_MODE == "demo" and transactions["data_source"].iloc[0] != "synthetic_demo":
    raise ValueError("Chế độ demo phải dùng dữ liệu synthetic_demo.")
print("Nguồn:", transactions["data_source"].iloc[0])
print("Số giỏ:", transactions["basket_id"].nunique(), "| Số món:", transactions["dish_id"].nunique())
display(transactions.head())
"""),
        cell("markdown", """
## Khai phá luật và đánh giá

Một giỏ là một lượt khách, kể cả khi tách thành nhiều hóa đơn. Chỉ lấy món đã phục vụ
trong các lượt đã hoàn tất thanh toán. Số lượng món không nhân bản số giao dịch.

Giữ khoảng 20% **ngày kinh doanh cuối** làm holdout, không chia ngẫu nhiên từng dòng.
Giỏ một món vẫn tham gia khai phá support nhưng không dùng bài kiểm tra giấu một món.
Mỗi giỏ holdout có từ hai món được giấu một món bằng quy tắc SHA-256 cố định của basket_id;
các món còn lại là đầu vào gợi ý. `hit_rate_at_k` là tỷ lệ tìm lại được món giấu trong top K;
`recommendation_coverage` là tỷ lệ giỏ có ít nhất một gợi ý. So sánh với top món phổ biến
chỉ tính trên train. Đây là bài kiểm tra giỏ hàng, không đo thứ tự gọi món thực tế.
"""),
        cell("code", """
OUTPUT_DIR = WORK_DIR / f"apriori_{RUN_ID}"
MODEL = run_experiment(INPUT_CSV, OUTPUT_DIR, min_support=MIN_SUPPORT,
                       min_confidence=MIN_CONFIDENCE, min_lift=MIN_LIFT,
                       test_fraction=TEST_FRACTION, k=TOP_K)
print(json.dumps({"nguon": MODEL["data_source"], "chia_du_lieu": MODEL["training"],
                  "danh_gia": MODEL["evaluation"]}, ensure_ascii=False, indent=2))
if not MODEL["rules"]:
    print("Không tìm được luật đạt ngưỡng. Đây là kết quả hợp lệ; không tạo luật giả để lấp chỗ trống.")
display(pd.DataFrame(MODEL["rules"]).head(10))
"""),
        cell("markdown", """
## Thử gợi ý món

Sửa `CART` thành danh sách dish_id của các món đang chọn. Ví dụ mặc định lấy vế trái
của một luật train để minh họa hoạt động, không phải một phép đo chất lượng bổ sung.
Khi tích hợp Django sau này cần lọc lại món còn bán bằng trạng thái thực tế lúc gợi ý.
"""),
        cell("code", """
CART = list(MODEL["rules"][0]["antecedents"]) if MODEL["rules"] else []
names = {item["dish_id"]: item["dish_name"] for item in MODEL["catalog"]}
suggestions = recommend(CART, MODEL["rules"], k=TOP_K)
print("Đang chọn:", [names.get(item, item) for item in CART])
print("Gợi ý:", [names.get(item, item) for item in suggestions])
"""),
        cell("markdown", """
## Lưu kết quả

File ZIP gồm `apriori_model.json`, `evaluation.json`, `association_rules.csv`,
`frequent_itemsets.csv`, `train_baskets.csv` và `holdout_baskets.csv`.
JSON lưu luật và metadata, không dùng pickle. Trường `data_source`, hash CSV, phiên bản
thư viện, ngưỡng và ngày chia tập giúp đối chiếu lại thí nghiệm. Nếu không có giỏ holdout
đủ hai món, chỉ số kiểm tra là `null`, không được diễn giải thành 0% hay 100%.

Support/confidence/lift mô tả liên hệ trên train. Dữ liệu ít hoặc dữ liệu mô phỏng cần
được ghi rõ trong báo cáo; không dùng các kết quả đó để tuyên bố độ chính xác thực tế.
"""),
        cell("code", """
ARCHIVE = shutil.make_archive(str(OUTPUT_DIR), "zip", root_dir=OUTPUT_DIR)
print("Kết quả:", OUTPUT_DIR.resolve())
print("ZIP:", ARCHIVE)
if IN_COLAB and DOWNLOAD_RESULTS:
    from google.colab import files
    files.download(ARCHIVE)
"""),
        cell("markdown", """
## Tài liệu tham khảo

- [Apriori — mlxtend](https://rasbt.github.io/mlxtend/user_guide/frequent_patterns/apriori/)
- [Association rules — mlxtend](https://rasbt.github.io/mlxtend/user_guide/frequent_patterns/association_rules/)

Phạm vi notebook này: đề xuất món bằng Apriori. Phần dự báo số đơn theo ngày là bước tiếp theo.
"""),
    ]
    for index, entry in enumerate(cells):
        entry["id"] = f"qlnh-apriori-{index:02d}"
    notebook = {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
                "metadata": {"colab": {"name": "02_apriori_giai_thich_code.ipynb", "provenance": []},
                             "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                             "language_info": {"name": "python", "version": "3.12"}}}
    path = BASE / "notebooks/02_apriori_giai_thich_code.ipynb"
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(path)
    build_easy_notebook(BASE)


if __name__ == "__main__":
    main()
