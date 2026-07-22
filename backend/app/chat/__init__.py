"""Chat service (Azure OpenAI, explain-only).

Consumes only the curated explanation summary derived from the
:class:`~app.domain.models.explanation.ExplanationContext`. Never makes
scheduling decisions and never interacts with the optimization engine.
"""

from __future__ import annotations

from app.chat.azure_client import AzureOpenAIChatClient, ChatCompletionClient
from app.chat.responder import ChatResponder, ChatResponse, create_default_responder

__all__ = [
    "AzureOpenAIChatClient",
    "ChatCompletionClient",
    "ChatResponder",
    "ChatResponse",
    "create_default_responder",
]
