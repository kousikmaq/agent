"""Phase 10 tests: the scenario planning engine.

Uses small instances that solve to OPTIMAL so scenario KPI comparisons are
stable and deterministic. Verifies transforms, comparison arithmetic, isolation
(no mutation of the original), and determinism.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.domain.enums import MachineStatus, OrderStatus, ScenarioType
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineAvailability
from app.domain.models.product import Product
from app.domain.models.production_order import ProductionOrder
from app.domain.models.routing import Operation, Routing
from app.domain.models.workforce import Worker, WorkerSkill
from app.optimization import SolverOptions
from app.rules import BusinessRulesEngine
from app.scenario import ScenarioPlanningEngine

BIZ = date(2026, 7, 17)


def _options() -> SolverOptions:
    return SolverOptions(max_time_seconds=10, num_search_workers=8, random_seed=42)


def _single_op_routing() -> Routing:
    return Routing(
        routing_id="RT-1",
        product_id="FG-1",
        operations=[
            Operation(
                operation_id="OP-1",
                routing_id="RT-1",
                sequence=1,
                name="Cut",
                work_center="WC",
                run_minutes_per_unit=10.0,
                eligible_machine_ids=["M-1", "M-2"],
            )
        ],
    )


def _order(order_id: str) -> ProductionOrder:
    return ProductionOrder(
        order_id=order_id,
        product_id="FG-1",
        quantity=10,  # 100-minute operation
        release_date=BIZ,
        due_date=BIZ + timedelta(days=10),
        status=OrderStatus.RELEASED,
    )


def _plan(state: FactoryState):
    policy = BusinessRulesEngine().evaluate(state)
    return ScenarioPlanningEngine(options=_options()).plan(state, policy)


def _result(comparison, scenario_type: ScenarioType):
    return next(r for r in comparison.results if r.scenario_type is scenario_type)


def test_comparison_has_all_scenarios_and_baseline() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1")],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[_single_op_routing()],
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
    )
    comparison = _plan(state)
    types = {r.scenario_type for r in comparison.results}
    assert types == {
        ScenarioType.CURRENT_PLAN,
        ScenarioType.OVERTIME_ENABLED,
        ScenarioType.ALTERNATE_MACHINES,
        ScenarioType.ADDITIONAL_SHIFT,
    }
    assert comparison.baseline_type is ScenarioType.CURRENT_PLAN
    baseline = _result(comparison, ScenarioType.CURRENT_PLAN)
    assert baseline.is_baseline is True
    # Baseline delta is zero by construction.
    assert all(v == 0 for v in comparison.kpi_deltas["Current Plan"].values())


def test_additional_shift_reduces_makespan_via_parallelism() -> None:
    # One machine, two orders -> baseline must serialise them.
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1"), _order("ORD-2")],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[
            Routing(
                routing_id="RT-1", product_id="FG-1",
                operations=[
                    Operation(
                        operation_id="OP-1", routing_id="RT-1", sequence=1, name="Cut",
                        work_center="WC", run_minutes_per_unit=10.0,
                        eligible_machine_ids=["M-1"],
                    )
                ],
            )
        ],
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
    )
    comparison = _plan(state)
    baseline = _result(comparison, ScenarioType.CURRENT_PLAN)
    additional = _result(comparison, ScenarioType.ADDITIONAL_SHIFT)
    assert additional.kpis["makespan_minutes"] < baseline.kpis["makespan_minutes"]


def test_alternate_machines_restores_down_machine() -> None:
    # M-2 is down; baseline can only use M-1 (serial). Alternate machines
    # brings M-2 back, enabling parallel execution.
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1"), _order("ORD-2")],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[_single_op_routing()],
        machines=[
            Machine(machine_id="M-1", name="A", work_center="WC"),
            Machine(machine_id="M-2", name="B", work_center="WC", status=MachineStatus.DOWN),
        ],
        machine_availability=[
            MachineAvailability(
                machine_id="M-1", day=BIZ,
                available_from=datetime.combine(BIZ, time(0, 0)),
                available_to=datetime.combine(BIZ, time(23, 59)),
            )
        ],
    )
    comparison = _plan(state)
    baseline = _result(comparison, ScenarioType.CURRENT_PLAN)
    alternate = _result(comparison, ScenarioType.ALTERNATE_MACHINES)
    assert alternate.kpis["makespan_minutes"] < baseline.kpis["makespan_minutes"]


def test_overtime_enables_earlier_start() -> None:
    # Availability starts at 06:00; overtime brings it to 00:00, so the single
    # operation can start (and finish) earlier.
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1")],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[_single_op_routing()],
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
        machine_availability=[
            MachineAvailability(
                machine_id="M-1", day=BIZ,
                available_from=datetime.combine(BIZ, time(6, 0)),
                available_to=datetime.combine(BIZ, time(22, 0)),
            )
        ],
    )
    comparison = _plan(state)
    baseline = _result(comparison, ScenarioType.CURRENT_PLAN)
    overtime = _result(comparison, ScenarioType.OVERTIME_ENABLED)
    assert overtime.kpis["makespan_minutes"] < baseline.kpis["makespan_minutes"]


def test_transforms_do_not_mutate_original_state() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1")],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[_single_op_routing()],
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
    )
    original_machine_count = len(state.machines)
    _plan(state)
    # Additional-shift transform adds machines only to its own clone.
    assert len(state.machines) == original_machine_count


def test_scenario_planning_is_deterministic() -> None:
    state = FactoryState(
        business_date="2026-07-17",
        production_orders=[_order("ORD-1")],
        products=[Product(product_id="FG-1", name="W", routing_id="RT-1")],
        routings=[_single_op_routing()],
        machines=[Machine(machine_id="M-1", name="A", work_center="WC")],
    )
    a = _plan(state)
    b = _plan(state)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
