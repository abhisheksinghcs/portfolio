"""Deterministic authorization policy.

This is the enforcement ring between structural validation and the tool. It is
deliberately separate from Pydantic:

    * Pydantic answers "are these arguments well-formed?" (structure).
    * Policy answers "is this well-formed proposal permitted?" (authorization).

A correctly shaped proposal can still be refused here. Production is denied by
this policy *and*, independently, by the tool itself — the "denied twice"
invariant, so a mistake in either layer alone cannot reach production data.

Authorization is a decision about deterministic, application-derived context,
never about the model's instructions. The model cannot argue its way past it.
"""

from __future__ import annotations

from collections.abc import Iterable

from change_agent.errors import ReasonCode
from change_agent.models import Decision, Environment, ExecutionContext
from change_agent.tools.deployment_status import DeploymentStatusArguments

# Single source of truth for the policy version stamped onto evidence.
POLICY_VERSION = "stage1-v1"


class Policy:
    """Environment-based authorization for the deployment-status tool.

    The permitted environments are configuration, not something baked into the
    tool. Anything outside the configured set fails closed. Stage 1A scopes
    policy to environment; later stages extend it to caller, tenant, approval,
    and resource ownership using :class:`ExecutionContext`.
    """

    DEFAULT_ALLOWED_ENVIRONMENTS = frozenset(
        {Environment.DEVELOPMENT, Environment.TEST, Environment.SANDBOX}
    )

    def __init__(
        self,
        allowed_environments: Iterable[Environment] | None = None,
        tools_requiring_approval: Iterable[str] | None = None,
    ) -> None:
        self._allowed_environments = (
            frozenset(allowed_environments)
            if allowed_environments is not None
            else self.DEFAULT_ALLOWED_ENVIRONMENTS
        )
        # Tools that a human must approve before the harness may run them.
        # Empty by default: Stage 1A's only tool is read-only and low-impact.
        # A real deployment lists its write / high-impact tools here.
        self._tools_requiring_approval = frozenset(tools_requiring_approval or ())

    def authorize(
        self,
        *,
        tool_name: str,
        arguments: DeploymentStatusArguments,
        context: ExecutionContext,
    ) -> Decision:
        """Decide whether a validated proposal is permitted.

        Stage 1A authorizes on environment and human approval; later stages
        expand the rules (tenant, resource ownership) using the same
        :class:`ExecutionContext`.
        """
        environment = arguments.environment

        # Independent second denial of production. The tool denies it too; this
        # policy layer must deny it on its own so neither layer is load-bearing
        # alone.
        if environment is Environment.PRODUCTION:
            return Decision.deny(ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED)

        # Fail closed: anything not explicitly permitted is refused.
        if environment not in self._allowed_environments:
            return Decision.deny(ReasonCode.ENVIRONMENT_NOT_PERMITTED)

        # Human-approval guardrail. A tool that requires approval is refused
        # unless this caller already holds an approval for it. The approval is
        # application-derived context, never something the model can assert.
        if (
            tool_name in self._tools_requiring_approval
            and tool_name not in context.approved_tools
        ):
            return Decision.deny(ReasonCode.APPROVAL_REQUIRED)

        return Decision.allow()
