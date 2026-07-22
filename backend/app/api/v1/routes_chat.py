"""Chat endpoints: ask the explain-only assistant, and fetch the curated context.

The assistant is grounded solely on the persisted explanation context for the
day; it never runs the solver or makes scheduling decisions.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_chat_responder, get_results_store
from app.api.v1.schemas import ChatRequest
from app.chat import ChatResponder
from app.chat.intent import fast_response
from app.chat.responder import ChatResponse
from app.core.exceptions import NotFoundError
from app.explanation import ExplanationContextBuilder
from app.explanation.schema import ExplanationSummary, MachineTrendDigest
from app.services import ResultsStore

router = APIRouter(prefix="/chat", tags=["chat"])

# How many recent days to include in the machine load trend.
_TREND_DAYS = 6
# How many of the busiest current-day machines to trend.
_TREND_MACHINES = 10


def _machine_trend(
    store: ResultsStore, business_date: str, machine_ids: list[str]
) -> list[MachineTrendDigest]:
    """Per-machine scheduled-minutes series over recent days (busiest machines).

    Reads each recent day's persisted schedule and totals minutes/ops per
    machine, so the assistant can answer 'is this machine slowing down / getting
    busier over time' from real history.
    """
    if not machine_ids:
        return []
    try:
        end = date.fromisoformat(business_date)
    except ValueError:
        return []

    wanted = set(machine_ids)
    # date -> {machine_id: [minutes, ops]}
    per_day: list[tuple[str, dict[str, list[float]]]] = []
    for back in range(_TREND_DAYS - 1, -1, -1):
        day = (end - timedelta(days=back)).isoformat()
        schedule = store.load_schedule(day)
        if schedule is None:
            continue
        totals: dict[str, list[float]] = {}
        for op in schedule.scheduled_operations:
            if op.machine_id not in wanted:
                continue
            dur = (op.end - op.start).total_seconds() / 60.0
            entry = totals.setdefault(op.machine_id, [0.0, 0.0])
            entry[0] += dur
            entry[1] += 1
        per_day.append((day, totals))

    trends: list[MachineTrendDigest] = []
    for mid in machine_ids:
        series = [
            {"date": d, "minutes": round(t[mid][0]), "operations": int(t[mid][1])}
            for d, t in per_day
            if mid in t
        ]
        if len(series) < 2:
            continue
        first = series[0]["minutes"]
        last = series[-1]["minutes"]
        if last > first * 1.1:
            direction = "rising"
        elif last < first * 0.9:
            direction = "falling"
        else:
            direction = "flat"
        trends.append(
            MachineTrendDigest(machine_id=mid, series=series, direction=direction)
        )
    return trends


@router.post("/{business_date}", response_model=ChatResponse, summary="Ask the assistant")
async def ask(
    business_date: str,
    request: ChatRequest,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    responder: Annotated[ChatResponder, Depends(get_chat_responder)],
) -> ChatResponse:
    """Answer a planner question grounded on the day's explanation context."""
    # Fast path: greetings and off-topic / vague questions are answered instantly
    # and never touch the context store or the machine-trend I/O below.
    canned = fast_response(request.question)
    if canned is not None:
        return ChatResponse(
            business_date=business_date,
            question=request.question,
            answer=canned,
        )
    context = store.load_context(business_date)
    if context is None:
        raise NotFoundError(
            f"No explanation context for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    # Build the curated summary and enrich it with a real multi-day machine
    # trend so the assistant can answer 'why is this machine slowing down'.
    summary = ExplanationContextBuilder().summarize(context)
    top_machines = [m.machine_id for m in summary.machine_load[:_TREND_MACHINES]]
    trend = _machine_trend(store, business_date, top_machines)
    summary = summary.model_copy(update={"machine_trend": trend})
    return responder.answer_from_summary(summary, request.question)


@router.get(
    "/{business_date}/context",
    response_model=ExplanationSummary,
    summary="Get the curated explanation context",
)
async def get_context(
    business_date: str,
    store: Annotated[ResultsStore, Depends(get_results_store)],
) -> ExplanationSummary:
    """Return the curated explanation summary the assistant is grounded on."""
    summary = store.load_summary(business_date)
    if summary is None:
        raise NotFoundError(
            f"No explanation summary for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    return summary
