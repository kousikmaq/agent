"""FastAPI application: chat (REST + WebSocket), read-only analysis endpoints, and a single
confirmed action-execute endpoint (human-in-the-loop). CORS is restricted to configured
origins; all request bodies are validated by Pydantic."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.actions.chart_action import generate_chart
from app.actions.email_action import send_alert_email
from app.actions.export_action import export_schedule
from app.actions.reorder_action import place_reorder, reorder_recommendations
from app.agents.chat_client import azure_available
from app.agents.service import answer
from app.analytics.allocation import allocate_resources
from app.analytics.bottleneck import detect_bottlenecks
from app.analytics.capacity import capacity_analysis
from app.analytics.prioritization import prioritize_orders
from app.api_schemas import ActionRequest, ChatRequest
from app.cache.semantic_cache import get_cache
from app.config import settings
from app.logging_config import log, setup_logging
from app.ml import explain, registry
from app.optimization.scheduler import compare_scenarios, optimize_schedule

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On first boot, generate data + train models if missing (no-op once ready).
    setup_logging()
    log.info("=" * 60)
    log.info("STARTUP Production Planning & Schedule Optimization Agent")
    log.info("STARTUP LLM configured: %s", azure_available())
    if settings.auto_setup:
        try:
            from app.setup import ensure_ready
            log.info("STARTUP checking dataset + trained models...")
            ensure_ready()
            log.info("STARTUP data + models ready")
        except Exception as exc:  # noqa: BLE001 - never block startup on setup issues
            log.warning("STARTUP auto-setup skipped: %s: %s", type(exc).__name__, exc)
    log.info("STARTUP ready - serving on the configured port")
    log.info("=" * 60)
    yield
    log.info("SHUTDOWN server stopping")


app = FastAPI(
    title="Production Planning & Schedule Optimization Agent",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _safe(fn, *args, **kwargs):
    """Run an analysis function, converting a missing-model error into a clean payload."""
    try:
        return fn(*args, **kwargs)
    except registry.ModelNotTrainedError as exc:
        return {"error": str(exc)}


# ---- meta -----------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict:
    return {
        "llm_configured": azure_available(),
        "models_trained": registry.models_available(),
        "model_metrics": registry.metrics(),
        "cache": get_cache().stats(),
    }


# ---- chat -----------------------------------------------------------------
@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    return await answer(req.query, use_cache=req.use_cache)


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            query = str(data.get("query", ""))
            await ws.send_json({"type": "status", "message": "Analysing your question..."})
            result = await answer(query, use_cache=bool(data.get("use_cache", True)))
            await ws.send_json({"type": "answer", "payload": result})
    except WebSocketDisconnect:
        return


# ---- read-only analysis ---------------------------------------------------
@app.get("/api/capacity")
def api_capacity(horizon_days: int = 7) -> dict:
    return capacity_analysis(horizon_days)


@app.get("/api/bottlenecks")
def api_bottlenecks(horizon_days: int = 7) -> dict:
    return detect_bottlenecks(horizon_days)


@app.get("/api/prioritize")
def api_prioritize(top_n: int = 10) -> dict:
    return prioritize_orders(top_n)


@app.get("/api/allocation")
def api_allocation() -> dict:
    return allocate_resources()


@app.get("/api/schedule")
def api_schedule(scenario: str = "min_risk", max_orders: int = 12) -> dict:
    return optimize_schedule(scenario=scenario, max_orders=max_orders)


@app.get("/api/scenarios")
def api_scenarios(max_orders: int = 12) -> dict:
    return compare_scenarios(max_orders=max_orders)


@app.get("/api/risk/delay")
def api_delay(top_n: int = 8) -> dict:
    return _safe(explain.explain_delay_risk, top_n)


@app.get("/api/risk/downtime")
def api_downtime() -> dict:
    return _safe(explain.explain_downtime)


@app.get("/api/risk/orders")
def api_order_risk(top_n: int = 10) -> dict:
    return _safe(registry.predict_order_due_risk, top_n)


@app.get("/api/demand")
def api_demand(horizon_days: int = 7) -> dict:
    return _safe(explain.explain_demand, horizon_days)


@app.get("/api/demand/stockout")
def api_stockout(top_n: int = 10) -> dict:
    return _safe(registry.demand_stockout_risk, top_n)


@app.get("/api/demand/regions")
def api_regions() -> dict:
    return _safe(registry.demand_region_split)


@app.get("/api/demand/forecast")
def api_demand_forecast(horizon_days: int = 7) -> dict:
    """Structured per-SKU forecast with P10/P50/P90 band + revenue (for the band chart view)."""
    return _safe(registry.forecast_demand, horizon_days)


@app.get("/api/machines")
def api_machines(horizon_days: int = 7) -> dict:
    """Per-machine health view: capacity utilisation merged with ML downtime risk / health /
    failure type / maintenance window (for the Machines control-tower view)."""
    def _build() -> dict:
        cap = capacity_analysis(horizon_days)
        health = {m["machine_id"]: m for m in registry.predict_downtime_latest()["machines"]}
        machines = []
        for m in cap["per_machine"]:
            h = health.get(m["machine_id"], {})
            machines.append({
                "machine_id": m["machine_id"],
                "machine_name": m["machine_name"],
                "utilization_pct": m["utilization_pct"],
                "p90_utilization_pct": m["p90_utilization_pct"],
                "required_hours": m["required_hours"],
                "available_hours": m["available_hours"],
                "expected_shortfall_hours": m["expected_shortfall_hours"],
                "status": m["status"],
                "downtime_risk_pct": h.get("downtime_risk_pct", 0.0),
                "health_index": h.get("health_index", 100.0),
                "failure_type": h.get("failure_type", "None"),
                "alert": h.get("alert", False),
            })
        return {"machines": machines, "constrained_machines": cap["constrained_machines"],
                "machines_at_risk": [m["machine_id"] for m in machines if m["alert"]]}
    return _safe(_build)


@app.get("/api/reorder/recommendations")
def api_reorder_recs(horizon_days: int = 7) -> dict:
    return reorder_recommendations(horizon_days)


@app.get("/api/metrics")
def api_metrics() -> dict:
    return registry.metrics()


# ---- weekly master plan (proactive baseline) ------------------------------
@app.get("/api/plan")
def api_plan(scenario: str = "min_risk") -> dict:
    from app.planning import get_weekly_plan
    return _safe(get_weekly_plan, scenario)


@app.post("/api/plan/regenerate")
def api_plan_regenerate(scenario: str = "min_risk") -> dict:
    from app.planning import get_weekly_plan
    return _safe(get_weekly_plan, scenario, True)


# ---- confirmed actions (human-in-the-loop) --------------------------------
_ACTIONS = {"send_email", "place_reorder", "generate_chart", "export_plan", "email_chart"}


@app.post("/api/actions/execute")
def execute_action(req: ActionRequest) -> dict:
    aid, p = req.id, req.params
    log.info("ACTION requested id=%s params=%s", aid, {k: p.get(k) for k in list(p)[:4]})
    if aid not in _ACTIONS:
        log.warning("ACTION rejected: unknown id=%s", aid)
        return {"status": "error", "error": f"unknown action '{aid}'"}
    if aid == "send_email":
        res = send_alert_email(p.get("subject", ""), p.get("body", ""), p.get("to"),
                               attachment=p.get("attachment"))
    elif aid == "email_chart":
        res = send_alert_email(
            p.get("subject", "Production insight chart"),
            p.get("body", "Please find the attached production insight chart."),
            p.get("to"), attachment=p.get("filename"))
    elif aid == "place_reorder":
        res = place_reorder(p.get("material_id", ""), p.get("quantity", 0), p.get("reason", ""))
    elif aid == "generate_chart":
        res = generate_chart(p.get("kind", ""), p.get("chart_type"))
    elif aid == "export_plan":
        res = export_schedule(p.get("scenario", "min_risk"), int(p.get("max_orders", 12)))
    else:
        res = {"status": "error", "error": "unhandled action"}
    log.info("ACTION done id=%s -> status=%s", aid, res.get("status"))
    return res
