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
    sublot_index: int = 0
    sublot_count: int = 1

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
        # Sub-lot groups for lot-split operations (each inner list is the set of
        # parallel sub-lots of one prioritised operation).
        self.split_groups: list[list[Task]] = []
        self.machine_optional_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self.machine_blocked_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self.worker_optional_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self.order_completion: dict[str, cp_model.IntVar] = {}
        self.tardiness: dict[str, cp_model.IntVar] = {}
        self.late_flags: dict[str, cp_model.IntVar] = {}
        self.makespan: cp_model.IntVar | None = None
        # Named linear objective expressions, populated in build(); the solver
        # optimises a per-scenario ordered subset of these lexicographically.
        self.objective_terms: dict[str, object] = {}
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
        """Create variables and apply every constraint family.

        The objective itself is NOT fixed here: :meth:`_build_objective_terms`
        publishes named linear expressions and the solver minimises a
        per-scenario ordered subset of them lexicographically.
        """
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

        self._build_objective_terms()
        return self

    def _build_objective_terms(self) -> None:
        """Publish the named linear objective expressions used by scenarios.

        Each is a minimisation target (lower is better). Maximising on-time
        delivery is expressed as minimising ``num_late``.
        """
        cp = self.model
        total_duration = sum(task.duration for task in self.tasks) or 1

        # On-time delivery: count of late orders, and total tardiness minutes.
        self.objective_terms["num_late"] = (
            sum(self.late_flags.values()) if self.late_flags else 0
        )
        self.objective_terms["total_tardiness"] = (
            sum(self.tardiness.values()) if self.tardiness else 0
        )

        # Throughput / compactness.
        if self.makespan is not None:
            self.objective_terms["makespan"] = self.makespan
        self.objective_terms["total_flow"] = (
            sum(self.order_completion.values()) if self.order_completion else 0
        )

        # Machine load balance / bottleneck: minimise the busiest machine's
        # assigned processing time so work spreads across eligible machines.
        machine_load_terms: dict[str, list] = {}
        for task in self.tasks:
            for machine_id, presence in task.machine_presence.items():
                machine_load_terms.setdefault(machine_id, []).append(
                    task.duration * presence
                )
        max_load = cp.NewIntVar(0, total_duration, "max_machine_load")
        for terms in machine_load_terms.values():
            cp.Add(sum(terms) <= max_load)
        self.objective_terms["max_machine_load"] = max_load

        # Overtime minutes: labour assigned to a worker beyond their regular
        # daily capacity (a cost proxy; minimised so overtime is only "spent"
        # when a higher-priority objective — fewer late orders — required it).
        workers_by_id = {w.worker_id: w for w in self.state.workers}
        worker_task_terms: dict[str, list] = {}
        for task in self.tasks:
            for worker_id, presence in task.worker_presence.items():
                worker_task_terms.setdefault(worker_id, []).append(
                    task.duration * presence
                )
        overtime_vars = []
        for worker_id, terms in worker_task_terms.items():
            worker = workers_by_id.get(worker_id)
            cap = worker.max_regular_minutes_per_day if worker is not None else 480
            minutes = cp.NewIntVar(0, total_duration, f"wmin_{worker_id}")
            cp.Add(minutes == sum(terms))
            overtime = cp.NewIntVar(0, total_duration, f"wot_{worker_id}")
            cp.Add(overtime >= minutes - cap)
            overtime_vars.append(overtime)
        self.objective_terms["total_overtime"] = (
            sum(overtime_vars) if overtime_vars else 0
        )

    def _duration_minutes(self, operation: Operation, quantity: int) -> int:
        """Deterministic processing time for an operation at a given quantity."""
        run = math.ceil(operation.run_minutes_per_unit * quantity)
        return max(1, operation.setup_minutes + run)

    def _split_count(self, order: ProductionOrder, operation: Operation) -> int:
        """How many parallel machines to split this operation across.

        Returns 1 (no split) unless lot splitting is enabled AND the order is
        prioritised (priority at/above the threshold) AND the operation has at
        least two eligible, non-batch machines. Batch work centres (paint/QC)
        already parallelise via batching, so they are never lot-split. The count
        is capped by the configured maximum, the eligible-machine count and the
        order quantity (a sub-lot must make at least one unit).
        """
        if not self.options.enable_lot_splitting:
            return 1
        if order.priority < self.options.lot_split_priority_threshold:
            return 1
        eligible = self.eligible_machines(operation)
        if len(eligible) < 2 or any(mid in self.batch_machines for mid in eligible):
            return 1
        return max(
            1,
            min(self.options.lot_split_max_parallel, len(eligible), order.quantity),
        )

    def _create_tasks(self) -> None:
        """Create one task (with time variables) per schedulable operation.

        A prioritised order's operation may be split into several parallel
        sub-lots (see :meth:`_split_count`), each becoming its own task so the
        pieces can run on different machines at the same time.
        """
        # First pass: gather durations (expanding sub-lots) to bound the horizon.
        # Each entry: (order, operation, index, duration, release, group_key,
        #              sublot_index, sublot_count).
        planned: list[
            tuple[ProductionOrder, Operation, int, int, int, tuple[str, str] | None, int, int]
        ] = []
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
                splits = self._split_count(order, operation)
                if splits <= 1:
                    duration = self._duration_minutes(operation, order.quantity)
                    planned.append(
                        (order, operation, index, duration, release, None, 0, 1)
                    )
                    continue
                # Divide the quantity as evenly as possible across sub-lots.
                base_qty, remainder = divmod(order.quantity, splits)
                group_key = (order.order_id, operation.operation_id)
                for sub in range(splits):
                    share = base_qty + (1 if sub < remainder else 0)
                    duration = self._duration_minutes(operation, share)
                    planned.append(
                        (order, operation, index, duration, release, group_key, sub, splits)
                    )

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
        groups: dict[tuple[str, str], list[Task]] = {}
        for (
            order,
            operation,
            index,
            duration,
            release,
            group_key,
            sub_index,
            sub_count,
        ) in planned:
            suffix = f"{order.order_id}_{operation.operation_id}_{sub_index}"
            start = self.model.NewIntVar(release, self.horizon, f"start_{suffix}")
            end = self.model.NewIntVar(0, self.horizon, f"end_{suffix}")
            interval = self.model.NewIntervalVar(start, duration, end, f"iv_{suffix}")
            task = Task(
                order=order,
                operation=operation,
                sequence_index=index,
                duration=duration,
                start=start,
                end=end,
                interval=interval,
                sublot_index=sub_index,
                sublot_count=sub_count,
            )
            self.tasks.append(task)
            self.tasks_by_order.setdefault(order.order_id, []).append(task)
            if group_key is not None:
                groups.setdefault(group_key, []).append(task)

        self.split_groups = [g for g in groups.values() if len(g) > 1]

        # Order completion + makespan variables.
        self.makespan = self.model.NewIntVar(0, self.horizon, "makespan")
        for order_id, order_tasks in self.tasks_by_order.items():
            completion = self.model.NewIntVar(0, self.horizon, f"completion_{order_id}")
            for task in order_tasks:
                self.model.Add(completion >= task.end)
            self.order_completion[order_id] = completion
            self.model.Add(self.makespan >= completion)
