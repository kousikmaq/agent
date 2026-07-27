"""Train, evaluate and persist the three models.

For each task we train two candidate model families and keep the better one on a held-out
test set (delay -> macro-F1, downtime -> F1, demand -> MAE). Pipelines bundle preprocessing
so inference only needs a raw feature DataFrame.

Run:  python -m app.ml.train      (from the backend/ directory)
"""
from __future__ import annotations

import json
import os

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    IsolationForest,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import (
    f1_score,
    mean_absolute_error,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.config import MODELS_DIR
from app.ml import features as F

SEED = 42


def _preprocessor(categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical)],
        remainder="passthrough",
    )


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true > 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100.0)


def _save(pipeline: Pipeline, name: str, meta: dict) -> None:
    joblib.dump(pipeline, os.path.join(MODELS_DIR, f"{name}.joblib"))
    with open(os.path.join(MODELS_DIR, f"{name}_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)


# ---------------------------------------------------------------------------
def train_delay() -> dict:
    X, y = F.build_delay_features()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED, stratify=y)
    pre = _preprocessor(F.DELAY_CATEGORICAL)

    candidates = {
        "random_forest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=SEED, n_jobs=-1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(random_state=SEED),
    }
    best_name, best_pipe, best_f1 = None, None, -1.0
    for cname, clf in candidates.items():
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        pipe.fit(X_tr, y_tr)
        f1 = f1_score(y_te, pipe.predict(X_te), average="macro")
        if f1 > best_f1:
            best_name, best_pipe, best_f1 = cname, pipe, f1

    y_pred = best_pipe.predict(X_te)
    proba = best_pipe.predict_proba(X_te)
    classes = list(best_pipe.named_steps["clf"].classes_)
    auc = float(roc_auc_score(y_te, proba, multi_class="ovr", average="macro"))
    metrics = {
        "model": best_name,
        "macro_f1": round(best_f1, 4),
        "macro_roc_auc": round(auc, 4),
        "test_size": int(len(y_te)),
        "class_distribution": {k: int(v) for k, v in y.value_counts().items()},
    }
    _save(best_pipe, "delay_risk", {
        "task": "classification",
        "target": F.DELAY_TARGET,
        "numeric": F.DELAY_NUMERIC,
        "categorical": F.DELAY_CATEGORICAL,
        "classes": classes,
        "metrics": metrics,
    })
    return metrics


def train_downtime() -> dict:
    X, y = F.build_downtime_features()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED, stratify=y)
    pre = _preprocessor(F.SENSOR_CATEGORICAL)

    candidates = {
        "random_forest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=SEED, n_jobs=-1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(random_state=SEED),
    }
    best_name, best_pipe, best_f1 = None, None, -1.0
    for cname, clf in candidates.items():
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        pipe.fit(X_tr, y_tr)
        f1 = f1_score(y_te, pipe.predict(X_te))
        if f1 > best_f1:
            best_name, best_pipe, best_f1 = cname, pipe, f1

    y_pred = best_pipe.predict(X_te)
    proba = best_pipe.predict_proba(X_te)[:, 1]
    metrics = {
        "model": best_name,
        "f1": round(best_f1, 4),
        "recall": round(float(recall_score(y_te, y_pred)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 4),
        "test_size": int(len(y_te)),
        "positive_rate": round(float(y.mean()), 4),
    }
    _save(best_pipe, "downtime", {
        "task": "classification",
        "target": F.DOWNTIME_TARGET,
        "numeric": F.SENSOR_NUMERIC,
        "categorical": F.SENSOR_CATEGORICAL,
        "classes": [0, 1],
        "metrics": metrics,
    })
    return metrics


def train_demand() -> dict:
    frame = F.build_demand_frame()
    train, test = F.time_split(frame, test_frac=0.2)
    cols = F.DEMAND_NUMERIC + F.DEMAND_CATEGORICAL
    X_tr, y_tr = train[cols], train[F.DEMAND_TARGET].to_numpy()
    X_te, y_te = test[cols], test[F.DEMAND_TARGET].to_numpy()
    pre = _preprocessor(F.DEMAND_CATEGORICAL)

    candidates = {
        "random_forest": RandomForestRegressor(n_estimators=300, random_state=SEED, n_jobs=-1),
        "hist_gradient_boosting": HistGradientBoostingRegressor(random_state=SEED),
    }
    best_name, best_pipe, best_mae = None, None, float("inf")
    for cname, reg in candidates.items():
        pipe = Pipeline([("pre", pre), ("reg", reg)])
        pipe.fit(X_tr, y_tr)
        mae = mean_absolute_error(y_te, pipe.predict(X_te))
        if mae < best_mae:
            best_name, best_pipe, best_mae = cname, pipe, mae

    pred = best_pipe.predict(X_te)
    # seasonal-naive baseline = last week's value (lag_7)
    baseline = test["lag_7"].to_numpy()
    metrics = {
        "model": best_name,
        "mae": round(float(best_mae), 3),
        "mape_pct": round(_mape(y_te, pred), 2),
        "baseline_mae": round(float(mean_absolute_error(y_te, baseline)), 3),
        "baseline_mape_pct": round(_mape(y_te, baseline), 2),
        "test_size": int(len(y_te)),
    }
    _save(best_pipe, "demand", {
        "task": "regression",
        "target": F.DEMAND_TARGET,
        "numeric": F.DEMAND_NUMERIC,
        "categorical": F.DEMAND_CATEGORICAL,
        "metrics": metrics,
    })
    return metrics


def train_duration() -> dict:
    X, y = F.build_duration_features()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED)
    pre = _preprocessor(F.DURATION_CATEGORICAL)

    candidates = {
        "random_forest": RandomForestRegressor(n_estimators=300, random_state=SEED, n_jobs=-1),
        "hist_gradient_boosting": HistGradientBoostingRegressor(random_state=SEED),
    }
    best_name, best_pipe, best_mae = None, None, float("inf")
    for cname, reg in candidates.items():
        pipe = Pipeline([("pre", pre), ("reg", reg)])
        pipe.fit(X_tr, y_tr)
        mae = mean_absolute_error(y_te, pipe.predict(X_te))
        if mae < best_mae:
            best_name, best_pipe, best_mae = cname, pipe, mae

    pred = best_pipe.predict(X_te)
    metrics = {
        "model": best_name,
        "mae_hours": round(float(best_mae), 3),
        "mape_pct": round(_mape(y_te.to_numpy(), pred), 2),
        "r2": round(float(r2_score(y_te, pred)), 3),
        "test_size": int(len(y_te)),
    }
    _save(best_pipe, "duration", {
        "task": "regression",
        "target": F.DURATION_TARGET,
        "numeric": F.DURATION_NUMERIC,
        "categorical": F.DURATION_CATEGORICAL,
        "metrics": metrics,
    })

    # P90 quantile model (worst-case duration)
    q_pipe = Pipeline([
        ("pre", _preprocessor(F.DURATION_CATEGORICAL)),
        ("reg", GradientBoostingRegressor(loss="quantile", alpha=0.9, random_state=SEED)),
    ])
    q_pipe.fit(X_tr, y_tr)
    _save(q_pipe, "duration_p90", {
        "task": "quantile_regression", "quantile": 0.9,
        "target": F.DURATION_TARGET,
        "numeric": F.DURATION_NUMERIC, "categorical": F.DURATION_CATEGORICAL,
    })
    return metrics


def train_delay_duration() -> dict:
    X, y = F.build_delay_duration_features()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED)
    pre = _preprocessor(F.DELAY_CATEGORICAL)
    pipe = Pipeline([("pre", pre), ("reg", HistGradientBoostingRegressor(random_state=SEED))])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    metrics = {
        "model": "hist_gradient_boosting",
        "mae_hours": round(float(mean_absolute_error(y_te, pred)), 3),
        "mape_pct": round(_mape(y_te.to_numpy(), pred), 2),
        "test_size": int(len(y_te)),
    }
    _save(pipe, "delay_duration", {
        "task": "regression", "target": "delay_hours",
        "numeric": F.DELAY_NUMERIC, "categorical": F.DELAY_CATEGORICAL, "metrics": metrics,
    })
    q = Pipeline([("pre", _preprocessor(F.DELAY_CATEGORICAL)),
                  ("reg", GradientBoostingRegressor(loss="quantile", alpha=0.9, random_state=SEED))])
    q.fit(X_tr, y_tr)
    _save(q, "delay_duration_p90", {"task": "quantile_regression", "quantile": 0.9,
                                    "numeric": F.DELAY_NUMERIC, "categorical": F.DELAY_CATEGORICAL})
    return metrics


def train_downtime_duration() -> dict:
    X, y = F.build_downtime_duration_features()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED)
    pre = _preprocessor(F.DURATION_CATEGORICAL)
    pipe = Pipeline([("pre", pre), ("reg", RandomForestRegressor(
        n_estimators=300, random_state=SEED, n_jobs=-1))])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    metrics = {
        "model": "random_forest",
        "mae_minutes": round(float(mean_absolute_error(y_te, pred)), 2),
        "r2": round(float(r2_score(y_te, pred)), 3),
        "test_size": int(len(y_te)),
    }
    _save(pipe, "downtime_duration", {
        "task": "regression", "target": "downtime_minutes",
        "numeric": F.DURATION_NUMERIC, "categorical": F.DURATION_CATEGORICAL, "metrics": metrics,
    })
    return metrics


def train_failure_type() -> dict:
    X, y = F.build_failure_type_features()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=SEED, stratify=y)
    pre = _preprocessor(F.SENSOR_CATEGORICAL)
    pipe = Pipeline([("pre", pre), ("clf", RandomForestClassifier(
        n_estimators=300, class_weight="balanced", random_state=SEED, n_jobs=-1))])
    pipe.fit(X_tr, y_tr)
    f1 = f1_score(y_te, pipe.predict(X_te), average="macro")
    metrics = {"model": "random_forest", "macro_f1": round(float(f1), 4), "test_size": int(len(y_te))}
    _save(pipe, "failure_type", {
        "task": "classification", "target": F.FAILURE_TYPE_TARGET,
        "numeric": F.SENSOR_NUMERIC, "categorical": F.SENSOR_CATEGORICAL,
        "classes": list(pipe.named_steps["clf"].classes_), "metrics": metrics,
    })
    return metrics


def train_anomaly() -> dict:
    X, _ = F.build_downtime_features()
    pre = _preprocessor(F.SENSOR_CATEGORICAL)
    pipe = Pipeline([("pre", pre), ("iso", IsolationForest(contamination=0.25, random_state=SEED))])
    pipe.fit(X)
    _save(pipe, "sensor_anomaly", {
        "task": "anomaly_detection",
        "numeric": F.SENSOR_NUMERIC, "categorical": F.SENSOR_CATEGORICAL,
        "metrics": {"model": "isolation_forest", "contamination": 0.25},
    })
    return {"model": "isolation_forest", "contamination": 0.25}


def train_demand_quantiles() -> dict:
    """P10/P90 band = point forecast +/- 1.28 * per-SKU daily volatility (normal approx of an
    80% interval). Robust on short, trending series where quantile/conformal calibration fails."""
    point = joblib.load(os.path.join(MODELS_DIR, "demand.joblib"))
    frame = F.build_demand_frame()
    train, test = F.time_split(frame, test_frac=0.2)
    cols = F.DEMAND_NUMERIC + F.DEMAND_CATEGORICAL
    z = 1.28

    sigma_by_product = train.groupby("product_id")["units_sold"].std().fillna(0.0).to_dict()
    global_sigma = float(train["units_sold"].std())

    yhat = point.predict(test[cols])
    y_te = test[F.DEMAND_TARGET].to_numpy()
    s = test["product_id"].map(sigma_by_product).fillna(global_sigma).to_numpy()
    lo = np.clip(yhat - z * s, 0, None)
    hi = yhat + z * s
    coverage = float(((y_te >= lo) & (y_te <= hi)).mean())

    meta = {
        "method": "normal_sigma_band", "z": z,
        "sigma_by_product": {k: round(float(v), 3) for k, v in sigma_by_product.items()},
        "global_sigma": round(global_sigma, 3),
        "p10_p90_coverage": round(coverage, 3), "target_coverage": 0.8, "test_size": int(len(y_te)),
    }
    with open(os.path.join(MODELS_DIR, "demand_quantiles.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return {k: meta[k] for k in ("method", "z", "p10_p90_coverage", "target_coverage", "test_size")}


def train_stockout() -> dict:
    frame = F.build_stockout_frame()
    train, test = F.time_split(frame, test_frac=0.2)
    cols = F.STOCKOUT_NUMERIC + F.STOCKOUT_CATEGORICAL
    X_tr, y_tr = train[cols], train[F.STOCKOUT_TARGET].astype(int)
    X_te, y_te = test[cols], test[F.STOCKOUT_TARGET].astype(int)
    pre = _preprocessor(F.STOCKOUT_CATEGORICAL)
    pipe = Pipeline([("pre", pre), ("clf", RandomForestClassifier(
        n_estimators=300, class_weight="balanced", random_state=SEED, n_jobs=-1))])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    metrics = {
        "model": "random_forest",
        "f1": round(float(f1_score(y_te, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, pred, zero_division=0)), 4),
        "positive_rate": round(float(y_tr.mean()), 4),
        "test_size": int(len(y_te)),
    }
    _save(pipe, "stockout", {
        "task": "classification", "target": F.STOCKOUT_TARGET,
        "numeric": F.STOCKOUT_NUMERIC, "categorical": F.STOCKOUT_CATEGORICAL,
        "classes": [0, 1], "metrics": metrics,
    })
    return metrics


def main() -> None:
    print("Training delay-risk classifier...")
    delay = train_delay()
    print("  ", delay)
    print("Training machine-downtime classifier...")
    downtime = train_downtime()
    print("  ", downtime)
    print("Training demand forecaster...")
    demand = train_demand()
    print("  ", demand)
    print("Training duration (cycle-time) regressor...")
    duration = train_duration()
    print("  ", duration)
    print("Training delay-duration (days-late) regressor...")
    delay_dur = train_delay_duration()
    print("  ", delay_dur)
    print("Training downtime-duration regressor...")
    down_dur = train_downtime_duration()
    print("  ", down_dur)
    print("Training failure-type classifier...")
    ftype = train_failure_type()
    print("  ", ftype)
    print("Training sensor anomaly detector...")
    anomaly = train_anomaly()
    print("  ", anomaly)
    print("Training demand quantiles (P10/P90)...")
    dq = train_demand_quantiles()
    print("  ", dq)
    print("Training stockout classifier...")
    stockout = train_stockout()
    print("  ", stockout)

    summary = {
        "delay_risk": delay, "downtime": downtime, "demand": demand, "duration": duration,
        "delay_duration": delay_dur, "downtime_duration": down_dur, "failure_type": ftype,
        "anomaly": anomaly, "demand_quantiles": dq, "stockout": stockout,
    }
    with open(os.path.join(MODELS_DIR, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print("\nSaved models + metrics to", MODELS_DIR)


if __name__ == "__main__":
    main()
