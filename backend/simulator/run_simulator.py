"""CLI entrypoint for the stateful daily factory simulator.

Examples
--------
Generate today's snapshot (seeds Day-0 if none exists)::

    python -m simulator.run_simulator

Generate a specific day::

    python -m simulator.run_simulator --date 2026-07-18

Generate a contiguous range of days (each evolves from the previous)::

    python -m simulator.run_simulator --start 2026-07-17 --days 5
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.utils.datetime_utils import parse_business_date
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine

logger = get_logger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate stateful daily manufacturing datasets."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Single business date to generate (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date for a range (YYYY-MM-DD). Use with --days.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of consecutive days to generate from --start (default 1).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the base RNG seed for reproducibility.",
    )
    return parser.parse_args(argv)


def _resolve_dates(args: argparse.Namespace) -> list[date]:
    """Determine the ordered list of business dates to generate."""
    if args.start:
        start = parse_business_date(args.start)
        return [start + timedelta(days=offset) for offset in range(max(1, args.days))]
    if args.date:
        return [parse_business_date(args.date)]
    return [date.today()]


def main(argv: list[str] | None = None) -> int:
    """Run the simulator for the requested date(s)."""
    settings = get_settings()
    configure_logging(settings)

    args = _parse_args(argv)
    config = SimulatorConfig()
    if args.seed is not None:
        config = config.model_copy(update={"base_seed": args.seed})

    engine = SimulatorEngine(config=config, datasets_dir=settings.datasets_dir)

    for business_date in _resolve_dates(args):
        _, change_log = engine.generate_day(business_date)
        logger.info(
            "Generated %s with %d change events.",
            change_log.business_date,
            len(change_log.events),
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
