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
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import (
    f1_score,
    mean_absolute_error,
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

    summary = {"delay_risk": delay, "downtime": downtime, "demand": demand}
    with open(os.path.join(MODELS_DIR, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print("\nSaved models + metrics to", MODELS_DIR)


if __name__ == "__main__":
    main()
