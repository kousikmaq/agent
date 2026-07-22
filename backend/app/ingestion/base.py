"""DataSource port (abstract base class).

Defines the contract every ingestion adapter must satisfy. The CSV adapter
implements it today; ERP/MES adapters will implement the same interface in the
future without any change to downstream engines. This ABC is structurally
compatible with the :class:`app.domain.interfaces.DataSource` protocol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models.factory_state import FactoryState


class DataSource(ABC):
    """Abstract source of daily factory snapshots."""

    @abstractmethod
    def load(self, business_date: str) -> FactoryState:
        """Return the :class:`FactoryState` for ``business_date`` (YYYY-MM-DD).

        Implementations perform schema-level parsing/validation. Cross-entity
        (referential) validation is applied separately by the loader.
        """
        raise NotImplementedError

    @abstractmethod
    def available_dates(self) -> list[str]:
        """Return the sorted business dates this source can provide."""
        raise NotImplementedError
