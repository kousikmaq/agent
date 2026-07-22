"""Objective function.

Builds the weighted minimisation objective. On-time delivery is the goal, so the
primary terms penalise lateness: a fixed penalty per late order (maximising the
count of on-time orders) plus per-minute weighted tardiness (order priority x
customer tier x tardiness penalty). Makespan is a small secondary term
encouraging compact schedules. The objective is deterministic and contains no
ML.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel

_MINUTES_PER_DAY = 1440


def _tardiness_coefficient(model: "SchedulingModel", order_id: str) -> int:
    """Integer objective weight for one minute of an order's tardiness.

    Combines the order's resolved priority weight with the plant tardiness
    penalty (expressed per day, converted to a per-minute integer). A floor of
    1 ensures every order's lateness is always penalised.
    """
    weight = model.policy.order_priority_weights.get(order_id, 1.0)
    penalty_per_day = model.policy.tardiness_penalty_per_day
    coefficient = weight * penalty_per_day / _MINUTES_PER_DAY
    return max(1, round(coefficient))


def build_objective(model: "SchedulingModel") -> None:
    """Attach the on-time + weighted tardiness + makespan objective to the model."""
    terms = []

    # Primary goal: get orders delivered on time. A fixed penalty per late order
    # pushes the solver to maximise the number of fully on-time orders, weighted
    # by each order's priority so critical orders are protected first.
    late_weight = model.options.late_order_weight
    if late_weight > 0:
        for order_id, is_late in model.late_flags.items():
            priority = max(1, round(model.policy.order_priority_weights.get(order_id, 1.0)))
            terms.append(late_weight * priority * is_late)

    for order_id, tardiness in model.tardiness.items():
        terms.append(_tardiness_coefficient(model, order_id) * tardiness)

    if model.makespan is not None and model.options.makespan_weight > 0:
        terms.append(model.options.makespan_weight * model.makespan)

    if terms:
        model.model.Minimize(sum(terms))
