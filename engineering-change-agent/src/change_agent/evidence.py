"""Content-minimizing security evidence.

Evidence answers "what did the harness decide, and what happened?" — not "what
did the user say or the model generate?" The emitter is designed so that leaking
sensitive content is *structurally hard*: ``emit`` has no parameter for prompts,
completions, tokens, credentials, full tool results, or stack traces, so none of
those can be recorded even by mistake.

Each event carries only short, stable, decision-oriented fields. The harness
calls the emitter at each decision point; the emitter never affects control flow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvidenceStage(str, Enum):
    """Where in the request flow an event was produced."""

    TOOL_AUTHORIZATION = "tool_authorization"
    TOOL_EXECUTION = "tool_execution"
    FINAL_RESPONSE = "final_response"


class EvidenceOutcome(str, Enum):
    """What ultimately happened at this stage."""

    SUCCESS = "success"
    FAILURE = "failure"
    NOT_EXECUTED = "not_executed"


# Every key an emitted event is ever allowed to contain. Anything not here is,
# by construction, impossible to record — this list is the content-minimization
# contract that tests assert against.
ALLOWED_EVENT_KEYS = frozenset(
    {
        "timestamp",
        "run_id",
        "stage",
        "tool",
        "decision",
        "reason",
        "target_environment",
        "outcome",
        "latency_ms",
        "policy_version",
        "proposal_id",
    }
)


def _coerce(value: Any) -> Any:
    """Reduce enums to their stable string value so events serialize cleanly."""
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class EvidenceEvent:
    """A single, immutable evidence record. Optional fields default to ``None``
    and are omitted from the serialized form."""

    timestamp: str
    run_id: str
    stage: str
    tool: str | None = None
    decision: str | None = None
    reason: str | None = None
    target_environment: str | None = None
    outcome: str | None = None
    latency_ms: float | None = None
    policy_version: str | None = None
    proposal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "timestamp": self.timestamp,
                "run_id": self.run_id,
                "stage": self.stage,
                "tool": self.tool,
                "decision": self.decision,
                "reason": self.reason,
                "target_environment": self.target_environment,
                "outcome": self.outcome,
                "latency_ms": self.latency_ms,
                "policy_version": self.policy_version,
                "proposal_id": self.proposal_id,
            }.items()
            if value is not None
        }


class EvidenceEmitter:
    """Creates and collects :class:`EvidenceEvent` records for one run.

    ``run_id`` and ``policy_version`` are stamped onto every event. An optional
    ``sink`` receives each event as a dict (e.g. to write JSON lines); tests use
    it to capture output. ``clock`` is injectable so tests can assert timestamps
    deterministically.
    """

    def __init__(
        self,
        *,
        run_id: str,
        policy_version: str,
        sink: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._run_id = run_id
        self._policy_version = policy_version
        self._sink = sink
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._events: list[EvidenceEvent] = []

    def emit(
        self,
        *,
        stage: EvidenceStage | str,
        tool: str | None = None,
        decision: str | None = None,
        reason: str | None = None,
        target_environment: str | None = None,
        outcome: EvidenceOutcome | str | None = None,
        latency_ms: float | None = None,
        proposal_id: str | None = None,
    ) -> EvidenceEvent:
        """Record one event. Only these decision-oriented fields are accepted;
        there is deliberately no way to pass raw content."""
        event = EvidenceEvent(
            timestamp=self._clock().isoformat(),
            run_id=self._run_id,
            stage=_coerce(stage),
            tool=tool,
            decision=_coerce(decision),
            reason=_coerce(reason),
            target_environment=_coerce(target_environment),
            outcome=_coerce(outcome),
            latency_ms=latency_ms,
            policy_version=self._policy_version,
            proposal_id=proposal_id,
        )
        self._events.append(event)
        if self._sink is not None:
            self._sink(event.to_dict())
        return event

    @property
    def events(self) -> tuple[EvidenceEvent, ...]:
        return tuple(self._events)
