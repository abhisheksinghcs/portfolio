"""Model communication for Stage 1A.

This module owns *one* responsibility: turning a list of Chat Completions
messages (plus optional tool schemas) into a model response, using the Microsoft
Foundry / Azure OpenAI **v1 (OpenAI-compatible)** endpoint with Microsoft Entra
authentication.

It intentionally does **not** own the loop, response parsing, tool-call
correlation, or authorization. The rest of the harness depends on the small
:class:`ChatModel` protocol, so tests inject a fake and never touch the network
or credentials.

Verified against Microsoft Learn (Foundry v1 API, Python):
    * Use the plain ``OpenAI`` client with ``base_url`` ending in ``/openai/v1/``
      (not the older ``AzureOpenAI`` client).
    * Authenticate by passing ``get_bearer_token_provider(...)`` as ``api_key``;
      the v1 client refreshes the token automatically. No API key is used.
    * ``model`` is the *deployment* name (here ``gpt-5.5``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from change_agent.errors import ConfigurationError

# Current Microsoft Learn scope for the Foundry v1 endpoint. The identity still
# needs the "Cognitive Services OpenAI User" role on the resource.
DEFAULT_TOKEN_SCOPE = "https://ai.azure.com/.default"
DEFAULT_DEPLOYMENT = "gpt-5.5"


def _normalize_base_url(raw: str) -> str:
    """Ensure the base URL targets the v1 route and ends with a slash.

    Accepts either the bare resource endpoint or one already ending in
    ``/openai/v1``; a 404 results if the path is wrong, so we normalize it.
    """
    url = raw.rstrip("/")
    if not url.endswith("/openai/v1"):
        url = f"{url}/openai/v1"
    return f"{url}/"


@dataclass(frozen=True)
class ModelConfig:
    """Approved model target. Configuration is owned by the application, not the
    model: endpoint, deployment, and token scope are set here, never proposed by
    the model."""

    base_url: str
    deployment: str
    token_scope: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ModelConfig":
        source = env if env is not None else dict(os.environ)
        raw_base_url = source.get("AZURE_OPENAI_BASE_URL")
        if not raw_base_url:
            raise ConfigurationError(
                "AZURE_OPENAI_BASE_URL is required, e.g. "
                "https://YOUR-RESOURCE.openai.azure.com/openai/v1/"
            )
        return cls(
            base_url=_normalize_base_url(raw_base_url),
            deployment=source.get("AZURE_OPENAI_DEPLOYMENT", DEFAULT_DEPLOYMENT),
            token_scope=source.get("AZURE_OPENAI_TOKEN_SCOPE", DEFAULT_TOKEN_SCOPE),
        )


class ChatModel(Protocol):
    """The harness depends on this narrow interface, not on the OpenAI SDK, so a
    fake can stand in for tests."""

    def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> Any: ...


class FoundryChatModel:
    """Entra-authenticated Chat Completions client for the Foundry v1 endpoint.

    The underlying SDK client is injectable so tests can supply a fake; the real
    client is built lazily so importing this module never requires the SDK,
    credentials, or a network.
    """

    def __init__(self, config: ModelConfig, client: Any | None = None) -> None:
        self._config = config
        self._client = client if client is not None else self._build_client(config)

    @staticmethod
    def _build_client(config: ModelConfig) -> Any:
        # Imported lazily: only the real credential path needs these packages.
        from azure.identity import (
            DefaultAzureCredential,
            get_bearer_token_provider,
        )
        from openai import OpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), config.token_scope
        )
        return OpenAI(base_url=config.base_url, api_key=token_provider)

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self._config.deployment,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            # Stage 1A is strictly sequential: at most one tool call per turn.
            kwargs["parallel_tool_calls"] = False
        return self._client.chat.completions.create(**kwargs)
