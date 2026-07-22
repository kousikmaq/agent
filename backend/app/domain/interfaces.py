"""Common domain interfaces (ports).

Defines the abstract contracts that adapters in outer layers implement. Keeping
these as :class:`typing.Protocol` definitions lets the domain core depend on
behaviour, not concrete classes, supporting the Dependency Inversion Principle
and the swappable data-source seam. No implementations live here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.factory_state import FactoryState


@runtime_checkable
class Identifiable(Protocol):
    """Any entity exposing a stable identifier."""

    id: str


@runtime_checkable
class DataSource(Protocol):
    """Port for loading a full factory snapshot for a given business date.

    Implemented by the CSV adapter today and by ERP/MES adapters in the future.
    Only the adapter changes when the data source changes; every downstream
    engine continues to consume :class:`FactoryState` unchanged.
    """

    def load(self, business_date: str) -> FactoryState:
        """Return the validated :class:`FactoryState` for ``business_date``."""
        ...

    def available_dates(self) -> list[str]:
        """Return the business dates (YYYY-MM-DD) this source can provide."""
        ...


@runtime_checkable
class SnapshotRepository(Protocol):
    """Port for persisting and retrieving dated factory snapshots."""

    def save(self, state: FactoryState) -> None:
        """Persist a factory snapshot for its business date."""
        ...

    def load(self, business_date: str) -> FactoryState:
        """Load a previously persisted snapshot."""
        ...

    def exists(self, business_date: str) -> bool:
        """Return whether a snapshot exists for ``business_date``."""
        ...
