"""Base classes and shared configuration for all domain models.

Every canonical entity and DTO in the domain layer inherits from
:class:`DomainModel`, giving the whole layer consistent validation and
serialization behaviour. This module contains no business logic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base class for canonical domain entities.

    Configuration choices:

    * ``extra="forbid"`` - reject unknown fields so malformed source data
      fails fast during ingestion rather than silently propagating.
    * ``str_strip_whitespace=True`` - normalise incidental whitespace from CSV
      / ERP exports.
    * ``validate_assignment=True`` - keep instances valid after mutation.
    * ``frozen=False`` - entities may be transformed (e.g. by scenario
      planning) but always via validated assignment.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        frozen=False,
        use_enum_values=False,
    )


class FrozenDomainModel(DomainModel):
    """Immutable variant for value objects and computed result DTOs.

    Used for outputs that should not change after construction (risk records,
    recommendations, scenario results) to guarantee auditability.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        frozen=True,
        use_enum_values=False,
    )
