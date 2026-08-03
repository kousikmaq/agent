"""Constraint: routing precedence.

Operations of the same production order must execute in their routing sequence:
each operation starts no earlier than the previous operation finishes. When an
operation is lot-split into parallel sub-lots (same sequence index), the whole
group is treated as one step: every sub-lot of the next operation waits for
*all* sub-lots of the previous operation to finish, while sub-lots within a step
run in parallel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_precedence(model: "SchedulingModel") -> None:
    """Chain each order's operation *steps* (sub-lots run in parallel)."""
    for order_tasks in model.tasks_by_order.values():
        by_step: dict[int, list] = {}
        for task in order_tasks:
            by_step.setdefault(task.sequence_index, []).append(task)
        steps = sorted(by_step)
        for previous_step, current_step in zip(steps, steps[1:]):
            for current in by_step[current_step]:
                for previous in by_step[previous_step]:
                    model.model.Add(current.start >= previous.end)

