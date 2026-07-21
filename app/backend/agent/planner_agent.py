"""
The planning copilot.

Primary path: Azure OpenAI (chat completions with tool-calling). The model calls
the deterministic planning tools and explains the result in plain language.

Fallback path: if Azure OpenAI is not configured, we answer from a simple template
built on the SAME deterministic capacity result. The app always works.

Golden rule: the numbers always come from the engine tools, never invented.
"""
import json
import os

from logging_config import get_logger
from services.capacity import analyze_week, overview, default_week
from services.prioritize import prioritize_week
from services.allocate import allocate_week
from services.risk import delay_risk_week
from services.demand import demand_vs_capacity
from services.scenarios import scenarios

log = get_logger("agent")


def analyze_capacity() -> str:
    """Analyze the busiest week's production capacity. Returns JSON with each work
    centre's required vs available hours, utilisation percent, and the bottleneck."""
    log.info("AGENT TOOL  analyze_capacity() called")
    return json.dumps(analyze_week(default_week()).model_dump())


def capacity_overview() -> str:
    """Return a JSON summary of capacity utilisation for every week of the order
    book (bulk view), including which weeks are overloaded."""
    log.info("AGENT TOOL  capacity_overview() called")
    return json.dumps(overview().model_dump())


def order_priority() -> str:
    """Return the prioritised order list for the busiest week: which orders to run
    first and why (due date, critical ratio, customer tier, penalty)."""
    log.info("AGENT TOOL  order_priority() called")
    res = prioritize_week(default_week())
    top = res.model_dump()
    top["orders"] = top["orders"][:10]  # keep the prompt small
    return json.dumps(top)


def resource_allocation() -> str:
    """Return the recommended reallocations for the busiest week: move work off
    overloaded machines onto idle backups, with the before/after balance."""
    log.info("AGENT TOOL  resource_allocation() called")
    return json.dumps(allocate_week(default_week()).model_dump())


def delay_risk() -> str:
    """Return the delay-risk report for the busiest week: at-risk orders, which
    components are short (material), and capacity risk, with fixes."""
    log.info("AGENT TOOL  delay_risk() called")
    res = delay_risk_week(default_week())
    out = res.model_dump()
    out["orders"] = [o for o in out["orders"] if o["at_risk"]][:10]
    return json.dumps(out)


def demand_vs_capacity_tool() -> str:
    """Return the horizon-level demand-vs-capacity check: whether the whole order
    book can be committed, total load, gaps, and which weeks are overloaded."""
    log.info("AGENT TOOL  demand_vs_capacity() called")
    return json.dumps(demand_vs_capacity().model_dump())


def what_if_scenarios() -> str:
    """Return what-if scenarios for the busiest week: baseline vs adding a shift vs
    deferring the least-urgent orders, with the effect on the bottleneck."""
    log.info("AGENT TOOL  what_if_scenarios() called")
    return json.dumps(scenarios(default_week()).model_dump())


# ---- Azure OpenAI copilot (tool-calling) ----
_TOOLS = [analyze_capacity, capacity_overview, order_priority, resource_allocation,
          delay_risk, demand_vs_capacity_tool, what_if_scenarios]
_TOOL_MAP = {f.__name__: f for f in _TOOLS}
_TOOL_SPECS = [{
    "type": "function",
    "function": {
        "name": f.__name__,
        "description": " ".join((f.__doc__ or "").split()),
        "parameters": {"type": "object", "properties": {}},
    },
} for f in _TOOLS]

_SYSTEM = (
    "You are a production planning assistant for a valve factory. Answer the planner's "
    "question by calling the relevant tool(s): analyze_capacity / capacity_overview for load "
    "and bottlenecks, order_priority for what to run first, resource_allocation for offloading "
    "overloaded machines, delay_risk for at-risk orders and material shortages, "
    "demand_vs_capacity_tool for whether the whole order book can be committed, and "
    "what_if_scenarios to compare options. Explain the result in short, plain language for a "
    "planner. Never invent numbers - only use what the tools return. Be concise and practical."
)

_client = None
_client_tried = False


def _get_client():
    """Build an Azure OpenAI client from the environment, or None if unavailable."""
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    ep = os.getenv("AZURE_OPENAI_ENDPOINT")
    key = os.getenv("AZURE_OPENAI_API_KEY")
    dep = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not (ep and key and dep):
        log.warning("Azure OpenAI env not set - copilot runs in FALLBACK (template) mode.")
        return None
    try:
        from openai import AsyncAzureOpenAI
        _client = AsyncAzureOpenAI(
            azure_endpoint=ep, api_key=key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
        log.info("Azure OpenAI copilot ready (deployment '%s').", dep)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not initialise Azure OpenAI (%s). Fallback mode.", exc)
        _client = None
    return _client


async def ask_agent(question: str) -> tuple[str, bool]:
    """Return (answer, used_llm). Uses Azure OpenAI with tool-calling; falls back to a
    deterministic template if the LLM is unavailable."""
    log.info("AGENT ASK  %r", question)
    client = _get_client()

    if client is not None:
        try:
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
            messages = [{"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": question}]
            for _ in range(5):
                resp = await client.chat.completions.create(
                    model=deployment, messages=messages,
                    tools=_TOOL_SPECS, tool_choice="auto", temperature=0)
                msg = resp.choices[0].message
                if msg.tool_calls:
                    messages.append({
                        "role": "assistant", "content": msg.content or "",
                        "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
                    for tc in msg.tool_calls:
                        fn = _TOOL_MAP.get(tc.function.name)
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": fn() if fn else "{}"})
                    continue
                text = msg.content or ""
                log.info("AGENT ANSWER (llm)  %s", text[:120])
                return text, True
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM run failed (%s). Falling back to template.", exc)

    # ---- fallback: deterministic template on the real capacity result ----
    wl = analyze_week(default_week())
    lines = [wl.summary, "", f"Work-centre load for the week of {wl.week_start}:"]
    for r in wl.resources:
        flag = "  <-- overloaded" if r.status == "OVERLOADED" else ""
        lines.append(f"  - {r.work_center} ({r.name}): {r.utilization_pct:.0f}% "
                     f"({r.required_hours:.0f}h needed / {r.available_hours:.0f}h available){flag}")
    lines.append("")
    lines.append(wl.batching.note)
    answer = "\n".join(lines)
    log.info("AGENT ANSWER (fallback)  %s", wl.summary)
    return answer, False
