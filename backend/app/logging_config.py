"""Readable, step-by-step application logging (portable ASCII, no noisy 200-only lines)."""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the 'planner' logger once with a clean, human-readable format."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger = logging.getLogger("planner")
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True


def get_logger() -> logging.Logger:
    setup_logging()
    return logging.getLogger("planner")


log = get_logger()
