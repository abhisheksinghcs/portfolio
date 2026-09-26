"""Test doubles for the model. These mimic the OpenAI Chat Completions response
shape (``response.choices[0].message`` with ``content`` and ``tool_calls``) using
plain namespaces, so harness tests need no network or SDK."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any


def tool_call(call_id: str, name: str, arguments: Any) -> SimpleNamespace:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=raw),
    )


def message(content: str | None = None, tool_calls: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def response(msg: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class ScriptedModel:
    """Returns a fixed list of responses in order, recording each call."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, messages: list, tools: list) -> SimpleNamespace:
        self.calls.append({"messages": list(messages), "tools": tools})
        return self._responses.pop(0)


class AlwaysToolModel:
    """Proposes a fresh tool call on every turn (never finalizes), for budget
    tests. Each call uses a new tool_call_id so correlation never trips first."""

    def __init__(self, name: str = "get_deployment_status", arguments: dict | None = None) -> None:
        self._name = name
        self._arguments = arguments or {
            "application": "payments-api",
            "environment": "test",
            "deployment_id": "DEP-1003",
        }
        self._n = 0

    def complete(self, *, messages: list, tools: list) -> SimpleNamespace:
        index = self._n
        self._n += 1
        return response(
            message(tool_calls=[tool_call(f"call_{index}", self._name, self._arguments)])
        )
