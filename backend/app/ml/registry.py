"""Model registry + inference. Loads the trained pipelines and applies them to live data
(pending jobs, latest sensor readings, demand history). Returns JSON-serializable dicts."""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache

import joblib
import numpy as np
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


REQUIRED_MODELS = (
    "delay_risk", "downtime", "demand", "duration", "duration_p90",
    "delay_duration", "delay_duration_p90", "downtime_duration",
    "failure_type", "sensor_anomaly", "stockout",
)


def all_models_available() -> bool:
    """True when every trained artifact needed by the app is present."""
    joblibs = all(os.path.exists(os.path.join(MODELS_DIR, f"{n}.joblib")) for n in REQUIRED_MODELS)
    return joblibs and os.path.exists(os.path.join(MODELS_DIR, "demand_quantiles.json"))


def reload() -> None:
    """Drop cached loaded models (call after (re)training)."""
    _load.cache_clear()


def duration_model_available() -> bool:
    return os.path.exists(os.path.join(MODELS_DIR, "duration.joblib"))


def metrics() -> dict:
    path = os.path.join(MODELS_DIR, "metrics.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_optional(name):
    try:
        return _load(name)
    except ModelNotTrainedError:
        return None


def _quantile_meta() -> dict:
    path = os.path.join(MODELS_DIR, "demand_quantiles.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _likely_cause(row) -> str:
    """Heuristic delay cause (the recorded cause is random in the data, so this is a rule)."""
    if float(row.get("downtime_minutes", 0)) >= 25:
        return "Machine downtime"
    if str(row.get("shift_id", "")) == "S3":
        return "Night-shift setup delay"
    if float(row.get("processing_hours", 0)) >= 1.5:
        return "Long changeover / large batch"
    return "Process variance"


# ---------------------------------------------------------------------------
# Duration (cycle-time) + machine downtime probability (feed capacity/bottleneck)
# ---------------------------------------------------------------------------
def predict_duration(jobs) -> list[float]:
    """Predicted actual processing hours for each job-operation row."""
    model, _ = _load("duration")
    return [float(v) for v in model.predict(F.duration_feature_matrix(jobs))]


def predict_duration_p90(jobs) -> list[float]:
    model, _ = _load("duration_p90")
    return [float(v) for v in model.predict(F.duration_feature_matrix(jobs))]


def downtime_prob_by_machine() -> dict:
    """Latest predicted downtime probability (0-1) per machine."""
    res = predict_downtime_latest()
    return {m["machine_id"]: m["downtime_risk_pct"] / 100.0 for m in res.get("machines", [])}


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
    # enrich with predicted delay magnitude (days) + P90 + likely cause
    dur = _load_optional("delay_duration")
    durp90 = _load_optional("delay_duration_p90")
    Xr = F.delay_feature_matrix(at_risk)
    exp_hours = dur[0].predict(Xr) if dur else [None] * len(at_risk)
    p90_hours = durp90[0].predict(Xr) if durp90 else [None] * len(at_risk)

    rows = []
    for i, (_, r) in enumerate(at_risk.iterrows()):
        eh = exp_hours[i]
        ph = p90_hours[i]
        rows.append({
            "job_id": r["job_id"],
            "order_id": r["order_id"],
            "operation_id": r["operation_id"],
            "machine_id": r["machine_id"],
            "predicted_status": r["predicted_status"],
            "delay_risk_pct": round(float(r["delay_risk"]) * 100.0, 1),
            "expected_delay_hours": (round(float(eh), 1) if eh is not None else None),
            "expected_delay_days": (round(float(eh) / 24.0, 2) if eh is not None else None),
            "p90_delay_hours": (round(float(ph), 1) if ph is not None else None),
            "likely_cause": _likely_cause(r),
        })
    summary = pd.Series(pred).value_counts().to_dict()
    return {
        "count": int(len(pend)),
        "predicted_distribution": {k: int(v) for k, v in summary.items()},
        "at_risk": rows,
    }


def predict_order_due_risk(top_n: int = 10) -> dict:
    """Order-level: will the whole order miss its due date, and by how many days."""
    model, _ = _load("delay_risk")
    dur = _load_optional("delay_duration")
    orders = da.orders()
    pend_orders = orders[orders["status"].isin(["Open", "Scheduled"])]
    pending_ids = set(pend_orders["order_id"])
    jobs = da.job_operations()
    pend = jobs[jobs["order_id"].isin(pending_ids)].copy()
    if pend.empty:
        return {"count": 0, "at_risk_orders": []}

    X = F.delay_feature_matrix(pend)
    classes = list(model.named_steps["clf"].classes_)
    bad_idx = [i for i, c in enumerate(classes) if c in DELAY_CLASSES_BAD]
    pend["risk"] = model.predict_proba(X)[:, bad_idx].sum(axis=1)
    pend["exp_delay_h"] = (dur[0].predict(X) if dur else 2.0) * pend["risk"]

    due_by_order = dict(zip(orders["order_id"], orders["due_date"]))
    out = []
    for oid, grp in pend.groupby("order_id"):
        last_end = grp["scheduled_end"].max()
        order_delay_h = float(grp["exp_delay_h"].sum())
        completion = last_end + pd.Timedelta(hours=order_delay_h)
        due = due_by_order.get(oid)
        days_over = (completion - due).total_seconds() / 86400.0 if due is not None else 0.0
        out.append({
            "order_id": oid,
            "predicted_completion": completion.strftime("%d-%m-%Y %H:%M:%S"),
            "due_date": due.strftime("%d-%m-%Y") if due is not None else None,
            "will_miss_due": bool(days_over > 0),
            "days_over": round(days_over, 2),
            "order_risk_pct": round(float(grp["risk"].max()) * 100.0, 1),
        })
    out.sort(key=lambda r: r["days_over"], reverse=True)
    misses = [o for o in out if o["will_miss_due"]]
    return {"count": len(out), "orders_missing_due": len(misses), "at_risk_orders": out[:top_n]}


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

    ftype_model = _load_optional("failure_type")
    anom = _load_optional("sensor_anomaly")
    ftypes = ftype_model[0].predict(X) if ftype_model else [None] * len(latest)
    anomaly_scores = (-anom[0].decision_function(X)) if anom else [None] * len(latest)
    anomaly_flags = (anom[0].predict(X) == -1) if anom else [None] * len(latest)

    rows = []
    for i, (_, r) in enumerate(latest.iterrows()):
        prob = float(r["downtime_prob"])
        alert = prob >= 0.5
        rows.append({
            "machine_id": r["machine_id"],
            "reading_time": r["reading_time"].strftime("%d-%m-%Y %H:%M:%S"),
            "downtime_risk_pct": round(prob * 100.0, 1),
            "health_index": round(100.0 * (1.0 - prob), 1),
            "failure_type": (str(ftypes[i]) if alert and ftypes[i] is not None else "None"),
            "anomaly_score": (round(float(anomaly_scores[i]), 3) if anomaly_scores[i] is not None else None),
            "is_anomaly": (bool(anomaly_flags[i]) if anomaly_flags[i] is not None else None),
            "alert": bool(alert),
        })
    rows.sort(key=lambda r: r["downtime_risk_pct"], reverse=True)
    return {"machines": rows, "machines_at_risk": [r["machine_id"] for r in rows if r["alert"]]}


def predict_downtime_duration(jobs) -> list[float]:
    """Predicted downtime minutes for job-operation rows."""
    model, _ = _load("downtime_duration")
    return [float(v) for v in model.predict(F.duration_feature_matrix(jobs))]


# ---------------------------------------------------------------------------
# Demand forecast (recursive multi-step per SKU)
# ---------------------------------------------------------------------------
def forecast_demand(horizon_days: int = 7, product_ids: list[str] | None = None) -> dict:
    model, meta = _load("demand")
    frame = da.demand().sort_values(["product_id", "demand_date"]).copy()
    all_products = list(frame["product_id"].unique())
    targets = product_ids or all_products

    qmeta = _quantile_meta()
    z = qmeta.get("z", 1.28)
    sigma_by_product = qmeta.get("sigma_by_product", {})
    global_sigma = qmeta.get("global_sigma", 0.0)
    price_by_product = dict(zip(frame["product_id"], frame["unit_price"]))

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

        total = sum(forecasts)
        sigma = float(sigma_by_product.get(pid, global_sigma))
        band = z * sigma * math.sqrt(horizon_days)          # interval on the horizon total
        price = float(price_by_product.get(pid, 0.0))
        results.append({
            "product_id": pid,
            "forecast_units_total": round(total, 1),
            "forecast_daily_avg": round(total / horizon_days, 1),
            "p10_units_total": round(max(0.0, total - band), 1),
            "p90_units_total": round(total + band, 1),
            "forecast_revenue": round(total * price, 1),
        })

    results.sort(key=lambda r: r["forecast_units_total"], reverse=True)
    return {"horizon_days": horizon_days, "products": results}


def demand_stockout_risk(top_n: int = 10) -> dict:
    """Predicted probability of a stockout in the next period, per SKU."""
    model, _ = _load("stockout")
    frame = F.build_stockout_frame()
    latest = frame.sort_values("demand_date").groupby("product_id").tail(1).copy()
    X = latest[F.STOCKOUT_NUMERIC + F.STOCKOUT_CATEGORICAL]
    latest["stockout_prob"] = model.predict_proba(X)[:, 1]
    rows = [
        {
            "product_id": r["product_id"],
            "current_inventory": int(r["inventory_level"]),
            "stockout_next_prob_pct": round(float(r["stockout_prob"]) * 100.0, 1),
            "alert": bool(r["stockout_prob"] >= 0.5),
        }
        for _, r in latest.sort_values("stockout_prob", ascending=False).head(top_n).iterrows()
    ]
    return {"products": rows, "at_risk": [r["product_id"] for r in rows if r["alert"]]}


def demand_region_split() -> dict:
    """Historical demand share by region (the 'where' of demand)."""
    d = da.demand()
    share = d.groupby("region")["units_sold"].sum()
    total = float(share.sum()) or 1.0
    return {"region_share_pct": {k: round(float(v) / total * 100.0, 1) for k, v in share.items()}}
