"""Risk Detection Agent.

A thin wrapper around the existing deterministic risk engine - no detection or
severity logic is duplicated here. Reads the FactoryState, ScheduleResult, and
KpiSet from the shared context, runs the existing engine, and stores the
resulting RiskReport back into the context.
"""

from __future__ import annotations

from collections import Counter

from app.agents.analytics_agent import KPIS_KEY
from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import RiskAgentOutput
from app.agents.data_agent import FACTORY_STATE_KEY
from app.agents.errors import CriticalAgentError
from app.agents.planning_agent import SCHEDULE_RESULT_KEY
from app.agents.timing import Stopwatch
from app.domain.models.risk import RiskReport
from app.risk import RiskDetectionEngine

# Shared-context key for the produced risk report.
RISK_REPORT_KEY = "risk_report"


class RiskAgent(BaseAgent):
    """Detects operational risks via the existing deterministic engine."""

    name = "risk_agent"

    def __init__(self, engine: RiskDetectionEngine | None = None) -> None:
        self._engine = engine or RiskDetectionEngine()

    def execute(self, context: WorkflowContext) -> RiskAgentOutput:
        schedule = context.shared.get(SCHEDULE_RESULT_KEY)
        kpis = context.shared.get(KPIS_KEY)
        if schedule is None:
            raise CriticalAgentError(
                "No ScheduleResult in context; the Planning Agent must run first."
            )
        if kpis is None:
            raise CriticalAgentError(
                "No KpiSet in context; the Analytics Agent must run first."
            )
        state = context.shared.get(FACTORY_STATE_KEY)
        if state is None:
            raise CriticalAgentError(
                "No FactoryState in context; the Data Agent must run first."
            )

        with Stopwatch() as sw:
            report = self._engine.detect(state, schedule, kpis)

        context.shared[RISK_REPORT_KEY] = report
        self._log_report(report, sw.elapsed_ms)
        return RiskAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            risks=report,
        )

    def _log_report(self, report: RiskReport, duration_ms: float) -> None:
        by_severity = Counter(str(r.severity) for r in report.risks)
        categories = sorted({str(r.risk_type) for r in report.risks})
        machines: set[str] = set()
        workers: set[str] = set()
        orders: set[str] = set()
        for risk in report.risks:
            machines.update(risk.affected_entities.get("machine_ids", []))
            workers.update(risk.affected_entities.get("worker_ids", []))
            orders.update(risk.affected_entities.get("order_ids", []))

        self.logger.info(
            "Risk detection in %.1f ms | total=%d critical=%d high=%d medium=%d "
            "low=%d categories=%s affected_machines=%d affected_workers=%d "
            "affected_orders=%d",
            duration_ms,
            len(report.risks),
            by_severity.get("CRITICAL", 0),
            by_severity.get("HIGH", 0),
            by_severity.get("MEDIUM", 0),
            by_severity.get("LOW", 0),
            categories,
            len(machines),
            len(workers),
            len(orders),
        )
