"""Risk detection DTOs.

Output structures produced by the Risk Detection Engine (later phase). Each
:class:`Risk` is an immutable, evidence-backed record so results are fully
auditable and safe to feed to the explanation layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.enums import RiskSeverity, RiskType
from app.domain.models.base import FrozenDomainModel


class Risk(FrozenDomainModel):
    """A single detected operational risk."""

    risk_id: str = Field(..., description="Unique risk identifier.")
    risk_type: RiskType = Field(..., description="Category of the risk.")
    severity: RiskSeverity = Field(..., description="Assessed severity.")
    title: str = Field(..., description="Short human-readable summary.")
    description: str = Field(..., description="Detailed description of the risk.")
    affected_entities: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Impacted entity ids grouped by type (e.g. 'order_ids').",
    )
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Quantitative evidence supporting the detection.",
    )


class RiskReport(FrozenDomainModel):
    """The complete set of risks detected for a production day."""

    business_date: str = Field(..., description="Day the report applies to (YYYY-MM-DD).")
    risks: list[Risk] = Field(
        default_factory=list, description="All detected risks."
    )
