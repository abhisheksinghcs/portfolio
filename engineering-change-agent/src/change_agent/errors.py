"""Stable reason codes shared across enforcement points.

Reason codes are part of the security contract: evidence, tests, and the
article all reference these exact strings, so they must stay stable even if
internal messages change.
"""

from enum import Enum


class ConfigurationError(RuntimeError):
    """Raised when required model/runtime configuration is missing or invalid."""


class HarnessError(RuntimeError):
    """Base class for harness control-flow failures.

    Carries the evidence events emitted before the failure so callers (and tests)
    can inspect what the harness recorded on the way to stopping.
    """

    def __init__(self, message: str, events: tuple = ()) -> None:
        super().__init__(message)
        self.events = tuple(events)


class InvalidModelResponse(HarnessError):
    """The model returned something the protocol does not allow (no final answer
    or tool call, multiple tool calls, or a correlation violation)."""


class HarnessLimitExceeded(HarnessError):
    """A budget was exhausted (maximum steps or maximum tool calls)."""


class ToolTimeout(Exception):
    """A tool handler exceeded its execution timeout."""


class ReasonCode(str, Enum):
    """Stable, content-free codes explaining a denial, failure, or not-found."""

    # Tool-contract enforcement.
    PRODUCTION_ENVIRONMENT_PROHIBITED = "production_environment_prohibited"
    UNKNOWN_APPLICATION = "unknown_application"
    UNKNOWN_DEPLOYMENT = "unknown_deployment"

    # Authorization-policy enforcement.
    ENVIRONMENT_NOT_PERMITTED = "environment_not_permitted"
    APPROVAL_REQUIRED = "approval_required"

    # Harness and conversation-protocol enforcement.
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    UNEXPECTED_MULTIPLE_TOOL_CALLS = "unexpected_multiple_tool_calls"
    MISSING_TOOL_CALL_ID = "missing_tool_call_id"
    REUSED_TOOL_CALL_ID = "reused_tool_call_id"
    INVALID_MODEL_RESPONSE = "invalid_model_response"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    MAX_TOOL_CALLS_EXCEEDED = "max_tool_calls_exceeded"
