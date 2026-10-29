"""Apriori experiment shared by the CLI and the self-contained Colab notebook."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import mlxtend
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

from ai_tools.schema import DATA_SOURCES, SCHEMA_VERSION, TRANSACTION_FIELDS
from ai_tools.inference import recommend


def load_transactions(path):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = set(TRANSACTION_FIELDS) - set(frame.columns)
    if missing:
        raise ValueError(f"CSV thiếu các cột: {', '.join(sorted(missing))}")
    frame = frame[list(TRANSACTION_FIELDS)].copy()
    if frame.empty:
        raise ValueError("CSV chưa có giỏ món hợp lệ. Xuất thêm dữ liệu hoặc chạy chế độ demo.")
    for field in TRANSACTION_FIELDS:
        frame[field] = frame[field].str.strip()
        if frame[field].eq("").any():
            raise ValueError(f"Cột {field} có giá trị trống.")
    if set(frame["schema_version"]) != {str(SCHEMA_VERSION)}:
        raise ValueError("Phiên bản schema CSV chưa được hỗ trợ.")
    sources = set(frame["data_source"])
    if len(sources) != 1 or not sources <= DATA_SOURCES:
        raise ValueError("Chỉ dùng một nguồn application_export hoặc synthetic_demo trong mỗi lần chạy.")
    if not frame["basket_closed_at"].str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError("basket_closed_at phải có múi giờ, ví dụ 2026-01-01T12:00:00+07:00.")
    frame["basket_closed_at"] = pd.to_datetime(frame["basket_closed_at"], format="ISO8601", utc=True)
    quantity = pd.to_numeric(frame["quantity"], errors="raise")
    if not (np.isfinite(quantity) & quantity.gt(0) & quantity.mod(1).eq(0)).all():
        raise ValueError("quantity phải là số nguyên dương hữu hạn.")
    frame["quantity"] = quantity
    if frame.groupby("basket_id")["basket_closed_at"].nunique().gt(1).any():
        raise ValueError("Một basket_id phải có cùng thời điểm đóng giỏ ở mọi dòng.")
    for field in ("dish_code", "dish_name"):
        if frame.groupby("dish_id")[field].nunique().gt(1).any():
            raise ValueError(f"Một dish_id có nhiều giá trị {field}; cần chuẩn hóa lại danh mục.")
    return frame.drop_duplicates().reset_index(drop=True)


def split_baskets(frame, *, test_fraction=0.2):
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction phải nằm giữa 0 và 1.")
    baskets = frame.groupby("basket_id", sort=True).agg(
        closed_at=("basket_closed_at", "first"),
        items=("dish_id", lambda values: tuple(sorted(set(values)))),
    ).reset_index().sort_values(["closed_at", "basket_id"])
    baskets["business_day"] = baskets["closed_at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
    days = sorted(baskets["business_day"].unique())
    if len(days) < 2:
        raise ValueError("Cần ít nhất 2 ngày có giỏ món để tách tập kiểm tra theo thời gian.")
    test_days = min(len(days) - 1, max(1, math.ceil(len(days) * test_fraction)))
    cutoff = days[-test_days]
    train = baskets[baskets["business_day"] < cutoff].copy()
    test = baskets[baskets["business_day"] >= cutoff].copy()
    return train, test, cutoff


def fit_rules(baskets, *, min_support=0.04, min_confidence=0.3, min_lift=1.05, max_len=3, max_rules=500):
    if not (0 < min_support <= 1 and 0 < min_confidence <= 1 and math.isfinite(min_lift) and min_lift > 0):
        raise ValueError("Ngưỡng support/confidence phải thuộc (0, 1], lift phải dương hữu hạn.")
    if max_len < 2 or max_rules < 1:
        raise ValueError("max_len phải từ 2 và max_rules phải dương.")
    transactions = baskets["items"].tolist()
    if not transactions:
        raise ValueError("Tập huấn luyện trống.")
    encoder = TransactionEncoder()
    matrix = encoder.fit(transactions).transform(transactions)
    encoded = pd.DataFrame(matrix, columns=encoder.columns_, dtype=bool)
    frequent = apriori(encoded, min_support=min_support, use_colnames=True, max_len=max_len)
    if frequent.empty or not frequent["itemsets"].map(len).ge(2).any():
        return [], frequent
    discovered = association_rules(frequent, num_itemsets=len(encoded), metric="confidence",
                                   min_threshold=min_confidence, return_metrics=["support", "confidence", "lift"])
    discovered = discovered[discovered["consequents"].map(len).eq(1) & discovered["lift"].ge(min_lift)]
    rules = [{
        "antecedents": sorted(row.antecedents), "consequents": sorted(row.consequents),
        "support": float(row.support), "confidence": float(row.confidence), "lift": float(row.lift),
    } for row in discovered.itertuples()]
    rules.sort(key=lambda rule: (-rule["confidence"], -rule["lift"], -rule["support"], rule["antecedents"], rule["consequents"]))
    return rules[:max_rules], frequent


def evaluate_rules(train, test, rules, *, k=3):
    popularity = Counter(item for items in train["items"] for item in set(items))
    ranked_popular = sorted(popularity, key=lambda item: (-popularity[item], item))
    eligible = hits = baseline_hits = covered = 0
    for basket in test.itertuples():
        if len(basket.items) < 2:
            continue
        hidden_index = int.from_bytes(hashlib.sha256(basket.basket_id.encode()).digest()[:8], "big") % len(basket.items)
        hidden = basket.items[hidden_index]
        observed = set(basket.items) - {hidden}
        predictions = recommend(observed, rules, k=k)
        baseline = [item for item in ranked_popular if item not in observed][:k]
        eligible += 1
        covered += bool(predictions)
        hits += hidden in predictions
        baseline_hits += hidden in baseline
    return {
        "protocol": "chronological_business_days_then_hide_one_item_sha256_basket_id",
        "k": k, "test_baskets": len(test), "eligible_baskets": eligible,
        "single_item_baskets_skipped": len(test) - eligible,
        "hit_rate_at_k": hits / eligible if eligible else None,
        "recommendation_coverage": covered / eligible if eligible else None,
        "popularity_baseline_hit_rate_at_k": baseline_hits / eligible if eligible else None,
        "note": "Giấu một món trong giỏ hoàn tất để kiểm tra; không phải đánh giá thứ tự chọn món thực tế.",
    }


def run_experiment(csv_path, output_dir, *, min_support=0.04, min_confidence=0.3, min_lift=1.05,
                   max_len=3, max_rules=500, test_fraction=0.2, k=3):
    frame = load_transactions(csv_path)
    train, test, cutoff = split_baskets(frame, test_fraction=test_fraction)
    parameters = {"min_support": min_support, "min_confidence": min_confidence,
                  "min_lift": min_lift, "max_len": max_len, "max_rules": max_rules}
    rules, frequent = fit_rules(train, **parameters)
    metrics = evaluate_rules(train, test, rules, k=k)
    source = frame["data_source"].iloc[0]
    catalog = frame[["dish_id", "dish_code", "dish_name"]].drop_duplicates("dish_id").sort_values("dish_id")
    model = {
        "schema_version": SCHEMA_VERSION, "algorithm": "Apriori", "data_source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "versions": {"mlxtend": mlxtend.__version__, "pandas": pd.__version__, "numpy": np.__version__},
        "input_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
        "parameters": {**parameters, "test_fraction": test_fraction, "k": k},
        "training": {"baskets": len(train), "holdout_baskets": len(test),
                     "holdout_start_business_day": cutoff.isoformat(), "rule_count": len(rules),
                     "train_start": train["closed_at"].min().isoformat(), "train_end": train["closed_at"].max().isoformat()},
        "limitations": [
            "Dữ liệu synthetic_demo có các cặp món được tạo chủ ý, chỉ dùng kiểm tra quy trình.",
            "application_export xác nhận nguồn ứng dụng, không xác nhận đây là dữ liệu kinh doanh thực.",
            "Support/confidence/lift đo liên hệ trong tập train, không phải độ chính xác ngoài thực tế.",
            "Chọn ngưỡng trước khi xem holdout; thử nhiều ngưỡng trên holdout làm kết quả mang tính thăm dò.",
            "Khi tích hợp web phải lọc lại món còn bán bằng trạng thái hiện tại của hệ thống.",
        ],
        "catalog": catalog.to_dict("records"), "evaluation": metrics, "rules": rules,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    for name, payload in (("apriori_model.json", model), ("evaluation.json", metrics)):
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    rule_frame = pd.DataFrame(rules, columns=["antecedents", "consequents", "support", "confidence", "lift"])
    for column in ("antecedents", "consequents"):
        rule_frame[column] = rule_frame[column].map(lambda items: json.dumps(items, ensure_ascii=False))
    rule_frame.to_csv(output / "association_rules.csv", index=False, encoding="utf-8-sig")
    frequent = frequent.copy()
    frequent["itemsets"] = frequent["itemsets"].map(lambda items: json.dumps(sorted(items), ensure_ascii=False))
    frequent.to_csv(output / "frequent_itemsets.csv", index=False, encoding="utf-8-sig")
    for name, fold in (("train_baskets.csv", train), ("holdout_baskets.csv", test)):
        fold = fold.copy()
        fold["items"] = fold["items"].map(lambda items: json.dumps(items, ensure_ascii=False))
        fold.to_csv(output / name, index=False, encoding="utf-8-sig")
    return model
