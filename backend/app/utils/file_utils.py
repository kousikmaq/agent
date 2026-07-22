"""Filesystem helper utilities.

Thin, well-tested helpers for the directory conventions used by the system
(dated dataset/output folders). Kept free of business logic so both the API
and the simulator can rely on them.
"""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if it does not yet exist and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def dated_subdir(base: Path, business_date: str) -> Path:
    """Return ``base/<business_date>`` (e.g. ``datasets/2026-07-17``).

    The directory is *not* created here; callers decide whether they are
    reading (must exist) or writing (should be created).
    """
    return base / business_date


def list_dated_subdirs(base: Path) -> list[str]:
    """Return the sorted names of dated subdirectories under ``base``.

    Non-existent ``base`` yields an empty list rather than raising, which keeps
    callers simple on a fresh checkout.
    """
    if not base.exists():
        return []
    return sorted(child.name for child in base.iterdir() if child.is_dir())
