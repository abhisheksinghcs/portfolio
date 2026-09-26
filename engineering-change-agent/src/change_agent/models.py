"""Domain models for the harness.

These models describe *data shapes*, not permissions. Structural validation
here (Pydantic) establishes that arguments are well-formed; it never
establishes that an operation is authorized. That separation is a core
security invariant of the harness.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Environment(str, Enum):
    """Deployment environments the agent can be asked about.

    ``production`` is intentionally a *structurally valid* value: the model may
    legitimately name it. Rejecting production is an authorization decision made
    by the tool (and, later, application policy) — not a schema-shape decision.
    """

    DEVELOPMENT = "development"
    TEST = "test"
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class DeploymentStatus(BaseModel):
    """Structured, read-only status returned by ``get_deployment_status``."""

    model_config = ConfigDict(extra="forbid")

    deployment_id: str
    application: str
    environment: Environment
    status: str
    tests_passed: bool
    open_blockers: int
    change_window_available: bool


class Outcome(str, Enum):
    """Normalized outcome of a tool proposal after enforcement and execution."""

    SUCCESS = "success"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolResult:
    """Normalized result of a tool proposal.

    A single, uniform shape is returned whether the proposal succeeded, was
    denied, produced no match, or failed. Callers never receive raw exceptions,
    stack traces, or partial data — only this normalized structure.
    """

    outcome: Outcome
    reason: str | None = None
    data: dict[str, Any] | None = None

    @classmethod
    def success(cls, data: dict[str, Any]) -> "ToolResult":
        return cls(outcome=Outcome.SUCCESS, data=data)

    @classmethod
    def denied(cls, reason: str) -> "ToolResult":
        # Denials carry a stable reason code and never any target data.
        return cls(outcome=Outcome.DENIED, reason=reason)

    @classmethod
    def not_found(cls, reason: str) -> "ToolResult":
        # Not-found carries a reason but no record contents, avoiding leakage.
        return cls(outcome=Outcome.NOT_FOUND, reason=reason)

    @classmethod
    def failed(cls, reason: str) -> "ToolResult":
        return cls(outcome=Outcome.FAILED, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"outcome": self.outcome.value}
        if self.reason is not None:
            result["reason"] = self.reason
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass(frozen=True)
class ExecutionContext:
    """Deterministic, application-derived context for an authorization decision.

    These values come from the application (the validated caller identity, the
    agent's identity, the declared purpose, and any approvals the caller holds) —
    never from the model's proposal. Stage 1A carries the minimum; later stages
    expand it (tenant, resource ownership).
    """

    caller_id: str
    agent_id: str
    purpose: str
    # Tool names for which a human approval has already been granted to this
    # caller. Empty by default: nothing is pre-approved.
    approved_tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Decision:
    """Outcome of an authorization check: permitted or refused, with a reason.

    Separate from :class:`ToolResult`: a ``Decision`` answers "is this allowed?"
    A ``ToolResult`` reports what happened when the tool ran (or why it did not).
    """

    allowed: bool
    reason: str | None = None

    @classmethod
    def allow(cls) -> "Decision":
        return cls(allowed=True)

    @classmethod
    def deny(cls, reason: str) -> "Decision":
        return cls(allowed=False, reason=reason)
