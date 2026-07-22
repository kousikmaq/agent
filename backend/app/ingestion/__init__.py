"""Data ingestion & validation layer (ports & adapters).

The single swappable seam between external data sources (CSV simulator today,
ERP/MES tomorrow) and the deterministic domain core. Every downstream engine
consumes the validated :class:`~app.domain.models.factory_state.FactoryState`
returned here, so only the adapter changes when the data source changes.
"""

from __future__ import annotations

from app.ingestion.base import DataSource
from app.ingestion.csv_source import CsvDataSource
from app.ingestion.loader import FactoryStateLoader, load_factory_state
from app.ingestion.snapshot import SnapshotManager
from app.ingestion.validators import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    validate_factory_state,
)

__all__ = [
    "DataSource",
    "CsvDataSource",
    "FactoryStateLoader",
    "load_factory_state",
    "SnapshotManager",
    "validate_factory_state",
    "ValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
]
