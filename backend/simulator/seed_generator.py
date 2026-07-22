"""Day-0 baseline factory generator.

Builds a complete, internally-consistent :class:`FactoryState` from scratch for
the first production day. Subsequent days are produced by *evolving* this
baseline (see :mod:`simulator.engine`), never by regenerating it.

All randomness flows through the injected :class:`random.Random` so a given
seed reproduces an identical factory.
"""

from __future__ import annotations

from datetime import date, timedelta
from random import Random

from app.domain.enums import (
    BusinessRuleType,
    CustomerTier,
    MachineStatus,
    OrderStatus,
    PurchaseOrderStatus,
    RuleEnforcement,
    SkillProficiency,
    UnitOfMeasure,
)
from app.domain.models.bom import BomLine
from app.domain.models.business_rule import BusinessRule
from app.domain.models.customer import Customer
from app.domain.models.factory_state import FactoryState
from app.domain.models.inventory import InventoryItem
from app.domain.models.machine import Machine
from app.domain.models.plant_calendar import PlantCalendar
from app.domain.models.product import Product
from app.domain.models.production_order import ProductionOrder
from app.domain.models.purchase_order import PurchaseOrder
from app.domain.models.routing import Operation, Routing
from app.domain.models.supplier import Supplier
from app.domain.models.workforce import Worker, WorkerSkill
from app.utils.datetime_utils import format_business_date
from simulator.calendars import (
    STANDARD_SHIFTS,
    build_machine_availability,
    build_shift_calendars,
    build_worker_availability,
)
from simulator.config import SimulatorConfig


def _skill_code(work_center: str) -> str:
    """Return the canonical skill code required to work a work center."""
    return f"SKILL_{work_center}"


def _build_machines(config: SimulatorConfig) -> list[Machine]:
    machines: list[Machine] = []
    counter = 0
    for work_center in config.work_centers:
        for index in range(config.machines_per_work_center):
            counter += 1
            machines.append(
                Machine(
                    machine_id=f"MC-{counter:04d}",
                    name=f"{work_center} Machine {index + 1}",
                    work_center=work_center,
                    status=MachineStatus.AVAILABLE,
                    capacity_minutes_per_day=960,  # two 8h shifts
                    efficiency_factor=1.0,
                )
            )
    return machines


def _build_products(config: SimulatorConfig) -> tuple[list[Product], list[Product]]:
    """Return ``(finished_goods, raw_materials)`` product lists."""
    finished: list[Product] = []
    for i in range(config.num_finished_products):
        pid = f"FG-{i + 1:04d}"
        finished.append(
            Product(
                product_id=pid,
                name=f"Finished Good {i + 1}",
                uom=UnitOfMeasure.EACH,
                routing_id=f"RT-{i + 1:04d}",
                standard_cost=round(50 + i * 7.5, 2),
                is_purchased=False,
            )
        )
    raw: list[Product] = []
    for i in range(config.num_raw_materials):
        pid = f"RM-{i + 1:04d}"
        raw.append(
            Product(
                product_id=pid,
                name=f"Raw Material {i + 1}",
                uom=UnitOfMeasure.KILOGRAM if i % 2 else UnitOfMeasure.EACH,
                routing_id=None,
                standard_cost=round(2 + i * 0.9, 2),
                is_purchased=True,
            )
        )
    return finished, raw


def _build_routings(
    finished: list[Product], machines: list[Machine], config: SimulatorConfig, rng: Random
) -> list[Routing]:
    machines_by_wc: dict[str, list[str]] = {}
    for machine in machines:
        machines_by_wc.setdefault(machine.work_center, []).append(machine.machine_id)

    routings: list[Routing] = []
    op_counter = 0
    for index, product in enumerate(finished, start=1):
        count = rng.randint(
            config.operations_per_routing_min, config.operations_per_routing_max
        )
        count = min(count, len(config.work_centers))
        # Preserve canonical work-center order for a realistic process flow.
        chosen = sorted(
            rng.sample(range(len(config.work_centers)), count)
        )
        operations: list[Operation] = []
        for sequence, wc_index in enumerate(chosen, start=1):
            op_counter += 1
            work_center = config.work_centers[wc_index]
            operations.append(
                Operation(
                    operation_id=f"OP-{op_counter:04d}",
                    routing_id=product.routing_id or f"RT-{index:04d}",
                    sequence=sequence,
                    name=f"{work_center} step",
                    work_center=work_center,
                    setup_minutes=rng.randint(10, 60),
                    run_minutes_per_unit=round(rng.uniform(0.5, 5.0), 2),
                    eligible_machine_ids=list(machines_by_wc.get(work_center, [])),
                    required_skill=_skill_code(work_center),
                )
            )
        routings.append(
            Routing(
                routing_id=product.routing_id or f"RT-{index:04d}",
                product_id=product.product_id,
                version="1",
                operations=operations,
            )
        )
    return routings


def _build_boms(
    finished: list[Product], raw: list[Product], config: SimulatorConfig, rng: Random
) -> list[BomLine]:
    boms: list[BomLine] = []
    for product in finished:
        count = rng.randint(config.components_per_bom_min, config.components_per_bom_max)
        count = min(count, len(raw))
        for component in rng.sample(raw, count):
            boms.append(
                BomLine(
                    parent_product_id=product.product_id,
                    component_product_id=component.product_id,
                    quantity_per=round(rng.uniform(0.5, 4.0), 2),
                    scrap_factor=round(rng.choice([0.0, 0.02, 0.05]), 2),
                )
            )
    return boms


def _build_workforce(
    config: SimulatorConfig, rng: Random
) -> tuple[list[Worker], list[WorkerSkill]]:
    shift_ids = [shift.shift_id for shift in STANDARD_SHIFTS]
    skills_pool = [_skill_code(wc) for wc in config.work_centers]
    workers: list[Worker] = []
    worker_skills: list[WorkerSkill] = []
    for i in range(config.num_workers):
        worker_id = f"WK-{i + 1:04d}"
        workers.append(
            Worker(
                worker_id=worker_id,
                name=f"Worker {i + 1}",
                home_shift_id=shift_ids[i % len(shift_ids)],
                max_regular_minutes_per_day=480,
                max_overtime_minutes_per_day=120,
                overtime_allowed=rng.random() > 0.2,
            )
        )
        skill_count = rng.randint(1, 3)
        for skill in rng.sample(skills_pool, min(skill_count, len(skills_pool))):
            worker_skills.append(
                WorkerSkill(
                    worker_id=worker_id,
                    skill=skill,
                    proficiency=rng.choice(list(SkillProficiency)),
                )
            )
    return workers, worker_skills


def _build_customers(config: SimulatorConfig, rng: Random) -> list[Customer]:
    tiers = list(CustomerTier)
    customers: list[Customer] = []
    for i in range(config.num_customers):
        tier = rng.choice(tiers)
        customers.append(
            Customer(
                customer_id=f"CU-{i + 1:04d}",
                name=f"Customer {i + 1}",
                tier=tier,
                sla_days=rng.choice([3, 5, 7, 10, 14]),
                country=rng.choice(["US", "DE", "IN", "JP", "BR"]),
            )
        )
    return customers


def _build_suppliers(
    raw: list[Product], config: SimulatorConfig, rng: Random
) -> tuple[list[Supplier], dict[str, str]]:
    """Return suppliers and a mapping of ``product_id -> supplier_id``."""
    suppliers: list[Supplier] = []
    for i in range(config.num_suppliers):
        suppliers.append(
            Supplier(
                supplier_id=f"SP-{i + 1:04d}",
                name=f"Supplier {i + 1}",
                lead_time_days=rng.choice([2, 3, 5, 7, 10]),
                reliability_score=round(rng.uniform(0.7, 0.99), 2),
                country=rng.choice(["US", "DE", "CN", "IN", "MX"]),
            )
        )
    supplier_for_material = {
        material.product_id: rng.choice(suppliers).supplier_id for material in raw
    }
    return suppliers, supplier_for_material


def _build_inventory(
    finished: list[Product], raw: list[Product], rng: Random
) -> list[InventoryItem]:
    inventory: list[InventoryItem] = []
    for product in finished:
        on_hand = float(rng.randint(0, 60))
        inventory.append(
            InventoryItem(
                product_id=product.product_id,
                on_hand=on_hand,
                allocated=float(rng.randint(0, int(on_hand))) if on_hand else 0.0,
                safety_stock=10.0,
                reorder_point=20.0,
            )
        )
    for material in raw:
        on_hand = float(rng.randint(200, 2000))
        inventory.append(
            InventoryItem(
                product_id=material.product_id,
                on_hand=on_hand,
                allocated=float(rng.randint(0, int(on_hand * 0.3))),
                safety_stock=float(rng.randint(100, 300)),
                reorder_point=float(rng.randint(300, 600)),
            )
        )
    return inventory


def _build_purchase_orders(
    raw: list[Product],
    supplier_for_material: dict[str, str],
    suppliers: list[Supplier],
    business_date: date,
    config: SimulatorConfig,
    rng: Random,
) -> list[PurchaseOrder]:
    supplier_by_id = {supplier.supplier_id: supplier for supplier in suppliers}
    purchase_orders: list[PurchaseOrder] = []
    for i in range(config.initial_open_purchase_orders):
        material = rng.choice(raw)
        supplier_id = supplier_for_material[material.product_id]
        lead = supplier_by_id[supplier_id].lead_time_days
        order_date = business_date - timedelta(days=rng.randint(0, 3))
        purchase_orders.append(
            PurchaseOrder(
                po_id=f"PO-{i + 1:04d}",
                supplier_id=supplier_id,
                product_id=material.product_id,
                quantity=float(rng.randint(200, 1500)),
                order_date=order_date,
                expected_arrival=order_date + timedelta(days=lead),
                status=rng.choice(
                    [
                        PurchaseOrderStatus.CONFIRMED,
                        PurchaseOrderStatus.IN_TRANSIT,
                        PurchaseOrderStatus.OPEN,
                    ]
                ),
            )
        )
    return purchase_orders


def _build_production_orders(
    finished: list[Product],
    customers: list[Customer],
    business_date: date,
    config: SimulatorConfig,
    rng: Random,
) -> list[ProductionOrder]:
    orders: list[ProductionOrder] = []
    for i in range(config.initial_production_orders):
        product = rng.choice(finished)
        customer = rng.choice(customers)
        lead = rng.randint(config.order_lead_days_min, config.order_lead_days_max)
        release = business_date - timedelta(days=rng.randint(0, 2))
        orders.append(
            ProductionOrder(
                order_id=f"ORD-{i + 1:04d}",
                product_id=product.product_id,
                customer_id=customer.customer_id,
                quantity=rng.randint(
                    config.order_quantity_min, config.order_quantity_max
                ),
                release_date=release,
                due_date=business_date + timedelta(days=lead),
                priority=rng.randint(1, 10),
                status=OrderStatus.RELEASED,
            )
        )
    return orders


def _build_business_rules() -> list[BusinessRule]:
    return [
        BusinessRule(
            rule_id="BR-0001",
            rule_type=BusinessRuleType.PRIORITY_WEIGHT,
            enforcement=RuleEnforcement.SOFT,
            weight=2.0,
            parameters={"STRATEGIC": 4, "KEY": 3, "STANDARD": 2, "LOW": 1},
        ),
        BusinessRule(
            rule_id="BR-0002",
            rule_type=BusinessRuleType.DUE_DATE_ENFORCEMENT,
            enforcement=RuleEnforcement.SOFT,
            weight=3.0,
            parameters={"tardiness_penalty_per_day": 100},
        ),
        BusinessRule(
            rule_id="BR-0003",
            rule_type=BusinessRuleType.MAX_OVERTIME,
            enforcement=RuleEnforcement.HARD,
            parameters={"max_overtime_minutes_per_day": 120},
        ),
        BusinessRule(
            rule_id="BR-0004",
            rule_type=BusinessRuleType.SAFETY_STOCK,
            enforcement=RuleEnforcement.HARD,
            parameters={"respect_safety_stock": True},
        ),
    ]


def _build_plant_calendar(
    business_date: date, config: SimulatorConfig
) -> list[PlantCalendar]:
    calendar: list[PlantCalendar] = []
    for offset in range(config.planning_horizon_days):
        day = business_date + timedelta(days=offset)
        is_weekend = day.weekday() >= 5
        calendar.append(
            PlantCalendar(
                day=day,
                is_working_day=not is_weekend,
                holiday_name="Weekend" if is_weekend else None,
            )
        )
    return calendar


def generate_baseline(business_date: date, config: SimulatorConfig, rng: Random) -> FactoryState:
    """Generate a complete Day-0 :class:`FactoryState` for ``business_date``."""
    machines = _build_machines(config)
    finished, raw = _build_products(config)
    routings = _build_routings(finished, machines, config, rng)
    boms = _build_boms(finished, raw, config, rng)
    workers, worker_skills = _build_workforce(config, rng)
    customers = _build_customers(config, rng)
    suppliers, supplier_for_material = _build_suppliers(raw, config, rng)
    inventory = _build_inventory(finished, raw, rng)
    purchase_orders = _build_purchase_orders(
        raw, supplier_for_material, suppliers, business_date, config, rng
    )
    production_orders = _build_production_orders(
        finished, customers, business_date, config, rng
    )

    return FactoryState(
        business_date=format_business_date(business_date),
        production_orders=production_orders,
        customers=customers,
        products=[*finished, *raw],
        routings=routings,
        boms=boms,
        machines=machines,
        machine_availability=build_machine_availability(machines, business_date, config),
        machine_maintenance=[],
        workers=workers,
        worker_skills=worker_skills,
        worker_availability=build_worker_availability(workers, business_date),
        shifts=list(STANDARD_SHIFTS),
        shift_calendars=build_shift_calendars(business_date),
        plant_calendar=_build_plant_calendar(business_date, config),
        inventory=inventory,
        suppliers=suppliers,
        purchase_orders=purchase_orders,
        business_rules=_build_business_rules(),
    )
