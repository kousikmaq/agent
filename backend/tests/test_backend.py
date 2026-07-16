"""Backend test suite: data, analytics, ML, optimization, cache, actions and the API.
Run from the backend/ directory:  python -m pytest -q"""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app import data_access as da
from app.actions.chart_action import generate_chart
from app.actions.email_action import send_alert_email
from app.actions.export_action import export_schedule
from app.actions.reorder_action import place_reorder
from app.agents.service import answer
from app.analytics.bottleneck import detect_bottlenecks
from app.analytics.capacity import capacity_analysis
from app.cache.semantic_cache import SemanticCache
from app.main import app
from app.ml import registry
from app.optimization.scheduler import optimize_schedule

client = TestClient(app)


# ---- data ----
def test_data_row_counts_and_keys():
    assert len(da.job_operations()) >= 500
    assert len(da.orders()) == 500
    assert set(da.machines()["machine_id"]) == {"M01", "M02", "M03", "M04", "M05"}
    # every job references a valid order
    assert da.job_operations()["order_id"].isin(set(da.orders()["order_id"])).all()


# ---- analytics ----
def test_capacity_and_bottleneck():
    cap = capacity_analysis()
    assert "overall_utilization_pct" in cap and cap["per_machine"]
    bn = detect_bottlenecks()
    assert bn["primary_bottleneck"] in set(da.machines()["machine_id"])


# ---- ML ----
def test_models_available_and_metrics():
    assert registry.models_available()
    m = registry.metrics()
    assert m["delay_risk"]["macro_f1"] >= 0.7
    assert m["downtime"]["f1"] >= 0.7
    assert m["demand"]["mape_pct"] < m["demand"]["baseline_mape_pct"]
    # added targets
    assert m["duration"]["r2"] > 0.3
    assert m["downtime_duration"]["r2"] > 0.3
    assert m["failure_type"]["macro_f1"] >= 0.6
    assert m["demand_quantiles"]["p10_p90_coverage"] >= 0.7
    assert m["stockout"]["f1"] >= 0.6


def test_predictions_run():
    assert "at_risk" in registry.predict_delay_for_pending(top_n=5)
    assert "machines" in registry.predict_downtime_latest()
    assert registry.forecast_demand(7)["products"]


def test_new_target_outputs():
    d = registry.predict_delay_for_pending(top_n=3)["at_risk"][0]
    assert "expected_delay_days" in d and "likely_cause" in d and "p90_delay_hours" in d
    assert "at_risk_orders" in registry.predict_order_due_risk(5)
    m = registry.predict_downtime_latest()["machines"][0]
    assert "health_index" in m and "failure_type" in m and "anomaly_score" in m
    f = registry.forecast_demand(7)["products"][0]
    assert "p10_units_total" in f and "p90_units_total" in f and "forecast_revenue" in f
    assert "products" in registry.demand_stockout_risk(3)
    assert "region_share_pct" in registry.demand_region_split()


# ---- optimization ----
def test_schedule_feasible_all_scenarios():
    for sc in ("max_throughput", "min_risk", "min_cost"):
        plan = optimize_schedule(sc, max_orders=8)
        assert plan["assignments"], f"no plan for {sc}"
        assert plan["kpis"]["solver_status"] in ("OPTIMAL", "FEASIBLE")


# ---- cache ----
def test_cache_roundtrip(tmp_path):
    c = SemanticCache(db_path=str(tmp_path / "c.db"))
    assert c.get("q") is None
    c.set("Hello  World", {"x": 1})
    assert c.get("hello world") == {"x": 1}  # normalised match
    assert c.stats()["entries"] == 1


# ---- actions ----
def test_actions_safe():
    assert send_alert_email("s", "b", "ops@example.com")["status"] in ("sent", "simulated")
    assert send_alert_email("s", "b", "not-an-email")["status"] == "error"
    assert place_reorder("MAT001", 100)["status"] == "placed"
    assert place_reorder("BAD", 100)["status"] == "error"
    assert place_reorder("MAT001", -5)["status"] == "error"
    assert generate_chart("capacity")["status"] == "ok"
    assert generate_chart("nope")["status"] == "error"
    assert export_schedule("min_risk", 6)["status"] == "ok"


# ---- service (deterministic path) ----
def test_answer_service():
    res = asyncio.run(answer("where is the bottleneck?", use_cache=False))
    assert res["intent"] == "bottleneck"
    assert res["message"] and "suggested_actions" in res


# ---- API ----
def test_api_status_and_analysis():
    assert client.get("/health").json()["status"] == "ok"
    st = client.get("/api/status").json()
    assert st["models_trained"] is True
    assert client.get("/api/capacity").json()["per_machine"]
    assert client.get("/api/schedule?scenario=min_cost&max_orders=6").json()["assignments"]
    assert client.get("/api/risk/delay").json()["type"] == "delay_risk"


def test_api_chat_and_action():
    r = client.post("/api/chat", json={"query": "show me delay risk", "use_cache": False}).json()
    assert r["intent"] == "delay_risk"
    act = client.post("/api/actions/execute",
                      json={"id": "generate_chart", "params": {"kind": "downtime"}}).json()
    assert act["status"] == "ok"
    bad = client.post("/api/actions/execute", json={"id": "hack", "params": {}}).json()
    assert bad["status"] == "error"


def test_api_websocket():
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"query": "capacity status", "use_cache": False})
        assert ws.receive_json()["type"] == "status"
        assert ws.receive_json()["type"] == "answer"
