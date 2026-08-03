"""Tests for the SQLite snapshot store and SQLite-first data source.

The simulator writes each day to CSV *and* (dual-write) to ``datasets/factory.db``.
These tests prove the SQLite round-trip is identical to the CSV round-trip, that
the store lists its dates, and that :class:`SqliteDataSource` falls back to CSV
for a date not present in the database.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.ingestion import CsvDataSource, SqliteDataSource
from app.ingestion.sqlite_store import FactorySqliteStore, get_factory_store
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine

BIZ_DATE = "2026-07-17"
NEXT_DATE = "2026-07-18"


def _small_config() -> SimulatorConfig:
    return SimulatorConfig(
        num_finished_products=5,
        num_raw_materials=6,
        machines_per_work_center=2,
        num_workers=12,
        initial_production_orders=10,
        initial_open_purchase_orders=5,
    )


@pytest.fixture()
def datasets_dir(tmp_path: Path) -> Path:
    """Generate two evolving days (dual-written to CSV + SQLite)."""
    engine = SimulatorEngine(config=_small_config(), datasets_dir=tmp_path)
    engine.generate_day(date(2026, 7, 17))
    engine.generate_day(date(2026, 7, 18))
    return tmp_path


def test_dual_write_creates_database(datasets_dir: Path) -> None:
    assert (datasets_dir / "factory.db").exists()


def test_store_lists_written_dates(datasets_dir: Path) -> None:
    store = get_factory_store(datasets_dir)
    assert store.available_dates() == [BIZ_DATE, NEXT_DATE]


def test_sqlite_load_matches_csv_load(datasets_dir: Path) -> None:
    csv_state = CsvDataSource(datasets_dir).load(BIZ_DATE)
    sqlite_state = get_factory_store(datasets_dir).load_state(BIZ_DATE)
    assert sqlite_state is not None
    assert sqlite_state.model_dump() == csv_state.model_dump()


def test_sqlite_data_source_reads_from_database(datasets_dir: Path) -> None:
    source = SqliteDataSource(datasets_dir)
    assert source.load(NEXT_DATE).model_dump() == (
        CsvDataSource(datasets_dir).load(NEXT_DATE).model_dump()
    )
    assert source.available_dates() == [BIZ_DATE, NEXT_DATE]


def test_sqlite_data_source_falls_back_to_csv(datasets_dir: Path) -> None:
    # A date present only on disk (not in the DB) is served from CSV.
    store = FactorySqliteStore(datasets_dir / "factory.db")
    csv_only = CsvDataSource(datasets_dir).load(BIZ_DATE)
    with store._connect() as conn:  # noqa: SLF001 - test manipulates DB directly
        conn.execute("DELETE FROM _snapshots WHERE business_date = ?", (BIZ_DATE,))
    source = SqliteDataSource(datasets_dir)
    assert source.load(BIZ_DATE).model_dump() == csv_only.model_dump()


def test_change_log_is_persisted(datasets_dir: Path) -> None:
    # The evolved day (07-18) carries change events; they land in the DB.
    store = FactorySqliteStore(datasets_dir / "factory.db")
    with store._connect() as conn:  # noqa: SLF001 - direct read for assertion
        count = conn.execute(
            "SELECT COUNT(1) FROM change_log WHERE business_date = ?", (NEXT_DATE,)
        ).fetchone()[0]
    assert count > 0

