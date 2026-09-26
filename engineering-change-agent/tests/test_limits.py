"""Harness budget and execution-boundary tests: step and tool-call limits,
tool timeout, and tool exception normalization (no leakage)."""

from __future__ import annotations

import time

import pytest

from change_agent.errors import HarnessLimitExceeded
from change_agent.harness import Harness, HarnessLimits
from change_agent.models import ExecutionContext, ToolResult
from change_agent.policy import Policy
from change_agent.tool_registry import RegisteredTool, ToolRegistry, default_registry
from change_agent.tools.deployment_status import DeploymentStatusArguments
from harness_fakes import AlwaysToolModel, ScriptedModel, message, response, tool_call

CONTEXT = ExecutionContext(
    caller_id="user-1", agent_id="engbot", purpose="change-readiness"
)

VALID_ARGS = {
    "application": "payments-api",
    "environment": "test",
    "deployment_id": "DEP-1003",
}


def _tool_messages(call: dict) -> list[dict]:
    return [m for m in call["messages"] if m.get("role") == "tool"]


def _single_tool_model() -> ScriptedModel:
    return ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "get_deployment_status", VALID_ARGS)])),
            response(message(content="Done.")),
        ]
    )


def _registry_with_handler(handler) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="get_deployment_status",
            description="test handler",
            arguments_model=DeploymentStatusArguments,
            handler=handler,
        )
    )
    return registry


# --- Budgets ---------------------------------------------------------------


def test_max_steps_exceeded_terminates_with_evidence() -> None:
    harness = Harness(
        model=AlwaysToolModel(),
        registry=default_registry(),
        policy=Policy(),
        context=CONTEXT,
        limits=HarnessLimits(max_steps=3, max_tool_calls=10),
    )
    with pytest.raises(HarnessLimitExceeded) as exc:
        harness.run("loop forever", run_id="run-1")

    assert any(e.reason == "max_steps_exceeded" for e in exc.value.events)


def test_max_tool_calls_exceeded_terminates_with_evidence() -> None:
    harness = Harness(
        model=AlwaysToolModel(),
        registry=default_registry(),
        policy=Policy(),
        context=CONTEXT,
        limits=HarnessLimits(max_steps=10, max_tool_calls=2),
    )
    with pytest.raises(HarnessLimitExceeded) as exc:
        harness.run("call the tool repeatedly", run_id="run-1")

    assert any(e.reason == "max_tool_calls_exceeded" for e in exc.value.events)


# --- Execution boundary ----------------------------------------------------


def test_tool_timeout_is_normalized() -> None:
    def slow(_arguments):
        time.sleep(0.3)
        return ToolResult.success({"ok": True})

    model = _single_tool_model()
    harness = Harness(
        model=model,
        registry=_registry_with_handler(slow),
        policy=Policy(),
        context=CONTEXT,
        limits=HarnessLimits(tool_timeout=0.05),
    )
    result = harness.run("check a slow tool", run_id="run-1")

    execution = next(e for e in result.events if e.stage == "tool_execution")
    assert execution.reason == "tool_timeout"
    assert execution.outcome == "failure"
    assert "tool_timeout" in _tool_messages(model.calls[1])[0]["content"]


def test_tool_exception_is_normalized_without_leakage() -> None:
    def boom(_arguments):
        raise RuntimeError("secret internal detail: connection string=...")

    model = _single_tool_model()
    harness = Harness(
        model=model,
        registry=_registry_with_handler(boom),
        policy=Policy(),
        context=CONTEXT,
    )
    result = harness.run("trigger a failure", run_id="run-1")

    execution = next(e for e in result.events if e.stage == "tool_execution")
    assert execution.reason == "tool_execution_failed"
    assert execution.outcome == "failure"

    tool_content = _tool_messages(model.calls[1])[0]["content"]
    assert "secret internal detail" not in tool_content
    assert "tool_execution_failed" in tool_content
