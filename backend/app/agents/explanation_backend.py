"""Explanation chat backend (Microsoft Agent Framework ChatAgent).

Isolates the LLM call behind a small port so the Explanation Agent stays
testable and the deterministic engines remain unreachable from the chat path.

The backend consumes ONLY the curated ``ExplanationSummary`` (derived from the
``ExplanationContext``). It never imports or calls the solver, rules, analytics,
risk, recommendation, or scenario engines - this module deliberately imports
none of them.

The concrete :class:`MafChatBackend` builds a Microsoft Agent Framework
``ChatAgent`` over Azure OpenAI (Azure AD token auth). Dependencies are imported
lazily so importing this module never requires ``agent-framework`` or Azure
connectivity; when unavailable it raises :class:`ExplanationChatUnavailable`,
which the agent handles gracefully.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.chat.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import get_settings
from app.explanation.schema import ExplanationSummary

_AAD_SCOPE = "https://cognitiveservices.azure.com/.default"


@dataclass
class ChatAnswer:
    """A grounded answer plus token/usage metadata."""

    answer: str
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None


class ExplanationChatUnavailable(Exception):
    """Raised when the chat backend cannot serve a request (config/deps/network)."""


@runtime_checkable
class ExplanationChatBackend(Protocol):
    """Port for a grounded, explain-only chat backend."""

    def explain(self, summary: ExplanationSummary, question: str) -> ChatAnswer:
        """Answer ``question`` grounded solely on ``summary``."""
        ...


def _extract_usage(result: Any) -> dict[str, int | None]:
    """Best-effort extraction of token usage from a MAF run result."""
    usage = getattr(result, "usage", None) or getattr(result, "usage_details", None)
    prompt = getattr(usage, "prompt_tokens", None) if usage else None
    completion = getattr(usage, "completion_tokens", None) if usage else None
    total = getattr(usage, "total_tokens", None) if usage else None
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


class MafChatBackend:
    """Explain-only chat backend using a Microsoft Agent Framework ChatAgent.

    All heavy dependencies are imported lazily inside :meth:`explain`, and any
    failure is surfaced as :class:`ExplanationChatUnavailable` so the caller can
    degrade gracefully while preserving deterministic outputs.
    """

    AGENT_NAME = "explanation_agent"

    def explain(self, summary: ExplanationSummary, question: str) -> ChatAnswer:
        from time import perf_counter

        settings = get_settings()
        if not settings.azure_openai_endpoint or not settings.azure_openai_deployment:
            raise ExplanationChatUnavailable("Azure OpenAI is not configured.")

        try:
            from agent_framework.azure import AzureOpenAIChatClient
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ExplanationChatUnavailable(
                "Microsoft Agent Framework is not installed."
            ) from exc

        try:
            # Prefer API-key auth when configured; otherwise Azure AD token auth.
            if settings.azure_openai_api_key:
                client = AzureOpenAIChatClient(
                    endpoint=settings.azure_openai_endpoint,
                    deployment_name=settings.azure_openai_deployment,
                    api_version=settings.azure_openai_api_version,
                    api_key=settings.azure_openai_api_key,
                )
            else:
                from azure.identity import (
                    DefaultAzureCredential,
                    get_bearer_token_provider,
                )

                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(), _AAD_SCOPE
                )
                client = AzureOpenAIChatClient(
                    endpoint=settings.azure_openai_endpoint,
                    deployment_name=settings.azure_openai_deployment,
                    api_version=settings.azure_openai_api_version,
                    ad_token_provider=token_provider,
                )
            # Build the explain-only agent grounded on the curated summary only.
            agent = client.as_agent(name=self.AGENT_NAME, instructions=SYSTEM_PROMPT)
            prompt = build_user_prompt(summary, question)

            started = perf_counter()
            result = asyncio.run(agent.run(prompt))
            latency_ms = round((perf_counter() - started) * 1000, 3)

            usage = _extract_usage(result)
            return ChatAnswer(
                answer=(getattr(result, "text", "") or "").strip(),
                model=settings.azure_openai_deployment,
                latency_ms=latency_ms,
                **usage,
            )
        except ExplanationChatUnavailable:
            raise
        except Exception as exc:  # pragma: no cover - network/SDK dependent
            raise ExplanationChatUnavailable(str(exc)) from exc


class OpenAIExplanationBackend:
    """Explain-only fallback backend using the Azure OpenAI SDK directly.

    Used when the Microsoft Agent Framework is not installed but Azure OpenAI is
    reachable via the ``openai`` SDK. Still grounded solely on the curated
    ``ExplanationSummary`` and still imports no deterministic engine.
    """

    def explain(self, summary: ExplanationSummary, question: str) -> ChatAnswer:
        from time import perf_counter

        from app.chat.azure_client import AzureOpenAIChatClient
        from app.core.exceptions import ConfigurationError

        settings = get_settings()
        client = AzureOpenAIChatClient()
        prompt = build_user_prompt(summary, question)
        try:
            started = perf_counter()
            answer = client.complete(SYSTEM_PROMPT, prompt)
            latency_ms = round((perf_counter() - started) * 1000, 3)
        except ConfigurationError as exc:
            raise ExplanationChatUnavailable(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - network/SDK dependent
            raise ExplanationChatUnavailable(str(exc)) from exc
        return ChatAnswer(
            answer=answer,
            model=settings.azure_openai_deployment,
            latency_ms=latency_ms,
        )


class CompositeChatBackend:
    """Tries a primary backend, then a fallback, before giving up."""

    def __init__(
        self, primary: ExplanationChatBackend, fallback: ExplanationChatBackend
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def explain(self, summary: ExplanationSummary, question: str) -> ChatAnswer:
        try:
            return self._primary.explain(summary, question)
        except ExplanationChatUnavailable:
            return self._fallback.explain(summary, question)


def default_explanation_backend() -> ExplanationChatBackend:
    """Prefer the MAF ChatAgent; fall back to the Azure OpenAI SDK."""
    return CompositeChatBackend(MafChatBackend(), OpenAIExplanationBackend())
