"""The bounded agent loop.

This is where "the model proposes; deterministic code disposes" actually
happens. Everything the model returns is an untrusted proposal. For each turn the
harness:

    1. calls the model with the conversation and the advertised tool schemas,
    2. preserves the complete assistant message (including any tool proposal),
    3. enforces the conversation protocol (sequential, correlated tool calls),
    4. resolves the tool from the registry (unknown -> fail closed),
    5. validates argument *shape* (Pydantic),
    6. authorizes the validated proposal (policy),
    7. executes within a timeout, normalizing every failure,
    8. emits content-minimizing evidence,
    9. appends a correlated tool-result message and continues,
   10. stops on a final answer or when a budget is exhausted.

The loop owns orchestration and budgets. It does not own the tool contract,
policy rules, evidence shape, or model transport — those are injected.
"""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from change_agent.errors import (
    HarnessLimitExceeded,
    InvalidModelResponse,
    ReasonCode,
    ToolTimeout,
)
from change_agent.evidence import (
    EvidenceEmitter,
    EvidenceEvent,
    EvidenceOutcome,
    EvidenceStage,
)
from change_agent.instructions import build_initial_context
from change_agent.model_client import ChatModel
from change_agent.models import ExecutionContext, Outcome, ToolResult
from change_agent.policy import POLICY_VERSION, Policy
from change_agent.tool_registry import ToolRegistry

_DECISION_ALLOWED = "allowed"
_DECISION_DENIED = "denied"


@dataclass(frozen=True)
class HarnessLimits:
    """Execution budgets. A model loop without budgets can run forever or hammer
    a tool; these make termination guaranteed and bounded."""

    max_steps: int = 8
    max_tool_calls: int = 4
    tool_timeout: float = 5.0


@dataclass(frozen=True)
class HarnessResult:
    """The final answer plus the evidence emitted during the run."""

    answer: str
    events: tuple[EvidenceEvent, ...]


def execute_with_timeout(
    handler: Any, arguments: Any, timeout: float
) -> ToolResult:
    """Run a tool handler under a wall-clock timeout.

    A timeout raises :class:`ToolTimeout`. The executor is not awaited on timeout
    so a slow handler cannot block the loop; the abandoned thread is a known
    Stage 1A limitation (real cancellation is deferred).
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(handler, arguments)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout as exc:
        raise ToolTimeout() from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:8]}"


def _environment_value(arguments: Any) -> str | None:
    environment = getattr(arguments, "environment", None)
    return environment.value if isinstance(environment, Enum) else environment


class Harness:
    """Owns the bounded model/tool loop for one agent."""

    def __init__(
        self,
        *,
        model: ChatModel,
        registry: ToolRegistry,
        policy: Policy,
        context: ExecutionContext,
        limits: HarnessLimits | None = None,
        evidence_sink: Any | None = None,
    ) -> None:
        self._model = model
        self._registry = registry
        self._policy = policy
        self._context = context
        self._limits = limits or HarnessLimits()
        self._evidence_sink = evidence_sink

    def run(self, user_prompt: str, *, run_id: str | None = None) -> HarnessResult:
        emitter = EvidenceEmitter(
            run_id=run_id or _new_run_id(),
            policy_version=POLICY_VERSION,
            sink=self._evidence_sink,
        )
        messages = build_initial_context(user_prompt)
        tools = self._registry.schemas()
        seen_ids: set[str] = set()
        tool_calls_made = 0

        for _ in range(self._limits.max_steps):
            response = self._model.complete(messages=messages, tools=tools)
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])

            # Preserve the complete assistant message, tool proposals included,
            # before doing anything with it.
            messages.append(self._assistant_message(message, tool_calls))

            if tool_calls:
                # Stage 1A is strictly sequential.
                if len(tool_calls) > 1:
                    emitter.emit(
                        stage=EvidenceStage.TOOL_AUTHORIZATION,
                        decision=_DECISION_DENIED,
                        reason=ReasonCode.UNEXPECTED_MULTIPLE_TOOL_CALLS,
                        outcome=EvidenceOutcome.NOT_EXECUTED,
                    )
                    raise InvalidModelResponse(
                        "Stage 1A permits one tool call per assistant turn",
                        emitter.events,
                    )

                proposal = tool_calls[0]
                self._check_correlation(proposal, seen_ids, emitter)

                if tool_calls_made >= self._limits.max_tool_calls:
                    emitter.emit(
                        stage=EvidenceStage.TOOL_AUTHORIZATION,
                        tool=self._tool_name(proposal),
                        decision=_DECISION_DENIED,
                        reason=ReasonCode.MAX_TOOL_CALLS_EXCEEDED,
                        outcome=EvidenceOutcome.NOT_EXECUTED,
                        proposal_id=proposal.id,
                    )
                    raise HarnessLimitExceeded(
                        "maximum tool calls exceeded", emitter.events
                    )

                result = self._process_tool_call(proposal, emitter)
                messages.append(self._tool_message(proposal, result))
                tool_calls_made += 1
                continue

            # No tool call: a final answer requires content.
            content = getattr(message, "content", None)
            if content:
                emitter.emit(
                    stage=EvidenceStage.FINAL_RESPONSE,
                    outcome=EvidenceOutcome.SUCCESS,
                )
                return HarnessResult(answer=content, events=emitter.events)

            emitter.emit(
                stage=EvidenceStage.FINAL_RESPONSE,
                decision=_DECISION_DENIED,
                reason=ReasonCode.INVALID_MODEL_RESPONSE,
                outcome=EvidenceOutcome.NOT_EXECUTED,
            )
            raise InvalidModelResponse(
                "Assistant returned neither final content nor a tool call",
                emitter.events,
            )

        emitter.emit(
            stage=EvidenceStage.FINAL_RESPONSE,
            decision=_DECISION_DENIED,
            reason=ReasonCode.MAX_STEPS_EXCEEDED,
            outcome=EvidenceOutcome.NOT_EXECUTED,
        )
        raise HarnessLimitExceeded("maximum agent steps reached", emitter.events)

    # -- protocol correlation -----------------------------------------------

    def _check_correlation(
        self, proposal: Any, seen_ids: set[str], emitter: EvidenceEmitter
    ) -> None:
        """Every proposal must carry a fresh tool_call_id. Missing or reused
        identifiers fail closed before any execution."""
        proposal_id = getattr(proposal, "id", None)
        if not proposal_id:
            emitter.emit(
                stage=EvidenceStage.TOOL_AUTHORIZATION,
                decision=_DECISION_DENIED,
                reason=ReasonCode.MISSING_TOOL_CALL_ID,
                outcome=EvidenceOutcome.NOT_EXECUTED,
            )
            raise InvalidModelResponse(
                "Tool call is missing a tool_call_id", emitter.events
            )
        if proposal_id in seen_ids:
            emitter.emit(
                stage=EvidenceStage.TOOL_AUTHORIZATION,
                tool=self._tool_name(proposal),
                decision=_DECISION_DENIED,
                reason=ReasonCode.REUSED_TOOL_CALL_ID,
                outcome=EvidenceOutcome.NOT_EXECUTED,
                proposal_id=proposal_id,
            )
            raise InvalidModelResponse(
                "Reused tool_call_id", emitter.events
            )
        seen_ids.add(proposal_id)

    # -- one tool proposal --------------------------------------------------

    def _process_tool_call(
        self, proposal: Any, emitter: EvidenceEmitter
    ) -> ToolResult:
        name = self._tool_name(proposal)
        tool = self._registry.resolve(name)

        if tool is None:
            emitter.emit(
                stage=EvidenceStage.TOOL_AUTHORIZATION,
                tool=name,
                decision=_DECISION_DENIED,
                reason=ReasonCode.UNKNOWN_TOOL,
                outcome=EvidenceOutcome.NOT_EXECUTED,
                proposal_id=proposal.id,
            )
            return ToolResult.denied(ReasonCode.UNKNOWN_TOOL)

        # Structural validation only. Malformed JSON or a shape mismatch is an
        # invalid-argument denial, not an execution.
        try:
            raw_arguments = json.loads(proposal.function.arguments)
            arguments = tool.arguments_model.model_validate(raw_arguments)
        except (json.JSONDecodeError, ValidationError, TypeError):
            emitter.emit(
                stage=EvidenceStage.TOOL_AUTHORIZATION,
                tool=name,
                decision=_DECISION_DENIED,
                reason=ReasonCode.INVALID_ARGUMENTS,
                outcome=EvidenceOutcome.NOT_EXECUTED,
                proposal_id=proposal.id,
            )
            return ToolResult.denied(ReasonCode.INVALID_ARGUMENTS)

        target_environment = _environment_value(arguments)

        # Authorization is a separate deterministic decision.
        decision = self._policy.authorize(
            tool_name=name, arguments=arguments, context=self._context
        )
        if not decision.allowed:
            emitter.emit(
                stage=EvidenceStage.TOOL_AUTHORIZATION,
                tool=name,
                decision=_DECISION_DENIED,
                reason=decision.reason,
                target_environment=target_environment,
                outcome=EvidenceOutcome.NOT_EXECUTED,
                proposal_id=proposal.id,
            )
            return ToolResult.denied(decision.reason or ReasonCode.INVALID_ARGUMENTS)

        # Execution, with failures normalized so no stack trace reaches the model.
        start = perf_counter()
        try:
            result = execute_with_timeout(
                tool.handler, arguments, self._limits.tool_timeout
            )
        except ToolTimeout:
            return self._emit_execution_failure(
                emitter, name, ReasonCode.TOOL_TIMEOUT, target_environment,
                proposal.id, start,
            )
        except Exception:
            return self._emit_execution_failure(
                emitter, name, ReasonCode.TOOL_EXECUTION_FAILED, target_environment,
                proposal.id, start,
            )

        latency_ms = (perf_counter() - start) * 1000
        succeeded = result.outcome is Outcome.SUCCESS
        emitter.emit(
            stage=EvidenceStage.TOOL_EXECUTION,
            tool=name,
            decision=_DECISION_ALLOWED,
            reason=None if succeeded else result.reason,
            target_environment=target_environment,
            outcome=EvidenceOutcome.SUCCESS if succeeded else EvidenceOutcome.FAILURE,
            latency_ms=latency_ms,
            proposal_id=proposal.id,
        )
        return result

    def _emit_execution_failure(
        self,
        emitter: EvidenceEmitter,
        name: str,
        reason: ReasonCode,
        target_environment: str | None,
        proposal_id: str,
        start: float,
    ) -> ToolResult:
        emitter.emit(
            stage=EvidenceStage.TOOL_EXECUTION,
            tool=name,
            decision=_DECISION_ALLOWED,
            reason=reason,
            target_environment=target_environment,
            outcome=EvidenceOutcome.FAILURE,
            latency_ms=(perf_counter() - start) * 1000,
            proposal_id=proposal_id,
        )
        return ToolResult.failed(reason)

    # -- message construction -----------------------------------------------

    @staticmethod
    def _tool_name(proposal: Any) -> str:
        return proposal.function.name

    @staticmethod
    def _assistant_message(message: Any, tool_calls: list[Any]) -> dict[str, Any]:
        assistant: dict[str, Any] = {
            "role": "assistant",
            "content": getattr(message, "content", None),
        }
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ]
        return assistant

    @staticmethod
    def _tool_message(proposal: Any, result: ToolResult) -> dict[str, Any]:
        # Correlated to the proposal through tool_call_id.
        return {
            "role": "tool",
            "tool_call_id": proposal.id,
            "name": proposal.function.name,
            "content": json.dumps(result.to_dict()),
        }
