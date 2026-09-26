"""End-to-end harness tests using a scripted fake model (no network).

These cover the successful read path plus the conversation-protocol and
enforcement behaviors: production denial, unknown tool, invalid arguments, mixed
content, sequential constraint, and tool_call_id correlation.
"""

from __future__ import annotations

import pytest

from change_agent.errors import InvalidModelResponse
from change_agent.harness import Harness
from change_agent.models import ExecutionContext
from change_agent.policy import Policy
from change_agent.tool_registry import default_registry
from harness_fakes import ScriptedModel, message, response, tool_call

CONTEXT = ExecutionContext(
    caller_id="user-1", agent_id="engbot", purpose="change-readiness"
)

VALID_ARGS = {
    "application": "payments-api",
    "environment": "test",
    "deployment_id": "DEP-1003",
}


def _harness(model, **kwargs) -> Harness:
    return Harness(
        model=model,
        registry=default_registry(),
        policy=Policy(),
        context=CONTEXT,
        **kwargs,
    )


def _tool_messages(call: dict) -> list[dict]:
    return [m for m in call["messages"] if m.get("role") == "tool"]


# --- Successful path -------------------------------------------------------


def test_successful_read_flow_returns_grounded_answer() -> None:
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "get_deployment_status", VALID_ARGS)])),
            response(message(content="DEP-1003 in test is ready: tests passed, 0 blockers.")),
        ]
    )
    result = _harness(model).run("Is DEP-1003 ready?", run_id="run-1")

    assert "ready" in result.answer.lower()
    stages = [e.stage for e in result.events]
    assert "tool_execution" in stages
    assert stages[-1] == "final_response"

    execution = next(e for e in result.events if e.stage == "tool_execution")
    assert execution.outcome == "success"
    assert execution.decision == "allowed"
    assert execution.proposal_id == "call_1"
    assert execution.target_environment == "test"


def test_second_model_call_sees_the_correlated_tool_result() -> None:
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "get_deployment_status", VALID_ARGS)])),
            response(message(content="Looks ready.")),
        ]
    )
    _harness(model).run("Is DEP-1003 ready?", run_id="run-1")

    second_call = model.calls[1]
    tool_messages = _tool_messages(second_call)
    assert tool_messages
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert "validation_complete" in tool_messages[0]["content"]


# --- Enforcement paths -----------------------------------------------------


def test_production_is_denied_and_not_executed() -> None:
    prod_args = {**VALID_ARGS, "environment": "production", "deployment_id": "DEP-9"}
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "get_deployment_status", prod_args)])),
            response(message(content="I can't assess production deployments.")),
        ]
    )
    result = _harness(model).run("Is DEP-9 ready in prod?", run_id="run-1")

    authorization = next(e for e in result.events if e.stage == "tool_authorization")
    assert authorization.decision == "denied"
    assert authorization.reason == "production_environment_prohibited"
    assert authorization.outcome == "not_executed"
    assert not any(
        e.stage == "tool_execution" and e.outcome == "success" for e in result.events
    )
    assert "production_environment_prohibited" in _tool_messages(model.calls[1])[0]["content"]


def test_unknown_tool_is_denied() -> None:
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "launch_missiles", {})])),
            response(message(content="That tool is not available.")),
        ]
    )
    result = _harness(model).run("Do something dangerous.", run_id="run-1")

    authorization = next(e for e in result.events if e.stage == "tool_authorization")
    assert authorization.reason == "unknown_tool"
    assert authorization.outcome == "not_executed"


def test_invalid_arguments_are_denied() -> None:
    smuggled = {**VALID_ARGS, "url": "https://attacker.example/exfil"}
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "get_deployment_status", smuggled)])),
            response(message(content="Those arguments were rejected.")),
        ]
    )
    result = _harness(model).run("Check with a smuggled field.", run_id="run-1")

    authorization = next(e for e in result.events if e.stage == "tool_authorization")
    assert authorization.reason == "invalid_arguments"
    assert authorization.outcome == "not_executed"


def test_mixed_content_processes_tool_before_finalizing() -> None:
    # The first message carries provisional text *and* a tool proposal; the
    # proposal must be processed rather than treating the text as final.
    model = ScriptedModel(
        [
            response(
                message(
                    content="Let me check that deployment.",
                    tool_calls=[tool_call("call_1", "get_deployment_status", VALID_ARGS)],
                )
            ),
            response(message(content="DEP-1003 is ready.")),
        ]
    )
    result = _harness(model).run("Is DEP-1003 ready?", run_id="run-1")

    assert result.answer == "DEP-1003 is ready."
    assert any(e.stage == "tool_execution" and e.outcome == "success" for e in result.events)


# --- Conversation-protocol failures (fail closed) --------------------------


def test_multiple_tool_calls_fail_closed() -> None:
    model = ScriptedModel(
        [
            response(
                message(
                    tool_calls=[
                        tool_call("call_1", "get_deployment_status", VALID_ARGS),
                        tool_call("call_2", "get_deployment_status", VALID_ARGS),
                    ]
                )
            )
        ]
    )
    with pytest.raises(InvalidModelResponse) as exc:
        _harness(model).run("Check two at once.", run_id="run-1")

    assert any(e.reason == "unexpected_multiple_tool_calls" for e in exc.value.events)


def test_missing_tool_call_id_fails_closed() -> None:
    model = ScriptedModel(
        [response(message(tool_calls=[tool_call("", "get_deployment_status", VALID_ARGS)]))]
    )
    with pytest.raises(InvalidModelResponse) as exc:
        _harness(model).run("No id.", run_id="run-1")

    assert any(e.reason == "missing_tool_call_id" for e in exc.value.events)


def test_reused_tool_call_id_fails_closed() -> None:
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("dup", "get_deployment_status", VALID_ARGS)])),
            response(message(tool_calls=[tool_call("dup", "get_deployment_status", VALID_ARGS)])),
        ]
    )
    with pytest.raises(InvalidModelResponse) as exc:
        _harness(model).run("Reuse an id.", run_id="run-1")

    assert any(e.reason == "reused_tool_call_id" for e in exc.value.events)


def test_no_content_and_no_tool_call_fails_closed() -> None:
    model = ScriptedModel([response(message(content=None, tool_calls=None))])
    with pytest.raises(InvalidModelResponse) as exc:
        _harness(model).run("Say nothing.", run_id="run-1")

    assert any(e.reason == "invalid_model_response" for e in exc.value.events)
