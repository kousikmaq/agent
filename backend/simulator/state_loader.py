"""State loader: read a previously written datasets/<date>/ snapshot back.

Reconstructs a validated :class:`FactoryState` from CSV so the engine can
evolve the previous day into the next. Symmetric with :mod:`simulator.writer`
via the shared schema registry. (In a later phase the ingestion layer will
provide the production CSV adapter; the simulator keeps its own reader so it
remains self-contained.)
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel

from app.core.exceptions import DataIngestionError
from app.domain.models.factory_state import FactoryState
from app.domain.models.routing import Operation, Routing
from simulator.schema import (
    CSV_REGISTRY,
    OPERATIONS_FILE,
    ROUTINGS_FILE,
)
from simulator.serialization import row_to_model


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV into a list of raw string dicts (empty if the file is absent)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_models(path: Path, model_cls: type[BaseModel]) -> list[BaseModel]:
    return [row_to_model(row, model_cls) for row in _read_rows(path)]


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


def load_state(business_date: str, datasets_dir: Path) -> FactoryState:
    """Load the :class:`FactoryState` snapshot for ``business_date``.

    Raises
    ------
    DataIngestionError
        If the dated snapshot directory does not exist.
    """
    directory = datasets_dir / business_date
    if not directory.exists():
        raise DataIngestionError(
            f"No dataset snapshot found for {business_date}.",
            details={"directory": str(directory)},
        )

    collections: dict[str, list[BaseModel]] = {}
    for filename, attribute, model_cls in CSV_REGISTRY:
        collections[attribute] = _read_models(directory / filename, model_cls)

    return FactoryState(
        business_date=business_date,
        routings=_read_routings(directory),
        **collections,
    )
