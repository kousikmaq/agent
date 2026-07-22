"""Constraint: machine assignment and capacity (no-overlap / batching).

Each task is assigned to exactly one eligible machine. Assignment is modelled
with a presence literal per candidate machine and an optional interval that
shares the task's start/end.

Capacity is then enforced per machine:
- **Regular machines** run one task at a time (``NoOverlap``).
- **Batch-processing machines** (paint booth / QC chamber) run up to
  ``batch_capacity`` *compatible* operations at once: a per-machine
  ``AddCumulative`` caps concurrency, and operations of different product
  families are kept from overlapping so only same-family jobs share a batch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import OptimizationError
from app.optimization.batching import product_family

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_machine_capacity(model: "SchedulingModel") -> None:
    """Add machine assignment variables and per-machine capacity constraints."""
    cp = model.model

    # Per machine: optional interval + family for each candidate assignment.
    interval_family: dict[str, list[tuple[object, str]]] = {}

    for task in model.tasks:
        eligible = model.eligible_machines(task.operation)
        if not eligible:
            raise OptimizationError(
                f"Operation {task.operation.operation_id} has no eligible machine.",
                details={"order_id": task.order.order_id},
            )

        family = product_family(task.order.product_id)
        presence_literals = []
        for machine_id in eligible:
            presence = cp.NewBoolVar(f"asg_{task.order.order_id}_{task.operation.operation_id}_{machine_id}")
            optional = cp.NewOptionalIntervalVar(
                task.start,
                task.duration,
                task.end,
                presence,
                f"mopt_{task.order.order_id}_{task.operation.operation_id}_{machine_id}",
            )
            task.machine_presence[machine_id] = presence
            model.machine_optional_intervals.setdefault(machine_id, []).append(optional)
            interval_family.setdefault(machine_id, []).append((optional, family))
            presence_literals.append(presence)

        # Exactly one machine runs the task.
        cp.AddExactlyOne(presence_literals)

    # Per-machine capacity: no-overlap for regular machines, batching for batch
    # machines. Maintenance-blocked intervals (populated by the maintenance
    # constraint) block the whole machine either way.
    machine_ids = set(model.machine_optional_intervals) | set(model.machine_blocked_intervals)
    capacity = model.options.batch_capacity
    for machine_id in machine_ids:
        op_intervals = list(model.machine_optional_intervals.get(machine_id, []))
        blocked = list(model.machine_blocked_intervals.get(machine_id, []))

        if machine_id in model.batch_machines and capacity > 1:
            _add_batch_machine(
                model,
                machine_id,
                interval_family.get(machine_id, []),
                blocked,
                capacity,
                model.options.batch_same_family_only,
            )
            continue

        intervals = op_intervals + blocked
        if len(intervals) > 1:
            cp.AddNoOverlap(intervals)


def _add_batch_machine(
    model: "SchedulingModel",
    machine_id: str,
    intervals_with_family: list[tuple[object, str]],
    blocked: list[object],
    capacity: int,
    same_family_only: bool,
) -> None:
    """Constrain one batch machine: compatible jobs batch (up to capacity)."""
    cp = model.model
    op_intervals = [iv for iv, _ in intervals_with_family]

    # Cap concurrency to the batch capacity; maintenance fully blocks the
    # machine (demand == capacity), so no operation overlaps maintenance.
    if op_intervals or blocked:
        cp.AddCumulative(
            op_intervals + blocked,
            [1] * len(op_intervals) + [capacity] * len(blocked),
            capacity,
        )

    # Operations of different product families may not overlap, so only
    # same-family operations can share a batch window.
    if same_family_only:
        n = len(intervals_with_family)
        for i in range(n):
            iv_i, fam_i = intervals_with_family[i]
            for j in range(i + 1, n):
                iv_j, fam_j = intervals_with_family[j]
                if fam_i != fam_j:
                    cp.AddNoOverlap([iv_i, iv_j])


