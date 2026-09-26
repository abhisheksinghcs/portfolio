"""Tests for the CLI wiring. The happy path injects a fake model so no network
or credentials are needed; the config-error path is exercised directly."""

from __future__ import annotations

from change_agent import cli
from harness_fakes import ScriptedModel, message, response, tool_call

VALID_ARGS = {
    "application": "payments-api",
    "environment": "test",
    "deployment_id": "DEP-1003",
}


def test_missing_config_returns_error(monkeypatch, capsys) -> None:
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)

    code = cli.main(["Is", "DEP-1003", "ready?"])

    assert code == 2
    assert "AZURE_OPENAI_BASE_URL" in capsys.readouterr().err


def test_happy_path_prints_answer_and_evidence(monkeypatch, capsys) -> None:
    monkeypatch.setenv(
        "AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/"
    )
    model = ScriptedModel(
        [
            response(message(tool_calls=[tool_call("call_1", "get_deployment_status", VALID_ARGS)])),
            response(message(content="DEP-1003 is ready.")),
        ]
    )

    code = cli.main(["Is DEP-1003 ready?"], model=model)

    assert code == 0
    captured = capsys.readouterr()
    assert "DEP-1003 is ready." in captured.out
    # Evidence goes to stderr, separate from the answer.
    assert "tool_execution" in captured.err
