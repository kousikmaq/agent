"""Azure OpenAI client wrapper.

Defines the :class:`ChatCompletionClient` port and an Azure OpenAI adapter that
authenticates with Azure AD token auth (no API keys). The client only performs
text chat completions; it has no access to the domain, the solver, or any
factory data - the responder feeds it a curated summary as plain text.

Dependency injection: the responder depends on the :class:`ChatCompletionClient`
protocol, so a fake client can be substituted in tests without Azure access.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Azure AD scope for Azure OpenAI / Cognitive Services.
_AAD_SCOPE = "https://cognitiveservices.azure.com/.default"


@runtime_checkable
class ChatCompletionClient(Protocol):
    """Port for a text chat-completion backend."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the assistant's reply to a system + user prompt pair."""
        ...


class AzureOpenAIChatClient:
    """Azure OpenAI adapter using Azure AD token authentication.

    The underlying SDK client and credential are created lazily so importing
    this module never requires Azure connectivity or credentials (e.g. in
    tests). Configuration is read from application settings.
    """

    def __init__(
        self, settings: Settings | None = None, *, temperature: float = 0.0
    ) -> None:
        self._settings = settings or get_settings()
        self._temperature = temperature
        self._client = None  # created on first use

    def _ensure_configured(self) -> None:
        if not self._settings.azure_openai_endpoint:
            raise ConfigurationError(
                "Azure OpenAI endpoint is not configured (PPO_AZURE_OPENAI_ENDPOINT)."
            )
        if not self._settings.azure_openai_deployment:
            raise ConfigurationError(
                "Azure OpenAI deployment is not configured (PPO_AZURE_OPENAI_DEPLOYMENT)."
            )

    def _get_client(self):
        """Lazily build the Azure OpenAI SDK client.

        Uses API-key auth when a key is configured; otherwise Azure AD token
        auth via ``DefaultAzureCredential``.
        """
        if self._client is not None:
            return self._client
        self._ensure_configured()
        try:
            from openai import AzureOpenAI
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConfigurationError(
                "Azure OpenAI dependency is missing; install 'openai'."
            ) from exc

        if self._settings.azure_openai_api_key:
            self._client = AzureOpenAI(
                azure_endpoint=self._settings.azure_openai_endpoint,
                api_version=self._settings.azure_openai_api_version,
                api_key=self._settings.azure_openai_api_key,
            )
            return self._client

        try:
            from azure.identity import (
                DefaultAzureCredential,
                get_bearer_token_provider,
            )
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConfigurationError(
                "Azure AD auth dependency is missing; install 'azure-identity' "
                "or set PPO_AZURE_OPENAI_API_KEY."
            ) from exc

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), _AAD_SCOPE
        )
        self._client = AzureOpenAI(
            azure_endpoint=self._settings.azure_openai_endpoint,
            api_version=self._settings.azure_openai_api_version,
            azure_ad_token_provider=token_provider,
        )
        return self._client

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Perform a single chat completion and return the reply text."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self._settings.azure_openai_deployment,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()
