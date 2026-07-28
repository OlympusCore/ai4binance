from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from ai4binance.governance import (
    OutcomeStatus,
    OutcomeVerification,
    RunContext,
    ToolDescriptor,
    ToolPermission,
    ToolPolicyDecision,
    ToolSideEffect,
    build_decision_record,
    build_outcome_attestation,
    canonical_sha256,
    failed_outcome,
    not_executed_outcome,
    unverified_outcome,
)


def test_decision_record_hashes_policy_and_evidence_deterministically() -> None:
    descriptor = ToolDescriptor(
        "quality-triage",
        "Read local quality triage artifacts",
        ("ai4binance",),
        ToolSideEffect.READ_LOCAL,
    )
    record = build_decision_record(
        context=RunContext("run-1", "tool-check"),
        project="ai4binance",
        agent="qa",
        tool=descriptor.name,
        permission=ToolPermission.READ_ONLY,
        approved=False,
        descriptor=descriptor,
        decision=ToolPolicyDecision.ALLOW,
        reason_codes=("POLICY_RULE:allow",),
        approval_id=None,
        state_hash_before=canonical_sha256({"state": "before"}),
        evidence_hashes=("b" * 64, "a" * 64, "a" * 64),
        policy_id="policy",
        policy_version="1",
        target="Artifacts/quality-triage/state.json",
    )

    assert record.execution_allowed is False
    assert record.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert record.evidence_set_hash == canonical_sha256(["a" * 64, "b" * 64])
    assert record.side_effect is ToolSideEffect.READ_LOCAL


def test_outcome_attestation_contracts_are_fail_closed() -> None:
    unknown = unverified_outcome()
    attestation = build_outcome_attestation("decision-1", "execution-1", unknown)

    assert attestation.outcome is OutcomeStatus.UNKNOWN
    assert attestation.reason_codes == ("OUTCOME_VALIDATOR_MISSING",)
    assert not_executed_outcome("DENIED").outcome is OutcomeStatus.NOT_EXECUTED
    assert failed_outcome(RuntimeError("boom")).reason_codes == ("RuntimeError",)
    with pytest.raises(ValueError, match="cannot authorize"):
        OutcomeVerification(
            OutcomeStatus.SUCCEEDED,
            "validator",
            (),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="timezone"):
        attestation.__class__(
            "decision",
            "execution",
            datetime(2026, 1, 1),
            OutcomeStatus.SUCCEEDED,
            "validator",
            None,
            (),
        )


def test_decision_record_contract_edges() -> None:
    with pytest.raises(ValueError, match="identity"):
        RunContext("", "step")
    child = RunContext("run", "parent").for_step("child")
    assert child.parent_event_id == "parent"

    descriptor = ToolDescriptor(
        "quality-triage",
        "Read local quality triage artifacts",
        ("ai4binance",),
        ToolSideEffect.READ_LOCAL,
    )
    record = build_decision_record(
        context=RunContext("run", "step"),
        project="ai4binance",
        agent="agent",
        tool="quality-triage",
        permission=ToolPermission.READ_ONLY,
        approved=False,
        descriptor=descriptor,
        decision=ToolPolicyDecision.DENY,
        reason_codes=("POLICY_DEFAULT_DENY",),
        approval_id=None,
        state_hash_before=None,
        evidence_hashes=(),
        policy_id="policy",
        policy_version="1",
    )
    with pytest.raises(ValueError, match="timestamp"):
        record.__class__(
            record.decision_id,
            datetime(2026, 1, 1),
            record.run_id,
            record.step_id,
            record.parent_event_id,
            record.project,
            record.agent,
            record.tool_name,
            record.permission,
            record.side_effect,
            record.target_hash,
            record.arguments_hash,
            record.evidence_set_hash,
            record.state_hash_before,
            record.policy_id,
            record.policy_version,
            record.policy_hash,
            record.decision,
            record.reason_codes,
        )
    with pytest.raises(ValueError, match="reason"):
        replace(record, reason_codes=())
    with pytest.raises(ValueError, match="sha256"):
        replace(record, policy_hash="bad")
    with pytest.raises(ValueError, match="validator"):
        OutcomeVerification(OutcomeStatus.SUCCEEDED, "", ())
    with pytest.raises(ValueError, match="sha256"):
        OutcomeVerification(
            OutcomeStatus.SUCCEEDED,
            "validator",
            (),
            observed_hash="bad",
        )
