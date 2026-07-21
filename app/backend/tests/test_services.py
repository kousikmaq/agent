"""
Fast regression tests for the planning services. Run from app/backend:
    .venv\\Scripts\\python.exe -m pytest
"""
from services.capacity import overview, analyze_week, heatmap, default_week, list_weeks
from services.prioritize import prioritize_week
from services.allocate import allocate_week
from services.risk import delay_risk_week
from services.demand import demand_vs_capacity
from services.scenarios import scenarios
from data_loader import load


def test_overview_shape():
    ov = overview()
    assert len(ov.weeks) == len(load()["weeks"])
    assert 0 <= ov.overloaded_weeks <= len(ov.weeks)
    assert ov.total_orders == 520


def test_default_week_has_bottleneck():
    wl = analyze_week(default_week())
    assert wl.bottleneck is not None
    assert wl.bottleneck.utilization_pct > 100


def test_heatmap_shape():
    hm = heatmap()
    assert len(hm.rows) == len(load()["work_centers"])
    for row in hm.rows:
        assert len(row.cells) == len(hm.weeks)


def test_priority_ranked_and_bounded():
    r = prioritize_week(default_week())
    scores = [o.score for o in r.orders]
    assert scores == sorted(scores, reverse=True)          # highest urgency first
    assert all(0 <= s <= 100 for s in scores)
    assert [o.rank for o in r.orders] == list(range(1, len(r.orders) + 1))


def test_priority_at_risk_consistent():
    for o in prioritize_week(default_week()).orders:
        if o.at_risk:
            assert o.critical_ratio < 1.0


def test_allocation_never_worsens():
    r = allocate_week(default_week())
    assert r.overloads_after <= r.overloads_before
    assert r.hours_moved >= 0
    # a machine that received work must never end up overloaded because of it
    for s in r.states:
        assert not (s.status_before == "OK" and s.status_after == "OVERLOADED")


def test_default_week_is_valid():
    assert default_week().isoformat() in list_weeks()


def test_delay_risk_consistent():
    r = delay_risk_week(default_week())
    assert 0 <= r.at_risk_count <= r.orders_considered
    # every shortage is a genuine shortfall
    for s in r.shortages:
        assert s.shortfall > 0 and s.required > s.available
    # an at-risk order must have at least one stated cause
    for o in r.orders:
        assert o.at_risk == bool(o.causes)


def test_demand_vs_capacity_totals():
    dc = demand_vs_capacity()
    assert dc.horizon_weeks == len(load()["weeks"])
    # overall totals equal the sum over resources
    assert round(sum(r.required_hours for r in dc.resources), 1) == dc.overall_required_hours
    assert dc.overall_feasible == (dc.overall_gap_hours == 0)


def test_scenarios_three_and_helpful():
    c = scenarios(default_week())
    assert len(c.scenarios) >= 3                       # brief requires >= 3 scenarios
    base = next(s for s in c.scenarios if s.key == "baseline")
    defer = next(s for s in c.scenarios if s.key == "defer")
    # deferring orders must not increase the overload count
    assert defer.overloaded_count <= base.overloaded_count
