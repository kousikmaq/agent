"""Configurable business rule data.

Business rules parametrise the deterministic scheduling behaviour (priority
weighting, overtime limits, due-date enforcement, safety-stock policy). The
rules engine (later phase) interprets these; here they are only data.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.enums import BusinessRuleType, RuleEnforcement
from app.domain.models.base import DomainModel


class BusinessRule(DomainModel):
    """A single configurable rule applied during scheduling.

    ``parameters`` is an open key/value map interpreted according to
    ``rule_type`` by the rules engine, keeping the model extensible without
    schema churn.
    """

    rule_id: str = Field(..., description="Unique rule identifier.")
    rule_type: BusinessRuleType = Field(..., description="Category of the rule.")
    enforcement: RuleEnforcement = Field(
        default=RuleEnforcement.SOFT,
        description="Hard constraint vs. soft weighted preference.",
    )
    scope: str | None = Field(
        default=None,
        description="Optional target scope (work center, product, customer id).",
    )
    weight: float = Field(
        default=1.0,
        ge=0,
        description="Relative weight for soft rules in the objective function.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Rule-type-specific parameters interpreted by the engine.",
    )
    is_active: bool = Field(default=True, description="Whether the rule is enabled.")
