"""Constraint: workforce assignment and skills.

Operations that require a skill are staffed by exactly one available, qualified
worker, and no worker may perform two tasks at once. Assignment mirrors the
machine model (presence literal + shared optional interval + per-worker
no-overlap). Operations whose required skill has no available worker are left
unstaffed (recorded as a warning) so the model stays feasible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_workforce_skills(model: "SchedulingModel") -> None:
    """Add worker assignment variables and per-worker no-overlap."""
    cp = model.model

    for task in model.tasks:
        if not task.operation.required_skill:
            continue
        workers = model.eligible_workers(task.operation)
        if not workers:
            model.warnings.append(
                f"Operation {task.operation.operation_id} (order "
                f"{task.order.order_id}) requires skill "
                f"{task.operation.required_skill} with no available worker; "
                "scheduled without a worker assignment."
            )
            continue

        presence_literals = []
        for worker_id in workers:
            presence = cp.NewBoolVar(
                f"wasg_{task.order.order_id}_{task.operation.operation_id}_{worker_id}"
            )
            optional = cp.NewOptionalIntervalVar(
                task.start,
                task.duration,
                task.end,
                presence,
                f"wopt_{task.order.order_id}_{task.operation.operation_id}_{worker_id}",
            )
            task.worker_presence[worker_id] = presence
            model.worker_optional_intervals.setdefault(worker_id, []).append(optional)
            presence_literals.append(presence)

        cp.AddExactlyOne(presence_literals)

    for intervals in model.worker_optional_intervals.values():
        if len(intervals) > 1:
            cp.AddNoOverlap(intervals)
