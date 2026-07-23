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


class ReplanPrioritiesRequest(BaseModel):
    """Request body to set per-order priorities and re-solve the day once."""

    priorities: dict[str, int] = Field(
        ...,
        min_length=1,
        description="Map of order_id -> new priority (1 = lowest, 10 = highest).",
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


class EmailRisksRequest(BaseModel):
    """Request body to email the day's risk summary."""

    severities: list[str] | None = Field(
        default=None,
        description="Optional severity filter (e.g. ['CRITICAL','HIGH']). "
        "Omit to include all risks.",
    )
    to: str | None = Field(
        default=None,
        description="Optional recipient override; defaults to ALERT_EMAIL_TO.",
    )
    preview: bool = Field(
        default=False,
        description="When true, render and return the email without sending it.",
    )


class PlaceOrderRequest(BaseModel):
    """Request body to email a purchase-order / material replenishment request."""

    item: str = Field(..., min_length=1, description="Item or material to order.")
    quantity: str = Field(
        default="As required", description="Requested quantity (free text)."
    )
    supplier: str | None = Field(default=None, description="Preferred supplier, if any.")
    order_id: str | None = Field(
        default=None, description="Production order this replenishment supports."
    )
    needed_by: str | None = Field(default=None, description="Required-by date/time.")
    reason: str | None = Field(default=None, description="Justification for the request.")
    to: str | None = Field(
        default=None,
        description="Optional recipient override; defaults to ALERT_EMAIL_TO.",
    )
    preview: bool = Field(
        default=False,
        description="When true, render and return the email without sending it.",
    )


class EmailActionResponse(BaseModel):
    """Receipt for a dispatched email action."""

    sent: bool = Field(..., description="Whether the email was dispatched.")
    subject: str = Field(..., description="Subject line of the email sent.")
    recipient: str = Field(..., description="Address the email was sent to.")


class EmailReportRequest(BaseModel):
    """Request to email (or preview) a per-tab report."""

    report_type: str = Field(
        ..., description="Report/tab identifier (overview, orders, scenarios, ...)."
    )
    role: str | None = Field(
        default=None, description="Operational role the report is addressed to."
    )
    to: str | None = Field(
        default=None, description="Optional recipient override; defaults to ALERT_EMAIL_TO."
    )
    preview: bool = Field(
        default=False,
        description="When true, render and return the email without sending it.",
    )
    scenario_type: str | None = Field(
        default=None,
        description="For the scenarios report: which scenario to detail.",
    )


class EmailPreviewResponse(BaseModel):
    """Rendered email returned for a preview (no send)."""

    sent: bool = Field(default=False, description="Always false for a preview.")
    subject: str = Field(..., description="Rendered subject line.")
    html: str = Field(..., description="Rendered HTML body.")
    recipient: str = Field(..., description="Address the email would be sent to.")


class RolesResponse(BaseModel):
    """Available operational roles a report can be addressed to."""

    roles: list[str]

