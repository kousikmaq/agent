"""Read-only analysis tools shared by the MAF agents and the deterministic router.
Each returns a JSON-serializable dict. Actions with side-effects are NOT here - they are
executed only via confirmed API endpoints (human-in-the-loop)."""
from __future__ import annotations

from app.analytics.allocation import allocate_resources
from app.analytics.bottleneck import detect_bottlenecks
from app.analytics.capacity import capacity_analysis
from app.analytics.prioritization import prioritize_orders
from app.ml import explain, registry
from app.optimization.scheduler import compare_scenarios, optimize_schedule


def tool_capacity_analysis(horizon_days: int = 7) -> dict:
    """Analyse machine capacity vs required load over the next N days. Use for questions about
    capacity, utilisation, or whether the plant can cope with the workload."""
    return capacity_analysis(horizon_days)


def tool_detect_bottlenecks(horizon_days: int = 7) -> dict:
    """Find the machines that are the biggest bottlenecks (high load, queue, downtime)."""
    return detect_bottlenecks(horizon_days)


def tool_prioritize_orders(top_n: int = 10) -> dict:
    """Rank the most important pending orders by due-date urgency, priority and value."""
    return prioritize_orders(top_n)


def tool_allocate_resources() -> dict:
    """Assess workforce skill coverage of pending work and recommend worker assignments."""
    return allocate_resources()


def tool_optimize_schedule(scenario: str = "min_risk", max_orders: int = 12) -> dict:
    """Generate an optimized production schedule. scenario is one of
    'max_throughput', 'min_risk' or 'min_cost'."""
    return optimize_schedule(scenario=scenario, max_orders=max_orders)


def tool_compare_scenarios(max_orders: int = 12) -> dict:
    """Compare all three planning scenarios (throughput vs risk vs cost) side by side."""
    return compare_scenarios(max_orders=max_orders)


def tool_delay_risk(top_n: int = 8) -> dict:
    """Identify pending orders/operations at risk of being delayed or failing (ML)."""
    return explain.explain_delay_risk(top_n)


def tool_downtime_risk() -> dict:
    """Identify machines likely to break down soon from their latest sensor readings (ML)."""
    return explain.explain_downtime()


def tool_demand_forecast(horizon_days: int = 7) -> dict:
    """Forecast product demand for the next N days (ML)."""
    return explain.explain_demand(horizon_days)


def tool_model_metrics() -> dict:
    """Return the trained ML models' evaluation metrics."""
    return registry.metrics()


# tools grouped by specialist (used to build MAF agents)
SCHEDULING_TOOLS = [
    tool_capacity_analysis, tool_detect_bottlenecks, tool_prioritize_orders,
    tool_allocate_resources, tool_optimize_schedule, tool_compare_scenarios,
]
RISK_TOOLS = [tool_delay_risk, tool_downtime_risk, tool_model_metrics]
DEMAND_TOOLS = [tool_demand_forecast]
ALL_TOOLS = SCHEDULING_TOOLS + RISK_TOOLS + DEMAND_TOOLS
