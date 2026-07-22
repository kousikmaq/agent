"""Application exception hierarchy.

Defines a small, well-structured set of base exceptions that feature modules
in later phases will extend (e.g. ingestion, optimization, risk detection).
Keeping these in one place ensures consistent error semantics and HTTP
mapping across the whole API.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application-specific errors.

    Attributes
    ----------
    message:
        Human-readable error description.
    code:
        Stable, machine-readable error code (used by API clients / frontend).
    status_code:
        Default HTTP status code used when this error surfaces through the API.
    details:
        Optional structured context to aid debugging (never exposed verbatim
        in production responses unless explicitly safe).
    """

    code: str = "app_error"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}


class ConfigurationError(AppError):
    """Raised when the application is misconfigured (missing settings, etc.)."""

    code = "configuration_error"
    status_code = 500


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    code = "not_found"
    status_code = 404


class ValidationError(AppError):
    """Raised when input data fails business/domain validation."""

    code = "validation_error"
    status_code = 422


class DataIngestionError(AppError):
    """Raised when raw source data cannot be loaded or validated.

    Reserved for the ingestion phase; declared here so the error contract is
    stable from Phase 1 onward.
    """

    code = "data_ingestion_error"
    status_code = 400


class OptimizationError(AppError):
    """Raised when the scheduling/optimization engine fails.

    Reserved for the optimization phase.
    """

    code = "optimization_error"
    status_code = 500
