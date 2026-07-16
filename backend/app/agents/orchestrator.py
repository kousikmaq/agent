"""MAF specialist agents + orchestrator.

Three specialist agents (each with its domain tools) are exposed to an orchestrator agent as
tools (agent-as-tools pattern). The orchestrator decides which specialist to consult and
writes the final answer. This path is used when Azure OpenAI is configured; otherwise the
deterministic router handles the request.
"""
from __future__ import annotations

from functools import lru_cache

from app.agents import tools as T
from app.agents.chat_client import get_chat_client

SCHEDULING_INSTRUCTIONS = (
    "You are the Capacity & Scheduling specialist for a beverage manufacturing plant. "
    "Use your tools to answer questions about machine capacity, bottlenecks, order "
    "prioritisation, workforce allocation and schedule optimisation. Base every statement "
    "strictly on tool results and never invent numbers. Be concise."
)
RISK_INSTRUCTIONS = (
    "You are the Risk & Reliability specialist. Use your ML tools to identify orders at risk "
    "of delay and machines likely to break down. Report the specific items and their risk "
    "levels. Base everything on tool results; do not fabricate."
)
DEMAND_INSTRUCTIONS = (
    "You are the Demand & Inventory specialist. Use your tool to forecast product demand and "
    "highlight what will be needed. Base everything on tool results."
)
ORCHESTRATOR_INSTRUCTIONS = (
    "You are the orchestrator of a Production Planning & Schedule Optimization agent, talking to "
    "a busy factory production planner who is NOT a data scientist. Decide which specialist(s) to "
    "consult, then write the final answer.\n\n"
    "Base every number strictly on tool results - never invent figures.\n\n"
    "Format the answer in clear, simple, humanized language using Markdown, in this structure:\n"
    "1. Start with one bold plain-English sentence that says what this means for the plant "
    "(the 'so what'), e.g. **In short: two orders are likely to ship late unless we act today.**\n"
    "2. Then a short paragraph (2-3 sentences) explaining the situation in everyday words - "
    "translate jargon (e.g. say 'how busy the machine is' instead of 'utilisation').\n"
    "3. Then a '**Key points**' section with 2-5 bullet points, each citing the specific numbers.\n"
    "4. End with a '**Recommended next step**' line naming the single most useful action "
    "(email an alert, re-order a material, generate a chart, or export the plan).\n\n"
    "Keep it friendly, confident and easy to skim. Avoid raw tables of numbers; explain what they mean."
)


@lru_cache(maxsize=1)
def get_orchestrator():
    client = get_chat_client()
    scheduling = client.as_agent(
        name="SchedulingAgent", instructions=SCHEDULING_INSTRUCTIONS, tools=T.SCHEDULING_TOOLS)
    risk = client.as_agent(
        name="RiskAgent", instructions=RISK_INSTRUCTIONS, tools=T.RISK_TOOLS)
    demand = client.as_agent(
        name="DemandAgent", instructions=DEMAND_INSTRUCTIONS, tools=T.DEMAND_TOOLS)
    orchestrator = client.as_agent(
        name="Orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        tools=[
            scheduling.as_tool(
                name="ask_scheduling_specialist",
                description="Capacity, bottleneck, scheduling, prioritisation and workforce allocation."),
            risk.as_tool(
                name="ask_risk_specialist",
                description="Order delay-risk and machine-downtime predictions (ML)."),
            demand.as_tool(
                name="ask_demand_specialist",
                description="Product demand forecasting."),
        ],
    )
    return orchestrator


async def run_orchestrator(query: str) -> str:
    orchestrator = get_orchestrator()
    response = await orchestrator.run(query)
    return getattr(response, "text", str(response))
