"""Individual risk detectors.

Each detector is an independent, deterministic module exposing a
``detect(ctx, builder)`` function. The engine runs them in a fixed order.
"""

from __future__ import annotations

from app.risk.detectors import (
    capacity_shortage,
    delayed_orders,
    machine_overload,
    maintenance_conflict,
    material_shortage,
    safety_stock,
    worker_conflict,
)

# Fixed, deterministic execution order.
DETECTORS = (
    delayed_orders.detect,
    machine_overload.detect,
    capacity_shortage.detect,
    material_shortage.detect,
    safety_stock.detect,
    worker_conflict.detect,
    maintenance_conflict.detect,
)

__all__ = ["DETECTORS"]
