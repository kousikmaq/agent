"""Scenario KPI comparison.

Extracts a fixed set of headline KPIs from each scenario's result and computes
deltas against the baseline (current plan), so scenarios can be compared side by
side. Purely arithmetic and deterministic.
"""

from __future__ import annotations

from app.domain.models.analytics import KpiSet
from app.domain.models.scenario import ScenarioResult

# The KPIs surfaced for scenario comparison (stable order).
SCENARIO_KPI_KEYS: tuple[str, ...] = (
    "on_time_delivery_rate",
    "average_machine_utilization",
    "total_tardiness_minutes",
    "makespan_minutes",
    "work_in_progress",
    "scheduled_orders",
    "cost_total",
    "cost_labor_regular",
    "cost_labor_overtime",
    "cost_machine",
    "cost_tardiness_penalty",
)


def extract_scenario_kpis(kpis: KpiSet) -> dict[str, float]:
    """Extract the comparable headline KPIs from a :class:`KpiSet`."""
    return {
        "on_time_delivery_rate": float(kpis.on_time_delivery_rate or 0.0),
        "average_machine_utilization": float(kpis.average_machine_utilization or 0.0),
        "total_tardiness_minutes": float(kpis.total_tardiness_minutes or 0),
        "makespan_minutes": float(kpis.metrics.get("makespan_minutes", 0.0)),
        "work_in_progress": float(kpis.work_in_progress or 0),
        "scheduled_orders": float(kpis.metrics.get("scheduled_orders", 0.0)),
        "cost_total": float(kpis.metrics.get("cost_total", 0.0)),
        "cost_labor_regular": float(kpis.metrics.get("cost_labor_regular", 0.0)),
        "cost_labor_overtime": float(kpis.metrics.get("cost_labor_overtime", 0.0)),
        "cost_machine": float(kpis.metrics.get("cost_machine", 0.0)),
        "cost_tardiness_penalty": float(
            kpis.metrics.get("cost_tardiness_penalty", 0.0)
        ),
    }


def compute_kpi_deltas(
    baseline: ScenarioResult, results: list[ScenarioResult]
) -> dict[str, dict[str, float]]:
    """Return per-scenario KPI deltas versus the baseline (scenario minus base)."""
    deltas: dict[str, dict[str, float]] = {}
    for result in results:
        scenario_deltas: dict[str, float] = {}
        for key in SCENARIO_KPI_KEYS:
            base_value = baseline.kpis.get(key, 0.0)
            value = result.kpis.get(key, 0.0)
            scenario_deltas[key] = round(value - base_value, 4)
        deltas[result.name] = scenario_deltas
    return deltas
