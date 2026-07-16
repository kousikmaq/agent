"""Azure OpenAI chat-client factory for Microsoft Agent Framework. The API key is read from
settings (never hard-coded) and the client is only constructed when a real key is present."""
from __future__ import annotations

from functools import lru_cache

from app.config import settings


def azure_available() -> bool:
    return settings.has_azure


@lru_cache(maxsize=1)
def get_chat_client():
    if not settings.has_azure:
        raise RuntimeError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_API_KEY in .env to enable the LLM."
        )
    from agent_framework.azure import AzureOpenAIChatClient

    return AzureOpenAIChatClient(
        api_key=settings.azure_openai_api_key.get_secret_value(),
        deployment_name=settings.azure_openai_deployment,
        endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )
