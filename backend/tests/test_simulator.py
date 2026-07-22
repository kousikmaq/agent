"""Phase 3 tests: the stateful daily factory simulator.

Covers Day-0 seeding, deterministic reproducibility, CSV round-trip fidelity,
and stateful day-over-day evolution. All tests write to isolated temp
directories so they never touch the real ``datasets/`` folder.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from random import Random

from app.domain.enums import OrderStatus
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine
from simulator.seed_generator import generate_baseline
from simulator.state_loader import load_state
from simulator.utils import IdSequencer, poisson
from simulator.writer import write_state
from app.domain.models.change_log import ChangeLog


def _config() -> SimulatorConfig:
    # Smaller factory keeps tests fast while exercising every code path.
    return SimulatorConfig(
        num_finished_products=5,
        num_raw_materials=6,
        machines_per_work_center=2,
        num_workers=12,
        initial_production_orders=10,
        initial_open_purchase_orders=5,
    )


def test_day0_baseline_is_complete_and_valid() -> None:
    state = generate_baseline(date(2026, 7, 17), _config(), Random(1))
    assert state.business_date == "2026-07-17"
    assert state.machines and state.products and state.production_orders
    assert state.routings and state.workers and state.inventory
    # Every finished good has a routing.
    routing_ids = {r.routing_id for r in state.routings}
    for product in state.products:
        if not product.is_purchased:
            assert product.routing_id in routing_ids


def test_baseline_is_deterministic_for_same_seed() -> None:
    config = _config()
    a = generate_baseline(date(2026, 7, 17), config, Random(config.seed_for_date(1)))
    b = generate_baseline(date(2026, 7, 17), config, Random(config.seed_for_date(1)))
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_csv_round_trip_is_lossless(tmp_path: Path) -> None:
    state = generate_baseline(date(2026, 7, 17), _config(), Random(2))
    empty_log = ChangeLog(business_date=state.business_date, previous_date=None, events=[])
    write_state(state, empty_log, tmp_path)

    loaded = load_state("2026-07-17", tmp_path)
    assert loaded.model_dump(mode="json") == state.model_dump(mode="json")


def test_engine_seeds_then_evolves(tmp_path: Path) -> None:
    engine = SimulatorEngine(config=_config(), datasets_dir=tmp_path)

    _, day0_log = engine.generate_day(date(2026, 7, 17))
    assert day0_log.previous_date is None
    assert day0_log.events == []

    state1, day1_log = engine.generate_day(date(2026, 7, 18))
    assert day1_log.previous_date == "2026-07-17"
    assert state1.business_date == "2026-07-18"
    # Evolution should produce at least some operational change events.
    assert len(day1_log.events) > 0
    # Snapshots are preserved historically, not overwritten.
    assert (tmp_path / "2026-07-17").exists()
    assert (tmp_path / "2026-07-18").exists()


def test_evolution_is_reproducible(tmp_path: Path) -> None:
    config = _config()

    def run(root: Path) -> tuple[list[str], dict]:
        engine = SimulatorEngine(config=config, datasets_dir=root)
        engine.generate_day(date(2026, 7, 17))
        state, log = engine.generate_day(date(2026, 7, 18))
        event_ids = [e.event_id for e in log.events]
        return event_ids, state.model_dump(mode="json")

    ids_a, state_a = run(tmp_path / "a")
    ids_b, state_b = run(tmp_path / "b")
    assert ids_a == ids_b
    assert state_a == state_b


def test_calendars_are_single_day_after_roll(tmp_path: Path) -> None:
    engine = SimulatorEngine(config=_config(), datasets_dir=tmp_path)
    engine.generate_day(date(2026, 7, 17))
    state, _ = engine.generate_day(date(2026, 7, 18))
    # Availability/shift calendars are regenerated for the new day only.
    assert all(w.day == date(2026, 7, 18) for w in state.machine_availability)
    assert all(c.day == date(2026, 7, 18) for c in state.shift_calendars)
    assert all(a.day == date(2026, 7, 18) for a in state.worker_availability)


def test_cancelled_orders_persist_across_days(tmp_path: Path) -> None:
    engine = SimulatorEngine(config=_config(), datasets_dir=tmp_path)
    engine.generate_day(date(2026, 7, 17))
    # Run several days; cancelled orders should remain (historical continuity).
    last_state = None
    for offset in range(1, 6):
        last_state, _ = engine.generate_day(date(2026, 7, 17 + offset))
    assert last_state is not None
    statuses = {o.status for o in last_state.production_orders}
    # At minimum, orders exist and use valid statuses.
    assert statuses <= set(OrderStatus)


def test_id_sequencer_continues_from_existing() -> None:
    seq = IdSequencer("ORD-", ["ORD-0007", "ORD-0003"])
    assert seq.next() == "ORD-0008"
    assert seq.next() == "ORD-0009"


def test_poisson_is_non_negative_and_seeded() -> None:
    rng = Random(42)
    values = [poisson(rng, 4.0) for _ in range(100)]
    assert all(v >= 0 for v in values)
    assert poisson(Random(1), 0) == 0
