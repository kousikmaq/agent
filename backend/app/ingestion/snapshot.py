"""Snapshot manager - persist and retrieve dated factory snapshots.

Reads snapshots via the CSV adapter and writes canonical snapshots to
``datasets/<date>/``. Writing enables the future ERP/MES path to persist an
auditable, replayable copy of each ingested day using exactly the same on-disk
format the simulator produces. Implements the
:class:`app.domain.interfaces.SnapshotRepository` contract.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.domain.models.factory_state import FactoryState
from app.domain.models.routing import Operation
from app.ingestion.csv_codec import field_names, model_to_row
from app.ingestion.csv_schema import (
    CSV_REGISTRY,
    OPERATIONS_FILE,
    ROUTING_HEADER_FIELDS,
    ROUTINGS_FILE,
)
from app.ingestion.csv_source import CsvDataSource
from app.utils.file_utils import ensure_dir, list_dated_subdirs


class SnapshotManager:
    """Manages the lifecycle of dated CSV snapshots on disk."""

    def __init__(self, datasets_dir: Path) -> None:
        self._datasets_dir = ensure_dir(datasets_dir)
        self._reader = CsvDataSource(datasets_dir)

    # --- Read side ---------------------------------------------------------
    def load(self, business_date: str) -> FactoryState:
        """Load the snapshot for ``business_date`` (schema-validated)."""
        return self._reader.load(business_date)

    def exists(self, business_date: str) -> bool:
        """Return whether a snapshot exists for ``business_date``."""
        return (self._datasets_dir / business_date).exists()

    def available_dates(self) -> list[str]:
        """Return all snapshot dates present on disk, sorted ascending."""
        return list_dated_subdirs(self._datasets_dir)

    def latest_date(self) -> str | None:
        """Return the most recent snapshot date, or ``None`` if none exist."""
        dates = self.available_dates()
        return dates[-1] if dates else None

    # --- Write side --------------------------------------------------------
    def save(self, state: FactoryState) -> Path:
        """Persist ``state`` to ``datasets/<business_date>/`` and return the dir.

        Writing is append-only at day granularity: a dated folder is created;
        existing days are never modified.
        """
        directory = ensure_dir(self._datasets_dir / state.business_date)

        for filename, attribute, model_cls in CSV_REGISTRY:
            items = getattr(state, attribute)
            rows = [model_to_row(item) for item in items]
            self._write_csv(directory / filename, field_names(model_cls), rows)

        self._write_routings(directory, state)
        return directory

    # --- Internal helpers --------------------------------------------------
    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_routings(self, directory: Path, state: FactoryState) -> None:
        routing_rows: list[dict[str, str]] = []
        operation_rows: list[dict[str, str]] = []
        for routing in state.routings:
            routing_rows.append(
                {
                    "routing_id": routing.routing_id,
                    "product_id": routing.product_id,
                    "version": routing.version,
                }
            )
            operation_rows.extend(model_to_row(op) for op in routing.operations)

        self._write_csv(
            directory / ROUTINGS_FILE, list(ROUTING_HEADER_FIELDS), routing_rows
        )
        self._write_csv(
            directory / OPERATIONS_FILE, field_names(Operation), operation_rows
        )
