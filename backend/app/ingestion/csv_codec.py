"""Generic CSV cell codec (model <-> row).

Owns the canonical flat-cell encoding shared by the CSV adapter and the
snapshot manager. This is the read/write contract that the simulator's output
must also honour, guaranteeing that simulator-produced snapshots ingest cleanly
and that a future ERP adapter can persist identical snapshots.

Encoding rules (per cell):

* ``None``            -> empty string
* ``bool``            -> ``"true"`` / ``"false"``
* ``list`` / ``dict`` -> compact JSON (round-tripped on read)
* everything else     -> its JSON-mode string (dates/times/enums as ISO)

On read, empty cells are omitted so Pydantic applies field defaults, and cells
beginning with ``[`` or ``{`` are JSON-decoded back into lists/dicts.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


def field_names(model_cls: type[BaseModel]) -> list[str]:
    """Return the ordered CSV column names for a model class."""
    return list(model_cls.model_fields.keys())


def model_to_row(model: BaseModel) -> dict[str, str]:
    """Encode a model instance into a flat string dict for CSV writing."""
    data = model.model_dump(mode="json")
    row: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            row[key] = ""
        elif isinstance(value, bool):
            row[key] = "true" if value else "false"
        elif isinstance(value, (list, dict)):
            row[key] = json.dumps(value, separators=(",", ":"))
        else:
            row[key] = str(value)
    return row


def row_to_model(row: dict[str, str], model_cls: type[TModel]) -> TModel:
    """Decode a flat CSV row back into a validated model instance."""
    kwargs: dict[str, Any] = {}
    for key, raw in row.items():
        if raw is None:
            continue
        value = raw.strip() if isinstance(raw, str) else raw
        if value == "":
            continue  # let the model apply its default / None
        if value[0] in "[{":
            kwargs[key] = json.loads(value)
        else:
            kwargs[key] = value
    return model_cls(**kwargs)
