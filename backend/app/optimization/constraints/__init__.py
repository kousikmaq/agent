"""Modular CP-SAT constraint builders.

Each builder adds one family of constraints to a
:class:`~app.optimization.cp_sat_model.SchedulingModel`, keeping the model
readable, independently testable, and toggleable via solver options.
"""

from __future__ import annotations

from app.optimization.constraints.due_dates import add_due_dates
from app.optimization.constraints.machine_capacity import add_machine_capacity
from app.optimization.constraints.maintenance import add_maintenance
from app.optimization.constraints.material_availability import (
    add_material_availability,
)
from app.optimization.constraints.precedence import add_precedence
from app.optimization.constraints.shift_calendar import add_shift_calendar
from app.optimization.constraints.workforce_skills import add_workforce_skills

__all__ = [
    "add_precedence",
    "add_machine_capacity",
    "add_maintenance",
    "add_shift_calendar",
    "add_workforce_skills",
    "add_material_availability",
    "add_due_dates",
]
