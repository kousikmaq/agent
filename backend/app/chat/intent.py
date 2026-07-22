"""Lightweight intent classification for the explain-only assistant.

A fast, deterministic pre-check that routes a planner's question into one of
three intents:

- ``on_topic``  - the question is about the production schedule / factory state,
  so it must be answered by grounding the LLM on the curated context (the slow,
  expensive path).
- ``greeting``  - a greeting or pleasantry (hi, hello, thanks, ...), answered
  instantly with a friendly welcome and an offer to help.
- ``off_topic`` - the question is unrelated or too vague (general knowledge,
  chit-chat), answered instantly with a polite redirect.

Both ``greeting`` and ``off_topic`` skip the grounded LLM call entirely (the
fast, free path). The classifier is intentionally rule-based (no network / LLM
call) so these paths stay fast and free, and so the behaviour is deterministic
and unit-testable. The LLM system-prompt guardrail still handles anything that
slips through as an on-topic question, so misclassification degrades gracefully.
"""

from __future__ import annotations

import re
from typing import Literal

Intent = Literal["on_topic", "greeting", "off_topic"]

# Vocabulary that signals a genuine production-planning question. Kept specific
# to the domain to avoid matching everyday English in off-topic chatter.
_DOMAIN_KEYWORDS = frozenset(
    {
        "schedule", "scheduling", "scheduled", "reschedule",
        "plan", "plans", "planning", "planner", "replan",
        "order", "orders",
        "machine", "machines",
        "worker", "workers", "operator", "operators",
        "shift", "shifts", "overtime",
        "makespan", "bottleneck", "bottlenecks",
        "utilization", "utilisation", "capacity", "load", "congested",
        "risk", "risks", "at-risk",
        "recommendation", "recommendations", "recommend", "fix", "fixes",
        "scenario", "scenarios", "baseline", "what-if",
        "late", "tardy", "tardiness", "delay", "delayed",
        "delivery", "deliveries", "due", "on-time", "overdue",
        "kpi", "kpis", "metric", "metrics",
        "operation", "operations",
        "drift", "conflict", "conflicts",
        "optimizer", "optimize", "optimise", "optimization", "optimisation",
        "solver", "feasible", "infeasible",
        "production", "factory", "shopfloor", "shop-floor",
        "material", "materials", "component", "components",
        "inventory", "supply", "shortage", "routing", "routings",
        "sequence", "resequence", "reassign", "priority",
        "cost", "throughput", "weekly", "daily", "completion",
    }
)

# Greeting / pleasantry tokens. A message made up entirely of these (with no
# domain signal) is treated as a greeting rather than an off-topic question.
_GREETING_TOKENS = frozenset(
    {
        "hi", "hii", "hiya", "hey", "heya", "hello", "helloo", "yo", "howdy",
        "hola", "greetings", "there",
        "good", "morning", "afternoon", "evening", "day", "night",
        "thanks", "thank", "thankyou", "thanx", "thx", "ty", "cheers",
        "appreciate", "appreciated",
        "bye", "goodbye", "cya", "later",
        "how", "are", "you", "doing", "is", "it", "going", "sup", "whatsup",
        "please", "welcome",
    }
)

# Entity id patterns used across the domain (orders, machines, workers, ...),
# e.g. "ORD-0012", "MC-0002", "RM-0015", "OP-1", "M-1", "W-1".
_ID_PATTERN = re.compile(r"\b(?:ORD|MC|RM|WC|OP|M|W)-\d+\b", re.IGNORECASE)

# Tokenizer that keeps hyphenated domain terms (e.g. "on-time", "at-risk").
_WORD_PATTERN = re.compile(r"[a-z][a-z\-]*")


def classify_intent(question: str) -> Intent:
    """Classify ``question`` as ``on_topic``, ``greeting``, or ``off_topic``.

    On-topic when the question references a domain entity id (e.g. ``ORD-0012``)
    or any production-planning keyword. Otherwise, a message made up entirely of
    greeting/pleasantry words is a greeting; anything else is off-topic. Empty
    input falls through to off-topic.
    """
    normalized = question.strip().lower()
    if not normalized:
        return "off_topic"
    if _ID_PATTERN.search(question):
        return "on_topic"
    tokens = _WORD_PATTERN.findall(normalized)
    if set(tokens) & _DOMAIN_KEYWORDS:
        return "on_topic"
    if tokens and all(token in _GREETING_TOKENS for token in tokens):
        return "greeting"
    return "off_topic"


# Instant, friendly welcome returned for greetings without an LLM call.
GREETING_RESPONSE = (
    "Hello! I'm your production-planning assistant. I can help you make sense of "
    "today's schedule - capacity bottlenecks, late orders and why they're at "
    "risk, machine load and trends, recommended fixes, and scenario comparisons. "
    "What would you like to look at?"
)

# Instant, friendly redirect returned for off-topic questions without an LLM
# call. Mirrors the tone the grounded assistant uses for out-of-scope questions.
OFF_TOPIC_RESPONSE = (
    "Thanks for asking, but I'm a production-planning assistant, so I can't help "
    "with that. I can explain today's schedule and answer questions about late "
    "orders, machine load and bottlenecks, risks, recommendations, and scenario "
    "comparisons. Let me know what you'd like to explore."
)

# Canned replies for the non-grounded intents.
_FAST_RESPONSES: dict[Intent, str] = {
    "greeting": GREETING_RESPONSE,
    "off_topic": OFF_TOPIC_RESPONSE,
}


def fast_response(question: str) -> str | None:
    """Return an instant canned reply for non-grounded intents, else ``None``.

    Returns the greeting or off-topic message when the question needs no grounded
    answer, or ``None`` when the question is on-topic and must be answered by the
    LLM using the curated context.
    """
    return _FAST_RESPONSES.get(classify_intent(question))

