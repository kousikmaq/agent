"""Shared API request/response schemas for API version 1.

Only foundation-level schemas live here. Feature-specific schemas (schedule,
risks, recommendations, scenarios) will be added alongside their routers in
later phases.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response body for the health and readiness probes."""

    status: str = Field(..., description="Service status indicator.")
    service: str = Field(..., description="Human-readable service name.")
    version: str = Field(..., description="Running application version.")
    environment: str = Field(
        ..., description="Deployment environment (development/staging/production)."
    )


class RunScheduleRequest(BaseModel):
    """Request body to run (or re-run) the planning pipeline for a date."""

    business_date: str = Field(..., description="Business date to plan (YYYY-MM-DD).")
    max_time_seconds: float | None = Field(
        default=None, gt=0, description="Optional solver time budget override."
    )
    force: bool = Field(
        default=False, description="Re-run even if cached results exist."
    )


class ApplyScenarioRequest(BaseModel):
    """Request body to commit a scenario plan as the current plan for a date."""

    scenario_type: str = Field(
        ..., description="Scenario to apply as the committed plan (e.g. OVERTIME_ENABLED)."
    )
    max_time_seconds: float | None = Field(
        default=None, gt=0, description="Optional solver time budget override."
    )


class MitigateOrdersRequest(BaseModel):
    """Request body to raise the priority of delayed orders and re-solve."""

    order_ids: list[str] = Field(
        ..., min_length=1, description="Orders whose priority should be raised."
    )
    priority: int = Field(
        default=10,
        ge=1,
        le=10,
        description="Priority to assign the orders (1 = lowest, 10 = highest).",
    )
    max_time_seconds: float | None = Field(
        default=None, gt=0, description="Optional solver time budget override."
    )


class ApplyFixRequest(BaseModel):
    """Request body to apply a recommended fix action and re-solve the day."""

    action: str = Field(
        ..., description="Recommendation action to apply (e.g. ADD_SHIFT)."
    )
    targets: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Affected entity ids grouped by type (machine_ids, "
        "worker_ids, product_ids).",
    )
    max_time_seconds: float | None = Field(
        default=None, gt=0, description="Optional solver time budget override."
    )


class FixActionItem(BaseModel):
    """One recommended fix action within a combined apply request."""

    action: str = Field(..., description="Recommendation action to apply.")
    targets: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Affected entity ids grouped by type.",
    )


class ApplyFixesRequest(BaseModel):
    """Apply several fixes (priority + actions) in a single re-solve."""

    order_ids: list[str] = Field(
        default_factory=list,
        description="Orders whose priority should be raised (delayed orders).",
    )
    priority: int = Field(
        default=10, ge=1, le=10, description="Priority to assign those orders."
    )
    actions: list[FixActionItem] = Field(
        default_factory=list,
        description="Fix actions to apply before the single re-solve.",
    )
    max_time_seconds: float | None = Field(
        default=None, gt=0, description="Optional solver time budget override."
    )


class GenerateDataRequest(BaseModel):
    """Request body to generate a daily factory snapshot via the simulator."""

    business_date: str = Field(..., description="Business date to generate (YYYY-MM-DD).")


class GenerateDataResponse(BaseModel):
    """Result of generating a daily snapshot."""

    business_date: str
    change_events: int


class DatesResponse(BaseModel):
    """Available business dates."""

    dates: list[str]


class ChatRequest(BaseModel):
    """A planner question about a planned production day."""

    question: str = Field(..., min_length=1, description="The planner's question.")
