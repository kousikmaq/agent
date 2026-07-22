"""Routing and operation master data.

A :class:`Routing` is the ordered sequence of :class:`Operation` steps required
to manufacture a product. Operations are stored on their routing and reference
the machines and skills they require.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from app.domain.models.base import DomainModel


class Operation(DomainModel):
    """A single routing step performed on an eligible machine.

    Processing time for a production order of quantity ``q`` is modelled as
    ``setup_minutes + run_minutes_per_unit * q`` (computed by later phases,
    not here).
    """

    operation_id: str = Field(..., description="Unique operation identifier.")
    routing_id: str = Field(..., description="Owning routing identifier.")
    sequence: int = Field(
        ..., ge=1, description="1-based position within the routing."
    )
    name: str = Field(..., description="Operation display name.")
    work_center: str = Field(
        ..., description="Work center / department the operation belongs to."
    )
    setup_minutes: int = Field(
        default=0, ge=0, description="Fixed setup time in minutes."
    )
    run_minutes_per_unit: float = Field(
        ..., ge=0, description="Variable run time per produced unit, in minutes."
    )
    eligible_machine_ids: list[str] = Field(
        default_factory=list,
        description="Machines capable of performing this operation.",
    )
    required_skill: str | None = Field(
        default=None,
        description="Skill code a worker must hold to run this operation.",
    )

    @field_validator("eligible_machine_ids")
    @classmethod
    def _dedupe_machines(cls, value: list[str]) -> list[str]:
        """Remove duplicate machine references while preserving order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for machine_id in value:
            if machine_id not in seen:
                seen.add(machine_id)
                ordered.append(machine_id)
        return ordered


class Routing(DomainModel):
    """An ordered set of operations that produces a product."""

    routing_id: str = Field(..., description="Unique routing identifier.")
    product_id: str = Field(..., description="Product this routing produces.")
    version: str = Field(default="1", description="Routing version label.")
    operations: list[Operation] = Field(
        default_factory=list,
        description="Operations in execution order (validated to be unique).",
    )

    @field_validator("operations")
    @classmethod
    def _validate_sequence_unique(cls, value: list[Operation]) -> list[Operation]:
        """Ensure operation sequence numbers are unique within the routing."""
        sequences = [op.sequence for op in value]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Operation sequence numbers must be unique per routing.")
        return sorted(value, key=lambda op: op.sequence)
