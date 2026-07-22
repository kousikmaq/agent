"""Daily change-log DTOs.

Structured record of the operational deltas applied when a new production day
evolves from the previous one. Written by the stateful simulator and consumed
by the UI ("what changed today") and the explanation layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.enums import ChangeEventType
from app.domain.models.base import FrozenDomainModel


class ChangeEvent(FrozenDomainModel):
    """A single operational change applied to the factory state."""

    event_id: str = Field(..., description="Unique change event identifier.")
    event_type: ChangeEventType = Field(..., description="Type of operational change.")
    entity_type: str = Field(..., description="Domain entity affected (e.g. 'machine').")
    entity_id: str = Field(..., description="Identifier of the affected entity.")
    description: str = Field(..., description="Human-readable description of the change.")
    before: dict[str, Any] = Field(
        default_factory=dict, description="Relevant field values before the change."
    )
    after: dict[str, Any] = Field(
        default_factory=dict, description="Relevant field values after the change."
    )


class ChangeLog(FrozenDomainModel):
    """The complete set of changes distinguishing a day from the prior day."""

    business_date: str = Field(..., description="Day the log applies to (YYYY-MM-DD).")
    previous_date: str | None = Field(
        default=None, description="Prior day the state evolved from (YYYY-MM-DD)."
    )
    events: list[ChangeEvent] = Field(
        default_factory=list, description="All changes applied for the day."
    )
