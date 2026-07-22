"""Phase 4 tests: the data ingestion layer.

Covers the CSV adapter, cross-entity validators, the loader (with dependency
injection), and the snapshot manager. Snapshots are produced by the simulator
into temp dirs so tests verify the shared CSV contract end to end.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from random import Random

import pytest

from app.core.exceptions import DataIngestionError, ValidationError
from app.domain.models.factory_state import FactoryState
from app.ingestion import (
    CsvDataSource,
    FactoryStateLoader,
    SnapshotManager,
    load_factory_state,
    validate_factory_state,
)
from app.ingestion.base import DataSource
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine
from simulator.seed_generator import generate_baseline


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
    """Generate two evolving days into a temp datasets directory."""
    engine = SimulatorEngine(config=_small_config(), datasets_dir=tmp_path)
    engine.generate_day(date(2026, 7, 17))
    engine.generate_day(date(2026, 7, 18))
    return tmp_path


def test_csv_source_implements_port(datasets_dir: Path) -> None:
    source = CsvDataSource(datasets_dir)
    assert isinstance(source, DataSource)
    assert source.available_dates() == ["2026-07-17", "2026-07-18"]


def test_csv_source_loads_valid_factory_state(datasets_dir: Path) -> None:
    state = CsvDataSource(datasets_dir).load("2026-07-17")
    assert isinstance(state, FactoryState)
    assert state.business_date == "2026-07-17"
    assert state.machines and state.production_orders and state.routings


def test_csv_source_round_trips_simulator_output(datasets_dir: Path) -> None:
    # A simulator snapshot ingests losslessly (shared CSV contract).
    config = _small_config()
    expected = generate_baseline(date(2026, 7, 17), config, Random(config.seed_for_date(date(2026, 7, 17).toordinal())))
    loaded = CsvDataSource(datasets_dir).load("2026-07-17")
    assert loaded.model_dump(mode="json") == expected.model_dump(mode="json")


def test_missing_snapshot_raises(datasets_dir: Path) -> None:
    with pytest.raises(DataIngestionError):
        CsvDataSource(datasets_dir).load("2099-01-01")


def test_loader_returns_validated_state(datasets_dir: Path) -> None:
    state = load_factory_state("2026-07-18", datasets_dir)
    assert isinstance(state, FactoryState)


def test_validation_passes_for_generated_data(datasets_dir: Path) -> None:
    state = CsvDataSource(datasets_dir).load("2026-07-18")
    result = validate_factory_state(state)
    assert not result.has_errors


def test_validation_detects_dangling_reference(datasets_dir: Path) -> None:
    state = CsvDataSource(datasets_dir).load("2026-07-17")
    # Point an order at a non-existent product.
    state.production_orders[0].product_id = "GHOST-PRODUCT"
    result = validate_factory_state(state)
    assert result.has_errors
    assert any(i.code == "order_product_not_found" for i in result.errors)


def test_loader_raises_on_fatal_validation(datasets_dir: Path) -> None:
    class _BrokenSource(DataSource):
        def load(self, business_date: str) -> FactoryState:
            state = CsvDataSource(datasets_dir).load("2026-07-17")
            state.inventory[0].product_id = "GHOST"
            return state

        def available_dates(self) -> list[str]:
            return ["2026-07-17"]

    loader = FactoryStateLoader(_BrokenSource())
    with pytest.raises(ValidationError):
        loader.load("2026-07-17")


def test_loader_can_skip_validation(datasets_dir: Path) -> None:
    class _BrokenSource(DataSource):
        def load(self, business_date: str) -> FactoryState:
            state = CsvDataSource(datasets_dir).load("2026-07-17")
            state.inventory[0].product_id = "GHOST"
            return state

        def available_dates(self) -> list[str]:
            return ["2026-07-17"]

    loader = FactoryStateLoader(_BrokenSource(), validate=False)
    state = loader.load("2026-07-17")  # does not raise
    assert isinstance(state, FactoryState)


def test_snapshot_manager_save_and_reload(datasets_dir: Path, tmp_path: Path) -> None:
    original = CsvDataSource(datasets_dir).load("2026-07-18")

    target = tmp_path / "persisted"
    manager = SnapshotManager(target)
    assert not manager.exists("2026-07-18")

    manager.save(original)
    assert manager.exists("2026-07-18")
    assert manager.latest_date() == "2026-07-18"

    reloaded = manager.load("2026-07-18")
    assert reloaded.model_dump(mode="json") == original.model_dump(mode="json")
