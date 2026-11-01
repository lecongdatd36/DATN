"""Generate a standalone, multi-step Colab notebook from the forecast source files."""
import ast
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODULES = ("forecast_store.py", "forecast_demo.py", "forecast_training.py", "forecast_notebook.py")


def cell(kind, source, name, hidden=False):
    result = {"cell_type": kind, "id": name, "metadata": {}, "source": source.strip().splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
        if hidden:
            result["metadata"] = {"cellView": "form"}
    return result


def function_source(path, name):
    source = path.read_text(encoding="utf-8-sig")
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, node)


def build():
    requirements = dict(line.split("==", 1) for line in (BASE / "requirements-forecast.txt").read_text().splitlines()
                        if line.strip() and not line.startswith("#"))
    modules = {"__init__.py": "", **{name: (BASE / "ai_tools" / name).read_text(encoding="utf-8-sig") for name in MODULES}}
    installer = function_source(BASE / "ai_tools/colab_runner.py", "ensure_training_packages")
    feature_code = function_source(BASE / "ai_tools/forecast_training.py", "feature_row")
    fit_code = function_source(BASE / "ai_tools/forecast_training.py", "fit_model")
    cells = [
        cell("markdown", """
# CƠM QUÊ — Random Forest dự báo số đơn trong 7 ngày

Notebook độc lập cho mục 3.6 của đề cương: kiểm tra CSV → tạo đặc trưng lịch sử →
huấn luyện/đánh giá → biểu đồ → học lại toàn bộ → dự báo 7 ngày → tải kết quả.

**Cách dùng:** mở trên Google Colab bằng **File → Upload notebook**, chọn Python 3 (>= 3.12),
chỉnh ô cấu hình rồi **Runtime → Run all**. CPU đủ để chạy; không cần GPU, database hoặc API key.
Mã nguồn xử lý đã được nhúng trong notebook, không cần clone repo. Chạy lại từ bước 2 tạo thư mục run mới.

**Mặc định là dữ liệu mô phỏng, seed 42. Kết quả không chứng minh chất lượng trên bán hàng thực tế.**
Nguồn `application_export` cũng có thể là đơn nhập thử; cần xác minh nguồn trước khi kết luận hiệu quả kinh doanh.
Notebook không tự thay đổi bộ kết quả Dashboard hay triển khai lên Render.
""", "intro"),
        cell("markdown", """
## 1. Chọn dữ liệu và ngày tham chiếu

- `DATA_MODE="demo"`, `DATA_SOURCE="mo_phong"`: tự sinh chuỗi ngày liên tục đến hết hôm trước ngày tham chiếu.
- `DATA_MODE="csv"`: tải CSV lên Colab (để trống `CSV_PATH`) hoặc nhập đường dẫn file đã có.
  Chọn đúng `DATA_SOURCE`: `mo_phong` cho CSV demo; `application_export` cho CSV xuất từ ứng dụng.
- `REFERENCE_DATE=""`: ngày hiện tại theo `Asia/Ho_Chi_Minh`.
  Có thể đặt `2026-12-12` để kiểm thử; khi đó đầu vào phải kết thúc ngày `2026-12-11`,
  dự báo cho `12/12–18/12/2026`. Với CSV lịch sử, nhập ngày ngay sau ngày cuối CSV.
- CSV phải có `ngay,so_don,nguon_du_lieu`, ít nhất **120 ngày liên tục**, số đơn nguyên không âm.
  Ngày theo `YYYY-MM-DD`, không thiếu/trùng ngày hoặc trộn hai nguồn. Không tự bù dữ liệu ứng dụng bằng mô phỏng.
- Những dòng từ ngày tham chiếu trở đi không được đưa vào snapshot huấn luyện.
""", "configuration-help"),
        cell("code", '''
#@title Cấu hình dữ liệu
DATA_MODE = "demo" #@param ["demo", "csv"]
DATA_SOURCE = "mo_phong" #@param ["mo_phong", "application_export"]
CSV_PATH = "" #@param {type:"string"}
REFERENCE_DATE = "" #@param {type:"string"}
DOWNLOAD_RESULTS = True #@param {type:"boolean"}
''', "configuration"),
        cell("markdown", """
## 2. Chuẩn bị thư viện và mã nguồn

Các thư viện huấn luyện dùng phiên bản cố định trong `requirements-forecast.txt`,
khớp môi trường AI hiện tại của dự án. Chỉ cài khi thiếu hoặc khác phiên bản.
Huấn luyện và vẽ biểu đồ chạy trong tiến trình Python mới, tránh dùng lại NumPy/pandas đã được kernel Colab nạp trước khi cài.
Lỗi cài đặt/huấn luyện sẽ được giữ lại để xử lý, không tự đổi mô hình hoặc nguồn dữ liệu.
""", "setup-help"),
        cell("code", f'''
#@title Chuẩn bị môi trường và mã xử lý (mở ô này nếu cần xem mã nhúng)
import csv
from html import escape
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

if sys.version_info < (3, 12):
    raise RuntimeError("Notebook cần Python >= 3.12. Hãy chọn runtime Python tương thích.")
TRAINING_REQUIREMENTS = {requirements!r}
{installer}

ensure_training_packages(TRAINING_REQUIREMENTS)
try:
    from google.colab import files as colab_files
except ImportError:
    colab_files = None
try:
    from IPython.display import display, HTML, Image
except ImportError:
    display, HTML, Image = print, None, None

WORK_ROOT = Path(os.environ.get("QLNH_FORECAST_NOTEBOOK_ROOT", "/content/qlnh_order_forecast" if colab_files else "artifacts/ai/forecast_notebook")).resolve()
SUPPORT_ROOT = WORK_ROOT / ("source_" + uuid4().hex[:12])
PACKAGE = SUPPORT_ROOT / "ai_tools"
PACKAGE.mkdir(parents=True, exist_ok=False)
SOURCE_FILES = {modules!r}
for name, content in SOURCE_FILES.items():
    (PACKAGE / name).write_text(content, encoding="utf-8")
for name in list(sys.modules):
    if name == "ai_tools" or name.startswith("ai_tools."):
        del sys.modules[name]
sys.path.insert(0, str(SUPPORT_ROOT))
from ai_tools.forecast_notebook import prepare_run, create_archive

def run_worker(action):
    env = dict(os.environ, PYTHONPATH=str(SUPPORT_ROOT), PYTHONIOENCODING="utf-8",
               MPLBACKEND="Agg", MPLCONFIGDIR=str(WORK_ROOT / ".matplotlib"))
    process = subprocess.run([sys.executable, "-m", "ai_tools.forecast_notebook", action, str(OUTPUT_DIR)],
                             cwd=SUPPORT_ROOT, env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if process.stdout:
        print(process.stdout)
    if process.returncode:
        raise RuntimeError("Bước " + action + " thất bại:\\n" + process.stderr)
    if process.stderr:
        print(process.stderr)

def show_csv(path, limit=10):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = [row for index, row in enumerate(reader) if index < limit]
    if HTML:
        header = "".join("<th>" + escape(name) + "</th>" for name in fields)
        body = "".join("<tr>" + "".join("<td>" + escape(str(row[name])) + "</td>" for name in fields) + "</tr>" for row in rows)
        display(HTML('<div style="overflow:auto"><table style="border-collapse:collapse" border="1" cellpadding="7"><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table></div>'))
    else:
        print(rows)

def show_chart(name):
    path = OUTPUT_DIR / "charts" / name
    if Image:
        display(Image(filename=str(path)))
    else:
        print("Biểu đồ:", path)

print("Đã chuẩn bị thư viện và mã nguồn. Thư mục làm việc:", WORK_ROOT)
''', "setup", hidden=True),
        cell("markdown", """
## 3. Đọc CSV, kiểm tra và tạo snapshot riêng

Mỗi lần chạy bước này tạo một run mới, giữ nguyên kết quả cũ. `input.csv` chỉ gồm 3 cột tổng hợp,
không đưa các cột phụ trong CSV tải lên vào ZIP kết quả. Không đọc hoặc ghi database nghiệp vụ.
""", "prepare-help"),
        cell("code", '''
input_path = CSV_PATH.strip() or None
if DATA_MODE == "csv" and input_path is None:
    if colab_files is None:
        raise FileNotFoundError("Chạy ngoài Colab: cần đặt CSV_PATH đến file CSV có sẵn.")
    uploaded = colab_files.upload()
    if len(uploaded) != 1 or not next(iter(uploaded)).lower().endswith(".csv"):
        raise ValueError("Hãy chọn đúng một file CSV số đơn theo ngày.")
    input_path = next(iter(uploaded))

OUTPUT_DIR = prepare_run(root=WORK_ROOT, mode=DATA_MODE, source=DATA_SOURCE,
                         reference_date=REFERENCE_DATE.strip() or None, csv_path=input_path)
DATASET = json.loads((OUTPUT_DIR / "dataset.json").read_text(encoding="utf-8"))
print("Nguồn:", DATASET["data_source"], "| Run:", DATASET["run_id"])
print("Dữ liệu học:", DATASET["training_first_date"], "đến", DATASET["training_last_date"], "|", DATASET["training_days"], "ngày")
print("Dòng từ ngày tham chiếu trở đi đã loại:", DATASET["excluded_future_rows"])
print(DATASET["limitation"])
show_csv(OUTPUT_DIR / "input.csv", limit=7)
''', "prepare"),
        cell("markdown", f"""
## 4. Đặc trưng và mô hình được sử dụng

| Đặc trưng | Ý nghĩa |
|---|---|
| `thu`, `cuoi_tuan`, `chi_so_ngay` | Thứ trong tuần, cuối tuần, số ngày tính từ mốc đầu |
| `don_hom_qua` | Số đơn ngày trước |
| `don_7_ngay_truoc`, `don_14_ngay_truoc`, `don_28_ngay_truoc` | Số đơn cùng ngày cách 7/14/28 ngày |
| `trung_binh_7_ngay`, `trung_binh_28_ngay` | Trung bình **các ngày trước**, không chứa ngày cần dự báo |

Random Forest: **200 cây**, `max_depth=8`, `min_samples_leaf=3`, `random_state=42`.
Mã dưới đây lấy từ cùng file nguồn được nhúng và thực thi trong notebook:

```python
{feature_code}

{fit_code}
```

**Dự báo nhiều bước:** ngày thứ hai dùng kết quả dự báo ngày thứ nhất cho giá trị trễ chưa có thực tế;
không lấy dữ liệu thực tế trong 7 ngày kiểm tra để đưa vào đặc trưng giữa lượt dự báo.

**Đánh giá:** giữ 28 ngày cuối, chia 4 lượt liên tiếp × 7 ngày. Mỗi lượt học lại chỉ từ dữ liệu trước lượt đó.
Baseline dùng số đơn cùng thứ tuần trước. Sau đánh giá mới học lại toàn bộ dữ liệu để dự báo 7 ngày mới.
Không chia ngẫu nhiên chuỗi thời gian và không chọn lại tham số dựa trên cùng 28 ngày rồi coi đó là kiểm tra độc lập.
""", "model-explanation"),
        cell("code", '''
run_worker("train")
EVALUATION = json.loads((OUTPUT_DIR / "evaluation.json").read_text(encoding="utf-8"))
print("MAE Random Forest:", round(EVALUATION["mae_ai"], 3), "đơn/ngày")
print("MAE baseline:", round(EVALUATION["mae_baseline"], 3), "đơn/ngày")
print("RMSE Random Forest:", round(EVALUATION["rmse_ai"], 3), "đơn/ngày")
''', "train"),
        cell("markdown", """
## 5. Đánh giá và biểu đồ

MAE là sai số tuyệt đối trung bình, tính theo đơn/ngày; RMSE làm nổi rõ hơn sai số lớn.
Các chỉ số dùng dự báo chưa làm tròn. Kết quả không bảo đảm Random Forest tốt hơn baseline.
Vạch dọc trên biểu đồ đánh giá chia 4 lượt dự báo. Không có khoảng tin cậy vì pipeline chưa ước lượng đại lượng đó.
""", "evaluation-help"),
        cell("code", '''
run_worker("report")
REPORT = json.loads((OUTPUT_DIR / "notebook_report.json").read_text(encoding="utf-8"))
print(REPORT["conclusion"])
print("RMSE baseline:", round(REPORT["rmse_baseline"], 3), "đơn/ngày")
if REPORT["mae_improvement_percent"] is not None:
    print("Mức giảm MAE so với baseline:", round(REPORT["mae_improvement_percent"], 2), "% (âm nghĩa là kém hơn)")
else:
    print("Baseline có MAE = 0; không chia cho 0 để tính phần trăm cải thiện.")
show_csv(OUTPUT_DIR / "mae_theo_luot.csv")
show_csv(OUTPUT_DIR / "mae_theo_buoc.csv")
show_chart("01_lich_su.png")
show_chart("02_kiem_tra_28_ngay.png")
show_chart("03_mae_theo_buoc.png")
''', "evaluation"),
        cell("markdown", """
## 6. Dự báo 7 ngày tiếp theo và giải thích đặc trưng

Bảng dưới là dự báo mới sau khi học lại toàn bộ snapshot; số đơn nguyên, không âm.
Biểu đồ feature importance MDI mô tả mô hình cuối, không chứng minh nguyên nhân hoặc độ chính xác ngoài dữ liệu học.
Không gọi những đặc trưng có điểm cao là nguyên nhân làm tăng số đơn.
""", "forecast-help"),
        cell("code", '''
show_csv(OUTPUT_DIR / "du_bao_7_ngay.csv")
show_chart("04_du_bao_7_ngay.png")
show_csv(OUTPUT_DIR / "feature_importance.csv")
show_chart("05_dac_trung.png")
for limitation in REPORT["limitations"]:
    print("•", limitation)
''', "forecast"),
        cell("markdown", """
## 7. Tải bộ kết quả

ZIP chứa snapshot CSV, model `forecast_demo.joblib`, dự báo 7 ngày, 28 ngày đánh giá,
MAE theo lượt/bước, feature importance, 5 biểu đồ PNG, metadata, phiên bản thư viện và manifest checksum.
Tên model được giữ tương thích mã hiện có; hãy đọc `data_source` trong metadata để xác định nguồn.
Chỉ mở model joblib từ nguồn tin cậy và dùng môi trường thư viện tương thích.

Notebook **không công bố lên Dashboard**. Web chỉ đọc các run được updater kiểm tra và công bố riêng.
Không chép đè từng file vào bộ đang chạy trên website. CSV mô phỏng và CSV ứng dụng vẫn là hai nguồn tách biệt.
""", "download-help"),
        cell("code", '''
ARCHIVE = create_archive(OUTPUT_DIR)
print("Đã lưu run:", OUTPUT_DIR)
print("ZIP:", ARCHIVE)
if DOWNLOAD_RESULTS and colab_files is not None:
    colab_files.download(str(ARCHIVE))
elif DOWNLOAD_RESULTS:
    print("Chạy local: mở file ZIP ở đường dẫn trên.")
''', "download"),
        cell("markdown", """
## Tài liệu và giới hạn

- [Colab: mở/tải notebook](https://research.google.com/colaboratory/faq.html)
- [Colab: upload/download file](https://github.com/googlecolab/colabtools/blob/main/google/colab/files.py)
- [RandomForestRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html)
- [Giới hạn feature importance dựa trên impurity](https://scikit-learn.org/stable/auto_examples/inspection/plot_permutation_importance.html)

Đây là thí nghiệm tái lập quy trình dự báo đang có. Muốn đánh giá hiệu quả nhà hàng thực tế cần dữ liệu vận hành được xác minh,
nhiều giai đoạn kiểm tra và đối chiếu nhu cầu thực tế; không suy ra chất lượng kinh doanh từ dữ liệu mô phỏng.
""", "references"),
    ]
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"colab": {"name": "03_random_forest_du_bao_so_don.ipynb", "provenance": []},
                         "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python", "version": "3.12"}}}


def main():
    target = BASE / "notebooks/03_random_forest_du_bao_so_don.ipynb"
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
