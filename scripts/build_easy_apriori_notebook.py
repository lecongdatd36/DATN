"""Build the beginner notebook with a single independently runnable cell."""

import json


def build_easy_notebook(base):
    def embed(path):
        return "".join(line for line in (base / path).read_text(encoding="utf-8").splitlines(keepends=True)
                       if not line.startswith("from ai_tools."))

    worker = "\n\n".join(embed("ai_tools/" + name) for name in ("schema.py", "demo.py", "apriori.py", "notebook_job.py"))
    requirements = dict(line.split("==", 1) for line in (base / "requirements-ai.txt").read_text().splitlines()
                        if line.strip() and not line.startswith("#"))
    source = '''# @title ▶ BẤM NÚT NÀY ĐỂ CHẠY AI { display-mode: "form" }
DATA_MODE = "demo" # @param ["demo", "csv"]
MON_DANG_CHON = "Cơm trắng, Rau xào" # @param {type:"string"}
DEMO_BASKETS = 2000 # @param {type:"integer"}
'''
    source += "\n" + (base / "ai_tools/colab_runner.py").read_text(encoding="utf-8")
    source += "\n\nTRAINING_SOURCE = " + repr(worker) + "\n"
    source += "TRAINING_REQUIREMENTS = " + repr(requirements) + "\n"
    source += '''
MODEL, OUTPUT_DIR, INFERENCE, ARCHIVE = execute_notebook(
    mode=DATA_MODE, cart_text=MON_DANG_CHON, baskets=DEMO_BASKETS,
    source=TRAINING_SOURCE, requirements=TRAINING_REQUIREMENTS,
)
'''
    intro = '''# Chạy thử AI gợi ý món — chỉ bấm ▶ một lần

**Bản dễ dùng v2 — ô chạy độc lập, không cần chạy các ô khai báo hàm trước.**

1. Trong ô bên dưới, giữ `DATA_MODE = demo` để chạy thử.
2. Nhập món đang chọn ở `MON_DANG_CHON`, ngăn cách bằng dấu phẩy. Ví dụ: **Cơm trắng, Rau xào**.
3. Bấm **▶** ở bên trái **chính ô bên dưới**. Chờ đến khi hiện **4/4 — ĐÃ CHẠY XONG**.
4. Đọc **ĐANG CHỌN** và **GỢI Ý** ngay dưới ô. Muốn thử món khác, sửa tên rồi bấm lại ▶.

Lần đầu cần cài thư viện nên có thể mất vài phút. Bạn sẽ thấy tiến độ 1/4 → 4/4.
Để trống tên món sẽ lấy một ví dụ từ các luật vừa học. Có thể dùng tên món hoặc mã món.

**Demo dùng 2.000 giỏ mô phỏng**, không phải dữ liệu kinh doanh thực tế.
Chọn `csv` để tải file xuất từ ứng dụng; file chỉ cần dữ liệu giỏ món, không cần tên/SĐT khách.
'''
    after = '''## Kết quả bạn nhận được

- **ĐANG CHỌN / GỢI Ý**: các món đầu vào và món thuật toán đề xuất.
- **Danh mục món để thử tiếp**: mở bảng để xem tên và mã món hợp lệ.
- File ZIP: chứa luật JSON, báo cáo đánh giá, các bảng CSV và `suggestions.json`.

Nếu không có luật phù hợp, chương trình ghi rõ chưa có gợi ý. Nếu nhập tên không tồn tại,
sửa tên theo danh mục rồi bấm lại ▶. Các chỉ số trên dữ liệu demo chỉ chứng minh quy trình.

Mã xử lý vẫn có trong ô chạy (có thể mở phần code để xem). Bản giải thích từng hàm nằm ở
`notebooks/02_apriori_giai_thich_code.ipynb`. Gợi ý trên giao diện nhà hàng là bước tiếp theo.
'''
    notebook = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"colab": {"name": "01_apriori_goi_y_mon.ipynb", "provenance": []},
                     "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "cells": [
            {"cell_type": "markdown", "id": "intro-v2", "metadata": {}, "source": intro.splitlines(keepends=True)},
            {"cell_type": "code", "id": "run-all-v2", "metadata": {"cellView": "form"},
             "execution_count": None, "outputs": [], "source": source.splitlines(keepends=True)},
            {"cell_type": "markdown", "id": "results-v2", "metadata": {}, "source": after.splitlines(keepends=True)},
        ],
    }
    path = base / "notebooks/01_apriori_goi_y_mon.ipynb"
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(path)
