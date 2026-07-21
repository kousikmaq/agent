"""
FastAPI entry point for the Production Planning & Schedule Optimization Agent.

Run:  uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from logging_config import setup_logging, get_logger
from models import (WeekLoad, OverviewResult, HeatmapResult, PriorityResult,
                    AllocationResult, SchedulePlan, DelayRiskResult, DemandVsCapacity,
                    ScenarioComparison, DatasetSummary, FeatureStatus, AgentAsk, AgentReply)
from data_loader import dataset_counts, load
from services.capacity import analyze_week, overview, heatmap, list_weeks, default_week
from services.prioritize import prioritize_week
from services.allocate import allocate_week
from services.schedule import optimize_week
from services.risk import delay_risk_week
from services.demand import demand_vs_capacity
from services.scenarios import scenarios
from services.stubs import stub
from agent.planner_agent import ask_agent

setup_logging()
log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("Production Planning Agent API starting up")
    log.info("Interactive API docs available at  /docs")
    log.info("=" * 60)
    yield


app = FastAPI(title="Production Planning Agent", version="0.3.0", lifespan=lifespan)


def _parse_week(week: str | None) -> date:
    """Validate the ?week= param, defaulting to the busiest week."""
    if not week:
        return default_week()
    try:
        wk = date.fromisoformat(week)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid week '{week}', expected YYYY-MM-DD.")
    if wk not in load()["weeks"]:
        raise HTTPException(status_code=404, detail=f"No orders for week {week}.")
    return wk

app.add_middleware(
    CORSMiddleware,
    # Allow any localhost port during development (the Vite port can vary).
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    log.info("GET /api/health")
    return {"status": "ok"}


@app.get("/api/dataset/summary", response_model=DatasetSummary)
def dataset_summary():
    """Row counts per table + the weeks in the order book (for the dashboard)."""
    log.info("GET /api/dataset/summary")
    d = load()
    return DatasetSummary(tables=dataset_counts(), total_orders=d["counts"]["orders"],
                          weeks=[w.isoformat() for w in d["weeks"]])


@app.get("/api/weeks")
def weeks():
    """List of week-start dates available for capacity drill-down."""
    log.info("GET /api/weeks")
    return {"weeks": list_weeks(), "default": default_week().isoformat()}


@app.get("/api/capacity/overview", response_model=OverviewResult)
def capacity_overview():
    """BULK: capacity utilisation for every week of the order book, in one pass."""
    log.info("GET /api/capacity/overview")
    return overview()


@app.get("/api/capacity/heatmap", response_model=HeatmapResult)
def capacity_heatmap():
    """Work-centre x week utilisation grid (the classic capacity heatmap)."""
    log.info("GET /api/capacity/heatmap")
    return heatmap()


@app.get("/api/capacity", response_model=WeekLoad)
def capacity_week(week: str | None = Query(default=None, description="week start YYYY-MM-DD")):
    """Capacity analysis for one week (defaults to the most overloaded week)."""
    log.info("GET /api/capacity | week=%s", week)
    return analyze_week(_parse_week(week))


@app.get("/api/priority", response_model=PriorityResult)
def priority_week(week: str | None = Query(default=None, description="week start YYYY-MM-DD")):
    """Order prioritization for one week (EDD + Critical Ratio + customer/penalty)."""
    log.info("GET /api/priority | week=%s", week)
    return prioritize_week(_parse_week(week))


@app.get("/api/allocate", response_model=AllocationResult)
def allocate_week_ep(week: str | None = Query(default=None, description="week start YYYY-MM-DD")):
    """Resource allocation: offload overloaded machines to idle backups (before/after)."""
    log.info("GET /api/allocate | week=%s", week)
    return allocate_week(_parse_week(week))


@app.get("/api/schedule", response_model=SchedulePlan)
def schedule_week_ep(week: str | None = Query(default=None, description="week start YYYY-MM-DD"),
                     n: int = Query(default=12, ge=1, le=25, description="how many top orders to schedule")):
    """Schedule optimization (OR-Tools CP-SAT) for the top-N urgent orders of a week."""
    log.info("GET /api/schedule | week=%s n=%s", week, n)
    return optimize_week(_parse_week(week), n)


@app.get("/api/risk", response_model=DelayRiskResult)
def delay_risk_ep(week: str | None = Query(default=None, description="week start YYYY-MM-DD")):
    """Delay risk: material feasibility (BOM vs inventory) + capacity risk, with fixes."""
    log.info("GET /api/risk | week=%s", week)
    return delay_risk_week(_parse_week(week))


@app.get("/api/demand", response_model=DemandVsCapacity)
def demand_ep():
    """Demand vs capacity across the whole horizon: can we commit to the order book?"""
    log.info("GET /api/demand")
    return demand_vs_capacity()


@app.get("/api/scenarios", response_model=ScenarioComparison)
def scenarios_ep(week: str | None = Query(default=None, description="week start YYYY-MM-DD")):
    """What-if planning scenarios for a week: baseline vs add-a-shift vs defer orders."""
    log.info("GET /api/scenarios | week=%s", week)
    return scenarios(_parse_week(week))


@app.get("/api/features", response_model=list[FeatureStatus])
def features():
    """The full roadmap, so the dashboard can show what is live vs planned."""
    log.info("GET /api/features")
    return [
        FeatureStatus(key="capacity", name="Capacity analysis", status="implemented",
                      description="Weekly work needed vs hours available per machine, with overload flags."),
        FeatureStatus(key="bottleneck", name="Bottleneck detection", status="implemented",
                      description="The busiest machine that limits throughput (from capacity)."),
        FeatureStatus(key="batch_bulk", name="Bulk processing", status="implemented",
                      description="Analyse the whole order book (every week) in one pass."),
        FeatureStatus(key="batch_campaign", name="Batch/campaign insight", status="implemented",
                      description="Setup hours saved by running same-item orders as one campaign."),
        FeatureStatus(key="optimization", name="Schedule optimization", status="implemented",
                      description="OR-Tools CP-SAT feasible sequence (Gantt) minimising makespan."),
        FeatureStatus(key="demand_vs_capacity", name="Demand vs capacity", status="implemented",
                      description="Horizon-level: can we commit to the whole order book? Gap + fix."),
        FeatureStatus(key="scenarios", name="What-if scenarios", status="implemented",
                      description="Compare baseline vs add-a-shift vs defer-orders for a week."),
        FeatureStatus(key="prioritization", name="Order prioritization", status="implemented",
                      description="EDD + Critical Ratio + customer/penalty weight."),
        FeatureStatus(key="allocation", name="Resource allocation", status="implemented",
                      description="Move work to an idle qualified backup machine (before/after)."),
        FeatureStatus(key="delay_risk", name="Delay risk", status="implemented",
                      description="Late orders + material feasibility (BOM vs inventory) with a fix."),
    ]


@app.get("/api/features/{key}")
def feature_detail(key: str):
    """Stub endpoint for planned features."""
    log.info("GET /api/features/%s", key)
    return stub(key)


@app.post("/api/agent/ask", response_model=AgentReply)
async def agent_ask(body: AgentAsk):
    """Ask the planning copilot a question in plain language."""
    log.info("POST /api/agent/ask")
    answer, used_llm = await ask_agent(body.question)
    return AgentReply(answer=answer, used_llm=used_llm)
