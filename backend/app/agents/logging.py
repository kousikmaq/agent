"""Agent logging helpers.

Thin wrapper over the application logger so every agent logs under a consistent
``agents.<name>`` namespace without importing the core logging module directly.
"""

from __future__ import annotations

import logging

from app.core.logging import get_logger


def get_agent_logger(name: str) -> logging.Logger:
    """Return a logger scoped to an agent (``agents.<name>``)."""
    return get_logger(f"agents.{name}")


def get_workflow_logger() -> logging.Logger:
    """Return the orchestration-level workflow logger."""
    return get_logger("agents.workflow")
