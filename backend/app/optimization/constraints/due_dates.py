"""Constraint: due dates and tardiness.

Defines a non-negative tardiness variable per order (minutes late beyond the end
of its due date). The objective minimises weighted tardiness; when the resolved
policy marks due dates HARD and the solver options allow it, completion is also
constrained not to exceed the due date.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.enums import RuleEnforcement

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_due_dates(model: "SchedulingModel") -> None:
    """Create tardiness variables and optional hard due-date constraints."""
    cp = model.model
    hard = (
        model.options.enforce_hard_due_dates
        and model.policy.due_date_enforcement is RuleEnforcement.HARD
    )

    for order_id, completion in model.order_completion.items():
        order_tasks = model.tasks_by_order[order_id]
        due_minute = model.date_to_minute(
            order_tasks[0].order.due_date, end_of_day=True
        )

        tardiness = cp.NewIntVar(0, model.horizon, f"tardiness_{order_id}")
        # tardiness >= completion - due (>= 0 enforced by the variable domain).
        cp.Add(tardiness >= completion - due_minute)
        model.tardiness[order_id] = tardiness

        # A reified "is this order late?" flag so the objective can maximise the
        # count of on-time orders (the primary delivery goal), not just minimise
        # total lateness minutes.
        is_late = cp.NewBoolVar(f"late_{order_id}")
        cp.Add(tardiness >= 1).OnlyEnforceIf(is_late)
        cp.Add(tardiness == 0).OnlyEnforceIf(is_late.Not())
        model.late_flags[order_id] = is_late

        if hard:
            cp.Add(completion <= due_minute)
