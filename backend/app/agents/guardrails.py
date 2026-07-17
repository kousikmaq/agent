"""Input guardrails for the assistant.

Runs BEFORE the router and the LLM so that greetings, vague one-word messages, off-topic
general-knowledge questions and unsafe / inappropriate content get a safe, on-brand reply
instead of a production analysis or an unfiltered model answer.

Design: a genuine production/scheduling question always passes straight through (``screen``
returns ``None``). Only messages that either (a) contain unsafe content, or (b) contain no
domain vocabulary at all are intercepted. This keeps false positives low - the assistant
still answers every real question - while politely redirecting everything else.
"""
from __future__ import annotations

import re

# Vocabulary that ties a question to this assistant's job. If ANY term appears the message is
# treated as in-scope and passed through to the normal router / LLM (unless it is unsafe).
_DOMAIN_TERMS = re.compile(
    r"\b(product\w*|manufactur\w*|schedul\w*|machine\w*|line|shift\w*|worker\w*|labou?r|"
    r"staff\w*|workforce|skill\w*|order\w*|job\w*|operation\w*|makespan|tardiness|due|"
    r"priorit\w*|capacit\w*|utili[sz]\w*|bottleneck\w*|constrain\w*|downtime|break\s?down\w*|"
    r"maintenance|sensor\w*|reliab\w*|demand\w*|forecast\w*|sales|sell\w*|stock\w*|inventor\w*|"
    r"material\w*|re-?order\w*|procure\w*|supplier\w*|energy|cost\w*|kpi\w*|plan\w*|scenario\w*|"
    r"throughput|risk\w*|delay\w*|late|overdue|report\w*|insight\w*|chart\w*|graph\w*|export\w*|"
    r"email\w*|batch\w*|sku\w*|beverage\w*|plant|factory|resource\w*|allocat\w*|assign\w*|"
    r"summar\w*|status|overview|week\w*)\b",
    re.I,
)

# Clearly unsafe / adult / harmful. Always refused, even if a domain word also appears.
_UNSAFE = re.compile(
    r"\b(sex\w*|porn\w*|nude\w*|nudity|naked|nsfw|xxx|explicit|erotic\w*|escort\w*|hooker\w*|"
    r"boob\w*|breast\w*|penis|vagina|orgasm\w*|masturbat\w*|hentai|sunny\s*leone|"
    r"kill\s+(myself|someone|him|her|them)|suicide|bomb\s+making|make\s+a\s+bomb|"
    r"how\s+to\s+hack|build\s+a\s+weapon)\b",
    re.I,
)

# Common greetings / small talk (matched at the start of the message).
_GREETING = re.compile(
    r"^\s*(hi+|hey+|hello+|hiya|yo|hola|namaste|"
    r"good\s*(morning|afternoon|evening|night|day)|gm|gn|"
    r"how\s+are\s+you|how'?s\s+it\s+going|what'?s\s+up|sup|"
    r"thanks?|thank\s+you|thx|ty|bye|goodbye|see\s+you)\b",
    re.I,
)

# The examples shown to the user in every redirect, so they learn what to ask.
_EXAMPLES = [
    "Summarise this week's production plan",
    "Which machines are the biggest bottlenecks?",
    "What are the top orders at risk of missing their due date?",
    "Compare the throughput, min-risk and min-cost scenarios",
    "What is the demand forecast for the next 7 days?",
]

_CAPABILITIES = (
    "I'm the Production & Scheduling Assistant. I can help with the weekly plan, machine "
    "capacity and bottlenecks, order scheduling and priorities, delay and downtime risk, "
    "demand forecasting, material re-ordering, and the workforce."
)


def _result(intent: str, message: str, headline: str) -> dict:
    """Build a response in the same shape the router/answer service produces."""
    return {
        "intent": intent,
        "agent": "Assistant",
        "message": message,
        "headline": headline,
        "details": _EXAMPLES,
        "data": {},
        "suggested_actions": [],
        "guardrail": intent,
    }


def screen(query: str) -> dict | None:
    """Return a safe canned response for out-of-scope input, or ``None`` to allow the query
    through to the normal router / LLM pipeline."""
    q = (query or "").strip()
    if not q:
        return _result(
            "clarify",
            "Could you share a bit more? " + _CAPABILITIES + " Try one of the examples below.",
            "Please rephrase your question",
        )

    ql = q.lower()

    # 1. Unsafe / inappropriate -> always refuse, regardless of any domain words present.
    if _UNSAFE.search(ql):
        return _result(
            "refused",
            "I can't help with that. " + _CAPABILITIES + " Please ask something related to "
            "production planning or scheduling - here are a few examples.",
            "That request is outside what I can help with",
        )

    # 2. A real production/scheduling question -> let the normal pipeline handle it.
    if _DOMAIN_TERMS.search(ql):
        return None

    # 3. Greeting / small talk.
    if _GREETING.search(ql):
        return _result(
            "greeting",
            "Hello! " + _CAPABILITIES + " What would you like to look at? You can start with "
            "one of these:",
            "Hi - how can I help with production today?",
        )

    # 4. Very short / vague (no domain vocabulary and only a couple of words).
    if len(re.findall(r"[a-z0-9']+", ql)) <= 3:
        return _result(
            "clarify",
            "I'm not sure what you'd like to know. " + _CAPABILITIES + " Try being a little "
            "more specific - for example:",
            "Could you rephrase that?",
        )

    # 5. Off-topic / general-knowledge / personal, or any longer message with no domain terms.
    return _result(
        "off_topic",
        "That's outside my area. " + _CAPABILITIES + " I can't answer general or personal "
        "questions, but I'm happy to help with any of these:",
        "I can only help with production & scheduling",
    )
