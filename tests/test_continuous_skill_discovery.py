from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request

import pytest

from ai4binance.config import Settings
from ai4binance.governance.workflow import AgentWorkspaceComponentStatus
from ai4binance.skills import (
    ContinuousDiscoveryStageId,
    ContinuousDiscoveryStageReview,
    ContinuousDiscoveryStageReviewerResult,
    ContinuousSkillDiscoveryEngine,
    DiscoveryCandidate,
    DiscoveryDecision,
    ScoreDecision,
    SkillDiscoveryRuntime,
    SourceDocument,
    StaticCandidateScout,
    StaticDocumentationFetcher,
    audit_skill_root,
    build_skill_discovery_runtime,
    discovery_pipeline,
    filter_candidate,
    github_discovery,
    read_skill_discovery_status,
    review_discovery_stage,
    workspace_component_evidence_from_draft,
)
from ai4binance.skills.continuous_discovery import LIBRARY_ADMISSION_APPROVAL_MARKER
from ai4binance.skills.continuous_runtime import SkillDiscoverySupervisor
from ai4binance.skills.github_discovery import GitHubSearchScout

NOW = datetime(2026, 8, 1, tzinfo=UTC)
PINNED = "a" * 40


def candidate(
    *,
    repository: str = "example/agent-workflow",
    source_url: str = "https://github.com/example/agent-workflow",
    description: str = "Reusable agent workflow and skill review pipeline",
    stars: int = 842,
    language: str = "Python",
    archived: bool = False,
    pushed_at: datetime = datetime(2026, 7, 1, tzinfo=UTC),
    pinned_revision: str | None = PINNED,
    topics: tuple[str, ...] = ("agent", "workflow"),
) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        repository=repository,
        source_url=source_url,
        description=description,
        stars=stars,
        language=language,
        archived=archived,
        pushed_at=pushed_at,
        discovered_at=NOW,
        pinned_revision=pinned_revision,
        topics=topics,
    )


def documents() -> tuple[SourceDocument, ...]:
    return (
        SourceDocument(
            "README.md",
            (
                "Agent workflow pipeline with discover filter read extract score "
                "generate review publish stages."
            ),
        ),
        SourceDocument(
            "examples/example.md",
            "Example review rubric for reusable validation workflow skills.",
        ),
    )


def test_filter_requires_fresh_pinned_reusable_repository() -> None:
    kept = filter_candidate(
        candidate(),
        min_stars=100,
        allowed_languages=("Python",),
        pushed_after=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert kept.decision is DiscoveryDecision.KEEP
    assert kept.execution_allowed is False
    assert kept.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    rejected = filter_candidate(
        candidate(
            repository="example/css-animation",
            source_url="https://github.com/example/css-animation",
            stars=1,
            pinned_revision=None,
            description="CSS animation library",
            topics=("css",),
        ),
        min_stars=100,
        allowed_languages=("Python",),
        pushed_after=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert rejected.decision is DiscoveryDecision.REJECT
    assert rejected.reasons == (
        "STAR_THRESHOLD_NOT_MET",
        "AI_WORKFLOW_SCOPE_NOT_EVIDENT",
        "PINNED_REVISION_REQUIRED",
    )


def test_engine_creates_quarantined_draft_and_verified_state(tmp_path: Path) -> None:
    engine = ContinuousSkillDiscoveryEngine(
        scout=StaticCandidateScout((candidate(),)),
        fetcher=StaticDocumentationFetcher({candidate().repository: documents()}),
        staging_directory=tmp_path / "runtime" / "skill_staging",
        state_path=tmp_path / "runtime" / "state" / "skill_discovery.json",
        ledger_path=tmp_path / "logs" / "skill_discovery_events.jsonl",
    )

    report = engine.run_once(
        queries=("agent workflow",),
        max_candidates=1,
        min_score=0.85,
        now=NOW,
    )

    assert report.candidates_seen == 1
    assert report.candidates_kept == 1
    assert report.drafts_created == 1
    assert len(report.admission_records) == 1
    assert report.admission_records[0].status == "NOT_ADMITTED"
    assert report.admission_records[0].approval_marker == (
        LIBRARY_ADMISSION_APPROVAL_MARKER
    )
    assert report.blockers == ()
    assert len(report.workspace_component_reviews) == 1
    workspace_review = report.workspace_component_reviews[0]
    assert (
        workspace_review.status is AgentWorkspaceComponentStatus.RESEARCH_ONLY_WORKSPACE
    )
    assert workspace_review.component_id == "agent-workflow"
    assert workspace_review.source_path.endswith("agent-workflow/SKILL.md")
    assert workspace_review.blockers == (
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.scores[0].decision is ScoreDecision.PASS
    assert tuple(review.stage_id for review in report.stage_reviews) == (
        ContinuousDiscoveryStageId.SCOUT,
        ContinuousDiscoveryStageId.FILTER,
        ContinuousDiscoveryStageId.READER,
        ContinuousDiscoveryStageId.EXTRACTOR,
        ContinuousDiscoveryStageId.SCORE,
        ContinuousDiscoveryStageId.GENERATOR,
        ContinuousDiscoveryStageId.REVIEWER,
        ContinuousDiscoveryStageId.PUBLISHER,
    )
    assert all(
        review.reviewer_result is ContinuousDiscoveryStageReviewerResult.PASSED
        for review in report.stage_reviews
    )
    assert all(len(review.input_sha256) == 64 for review in report.stage_reviews)
    assert all(len(review.output_sha256) == 64 for review in report.stage_reviews)
    assert all(review.citations for review in report.stage_reviews)
    assert all(review.execution_allowed is False for review in report.stage_reviews)
    draft_dir = Path(report.drafts[0].draft_directory)
    assert (draft_dir / "SKILL.md").exists()
    assert (draft_dir / "metadata.json").exists()
    assert (draft_dir / "workspace-review.json").exists()
    workspace_payload = json.loads(
        (draft_dir / "workspace-review.json").read_text(encoding="utf-8")
    )
    assert workspace_payload["status"] == "RESEARCH_ONLY_WORKSPACE"
    assert workspace_payload["execution_allowed"] is False
    assert (
        json.loads((draft_dir / "metadata.json").read_text(encoding="utf-8"))[
            "library_admission_approval_marker"
        ]
        == LIBRARY_ADMISSION_APPROVAL_MARKER
    )
    assert "HUMAN_REVIEW_REQUIRED" in (draft_dir / "review.md").read_text(
        encoding="utf-8"
    )
    record_dir = tmp_path / "runtime" / "skill_staging" / "_admit"
    admission = record_dir / "agent-workflow" / "admission.json"
    assert admission.exists()
    admission_payload = json.loads(admission.read_text(encoding="utf-8"))
    assert admission_payload["status"] == "NOT_ADMITTED"
    assert admission_payload["not_admitted_reasons"] == [
        "HUMAN_REVIEW_REQUIRED",
        "PR_REQUIRED",
    ]
    assert admission_payload["approval_marker"] == LIBRARY_ADMISSION_APPROVAL_MARKER
    assert "github_remediation_queries" in admission_payload
    assert (admission.parent / "github-resolution.md").exists()
    audit = audit_skill_root(tmp_path / "runtime" / "skill_staging")
    assert audit.skill_count == 1
    assert audit.blockers == ()
    state_path = tmp_path / "runtime" / "state" / "skill_discovery.json"
    assert state_path.exists()
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["workspace_component_reviews"][0]["component_id"] == (
        "agent-workflow"
    )
    assert state_payload["stage_reviews"][0]["stage_id"] == "SCOUT"
    assert state_payload["stage_reviews"][-1]["stage_id"] == "PUBLISHER"
    assert (tmp_path / "logs" / "skill_discovery_events.jsonl").exists()
    evidence = workspace_component_evidence_from_draft(
        candidate=candidate(),
        score=report.scores[0],
        draft=report.drafts[0],
    )
    assert evidence.component_id == "agent-workflow"
    assert evidence.execution_allowed is False


def test_engine_rejects_authority_drift_without_draft(tmp_path: Path) -> None:
    risky_docs = (
        SourceDocument(
            "README.md",
            "Agent workflow that can bypass risk gate and place order.",
        ),
        SourceDocument("examples/example.md", "Example workflow."),
    )
    engine = ContinuousSkillDiscoveryEngine(
        scout=StaticCandidateScout((candidate(),)),
        fetcher=StaticDocumentationFetcher({candidate().repository: risky_docs}),
        staging_directory=tmp_path / "runtime" / "skill_staging",
        state_path=tmp_path / "state" / "skill_discovery.json",
        ledger_path=tmp_path / "logs" / "skill_discovery_events.jsonl",
    )

    report = engine.run_once(
        queries=("agent workflow",),
        max_candidates=1,
        min_score=0.85,
        now=NOW,
    )

    assert report.drafts_created == 0
    assert "CHECK_FAILED:GENERAL_PURPOSE" in report.blockers
    assert len(report.admission_records) == 1
    assert report.admission_records[0].status == "NOT_ADMITTED"
    assert "CHECK_FAILED:GENERAL_PURPOSE" in report.admission_records[0].reasons
    assert "GENERAL PURPOSE" in (
        tmp_path
        / "runtime"
        / "skill_staging"
        / "_admit"
        / "agent-workflow"
        / "github-resolution.md"
    ).read_text(encoding="utf-8")
    assert not (
        tmp_path / "runtime" / "skill_staging" / "agent-workflow-workflow"
    ).exists()


def test_engine_watchlists_trading_scope_workspace_review(tmp_path: Path) -> None:
    trading_candidate = candidate(
        repository="example/market-agent",
        source_url="https://github.com/example/market-agent",
        description="Reusable agent workflow for market strategy validation",
        topics=("agent", "workflow", "strategy"),
    )
    trading_docs = (
        SourceDocument(
            "README.md",
            (
                "Agent workflow pipeline with discover filter read extract score "
                "generate review publish stages for market strategy validation."
            ),
        ),
        SourceDocument(
            "examples/example.md",
            "Example review rubric for reusable validation workflow skills.",
        ),
    )
    engine = ContinuousSkillDiscoveryEngine(
        scout=StaticCandidateScout((trading_candidate,)),
        fetcher=StaticDocumentationFetcher(
            {trading_candidate.repository: trading_docs}
        ),
        staging_directory=tmp_path / "runtime" / "skill_staging",
        state_path=tmp_path / "state" / "skill_discovery.json",
        ledger_path=tmp_path / "logs" / "skill_discovery_events.jsonl",
    )

    report = engine.run_once(
        queries=("agent workflow",),
        max_candidates=1,
        min_score=0.85,
        now=NOW,
    )

    assert report.drafts_created == 1
    assert "WORKSPACE_TRADING_SCOPE_REVIEW_REQUIRED" in report.blockers
    assert (
        report.workspace_component_reviews[0].status
        is AgentWorkspaceComponentStatus.WATCHLIST
    )
    assert "WORKSPACE_TRADING_SCOPE_REVIEW_REQUIRED" in (
        report.workspace_component_reviews[0].blockers
    )
    reviewer_stage = next(
        review
        for review in report.stage_reviews
        if review.stage_id is ContinuousDiscoveryStageId.REVIEWER
    )
    assert (
        reviewer_stage.reviewer_result
        is ContinuousDiscoveryStageReviewerResult.WATCHLIST
    )
    assert "WORKSPACE_TRADING_SCOPE_REVIEW_REQUIRED" in reviewer_stage.blockers
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_rejected_filter_keeps_library_record_and_marker_readiness(
    tmp_path: Path,
) -> None:
    rejected = candidate(
        repository="example/css-animation",
        source_url="https://github.com/example/css-animation",
        stars=1,
        pinned_revision=None,
        description="CSS animation library",
        topics=("css",),
    )
    record_dir = (
        tmp_path / "runtime" / "skill_staging" / "_admit" / "css-animation-workflow"
    )
    record_dir.mkdir(parents=True)
    (record_dir / LIBRARY_ADMISSION_APPROVAL_MARKER).write_text(
        "human-approved remediation evidence\n",
        encoding="utf-8",
    )
    engine = ContinuousSkillDiscoveryEngine(
        scout=StaticCandidateScout((rejected,)),
        fetcher=StaticDocumentationFetcher({}),
        staging_directory=tmp_path / "runtime" / "skill_staging",
        state_path=tmp_path / "state" / "skill_discovery.json",
        ledger_path=tmp_path / "logs" / "skill_discovery_events.jsonl",
    )

    report = engine.run_once(
        queries=("agent workflow",),
        max_candidates=1,
        min_score=0.85,
        now=NOW,
    )

    assert report.drafts_created == 0
    assert report.admission_records[0].status == "READY_FOR_LIBRARY_PR"
    assert report.admission_records[0].approval_marker_present is True
    admission_payload = json.loads(
        (record_dir / "admission.json").read_text(encoding="utf-8")
    )
    assert admission_payload["not_admitted_reasons"] == [
        "STAR_THRESHOLD_NOT_MET",
        "AI_WORKFLOW_SCOPE_NOT_EVIDENT",
        "PINNED_REVISION_REQUIRED",
    ]


def test_stage_review_watchlists_missing_citation() -> None:
    review = review_discovery_stage(
        cycle_id="cycle-1",
        stage_id=ContinuousDiscoveryStageId.READER,
        subject_id="example/agent-workflow",
        input_payload={"path": "README.md"},
        output_payload={"loaded": False},
        citations=(),
    )

    assert review.reviewer_result is ContinuousDiscoveryStageReviewerResult.WATCHLIST
    assert review.citations == ("artifact://stage-citation-missing",)
    assert "STAGE_CITATION_REQUIRED" in review.blockers
    assert review.execution_allowed is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_contracts_reject_authority_drift_and_bad_shapes() -> None:
    base = candidate()
    with pytest.raises(ValueError, match="execution authority"):
        replace(base, execution_allowed=True)
    with pytest.raises(ValueError, match="live blocked"):
        replace(base, live_eligibility_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(base, source_url="https://token@example.com/repo")
    with pytest.raises(ValueError, match="owner/name"):
        replace(base, repository="missing-owner")
    with pytest.raises(ValueError, match="input hash"):
        ContinuousDiscoveryStageReview(
            cycle_id="cycle-1",
            stage_id=ContinuousDiscoveryStageId.SCORE,
            subject_id="example/agent-workflow",
            input_sha256="not-a-hash",
            output_sha256="0" * 64,
            citations=("https://github.com/example/agent-workflow",),
            reviewer_result=ContinuousDiscoveryStageReviewerResult.PASSED,
            blockers=(
                "STAGE_REVIEW_READ_ONLY",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        )
    with pytest.raises(ValueError, match="cannot contain blockers"):
        ContinuousDiscoveryStageReview(
            cycle_id="cycle-1",
            stage_id=ContinuousDiscoveryStageId.SCORE,
            subject_id="example/agent-workflow",
            input_sha256="0" * 64,
            output_sha256="1" * 64,
            citations=("https://github.com/example/agent-workflow",),
            reviewer_result=ContinuousDiscoveryStageReviewerResult.PASSED,
            blockers=(
                "CHECK_FAILED:CONFIDENCE_THRESHOLD",
                "STAGE_REVIEW_READ_ONLY",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        )


class JsonResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> JsonResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


def test_github_scout_parses_and_deduplicates_public_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "items": [
            {
                "full_name": "example/agent-workflow",
                "html_url": "https://github.com/example/agent-workflow",
                "description": "Reusable agent workflow",
                "stargazers_count": "250",
                "language": "Python",
                "archived": False,
                "pushed_at": "2026-07-20T00:00:00Z",
                "default_branch": "main",
                "topics": ["agent", "workflow"],
            },
            {
                "full_name": "example/agent-workflow",
                "html_url": "https://github.com/example/agent-workflow",
                "description": "Duplicate",
                "stargazers_count": 1,
                "language": "Python",
                "archived": False,
                "pushed_at": "bad-date",
            },
        ]
    }

    def fake_urlopen(request: Request, timeout: float) -> JsonResponse:
        assert "api.github.com/search/repositories" in request.full_url
        assert timeout == 10.0
        return JsonResponse(json_bytes(payload))

    monkeypatch.setattr(github_discovery, "urlopen", fake_urlopen)

    candidates = GitHubSearchScout().discover(
        queries=("agent workflow",),
        max_candidates=5,
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].repository == "example/agent-workflow"
    assert candidates[0].stars == 250
    assert candidates[0].pushed_at.tzinfo is not None


def test_github_scout_rejects_invalid_shapes_and_large_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        GitHubSearchScout(api_base_url="http://api.github.com")
    with pytest.raises(ValueError, match="max_candidates"):
        GitHubSearchScout().discover(queries=("x",), max_candidates=0, now=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        GitHubSearchScout().discover(
            queries=("x",),
            max_candidates=1,
            now=datetime(2026, 8, 1),
        )
    with pytest.raises(ValueError, match="timeout"):
        GitHubSearchScout(timeout_seconds=0.0)
    with pytest.raises(ValueError, match="payload limit"):
        GitHubSearchScout(maximum_payload_bytes=1)
    assert GitHubSearchScout()._search("   ", per_page=1) == ()

    def fake_urlopen(request: Request, timeout: float) -> JsonResponse:
        del request, timeout
        return JsonResponse(b"x" * 10_002)

    monkeypatch.setattr(github_discovery, "urlopen", fake_urlopen)
    scout = GitHubSearchScout(maximum_payload_bytes=10_000)
    with pytest.raises(ValueError, match="payload"):
        scout.discover(queries=("agent",), max_candidates=1, now=NOW)


def test_github_scout_rejects_unexpected_response_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_array_response(request: Request, timeout: float) -> JsonResponse:
        del request, timeout
        return JsonResponse(b"[]")

    monkeypatch.setattr(github_discovery, "urlopen", fake_array_response)
    with pytest.raises(ValueError, match="JSON object"):
        GitHubSearchScout().discover(queries=("agent",), max_candidates=1, now=NOW)

    def fake_items_response(request: Request, timeout: float) -> JsonResponse:
        del request, timeout
        return JsonResponse(json_bytes({"items": {}}))

    monkeypatch.setattr(github_discovery, "urlopen", fake_items_response)
    with pytest.raises(ValueError, match="items"):
        GitHubSearchScout().discover(queries=("agent",), max_candidates=1, now=NOW)


def test_documentation_fetcher_reads_bounded_raw_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="timeout"):
        discovery_pipeline.GitHubDocumentationFetcher(timeout_seconds=0.0)
    with pytest.raises(ValueError, match="byte limit"):
        discovery_pipeline.GitHubDocumentationFetcher(max_total_bytes=1)

    def fake_urlopen(request: Request, timeout: float) -> JsonResponse:
        assert timeout == 10.0
        if request.full_url.endswith(f"/{PINNED}/README.md"):
            return JsonResponse(b"hello workflow")
        raise OSError("not found")

    monkeypatch.setattr(discovery_pipeline, "urlopen", fake_urlopen)
    plan = discovery_pipeline.build_read_plan(candidate())

    docs = discovery_pipeline.GitHubDocumentationFetcher().fetch(plan)

    assert docs == (SourceDocument("README.md", "hello workflow"),)


def test_engine_records_discovery_failure_without_secret_details(
    tmp_path: Path,
) -> None:
    class FailingScout:
        def discover(
            self,
            *,
            queries: Sequence[str],
            max_candidates: int,
            now: datetime,
        ) -> tuple[DiscoveryCandidate, ...]:
            del queries, max_candidates, now
            raise OSError("private-token-value")

    engine = ContinuousSkillDiscoveryEngine(
        scout=FailingScout(),
        fetcher=StaticDocumentationFetcher({}),
        staging_directory=tmp_path / "runtime" / "skill_staging",
        state_path=tmp_path / "state" / "skill_discovery.json",
        ledger_path=tmp_path / "logs" / "skill_discovery_events.jsonl",
    )

    report = engine.run_once(
        queries=("agent workflow",),
        max_candidates=1,
        min_score=0.85,
        now=NOW,
    )

    assert report.blockers == ("GITHUB_DISCOVERY_UNAVAILABLE",)
    ledger_text = (tmp_path / "logs" / "skill_discovery_events.jsonl").read_text(
        encoding="utf-8"
    )
    assert "private-token-value" not in ledger_text


def test_status_and_supervisor_reject_invalid_runtime_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    missing = read_skill_discovery_status(settings)
    assert missing["blockers"] == ("SKILL_DISCOVERY_STATE_UNAVAILABLE",)

    state_path = tmp_path / "runtime" / "state" / "skill_discovery.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("[]", encoding="utf-8")
    invalid = read_skill_discovery_status(settings)
    assert invalid["blockers"] == ("SKILL_DISCOVERY_STATE_INVALID",)

    runtime = build_skill_discovery_runtime(
        settings,
        source_file=None,
        max_candidates=1,
        min_score=0.85,
    )
    with pytest.raises(ValueError, match="interval"):
        SkillDiscoverySupervisor(
            runtime=runtime,
            interval_seconds=1.0,
            lock_path=tmp_path / "runtime" / "state" / "skill_discovery.lock",
        )
    supervisor = SkillDiscoverySupervisor(
        runtime=runtime,
        interval_seconds=300.0,
        lock_path=tmp_path / "runtime" / "state" / "skill_discovery.lock",
    )
    with pytest.raises(ValueError, match="max_cycles"):
        supervisor.run(max_cycles=0)

    with pytest.raises(ValueError, match="lock path"):
        SkillDiscoverySupervisor(
            runtime=runtime,
            interval_seconds=300.0,
            lock_path=Path("relative.lock"),
        )


def test_supervisor_runs_multiple_bounded_cycles_and_sleeps(tmp_path: Path) -> None:
    engine = ContinuousSkillDiscoveryEngine(
        scout=StaticCandidateScout((candidate(),)),
        fetcher=StaticDocumentationFetcher({candidate().repository: documents()}),
        staging_directory=tmp_path / "runtime" / "skill_staging",
        state_path=tmp_path / "state" / "skill_discovery.json",
        ledger_path=tmp_path / "logs" / "skill_discovery_events.jsonl",
    )
    sleeps: list[float] = []
    supervisor = SkillDiscoverySupervisor(
        runtime=SkillDiscoveryRuntime(
            engine=engine,
            queries=("agent workflow",),
            max_candidates=1,
            min_score=0.85,
        ),
        interval_seconds=300.0,
        lock_path=tmp_path / "state" / "skill_discovery.lock",
        sleeper=sleeps.append,
    )

    completed = supervisor.run(max_cycles=2)

    assert completed == 2
    assert sleeps == [300.0]
    assert not (tmp_path / "state" / "skill_discovery.lock").exists()


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")
