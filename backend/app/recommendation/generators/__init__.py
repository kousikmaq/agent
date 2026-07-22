"""Recommendation generators.

Each generator is an independent, deterministic module exposing a
``generate(ctx, builder)`` function that maps specific risk types to concrete,
feasibility-checked recommendations. The engine runs them in a fixed order.
"""

from __future__ import annotations

from app.recommendation.generators import (
    alternate_machine,
    alternate_worker,
    approve_overtime,
    expedite_po,
    reschedule_maintenance,
    split_batch,
)

# Fixed, deterministic execution order.
GENERATORS = (
    alternate_machine.generate,
    alternate_worker.generate,
    split_batch.generate,
    reschedule_maintenance.generate,
    approve_overtime.generate,
    expedite_po.generate,
)

__all__ = ["GENERATORS"]
