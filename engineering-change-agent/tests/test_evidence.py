"""Tests for the content-minimizing evidence emitter.

These prove two things:
    * Events carry the expected decision-oriented fields (and enums serialize as
      plain strings).
    * Events can *only* contain whitelisted, content-free keys — no prompts,
      completions, tokens, credentials, or full results can leak.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from change_agent.errors import ReasonCode
from change_agent.evidence import (
    ALLOWED_EVENT_KEYS,
    EvidenceEmitter,
    EvidenceOutcome,
    EvidenceStage,
)
from change_agent.models import Environment
from change_agent.policy import POLICY_VERSION

FIXED_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _emitter(**kwargs: object) -> EvidenceEmitter:
    return EvidenceEmitter(
        run_id="run-test",
        policy_version=POLICY_VERSION,
        clock=lambda: FIXED_TIME,
        **kwargs,
    )


def test_authorization_denial_records_expected_fields() -> None:
    emitter = _emitter()

    event = emitter.emit(
        stage=EvidenceStage.TOOL_AUTHORIZATION,
        tool="get_deployment_status",
        decision="denied",
        reason=ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED,
        target_environment=Environment.PRODUCTION,
        outcome=EvidenceOutcome.NOT_EXECUTED,
        proposal_id="call_abc123",
    )

    data = event.to_dict()
    assert data["run_id"] == "run-test"
    assert data["stage"] == "tool_authorization"
    assert data["tool"] == "get_deployment_status"
    assert data["decision"] == "denied"
    assert data["reason"] == "production_environment_prohibited"
    assert data["target_environment"] == "production"
    assert data["outcome"] == "not_executed"
    assert data["policy_version"] == "stage1-v1"
    assert data["proposal_id"] == "call_abc123"
    assert data["timestamp"] == FIXED_TIME.isoformat()


def test_enum_values_serialize_as_plain_strings() -> None:
    emitter = _emitter()

    event = emitter.emit(
        stage=EvidenceStage.TOOL_EXECUTION,
        outcome=EvidenceOutcome.SUCCESS,
        target_environment=Environment.TEST,
    )

    data = event.to_dict()
    assert data["stage"] == "tool_execution"
    assert data["outcome"] == "success"
    assert data["target_environment"] == "test"


def test_none_fields_are_omitted() -> None:
    emitter = _emitter()

    event = emitter.emit(stage=EvidenceStage.FINAL_RESPONSE, outcome=EvidenceOutcome.SUCCESS)

    data = event.to_dict()
    assert "tool" not in data
    assert "reason" not in data
    assert "target_environment" not in data
    assert "proposal_id" not in data


def test_emitted_keys_are_a_subset_of_the_allowlist() -> None:
    # Content-minimization contract: an event can never contain a key outside
    # the whitelist, so raw content has nowhere to live.
    emitter = _emitter()

    event = emitter.emit(
        stage=EvidenceStage.TOOL_EXECUTION,
        tool="get_deployment_status",
        decision="allowed",
        outcome=EvidenceOutcome.SUCCESS,
        latency_ms=1.5,
        proposal_id="call_xyz",
    )

    assert set(event.to_dict()).issubset(ALLOWED_EVENT_KEYS)


def test_events_are_collected_and_delivered_to_sink() -> None:
    captured: list[dict] = []
    emitter = _emitter(sink=captured.append)

    emitter.emit(stage=EvidenceStage.TOOL_AUTHORIZATION, decision="allowed")
    emitter.emit(stage=EvidenceStage.TOOL_EXECUTION, outcome=EvidenceOutcome.SUCCESS)

    assert len(emitter.events) == 2
    assert len(captured) == 2
    assert captured[0]["decision"] == "allowed"


def test_event_is_immutable() -> None:
    emitter = _emitter()
    event = emitter.emit(stage=EvidenceStage.FINAL_RESPONSE)

    with pytest.raises(Exception):
        event.reason = "tampered"  # type: ignore[misc]
