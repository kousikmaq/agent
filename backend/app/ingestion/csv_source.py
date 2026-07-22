"""CSV data-source adapter.

Reads a dated snapshot directory (``datasets/<YYYY-MM-DD>/``) and reconstructs a
schema-validated :class:`FactoryState`. Implements the :class:`DataSource` port
so it is fully interchangeable with future ERP/MES adapters.

Only *schema-level* validation happens here (Pydantic parsing). Cross-entity
referential validation is applied by the loader via :mod:`app.ingestion.validators`.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import DataIngestionError
from app.domain.models.factory_state import FactoryState
from app.domain.models.routing import Operation, Routing
from app.ingestion.base import DataSource
from app.ingestion.csv_codec import row_to_model
from app.ingestion.csv_schema import (
    CSV_REGISTRY,
    OPERATIONS_FILE,
    ROUTINGS_FILE,
)
from app.utils.file_utils import list_dated_subdirs


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV into a list of raw string dicts (empty if the file is absent)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_models(path: Path, model_cls: type[BaseModel]) -> list[BaseModel]:
    """Parse every row of ``path`` into ``model_cls`` instances.

    Wraps Pydantic validation errors in :class:`DataIngestionError` with the
    offending file and row for actionable diagnostics.
    """
    models: list[BaseModel] = []
    for index, row in enumerate(_read_rows(path), start=2):  # row 1 is the header
        try:
            models.append(row_to_model(row, model_cls))
        except PydanticValidationError as exc:
            raise DataIngestionError(
                f"Invalid row in {path.name} (line {index}).",
                details={"file": path.name, "line": index, "errors": exc.errors()},
            ) from exc
    return models


def _read_routings(directory: Path) -> list[Routing]:
    """Reassemble routings from the header + flattened operations files."""
    operations_by_routing: dict[str, list[Operation]] = {}
    for row in _read_rows(directory / OPERATIONS_FILE):
        operation = row_to_model(row, Operation)
        operations_by_routing.setdefault(operation.routing_id, []).append(operation)

    routings: list[Routing] = []
    for row in _read_rows(directory / ROUTINGS_FILE):
        routing_id = row["routing_id"]
        routings.append(
            Routing(
                routing_id=routing_id,
                product_id=row["product_id"],
                version=row.get("version") or "1",
                operations=operations_by_routing.get(routing_id, []),
            )
        )
    return routings


def read_factory_state(directory: Path, business_date: str) -> FactoryState:
    """Read a snapshot directory into a schema-validated :class:`FactoryState`."""
    collections: dict[str, list[BaseModel]] = {}
    for filename, attribute, model_cls in CSV_REGISTRY:
        collections[attribute] = _read_models(directory / filename, model_cls)

    return FactoryState(
        business_date=business_date,
        routings=_read_routings(directory),
        **collections,
    )


class CsvDataSource(DataSource):
    """Loads factory snapshots from dated CSV directories."""

    def __init__(self, datasets_dir: Path) -> None:
        self._datasets_dir = datasets_dir

    def load(self, business_date: str) -> FactoryState:
        """Load the :class:`FactoryState` for ``business_date``.

        Raises
        ------
        DataIngestionError
            If the dated snapshot directory does not exist.
        """
        directory = self._datasets_dir / business_date
        if not directory.exists():
            raise DataIngestionError(
                f"No dataset snapshot found for {business_date}.",
                details={"directory": str(directory)},
            )
        return read_factory_state(directory, business_date)

    def available_dates(self) -> list[str]:
        """Return the sorted business dates available on disk."""
        return list_dated_subdirs(self._datasets_dir)
