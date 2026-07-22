"""Phase 6 tests: the OR-Tools CP-SAT optimization engine.

Uses small, hand-built factory states that solve to OPTIMAL quickly and
deterministically, verifying each constraint family (precedence, machine
no-overlap, availability, maintenance, workforce) and determinism.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from app.domain.enums import (
    MaintenanceType,
    OrderStatus,
    SolverStatus,
)
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineAvailability, MachineMaintenance
from app.domain.models.product import Product
from app.domain.models.production_order import ProductionOrder
from app.domain.models.routing import Operation, Routing
from app.domain.models.workforce import Worker, WorkerSkill
from app.optimization import SchedulingSolver, SolverOptions
from app.rules import BusinessRulesEngine

BIZ_DATE = date(2026, 7, 17)
BASE = datetime.combine(BIZ_DATE, time(0, 0))


def _fast_options(**overrides) -> SolverOptions:
    opts = dict(max_time_seconds=10, num_search_workers=8, random_seed=42)
    opts.update(overrides)
    return SolverOptions(**opts)


def _two_op_state(*, with_availability: bool = True, maintenance=None) -> FactoryState:
    """A single order with a 2-operation routing across two machines/workers."""
    routing = Routing(
        routing_id="RT-1",
        product_id="FG-1",
        operations=[
            Operation(
                operation_id="OP-1",
                routing_id="RT-1",
                sequence=1,
                name="Cut",
                work_center="CUTTING",
                setup_minutes=10,
                run_minutes_per_unit=1.0,
                eligible_machine_ids=["M-1"],
                required_skill="SKILL_CUTTING",
            ),
            Operation(
                operation_id="OP-2",
                routing_id="RT-1",
                sequence=2,
                name="Weld",
                work_center="WELDING",
                setup_minutes=5,
                run_minutes_per_unit=2.0,
                eligible_machine_ids=["M-2"],
                required_skill="SKILL_WELDING",
            ),
        ],
    )
    availability = []
    if with_availability:
        for machine_id in ("M-1", "M-2"):
            availability.append(
                MachineAvailability(
                    machine_id=machine_id,
                    day=BIZ_DATE,
                    available_from=datetime.combine(BIZ_DATE, time(6, 0)),
                    available_to=datetime.combine(BIZ_DATE, time(22, 0)),
                )
            )
    return FactoryState(
        business_date="2026-07-17",
        production_orders=[
            ProductionOrder(
                order_id="ORD-1",
                product_id="FG-1",
                quantity=10,
                release_date=BIZ_DATE,
                due_date=BIZ_DATE + timedelta(days=5),
                priority=5,
                status=OrderStatus.RELEASED,
            )
        ],
        products=[Product(product_id="FG-1", name="Widget", routing_id="RT-1")],
        routings=[routing],
        machines=[
            Machine(machine_id="M-1", name="Cutter", work_center="CUTTING"),
            Machine(machine_id="M-2", name="Welder", work_center="WELDING"),
        ],
        machine_availability=availability,
        machine_maintenance=maintenance or [],
        workers=[
            Worker(worker_id="W-1", name="Alice"),
            Worker(worker_id="W-2", name="Bob"),
        ],
        worker_skills=[
            WorkerSkill(worker_id="W-1", skill="SKILL_CUTTING"),
            WorkerSkill(worker_id="W-2", skill="SKILL_WELDING"),
        ],
    )


def _solve(state: FactoryState, options: SolverOptions | None = None):
    policy = BusinessRulesEngine().evaluate(state)
    return SchedulingSolver(options or _fast_options()).solve(state, policy)


def _op(result, operation_id):
    return next(o for o in result.scheduled_operations if o.operation_id == operation_id)


def test_solves_to_optimal_and_schedules_all_operations() -> None:
    result = _solve(_two_op_state())
    assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert len(result.scheduled_operations) == 2


def test_precedence_is_respected() -> None:
    result = _solve(_two_op_state())
    assert _op(result, "OP-2").start >= _op(result, "OP-1").end


def test_machines_and_workers_are_assigned() -> None:
    result = _solve(_two_op_state())
    op1, op2 = _op(result, "OP-1"), _op(result, "OP-2")
    assert op1.machine_id == "M-1" and op2.machine_id == "M-2"
    assert op1.worker_id == "W-1" and op2.worker_id == "W-2"


def test_machine_availability_earliest_start_respected() -> None:
    result = _solve(_two_op_state(with_availability=True))
    six_am = datetime.combine(BIZ_DATE, time(6, 0))
    assert all(op.start >= six_am for op in result.scheduled_operations)


def test_maintenance_window_is_avoided() -> None:
    # Block M-1 for the morning; OP-1 must not overlap the window.
    maint = [
        MachineMaintenance(
            maintenance_id="MT-1",
            machine_id="M-1",
            maintenance_type=MaintenanceType.PLANNED,
            start=datetime.combine(BIZ_DATE, time(6, 0)),
            end=datetime.combine(BIZ_DATE, time(12, 0)),
        )
    ]
    result = _solve(_two_op_state(maintenance=maint))
    op1 = _op(result, "OP-1")
    window_start = datetime.combine(BIZ_DATE, time(6, 0))
    window_end = datetime.combine(BIZ_DATE, time(12, 0))
    # No overlap between the operation and the maintenance window.
    assert op1.end <= window_start or op1.start >= window_end


def test_no_two_operations_overlap_on_same_machine() -> None:
    # Two orders competing for the same machines.
    state = _two_op_state()
    second = state.production_orders[0].model_copy(update={"order_id": "ORD-2"})
    state.production_orders.append(second)
    result = _solve(state)

    by_machine: dict[str, list] = {}
    for op in result.scheduled_operations:
        by_machine.setdefault(op.machine_id, []).append((op.start, op.end))
    for intervals in by_machine.values():
        intervals.sort()
        for (_, prev_end), (next_start, _) in zip(intervals, intervals[1:]):
            assert next_start >= prev_end


def test_workforce_can_be_disabled() -> None:
    result = _solve(_two_op_state(), _fast_options(enable_workforce=False))
    assert all(op.worker_id is None for op in result.scheduled_operations)


def test_solution_is_deterministic() -> None:
    state = _two_op_state()
    a = _solve(state)
    b = _solve(state)
    # Compare the schedule itself; wall-clock solve time naturally varies.
    a_dump = a.model_dump(mode="json", exclude={"solve_time_seconds"})
    b_dump = b.model_dump(mode="json", exclude={"solve_time_seconds"})
    assert a_dump == b_dump


def test_empty_problem_returns_optimal_empty_schedule() -> None:
    state = _two_op_state()
    state.production_orders[0].status = OrderStatus.CANCELLED
    result = _solve(state)
    assert result.status is SolverStatus.OPTIMAL
    assert result.scheduled_operations == []
    assert result.makespan_minutes == 0
