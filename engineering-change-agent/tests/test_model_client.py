"""Tests for the model client.

These exercise configuration handling and request construction with an injected
fake SDK client — no network, no credentials. They verify the harness's
contract with the model: the approved deployment is used, and Stage 1A is
strictly sequential (``parallel_tool_calls=False``).
"""

from __future__ import annotations

import pytest

from change_agent.errors import ConfigurationError
from change_agent.model_client import (
    DEFAULT_DEPLOYMENT,
    DEFAULT_TOKEN_SCOPE,
    FoundryChatModel,
    ModelConfig,
)


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> dict:
        self.calls.append(kwargs)
        return {"ok": True}


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


def _config() -> ModelConfig:
    return ModelConfig(
        base_url="https://example.openai.azure.com/openai/v1/",
        deployment="gpt-5.5",
        token_scope=DEFAULT_TOKEN_SCOPE,
    )


# --- Configuration ---------------------------------------------------------


def test_from_env_normalizes_bare_endpoint() -> None:
    config = ModelConfig.from_env(
        {"AZURE_OPENAI_BASE_URL": "https://example.openai.azure.com"}
    )
    assert config.base_url == "https://example.openai.azure.com/openai/v1/"
    assert config.deployment == DEFAULT_DEPLOYMENT
    assert config.token_scope == DEFAULT_TOKEN_SCOPE


def test_from_env_normalizes_trailing_slash_on_v1_url() -> None:
    config = ModelConfig.from_env(
        {"AZURE_OPENAI_BASE_URL": "https://example.openai.azure.com/openai/v1"}
    )
    assert config.base_url == "https://example.openai.azure.com/openai/v1/"


def test_from_env_reads_overrides() -> None:
    config = ModelConfig.from_env(
        {
            "AZURE_OPENAI_BASE_URL": "https://example.openai.azure.com/openai/v1/",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
            "AZURE_OPENAI_TOKEN_SCOPE": "https://cognitiveservices.azure.com/.default",
        }
    )
    assert config.deployment == "gpt-4o"
    assert config.token_scope == "https://cognitiveservices.azure.com/.default"


def test_from_env_requires_base_url() -> None:
    with pytest.raises(ConfigurationError):
        ModelConfig.from_env({})


# --- Request construction --------------------------------------------------


def test_complete_uses_deployment_and_disables_parallel_tool_calls() -> None:
    fake = _FakeClient()
    model = FoundryChatModel(_config(), client=fake)

    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "get_deployment_status"}}]
    model.complete(messages=messages, tools=tools)

    (call,) = fake.chat.completions.calls
    assert call["model"] == "gpt-5.5"
    assert call["messages"] is messages
    assert call["tools"] is tools
    assert call["parallel_tool_calls"] is False


def test_complete_without_tools_omits_tool_kwargs() -> None:
    fake = _FakeClient()
    model = FoundryChatModel(_config(), client=fake)

    model.complete(messages=[{"role": "user", "content": "hi"}], tools=None)

    (call,) = fake.chat.completions.calls
    assert "tools" not in call
    assert "parallel_tool_calls" not in call
