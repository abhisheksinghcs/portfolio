"""Tests for initial-context construction."""

from __future__ import annotations

from change_agent.instructions import SYSTEM_INSTRUCTIONS, build_initial_context


def test_build_initial_context_has_system_then_user() -> None:
    messages = build_initial_context("Is DEP-1003 ready?")

    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == SYSTEM_INSTRUCTIONS
    assert messages[1]["content"] == "Is DEP-1003 ready?"


def test_system_prompt_references_the_tool() -> None:
    assert "get_deployment_status" in SYSTEM_INSTRUCTIONS
