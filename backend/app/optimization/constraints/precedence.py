"""Constraint: routing precedence.

Operations of the same production order must execute in their routing sequence:
each operation starts no earlier than the previous operation finishes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_precedence(model: "SchedulingModel") -> None:
    """Chain each order's operations in routing order."""
    for order_tasks in model.tasks_by_order.values():
        ordered = sorted(order_tasks, key=lambda task: task.sequence_index)
        for previous, current in zip(ordered, ordered[1:]):
            model.model.Add(current.start >= previous.end)
