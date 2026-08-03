"""Planning-goal advisor: natural-language goal -> validated objective weights.

Turns a planner's plain-English goal (e.g. "protect deliveries this week, cost
is secondary") into a weighted objective the CP-SAT solver understands. The LLM
only *chooses weights over a fixed term set*; this module then validates the
output down to known terms and safe integer ranges before it is ever handed to
the solver. If the model is unavailable or its answer is unusable, it falls back
to the deterministic default weights, so the feature can never break planning.
"""

from __future__ import annotations

from app.advisor.models import WeightProposal
from app.advisor.parsing import extract_json_object
from app.advisor.prompts import GOAL_SYSTEM_PROMPT, build_goal_prompt
from app.advisor.terms import ALLOWED_TERMS, WEIGHT_MAX
from app.chat.azure_client import ChatCompletionClient
from app.chat.intent import classify_intent
from app.core.logging import get_logger
from app.optimization.objective_spec import (
    MAKESPAN,
    TOTAL_TARDINESS,
)

logger = get_logger(__name__)

# Minimum tie-breaker weights always kept on the schedule so no objective ever
# leaves the plan's compactness unconstrained. Without a makespan/tardiness
# floor the solver can satisfy a single-term goal (e.g. only ``num_late``) with a
# feasible-but-absurd schedule (a makespan of hundreds of days), because nothing
# rewards finishing sooner. These floors are tiny next to a primary weight, so
# they only break ties between otherwise equally-good plans.
_WEIGHT_FLOOR: dict[str, int] = {MAKESPAN: 5, TOTAL_TARDINESS: 10}


def _apply_floor(weights: dict[str, int]) -> dict[str, int]:
    """Guarantee the compactness tie-breaker weights are present."""
    out = dict(weights)
    for term, floor in _WEIGHT_FLOOR.items():
        out[term] = max(out.get(term, 0), floor)
    return out


def _validate_weights(raw: object) -> dict[str, int]:
    """Keep only known terms with non-negative integer weights within bounds."""
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, int] = {}
    for name, value in raw.items():
        if name not in ALLOWED_TERMS:
            continue
        try:
            weight = int(round(float(value)))
        except (TypeError, ValueError):
            continue
        if weight <= 0:
            continue
        clean[name] = min(weight, WEIGHT_MAX)
    return clean


class PlanningGoalAdvisor:
    """Proposes a validated objective weighting for a natural-language goal."""

    def __init__(self, client: ChatCompletionClient) -> None:
        self._client = client

    def propose_weights(self, goal: str) -> WeightProposal:
        """Return validated objective weights that best serve ``goal``.

        The assistant decides intent first: obvious greetings are answered
        instantly (no LLM), everything else is sent to the model, which either
        derives an objective from the goal or declares it is not a planning goal.
        A plan is only ever produced when a real objective was understood -- an
        unclear or unrelated request gets a conversational reply, never a
        default plan.
        """
        goal = (goal or "").strip()
        if not goal:
            return self._reply(
                goal, "Please describe a planning goal to optimise for."
            )

        # Fast path: an obvious greeting is answered without an LLM call. Only
        # pure greetings are short-circuited here; deciding whether anything else
        # is a real goal is left to the model (goal phrasings rarely contain the
        # chat classifier's domain keywords).
        if classify_intent(goal) == "greeting":
            return self._reply(
                goal,
                "Hi! I'm your planning assistant. Tell me a goal for today's "
                "schedule — for example 'protect deliveries this week', 'finish "
                "everything as fast as possible', or 'reduce overtime cost' — and "
                "I'll re-optimise the plan for you.",
            )

        try:
            reply = self._client.complete(
                GOAL_SYSTEM_PROMPT, build_goal_prompt(goal)
            )
        except Exception as exc:  # noqa: BLE001 - never fail planning on LLM error
            logger.warning("Goal advisor LLM call failed: %s", exc)
            return self._reply(
                goal,
                "The planning assistant is unavailable right now, so I didn't "
                "change the plan. Please try again in a moment.",
                fallback=True,
            )

        parsed = extract_json_object(reply) or {}
        weights = _validate_weights(parsed.get("weights"))
        # The model reports non-goals with is_goal=false; also treat an empty or
        # unmappable weighting as "not understood" rather than forcing a plan.
        if parsed.get("is_goal") is False or not weights:
            message = str(parsed.get("message", "")).strip() or (
                "That doesn't look like a planning goal I can optimise. Try "
                "something like 'prioritise on-time delivery', 'minimise cost', "
                "or 'balance machine load'."
            )
            logger.info("Goal advisor treated input as a non-goal; no plan applied.")
            return self._reply(goal, message)

        return WeightProposal(
            goal=goal,
            weights=_apply_floor(weights),
            strategy=str(parsed.get("strategy", "")).strip(),
            rationale=str(parsed.get("rationale", "")).strip(),
            usable=True,
            fallback=False,
        )

    @staticmethod
    def _reply(goal: str, note: str, fallback: bool = False) -> WeightProposal:
        """A conversational reply that never commits a plan (no objective)."""
        return WeightProposal(
            goal=goal,
            weights={},
            strategy="",
            rationale=note,
            usable=False,
            fallback=fallback,
        )
