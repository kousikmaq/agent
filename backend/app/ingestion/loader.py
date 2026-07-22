"""FactoryState loader - orchestrates ingestion end to end.

Combines a pluggable :class:`DataSource` (dependency-injected) with cross-entity
validation to return a fully validated :class:`FactoryState`. This is the entry
point downstream engines use; they never touch CSV files or ERP payloads
directly.
"""

from __future__ import annotations

from pathlib import Path

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.domain.models.factory_state import FactoryState
from app.ingestion.base import DataSource
from app.ingestion.csv_source import CsvDataSource
from app.ingestion.validators import ValidationResult, validate_factory_state

logger = get_logger(__name__)


class FactoryStateLoader:
    """Loads and validates factory snapshots from an injected data source."""

    def __init__(self, source: DataSource, *, validate: bool = True) -> None:
        """Create a loader.

        Parameters
        ----------
        source:
            The data-source adapter (CSV today, ERP/MES tomorrow).
        validate:
            When ``True`` (default), cross-entity validation is enforced and a
            :class:`ValidationError` is raised on any fatal issue.
        """
        self._source = source
        self._validate = validate

    def load(self, business_date: str) -> FactoryState:
        """Load, validate, and return the :class:`FactoryState` for a date.

        Raises
        ------
        ValidationError
            If validation is enabled and the snapshot has fatal issues.
        """
        state = self._source.load(business_date)

        if self._validate:
            result = validate_factory_state(state)
            self._log_result(result)
            if result.has_errors:
                raise ValidationError(
                    f"Factory snapshot for {business_date} failed validation with "
                    f"{len(result.errors)} error(s).",
                    details={
                        "business_date": business_date,
                        "errors": [issue.model_dump() for issue in result.errors],
                    },
                )
        return state

    def validate_only(self, business_date: str) -> ValidationResult:
        """Load a snapshot and return its validation result without raising."""
        state = self._source.load(business_date)
        return validate_factory_state(state)

    def available_dates(self) -> list[str]:
        """Return the business dates the underlying source can provide."""
        return self._source.available_dates()

    @staticmethod
    def _log_result(result: ValidationResult) -> None:
        for warning in result.warnings:
            logger.warning("[%s] %s", warning.code, warning.message)
        if result.has_errors:
            logger.error(
                "Snapshot %s has %d validation error(s).",
                result.business_date,
                len(result.errors),
            )


def load_factory_state(
    business_date: str, datasets_dir: Path, *, validate: bool = True
) -> FactoryState:
    """Convenience helper: load a CSV snapshot for ``business_date``.

    Wires a :class:`CsvDataSource` into a :class:`FactoryStateLoader` for the
    common case; downstream services may instead inject a custom data source.
    """
    loader = FactoryStateLoader(CsvDataSource(datasets_dir), validate=validate)
    return loader.load(business_date)
