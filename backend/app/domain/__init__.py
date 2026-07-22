"""Domain core package.

Holds the pure, deterministic business layer: canonical models, enums, DTOs,
and common interfaces. Business logic (rules, optimization, analytics, risk,
recommendation, scenario, explanation) is added in later phases. This package
must remain free of I/O, framework, ML, and LLM dependencies.
"""

from __future__ import annotations

from app.domain import enums, interfaces

__all__ = ["enums", "interfaces"]
