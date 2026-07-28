from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.agents.evaluation import (
    AdvisoryEvalExpectation,
    AdvisoryEvalResult,
    AdvisoryTrace,
    evaluate_advisory_trace,
)
from ai4binance.governance.sidecar import (
    SidecarPilotAssessment,
    SidecarPilotEvidence,
    assess_sidecar_pilot,
)
from ai4binance.governance.workflow import (
    WorkflowAuthority,
    WorkflowGraph,
    WorkflowNode,
    WorkflowPreview,
    WorkflowPreviewStatus,
    market_outlook_workflow,
    preview_workflow,
)
from ai4binance.learning.governance import (
    GovernedLesson,
    LessonStatus,
    stage_learning_summary,
)
from ai4binance.learning.models import LearningSummary, LessonCandidate
from ai4binance.ops.jobs import (
    JobAdmission,
    JobCapability,
    JobManifest,
    JobRequest,
    assess_job_admission,
    nightly_quality_job_manifest,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)
HASH = "a" * 64


def lesson() -> GovernedLesson:
    return GovernedLesson.from_candidate(
        LessonCandidate("WEAK_OOS", 3, "Repeated weak OOS evidence"),
        lesson_id="lesson-1",
        source_artifact_id="learning-summary-1",
        observed_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )


def test_lesson_lifecycle_requires_validation_human_approval_and_expiry() -> None:
    item = lesson()
    for status in (
        LessonStatus.DEDUPLICATED,
        LessonStatus.CONTRADICTION_CHECKED,
        LessonStatus.VALIDATION_PENDING,
    ):
        item = item.transition(status, at=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="validation artifacts"):
        item.transition(LessonStatus.RESEARCH_ONLY, at=NOW + timedelta(minutes=2))
    item = item.transition(
        LessonStatus.RESEARCH_ONLY,
        at=NOW + timedelta(minutes=2),
        validation_artifact_ids=("oos-report-1",),
    )
    with pytest.raises(ValueError, match="human approval"):
        item.transition(LessonStatus.HUMAN_APPROVED, at=NOW + timedelta(minutes=3))
    item = item.transition(
        LessonStatus.HUMAN_APPROVED,
        at=NOW + timedelta(minutes=3),
        human_approved=True,
    )
    item = item.transition(LessonStatus.ACTIVE_LESSON, at=NOW + timedelta(minutes=4))
    assert item.execution_allowed is False
    assert item.risk_change_allowed is False
    assert item.parameter_change_allowed is False
    expired = item.transition(LessonStatus.EXPIRED, at=NOW + timedelta(days=31))
    assert expired.status is LessonStatus.EXPIRED


def test_lesson_blocks_skipped_and_expired_approval() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        lesson().transition(LessonStatus.RESEARCH_ONLY, at=NOW)
    item = lesson()
    for status in (
        LessonStatus.DEDUPLICATED,
        LessonStatus.CONTRADICTION_CHECKED,
        LessonStatus.VALIDATION_PENDING,
        LessonStatus.RESEARCH_ONLY,
    ):
        item = item.transition(
            status,
            at=NOW + timedelta(minutes=1),
            validation_artifact_ids=("oos-report",),
        )
    with pytest.raises(ValueError, match="expired"):
        item.transition(
            LessonStatus.HUMAN_APPROVED,
            at=NOW + timedelta(days=31),
            human_approved=True,
        )


def job_manifest(root: Path) -> JobManifest:
    return JobManifest(
        job_id="nightly-quality",
        allowed_capabilities=(
            JobCapability.READ_REPOSITORY,
            JobCapability.WRITE_ARTIFACT,
            JobCapability.RUN_FIXED_QUALITY_COMMANDS,
        ),
        allowed_roots=(root,),
        timeout_seconds=600,
        maximum_output_bytes=100_000,
        maximum_concurrency=1,
        lock_path=root / ".nightly.lock",
    )


def test_job_admission_requires_capability_path_timeout_and_lock(
    tmp_path: Path,
) -> None:
    request = JobRequest(
        job_id="nightly-quality",
        idempotency_key="2026-07-13",
        requested_capabilities=(JobCapability.READ_REPOSITORY,),
        target_paths=(tmp_path / "repo",),
        timeout_enforced_by_runner=True,
        lock_acquired=True,
    )
    result = assess_job_admission(job_manifest(tmp_path), request)
    assert result.admitted is True
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    blocked = assess_job_admission(
        job_manifest(tmp_path),
        replace(
            request,
            job_id="other",
            target_paths=(tmp_path.parent / "outside",),
            network_requested=True,
            timeout_enforced_by_runner=False,
            lock_acquired=False,
        ),
    )
    assert blocked.blockers == (
        "JOB_IDENTITY_MISMATCH",
        "JOB_PATH_NOT_ALLOWED",
        "JOB_NETWORK_NOT_ALLOWED",
        "JOB_TIMEOUT_NOT_ENFORCED",
        "JOB_LOCK_NOT_ACQUIRED",
    )


def advisory_trace(
    *,
    fixture_id: str = "fixture-1",
    citations: tuple[str, ...] = ("artifact-1",),
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",),
    duration_ms: int = 50,
) -> AdvisoryTrace:
    return AdvisoryTrace(
        trace_id="trace-1",
        fixture_id=fixture_id,
        model_id="advisory-model",
        prompt_revision="prompt-v1",
        input_sha256=HASH,
        output_sha256=HASH,
        citations=citations,
        blockers=blockers,
        started_at=NOW,
        finished_at=NOW + timedelta(milliseconds=duration_ms),
    )


def test_advisory_eval_is_deterministic_and_never_promotion_evidence() -> None:
    expectation = AdvisoryEvalExpectation(
        fixture_id="fixture-1",
        required_citations=("artifact-1",),
        required_blockers=("LIVE_ORDER_BLOCKED",),
        maximum_duration_ms=100,
    )
    passed = evaluate_advisory_trace(advisory_trace(), expectation)
    assert passed.passed is True
    assert passed.grader == "DETERMINISTIC_RULES"
    assert passed.promotion_evidence is False
    assert passed.execution_allowed is False

    failed = evaluate_advisory_trace(
        advisory_trace(
            fixture_id="other",
            citations=(),
            blockers=(),
            duration_ms=101,
        ),
        expectation,
    )
    assert failed.blockers == (
        "ADVISORY_FIXTURE_MISMATCH",
        "ADVISORY_REQUIRED_CITATION_MISSING",
        "ADVISORY_REQUIRED_BLOCKER_MISSING",
        "ADVISORY_LATENCY_BUDGET_EXCEEDED",
    )


def test_market_outlook_graph_is_deterministic_read_only_dag() -> None:
    graph = market_outlook_workflow()
    assert graph.topological_order() == (
        "market_data",
        "market_outlook",
        "setup_radar",
        "candidate_arbitration",
        "risk_evaluation",
        "paper_proposal",
        "closure_review",
    )
    assert graph.execution_allowed is False
    assert graph.nodes[-2].authority is WorkflowAuthority.PAPER_PROPOSAL
    preview = preview_workflow(
        graph,
        validation_points=("risk_evaluation", "paper_proposal", "closure_review"),
    )
    assert preview.status == "HUMAN_REVIEW_REQUIRED"
    assert preview.execution_allowed is False
    assert preview.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "LIVE_ORDER_BLOCKED" in preview.blockers


def test_workflow_graph_rejects_unknown_dependencies_and_cycles() -> None:
    node = WorkflowNode(
        "a", "TEST", ("missing",), (), (), 1, WorkflowAuthority.READ_ONLY
    )
    with pytest.raises(ValueError, match="unknown"):
        WorkflowGraph("graph", (node,))
    cycle_a = replace(node, dependencies=("b",))
    cycle_b = replace(node, node_id="b", dependencies=("a",))
    with pytest.raises(ValueError, match="cycle"):
        WorkflowGraph("graph", (cycle_a, cycle_b))


def test_workflow_preview_rejects_authority_drift() -> None:
    with pytest.raises(ValueError, match="identity"):
        WorkflowPreview(
            "",
            ("a",),
            ("a",),
        )
    with pytest.raises(ValueError, match="validation point"):
        WorkflowPreview(
            "graph",
            ("a",),
            ("missing",),
        )
    with pytest.raises(ValueError, match="review-only"):
        WorkflowPreview(
            "graph",
            ("a",),
            ("a",),
            status=WorkflowPreviewStatus.HUMAN_REVIEW_REQUIRED,
            blockers=("HUMAN_REVIEW_REQUIRED",),
        )
    with pytest.raises(ValueError, match="review-only"):
        WorkflowPreview(
            "graph",
            ("a",),
            ("a",),
            execution_allowed=True,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(lesson(), lesson_id=""),
        lambda: replace(lesson(), evidence_count=0),
        lambda: replace(lesson(), source_artifact_ids=()),
        lambda: replace(lesson(), source_artifact_ids=("a", "a")),
        lambda: replace(lesson(), source_artifact_ids=("",)),
        lambda: replace(lesson(), observed_at=datetime(2026, 7, 13)),
        lambda: replace(lesson(), expires_at=NOW),
        lambda: replace(lesson(), validation_artifact_ids=("a", "a")),
        lambda: replace(lesson(), execution_allowed=True),
        lambda: replace(
            lesson(),
            status=LessonStatus.HUMAN_APPROVED,
            validation_artifact_ids=(),
        ),
    ],
)
def test_lesson_contract_rejects_invalid_shapes(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_lesson_terminal_and_blocked_transitions_are_rejected() -> None:
    rejected = lesson().transition(LessonStatus.REJECTED, at=NOW)
    with pytest.raises(ValueError, match="terminal"):
        rejected.transition(LessonStatus.EXPIRED, at=NOW)
    with pytest.raises(ValueError, match="terminal"):
        rejected.transition(LessonStatus.DEDUPLICATED, at=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        lesson().transition(LessonStatus.DEDUPLICATED, at=datetime(2026, 7, 13))

    item = lesson()
    for status in (
        LessonStatus.DEDUPLICATED,
        LessonStatus.CONTRADICTION_CHECKED,
        LessonStatus.VALIDATION_PENDING,
        LessonStatus.RESEARCH_ONLY,
    ):
        item = item.transition(
            status,
            at=NOW + timedelta(minutes=1),
            validation_artifact_ids=("oos",),
        )
    with pytest.raises(ValueError, match="blocked"):
        item.transition(
            LessonStatus.HUMAN_APPROVED,
            at=NOW + timedelta(minutes=2),
            blockers=("CONTRADICTION",),
            human_approved=True,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(job_manifest(Path("C:/repo")), job_id=""),
        lambda: replace(job_manifest(Path("C:/repo")), allowed_capabilities=()),
        lambda: replace(job_manifest(Path("C:/repo")), allowed_roots=(Path("repo"),)),
        lambda: replace(job_manifest(Path("C:/repo")), lock_path=Path("lock")),
        lambda: replace(job_manifest(Path("C:/repo")), timeout_seconds=0),
        lambda: replace(job_manifest(Path("C:/repo")), maximum_output_bytes=1),
        lambda: replace(job_manifest(Path("C:/repo")), maximum_concurrency=0),
        lambda: replace(job_manifest(Path("C:/repo")), network_allowed=True),
        lambda: JobRequest("", "key", (JobCapability.READ_REPOSITORY,), (), True, True),
        lambda: JobRequest("job", "key", (), (), True, True),
        lambda: JobRequest(
            "job",
            "key",
            (JobCapability.READ_REPOSITORY,),
            (Path("relative"),),
            True,
            True,
        ),
        lambda: JobAdmission("job", "key", True, ("BLOCKER",)),
        lambda: JobAdmission("job", "key", True, (), execution_allowed=True),
    ],
)
def test_job_contract_rejects_invalid_shapes(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_job_blocks_unlisted_capability(tmp_path: Path) -> None:
    request = JobRequest(
        "nightly-quality",
        "key",
        (JobCapability.RUN_FIXED_QUALITY_COMMANDS,),
        (),
        True,
        True,
    )
    restricted = replace(
        job_manifest(tmp_path),
        allowed_capabilities=(JobCapability.READ_REPOSITORY,),
    )
    assert assess_job_admission(restricted, request).blockers == (
        "JOB_CAPABILITY_NOT_ALLOWED",
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(advisory_trace(), trace_id=""),
        lambda: replace(advisory_trace(), input_sha256="bad"),
        lambda: replace(advisory_trace(), citations=("a", "a")),
        lambda: replace(advisory_trace(), started_at=datetime(2026, 7, 13)),
        lambda: replace(advisory_trace(), finished_at=NOW - timedelta(seconds=1)),
        lambda: replace(advisory_trace(), redacted=False),
        lambda: AdvisoryEvalExpectation("", (), (), 1),
        lambda: AdvisoryEvalExpectation("fixture", (), (), 0),
        lambda: AdvisoryEvalResult("trace", True, ("BLOCKER",)),
        lambda: AdvisoryEvalResult("trace", True, (), promotion_evidence=True),
    ],
)
def test_advisory_contract_rejects_invalid_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: WorkflowNode("", "TEST", (), (), (), 1, WorkflowAuthority.READ_ONLY),
        lambda: WorkflowNode("a", "TEST", (), (), (), 0, WorkflowAuthority.READ_ONLY),
        lambda: WorkflowNode(
            "a", "TEST", ("b", "b"), (), (), 1, WorkflowAuthority.READ_ONLY
        ),
        lambda: WorkflowNode(
            "a",
            "TEST",
            (),
            (),
            (),
            1,
            WorkflowAuthority.READ_ONLY,
            execution_allowed=True,
        ),
        lambda: WorkflowGraph("", (market_outlook_workflow().nodes[0],)),
        lambda: WorkflowGraph("graph", (market_outlook_workflow().nodes[0],) * 2),
        lambda: replace(market_outlook_workflow(), execution_allowed=True),
    ],
)
def test_workflow_contract_rejects_invalid_shapes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_learning_summary_stages_only_unapproved_lessons() -> None:
    summary = LearningSummary(
        summary_id="summary-1",
        created_at=NOW,
        lessons=(LessonCandidate("WEAK_OOS", 2, "Needs validation"),),
        experiments=(),
    )
    staged = stage_learning_summary(summary, expires_at=NOW + timedelta(days=30))
    assert len(staged) == 1
    assert staged[0].status is LessonStatus.OBSERVED
    assert staged[0].source_artifact_ids == ("summary-1",)
    assert staged[0].execution_allowed is False


def test_nightly_quality_manifest_matches_existing_safe_loop(tmp_path: Path) -> None:
    manifest = nightly_quality_job_manifest(tmp_path, tmp_path / "artifacts")
    assert manifest.maximum_concurrency == 1
    assert manifest.network_allowed is False
    assert manifest.secret_access_allowed is False
    assert manifest.trading_authority is False
    with pytest.raises(ValueError, match="absolute"):
        nightly_quality_job_manifest(Path("relative"), tmp_path)


def sidecar_evidence(
    *,
    localhost_bound: bool = True,
    authentication_enabled: bool = True,
    ssrf_protection_enabled: bool = True,
    external_network_disabled: bool = True,
    arbitrary_code_disabled: bool = True,
    read_only_artifacts: bool = True,
    resource_limits_enabled: bool = True,
    secrets_mounted: bool = False,
    exchange_adapter_present: bool = False,
) -> SidecarPilotEvidence:
    return SidecarPilotEvidence(
        component_id="langflow-isolated-pilot",
        image_digest=f"sha256:{HASH}",
        localhost_bound=localhost_bound,
        authentication_enabled=authentication_enabled,
        ssrf_protection_enabled=ssrf_protection_enabled,
        external_network_disabled=external_network_disabled,
        arbitrary_code_disabled=arbitrary_code_disabled,
        read_only_artifacts=read_only_artifacts,
        resource_limits_enabled=resource_limits_enabled,
        secrets_mounted=secrets_mounted,
        exchange_adapter_present=exchange_adapter_present,
    )


def test_sidecar_pilot_is_default_deny_and_read_only() -> None:
    allowed = assess_sidecar_pilot(sidecar_evidence())
    assert allowed.pilot_allowed is True
    assert allowed.read_only is True
    assert allowed.execution_allowed is False
    assert allowed.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    blocked = assess_sidecar_pilot(
        sidecar_evidence(
            localhost_bound=False,
            authentication_enabled=False,
            ssrf_protection_enabled=False,
            external_network_disabled=False,
            arbitrary_code_disabled=False,
            read_only_artifacts=False,
            resource_limits_enabled=False,
            secrets_mounted=True,
            exchange_adapter_present=True,
        )
    )
    assert blocked.pilot_allowed is False
    assert len(blocked.blockers) == 9


def test_sidecar_contract_rejects_unpinned_or_authorized_shapes() -> None:
    with pytest.raises(ValueError, match="digest"):
        replace(sidecar_evidence(), image_digest="latest")
    with pytest.raises(ValueError, match="disagree"):
        SidecarPilotAssessment("langflow", True, ("BLOCKER",))
    with pytest.raises(ValueError, match="read-only"):
        SidecarPilotAssessment("langflow", True, (), execution_allowed=True)
