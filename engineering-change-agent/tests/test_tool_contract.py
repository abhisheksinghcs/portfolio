"""Contract tests for the read-only ``get_deployment_status`` tool.

These tests prove the tool's own contract in isolation — no model, no network,
no policy layer. They demonstrate the security invariants that the article
cites:

    * Structural validation is not authorization.
    * Production is denied by the tool itself.
    * The tool serves only known applications and known records.
    * Not-found leaks no record contents.
    * Unexpected fields (arbitrary URLs, IDs, secrets) are rejected by shape.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from change_agent.errors import ReasonCode
from change_agent.models import Outcome
from change_agent.tools.deployment_status import (
    DeploymentStatusArguments,
    get_deployment_status,
)


def _args(**overrides: object) -> DeploymentStatusArguments:
    payload = {
        "application": "payments-api",
        "environment": "test",
        "deployment_id": "DEP-1003",
    }
    payload.update(overrides)
    return DeploymentStatusArguments.model_validate(payload)


# --- Allowed behavior ------------------------------------------------------


def test_valid_test_deployment_returns_status() -> None:
    result = get_deployment_status(_args())

    assert result.outcome is Outcome.SUCCESS
    assert result.data is not None
    assert result.data["deployment_id"] == "DEP-1003"
    assert result.data["environment"] == "test"
    assert result.data["tests_passed"] is True


def test_valid_sandbox_deployment_returns_status() -> None:
    result = get_deployment_status(
        _args(environment="sandbox", deployment_id="DEP-2001")
    )

    assert result.outcome is Outcome.SUCCESS
    assert result.data is not None
    assert result.data["environment"] == "sandbox"
    assert result.data["open_blockers"] == 2


# --- Denied / not-found behavior ------------------------------------------


def test_production_is_denied_by_the_tool() -> None:
    # "production" is structurally valid, so it passes the schema and reaches
    # the tool, which denies it. Validation is not authorization.
    result = get_deployment_status(
        _args(environment="production", deployment_id="DEP-9999")
    )

    assert result.outcome is Outcome.DENIED
    assert result.reason == ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED
    assert result.data is None


def test_unknown_application_is_denied() -> None:
    result = get_deployment_status(_args(application="totally-unknown"))

    assert result.outcome is Outcome.DENIED
    assert result.reason == ReasonCode.UNKNOWN_APPLICATION
    assert result.data is None


def test_unknown_deployment_is_not_found_without_leakage() -> None:
    result = get_deployment_status(_args(deployment_id="DEP-0000"))

    assert result.outcome is Outcome.NOT_FOUND
    assert result.reason == ReasonCode.UNKNOWN_DEPLOYMENT
    assert result.data is None


# --- Structural rejection (schema, not authorization) ----------------------


def test_missing_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeploymentStatusArguments.model_validate(
            {"application": "payments-api", "environment": "test"}
        )


def test_unexpected_argument_is_rejected() -> None:
    # An arbitrary URL smuggled in as an extra field is refused by shape.
    with pytest.raises(ValidationError):
        DeploymentStatusArguments.model_validate(
            {
                "application": "payments-api",
                "environment": "test",
                "deployment_id": "DEP-1003",
                "url": "https://attacker.example/exfil",
            }
        )


def test_empty_string_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeploymentStatusArguments.model_validate(
            {
                "application": "",
                "environment": "test",
                "deployment_id": "DEP-1003",
            }
        )


def test_wrong_type_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeploymentStatusArguments.model_validate(
            {
                "application": 123,
                "environment": "test",
                "deployment_id": "DEP-1003",
            }
        )


def test_unknown_environment_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeploymentStatusArguments.model_validate(
            {
                "application": "payments-api",
                "environment": "staging",
                "deployment_id": "DEP-1003",
            }
        )
