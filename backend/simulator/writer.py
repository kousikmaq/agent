"""Writer: persist a FactoryState (and its change log) to datasets/<date>/.

Each domain collection is written to its own CSV using the shared schema
registry, guaranteeing symmetry with :mod:`simulator.state_loader`. Writing is
append-only at the day granularity: a new dated folder is created and prior
days are never overwritten.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.domain.models.change_log import ChangeLog
from app.domain.models.factory_state import FactoryState
from app.domain.models.routing import Operation, Routing
from app.utils.file_utils import ensure_dir
from simulator.schema import (
    CHANGE_LOG_FILE,
    CSV_REGISTRY,
    OPERATIONS_FILE,
    ROUTINGS_FILE,
)
from simulator.serialization import field_names, model_to_row


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write ``rows`` to ``path`` with a header, even when there are no rows."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_routings(directory: Path, routings: list[Routing]) -> None:
    """Split routings into a header file and a flattened operations file."""
    routing_rows: list[dict[str, str]] = []
    operation_rows: list[dict[str, str]] = []
    for routing in routings:
        routing_rows.append(
            {
                "routing_id": routing.routing_id,
                "product_id": routing.product_id,
                "version": routing.version,
            }
        )
        for operation in routing.operations:
            operation_rows.append(model_to_row(operation))

    _write_csv(
        directory / ROUTINGS_FILE,
        ["routing_id", "product_id", "version"],
        routing_rows,
    )
    _write_csv(
        directory / OPERATIONS_FILE,
        field_names(Operation),
        operation_rows,
    )


def _write_change_log(directory: Path, change_log: ChangeLog) -> None:
    """Write the structured daily change log to its own CSV."""
    fieldnames = [
        "business_date",
        "previous_date",
        "event_id",
        "event_type",
        "entity_type",
        "entity_id",
        "description",
        "before",
        "after",
    ]
    rows: list[dict[str, str]] = []
    for event in change_log.events:
        row = model_to_row(event)
        row["business_date"] = change_log.business_date
        row["previous_date"] = change_log.previous_date or ""
        rows.append(row)
    _write_csv(directory / CHANGE_LOG_FILE, fieldnames, rows)


def write_state(
    state: FactoryState, change_log: ChangeLog, datasets_dir: Path
) -> Path:
    """Persist ``state`` and ``change_log`` under ``datasets/<business_date>/``.

    Returns the directory the snapshot was written to.
    """
    directory = ensure_dir(datasets_dir / state.business_date)

    for filename, attribute, model_cls in CSV_REGISTRY:
        items = getattr(state, attribute)
        rows = [model_to_row(item) for item in items]
        _write_csv(directory / filename, field_names(model_cls), rows)

    _write_routings(directory, state.routings)
    _write_change_log(directory, change_log)
    return directory
