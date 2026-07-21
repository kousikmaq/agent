"""
Data shapes (Pydantic models) shared by the API and the services.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


# ----------------------------- capacity (per week) -----------------------------
class ResourceLoad(BaseModel):
    work_center: str
    name: str
    department: str
    required_hours: float
    available_hours: float
    utilization_pct: float
    overload_hours: float
    status: str  # "OK" | "OVERLOADED"


class Bottleneck(BaseModel):
    work_center: str
    utilization_pct: float
    overload_hours: float
    message: str


class BatchingInsight(BaseModel):
    naive_setup_hours: float
    batched_setup_hours: float
    setup_hours_saved: float
    note: str


class OrderRow(BaseModel):
    order_id: str
    item_id: str
    item_name: str
    customer_id: str
    quantity: int
    due_date: str
    priority: str
    status: str


class Recommendation(BaseModel):
    from_wc: str
    to_wc: str
    hours: float
    text: str


class WeekLoad(BaseModel):
    week_start: str
    orders_considered: int
    resources: List[ResourceLoad]
    bottleneck: Optional[Bottleneck]
    batching: BatchingInsight
    recommendations: List[Recommendation]
    summary: str
    orders: List[OrderRow]


# ----------------------------- bulk overview (all weeks) -----------------------------
class WeekSummary(BaseModel):
    week_start: str
    orders: int
    bottleneck_wc: Optional[str]
    bottleneck_util: float
    overloaded_count: int
    total_required_hours: float
    total_capacity_hours: float
    status: str  # "OK" | "TIGHT" | "OVERLOADED"


class OverviewResult(BaseModel):
    weeks: List[WeekSummary]
    total_orders: int
    overloaded_weeks: int


# ----------------------------- heatmap (work centre x week) -----------------------------
class HeatCell(BaseModel):
    week_start: str
    utilization_pct: float
    status: str  # "OK" | "TIGHT" | "OVERLOADED"

class HeatRow(BaseModel):
    work_center: str
    name: str
    department: str
    cells: List[HeatCell]


class HeatmapResult(BaseModel):
    weeks: List[str]
    rows: List[HeatRow]


# ----------------------------- order prioritization -----------------------------
class OrderPriority(BaseModel):
    rank: int
    order_id: str
    item_name: str
    customer_id: str
    tier: str
    quantity: int
    due_date: str
    days_to_due: int
    processing_hours: float
    critical_ratio: float
    score: float
    at_risk: bool
    reasons: List[str]


class PriorityResult(BaseModel):
    week_start: str
    as_of: str
    orders_considered: int
    orders: List[OrderPriority]


# ----------------------------- resource allocation -----------------------------
class AllocationMove(BaseModel):
    from_wc: str
    to_wc: str
    hours: float
    note: str


class AllocationState(BaseModel):
    work_center: str
    name: str
    util_before: float
    util_after: float
    status_before: str
    status_after: str


class AllocationResult(BaseModel):
    week_start: str
    orders_considered: int
    hours_moved: float
    overloads_before: int
    overloads_after: int
    moves: List[AllocationMove]
    states: List[AllocationState]
    summary: str


# ----------------------------- schedule optimization -----------------------------
class ScheduledOp(BaseModel):
    order_id: str
    item_name: str
    work_center: str
    op_seq: int
    start_min: int
    end_min: int
    duration_min: int


class SchedulePlan(BaseModel):
    week_start: str
    orders_scheduled: int
    machines: List[str]
    makespan_min: int
    makespan_hours: float
    status: str          # "OPTIMAL" | "FEASIBLE" | "NO_SOLUTION"
    objective: str
    solve_ms: int
    ops: List[ScheduledOp]


# ----------------------------- delay risk -----------------------------
class ComponentShortage(BaseModel):
    component_id: str
    component_name: str
    required: int
    available: int
    shortfall: int
    lead_time_days: int
    note: str


class DelayRiskOrder(BaseModel):
    order_id: str
    item_name: str
    customer_id: str
    due_date: str
    at_risk: bool
    causes: List[str]
    fix: str


class DelayRiskResult(BaseModel):
    week_start: str
    orders_considered: int
    at_risk_count: int
    material_risk_count: int
    capacity_risk_count: int
    shortages: List[ComponentShortage]
    orders: List[DelayRiskOrder]
    summary: str


# ----------------------------- demand vs capacity (horizon) -----------------------------
class ResourceDemand(BaseModel):
    work_center: str
    name: str
    department: str
    required_hours: float
    available_hours: float
    utilization_pct: float
    gap_hours: float
    feasible: bool


class DepartmentDemand(BaseModel):
    department: str
    required_hours: float
    available_hours: float
    utilization_pct: float
    gap_hours: float
    feasible: bool


class DemandVsCapacity(BaseModel):
    horizon_weeks: int
    overall_required_hours: float
    overall_available_hours: float
    overall_utilization_pct: float
    overall_gap_hours: float
    overall_feasible: bool
    overloaded_weeks: int
    verdict: str
    fixes: List[str]
    departments: List[DepartmentDemand]
    resources: List[ResourceDemand]


# ----------------------------- what-if scenarios -----------------------------
class Scenario(BaseModel):
    key: str
    name: str
    description: str
    bottleneck_wc: Optional[str]
    bottleneck_util: float
    overloaded_count: int
    orders_planned: int
    outcome: str


class ScenarioComparison(BaseModel):
    week_start: str
    scenarios: List[Scenario]
    summary: str


# ----------------------------- misc -----------------------------
class DatasetSummary(BaseModel):
    tables: dict
    total_orders: int
    weeks: List[str]


class FeatureStatus(BaseModel):
    key: str
    name: str
    status: str  # "implemented" | "planned"
    description: str


class AgentAsk(BaseModel):
    # Bounded input: rejects empty and oversized questions at the API boundary.
    question: str = Field(min_length=1, max_length=500)
    # Optional current tab, used only to bias which tool the copilot reaches for.
    context: Optional[str] = Field(default=None, max_length=40)


class AgentReply(BaseModel):
    answer: str
    used_llm: bool
