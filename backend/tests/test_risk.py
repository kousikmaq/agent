"""Phase 8 tests: the risk detection engine.

Each test builds a minimal state + schedule that triggers a specific detector,
then asserts the corresponding risk type is reported.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.analytics import AnalyticsEngine
from app.domain.enums import (
    MaintenanceType,
    OrderStatus,
    RiskType,
    SolverStatus,
)
from app.domain.models.factory_state import FactoryState
from app.domain.models.inventory import InventoryItem
from app.domain.models.machine import Machine, MachineAvailability, MachineMaintenance
from app.domain.models.bom import BomLine
from app.domain.models.product import Product
from app.domain.models.production_order import ProductionOrder
from app.domain.models.purchase_order import PurchaseOrder
from app.domain.models.routing import Operation, Routing
from app.domain.models.schedule import ScheduledOperation, ScheduleResult
from app.domain.models.supplier import Supplier
from app.risk import RiskDetectionEngine

BIZ = date(2026, 7, 17)


def _order(order_id: str, due: date, qty: int = 10, product: str = "FG-1") -> ProductionOrder:
    return ProductionOrder(
        order_id=order_id,
        product_id=product,
        quantity=qty,
        release_date=BIZ,
        due_date=due,
        priority=5,
        status=OrderStatus.RELEASED,
    )


def _schedule(*ops: ScheduledOperation) -> ScheduleResult:
    base = datetime.combine(BIZ, time(0, 0))
    makespan = max((int((o.end - base).total_seconds() // 60) for o in ops), default=0)
    return ScheduleResult(
        business_date="2026-07-17",
        status=SolverStatus.OPTIMAL,
        scheduled_operations=list(ops),
        makespan_minutes=makespan,
    )


def _op(order_id, op_id, machine, start, end, worker=None) -> ScheduledOperation:
    return ScheduledOperation(
        order_id=order_id, operation_id=op_id, machine_id=machine,
        worker_id=worker, start=start, end=end,
    )


def _detect(state: FactoryState, schedule: ScheduleResult):
    kpis = AnalyticsEngine().compute(state, schedule)
    return RiskDetectionEngine().detect(state, schedule, kpis)


def _types(report) -> set:
    return {r.risk_type for r in report.risks}


def test_delayed_order_detected() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ)],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    schedule = _schedule(
        _op("ORD-1", "OP-1", "M-1", datetime(2026, 7, 18, 0, 0), datetime(2026, 7, 20, 0, 0))
    )
    assert RiskType.DELAYED_ORDER in _types(_detect(state, schedule))


def test_machine_overload_detected() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5))],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
        machine_availability=[
            MachineAvailability(
                machine_id="M-1", day=BIZ,
                available_from=datetime(2026, 7, 17, 6, 0),
                available_to=datetime(2026, 7, 17, 14, 0),  # 480 min
            )
        ],
    )
    # 600 busy minutes vs 480 available -> overloaded.
    schedule = _schedule(
        _op("ORD-1", "OP-1", "M-1", datetime(2026, 7, 17, 6, 0), datetime(2026, 7, 17, 16, 0))
    )
    assert RiskType.MACHINE_OVERLOAD in _types(_detect(state, schedule))


def test_capacity_shortage_detected() -> None:
    routing = Routing(
        routing_id="RT-1", product_id="FG-1",
        operations=[
            Operation(
                operation_id="OP-1", routing_id="RT-1", sequence=1, name="Heavy",
                work_center="WC", run_minutes_per_unit=100.0, eligible_machine_ids=["M-1"],
            )
        ],
    )
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5), qty=20)],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[routing],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC",
                          capacity_minutes_per_day=1440)],
    )
    # Demand 20 * 100 = 2000 min > 1440 available -> shortage.
    report = _detect(state, _schedule())
    assert RiskType.CAPACITY_SHORTAGE in _types(report)


def test_material_shortage_detected() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5), qty=100)],
        products=[
            Product(product_id="FG-1", name="W", routing_id="RT-1"),
            Product(product_id="RM-1", name="Steel", is_purchased=True),
        ],
        boms=[BomLine(parent_product_id="FG-1", component_product_id="RM-1", quantity_per=4)],
        inventory=[InventoryItem(product_id="RM-1", on_hand=10)],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    # Demand 100 * 4 = 400 vs supply 10 -> shortage.
    assert RiskType.MATERIAL_SHORTAGE in _types(_detect(state, _schedule()))


def test_safety_stock_breach_detected() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        inventory=[
            InventoryItem(product_id="RM-1", on_hand=5, allocated=0,
                          safety_stock=100, reorder_point=200)
        ],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    assert RiskType.INVENTORY_BELOW_SAFETY_STOCK in _types(_detect(state, _schedule()))


def test_unstaffed_operation_is_worker_conflict() -> None:
    routing = Routing(
        routing_id="RT-1", product_id="FG-1",
        operations=[
            Operation(
                operation_id="OP-1", routing_id="RT-1", sequence=1, name="Cut",
                work_center="WC", run_minutes_per_unit=1.0,
                eligible_machine_ids=["M-1"], required_skill="SKILL_WC",
            )
        ],
    )
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5))],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[routing],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    # Scheduled without a worker despite requiring a skill.
    schedule = _schedule(
        _op("ORD-1", "OP-1", "M-1", datetime(2026, 7, 17, 6, 0),
            datetime(2026, 7, 17, 7, 0), worker=None)
    )
    assert RiskType.WORKER_CONFLICT in _types(_detect(state, schedule))


def test_maintenance_conflict_detected() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=5))],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
        machine_maintenance=[
            MachineMaintenance(
                maintenance_id="MT-1", machine_id="M-1",
                maintenance_type=MaintenanceType.PLANNED,
                start=datetime(2026, 7, 17, 6, 0), end=datetime(2026, 7, 17, 12, 0),
            )
        ],
    )
    # Operation overlaps the maintenance window on the same machine.
    schedule = _schedule(
        _op("ORD-1", "OP-1", "M-1", datetime(2026, 7, 17, 8, 0), datetime(2026, 7, 17, 10, 0))
    )
    assert RiskType.MAINTENANCE_CONFLICT in _types(_detect(state, schedule))


def test_clean_state_produces_no_risks() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1", due=BIZ + timedelta(days=10))],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
        machine_availability=[
            MachineAvailability(
                machine_id="M-1", day=BIZ,
                available_from=datetime(2026, 7, 17, 6, 0),
                available_to=datetime(2026, 7, 17, 22, 0),
            )
        ],
    )
    # Small on-time operation, no materials/inventory concerns.
    schedule = _schedule(
        _op("ORD-1", "OP-1", "M-1", datetime(2026, 7, 17, 6, 0), datetime(2026, 7, 17, 7, 0))
    )
    report = _detect(state, schedule)
    assert report.risks == []


def test_detection_is_deterministic() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        inventory=[InventoryItem(product_id="RM-1", on_hand=5, safety_stock=100)],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )
    schedule = _schedule()
    a = _detect(state, schedule)
    b = _detect(state, schedule)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
