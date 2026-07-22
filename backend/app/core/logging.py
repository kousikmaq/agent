"""Centralised logging configuration.

Provides a single :func:`configure_logging` entrypoint that sets up either
human-readable console logging (development) or structured JSON logging
(production / log aggregation), driven by application settings.
"""

from __future__ import annotations

import logging
import sys
from logging.config import dictConfig

from app.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure the root logger according to application settings.

    Parameters
    ----------
    settings:
        The active application settings. ``log_level`` controls verbosity and
        ``log_json`` toggles structured JSON output suitable for log
        aggregation systems.
    """
    if settings.log_json:
        formatter = {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    else:
        formatter = {
            "format": (
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            ),
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": formatter},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": sys.stdout,
                }
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console"],
            },
            # Align noisy third-party loggers with our configured level.
            "loggers": {
                "uvicorn": {"level": settings.log_level, "propagate": False,
                            "handlers": ["console"]},
                "uvicorn.error": {"level": settings.log_level,
                                  "propagate": False, "handlers": ["console"]},
                "uvicorn.access": {"level": settings.log_level,
                                   "propagate": False, "handlers": ["console"]},
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger.

    Thin convenience wrapper around :func:`logging.getLogger` so feature
    modules import a single symbol instead of the stdlib directly.
    """
    return logging.getLogger(name)
