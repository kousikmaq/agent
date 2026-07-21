"""
Generates a connected, relational manufacturing dataset for the
Production Planning Agent, grounded in real valve-manufacturing structure
(valve types, materials, components, BOM). Deterministic (seeded).

Tables (all linked by IDs):
  work_centers -> routings <- items -> bom <- components -> inventory
  customers -> orders <- items

Run:  python generate_dataset.py   (from app/backend/data)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent

# ----------------------------------------------------------------- dimensions
VALVE_TYPES = ["Gate", "Globe", "Ball", "Butterfly", "Check", "Needle", "Plug", "Diaphragm", "Safety"]
MATERIALS = ["Brass", "Bronze", "CastIron", "CarbonSteel", "StainlessSteel", "Duplex"]
SIZES = [15, 25, 40, 50, 80, 100, 150, 200]

# ----------------------------------------------------------------- work centers
# department, capacity = hours_per_shift * shifts_per_day * days_per_week
WORK_CENTERS = [
    ("CAST-01", "Body Casting", "Foundry", 8, 3, 5),
    ("CNC-01", "CNC Machining 1", "Machining", 8, 3, 5),
    ("CNC-02", "CNC Machining 2", "Machining", 8, 3, 5),
    ("CNC-03", "CNC Machining 3", "Machining", 8, 3, 5),
    ("GRIND-01", "Seat Grinding", "Finishing", 8, 2, 5),
    ("ASSY-01", "Assembly Line 1", "Assembly", 8, 3, 5),
    ("ASSY-02", "Assembly Line 2", "Assembly", 8, 3, 5),
    ("TEST-01", "Pressure Testing", "Quality", 8, 3, 5),
    ("PACK-01", "Packing", "Logistics", 8, 2, 5),
]

# op_seq, wc_group, setup_min, run_base_min_per_unit
ROUTING_TEMPLATE = [
    (10, "CAST", 40, 0.7),
    (20, "CNC", 30, 1.8),
    (30, "GRIND", 15, 0.5),
    (40, "ASSY", 15, 0.9),
    (50, "TEST", 10, 0.6),
    (60, "PACK", 5, 0.25),
]

# ----------------------------------------------------------------- components
COMPONENT_DEFS = [
    ("Body", "Casting"), ("Bonnet", "Casting"), ("Disc", "Machined"),
    ("Ball", "Machined"), ("Gate", "Machined"), ("Stem", "Machined"),
    ("SeatRing", "Sealing"), ("Gasket", "Sealing"), ("ORing", "Sealing"),
    ("Spring", "Hardware"), ("Handwheel", "Hardware"), ("Actuator", "Hardware"),
    ("FastenerSet", "Hardware"), ("Nameplate", "Hardware"), ("PackingGland", "Sealing"),
]
SUPPLIERS = ["Ferro Alloys Ltd", "SealTech Co", "Precision Parts Inc", "NordForge", "Delta Hardware"]


def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name:22} {len(rows):4} rows")


def build():
    print("Generating dataset...")

    # ---- work_centers.csv
    wc_rows = []
    for wid, name, dept, hps, spd, days in WORK_CENTERS:
        wc_rows.append([wid, name, dept, hps, spd, days, hps * spd * days])
    write_csv("work_centers.csv",
              ["work_center_id", "name", "department", "hours_per_shift",
               "shifts_per_day", "days_per_week", "weekly_capacity_hours"], wc_rows)

    cnc_ids = ["CNC-01", "CNC-02", "CNC-03"]
    assy_ids = ["ASSY-01", "ASSY-02"]

    # ---- items.csv  (about 48 items)
    item_rows = []
    routing_rows = []
    items = []
    idx = 0
    for vtype in VALVE_TYPES:
        # a handful of material/size combos per valve type
        combos = random.sample([(m, s) for m in MATERIALS for s in SIZES], 5)
        for material, size in combos:
            idx += 1
            item_id = f"VLV-{idx:03d}"
            family = f"{vtype}-{material}"
            batch = random.choice([25, 50, 50, 100])
            name = f"{vtype} Valve {material} {size}mm"
            item_rows.append([item_id, name, vtype, material, size, family, batch])
            items.append((item_id, vtype, material, size, family))

            # routing for this item
            size_factor = max(0.5, min(2.0, size / 80.0))
            cnc = cnc_ids[idx % 3]
            cnc_alt = cnc_ids[(idx + 1) % 3]
            assy = assy_ids[idx % 2]
            for op_seq, grp, setup, run_base in ROUTING_TEMPLATE:
                if grp == "CAST":
                    wc, alt = "CAST-01", ""
                elif grp == "CNC":
                    wc, alt = cnc, cnc_alt
                elif grp == "GRIND":
                    wc, alt = "GRIND-01", ""
                elif grp == "ASSY":
                    wc, alt = assy, (assy_ids[(idx + 1) % 2])
                elif grp == "TEST":
                    wc, alt = "TEST-01", ""
                else:
                    wc, alt = "PACK-01", ""
                run = round(run_base * size_factor * random.uniform(0.9, 1.15), 2)
                routing_rows.append([item_id, op_seq, wc, setup, run, alt])
    write_csv("items.csv",
              ["item_id", "item_name", "valve_type", "body_material",
               "size_mm", "product_family", "standard_batch_size"], item_rows)
    write_csv("routings.csv",
              ["item_id", "op_seq", "work_center_id", "setup_min",
               "run_min_per_unit", "alt_work_center_id"], routing_rows)

    # ---- components.csv  (material variants -> ~45)
    comp_rows = []
    components = []
    cidx = 0
    for cname, cat in COMPONENT_DEFS:
        for material in random.sample(MATERIALS, 3):
            cidx += 1
            comp_id = f"CMP-{cidx:03d}"
            cost = round(random.uniform(2, 240), 2)
            lead = random.choice([3, 5, 7, 10, 14, 21, 30])
            comp_rows.append([comp_id, f"{cname} ({material})", cat, material,
                              cost, lead, random.choice(SUPPLIERS)])
            components.append((comp_id, cname, cat))
    write_csv("components.csv",
              ["component_id", "component_name", "category", "material",
               "unit_cost_usd", "lead_time_days", "supplier"], comp_rows)

    # ---- bom.csv  (link items -> components)
    bom_rows = []
    comps_by_name = {}
    for comp_id, cname, cat in components:
        comps_by_name.setdefault(cname, []).append(comp_id)
    for item_id, vtype, material, size, family in items:
        needed = ["Body", "Bonnet", "Stem", "Gasket", "FastenerSet", "Nameplate"]
        if vtype == "Ball":
            needed.append("Ball")
        elif vtype == "Gate":
            needed.append("Gate")
        elif vtype in ("Check", "Safety"):
            needed.append("Spring")
        else:
            needed.append("Disc")
        if vtype in ("Globe", "Gate", "Needle"):
            needed.append("Handwheel")
        for cname in needed:
            comp_id = random.choice(comps_by_name[cname])
            qty = 1
            if cname == "FastenerSet":
                qty = random.choice([4, 6, 8])
            elif cname == "Gasket":
                qty = 2
            bom_rows.append([item_id, comp_id, qty])
    write_csv("bom.csv", ["item_id", "component_id", "qty_per"], bom_rows)

    # ---- inventory.csv  (one row per component)
    # Most components are amply stocked; a few are constrained (short this period).
    # A separate RNG + replicated draws keep the main stream (orders/customers) unchanged.
    inv_rng = random.Random(7)
    # constrain only valve-type-specific parts, so shortages hit a realistic subset
    specialty = {"Disc", "Ball", "Gate", "Spring", "Handwheel", "SeatRing"}
    candidates = [c[0] for c in components if c[1] in specialty]
    short_set = set(inv_rng.sample(candidates, min(4, len(candidates))))
    inv_rows = []
    base = date(2026, 7, 6)
    for comp_id, cname, cat in components:
        # keep the original random stream intact so orders/customers do not change
        random.randint(0, 1200)
        random.randint(100, 400)
        _oo = random.choice([0, 0, 250, 500, 1000])
        if _oo:
            random.randint(2, 30)
        # realistic stock levels
        reorder = inv_rng.randint(200, 600)
        if comp_id in short_set:
            on_hand = inv_rng.randint(0, 500)
            on_order = inv_rng.choice([0, 1000, 2000])
            receipt = (base + timedelta(days=inv_rng.randint(20, 45))).isoformat() if on_order else ""
        else:
            on_hand = inv_rng.randint(40000, 90000)
            on_order = 0
            receipt = ""
        inv_rows.append([comp_id, on_hand, reorder, on_order, receipt])
    write_csv("inventory.csv",
              ["component_id", "on_hand_qty", "reorder_point",
               "on_order_qty", "next_receipt_date"], inv_rows)

    # ---- customers.csv  (30)
    tiers = ["A", "A", "B", "B", "B", "C"]
    countries = ["USA", "Germany", "India", "UK", "UAE", "Brazil", "Japan"]
    cust_rows = []
    customers = []
    for i in range(1, 31):
        cid = f"CUST-{i:03d}"
        tier = random.choice(tiers)
        penalty = {"A": random.choice([500, 750, 1000]),
                   "B": random.choice([100, 200, 300]),
                   "C": 0}[tier]
        cust_rows.append([cid, f"Customer {i:02d}", tier, penalty, random.choice(countries)])
        customers.append((cid, tier))
    write_csv("customers.csv",
              ["customer_id", "customer_name", "tier", "penalty_per_day_usd", "country"], cust_rows)

    # ---- orders.csv  (520, due dates spread over 16 weeks with varying demand)
    order_rows = []
    weeks = 16
    # a demand profile so some weeks are light and some peak (realistic)
    week_weights = [1.0, 1.3, 0.7, 1.7, 0.5, 1.2, 0.9, 1.8,
                    0.6, 1.1, 1.5, 0.7, 1.6, 0.8, 1.0, 0.6]
    for i in range(1, 521):
        oid = f"SO-{i:05d}"
        item_id = random.choice(items)[0]
        cid, tier = random.choice(customers)
        qty = random.randint(40, 320)
        wk = random.choices(range(weeks), weights=week_weights)[0]
        due = base + timedelta(days=wk * 7 + random.randint(0, 4))       # a weekday that week
        order_dt = due - timedelta(days=random.randint(10, 35))
        priority = {"A": "High", "B": "Normal", "C": "Low"}[tier]
        status = random.choices(["Open", "Released", "Completed"], weights=[55, 30, 15])[0]
        order_rows.append([oid, item_id, cid, order_dt.isoformat(),
                           due.isoformat(), qty, priority, status])
    write_csv("orders.csv",
              ["order_id", "item_id", "customer_id", "order_date",
               "due_date", "quantity", "priority", "status"], order_rows)

    print("Done.")


if __name__ == "__main__":
    build()
