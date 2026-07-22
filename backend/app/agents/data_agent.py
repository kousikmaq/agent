"""Data Agent.

Wraps the existing data services - no business logic is duplicated here:
- Snapshot Manager (dataset availability)
- Stateful Daily Factory Simulator (generates a snapshot when missing)
- CSV Loader / data source (builds the FactoryState)

It loads the requested production date, builds the ``FactoryState`` using the
existing implementation, and stores it (unmodified) in the shared
:class:`WorkflowContext`.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import DataAgentOutput
from app.agents.errors import CriticalAgentError, RecoverableAgentError
from app.agents.timing import Stopwatch
from app.core.exceptions import DataIngestionError
from app.ingestion import CsvDataSource, SnapshotManager
from app.utils.datetime_utils import parse_business_date
from simulator.engine import SimulatorEngine

# Shared-context key so downstream agents can locate the produced FactoryState.
FACTORY_STATE_KEY = "factory_state"


class DataAgent(BaseAgent):
    """Loads/prepares the factory snapshot using the existing services."""

    name = "data_agent"

    def __init__(
        self,
        data_source: CsvDataSource,
        snapshot: SnapshotManager,
        simulator: SimulatorEngine,
        datasets_dir: Path,
    ) -> None:
        self._data_source = data_source
        self._snapshot = snapshot
        self._simulator = simulator
        self._datasets_dir = datasets_dir

    def execute(self, context: WorkflowContext) -> DataAgentOutput:
        date_str = context.business_date
        try:
            day = parse_business_date(date_str)
        except ValueError as exc:
            raise CriticalAgentError(
                f"Invalid business date '{date_str}'; expected YYYY-MM-DD."
            ) from exc

        dataset_path = self._datasets_dir / date_str
        self.logger.info(
            "Business date: %s | dataset path: %s", date_str, dataset_path
        )

        # Ensure dataset availability, generating via the existing simulator.
        if not self._snapshot.exists(date_str):
            self.logger.info("Snapshot missing; generating via simulator.")
            self._simulator.generate_day(day)

        # Build the FactoryState using the existing CSV loader (schema-level).
        with Stopwatch() as sw:
            try:
                state = self._data_source.load(date_str)
            except DataIngestionError as exc:
                # Recoverable: a retry re-checks availability / regenerates.
                raise RecoverableAgentError(
                    f"Failed to load dataset for {date_str}: {exc.message}"
                ) from exc

        self.logger.info(
            "Loaded FactoryState in %.1f ms (orders=%d, machines=%d, path=%s).",
            sw.elapsed_ms,
            len(state.production_orders),
            len(state.machines),
            dataset_path,
        )

        # Store the FactoryState unmodified for downstream agents.
        context.shared[FACTORY_STATE_KEY] = state
        return DataAgentOutput(
            agent=self.name,
            business_date=date_str,
            factory_state=state,
            note=str(dataset_path),
        )
