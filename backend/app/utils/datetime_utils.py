"""Date and time helper utilities.

Small, dependency-free helpers used throughout the system for consistent
handling of business dates (the daily snapshot key) and UTC timestamps.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

# Canonical string format used for dataset/output folder names, e.g.
# ``datasets/2026-07-17``.
DATE_FORMAT = "%Y-%m-%d"


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def format_business_date(value: date) -> str:
    """Format a :class:`date` as the canonical ``YYYY-MM-DD`` string."""
    return value.strftime(DATE_FORMAT)


def parse_business_date(value: str) -> date:
    """Parse a canonical ``YYYY-MM-DD`` string into a :class:`date`.

    Raises
    ------
    ValueError
        If ``value`` does not match the expected ``YYYY-MM-DD`` format.
    """
    return datetime.strptime(value, DATE_FORMAT).date()
