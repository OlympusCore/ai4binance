from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from ai4binance.enterprise.contracts import (
    OpinionVerdict,
    OpsReadiness,
    WorkflowIdentity,
)
from ai4binance.enterprise.multiops_control import (
    MultiOpsRunnerAdmissionReview,
    _readiness_verdict,
    build_default_multiops_control_plane,
)
from ai4binance.multiops import (
    OpsBlocker,
    OpsCapability,
    OpsCheckResult,
    OpsDomain,
    OpsVerdict,
)
from ai4binance.ops.jobs import (
    JobCapability,
    JobRequest,
    JobSideEffect,
    RunnerAdmissionReport,
    nightly_quality_runner_manifest,
)

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


def test_multiops_control_plane_evaluates_runner_admission_as_report_only(
    tmp_path: Path,
) -> None:
    control = build_default_multiops_control_plane()
    review = control.evaluate_runner_admission(
        identity=identity(),
        runner_manifest=nightly_quality_runner_manifest(
            tmp_path,
            tmp_path / "artifacts",
        ),
        request=JobRequest(
            job_id="nightly-quality-triage",
            idempotency_key="2026-08-31T0200Z",
            requested_capabilities=(
                JobCapability.READ_REPOSITORY,
                JobCapability.WRITE_ARTIFACT,
                JobCapability.RUN_FIXED_QUALITY_COMMANDS,
            ),
            target_paths=(tmp_path, tmp_path / "artifacts"),
            timeout_enforced_by_runner=True,
            lock_acquired=True,
            requested_side_effects=(
                JobSideEffect.READ_REPOSITORY,
                JobSideEffect.WRITE_RUNTIME_ARTIFACTS,
                JobSideEffect.RUN_FIXED_QUALITY_COMMANDS,
            ),
            runner_id="runner:nightly-quality-triage",
            command_ref=(
                "powershell.exe -NoProfile -ExecutionPolicy Bypass "
                "-File .\\scripts\\quality.ps1"
            ),
        ),
        domain=OpsDomain.DEVSECOPS,
        capability=OpsCapability.CI,
        subject_ref="repo:ai4binance",
        evidence_refs=("quality-gate:latest",),
        observed_at=NOW,
    )

    assert isinstance(review, MultiOpsRunnerAdmissionReview)
    assert review.status == "RUNNER_READY_REPORT_ONLY"
    assert review.runner_report.blockers == ()
    assert review.ops_check.verdict is OpsVerdict.PASSED
    assert review.readiness.verdict is OpinionVerdict.ACCEPTED
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_multiops_control_plane_blocks_runner_without_subject_evidence(
    tmp_path: Path,
) -> None:
    control = build_default_multiops_control_plane()
    review = control.evaluate_runner_admission(
        identity=identity(),
        runner_manifest=nightly_quality_runner_manifest(
            tmp_path,
            tmp_path / "artifacts",
        ),
        request=JobRequest(
            job_id="nightly-quality-triage",
            idempotency_key="2026-08-31T0300Z",
            requested_capabilities=(JobCapability.READ_REPOSITORY,),
            target_paths=(tmp_path,),
            timeout_enforced_by_runner=True,
            lock_acquired=True,
            requested_side_effects=(JobSideEffect.READ_REPOSITORY,),
            runner_id="runner:nightly-quality-triage",
        ),
        domain=OpsDomain.DEVSECOPS,
        capability=OpsCapability.CI,
        subject_ref="repo:ai4binance",
        evidence_refs=(),
        observed_at=NOW,
    )

    assert review.status == "RUNNER_BLOCKED"
    assert review.ops_check.verdict is OpsVerdict.INSUFFICIENT_EVIDENCE
    assert OpsBlocker.EVIDENCE_REQUIRED.value in review.blockers
    assert "RUNNER_SUBJECT_EVIDENCE_REQUIRED" in review.blockers
    assert review.readiness.verdict is OpinionVerdict.INSUFFICIENT_EVIDENCE


def test_multiops_runner_review_rejects_invalid_or_authorizing_states() -> None:
    values: dict[str, object] = {
        "runner_report": cast(RunnerAdmissionReport, object()),
        "ops_check": cast(OpsCheckResult, object()),
        "readiness": cast(OpsReadiness, object()),
        "status": "RUNNER_BLOCKED",
        "blockers": ("EVIDENCE_MISSING",),
    }
    for overrides, message in (
        ({"status": "INVALID"}, "status is invalid"),
        ({"blockers": ("DUPLICATE", "DUPLICATE")}, "must be unique"),
        ({"blockers": ()}, "requires blockers"),
        (
            {"status": "RUNNER_READY_REPORT_ONLY", "blockers": ("BLOCKED",)},
            "cannot contain blockers",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "PAPER_APPROVED"}, "cannot promote"),
        ({"live_eligibility_status": "LIVE_READY"}, "remain live blocked"),
    ):
        attempt = dict(values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            MultiOpsRunnerAdmissionReview(**attempt)  # type: ignore[arg-type]


def test_multiops_readiness_mapping_preserves_non_accepting_verdicts() -> None:
    assert (
        _readiness_verdict(OpsVerdict.REVISION_REQUIRED)
        is OpinionVerdict.REVISION_REQUIRED
    )
    assert (
        _readiness_verdict(OpsVerdict.INSUFFICIENT_EVIDENCE)
        is OpinionVerdict.INSUFFICIENT_EVIDENCE
    )
    assert _readiness_verdict(OpsVerdict.BLOCKED) is OpinionVerdict.REJECTED
