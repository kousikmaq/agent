"""Change-log accumulation and the shared per-day simulation context.

``ChangeLogBuilder`` collects structured :class:`ChangeEvent` records as events
mutate the factory state, then assembles the immutable :class:`ChangeLog`
artifact written alongside the day's data.

``SimulationContext`` bundles the per-day RNG, configuration, dates, and the
log builder so event modules receive a single, tidy argument.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from random import Random
from typing import Any

from app.domain.enums import ChangeEventType
from app.domain.models.change_log import ChangeEvent, ChangeLog
from app.utils.datetime_utils import format_business_date
from simulator.config import SimulatorConfig


class ChangeLogBuilder:
    """Accumulates change events for a single production day."""

    def __init__(self, business_date: date) -> None:
        self._business_date = business_date
        self._date_str = format_business_date(business_date)
        self._events: list[ChangeEvent] = []

    def record(
        self,
        *,
        event_type: ChangeEventType,
        entity_type: str,
        entity_id: str,
        description: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        """Append a single change event to the log."""
        event_id = f"CHG-{self._date_str}-{len(self._events) + 1:04d}"
        self._events.append(
            ChangeEvent(
                event_id=event_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                description=description,
                before=before or {},
                after=after or {},
            )
        )

    def build(self, previous_date: date | None) -> ChangeLog:
        """Assemble the immutable change-log artifact for the day."""
        return ChangeLog(
            business_date=self._date_str,
            previous_date=(
                format_business_date(previous_date) if previous_date else None
            ),
            events=list(self._events),
        )

    @property
    def count(self) -> int:
        """Number of events recorded so far."""
        return len(self._events)


@dataclass
class SimulationContext:
    """Shared state passed to every daily event module."""

    rng: Random
    config: SimulatorConfig
    business_date: date
    previous_date: date | None
    log: ChangeLogBuilder = field(init=False)

    def __post_init__(self) -> None:
        self.log = ChangeLogBuilder(self.business_date)

    @property
    def business_date_str(self) -> str:
        """The business date formatted as ``YYYY-MM-DD``."""
        return format_business_date(self.business_date)
