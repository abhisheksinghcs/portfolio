"""Tests for deterministic authorization policy.

These prove that authorization is a *separate* decision from structural
validation, and that production is denied by policy independently of the tool
("denied twice").
"""

from __future__ import annotations

from change_agent.errors import ReasonCode
from change_agent.models import Environment, ExecutionContext, Outcome
from change_agent.policy import Policy
from change_agent.tools.deployment_status import (
    DeploymentStatusArguments,
    get_deployment_status,
)

CONTEXT = ExecutionContext(
    caller_id="user-1",
    agent_id="engbot",
    purpose="change-readiness",
)


def _args(**overrides: object) -> DeploymentStatusArguments:
    payload = {
        "application": "payments-api",
        "environment": "test",
        "deployment_id": "DEP-1003",
    }
    payload.update(overrides)
    return DeploymentStatusArguments.model_validate(payload)


def _authorize(policy: Policy, arguments: DeploymentStatusArguments):
    return policy.authorize(
        tool_name="get_deployment_status",
        arguments=arguments,
        context=CONTEXT,
    )


# --- Allowed ---------------------------------------------------------------


def test_allows_test_environment() -> None:
    decision = _authorize(Policy(), _args(environment="test"))

    assert decision.allowed is True
    assert decision.reason is None


def test_allows_sandbox_and_development() -> None:
    for environment, deployment_id in (
        ("sandbox", "DEP-2001"),
        ("development", "DEP-3007"),
    ):
        decision = _authorize(
            Policy(), _args(environment=environment, deployment_id=deployment_id)
        )
        assert decision.allowed is True


# --- Denied ----------------------------------------------------------------


def test_denies_production() -> None:
    decision = _authorize(Policy(), _args(environment="production"))

    assert decision.allowed is False
    assert decision.reason == ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED


def test_denies_environment_outside_configured_allowlist() -> None:
    # A policy configured to allow only "test" refuses an otherwise-valid
    # sandbox request. Authorization is configuration, not tool shape.
    restrictive = Policy(allowed_environments={Environment.TEST})

    decision = _authorize(restrictive, _args(environment="sandbox"))

    assert decision.allowed is False
    assert decision.reason == ReasonCode.ENVIRONMENT_NOT_PERMITTED


# --- Defense in depth ------------------------------------------------------


def test_production_denied_by_both_policy_and_tool() -> None:
    # "Denied twice": policy refuses production, and the tool refuses it too,
    # each independently, with the same stable reason code.
    arguments = _args(environment="production", deployment_id="DEP-9999")

    policy_decision = _authorize(Policy(), arguments)
    tool_result = get_deployment_status(arguments)

    assert policy_decision.allowed is False
    assert policy_decision.reason == ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED

    assert tool_result.outcome is Outcome.DENIED
    assert tool_result.reason == ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED
    assert tool_result.data is None
