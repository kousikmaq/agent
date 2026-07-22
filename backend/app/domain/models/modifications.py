"""DTOs tracking manual modifications applied to a day's committed plan.

Records the plan's original (baseline) KPIs, its current KPIs after any
applied fixes, and the ordered list of modifications, so the UI can show a
before/after comparison of the current plan versus the originally planned one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanModification(BaseModel):
    """A single fix applied to the committed plan."""

    label: str = Field(..., description="Human-readable summary of the change.")
    action: str = Field(..., description="Action code applied (e.g. ADD_SHIFT).")
    applied_at: str = Field(..., description="ISO timestamp the fix was applied.")
    targets: dict[str, list[str]] = Field(
        default_factory=dict, description="Entities the change targeted."
    )


class PlanModifications(BaseModel):
    """Baseline vs current KPIs plus the modifications applied to a day."""

    business_date: str = Field(..., description="Day the record applies to.")
    baseline_kpis: dict[str, float] = Field(
        default_factory=dict,
        description="Headline KPIs of the originally planned schedule.",
    )
    current_kpis: dict[str, float] = Field(
        default_factory=dict,
        description="Headline KPIs of the current (modified) schedule.",
    )
    modifications: list[PlanModification] = Field(
        default_factory=list, description="Ordered list of applied fixes."
    )
