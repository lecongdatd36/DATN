import json
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ai_tools.forecast_store import training_rows, sha256

SEED = 42
HORIZON = 7
TEST_DAYS = 28

FEATURES = [
    "thu", "cuoi_tuan", "chi_so_ngay",
    "don_hom_qua", "don_7_ngay_truoc",
    "don_14_ngay_truoc", "don_28_ngay_truoc",
    "trung_binh_7_ngay", "trung_binh_28_ngay",
]

def feature_row(day, history, first_day):
    if len(history) < 28:
        raise ValueError("Can 28 ngay lich su.")
    return [
        day.weekday(),
        int(day.weekday() >= 5),
        (day - first_day).days,
        history[-1],
        history[-7],
        history[-14],
        history[-28],
        float(np.mean(history[-7:])),
        float(np.mean(history[-28:])),
    ]


def fit_model(values, known_dates, first_day):
    # Moi dong chi dung lich su truoc ngay can du bao.
    X = [
        feature_row(known_dates[i], values[:i], first_day)
        for i in range(28, len(values))
    ]
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=3,
        random_state=SEED,
        n_jobs=-1,
    )
    model.fit(pd.DataFrame(X, columns=FEATURES), values[28:])
    return model


def forecast(model, values, next_day, first_day, days=7):
    history = list(map(float, values))
    predictions = []
    for step in range(days):
        day = next_day + timedelta(days=step)
        X = pd.DataFrame(
            [feature_row(day, history, first_day)],
            columns=FEATURES,
        )
        pred = max(0.0, float(model.predict(X)[0]))
        predictions.append(pred)
        # Ngay tuong lai chua co thuc te: dung du bao vua tao.
        history.append(pred)
    return predictions


def baseline_forecast(values, days=7):
    history = list(map(float, values))
    predictions = []
    for _ in range(days):
        pred = history[-7]
        predictions.append(pred)
        history.append(pred)
    return predictions


def train(input_path, output, source, reference_date, run_id):
    rows = training_rows(input_path, source, reference_date)
    dates = [date.fromisoformat(row["ngay"]) for row in rows]
    y = np.array([int(row["so_don"]) for row in rows], dtype=float)
    first_day = dates[0]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Updater created this unique run directory and immutable input snapshot.
    if any((output / name).exists() for name in ("evaluation.json", "forecast_demo.joblib", "du_bao_7_ngay.csv", "kiem_tra_du_bao.csv")):
        raise FileExistsError("Refuse to overwrite an existing training result")
    print("1. DU LIEU:", len(y), "ngay")
    print("2. DANH GIA 4 LUOT, MOI LUOT 7 NGAY")

    evaluation_rows = []
    test_start = len(y) - TEST_DAYS

    for origin in range(test_start, len(y), HORIZON):
        # Moi luot chi duoc hoc tu cac ngay da xay ra.
        train_y = y[:origin]
        model = fit_model(train_y, dates[:origin], first_day)
        model_preds = forecast(model, train_y, dates[origin], first_day, HORIZON)
        base_preds = baseline_forecast(train_y, HORIZON)

        for h in range(HORIZON):
            evaluation_rows.append({
                "run_id": run_id, "nguon_du_lieu": source,
                "ngay_bat_dau_du_bao": dates[origin].isoformat(),
                "ngay": dates[origin + h].isoformat(),
                "buoc_du_bao": h + 1,
                "thuc_te": int(y[origin + h]),
                "du_bao_ai": model_preds[h],
                "du_bao_tuan_truoc": base_preds[h],
            })

    evaluation = pd.DataFrame(evaluation_rows)
    actual = evaluation["thuc_te"]

    ai_mae = mean_absolute_error(actual, evaluation["du_bao_ai"])
    base_mae = mean_absolute_error(actual, evaluation["du_bao_tuan_truoc"])
    ai_rmse = float(np.sqrt(
        mean_squared_error(actual, evaluation["du_bao_ai"])
    ))

    print("MAE AI:", round(ai_mae, 3), "don/ngay")
    print("MAE TUAN TRUOC:", round(base_mae, 3), "don/ngay")
    print("RMSE AI:", round(ai_rmse, 3), "don/ngay")

    if ai_mae < base_mae:
        print("KET QUA: AI co MAE thap hon baseline tren lan thu nay.")
    elif ai_mae > base_mae:
        print("KET QUA: AI chua tot hon baseline tren lan thu nay.")
    else:
        print("KET QUA: AI va baseline co MAE bang nhau.")

    print("3. HOC LAI TOAN BO DU LIEU SAU DANH GIA")
    final_model = fit_model(y, dates, first_day)
    next_day = dates[-1] + timedelta(days=1)
    future = forecast(final_model, y, next_day, first_day, HORIZON)

    forecast_rows = [
        {
            "ngay": (next_day + timedelta(days=i)).isoformat(),
            "so_don_du_kien": int(round(pred)),
            "nguon_du_lieu": source, "run_id": run_id,
        }
        for i, pred in enumerate(future)
    ]

    evaluation.to_csv(
        output / "kiem_tra_du_bao.csv",
        index=False, encoding="utf-8-sig",
    )
    pd.DataFrame(forecast_rows).to_csv(
        output / "du_bao_7_ngay.csv",
        index=False, encoding="utf-8-sig",
    )

    report = {
        "schema_version": 2,
        "run_id": run_id,
        "data_source": source,
        "timezone": "Asia/Ho_Chi_Minh",
        "reference_date": reference_date.isoformat(),
        "training_days": len(y),
        "input_sha256": sha256(Path(input_path).read_bytes()),
        "target": "so_don_theo_ngay",
        "seed": SEED,
        "horizon_days": HORIZON,
        "evaluation_days": TEST_DAYS,
        "evaluation_method": "4 rolling origins, retrain before each 7-day forecast",
        "mae_ai": float(ai_mae),
        "mae_baseline": float(base_mae),
        "rmse_ai": ai_rmse,
        "metrics_use_unrounded_predictions": True,
        "final_model_refitted_on_all_days": True,
        "training_last_date": dates[-1].isoformat(),
        "sklearn_version": sklearn.__version__,
        "limitation": ("Du lieu mo phong; chua chung minh hieu qua thuc te." if source == "mo_phong" else "Can danh gia them tren du lieu ban hang thuc te."),
    }

    joblib.dump(
        {
            "schema_version": 1,
            "model": final_model,
            "features": FEATURES,
            "first_day": first_day.isoformat(),
            "last_day": dates[-1].isoformat(),
            "last_28_orders": y[-28:].tolist(),
            "metadata": report,
        },
        output / "forecast_demo.joblib",
    )
    # Bind the opaque model artifact to the JSON metadata without importing
    # joblib/sklearn in either the publisher or the web process.
    report["model_sha256"] = sha256((output / "forecast_demo.joblib").read_bytes())
    (output / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print("4. DU BAO 7 NGAY TIEP THEO:")
    for row in forecast_rows:
        print(row["ngay"], ":", row["so_don_du_kien"], "don")

    print("DA LUU KET QUA:", output.resolve())
    print("NGUON:", source)
