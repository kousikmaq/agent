"""Automated planning cadence: refresh the plan daily and each Saturday.

The plant runs on a fixed rhythm:

* **Every day** a fresh plan is produced for the new business date (the day's
  snapshot is generated if missing, then the full pipeline runs once).
* **Every Saturday** the next week's plans (Monday–Saturday) are published so
  the team has the coming week ready.

This module owns that cadence. It is deliberately idempotent: a day that is
already generated and planned is skipped, so restarting the server or running
the cycle repeatedly never recomputes or changes an existing plan (the "compute
once, then reuse" rule). A lightweight daemon thread runs the cycle once at
startup and then again shortly after each local midnight.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path

from app.core.logging import get_logger
from app.config import get_settings
from app.services.orchestrator import PlanningOrchestrator
from app.utils.datetime_utils import format_business_date
from simulator.engine import SimulatorEngine

logger = get_logger(__name__)

_SATURDAY = 5  # date.weekday(): Monday=0 … Saturday=5


class PlanningScheduler:
    """Ensures daily plans exist and publishes next-week plans on Saturdays."""

    def __init__(
        self,
        orchestrator: PlanningOrchestrator,
        simulator: SimulatorEngine,
        datasets_dir: Path,
    ) -> None:
        self._orch = orchestrator
        self._sim = simulator
        self._datasets_dir = datasets_dir

    # -- Core idempotent unit ----------------------------------------------
    def ensure_day(self, day: date) -> bool:
        """Generate the snapshot and run the pipeline for ``day`` if missing.

        Returns ``True`` if any work was done, ``False`` if the day was already
        generated and planned (so this is safe to call repeatedly).
        """
        business_date = format_business_date(day)
        did_work = False

        if not (self._datasets_dir / business_date).exists():
            logger.info("Scheduler: generating snapshot for %s.", business_date)
            self._sim.generate_day(day)
            did_work = True

        if not self._orch.store.exists(business_date):
            logger.info("Scheduler: running daily plan for %s.", business_date)
            self._orch.run(business_date)
            did_work = True

        return did_work

    # -- Daily + weekly cadence --------------------------------------------
    def run_cycle(self, today: date) -> None:
        """Refresh today's plan and, on Saturdays, publish next week's plans."""
        did_work = self.ensure_day(today)

        # After a fresh daily plan, optionally let the agent autonomously
        # re-plan around any high-priority orders that are running late.
        settings = get_settings()
        if did_work and settings.auto_replan_enabled:
            try:
                self._orch.auto_remediate(
                    format_business_date(today),
                    priority_max=settings.auto_replan_priority_max,
                    notify=settings.auto_notify_email,
                )
            except Exception:  # noqa: BLE001 - never let the cadence die
                logger.exception("Auto-remediate failed for %s.", today)

        # After a fresh daily plan, optionally auto-place purchase orders for
        # materials that are critically low (below both safety and reorder).
        if did_work and settings.auto_reorder_enabled:
            try:
                self._orch.auto_reorder(format_business_date(today))
            except Exception:  # noqa: BLE001 - never let the cadence die
                logger.exception("Auto-reorder failed for %s.", today)

        if today.weekday() == _SATURDAY:
            next_monday = today + timedelta(days=2)  # Sat + 2 = next Monday
            logger.info(
                "Scheduler: Saturday — publishing next week's plans from %s.",
                format_business_date(next_monday),
            )
            for offset in range(6):  # Monday … Saturday
                self.ensure_day(next_monday + timedelta(days=offset))


def start_scheduler_thread(
    scheduler: PlanningScheduler, stop_event: threading.Event
) -> threading.Thread:
    """Run the daily/weekly cycle in a daemon thread until ``stop_event`` is set.

    Executes one cycle immediately (catching up today's plan), then wakes a few
    minutes after each local midnight to run the next day's cycle. Solving runs
    off the event loop so the API stays responsive.
    """

    def _loop() -> None:
        while not stop_event.is_set():
            today = date.today()
            try:
                scheduler.run_cycle(today)
            except Exception:  # noqa: BLE001 - never let the thread die silently
                logger.exception("Scheduler cycle failed for %s.", today)

            # Sleep until just after the next local midnight, then re-check.
            now = datetime.now()
            next_run = datetime.combine(today + timedelta(days=1), time(0, 5))
            stop_event.wait(max(60.0, (next_run - now).total_seconds()))

    thread = threading.Thread(target=_loop, name="planning-scheduler", daemon=True)
    thread.start()
    return thread
