"""Risk Detection Engine.

Orchestrates the independent detectors over a shared, precomputed context and
assembles the immutable :class:`RiskReport`. Deterministic: detectors run in a
fixed order and each is a pure function of the inputs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from app.core.logging import get_logger
from app.domain.models.factory_state import FactoryState
from app.domain.models.risk import RiskReport
from app.domain.models.analytics import KpiSet
from app.domain.models.schedule import ScheduleResult
from app.risk.detectors import DETECTORS
from app.risk.result import RiskBuilder, RiskContext, build_risk_context

logger = get_logger(__name__)

Detector = Callable[[RiskContext, RiskBuilder], None]


class RiskDetectionEngine:
    """Runs the risk detectors and produces a :class:`RiskReport`."""

    def __init__(self, detectors: Iterable[Detector] | None = None) -> None:
        """Create the engine.

        Parameters
        ----------
        detectors:
            Optional override of the detector set (useful for testing or custom
            risk profiles). Defaults to the full :data:`DETECTORS` pipeline.
        """
        self._detectors: tuple[Detector, ...] = (
            tuple(detectors) if detectors is not None else DETECTORS
        )

    def detect(
        self, state: FactoryState, schedule: ScheduleResult, kpis: KpiSet
    ) -> RiskReport:
        """Detect all operational risks for a scheduled production day."""
        context = build_risk_context(state, schedule, kpis)
        builder = RiskBuilder(state.business_date)

        for detector in self._detectors:
            detector(context, builder)

        report = builder.build()
        logger.info(
            "Risk detection for %s produced %d risk(s).",
            state.business_date,
            len(report.risks),
        )
        return report
