from __future__ import annotations

from datetime import UTC, datetime

from ai4binance.enterprise.contracts import OpinionVerdict, WorkflowIdentity
from ai4binance.enterprise.multiops_control import (
    build_default_multiops_control_plane,
)
from ai4binance.multiops import OpsBlocker, OpsCapability, OpsDomain, OpsVerdict

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity(
        "wo-multiops",
        "run-multiops",
        "trace-multiops",
        NOW,
        snapshot_id="snapshot-multiops",
    )


def test_multiops_control_plane_blocks_checks_without_evidence() -> None:
    control = build_default_multiops_control_plane()

    result = control.evaluate_capability(
        check_id="devsecops-secret-scan",
        domain=OpsDomain.DEVSECOPS,
        capability=OpsCapability.SECRET_SCANNING,
        subject_ref="repo:ai4binance",
        evidence_refs=(),
    )
    readiness = control.to_ops_readiness(identity=identity(), result=result)

    assert result.verdict is OpsVerdict.INSUFFICIENT_EVIDENCE
    assert OpsBlocker.EVIDENCE_REQUIRED.value in result.blockers
    assert OpsBlocker.HUMAN_REVIEW_REQUIRED.value in result.blockers
    assert OpsBlocker.LIVE_BLOCKED.value in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert readiness.verdict is OpinionVerdict.INSUFFICIENT_EVIDENCE
    assert readiness.execution_allowed is False
    assert readiness.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_multiops_control_plane_accepts_evidence_as_readiness_only() -> None:
    control = build_default_multiops_control_plane()

    result = control.evaluate_capability(
        check_id="tradeops-closure-review",
        domain=OpsDomain.TRADEOPS,
        capability=OpsCapability.CLOSURE_REVIEW,
        subject_ref="paper-trade:HOTUSDT:001",
        evidence_refs=("closure-review:jsonl:001",),
    )
    readiness = control.to_ops_readiness(identity=identity(), result=result)

    assert result.verdict is OpsVerdict.PASSED
    assert result.blockers == ()
    assert result.execution_allowed is False
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert readiness.verdict is OpinionVerdict.ACCEPTED
    assert readiness.evidence_refs == (
        "tradeops-closure-review",
        "closure-review:jsonl:001",
    )
    assert readiness.blockers == ()
    assert readiness.execution_allowed is False
    assert readiness.promotion_status == "RESEARCH_ONLY"
    assert readiness.live_eligibility_status == "LIVE_ORDER_BLOCKED"
