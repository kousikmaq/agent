"""KPI & analytics engine.

Deterministically computes key performance indicators and curated performance
facts from a generated schedule. No ML, no LLM.
"""

from __future__ import annotations

from app.analytics.facts import AnalyticsFacts, build_analytics_facts
from app.analytics.kpis import AnalyticsEngine, aggregate_schedule
from app.analytics.deliveries import (
    DeliveryDriftReport,
    DeliveryReport,
    DeliveryStatus,
    build_delivery_drift,
    build_delivery_report,
)
from app.analytics.shopfloor import ShopFloorStatus, build_shopfloor_status
from app.analytics.weekly import (
    WeeklyDayPlan,
    WeeklyDayStatus,
    WeeklyPlanReport,
    build_weekly_plan,
)

__all__ = [
    "AnalyticsEngine",
    "aggregate_schedule",
    "AnalyticsFacts",
    "build_analytics_facts",
    "DeliveryReport",
    "DeliveryStatus",
    "build_delivery_report",
    "DeliveryDriftReport",
    "build_delivery_drift",
    "ShopFloorStatus",
    "build_shopfloor_status",
    "WeeklyDayPlan",
    "WeeklyDayStatus",
    "WeeklyPlanReport",
    "build_weekly_plan",
]
