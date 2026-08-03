"""Prompts for the LLM planning advisor.

Both prompts are tightly scoped and demand STRICT JSON so the model's output can
be parsed and validated deterministically. The advisor never lets the model
invent scheduling decisions: for goals it may only choose *weights* over a fixed
set of objective terms; for recommendations it may only *rank* the scenarios it
is shown. Anything outside those bounds is rejected by the parsers.
"""

from __future__ import annotations

import json

from app.advisor.terms import OBJECTIVE_TERMS, WEIGHT_MAX

# --- Goal -> objective weights ---------------------------------------------

_TERM_LINES = "\n".join(f"  - {name}: {desc}" for name, desc in OBJECTIVE_TERMS.items())

GOAL_SYSTEM_PROMPT = (
    "You are a production-planning strategist. You translate a planner's goal "
    "into a weighted objective for a CP-SAT scheduler. You do NOT create a "
    "schedule; you only choose how much to weight each objective term.\n\n"
    "The scheduler MINIMISES a weighted sum of these terms (higher weight = the "
    "solver tries harder to reduce it):\n"
    f"{_TERM_LINES}\n\n"
    "Rules:\n"
    f"- Use ONLY the term names listed above. Weights are integers 0..{WEIGHT_MAX}.\n"
    "- Express 'maximise on-time delivery' as a LARGE num_late weight.\n"
    "- Reflect the planner's priority order: the primary goal must dominate.\n"
    "- Omit terms that are irrelevant to the goal (they default to 0).\n"
    "- FIRST decide whether the text is a genuine production-planning goal. If it "
    "is NOT (a greeting, a question, or unrelated chit-chat), do NOT invent "
    "weights: return {\"is_goal\": false, \"message\": \"<one friendly sentence "
    "telling the planner to state a planning goal, with an example>\"}.\n"
    "- If it IS a planning goal, respond with STRICT JSON only, no prose:\n"
    '{"is_goal": true, "weights": {"<term>": <int>, ...}, '
    '"strategy": "<short label>", "rationale": "<one or two sentences>"}'
)


def build_goal_prompt(goal: str) -> str:
    """Build the user prompt asking the model to weight the objective."""
    return (
        "Planner goal:\n"
        f"{goal.strip()}\n\n"
        "Return the JSON weighting that best serves this goal."
    )


# --- Scenario comparison -> recommendation ---------------------------------

RECOMMEND_SYSTEM_PROMPT = (
    "You are a production-planning advisor. Given several what-if plans already "
    "solved for one day, you recommend which ONE the planner should commit. You "
    "do NOT change any plan; you only compare the numbers you are given.\n\n"
    "Prioritise, in order: more orders delivered on time (higher OTD), then less "
    "total tardiness, then lower cost, then a shorter makespan. Call out real "
    "trade-offs (e.g. higher OTD bought with more overtime cost).\n\n"
    "Respond with STRICT JSON only, no prose, matching:\n"
    '{"recommended_type": "<SCENARIO_TYPE>", '
    '"rationale": "<2-3 sentences grounded on the numbers>", '
    '"considerations": ["<trade-off>", ...]}'
)


def build_recommend_prompt(business_date: str, scenarios: list[dict]) -> str:
    """Build the user prompt describing each scenario's KPIs and deltas."""
    return (
        f"Business date: {business_date}\n"
        "Scenarios (KPIs and deltas vs the baseline current plan):\n"
        f"{json.dumps(scenarios, indent=2)}\n\n"
        "Recommend the single best scenario to commit. 'recommended_type' MUST be "
        "one of the scenario_type values above."
    )
