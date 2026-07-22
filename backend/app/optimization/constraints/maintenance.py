"""Constraint: machine maintenance windows.

Maintenance (planned, preventive, corrective, or breakdown) blocks a machine
for a fixed time window. Each window becomes a fixed interval added to the
machine's no-overlap set, so no task can be scheduled on that machine during
maintenance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.optimization.cp_sat_model import SchedulingModel


def add_maintenance(model: "SchedulingModel") -> None:
    """Register maintenance windows as blocked machine intervals."""
    cp = model.model

    for window in model.state.machine_maintenance:
        if window.machine_id not in model.machines_by_id:
            continue
        start = max(0, model.to_minute(window.start))
        end = min(model.horizon, max(0, model.to_minute(window.end)))
        size = end - start
        if size <= 0:
            continue  # window fully in the past or zero-length

        blocked = cp.NewIntervalVar(
            start, size, end, f"maint_{window.maintenance_id}"
        )
        model.machine_blocked_intervals.setdefault(window.machine_id, []).append(blocked)
