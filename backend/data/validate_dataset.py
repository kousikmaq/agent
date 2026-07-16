"""
Validate the generated star-schema dataset: foreign-key integrity, key nullability,
value ranges, date formats, machine-eligibility rules, and minimum fact-row counts.

Run:  python backend/data/validate_dataset.py
Exit code 0 = clean, 1 = problems found.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STAR = os.path.join(HERE, "star")

errors: list[str] = []
warnings: list[str] = []


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(STAR, name), dtype=str, keep_default_na=False)


def check_fk(child: pd.DataFrame, col: str, parent_ids: set[str], ctx: str) -> None:
    vals = set(child[col].unique()) - {""}
    missing = vals - parent_ids
    if missing:
        errors.append(f"[FK] {ctx}: {len(missing)} '{col}' values not in parent, e.g. {sorted(missing)[:5]}")


def check_no_null(df: pd.DataFrame, cols: list[str], ctx: str) -> None:
    for c in cols:
        blank = (df[c].astype(str).str.strip() == "").sum()
        if blank:
            errors.append(f"[NULL] {ctx}: column '{c}' has {blank} blank values")


def check_min_rows(df: pd.DataFrame, name: str, n: int = 500) -> None:
    if len(df) < n:
        errors.append(f"[ROWS] {name}: {len(df)} rows (< {n})")


def check_dates(df: pd.DataFrame, col: str, fmt: str, ctx: str) -> None:
    bad = 0
    for v in df[col].unique():
        if not v:
            continue
        try:
            datetime.strptime(v, fmt)
        except ValueError:
            bad += 1
    if bad:
        errors.append(f"[DATE] {ctx}: {bad} distinct '{col}' values not in format {fmt}")


def check_unique(df: pd.DataFrame, col: str, ctx: str) -> None:
    if df[col].duplicated().any():
        errors.append(f"[PK] {ctx}: '{col}' is not unique ({df[col].duplicated().sum()} dupes)")


def main() -> int:
    # dimensions
    products = load("dim_product.csv")
    machines = load("dim_machine.csv")
    operations = load("dim_operation.csv")
    shifts = load("dim_shift.csv")
    materials = load("dim_material.csv")
    factors = load("dim_downtime_factor.csv")
    workers = load("dim_worker.csv")
    # facts
    orders = load("fact_orders.csv")
    jobs = load("fact_job_operations.csv")
    sensor = load("fact_machine_sensor.csv")
    demand = load("fact_demand.csv")
    history = load("fact_production_history.csv")
    pva = load("fact_plan_vs_actual.csv")
    avail = load("fact_worker_shift_availability.csv")

    pid = set(products["product_id"])
    mid = set(machines["machine_id"])
    oid = set(operations["operation_id"])
    sid = set(shifts["shift_id"])
    matid = set(materials["material_id"])
    fid = set(factors["factor_id"])
    wid = set(workers["worker_id"])
    orderid = set(orders["order_id"])

    # primary keys
    check_unique(products, "product_id", "dim_product")
    check_unique(machines, "machine_id", "dim_machine")
    check_unique(workers, "worker_id", "dim_worker")
    check_unique(orders, "order_id", "fact_orders")
    check_unique(jobs, "job_id", "fact_job_operations")

    # dimension internal integrity
    for _, r in operations.iterrows():
        for m in r["eligible_machine_ids"].split(";"):
            if m not in mid:
                errors.append(f"[DIM] operation {r['operation_id']} eligible machine '{m}' invalid")
    for _, r in workers.iterrows():
        for m in r["machine_qualifications"].split(";"):
            if m not in mid:
                errors.append(f"[DIM] worker {r['worker_id']} qualification '{m}' invalid")
    check_fk(products, "base_material_id", matid, "dim_product.base_material_id")

    # fact foreign keys
    check_fk(orders, "product_id", pid, "fact_orders")
    check_fk(jobs, "order_id", orderid, "fact_job_operations")
    check_fk(jobs, "product_id", pid, "fact_job_operations")
    check_fk(jobs, "operation_id", oid, "fact_job_operations")
    check_fk(jobs, "machine_id", mid, "fact_job_operations")
    check_fk(jobs, "material_id", matid, "fact_job_operations")
    check_fk(jobs, "worker_id", wid, "fact_job_operations")
    check_fk(jobs, "shift_id", sid, "fact_job_operations")
    check_fk(jobs, "downtime_factor_id", fid, "fact_job_operations")  # "" excluded by check_fk
    check_fk(sensor, "machine_id", mid, "fact_machine_sensor")
    check_fk(demand, "product_id", pid, "fact_demand")
    check_fk(demand, "material_id", matid, "fact_demand")
    check_fk(history, "product_id", pid, "fact_production_history")
    check_fk(history, "machine_id", mid, "fact_production_history")
    check_fk(history, "shift_id", sid, "fact_production_history")
    check_fk(pva, "product_id", pid, "fact_plan_vs_actual")
    check_fk(pva, "machine_id", mid, "fact_plan_vs_actual")
    check_fk(avail, "worker_id", wid, "fact_worker_shift_availability")
    check_fk(avail, "shift_id", sid, "fact_worker_shift_availability")

    # machine-eligibility business rule: every job runs on a machine eligible for its operation
    elig = {r["operation_id"]: set(r["eligible_machine_ids"].split(";")) for _, r in operations.iterrows()}
    bad_elig = sum(1 for _, j in jobs.iterrows() if j["machine_id"] not in elig.get(j["operation_id"], set()))
    if bad_elig:
        errors.append(f"[RULE] {bad_elig} jobs assigned to a machine not eligible for their operation")

    # key nullability
    check_no_null(jobs, ["order_id", "product_id", "operation_id", "machine_id", "worker_id", "shift_id"], "fact_job_operations")
    check_no_null(orders, ["order_id", "product_id", "due_date"], "fact_orders")
    check_no_null(sensor, ["machine_id", "downtime_flag"], "fact_machine_sensor")

    # min rows on facts
    for df, nm in [(orders, "fact_orders"), (jobs, "fact_job_operations"), (sensor, "fact_machine_sensor"),
                   (demand, "fact_demand"), (history, "fact_production_history"), (pva, "fact_plan_vs_actual"),
                   (avail, "fact_worker_shift_availability")]:
        check_min_rows(df, nm)

    # date formats
    check_dates(orders, "release_date", "%d-%m-%Y", "fact_orders")
    check_dates(orders, "due_date", "%d-%m-%Y", "fact_orders")
    check_dates(jobs, "scheduled_start", "%d-%m-%Y %H:%M:%S", "fact_job_operations")
    check_dates(demand, "demand_date", "%d-%m-%Y", "fact_demand")

    # ML target sanity
    dist = jobs["job_status"].value_counts(normalize=True)
    if dist.get("Delayed", 0) < 0.10 or dist.get("Failed", 0) < 0.05:
        warnings.append(f"[ML] job_status may be imbalanced: {dist.to_dict()}")
    dtrate = sensor["downtime_flag"].astype(int).mean()
    if not (0.10 <= dtrate <= 0.45):
        warnings.append(f"[ML] downtime_flag rate {dtrate:.3f} outside healthy 0.10-0.45")

    # report
    print("=" * 60)
    print("DATASET VALIDATION")
    print("=" * 60)
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print("  ! " + w)
    if errors:
        print(f"\n{len(errors)} ERROR(s):")
        for e in errors:
            print("  x " + e)
        print("\nRESULT: FAIL")
        return 1
    print("\nAll referential-integrity, nullability, range and format checks passed.")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
