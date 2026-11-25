"""Publication gate: chronological holdout, enough observations, verified provenance and baseline."""
import math


def assess_model_quality(model, *, min_train=100, min_eligible=30):
    training = model.get("training") if isinstance(model.get("training"), dict) else {}
    evaluation = model.get("evaluation") if isinstance(model.get("evaluation"), dict) else {}
    provenance = model.get("data_provenance") if isinstance(model.get("data_provenance"), dict) else {}
    reasons = []
    if model.get("data_source") != "application_export" or provenance.get("kind") != "confirmed_business":
        reasons.append("Chưa xác nhận dữ liệu bán hàng thực; xuất từ ứng dụng chưa đủ chứng minh nguồn kinh doanh thực.")
    train_count = training.get("baskets", 0)
    eligible = evaluation.get("eligible_baskets", 0)
    if type(train_count) is not int or train_count < min_train:
        reasons.append(f"Cần ít nhất {min_train} giỏ huấn luyện.")
    if type(eligible) is not int or eligible < min_eligible:
        reasons.append(f"Cần ít nhất {min_eligible} giỏ kiểm tra đủ điều kiện.")
    protocol = evaluation.get("protocol", "")
    if protocol != "chronological_business_days_then_hide_one_item_sha256_basket_id":
        reasons.append("Chưa có đánh giá holdout theo ngày kinh doanh.")
    hit, baseline = evaluation.get("hit_rate_at_k"), evaluation.get("popularity_baseline_hit_rate_at_k")
    def finite_rate(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
    if not finite_rate(hit) or not finite_rate(baseline):
        reasons.append("Chưa có chỉ số hợp lệ để so sánh baseline.")
    elif hit <= baseline:
        reasons.append("Apriori chưa vượt cách gợi ý món phổ biến trên tập kiểm tra.")
    return {"passed": not reasons, "reasons": reasons, "train_baskets": train_count,
        "eligible_baskets": eligible, "hit_rate_at_k": hit, "baseline_hit_rate_at_k": baseline,
        "min_train": min_train, "min_eligible": min_eligible,
        "serving_strategy": "apriori" if not reasons else "popular_paid_dishes",
        "note": "Đây là điều kiện tối thiểu công bố, không phải khẳng định hiệu quả kinh doanh hoặc ý nghĩa thống kê."}
