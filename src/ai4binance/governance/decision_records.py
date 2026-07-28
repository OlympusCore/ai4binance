"""Deterministic decision and outcome records for governed tool calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from ai4binance.governance.tool_policy import (
    ToolDescriptor,
    ToolPermission,
    ToolPolicyDecision,
    ToolSideEffect,
)


class OutcomeStatus(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"
    UNKNOWN = "UNKNOWN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    step_id: str
    parent_event_id: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.step_id.strip():
            raise ValueError("run context identity is required")

    def for_step(self, step_id: str) -> RunContext:
        return RunContext(
            run_id=self.run_id,
            step_id=step_id,
            parent_event_id=self.step_id,
        )


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    timestamp: datetime
    run_id: str
    step_id: str
    parent_event_id: str | None
    project: str
    agent: str
    tool_name: str
    permission: ToolPermission
    side_effect: ToolSideEffect | None
    target_hash: str
    arguments_hash: str
    evidence_set_hash: str
    state_hash_before: str | None
    policy_id: str
    policy_version: str
    policy_hash: str
    decision: ToolPolicyDecision
    reason_codes: tuple[str, ...]
    approval_id: str | None = None
    capability_lease_id: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.decision_id.strip()
            or not self.run_id.strip()
            or not self.step_id.strip()
            or not self.project.strip()
            or not self.agent.strip()
            or not self.tool_name.strip()
        ):
            raise ValueError("decision record identity is required")
        if self.timestamp.tzinfo is None:
            raise ValueError("decision record timestamp must be timezone-aware")
        if not self.reason_codes:
            raise ValueError("decision record requires reason codes")
        for digest in (
            self.target_hash,
            self.arguments_hash,
            self.evidence_set_hash,
            self.policy_hash,
        ):
            _validate_sha256(digest)
        if self.state_hash_before is not None:
            _validate_sha256(self.state_hash_before)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("decision record cannot authorize trading")


@dataclass(frozen=True, slots=True)
class OutcomeVerification:
    outcome: OutcomeStatus
    validator: str
    reason_codes: tuple[str, ...]
    observed_hash: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.validator.strip():
            raise ValueError("outcome validator is required")
        if self.outcome is not OutcomeStatus.SUCCEEDED and not self.reason_codes:
            raise ValueError("non-success outcome verification requires reasons")
        if self.observed_hash is not None:
            _validate_sha256(self.observed_hash)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("outcome verification cannot authorize trading")


@dataclass(frozen=True, slots=True)
class OutcomeAttestation:
    decision_id: str
    execution_id: str
    timestamp: datetime
    outcome: OutcomeStatus
    validator: str
    observed_hash: str | None
    reason_codes: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.decision_id.strip()
            or not self.execution_id.strip()
            or not self.validator.strip()
        ):
            raise ValueError("outcome attestation identity is required")
        if self.timestamp.tzinfo is None:
            raise ValueError("outcome attestation timestamp must be timezone-aware")
        if self.outcome is not OutcomeStatus.SUCCEEDED and not self.reason_codes:
            raise ValueError("non-success outcome attestation requires reasons")
        if self.observed_hash is not None:
            _validate_sha256(self.observed_hash)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("outcome attestation cannot authorize trading")


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        _jsonable(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_execution_id() -> str:
    return str(uuid4())


def build_decision_record(
    *,
    context: RunContext,
    project: str,
    agent: str,
    tool: str,
    permission: ToolPermission,
    approved: bool,
    descriptor: ToolDescriptor | None,
    decision: ToolPolicyDecision,
    reason_codes: tuple[str, ...],
    approval_id: str | None,
    state_hash_before: str | None,
    evidence_hashes: tuple[str, ...],
    policy_id: str,
    policy_version: str,
    policy_hash: str | None = None,
    target: str | None = None,
    capability_lease_id: str | None = None,
) -> DecisionRecord:
    arguments = {
        "approved": approved,
        "permission": permission.value,
        "project": project,
        "target": target,
        "tool": tool,
    }
    policy_material: object = descriptor if descriptor is not None else {"tool": tool}
    return DecisionRecord(
        decision_id=new_execution_id(),
        timestamp=datetime.now(UTC),
        run_id=context.run_id,
        step_id=context.step_id,
        parent_event_id=context.parent_event_id,
        project=project,
        agent=agent,
        tool_name=tool,
        permission=permission,
        side_effect=descriptor.side_effect if descriptor is not None else None,
        target_hash=canonical_sha256(target),
        arguments_hash=canonical_sha256(arguments),
        evidence_set_hash=canonical_sha256(sorted(set(evidence_hashes))),
        state_hash_before=state_hash_before,
        policy_id=policy_id,
        policy_version=policy_version,
        policy_hash=policy_hash or canonical_sha256(policy_material),
        decision=decision,
        reason_codes=reason_codes,
        approval_id=approval_id,
        capability_lease_id=capability_lease_id,
    )


def build_outcome_attestation(
    decision_id: str,
    execution_id: str,
    verification: OutcomeVerification,
) -> OutcomeAttestation:
    return OutcomeAttestation(
        decision_id=decision_id,
        execution_id=execution_id,
        timestamp=datetime.now(UTC),
        outcome=verification.outcome,
        validator=verification.validator,
        observed_hash=verification.observed_hash,
        reason_codes=verification.reason_codes,
    )


def unverified_outcome(
    reason: str = "OUTCOME_VALIDATOR_MISSING",
) -> OutcomeVerification:
    return OutcomeVerification(
        outcome=OutcomeStatus.UNKNOWN,
        validator="none",
        reason_codes=(reason,),
    )


def failed_outcome(error: Exception) -> OutcomeVerification:
    return OutcomeVerification(
        outcome=OutcomeStatus.FAILED,
        validator="operation_exception",
        reason_codes=(type(error).__name__,),
    )


def not_executed_outcome(reason: str) -> OutcomeVerification:
    return OutcomeVerification(
        outcome=OutcomeStatus.NOT_EXECUTED,
        validator="policy_gate",
        reason_codes=(reason,),
    )


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise ValueError("expected sha256 hex digest")
