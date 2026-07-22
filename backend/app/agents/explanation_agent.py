"""Explanation Agent.

Builds the ExplanationContext from the deterministic upstream outputs (via the
existing ExplanationContextBuilder) and, when a question is supplied, narrates it
through a Microsoft Agent Framework ChatAgent over Azure OpenAI.

Explain-only guarantees:
- Consumes ONLY the curated ExplanationSummary derived from ExplanationContext.
- Never invokes the solver, business rules, analytics, risk, recommendation, or
  scenario engines (this module imports none of them).
- Never modifies deterministic outputs.

Failure handling:
- If the ExplanationContext cannot be built -> CriticalAgentError (stop).
- If Azure OpenAI is unavailable -> graceful: deterministic outputs are
  preserved and the answer is omitted; the workflow still succeeds.
"""

from __future__ import annotations

from app.agents.analytics_agent import KPIS_KEY
from app.agents.base import BaseAgent
from app.agents.context import WorkflowContext
from app.agents.contracts import ExplanationAgentOutput
from app.agents.errors import CriticalAgentError
from app.agents.explanation_backend import (
    ExplanationChatBackend,
    ExplanationChatUnavailable,
    default_explanation_backend,
)
from app.agents.recommendation_agent import RECOMMENDATION_SET_KEY
from app.agents.risk_agent import RISK_REPORT_KEY
from app.agents.scenario_agent import SCENARIO_COMPARISON_KEY
from app.agents.timing import Stopwatch
from app.explanation import ExplanationContextBuilder

# Shared-context keys and the schedule key (imported by value to avoid coupling).
from app.agents.planning_agent import SCHEDULE_RESULT_KEY

EXPLANATION_CONTEXT_KEY = "explanation_context"
EXPLANATION_SUMMARY_KEY = "explanation_summary"
EXPLANATION_ANSWER_KEY = "explanation_answer"


class ExplanationAgent(BaseAgent):
    """Builds the explanation context and narrates it via Azure OpenAI (explain-only)."""

    name = "explanation_agent"

    def __init__(
        self,
        builder: ExplanationContextBuilder | None = None,
        chat_backend: ExplanationChatBackend | None = None,
    ) -> None:
        self._builder = builder or ExplanationContextBuilder()
        self._chat_backend = chat_backend or default_explanation_backend()

    def execute(self, context: WorkflowContext) -> ExplanationAgentOutput:
        schedule = context.shared.get(SCHEDULE_RESULT_KEY)
        kpis = context.shared.get(KPIS_KEY)
        risks = context.shared.get(RISK_REPORT_KEY)
        recommendations = context.shared.get(RECOMMENDATION_SET_KEY)
        scenario_comparison = context.shared.get(SCENARIO_COMPARISON_KEY)

        missing = [
            name
            for name, value in (
                ("schedule", schedule),
                ("kpis", kpis),
                ("risks", risks),
                ("recommendations", recommendations),
                ("scenario_comparison", scenario_comparison),
            )
            if value is None
        ]
        if missing:
            raise CriticalAgentError(
                f"Cannot build ExplanationContext; missing upstream outputs: "
                f"{', '.join(missing)}."
            )

        # 1. Build the ExplanationContext (existing builder) + curated summary.
        with Stopwatch() as build_sw:
            explanation_context = self._builder.build(
                business_date=context.business_date,
                schedule=schedule,
                kpis=kpis,
                risks=risks,
                recommendations=recommendations,
                scenario_comparison=scenario_comparison,
                change_log=None,
            )
            summary = self._builder.summarize(explanation_context)

        context.shared[EXPLANATION_CONTEXT_KEY] = explanation_context
        context.shared[EXPLANATION_SUMMARY_KEY] = summary
        context_size = len(explanation_context.model_dump_json())
        self.logger.info(
            "Context built in %.1f ms | context_size=%d chars",
            build_sw.elapsed_ms,
            context_size,
        )

        # 2. Optionally narrate via the ChatAgent (grounded on the summary only).
        answer = self._maybe_explain(context, summary)
        context.shared[EXPLANATION_ANSWER_KEY] = answer

        return ExplanationAgentOutput(
            agent=self.name,
            business_date=context.business_date,
            explanation_context=explanation_context,
            answer=answer,
        )

    def _maybe_explain(self, context: WorkflowContext, summary) -> str | None:
        """Call the chat backend if a question was supplied; degrade gracefully."""
        question = context.params.get("question")
        if not question:
            self.logger.info("No question supplied; skipping ChatAgent narration.")
            return None

        try:
            with Stopwatch() as chat_sw:
                result = self._chat_backend.explain(summary, question)
            self.logger.info(
                "ChatAgent in %.1f ms | model=%s prompt_tokens=%s completion_tokens=%s "
                "total_tokens=%s latency=%sms",
                chat_sw.elapsed_ms,
                result.model,
                result.prompt_tokens,
                result.completion_tokens,
                result.total_tokens,
                result.latency_ms,
            )
            return result.answer
        except ExplanationChatUnavailable as exc:
            # Graceful: preserve deterministic outputs, omit the narrative.
            self.logger.warning(
                "Azure OpenAI unavailable; deterministic outputs preserved, "
                "narration skipped: %s",
                exc,
            )
            return None
