"""Timing utilities for measuring agent and workflow execution."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Stopwatch:
    """A context manager that measures elapsed wall-clock time in milliseconds.

    Example
    -------
    >>> with Stopwatch() as sw:
    ...     do_work()
    >>> sw.elapsed_ms
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self._elapsed_ms: float = 0.0

    def __enter__(self) -> "Stopwatch":
        self._start = perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self._elapsed_ms = round((perf_counter() - self._start) * 1000, 3)

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds (available after the context exits)."""
        return self._elapsed_ms
