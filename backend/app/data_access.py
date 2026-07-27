"""Load the star-schema CSVs into cached pandas DataFrames.

Single source of truth for all analytics / ML / optimization modules. Dates are parsed
once here so downstream code never re-parses. Everything is read-only.
"""
from __future__ import annotations

import os
from functools import lru_cache

import pandas as pd

from app.config import DATA_DIR

DATE_FMT = "%d-%m-%Y"
TS_FMT = "%d-%m-%Y %H:%M:%S"


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, f"{name}.csv")


@lru_cache(maxsize=None)
def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(_path(name))


# ---- dimensions ------------------------------------------------------------
def products() -> pd.DataFrame:
    return _read("dim_product").copy()


def machines() -> pd.DataFrame:
    return _read("dim_machine").copy()


def operations() -> pd.DataFrame:
    return _read("dim_operation").copy()


def shifts() -> pd.DataFrame:
    return _read("dim_shift").copy()


def materials() -> pd.DataFrame:
    return _read("dim_material").copy()


def downtime_factors() -> pd.DataFrame:
    return _read("dim_downtime_factor").copy()


def workers() -> pd.DataFrame:
    return _read("dim_worker").copy()


# ---- facts -----------------------------------------------------------------
def orders() -> pd.DataFrame:
    df = _read("fact_orders").copy()
    df["release_date"] = pd.to_datetime(df["release_date"], format=DATE_FMT)
    df["due_date"] = pd.to_datetime(df["due_date"], format=DATE_FMT)
    return df


def job_operations() -> pd.DataFrame:
    df = _read("fact_job_operations").copy()
    for c in ("scheduled_start", "scheduled_end", "actual_start", "actual_end"):
        df[c] = pd.to_datetime(df[c], format=TS_FMT)
    return df


def machine_sensor() -> pd.DataFrame:
    df = _read("fact_machine_sensor").copy()
    df["reading_time"] = pd.to_datetime(df["reading_time"], format=TS_FMT)
    return df


def demand() -> pd.DataFrame:
    df = _read("fact_demand").copy()
    df["demand_date"] = pd.to_datetime(df["demand_date"], format=DATE_FMT)
    return df


def production_history() -> pd.DataFrame:
    df = _read("fact_production_history").copy()
    df["production_date"] = pd.to_datetime(df["production_date"], format=DATE_FMT)
    return df


def plan_vs_actual() -> pd.DataFrame:
    df = _read("fact_plan_vs_actual").copy()
    df["production_date"] = pd.to_datetime(df["production_date"], format=DATE_FMT)
    return df


def worker_shift_availability() -> pd.DataFrame:
    df = _read("fact_worker_shift_availability").copy()
    df["availability_date"] = pd.to_datetime(df["availability_date"], format=DATE_FMT)
    return df


def clear_cache() -> None:
    """Drop cached frames (use after regenerating the dataset)."""
    _read.cache_clear()
