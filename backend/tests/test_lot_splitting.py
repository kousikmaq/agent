"""Tests: lot splitting — a prioritised order's operation runs on several
machines in parallel to finish sooner.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.domain.enums import OrderStatus, SolverStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine, MachineAvailability
from app.domain.models.product import Product
from app.domain.models.production_order import ProductionOrder
from app.domain.models.routing import Operation, Routing
from app.domain.models.workforce import Worker, WorkerSkill
from app.optimization import SchedulingSolver, SolverOptions
from app.rules import BusinessRulesEngine

BIZ_DATE = date(2026, 7, 17)
_MACHINES = ("MP-1", "MP-2", "MP-3")


def _options(**overrides) -> SolverOptions:
    opts = dict(max_time_seconds=10, num_search_workers=8, random_seed=42)
    opts.update(overrides)
    return SolverOptions(**opts)


def _pack_state(*, priority: int, quantity: int = 30) -> FactoryState:
    """One packing operation eligible on three machines, one order."""
    routing = Routing(
        routing_id="RT-P",
        product_id="FG-P",
        operations=[
            Operation(
                operation_id="OP-PACK",
                routing_id="RT-P",
                sequence=1,
                name="Packaging",
                work_center="PACKAGING",
                setup_minutes=5,
                run_minutes_per_unit=2.0,
                eligible_machine_ids=list(_MACHINES),
                required_skill="SKILL_PACKAGING",
            )
        ],
    )
    availability = [
        MachineAvailability(
            machine_id=mid,
            day=BIZ_DATE,
            available_from=datetime.combine(BIZ_DATE, time(6, 0)),
            available_to=datetime.combine(BIZ_DATE, time(22, 0)),
        )
        for mid in _MACHINES
    ]
    return FactoryState(
        business_date="2026-07-17",
        production_orders=[
            ProductionOrder(
                order_id="ORD-P",
                product_id="FG-P",
                quantity=quantity,
                release_date=BIZ_DATE,
                due_date=BIZ_DATE + timedelta(days=5),
                priority=priority,
                status=OrderStatus.RELEASED,
            )
        ],
        products=[Product(product_id="FG-P", name="Boxed Widget", routing_id="RT-P")],
        routings=[routing],
        machines=[Machine(machine_id=mid, name=mid, work_center="PACKAGING") for mid in _MACHINES],
        machine_availability=availability,
        workers=[Worker(worker_id=f"WP-{i}", name=f"Packer {i}") for i in range(1, 4)],
        worker_skills=[WorkerSkill(worker_id=f"WP-{i}", skill="SKILL_PACKAGING") for i in range(1, 4)],
    )


def _solve(state: FactoryState, options: SolverOptions | None = None):
    policy = BusinessRulesEngine().evaluate(state)
    return SchedulingSolver(options or _options()).solve(state, policy)


def _overlap(a, b) -> bool:
    return a.start < b.end and b.start < a.end


def test_prioritised_order_splits_across_parallel_machines() -> None:
    result = _solve(_pack_state(priority=10))
    assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    ops = [o for o in result.scheduled_operations if o.operation_id == "OP-PACK"]
    # Split into multiple sub-lots on DISTINCT machines.
    assert len(ops) >= 2
    machines = {o.machine_id for o in ops}
    assert len(machines) == len(ops)  # every sub-lot on its own machine
    # At least two sub-lots run at the same time (genuine parallelism).
    assert any(_overlap(ops[i], ops[j]) for i in range(len(ops)) for j in range(i + 1, len(ops)))


def test_split_finishes_sooner_than_single_machine() -> None:
    split = _solve(_pack_state(priority=10))
    single = _solve(_pack_state(priority=5))
    split_end = max(o.end for o in split.scheduled_operations)
    single_end = max(o.end for o in single.scheduled_operations)
    assert split_end < single_end


def test_non_prioritised_order_is_not_split() -> None:
    result = _solve(_pack_state(priority=5))
    ops = [o for o in result.scheduled_operations if o.operation_id == "OP-PACK"]
    assert len(ops) == 1


def test_lot_splitting_can_be_disabled() -> None:
    result = _solve(_pack_state(priority=10), _options(enable_lot_splitting=False))
    ops = [o for o in result.scheduled_operations if o.operation_id == "OP-PACK"]
    assert len(ops) == 1
