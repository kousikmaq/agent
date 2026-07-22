"""Constraint: shift calendar / resource availability.

Ties task timing to when resources become available. A task assigned to a
machine cannot start before that machine's earliest availability on the day
(derived from its availability windows). Release-date lower bounds are already
encoded in each task's start-variable domain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_shift_calendar(model: "SchedulingModel") -> None:
    """Enforce machine earliest-start times based on availability windows."""
    cp = model.model

    for task in model.tasks:
        for machine_id, presence in task.machine_presence.items():
            earliest = model.machine_avail_start.get(machine_id)
            if earliest is None or earliest <= 0:
                continue
            # If this machine is chosen, the task cannot start before it opens.
            cp.Add(task.start >= earliest).OnlyEnforceIf(presence)
