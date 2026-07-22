"""CP-SAT model construction.

Builds the constraint-programming model for one production day's schedule.
``SchedulingModel`` owns all decision variables and shared lookups; the actual
constraint relationships are delegated to the modular builders in
:mod:`app.optimization.constraints` and the objective to
:mod:`app.optimization.objectives`. The model is fully deterministic - no ML,
no randomness beyond the fixed solver seed.

Time is modelled in integer minutes measured from midnight of the business
date (the ``base`` datetime).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time

from ortools.sat.python import cp_model

from app.core.logging import get_logger
from app.domain.enums import MachineStatus, OrderStatus, WorkerAvailabilityStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.production_order import ProductionOrder
from app.domain.models.routing import Operation
from app.optimization.config import SolverOptions
from app.rules.policy import RulePolicy
from app.utils.datetime_utils import parse_business_date

logger = get_logger(__name__)

# Order statuses that are eligible for scheduling.
_SCHEDULABLE_STATUSES = {
    OrderStatus.PLANNED,
    OrderStatus.RELEASED,
    OrderStatus.IN_PROGRESS,
}

_MINUTES_PER_DAY = 1440


@dataclass
class Task:
    """A single (order, operation) unit of work with its decision variables."""

    order: ProductionOrder
    operation: Operation
    sequence_index: int
    duration: int
    start: cp_model.IntVar
    end: cp_model.IntVar
    interval: cp_model.IntervalVar
    machine_presence: dict[str, cp_model.IntVar] = field(default_factory=dict)
    worker_presence: dict[str, cp_model.IntVar] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.order.order_id, self.operation.operation_id)


class SchedulingModel:
    """Assembles the CP-SAT model, variables, constraints, and objective."""

    def __init__(
        self, state: FactoryState, policy: RulePolicy, options: SolverOptions
    ) -> None:
        self.state = state
        self.policy = policy
        self.options = options
        self.model = cp_model.CpModel()

        self.business_date: date = parse_business_date(state.business_date)
        self.base: datetime = datetime.combine(self.business_date, time(0, 0))

        # Populated during build().
        self.tasks: list[Task] = []
        self.tasks_by_order: dict[str, list[Task]] = {}
        self.machine_optional_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self.machine_blocked_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self.worker_optional_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self.order_completion: dict[str, cp_model.IntVar] = {}
        self.tardiness: dict[str, cp_model.IntVar] = {}
        self.late_flags: dict[str, cp_model.IntVar] = {}
        self.makespan: cp_model.IntVar | None = None
        self.horizon: int = _MINUTES_PER_DAY
        self.warnings: list[str] = []

        self._prepare_lookups()

    # -- Time helpers -------------------------------------------------------
    def to_minute(self, moment: datetime) -> int:
        """Convert an absolute datetime to integer minutes from the base."""
        return int((moment - self.base).total_seconds() // 60)

    def date_to_minute(self, day: date, *, end_of_day: bool = False) -> int:
        """Convert a calendar date to minutes from base (optionally day end)."""
        minutes = self.to_minute(datetime.combine(day, time(0, 0)))
        return minutes + (_MINUTES_PER_DAY if end_of_day else 0)

    # -- Lookups ------------------------------------------------------------
    def _prepare_lookups(self) -> None:
        self.routing_by_product = {r.product_id: r for r in self.state.routings}
        self.machines_by_id = {m.machine_id: m for m in self.state.machines}

        # A machine is usable if it is not fully down.
        self.usable_machines = {
            m.machine_id
            for m in self.state.machines
            if m.status != MachineStatus.DOWN
        }

        # Batch-processing machines: those in configured batch work centers.
        # At these machines several compatible operations run in one batch.
        self.batch_machines: set[str] = set()
        if self.options.enable_batching:
            batch_centers = set(self.options.batch_work_centers)
            self.batch_machines = {
                m.machine_id
                for m in self.state.machines
                if m.work_center in batch_centers
            }

        # Earliest minute each machine becomes available (from availability
        # windows on the business date); default to the day start.
        self.machine_avail_start: dict[str, int] = {}
        for window in self.state.machine_availability:
            minute = max(0, self.to_minute(window.available_from))
            current = self.machine_avail_start.get(window.machine_id)
            self.machine_avail_start[window.machine_id] = (
                minute if current is None else min(current, minute)
            )

        # Workers unavailable on the business date (leave/sick/training).
        unavailable = {
            record.worker_id
            for record in self.state.worker_availability
            if record.day == self.business_date
            and record.status != WorkerAvailabilityStatus.AVAILABLE
        }
        available_worker_ids = {
            w.worker_id for w in self.state.workers if w.worker_id not in unavailable
        }

        # Skill -> available qualified workers.
        self.skill_to_workers: dict[str, list[str]] = {}
        for skill in self.state.worker_skills:
            if skill.worker_id in available_worker_ids:
                self.skill_to_workers.setdefault(skill.skill, []).append(
                    skill.worker_id
                )

    # -- Eligibility --------------------------------------------------------
    def eligible_machines(self, operation: Operation) -> list[str]:
        """Return the machine ids an operation may run on, after policy/usability."""
        override = self.policy.machine_eligibility_overrides.get(operation.operation_id)
        base_ids = override if override is not None else operation.eligible_machine_ids

        usable = [m for m in base_ids if m in self.usable_machines]
        if usable:
            return usable
        # Fallback: keep original eligibility to preserve feasibility.
        if base_ids:
            self.warnings.append(
                f"Operation {operation.operation_id}: no usable eligible machine; "
                "retaining full eligibility to remain feasible."
            )
            return list(base_ids)
        return []

    def eligible_workers(self, operation: Operation) -> list[str]:
        """Return available workers qualified for an operation's required skill."""
        if not operation.required_skill:
            return []
        return list(self.skill_to_workers.get(operation.required_skill, []))

    # -- Build --------------------------------------------------------------
    def build(self) -> "SchedulingModel":
        """Create variables and apply every constraint family and the objective."""
        # Imported here to keep module import order simple and avoid cycles.
        from app.optimization.constraints import (
            add_due_dates,
            add_machine_capacity,
            add_maintenance,
            add_material_availability,
            add_precedence,
            add_shift_calendar,
            add_workforce_skills,
        )
        from app.optimization.objectives import build_objective

        self._create_tasks()
        if not self.tasks:
            return self  # nothing to schedule

        if self.options.enable_maintenance:
            add_maintenance(self)
        add_machine_capacity(self)
        add_shift_calendar(self)
        if self.options.enable_workforce:
            add_workforce_skills(self)
        add_precedence(self)
        if self.options.enable_materials:
            add_material_availability(self)
        add_due_dates(self)

        build_objective(self)
        return self

    def _duration_minutes(self, operation: Operation, quantity: int) -> int:
        """Deterministic processing time for an operation at a given quantity."""
        run = math.ceil(operation.run_minutes_per_unit * quantity)
        return max(1, operation.setup_minutes + run)

    def _create_tasks(self) -> None:
        """Create one task (with time variables) per schedulable operation."""
        # First pass: gather durations to bound the horizon.
        planned: list[tuple[ProductionOrder, Operation, int, int, int]] = []
        max_release = 0
        for order in self.state.production_orders:
            if order.status not in _SCHEDULABLE_STATUSES:
                continue
            routing = self.routing_by_product.get(order.product_id)
            if routing is None or not routing.operations:
                self.warnings.append(
                    f"Order {order.order_id}: no routing for product "
                    f"{order.product_id}; skipped."
                )
                continue
            release = max(0, self.date_to_minute(order.release_date))
            max_release = max(max_release, release)
            for index, operation in enumerate(routing.operations):
                duration = self._duration_minutes(operation, order.quantity)
                planned.append((order, operation, index, duration, release))

        if not planned:
            return

        total_duration = sum(item[3] for item in planned)
        max_due = 0
        for order in self.state.production_orders:
            if order.status in _SCHEDULABLE_STATUSES:
                max_due = max(max_due, self.date_to_minute(order.due_date, end_of_day=True))
        max_maint_end = 0
        for window in self.state.machine_maintenance:
            max_maint_end = max(max_maint_end, max(0, self.to_minute(window.end)))

        self.horizon = (
            max(max_due, max_release + total_duration, max_maint_end)
            + total_duration
            + _MINUTES_PER_DAY
        )

        # Second pass: create the decision variables.
        for order, operation, index, duration, release in planned:
            start = self.model.NewIntVar(release, self.horizon, f"start_{order.order_id}_{operation.operation_id}")
            end = self.model.NewIntVar(0, self.horizon, f"end_{order.order_id}_{operation.operation_id}")
            interval = self.model.NewIntervalVar(
                start, duration, end, f"iv_{order.order_id}_{operation.operation_id}"
            )
            task = Task(
                order=order,
                operation=operation,
                sequence_index=index,
                duration=duration,
                start=start,
                end=end,
                interval=interval,
            )
            self.tasks.append(task)
            self.tasks_by_order.setdefault(order.order_id, []).append(task)

        # Order completion + makespan variables.
        self.makespan = self.model.NewIntVar(0, self.horizon, "makespan")
        for order_id, order_tasks in self.tasks_by_order.items():
            completion = self.model.NewIntVar(0, self.horizon, f"completion_{order_id}")
            for task in order_tasks:
                self.model.Add(completion >= task.end)
            self.order_completion[order_id] = completion
            self.model.Add(self.makespan >= completion)
