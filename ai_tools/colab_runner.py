"""Standard-library-only controller for the single runnable Colab cell."""

from datetime import datetime, timezone
from html import escape
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import warnings


def ensure_training_packages(requirements):
    missing = []
    for package, version in requirements.items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed = None
        if installed != version:
            missing.append(f"{package}=={version}")
    if missing:
        print("Đang cài thư viện. Bước này có thể mất vài phút ở lần đầu...", flush=True)
        process = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", *missing],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
        if process.returncode:
            raise RuntimeError("Chưa cài được thư viện. Chi tiết lỗi đầu tiên:\n" + process.stdout + process.stderr)


def execute_notebook(*, mode, cart_text, baskets, source, requirements, csv_path=None, work_dir=None, download=True):
    if mode not in {"demo", "csv"}:
        raise ValueError("DATA_MODE chỉ nhận demo hoặc csv.")
    if not isinstance(baskets, int) or baskets < 2:
        raise ValueError("Số giỏ mô phỏng phải là số nguyên từ 2 trở lên.")
    # Colab's Jupyter transport may emit this Python 3.13 warning for every print.
    # Leave installation/training exceptions and all other warnings visible.
    warnings.filterwarnings("ignore", message=r"datetime\.datetime\.utcnow\(\) is deprecated.*",
                            category=DeprecationWarning, module=r"jupyter_client\.session")
    try:
        from google.colab import files
    except ImportError:
        files = None
    print("1/4 — Chuẩn bị thư viện", flush=True)
    ensure_training_packages(requirements)
    root = Path(work_dir) if work_dir else Path("/content/qlnh_apriori" if files else "artifacts/ai/notebook")
    root.mkdir(parents=True, exist_ok=True)
    output = root / ("apriori_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    print("2/4 — Chuẩn bị dữ liệu", flush=True)
    if mode == "csv":
        if csv_path is None and files:
            print("Chọn file CSV đã xuất từ ứng dụng.", flush=True)
            uploaded = files.upload()
            candidates = [name for name in uploaded if name.lower().endswith(".csv")]
            if len(candidates) != 1:
                raise ValueError("Chọn đúng một file CSV giao dịch.")
            csv_path = candidates[0]
        if csv_path is None or not Path(csv_path).is_file():
            raise ValueError("Chưa có file CSV. Chọn demo để chạy thử hoặc tải CSV lên.")
    job = {"mode": mode, "cart_text": cart_text, "baskets": baskets, "output": str(output.resolve()),
           "csv_path": str(Path(csv_path).resolve()) if csv_path else None}
    print("3/4 — Chạy Apriori và kiểm tra gợi ý", flush=True)
    with TemporaryDirectory(prefix="qlnh-apriori-worker-") as directory:
        worker, job_file = Path(directory) / "worker.py", Path(directory) / "job.json"
        worker.write_text(source, encoding="utf-8")
        job_file.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        process = subprocess.run([sys.executable, "-u", str(worker), str(job_file)], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace")
        if process.returncode:
            raise RuntimeError("Bước chạy Apriori chưa hoàn tất. Chi tiết lỗi:\n" + process.stdout + process.stderr)
    model = json.loads((output / "apriori_model.json").read_text(encoding="utf-8"))
    inference = json.loads((output / "suggestions.json").read_text(encoding="utf-8"))
    names = {item["dish_id"]: item["dish_name"] for item in model["catalog"]}
    selected = [names[item] for item in inference["cart"]]
    suggestions = [names[item] for item in inference["suggestions"]]
    print("4/4 — ĐÃ CHẠY XONG", flush=True)
    print("Nguồn dữ liệu:", model["data_source"], "| Số giỏ:", inference["basket_count"])
    print("Số luật tìm được:", model["training"]["rule_count"])
    print("ĐANG CHỌN:", ", ".join(selected) or "Chưa chọn món")
    print("GỢI Ý:", ", ".join(suggestions) or "Chưa có gợi ý phù hợp")
    if inference["unknown"]:
        print("Không tìm thấy món:", ", ".join(inference["unknown"]), "— xem danh mục bên dưới và sửa MON_DANG_CHON.")
    if inference["ambiguous"]:
        print("Tên trùng nhiều món:", ", ".join(inference["ambiguous"]), "— nhập mã món hoặc dish_id để chọn rõ.")
    if mode == "demo":
        print("Đây là dữ liệu mô phỏng; kết quả này chỉ dùng chạy thử quy trình.")
    print("Đánh giá:", json.dumps(model["evaluation"], ensure_ascii=False, indent=2))
    try:
        from IPython.display import HTML, display
    except ImportError:
        for item in model["catalog"]:
            print(item["dish_id"], "—", item["dish_name"])
    else:
        rows = "".join("<tr><td>" + escape(item["dish_id"]) + "</td><td>" + escape(item["dish_code"])
                       + "</td><td>" + escape(item["dish_name"]) + "</td></tr>" for item in model["catalog"])
        display(HTML("<p><b>Đang chọn:</b> " + escape(", ".join(selected)) + "</p><p><b>Gợi ý:</b> "
                     + escape(", ".join(suggestions) or "Chưa có gợi ý phù hợp")
                     + "</p><details><summary>Danh mục món để thử tiếp</summary><table><tr><th>dish_id</th><th>Mã</th><th>Tên món</th></tr>"
                     + rows + "</table></details>"))
    archive = shutil.make_archive(str(output), "zip", root_dir=output)
    print("Kết quả:", output.resolve())
    if files and download:
        files.download(archive)
    return model, output, inference, archive
