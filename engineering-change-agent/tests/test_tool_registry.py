"""Tests for the explicit tool registry."""

from __future__ import annotations

import pytest

from change_agent.models import Outcome
from change_agent.tool_registry import (
    RegisteredTool,
    ToolRegistry,
    default_registry,
)
from change_agent.tools.deployment_status import DeploymentStatusArguments


def test_default_registry_exposes_the_deployment_tool() -> None:
    registry = default_registry()

    assert registry.names() == ("get_deployment_status",)
    assert registry.resolve("get_deployment_status") is not None


def test_resolve_unknown_tool_returns_none() -> None:
    # The harness relies on this to fail closed; there is no dynamic lookup.
    assert default_registry().resolve("rm_minus_rf") is None


def test_duplicate_registration_is_rejected() -> None:
    registry = default_registry()
    with pytest.raises(ValueError):
        registry.register(
            RegisteredTool(
                name="get_deployment_status",
                description="dup",
                arguments_model=DeploymentStatusArguments,
                handler=lambda args: None,  # type: ignore[arg-type,return-value]
            )
        )


def test_schemas_are_derived_from_the_argument_model() -> None:
    (schema,) = default_registry().schemas()

    assert schema["type"] == "function"
    function = schema["function"]
    assert function["name"] == "get_deployment_status"

    parameters = function["parameters"]
    # extra="forbid" on the Pydantic model surfaces as additionalProperties=false.
    assert parameters["additionalProperties"] is False
    assert set(parameters["required"]) == {
        "application",
        "environment",
        "deployment_id",
    }


def test_advertised_schema_excludes_developer_docstrings() -> None:
    # Structure is advertised, not our internal commentary: no title/description
    # keys anywhere in the parameters tree.
    (schema,) = default_registry().schemas()

    def _keys(node: object) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            found |= set(node)
            for value in node.values():
                found |= _keys(value)
        elif isinstance(node, list):
            for item in node:
                found |= _keys(item)
        return found

    leaked = _keys(schema["function"]["parameters"]) & {"title", "description"}
    assert leaked == set()
    # The curated, model-facing description still lives at the function level.
    assert "production is not accessible" in schema["function"]["description"]


def test_registered_handler_runs_end_to_end() -> None:
    tool = default_registry().resolve("get_deployment_status")
    assert tool is not None

    arguments = tool.arguments_model.model_validate(
        {
            "application": "payments-api",
            "environment": "test",
            "deployment_id": "DEP-1003",
        }
    )
    result = tool.handler(arguments)

    assert result.outcome is Outcome.SUCCESS
    assert result.data is not None
    assert result.data["deployment_id"] == "DEP-1003"


def test_empty_registry_resolves_nothing() -> None:
    empty = ToolRegistry()
    assert empty.names() == ()
    assert empty.resolve("get_deployment_status") is None
    assert empty.schemas() == []
