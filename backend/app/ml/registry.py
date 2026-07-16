"""Model registry + inference. Loads the trained pipelines and applies them to live data
(pending jobs, latest sensor readings, demand history). Returns JSON-serializable dicts."""
from __future__ import annotations

import json
import os
from functools import lru_cache

import joblib
import pandas as pd

from app import data_access as da
from app.config import MODELS_DIR
from app.ml import features as F

DELAY_CLASSES_BAD = {"Delayed", "Failed"}


class ModelNotTrainedError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _load(name: str):
    path = os.path.join(MODELS_DIR, f"{name}.joblib")
    meta_path = os.path.join(MODELS_DIR, f"{name}_meta.json")
    if not os.path.exists(path):
        raise ModelNotTrainedError(
            f"Model '{name}' not found. Run:  python -m app.ml.train  (from backend/)"
        )
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    return joblib.load(path), meta


def models_available() -> bool:
    return all(os.path.exists(os.path.join(MODELS_DIR, f"{n}.joblib"))
               for n in ("delay_risk", "downtime", "demand"))


def metrics() -> dict:
    path = os.path.join(MODELS_DIR, "metrics.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Delay risk
# ---------------------------------------------------------------------------
def predict_delay_for_pending(top_n: int = 10) -> dict:
    model, meta = _load("delay_risk")
    orders = da.orders()
    pending_ids = set(orders[orders["status"].isin(["Open", "Scheduled"])]["order_id"])
    jobs = da.job_operations()
    pend = jobs[jobs["order_id"].isin(pending_ids)].copy()
    if pend.empty:
        return {"count": 0, "at_risk": []}

    X = F.delay_feature_matrix(pend)
    classes = list(model.named_steps["clf"].classes_)
    proba = model.predict_proba(X)
    pred = model.predict(X)
    bad_idx = [i for i, c in enumerate(classes) if c in DELAY_CLASSES_BAD]
    pend["predicted_status"] = pred
    pend["delay_risk"] = proba[:, bad_idx].sum(axis=1)

    at_risk = pend.sort_values("delay_risk", ascending=False).head(top_n)
    rows = [
        {
            "job_id": r["job_id"],
            "order_id": r["order_id"],
            "operation_id": r["operation_id"],
            "machine_id": r["machine_id"],
            "predicted_status": r["predicted_status"],
            "delay_risk_pct": round(float(r["delay_risk"]) * 100.0, 1),
        }
        for _, r in at_risk.iterrows()
    ]
    summary = pd.Series(pred).value_counts().to_dict()
    return {
        "count": int(len(pend)),
        "predicted_distribution": {k: int(v) for k, v in summary.items()},
        "at_risk": rows,
    }


# ---------------------------------------------------------------------------
# Machine downtime
# ---------------------------------------------------------------------------
def predict_downtime_latest() -> dict:
    model, meta = _load("downtime")
    sensor = da.machine_sensor()
    latest = sensor.sort_values("reading_time").groupby("machine_id").tail(1).copy()
    X = latest[F.SENSOR_NUMERIC + F.SENSOR_CATEGORICAL]
    proba = model.predict_proba(X)[:, 1]
    latest["downtime_prob"] = proba

    rows = [
        {
            "machine_id": r["machine_id"],
            "reading_time": r["reading_time"].strftime("%d-%m-%Y %H:%M:%S"),
            "downtime_risk_pct": round(float(r["downtime_prob"]) * 100.0, 1),
            "alert": bool(r["downtime_prob"] >= 0.5),
        }
        for _, r in latest.sort_values("downtime_prob", ascending=False).iterrows()
    ]
    return {"machines": rows, "machines_at_risk": [r["machine_id"] for r in rows if r["alert"]]}


# ---------------------------------------------------------------------------
# Demand forecast (recursive multi-step per SKU)
# ---------------------------------------------------------------------------
def forecast_demand(horizon_days: int = 7, product_ids: list[str] | None = None) -> dict:
    model, meta = _load("demand")
    frame = da.demand().sort_values(["product_id", "demand_date"]).copy()
    all_products = list(frame["product_id"].unique())
    targets = product_ids or all_products

    results = []
    for pid in targets:
        hist = frame[frame["product_id"] == pid].copy()
        if len(hist) < 8:
            continue
        series = hist["units_sold"].tolist()
        last_date = hist["demand_date"].max()
        forecasts = []
        for step in range(1, horizon_days + 1):
            fdate = last_date + pd.Timedelta(days=step)
            lag_1 = series[-1]
            lag_7 = series[-7]
            roll7 = float(pd.Series(series[-7:]).mean())
            row = pd.DataFrame([{
                "day_index": len(series),
                "day_of_week": fdate.dayofweek,
                "month": fdate.month,
                "promotion_flag": 0,
                "lag_1": lag_1,
                "lag_7": lag_7,
                "roll7_mean": roll7,
                "product_id": pid,
            }])
            yhat = float(model.predict(row[F.DEMAND_NUMERIC + F.DEMAND_CATEGORICAL])[0])
            yhat = max(0.0, yhat)
            forecasts.append(yhat)
            series.append(yhat)

        results.append({
            "product_id": pid,
            "forecast_units_total": round(sum(forecasts), 1),
            "forecast_daily_avg": round(sum(forecasts) / horizon_days, 1),
        })

    results.sort(key=lambda r: r["forecast_units_total"], reverse=True)
    return {"horizon_days": horizon_days, "products": results}
