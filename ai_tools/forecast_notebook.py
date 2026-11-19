"""Offline notebook preparation/reporting. Training uses the unchanged forecast pipeline."""
import argparse
from datetime import date, datetime, timedelta, timezone
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
from uuid import uuid4
import zipfile

from .forecast_demo import FIELDS, extend_demo
from .forecast_store import (SOURCES, atomic_bytes, atomic_json, csv_bytes, load_bundle,
                             read_daily, sha256, training_rows, vietnam_today)

PLOTS = ("01_lich_su.png", "02_kiem_tra_28_ngay.png", "03_mae_theo_buoc.png",
         "04_du_bao_7_ngay.png", "05_dac_trung.png")


def prepare_run(*, root, mode="demo", source="mo_phong", reference_date=None, csv_path=None):
    if mode not in ("demo", "csv") or source not in SOURCES:
        raise ValueError("Chế độ phải là demo/csv; nguồn phải là mo_phong/application_export.")
    if mode == "demo" and source != "mo_phong":
        raise ValueError("Không sinh dữ liệu mô phỏng cho nguồn application_export. Hãy chọn csv.")
    reference = date.fromisoformat(reference_date) if reference_date else vietnam_today()
    if mode == "csv" and (not csv_path or not Path(csv_path).is_file()):
        raise FileNotFoundError("Chưa có CSV. Hãy tải đúng một CSV hoặc đặt CSV_PATH; không chuyển sang demo.")
    run_id = "notebook_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:12]
    folder = Path(root).resolve() / run_id
    folder.mkdir(parents=True, exist_ok=False)
    original = Path(csv_path) if mode == "csv" else folder / "demo_input.csv"
    if mode == "demo":
        extend_demo(original, reference - timedelta(days=1))
    all_rows = read_daily(original, source)
    rows = training_rows(original, source, reference)
    # Export only the three public aggregate fields, never extra uploaded columns.
    snapshot = [{key: row[key] for key in FIELDS} for row in rows]
    atomic_bytes(folder / "input.csv", csv_bytes(snapshot, FIELDS))
    dataset = {
        "run_id": run_id, "data_source": source, "data_mode": mode,
        "reference_date": reference.isoformat(), "timezone": "Asia/Ho_Chi_Minh",
        "training_days": len(rows), "training_first_date": rows[0]["ngay"],
        "training_last_date": rows[-1]["ngay"], "uploaded_rows": len(all_rows),
        "excluded_future_rows": len(all_rows) - len(rows), "source_sha256": sha256(original.read_bytes()),
        "input_sha256": sha256((folder / "input.csv").read_bytes()),
        "evaluation_first_date": (reference - timedelta(days=28)).isoformat(),
        "limitation": ("Dữ liệu mô phỏng, chưa chứng minh chất lượng trên bán hàng thực tế."
                       if source == "mo_phong" else
                       "Nguồn CSV ứng dụng do người dùng cung cấp; có thể chứa đơn thử, chưa xác minh dữ liệu kinh doanh thực tế."),
    }
    atomic_json(folder / "dataset.json", dataset)
    return folder


def read_dataset(folder):
    folder = Path(folder)
    dataset = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    if dataset["run_id"] != folder.name:
        raise ValueError("Run ID không khớp thư mục notebook.")
    if dataset["input_sha256"] != sha256((folder / "input.csv").read_bytes()):
        raise ValueError("CSV đầu vào đã thay đổi sau bước kiểm tra.")
    rows = training_rows(folder / "input.csv", dataset["data_source"], date.fromisoformat(dataset["reference_date"]))
    if len(rows) != dataset["training_days"]:
        raise ValueError("Số ngày không khớp metadata.")
    return dataset


def train_run(folder):
    from .forecast_training import train
    folder = Path(folder)
    dataset = read_dataset(folder)
    train(folder / "input.csv", folder, dataset["data_source"],
          date.fromisoformat(dataset["reference_date"]), dataset["run_id"])
    load_bundle(folder, dataset["data_source"], date.fromisoformat(dataset["reference_date"]), dataset["run_id"], full=True)


def create_report(folder):
    import joblib
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from .forecast_training import FEATURES

    folder = Path(folder)
    if (folder / "notebook_report.json").exists():
        raise FileExistsError("Báo cáo đã tồn tại. Chạy lại từ bước tạo run để giữ lịch sử.")
    dataset = read_dataset(folder)
    report, _ = load_bundle(folder, dataset["data_source"], date.fromisoformat(dataset["reference_date"]),
                            dataset["run_id"], full=True)
    history = pd.read_csv(folder / "input.csv", parse_dates=["ngay"])
    evaluation = pd.read_csv(folder / "kiem_tra_du_bao.csv", parse_dates=["ngay", "ngay_bat_dau_du_bao"])
    future = pd.read_csv(folder / "du_bao_7_ngay.csv", parse_dates=["ngay"])
    evaluation["sai_so_ai"] = abs(evaluation["thuc_te"] - evaluation["du_bao_ai"])
    evaluation["sai_so_baseline"] = abs(evaluation["thuc_te"] - evaluation["du_bao_tuan_truoc"])
    by_horizon = evaluation.groupby("buoc_du_bao", as_index=False).agg(
        mae_ai=("sai_so_ai", "mean"), mae_baseline=("sai_so_baseline", "mean"),
    )
    by_origin = evaluation.groupby("ngay_bat_dau_du_bao", as_index=False).agg(
        mae_ai=("sai_so_ai", "mean"), mae_baseline=("sai_so_baseline", "mean"), so_ngay=("ngay", "size"),
    )
    by_horizon.to_csv(folder / "mae_theo_buoc.csv", index=False, encoding="utf-8-sig")
    by_origin.to_csv(folder / "mae_theo_luot.csv", index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    # This file was trained in this run and validated above; no uploaded joblib is loaded.
    payload = joblib.load(folder / "forecast_demo.joblib")
    model = payload["model"]
    importance = pd.DataFrame({"dac_trung": FEATURES, "muc_quan_trong": model.feature_importances_})
    importance = importance.sort_values("muc_quan_trong", ascending=False)
    importance.to_csv(folder / "feature_importance.csv", index=False, encoding="utf-8-sig")
    plots = folder / "charts"
    plots.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 13, "figure.facecolor": "white"})
    ai_color, base_color, actual_color = "#9d1231", "#ba862d", "#254e42"
    source_label = "Dữ liệu mô phỏng" if dataset["data_source"] == "mo_phong" else "CSV ứng dụng — nguồn chưa xác minh"

    def save(fig, ax, name, dated=True):
        ax.set_ylabel("Số đơn / ngày")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
        if dated:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
            fig.autofmt_xdate(rotation=25)
        fig.text(0.01, 0.01, source_label, color="#666666", fontsize=9)
        fig.tight_layout(rect=(0, .045, 1, 1))
        fig.savefig(plots / name, dpi=160)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(history["ngay"], history["so_don"], color=actual_color, linewidth=1.1)
    ax.axvspan(evaluation["ngay"].min(), evaluation["ngay"].max(), color=base_color, alpha=.16, label="28 ngày đánh giá")
    ax.set_title("Lịch sử số đơn trước ngày tham chiếu")
    ax.legend()
    save(fig, ax, PLOTS[0])

    fig, ax = plt.subplots(figsize=(12, 4.8))
    for column, label, color in (("thuc_te", "Thực tế", actual_color), ("du_bao_ai", "Random Forest", ai_color),
                                  ("du_bao_tuan_truoc", "Cùng thứ tuần trước", base_color)):
        ax.plot(evaluation["ngay"], evaluation[column], marker="o", markersize=3, label=label, color=color)
    for start in evaluation["ngay_bat_dau_du_bao"].drop_duplicates().iloc[1:]:
        ax.axvline(start, color="#aaaaaa", linewidth=.8, linestyle=":")
    ax.set_title("4 lượt dự báo 7 ngày trên 28 ngày cuối — đánh giá cuốn chiếu")
    ax.legend(ncols=3)
    save(fig, ax, PLOTS[1])

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(by_horizon["buoc_du_bao"] - .18, by_horizon["mae_ai"], .36, color=ai_color, label="Random Forest")
    ax.bar(by_horizon["buoc_du_bao"] + .18, by_horizon["mae_baseline"], .36, color=base_color, label="Cùng thứ tuần trước")
    ax.set_title("MAE theo bước dự báo — mỗi bước có 4 lần kiểm tra")
    ax.set_xlabel("Bước dự báo (ngày)")
    ax.set_xticks(range(1, 8))
    ax.legend()
    save(fig, ax, PLOTS[2], dated=False)

    fig, ax = plt.subplots(figsize=(12, 4.8))
    tail = history.tail(28)
    ax.plot(tail["ngay"], tail["so_don"], marker="o", markersize=3, color=actual_color, label="Lịch sử 28 ngày")
    ax.plot(future["ngay"], future["so_don_du_kien"], marker="o", linestyle="--", color=ai_color, label="Dự báo 7 ngày")
    ax.axvline(future["ngay"].iloc[0], color="#aaaaaa", linestyle=":")
    ax.set_title("Dự báo số đơn 7 ngày sau khi học lại toàn bộ lịch sử")
    ax.legend()
    save(fig, ax, PLOTS[3])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(importance["dac_trung"][::-1], importance["muc_quan_trong"][::-1], color=ai_color)
    ax.set_title("Mức quan trọng đặc trưng trong mô hình cuối (MDI)")
    ax.set_xlabel("Tỷ trọng giảm độ hỗn tạp; không phải quan hệ nhân quả")
    ax.grid(axis="x", alpha=.18)
    fig.text(.01, .01, source_label, color="#666666", fontsize=9)
    fig.tight_layout(rect=(0, .045, 1, 1))
    fig.savefig(plots / PLOTS[4], dpi=160)
    plt.close(fig)

    base_rmse = float(np.sqrt(np.mean((evaluation["thuc_te"] - evaluation["du_bao_tuan_truoc"]) ** 2)))
    improvement = ((report["mae_baseline"] - report["mae_ai"]) / report["mae_baseline"] * 100
                   if report["mae_baseline"] else None)
    result = {
        **report, "rmse_baseline": base_rmse, "mae_improvement_percent": improvement,
        "model_parameters": model.get_params(), "feature_names": FEATURES,
        "versions": {name: metadata.version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "matplotlib", "tzdata")},
        "python_version": platform.python_version(), "charts": list(PLOTS),
        "excluded_future_rows": dataset["excluded_future_rows"],
        "conclusion": ("MAE Random Forest thấp hơn baseline trong phép kiểm tra này."
                       if report["mae_ai"] < report["mae_baseline"] else
                       "Random Forest chưa có MAE thấp hơn baseline trong phép kiểm tra này."),
        "limitations": [dataset["limitation"],
                        "Không dùng kết quả đánh giá này để tự chọn lại tham số rồi báo cùng tập là kiểm tra độc lập.",
                        "Dự báo nhiều ngày dùng lại dự báo các bước trước; không dùng số thực tế tương lai.",
                        "Feature importance MDI chỉ mô tả mô hình cuối trên train, không chứng minh quan hệ nhân quả.",
                        "Notebook tạo kết quả offline; không tự công bố lên Dashboard hoặc thay đổi hosting."],
    }
    atomic_json(folder / "notebook_report.json", result)
    (folder / "README_KET_QUA.md").write_text(
        f"# Kết quả Random Forest QLNH\n\nRun: {dataset['run_id']}\n\nNguồn: {dataset['data_source']}\n\n"
        f"{dataset['limitation']}\n\nDữ liệu học đến {dataset['training_last_date']}; "
        f"dự báo bắt đầu {dataset['reference_date']}.\n\n{result['conclusion']}\n\n"
        "Không tự đưa file này lên Dashboard. Model joblib chỉ nên mở khi tin cậy nguồn; "
        "cần môi trường thư viện tương thích ghi trong notebook_report.json.\n",
        encoding="utf-8",
    )
    return result


def create_archive(folder):
    folder = Path(folder)
    dataset = read_dataset(folder)
    load_bundle(folder, dataset["data_source"], date.fromisoformat(dataset["reference_date"]), dataset["run_id"], full=True)
    report = json.loads((folder / "notebook_report.json").read_text(encoding="utf-8"))
    if report["run_id"] != dataset["run_id"] or report["data_source"] != dataset["data_source"]:
        raise ValueError("Báo cáo và dữ liệu không thuộc cùng lần chạy.")
    names = ["input.csv", "dataset.json", "forecast_demo.joblib", "evaluation.json", "du_bao_7_ngay.csv",
             "kiem_tra_du_bao.csv", "mae_theo_buoc.csv", "mae_theo_luot.csv", "feature_importance.csv",
             "notebook_report.json", "README_KET_QUA.md", *[f"charts/{name}" for name in PLOTS]]
    hashes = {name: sha256((folder / name).read_bytes()) for name in names}
    manifest = {"run_id": dataset["run_id"], "data_source": dataset["data_source"], "sha256": hashes}
    archive = folder.parent / (folder.name + "_" + uuid4().hex[:8] + ".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as stream:
        for name in names:
            stream.write(folder / name, name)
        stream.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("train", "report"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.action == "train":
        train_run(args.folder)
    else:
        create_report(args.folder)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
