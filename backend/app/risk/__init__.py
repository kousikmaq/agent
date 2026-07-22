"""Risk Detection Engine.

Deterministic detectors for machine overload, capacity/material shortages,
safety-stock breaches, worker conflicts, delayed orders, and maintenance
conflicts. Consumes the schedule + analytics + factory snapshot and produces an
immutable :class:`~app.domain.models.risk.RiskReport`. No ML, no LLM.
"""

from __future__ import annotations

from app.risk.engine import RiskDetectionEngine
from app.risk.result import RiskBuilder, RiskContext, build_risk_context

__all__ = [
    "RiskDetectionEngine",
    "RiskContext",
    "RiskBuilder",
    "build_risk_context",
]
