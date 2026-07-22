"""Chat responder - the explain-only assistant orchestration.

Turns an :class:`ExplanationContext` into a curated summary, grounds the LLM on
that summary alone, and returns the assistant's answer. The responder never
imports or calls the optimization engine, guaranteeing the LLM cannot influence
scheduling.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.models.base import FrozenDomainModel
from app.domain.models.explanation import ExplanationContext
from app.chat.azure_client import AzureOpenAIChatClient, ChatCompletionClient
from app.chat.prompts import SYSTEM_PROMPT, build_user_prompt
from app.explanation import ExplanationContextBuilder
from app.explanation.schema import ExplanationSummary

logger = get_logger(__name__)


class ChatResponse(FrozenDomainModel):
    """A single assistant answer, grounded on a specific day's context."""

    business_date: str
    question: str
    answer: str


class ChatResponder:
    """Answers planner questions grounded solely on the explanation context."""

    def __init__(
        self,
        client: ChatCompletionClient,
        builder: ExplanationContextBuilder | None = None,
    ) -> None:
        """Create the responder.

        Parameters
        ----------
        client:
            The chat-completion backend (Azure OpenAI adapter, or a fake in
            tests). Injected to keep the responder testable and provider-agnostic.
        builder:
            Explanation context builder used to curate the summary handed to the
            LLM. Defaults to a standard builder.
        """
        self._client = client
        self._builder = builder or ExplanationContextBuilder()

    def answer(self, context: ExplanationContext, question: str) -> ChatResponse:
        """Answer ``question`` grounded on ``context`` (via its curated summary)."""
        summary = self._builder.summarize(context)
        return self.answer_from_summary(summary, question)

    def answer_from_summary(
        self, summary: ExplanationSummary, question: str
    ) -> ChatResponse:
        """Answer using an already-curated :class:`ExplanationSummary`."""
        user_prompt = build_user_prompt(summary, question)
        logger.info(
            "Answering planner question for %s (%d chars of grounded context).",
            summary.business_date,
            len(user_prompt),
        )
        answer_text = self._client.complete(SYSTEM_PROMPT, user_prompt)
        return ChatResponse(
            business_date=summary.business_date,
            question=question,
            answer=answer_text,
        )


def create_default_responder() -> ChatResponder:
    """Build a responder backed by the Azure OpenAI client from settings."""
    return ChatResponder(AzureOpenAIChatClient())
