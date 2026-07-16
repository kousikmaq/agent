"""
Generate a coherent Beverage Manufacturing Plant dataset (star schema).

Replaces the mismatched multi-domain source CSVs with one consistent dataset where every
key (product/machine/worker/shift/material/operation/order) has a single meaning everywhere.
ML signal is deliberately injected so the downstream models can learn real relationships:
  - fact_job_operations.job_status   <- delay-risk classifier target
  - fact_machine_sensor.downtime_flag <- downtime classifier target
  - fact_demand.units_sold            <- demand forecaster target

Run:  python backend/data/generate_dataset.py
Output: backend/data/star/*.csv   (see schema.md)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "star")
os.makedirs(OUT, exist_ok=True)

DATE_FMT = "%d-%m-%Y"
TS_FMT = "%d-%m-%Y %H:%M:%S"


def d(dt: datetime) -> str:
    return dt.strftime(DATE_FMT)


def ts(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def save(df: pd.DataFrame, name: str) -> None:
    path = os.path.join(OUT, name)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"  {name:38s} rows={len(df)}")


# ---------------------------------------------------------------------------
# Reference constants
# ---------------------------------------------------------------------------
FLAVORS = ["Cola", "Orange", "Lemon", "Mango", "Apple", "Ginger", "Berry", "Lime"]
SIZES = [250, 500, 1000, 2000]
PACKS = ["Can", "PET Bottle", "Glass Bottle"]
REGIONS = ["North", "South", "East", "West"]

OP_SKILLS = ["Mixing", "Blending", "Carbonation", "Filling", "Labeling", "Packaging"]
OPERATIONS = [
    # op_id, name, skill, min_w, pref_w, eligible, seq, std_minutes
    ("OP10", "Mixing", "Mixing", 1, 2, "M01;M02", 10, 45),
    ("OP20", "Blending", "Blending", 1, 2, "M01;M02", 20, 40),
    ("OP30", "Carbonation", "Carbonation", 1, 1, "M02;M03", 30, 30),
    ("OP40", "Filling", "Filling", 2, 3, "M03;M04", 40, 50),
    ("OP50", "Labeling", "Labeling", 1, 2, "M04;M05", 50, 25),
    ("OP60", "Packaging", "Packaging", 2, 3, "M05;M01", 60, 35),
]
MACHINES = [
    # id, name, line, capable_ops, rate/hr, energy kwh/hr, reliability(0-1 higher=better)
    ("M01", "Prep-Mixer-1", "Line-A", "OP10;OP20;OP60", 900, 18.0, 0.93),
    ("M02", "Carbo-Unit-2", "Line-A", "OP10;OP20;OP30", 850, 22.0, 0.88),
    ("M03", "Filler-3", "Line-B", "OP30;OP40", 1200, 26.0, 0.90),
    ("M04", "Filler-Labeler-4", "Line-B", "OP40;OP50", 1100, 24.0, 0.85),
    ("M05", "Pack-Line-5", "Line-B", "OP50;OP60", 1000, 20.0, 0.91),
]
MATERIALS = [
    # id, name, uom, unit_cost, supplier, lead_days, reorder_pt, stock, safety
    ("MAT001", "Cola Concentrate", "litre", 180.0, "SUP01", 7, 400, 620, 150),
    ("MAT002", "Citrus Concentrate", "litre", 165.0, "SUP01", 7, 380, 210, 150),
    ("MAT003", "Sugar Syrup", "litre", 45.0, "SUP02", 4, 900, 1500, 300),
    ("MAT004", "CO2 Gas", "kg", 30.0, "SUP03", 3, 500, 260, 200),
    ("MAT005", "PET Preforms", "unit", 2.5, "SUP04", 10, 20000, 42000, 8000),
    ("MAT006", "Aluminium Cans", "unit", 3.2, "SUP04", 10, 25000, 18000, 9000),
]
SHIFTS = [
    ("S1", "Morning", "06:00", "14:00", 8, 30),
    ("S2", "Evening", "14:00", "22:00", 8, 26),
    ("S3", "Night", "22:00", "06:00", 8, 18),
]
DOWNTIME_FACTORS = [
    ("F01", "Mechanical Failure", "Machine", False),
    ("F02", "Electrical Fault", "Machine", False),
    ("F03", "Overheating", "Machine", False),
    ("F04", "High Vibration", "Machine", False),
    ("F05", "Material Shortage", "Supply", False),
    ("F06", "Changeover", "Process", False),
    ("F07", "Operator Error", "Human", True),
    ("F08", "Setup Delay", "Human", True),
    ("F09", "Quality Hold", "Process", False),
    ("F10", "Scheduled Maintenance", "Maintenance", False),
    ("F11", "Power Interruption", "Utility", False),
    ("F12", "Sensor Calibration", "Maintenance", False),
]

N_PRODUCTS = 40
N_WORKERS = 100
N_ORDERS = 500

HORIZON_START = datetime(2025, 6, 1, 6, 0, 0)   # planning "now"


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------
def build_dim_product() -> pd.DataFrame:
    rows = []
    for i in range(1, N_PRODUCTS + 1):
        flavor = FLAVORS[(i - 1) % len(FLAVORS)]
        size = int(rng.choice(SIZES))
        pack = PACKS[(i - 1) % len(PACKS)]
        base_mat = "MAT001" if flavor in ("Cola", "Ginger", "Berry") else "MAT002"
        rows.append({
            "product_id": f"PRD{i:03d}",
            "product_name": f"{flavor} {size}ml {pack}",
            "flavor": flavor,
            "size_ml": size,
            "pack_type": pack,
            "base_material_id": base_mat,
            "min_batch_minutes": int(rng.integers(60, 180)),
            "standard_unit_price": round(float(rng.uniform(15, 90)), 2),
        })
    return pd.DataFrame(rows)


def build_dim_machine() -> pd.DataFrame:
    return pd.DataFrame([
        {"machine_id": m, "machine_name": n, "line": ln, "capable_operations": ops,
         "nominal_rate_units_per_hr": rate, "hourly_energy_kwh": en, "reliability_index": rel}
        for (m, n, ln, ops, rate, en, rel) in MACHINES
    ])


def build_dim_operation() -> pd.DataFrame:
    return pd.DataFrame([
        {"operation_id": o, "operation_name": nm, "required_skill": sk, "min_workers": mn,
         "preferred_workers": pf, "eligible_machine_ids": el, "sequence": seq, "standard_minutes": stm}
        for (o, nm, sk, mn, pf, el, seq, stm) in OPERATIONS
    ])


def build_dim_shift() -> pd.DataFrame:
    return pd.DataFrame([
        {"shift_id": s, "shift_name": nm, "start_time": st, "end_time": et,
         "capacity_hours": ch, "required_workers": rw}
        for (s, nm, st, et, ch, rw) in SHIFTS
    ])


def build_dim_material() -> pd.DataFrame:
    return pd.DataFrame([
        {"material_id": mid, "material_name": nm, "unit_of_measure": uom, "unit_cost": uc,
         "supplier_id": sup, "supplier_lead_time_days": lt, "reorder_point": rp,
         "current_stock": stock, "safety_stock": ss}
        for (mid, nm, uom, uc, sup, lt, rp, stock, ss) in MATERIALS
    ])


def build_dim_downtime_factor() -> pd.DataFrame:
    return pd.DataFrame([
        {"factor_id": f, "factor_name": nm, "category": cat, "is_operator_error": err}
        for (f, nm, cat, err) in DOWNTIME_FACTORS
    ])


# machine -> operations it can perform (for worker qualification + routing)
MACHINE_OPS = {m[0]: m[3].split(";") for m in MACHINES}
OP_ELIGIBLE = {o[0]: o[5].split(";") for o in OPERATIONS}
OP_SKILL = {o[0]: o[2] for o in OPERATIONS}
OP_STD_MIN = {o[0]: o[7] for o in OPERATIONS}
SKILL_MACHINES = {sk: [m for m in MACHINE_OPS if any(OP_SKILL.get(op) == sk for op in MACHINE_OPS[m])]
                  for sk in OP_SKILLS}
MACH_RELIABILITY = {m[0]: m[6] for m in MACHINES}


def build_dim_worker() -> pd.DataFrame:
    rows = []
    all_skills = OP_SKILLS + ["QA", "Maintenance"]
    for i in range(1, N_WORKERS + 1):
        primary = OP_SKILLS[(i - 1) % len(OP_SKILLS)] if i <= 84 else all_skills[6 + ((i) % 2)]
        secondary = OP_SKILLS[(i) % len(OP_SKILLS)]
        quals = SKILL_MACHINES.get(primary, ["M01"])
        # add one adjacent machine qualification sometimes
        if rng.random() < 0.4:
            extra = f"M0{int(rng.integers(1, 6))}"
            quals = sorted(set(quals + [extra]))
        exp = int(rng.integers(1, 25))
        status = "Active" if rng.random() < 0.9 else "On Leave"
        rows.append({
            "worker_id": f"W{i:03d}",
            "worker_name": f"Worker_{i:03d}",
            "primary_skill": primary,
            "secondary_skill": secondary,
            "preferred_shift_id": f"S{int(rng.integers(1, 4))}",
            "max_weekly_hours": int(rng.choice([40, 44, 48])),
            "max_overtime_hours": int(rng.choice([4, 6, 8])),
            "hourly_cost_inr": round(float(rng.uniform(180, 480)) + exp * 6, 2),
            "experience_years": exp,
            "machine_qualifications": ";".join(quals),
            "employment_status": status,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
def build_fact_orders(products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i in range(1, N_ORDERS + 1):
        prod = products.iloc[int(rng.integers(0, len(products)))]
        release = HORIZON_START - timedelta(days=int(rng.integers(0, 30)))
        lead_days = int(rng.integers(3, 14))
        due = release + timedelta(days=lead_days)
        qty = int(rng.integers(2, 20)) * 500  # units
        priority = int(rng.choice([1, 2, 3], p=[0.25, 0.45, 0.30]))
        # most orders are historical (Completed); a realistic slice is still open/scheduled
        status = rng.choice(["Open", "Scheduled", "Completed"], p=[0.12, 0.10, 0.78])
        rows.append({
            "order_id": f"ORD{i:04d}",
            "product_id": prod["product_id"],
            "order_quantity": qty,
            "release_date": d(release),
            "due_date": d(due),
            "priority": priority,
            "customer_region": rng.choice(REGIONS),
            "status": status,
        })
    return pd.DataFrame(rows)


def build_fact_job_operations(orders: pd.DataFrame, workers: pd.DataFrame) -> pd.DataFrame:
    """500 orders x 6 operations. job_status carries injected delay signal.

    Two passes: (1) compute a risk score driven by operational features, then
    (2) assign labels by score percentiles so the target is balanced and learnable
    (~63% On-Time / 25% Delayed / 12% Failed).
    """
    worker_by_skill = {sk: workers[workers["primary_skill"] == sk]["worker_id"].tolist()
                       for sk in OP_SKILLS}
    fallback_workers = workers["worker_id"].tolist()
    exp_by_worker = dict(zip(workers["worker_id"], workers["experience_years"]))
    machine_energy = {m[0]: m[5] for m in MACHINES}

    staged = []
    jid = 0
    for _, order in orders.iterrows():
        release = datetime.strptime(order["release_date"], DATE_FMT).replace(hour=6)
        due = datetime.strptime(order["due_date"], DATE_FMT).replace(hour=22)
        batch_qty = int(order["order_quantity"])
        cursor = release
        for (op_id, _nm, skill, _mn, _pf, _el, seq, std_min) in OPERATIONS:
            jid += 1
            machine = rng.choice(OP_ELIGIBLE[op_id])
            pool = worker_by_skill.get(skill) or fallback_workers
            worker = rng.choice(pool)
            shift = f"S{int(rng.integers(1, 4))}"
            wexp = int(exp_by_worker[worker])

            size_factor = 1.0 + (batch_qty / 10000.0)
            proc_hours = round((std_min / 60.0) * size_factor * float(rng.uniform(0.85, 1.4)), 2)
            sched_start = cursor
            sched_end = sched_start + timedelta(hours=proc_hours)

            reliability = MACH_RELIABILITY[machine]
            downtime_minutes = float(max(0.0, rng.normal(18 * (1 - reliability) * 6, 8)))
            downtime_minutes = round(min(downtime_minutes, 120.0), 1)

            # ----- injected delay-risk latent score (features clearly drive it) -----
            risk = (
                0.9 * proc_hours
                + 0.05 * downtime_minutes
                + 16.0 * (1 - reliability)
                - 0.06 * wexp
                + (0.6 if shift == "S3" else 0.0)
                + (0.5 if order["priority"] == 1 else 0.0)
            )
            score = risk + float(rng.normal(0, 0.35))

            staged.append({
                "job_id": f"J{jid:05d}",
                "order_id": order["order_id"],
                "product_id": order["product_id"],
                "operation_id": op_id,
                "sequence": seq,
                "machine_id": machine,
                "material_id": rng.choice([m[0] for m in MATERIALS]),
                "worker_id": worker,
                "shift_id": shift,
                "batch_quantity": batch_qty,
                "processing_hours": proc_hours,
                "downtime_minutes": downtime_minutes,
                "energy_kwh": round(proc_hours * machine_energy[machine], 1),
                "_sched_start": sched_start,
                "_sched_end": sched_end,
                "_score": score,
            })
            cursor = sched_end + timedelta(minutes=15)

    # ----- pass 2: percentile-based label assignment -----
    scores = np.array([s["_score"] for s in staged])
    q_delay, q_fail = np.quantile(scores, [0.63, 0.88])

    rows = []
    for s in staged:
        sc = s["_score"]
        if sc >= q_fail:
            status = "Failed"
            delay_h = float(rng.uniform(2.5, 6.0))
            factor = rng.choice(["F01", "F02", "F03", "F05", "F11"])
        elif sc >= q_delay:
            status = "Delayed"
            delay_h = float(rng.uniform(0.5, 3.0))
            factor = rng.choice(["F03", "F04", "F06", "F07", "F08", "F09"])
        else:
            status = "On-Time"
            delay_h = float(rng.uniform(-0.3, 0.3))
            factor = ""
        actual_start = s["_sched_start"] + timedelta(hours=max(0.0, delay_h * 0.4))
        actual_end = s["_sched_end"] + timedelta(hours=delay_h)
        rows.append({
            "job_id": s["job_id"],
            "order_id": s["order_id"],
            "product_id": s["product_id"],
            "operation_id": s["operation_id"],
            "sequence": s["sequence"],
            "machine_id": s["machine_id"],
            "material_id": s["material_id"],
            "worker_id": s["worker_id"],
            "shift_id": s["shift_id"],
            "batch_quantity": s["batch_quantity"],
            "processing_hours": s["processing_hours"],
            "scheduled_start": ts(s["_sched_start"]),
            "scheduled_end": ts(s["_sched_end"]),
            "actual_start": ts(actual_start),
            "actual_end": ts(actual_end),
            "downtime_minutes": s["downtime_minutes"],
            "downtime_factor_id": factor,
            "energy_kwh": s["energy_kwh"],
            "job_status": status,
        })
    return pd.DataFrame(rows)


def build_fact_machine_sensor() -> pd.DataFrame:
    """600 readings. Faulty readings show a clear degraded signature (high temps/vibration,
    low pressures) and get downtime_flag=1; healthy readings are clearly separated. A small
    (~5%) label flip keeps it non-trivial. More-degraded machines fault more often, so
    machine_id is also informative."""
    rows = []
    n_per_machine = 120
    eid = 0
    for (mid, _nm, _ln, _ops, _rate, _en, reliability) in MACHINES:
        base_deg = 1 - reliability                 # 0.07 .. 0.15
        p_fault = 0.15 + 1.0 * base_deg            # ~0.22 .. 0.30
        t = datetime(2025, 5, 1, 6, 0, 0)
        for _ in range(n_per_machine):
            eid += 1
            t += timedelta(hours=float(rng.uniform(4, 10)))
            is_fault = rng.random() < p_fault
            if is_fault:
                hyd_p = rng.normal(85, 8)
                cool_p = rng.normal(4.8, 0.4)
                air_p = rng.normal(4.9, 0.4)
                cool_t = rng.normal(40, 4)
                hyd_t = rng.normal(72, 5)
                bearing_t = rng.normal(60, 5)
                spin_vib = rng.normal(3.4, 0.5)
                tool_vib = rng.normal(40, 4)
                rpm = rng.normal(17000, 1500)
                torque = rng.normal(30, 4)
                cutting = rng.normal(4.6, 0.5)
            else:
                hyd_p = rng.normal(122 - base_deg * 10, 8)
                cool_p = rng.normal(6.6, 0.4)
                air_p = rng.normal(6.4, 0.4)
                cool_t = rng.normal(23, 3)
                hyd_t = rng.normal(44, 4)
                bearing_t = rng.normal(32, 4)
                spin_vib = rng.normal(1.2, 0.3)
                tool_vib = rng.normal(25, 3)
                rpm = rng.normal(22500, 1500)
                torque = rng.normal(19, 3)
                cutting = rng.normal(3.1, 0.4)

            downtime = 1 if is_fault else 0
            if rng.random() < 0.05:               # small label noise
                downtime = 1 - downtime
            rows.append({
                "event_id": f"EVT{eid:05d}",
                "reading_time": ts(t),
                "machine_id": mid,
                "hydraulic_pressure_bar": round(float(hyd_p), 2),
                "coolant_pressure_bar": round(float(cool_p), 2),
                "air_system_pressure_bar": round(float(air_p), 2),
                "coolant_temp_c": round(float(cool_t), 1),
                "hydraulic_oil_temp_c": round(float(hyd_t), 1),
                "spindle_bearing_temp_c": round(float(bearing_t), 1),
                "spindle_vibration_um": round(float(spin_vib), 3),
                "tool_vibration_um": round(float(tool_vib), 2),
                "spindle_speed_rpm": int(max(0, rpm)),
                "voltage_v": round(float(rng.normal(340, 20)), 1),
                "torque_nm": round(float(torque), 2),
                "cutting_force_kn": round(float(cutting), 2),
                "machine_status": "DOWN" if downtime else "RUNNING",
                "downtime_flag": downtime,
            })
    return pd.DataFrame(rows)


def build_fact_demand(products: pd.DataFrame) -> pd.DataFrame:
    """10 SKUs x 60 days; units_sold has trend+weekly seasonality+promo signal."""
    rows = []
    skus = products.head(10)
    start = datetime(2025, 4, 1)
    for _, prod in skus.iterrows():
        base = float(rng.uniform(80, 260))
        trend = float(rng.uniform(-0.4, 0.8))
        inv = float(rng.uniform(800, 1600))
        unit_cost = round(float(rng.uniform(8, 20)), 2)
        unit_price = round(unit_cost * float(rng.uniform(1.3, 1.8)), 2)
        reorder = int(base * 3)
        for day in range(60):
            dt = start + timedelta(days=day)
            dow = dt.weekday()
            seasonal = 1.0 + 0.25 * np.sin(2 * np.pi * dow / 7.0)
            promo = int(rng.random() < 0.18)
            promo_lift = 1.0 + (0.5 if promo else 0.0)
            noise = float(rng.normal(1.0, 0.12))
            units = max(0, int(base * (1 + trend * day / 60.0) * seasonal * promo_lift * noise))
            inv = max(0.0, inv - units + (float(rng.uniform(0, 300)) if day % 7 == 0 else 0.0))
            stockout = int(inv <= 0)
            rows.append({
                "demand_date": d(dt),
                "product_id": prod["product_id"],
                "warehouse_id": f"WH_{int(rng.integers(1, 4))}",
                "region": rng.choice(REGIONS),
                "units_sold": units,
                "inventory_level": int(inv),
                "reorder_point": reorder,
                "order_quantity": int(base * 4),
                "unit_cost": unit_cost,
                "unit_price": unit_price,
                "promotion_flag": promo,
                "stockout_flag": stockout,
                "material_id": prod["base_material_id"],
            })
    return pd.DataFrame(rows)


def build_fact_production_history(products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    start = datetime(2025, 1, 1)
    for i in range(1, 501):
        dt = start + timedelta(days=int(rng.integers(0, 150)))
        prod = products.iloc[int(rng.integers(0, len(products)))]
        machine = rng.choice([m[0] for m in MACHINES])
        shift = f"S{int(rng.integers(1, 4))}"
        units = int(rng.integers(500, 4000))
        defects = int(max(0, rng.normal(units * 0.02, units * 0.01)))
        ptime = round(float(rng.uniform(4, 24)), 2)
        rows.append({
            "production_id": f"PH{i:04d}",
            "production_date": d(dt),
            "product_id": prod["product_id"],
            "machine_id": machine,
            "shift_id": shift,
            "units_produced": units,
            "defects": defects,
            "production_time_hours": ptime,
            "material_cost_per_unit": round(float(rng.uniform(6, 40)), 2),
            "labour_cost_per_hour": round(float(rng.uniform(200, 480)), 2),
            "energy_kwh": round(ptime * float(rng.uniform(15, 28)), 1),
            "operator_count": int(rng.integers(1, 5)),
            "maintenance_hours": round(float(rng.uniform(0, 5)), 2),
            "downtime_hours": round(float(rng.uniform(0, 4)), 2),
            "scrap_rate": round(defects / units if units else 0.0, 4),
            "rework_hours": round(float(rng.uniform(0, 3)), 2),
            "quality_checks_failed": int(rng.integers(0, 3)),
            "avg_temp_c": round(float(rng.uniform(20, 30)), 1),
            "avg_humidity_pct": round(float(rng.uniform(35, 65)), 1),
            "status": "COMPLETED",
        })
    return pd.DataFrame(rows)


def build_fact_plan_vs_actual(products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    start = datetime(2025, 1, 1)
    for i in range(1, 501):
        dt = start + timedelta(days=int(rng.integers(0, 150)))
        prod = products.iloc[int(rng.integers(0, len(products)))]
        machine = rng.choice([m[0] for m in MACHINES])
        plan_q = int(rng.integers(500, 4000))
        actual_q = int(max(0, plan_q * float(rng.uniform(0.8, 1.1))))
        plan_e = round(float(rng.uniform(80, 400)), 1)
        actual_e = round(plan_e * float(rng.uniform(0.85, 1.2)), 1)
        plan_t = round(float(rng.uniform(4, 20)), 2)
        actual_t = round(plan_t * float(rng.uniform(0.85, 1.25)), 2)
        var = round((actual_q - plan_q) / plan_q * 100.0, 2) if plan_q else 0.0
        rows.append({
            "plan_id": f"PLN{i:04d}",
            "production_date": d(dt),
            "product_id": prod["product_id"],
            "machine_id": machine,
            "plan_quantity": plan_q,
            "actual_quantity": actual_q,
            "plan_energy_kwh": plan_e,
            "actual_energy_kwh": actual_e,
            "plan_time_hours": plan_t,
            "actual_time_hours": actual_t,
            "quantity_variance_pct": var,
            "status": rng.choice(["ON_TARGET", "UNDER", "OVER"], p=[0.5, 0.3, 0.2]),
        })
    return pd.DataFrame(rows)


def build_fact_worker_shift_availability(workers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, w in workers.iterrows():
        primary_machine = w["machine_qualifications"].split(";")[0]
        for day in range(7):
            dt = HORIZON_START + timedelta(days=day)
            on_leave = w["employment_status"] == "On Leave"
            available = 0 if (on_leave or rng.random() < 0.12) else 1
            if available:
                status = "AVAILABLE"
                reason = ""
                hours = float(w["max_weekly_hours"]) / 5.0
                ot = int(rng.random() < 0.4)
            else:
                status = "UNAVAILABLE"
                reason = rng.choice(["Leave", "Sick", "Training", "Off"])
                hours = 0.0
                ot = 0
            rows.append({
                "worker_id": w["worker_id"],
                "availability_date": d(dt),
                "shift_id": w["preferred_shift_id"],
                "available": available,
                "availability_status": status,
                "available_hours": round(hours, 1),
                "overtime_available": ot,
                "unavailability_reason": reason,
                "primary_machine_id": primary_machine,
            })
    return pd.DataFrame(rows)


def main() -> None:
    print("Generating dimensions...")
    products = build_dim_product()
    machines = build_dim_machine()
    operations = build_dim_operation()
    shifts = build_dim_shift()
    materials = build_dim_material()
    factors = build_dim_downtime_factor()
    workers = build_dim_worker()
    save(products, "dim_product.csv")
    save(machines, "dim_machine.csv")
    save(operations, "dim_operation.csv")
    save(shifts, "dim_shift.csv")
    save(materials, "dim_material.csv")
    save(factors, "dim_downtime_factor.csv")
    save(workers, "dim_worker.csv")

    print("Generating facts...")
    orders = build_fact_orders(products)
    jobs = build_fact_job_operations(orders, workers)
    sensor = build_fact_machine_sensor()
    demand = build_fact_demand(products)
    history = build_fact_production_history(products)
    pva = build_fact_plan_vs_actual(products)
    avail = build_fact_worker_shift_availability(workers)
    save(orders, "fact_orders.csv")
    save(jobs, "fact_job_operations.csv")
    save(sensor, "fact_machine_sensor.csv")
    save(demand, "fact_demand.csv")
    save(history, "fact_production_history.csv")
    save(pva, "fact_plan_vs_actual.csv")
    save(avail, "fact_worker_shift_availability.csv")

    # quick signal report
    print("\nSignal check:")
    print("  job_status dist:\n", jobs["job_status"].value_counts().to_string())
    print("  downtime_flag rate:", round(sensor["downtime_flag"].mean(), 3))
    print("  demand units_sold mean:", round(demand["units_sold"].mean(), 1))
    print("\nDone ->", OUT)


if __name__ == "__main__":
    main()
