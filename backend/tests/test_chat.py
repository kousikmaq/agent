"""Phase 12 tests: the explain-only chat service.

Uses a fake chat-completion client (no Azure access) to verify that the LLM is
grounded ONLY on the curated explanation summary, that guardrails are present,
and that the responder never touches the solver.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.chat import ChatResponder
from app.chat.azure_client import AzureOpenAIChatClient, ChatCompletionClient
from app.chat.prompts import SYSTEM_PROMPT
from app.core.exceptions import ConfigurationError
from app.domain.enums import ScenarioType, SolverStatus
from app.domain.models.analytics import KpiSet
from app.domain.models.explanation import ExplanationContext
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import RiskReport
from app.domain.models.scenario import ScenarioComparison, ScenarioResult
from app.domain.models.schedule import ScheduledOperation, ScheduleResult

DATE = "2026-07-17"


class FakeClient:
    """Captures the prompts it receives and returns a canned reply."""

    def __init__(self, reply: str = "Grounded answer.") -> None:
        self.reply = reply
        self.system_prompt: str | None = None
        self.user_prompt: str | None = None
        self.calls = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.reply


def _context() -> ExplanationContext:
    return ExplanationContext(
        business_date=DATE,
        schedule=ScheduleResult(
            business_date=DATE,
            status=SolverStatus.OPTIMAL,
            scheduled_operations=[
                ScheduledOperation(
                    order_id="ORD-1", operation_id="OP-1", machine_id="M-1",
                    worker_id="W-1",
                    start=datetime(2026, 7, 17, 6, 0), end=datetime(2026, 7, 17, 7, 0),
                )
            ],
            makespan_minutes=60,
            objective_value=60.0,
            solve_time_seconds=0.01,
        ),
        kpis=KpiSet(business_date=DATE, on_time_delivery_rate=1.0, metrics={"makespan_minutes": 60.0}),
        risks=RiskReport(business_date=DATE, risks=[]),
        recommendations=RecommendationSet(business_date=DATE, recommendations=[]),
        scenario_comparison=ScenarioComparison(
            business_date=DATE,
            baseline_type=ScenarioType.CURRENT_PLAN,
            results=[
                ScenarioResult(scenario_type=ScenarioType.CURRENT_PLAN, name="Current Plan",
                               kpis={"makespan_minutes": 60.0}, is_baseline=True)
            ],
            kpi_deltas={},
        ),
        change_log=None,
    )


def test_fake_client_satisfies_protocol() -> None:
    assert isinstance(FakeClient(), ChatCompletionClient)


def test_responder_returns_answer() -> None:
    client = FakeClient(reply="The schedule is optimal.")
    responder = ChatResponder(client)
    response = responder.answer(_context(), "Is the schedule optimal?")
    assert response.answer == "The schedule is optimal."
    assert response.business_date == DATE
    assert response.question == "Is the schedule optimal?"
    assert client.calls == 1


def test_system_prompt_carries_guardrails() -> None:
    client = FakeClient()
    ChatResponder(client).answer(_context(), "Why is ORD-1 scheduled first?")
    assert client.system_prompt == SYSTEM_PROMPT
    lowered = client.system_prompt.lower()
    assert "explain" in lowered
    assert "never" in lowered  # guardrails against making decisions


def test_user_prompt_is_grounded_on_curated_summary_only() -> None:
    client = FakeClient()
    ChatResponder(client).answer(_context(), "What is the makespan?")
    prompt = client.user_prompt
    # Contains the curated context and the question.
    assert DATE in prompt
    assert "What is the makespan?" in prompt
    assert "scheduled_operations" in prompt  # summary field
    # The curated summary trims to counts; it must NOT leak raw factory internals
    # such as routings or inventory that were never part of the context.
    assert "routings" not in prompt
    assert "inventory" not in prompt


def test_responder_does_not_import_optimization() -> None:
    # Structural guardrail: the chat package must not import the solver.
    import app.chat.responder as responder_module

    source = responder_module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "from app.optimization" not in text
    assert "import app.optimization" not in text
    assert "SchedulingSolver" not in text


def test_azure_client_requires_configuration() -> None:
    # With no endpoint configured, using the client must fail clearly rather
    # than attempting an unauthenticated call.
    from app.config import Settings

    settings = Settings(azure_openai_endpoint=None, azure_openai_deployment=None)
    client = AzureOpenAIChatClient(settings=settings)
    with pytest.raises(ConfigurationError):
        client.complete("sys", "user")


@pytest.mark.parametrize(
    "question",
    [
        "What are the top capacity bottlenecks today?",
        "Why are orders at risk of being late?",
        "Which recommendations are feasible right now?",
        "How does the overtime scenario compare to the baseline?",
        "What is driving the makespan?",
        "Why is ORD-0012 late?",
        "Is MC-0002 overloaded?",
    ],
)
def test_classify_intent_on_topic(question: str) -> None:
    from app.chat.intent import classify_intent

    assert classify_intent(question) == "on_topic"


@pytest.mark.parametrize(
    "question",
    [
        "hi",
        "Hello!",
        "hey there",
        "Good morning",
        "thanks",
        "how are you?",
    ],
)
def test_classify_intent_greeting(question: str) -> None:
    from app.chat.intent import classify_intent

    assert classify_intent(question) == "greeting"


@pytest.mark.parametrize(
    "question",
    [
        "Who is Modi?",
        "Tell me a joke.",
        "What's the weather like?",
        "",
    ],
)
def test_classify_intent_off_topic(question: str) -> None:
    from app.chat.intent import classify_intent

    assert classify_intent(question) == "off_topic"


def test_greeting_skips_llm_and_returns_welcome() -> None:
    from app.chat.intent import GREETING_RESPONSE

    client = FakeClient(reply="should not be used")
    response = ChatResponder(client).answer(_context(), "hello")

    assert client.calls == 0
    assert response.answer == GREETING_RESPONSE
    assert response.question == "hello"


def test_off_topic_question_skips_llm_and_returns_redirect() -> None:
    from app.chat.intent import OFF_TOPIC_RESPONSE

    client = FakeClient(reply="should not be used")
    response = ChatResponder(client).answer(_context(), "Who is Modi?")

    # Fast path: no grounded LLM call was made.
    assert client.calls == 0
    assert response.answer == OFF_TOPIC_RESPONSE
    assert response.business_date == DATE
    assert response.question == "Who is Modi?"


def test_on_topic_question_uses_grounded_llm() -> None:
    client = FakeClient(reply="The makespan is 60 minutes.")
    response = ChatResponder(client).answer(_context(), "What is the makespan?")

    # Slow path: the grounded completion is invoked.
    assert client.calls == 1
    assert response.answer == "The makespan is 60 minutes."
