"""Feature engineering for the three ML models. Each builder returns tidy inputs and is
careful to avoid target leakage (no post-execution columns feed the delay model, and the
demand model uses only past information via lag features)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import data_access as da

# ---------------------------------------------------------------------------
# 1) Delay-risk classifier  (target: job_status  On-Time / Delayed / Failed)
# ---------------------------------------------------------------------------
DELAY_NUMERIC = [
    "processing_hours", "downtime_minutes", "batch_quantity", "sequence",
    "reliability_index", "experience_years", "hourly_cost_inr", "priority",
]
DELAY_CATEGORICAL = ["machine_id", "operation_id", "shift_id"]
DELAY_TARGET = "job_status"


def build_delay_features() -> tuple[pd.DataFrame, pd.Series]:
    jobs = da.job_operations()
    X = delay_feature_matrix(jobs)
    y = jobs[DELAY_TARGET].copy()
    return X, y


def delay_feature_matrix(jobs: pd.DataFrame) -> pd.DataFrame:
    """Build the delay-model feature columns for any subset of job-operations
    (used for both training and live inference). No post-execution columns are used."""
    machines = da.machines()[["machine_id", "reliability_index"]]
    workers = da.workers()[["worker_id", "experience_years", "hourly_cost_inr"]]
    orders = da.orders()[["order_id", "priority"]]
    df = (
        jobs.merge(machines, on="machine_id", how="left")
        .merge(workers, on="worker_id", how="left")
        .merge(orders, on="order_id", how="left")
    )
    return df[DELAY_NUMERIC + DELAY_CATEGORICAL].copy()


# ---------------------------------------------------------------------------
# 2) Machine-downtime classifier  (target: downtime_flag)
# ---------------------------------------------------------------------------
SENSOR_NUMERIC = [
    "hydraulic_pressure_bar", "coolant_pressure_bar", "air_system_pressure_bar",
    "coolant_temp_c", "hydraulic_oil_temp_c", "spindle_bearing_temp_c",
    "spindle_vibration_um", "tool_vibration_um", "spindle_speed_rpm",
    "voltage_v", "torque_nm", "cutting_force_kn",
]
SENSOR_CATEGORICAL = ["machine_id"]
DOWNTIME_TARGET = "downtime_flag"


def build_downtime_features() -> tuple[pd.DataFrame, pd.Series]:
    sensor = da.machine_sensor()
    X = sensor[SENSOR_NUMERIC + SENSOR_CATEGORICAL].copy()
    y = sensor[DOWNTIME_TARGET].astype(int).copy()
    return X, y


# ---------------------------------------------------------------------------
# 3) Demand forecaster  (target: units_sold, next-day per SKU)
# ---------------------------------------------------------------------------
DEMAND_NUMERIC = ["day_index", "day_of_week", "month", "promotion_flag",
                  "lag_1", "lag_7", "roll7_mean"]
DEMAND_CATEGORICAL = ["product_id"]
DEMAND_TARGET = "units_sold"


def build_demand_frame() -> pd.DataFrame:
    """Per-SKU time series with lag/rolling features. Rows with incomplete lags are dropped."""
    d = da.demand().sort_values(["product_id", "demand_date"]).copy()
    d["day_of_week"] = d["demand_date"].dt.dayofweek
    d["month"] = d["demand_date"].dt.month
    d["day_index"] = d.groupby("product_id").cumcount()

    g = d.groupby("product_id")["units_sold"]
    d["lag_1"] = g.shift(1)
    d["lag_7"] = g.shift(7)
    d["roll7_mean"] = g.shift(1).rolling(7).mean().reset_index(level=0, drop=True)

    d = d.dropna(subset=["lag_1", "lag_7", "roll7_mean"]).reset_index(drop=True)
    return d


def time_split(frame: pd.DataFrame, test_frac: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by date so the test set is strictly in the future (no leakage)."""
    cutoff = frame["demand_date"].quantile(1 - test_frac)
    train = frame[frame["demand_date"] < cutoff]
    test = frame[frame["demand_date"] >= cutoff]
    return train, test


# ---------------------------------------------------------------------------
# 4) Duration / cycle-time regressor  (target: processing_hours)
#    Predicts how long an operation will REALLY take, so capacity/bottleneck use
#    expected actual durations instead of nominal standard times.
# ---------------------------------------------------------------------------
DURATION_NUMERIC = ["batch_quantity", "sequence", "experience_years", "hourly_cost_inr"]
DURATION_CATEGORICAL = ["machine_id", "operation_id", "product_id", "shift_id"]
DURATION_TARGET = "processing_hours"


def duration_feature_matrix(jobs: pd.DataFrame) -> pd.DataFrame:
    """Feature columns for the duration model (training and live inference)."""
    workers = da.workers()[["worker_id", "experience_years", "hourly_cost_inr"]]
    df = jobs.merge(workers, on="worker_id", how="left")
    return df[DURATION_NUMERIC + DURATION_CATEGORICAL].copy()


def build_duration_features() -> tuple[pd.DataFrame, pd.Series]:
    jobs = da.job_operations()
    X = duration_feature_matrix(jobs)
    y = jobs[DURATION_TARGET].copy()
    return X, y


# ---------------------------------------------------------------------------
# 5) Delay DURATION (how late, hours) + delay CAUSE  (late operations only)
# ---------------------------------------------------------------------------
def _late_jobs() -> pd.DataFrame:
    jobs = da.job_operations()
    late = jobs[jobs["job_status"] != "On-Time"].copy()
    late["delay_hours"] = (
        (late["actual_end"] - late["scheduled_end"]).dt.total_seconds() / 3600.0
    ).clip(lower=0)
    return late


def build_delay_duration_features() -> tuple[pd.DataFrame, pd.Series]:
    late = _late_jobs()
    return delay_feature_matrix(late), late["delay_hours"]


# ---------------------------------------------------------------------------
# 6) Downtime DURATION (minutes) + FAILURE TYPE
# ---------------------------------------------------------------------------
def build_downtime_duration_features() -> tuple[pd.DataFrame, pd.Series]:
    jobs = da.job_operations()
    d = jobs[jobs["downtime_minutes"] > 0].copy()
    # use the duration feature set (job/machine context) - NOT the delay set, which
    # contains downtime_minutes itself and would leak the target.
    return duration_feature_matrix(d), d["downtime_minutes"]


FAILURE_TYPE_TARGET = "failure_type"


def build_failure_type_features() -> tuple[pd.DataFrame, pd.Series]:
    sensor = da.machine_sensor()
    faults = sensor[sensor["downtime_flag"] == 1].copy()
    X = faults[SENSOR_NUMERIC + SENSOR_CATEGORICAL]
    return X, faults[FAILURE_TYPE_TARGET]


# ---------------------------------------------------------------------------
# 7) Demand STOCKOUT (classification) - reuses the demand frame + inventory state
# ---------------------------------------------------------------------------
STOCKOUT_NUMERIC = ["day_of_week", "month", "promotion_flag", "lag_1", "lag_7",
                    "roll7_mean", "inventory_level", "reorder_point"]
STOCKOUT_CATEGORICAL = ["product_id"]
STOCKOUT_TARGET = "stockout_next"


def build_stockout_frame() -> pd.DataFrame:
    """Predict NEXT day's stockout from today's inventory state (a real forecast, not the
    same-day circular label)."""
    d = build_demand_frame()
    d["inventory_level"] = d["inventory_level"].astype(float)
    d["reorder_point"] = d["reorder_point"].astype(float)
    d[STOCKOUT_TARGET] = d.groupby("product_id")["stockout_flag"].shift(-1)
    d = d.dropna(subset=[STOCKOUT_TARGET]).reset_index(drop=True)
    d[STOCKOUT_TARGET] = d[STOCKOUT_TARGET].astype(int)
    return d

