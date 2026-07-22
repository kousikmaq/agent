"""Daily operational event generators. Implemented in the simulator phase."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.models.factory_state import FactoryState
from simulator.change_log import SimulationContext
from simulator.events import (
    cancellations,
    capacity_changes,
    inventory_consumption,
    machine_breakdowns,
    maintenance,
    overtime,
    po_arrivals,
    priority_changes,
    production_orders,
    replenishment,
    shift_changes,
    supplier_delays,
    worker_leave,
)

# Callable signature every event module exposes.
EventApplier = Callable[[FactoryState, SimulationContext], None]

# Ordered daily pipeline. Order is deliberate: material inflows are settled
# before consumption and replenishment; resource disruptions are applied before
# demand changes so the resulting snapshot is internally consistent.
EVENT_PIPELINE: tuple[EventApplier, ...] = (
    po_arrivals.apply,
    supplier_delays.apply,
    inventory_consumption.apply,
    replenishment.apply,
    machine_breakdowns.apply,
    maintenance.apply,
    worker_leave.apply,
    shift_changes.apply,
    overtime.apply,
    cancellations.apply,
    priority_changes.apply,
    production_orders.apply,
    capacity_changes.apply,
)

__all__ = ["EVENT_PIPELINE", "EventApplier"]
