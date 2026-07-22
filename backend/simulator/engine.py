"""SimulatorEngine: orchestrates Day-0 seeding and daily state evolution.

The engine is the reusable core behind the CLI. For a requested business date
it either:

* seeds a fresh Day-0 baseline (when no prior snapshot exists), or
* loads the most recent prior snapshot, rolls its calendars to the new day,
  applies the ordered daily event pipeline, and records a change log.

The resulting snapshot is persisted under ``datasets/<date>/`` and returned.
This mirrors how a real plant evolves day to day and keeps every day's data
historically preserved.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from random import Random

from app.core.logging import get_logger
from app.domain.models.change_log import ChangeLog
from app.domain.models.factory_state import FactoryState
from app.utils.datetime_utils import format_business_date, parse_business_date
from app.utils.file_utils import ensure_dir, list_dated_subdirs
from simulator import seed_generator
from simulator.calendars import (
    build_machine_availability,
    build_shift_calendars,
    build_worker_availability,
)
from simulator.change_log import SimulationContext
from simulator.config import SimulatorConfig
from simulator.events import EVENT_PIPELINE
from simulator.state_loader import load_state
from simulator.writer import write_state

logger = get_logger(__name__)


class SimulatorEngine:
    """Generates and persists daily factory snapshots."""

    def __init__(self, config: SimulatorConfig, datasets_dir: Path) -> None:
        self._config = config
        self._datasets_dir = ensure_dir(datasets_dir)

    # -- Public API ---------------------------------------------------------
    def generate_day(self, business_date: date) -> tuple[FactoryState, ChangeLog]:
        """Generate, persist, and return the snapshot for ``business_date``."""
        business_date_str = format_business_date(business_date)
        previous_date = self._find_previous_date(business_date)
        rng = Random(self._config.seed_for_date(business_date.toordinal()))

        if previous_date is None:
            logger.info("Seeding Day-0 baseline for %s", business_date_str)
            state = seed_generator.generate_baseline(business_date, self._config, rng)
            change_log = ChangeLog(
                business_date=business_date_str, previous_date=None, events=[]
            )
        else:
            logger.info(
                "Evolving %s -> %s",
                format_business_date(previous_date),
                business_date_str,
            )
            previous_state = load_state(
                format_business_date(previous_date), self._datasets_dir
            )
            ctx = SimulationContext(
                rng=rng,
                config=self._config,
                business_date=business_date,
                previous_date=previous_date,
            )
            state = self._evolve(previous_state, ctx)
            change_log = ctx.log.build(previous_date)

        directory = write_state(state, change_log, self._datasets_dir)
        logger.info(
            "Wrote snapshot for %s (%d change events) to %s",
            business_date_str,
            len(change_log.events),
            directory,
        )
        return state, change_log

    # -- Internal helpers ---------------------------------------------------
    def _evolve(
        self, previous_state: FactoryState, ctx: SimulationContext
    ) -> FactoryState:
        """Copy the prior state, roll calendars, and apply the event pipeline."""
        state = previous_state.model_copy(deep=True)
        state.business_date = ctx.business_date_str

        self._roll_calendars(state, ctx)

        for apply_event in EVENT_PIPELINE:
            apply_event(state, ctx)

        return state

    def _roll_calendars(self, state: FactoryState, ctx: SimulationContext) -> None:
        """Regenerate date-specific collections for the new business day.

        Machine availability, shift calendars, and worker availability are
        single-day and rebuilt fresh each day. Maintenance windows that have
        already ended are pruned; current/future windows are retained so the
        schedule respects them.
        """
        day = ctx.business_date
        state.machine_availability = build_machine_availability(
            state.machines, day, ctx.config
        )
        state.shift_calendars = build_shift_calendars(day)
        state.worker_availability = build_worker_availability(state.workers, day)
        state.machine_maintenance = [
            window
            for window in state.machine_maintenance
            if window.end.date() >= day
        ]

    def _find_previous_date(self, business_date: date) -> date | None:
        """Return the latest existing snapshot date strictly before the target."""
        candidates: list[date] = []
        for name in list_dated_subdirs(self._datasets_dir):
            try:
                parsed = parse_business_date(name)
            except ValueError:
                continue
            if parsed < business_date:
                candidates.append(parsed)
        return max(candidates) if candidates else None
