"""Deterministic continuous Agent Skill discovery pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from urllib.request import Request, urlopen
from uuid import uuid4

from ai4binance.governance.workflow import (
    AgentWorkspaceComponentEvidence,
    AgentWorkspaceComponentReview,
    AgentWorkspaceComponentType,
    review_agent_workspace_component,
)
from ai4binance.reporting import to_primitive
from ai4binance.skills.continuous_discovery import (
    LIBRARY_ADMISSION_APPROVAL_MARKER,
    ContinuousDiscoveryStageId,
    ContinuousDiscoveryStageReview,
    ContinuousDiscoveryStageReviewerResult,
    ContinuousLearningCycleReport,
    DeterministicFilterDecision,
    DiscoveryCandidate,
    DiscoveryDecision,
    DocumentationReadPlan,
    ExtractedWorkflow,
    QuarantinedSkillDraft,
    ScoreDecision,
    SkillGovernanceScore,
    SkillLibraryAdmissionRecord,
    SourceDocument,
)
from ai4binance.skills.github_discovery import CandidateScout
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified

_SKILL_NAME_CHARS = re.compile(r"[^a-z0-9-]+")
_AUTHORITY_TERMS = (
    "allow_auto_live_orders=true",
    "authorize live",
    "bypass gate",
    "bypass risk",
    "execute order",
    "place order",
    "submit order",
    "private key",
    "api key",
    "secret",
    ".env",
)
_WORKFLOW_TERMS = (
    "workflow",
    "agent",
    "skill",
    "review",
    "rubric",
    "test",
    "validation",
    "pipeline",
)
_STEP_TERMS = (
    "discover",
    "filter",
    "read",
    "extract",
    "score",
    "generate",
    "review",
    "publish",
    "validate",
)
_DEFAULT_READ_PATHS = (
    "README.md",
    "README",
    "docs/registries/registry_documentation_index.md",
    "docs/workflows.md",
    "examples/README.md",
    "examples/example.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
)
_BASELINE_STAGE_BLOCKERS = frozenset(
    {
        "STAGE_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    }
)


class DocumentationFetcher(Protocol):
    def fetch(self, plan: DocumentationReadPlan) -> tuple[SourceDocument, ...]: ...


@dataclass(frozen=True, slots=True)
class GitHubDocumentationFetcher:
    """Fetch bounded public text files from raw.githubusercontent.com."""

    timeout_seconds: float = 10.0
    max_total_bytes: int = 512_000
    user_agent: str = "ai4binance-skill-discovery"

    def __post_init__(self) -> None:
        if not 0.1 <= self.timeout_seconds <= 30.0:
            raise ValueError("documentation timeout is invalid")
        if not 10_000 <= self.max_total_bytes <= 2_000_000:
            raise ValueError("documentation total byte limit is invalid")

    def fetch(self, plan: DocumentationReadPlan) -> tuple[SourceDocument, ...]:
        repository = plan.candidate.repository
        revision = plan.candidate.pinned_revision or plan.candidate.default_branch
        documents: list[SourceDocument] = []
        remaining = self.max_total_bytes
        for relative_path in plan.paths:
            if remaining <= 0:
                break
            url = (
                "https://raw.githubusercontent.com/"
                f"{repository}/{revision}/{relative_path}"
            )
            request = Request(url, headers={"User-Agent": self.user_agent})  # noqa: S310
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310  # nosec B310
                    limit = min(plan.max_bytes_per_file, remaining)
                    payload = response.read(limit + 1)
            except OSError:
                continue
            truncated = len(payload) > min(plan.max_bytes_per_file, remaining)
            if truncated:
                payload = payload[: min(plan.max_bytes_per_file, remaining)]
            text = payload.decode("utf-8", errors="replace")
            remaining -= len(payload)
            documents.append(
                SourceDocument(
                    path=relative_path,
                    text=text,
                    truncated=truncated,
                )
            )
        return tuple(documents)


@dataclass(frozen=True, slots=True)
class StaticDocumentationFetcher:
    """Test and source-file helper that never touches the network."""

    documents_by_repository: Mapping[str, tuple[SourceDocument, ...]]

    def fetch(self, plan: DocumentationReadPlan) -> tuple[SourceDocument, ...]:
        return self.documents_by_repository.get(plan.candidate.repository, ())


def review_discovery_stage(
    *,
    cycle_id: str,
    stage_id: ContinuousDiscoveryStageId,
    subject_id: str,
    input_payload: object,
    output_payload: object,
    citations: tuple[str, ...],
    blockers: tuple[str, ...] = (),
) -> ContinuousDiscoveryStageReview:
    normalized_citations = tuple(dict.fromkeys(citations))
    stage_blockers = list(blockers)
    if not normalized_citations:
        normalized_citations = ("artifact://stage-citation-missing",)
        stage_blockers.append("STAGE_CITATION_REQUIRED")
    stage_blockers.extend(_BASELINE_STAGE_BLOCKERS)
    unique_blockers = tuple(dict.fromkeys(stage_blockers))
    reviewer_result = (
        ContinuousDiscoveryStageReviewerResult.WATCHLIST
        if any(blocker not in _BASELINE_STAGE_BLOCKERS for blocker in unique_blockers)
        else ContinuousDiscoveryStageReviewerResult.PASSED
    )
    return ContinuousDiscoveryStageReview(
        cycle_id=cycle_id,
        stage_id=stage_id,
        subject_id=subject_id,
        input_sha256=_payload_sha256(input_payload),
        output_sha256=_payload_sha256(output_payload),
        citations=normalized_citations,
        reviewer_result=reviewer_result,
        blockers=unique_blockers,
    )


def _payload_sha256(value: object) -> str:
    payload = json.dumps(
        to_primitive(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _append_stage_review(
    stage_reviews: list[ContinuousDiscoveryStageReview],
    blockers: list[str],
    review: ContinuousDiscoveryStageReview,
) -> None:
    stage_reviews.append(review)
    blockers.extend(
        blocker
        for blocker in review.blockers
        if blocker not in _BASELINE_STAGE_BLOCKERS
    )


def _candidate_citations(candidates: Sequence[DiscoveryCandidate]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(candidate.source_url for candidate in candidates))


def _document_citations(
    candidate: DiscoveryCandidate,
    documents: Sequence[SourceDocument],
) -> tuple[str, ...]:
    revision = candidate.pinned_revision or candidate.default_branch
    citations = tuple(
        f"https://github.com/{candidate.repository}/blob/{revision}/{document.path}"
        for document in documents
    )
    return citations or (candidate.source_url,)


@dataclass(frozen=True, slots=True)
class ContinuousSkillDiscoveryEngine:
    scout: CandidateScout
    fetcher: DocumentationFetcher
    staging_directory: Path
    state_path: Path
    ledger_path: Path
    min_stars: int = 100
    allowed_languages: tuple[str, ...] = ("Python", "Markdown", "TypeScript")
    pushed_after: datetime = field(
        default_factory=lambda: datetime(2026, 6, 1, tzinfo=UTC)
    )

    def __post_init__(self) -> None:
        if self.min_stars < 0:
            raise ValueError("minimum stars cannot be negative")
        if not self.allowed_languages:
            raise ValueError("allowed languages cannot be empty")
        for path in (self.staging_directory, self.state_path, self.ledger_path):
            if not path.is_absolute():
                raise ValueError("continuous discovery paths must be absolute")
        if self.pushed_after.tzinfo is None or self.pushed_after.utcoffset() is None:
            raise ValueError("pushed_after must be timezone-aware")

    def run_once(
        self,
        *,
        queries: Sequence[str],
        max_candidates: int,
        min_score: float,
        now: datetime | None = None,
    ) -> ContinuousLearningCycleReport:
        observed_at = now or datetime.now(UTC)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("cycle timestamp must be timezone-aware")
        if not 1 <= max_candidates <= 100:
            raise ValueError("max_candidates must be between 1 and 100")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between zero and one")
        query_tuple = tuple(queries)
        cycle_id = f"skill-discovery-{int(observed_at.timestamp() * 1000)}"
        ledger = JsonlAuditStore(self.ledger_path)
        ledger.append_verified(
            AuditEvent(
                event_type="SKILL_DISCOVERY_CYCLE_STARTED",
                timestamp=observed_at,
                snapshot_id=cycle_id,
                payload={
                    "max_candidates": max_candidates,
                    "query_count": len(query_tuple),
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            )
        )
        try:
            candidates = self.scout.discover(
                queries=query_tuple,
                max_candidates=max_candidates,
                now=observed_at,
            )
        except (OSError, RuntimeError, ValueError) as error:
            report = self._failure_report(cycle_id, observed_at, error)
            self._write_state(report)
            return report

        filter_decisions: list[DeterministicFilterDecision] = []
        scores: list[SkillGovernanceScore] = []
        drafts: list[QuarantinedSkillDraft] = []
        workspace_component_reviews: list[AgentWorkspaceComponentReview] = []
        admission_records: list[SkillLibraryAdmissionRecord] = []
        stage_reviews: list[ContinuousDiscoveryStageReview] = []
        blockers: list[str] = []
        _append_stage_review(
            stage_reviews,
            blockers,
            review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.SCOUT,
                subject_id=cycle_id,
                input_payload={
                    "queries": query_tuple,
                    "max_candidates": max_candidates,
                },
                output_payload=candidates,
                citations=_candidate_citations(candidates)
                or (f"artifact://{cycle_id}/scout-output",),
            ),
        )
        for candidate in candidates:
            decision = filter_candidate(
                candidate,
                min_stars=self.min_stars,
                allowed_languages=self.allowed_languages,
                pushed_after=self.pushed_after,
            )
            filter_decisions.append(decision)
            filter_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.FILTER,
                subject_id=candidate.repository,
                input_payload=candidate,
                output_payload=decision,
                citations=(candidate.source_url,),
                blockers=(
                    decision.reasons
                    if decision.decision is DiscoveryDecision.REJECT
                    else ()
                ),
            )
            _append_stage_review(stage_reviews, blockers, filter_review)
            ledger.append_verified(
                AuditEvent(
                    event_type="SKILL_DISCOVERY_CANDIDATE_FILTERED",
                    timestamp=observed_at,
                    snapshot_id=f"{cycle_id}:{candidate.repository}",
                    payload={
                        "decision": decision,
                        "stage_review": filter_review,
                    },
                )
            )
            if decision.decision is DiscoveryDecision.REJECT:
                admission_record = write_library_admission_record(
                    candidate=candidate,
                    reasons=decision.reasons,
                    output_root=self.staging_directory,
                    created_at=observed_at,
                )
                admission_records.append(admission_record)
                ledger.append_verified(
                    AuditEvent(
                        event_type="SKILL_DISCOVERY_LIBRARY_NOT_ADMITTED",
                        timestamp=observed_at,
                        snapshot_id=f"{cycle_id}:{admission_record.skill_name}",
                        payload={"admission_record": admission_record},
                    )
                )
                continue
            plan = build_read_plan(candidate)
            documents = self.fetcher.fetch(plan)
            reader_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.READER,
                subject_id=candidate.repository,
                input_payload=plan,
                output_payload=documents,
                citations=_document_citations(candidate, documents),
            )
            _append_stage_review(stage_reviews, blockers, reader_review)
            workflow = extract_workflow(candidate, documents, plan)
            extractor_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.EXTRACTOR,
                subject_id=candidate.repository,
                input_payload=documents,
                output_payload=workflow,
                citations=_document_citations(candidate, documents),
            )
            _append_stage_review(stage_reviews, blockers, extractor_review)
            score = score_workflow(
                workflow,
                documents=documents,
                min_score=min_score,
            )
            scores.append(score)
            score_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.SCORE,
                subject_id=candidate.repository,
                input_payload={
                    "workflow": workflow,
                    "min_score": min_score,
                },
                output_payload=score,
                citations=_document_citations(candidate, documents),
                blockers=score.blockers,
            )
            _append_stage_review(stage_reviews, blockers, score_review)
            if score.decision is ScoreDecision.REJECT:
                admission_record = write_library_admission_record(
                    candidate=candidate,
                    reasons=score.blockers,
                    output_root=self.staging_directory,
                    created_at=observed_at,
                )
                admission_records.append(admission_record)
                ledger.append_verified(
                    AuditEvent(
                        event_type="SKILL_DISCOVERY_LIBRARY_NOT_ADMITTED",
                        timestamp=observed_at,
                        snapshot_id=f"{cycle_id}:{admission_record.skill_name}",
                        payload={"admission_record": admission_record},
                    )
                )
                continue
            draft = write_quarantined_skill_draft(
                candidate=candidate,
                score=score,
                output_root=self.staging_directory,
                created_at=observed_at,
            )
            generator_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.GENERATOR,
                subject_id=candidate.repository,
                input_payload=score,
                output_payload=draft,
                citations=(
                    candidate.source_url,
                    f"artifact://{_logical_draft_skill_path(draft)}",
                ),
            )
            _append_stage_review(stage_reviews, blockers, generator_review)
            workspace_review = review_workspace_component_from_draft(
                candidate=candidate,
                score=score,
                draft=draft,
            )
            blockers.extend(
                blocker
                for blocker in workspace_review.blockers
                if blocker
                not in {
                    "HUMAN_REVIEW_REQUIRED",
                    "LIVE_ORDER_BLOCKED",
                }
            )
            reviewer_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.REVIEWER,
                subject_id=candidate.repository,
                input_payload=draft,
                output_payload=workspace_review,
                citations=workspace_review.citations,
                blockers=tuple(
                    blocker
                    for blocker in workspace_review.blockers
                    if blocker
                    not in {
                        "HUMAN_REVIEW_REQUIRED",
                        "LIVE_ORDER_BLOCKED",
                    }
                ),
            )
            _append_stage_review(stage_reviews, blockers, reviewer_review)
            draft = attach_workspace_component_review(
                draft=draft,
                review=workspace_review,
            )
            drafts.append(draft)
            workspace_component_reviews.append(workspace_review)
            admission_record = write_library_admission_record(
                candidate=candidate,
                reasons=("HUMAN_REVIEW_REQUIRED", "PR_REQUIRED"),
                output_root=self.staging_directory,
                created_at=observed_at,
            )
            admission_records.append(admission_record)
            publisher_review = review_discovery_stage(
                cycle_id=cycle_id,
                stage_id=ContinuousDiscoveryStageId.PUBLISHER,
                subject_id=candidate.repository,
                input_payload={
                    "draft": draft,
                    "workspace_review": workspace_review,
                },
                output_payload=admission_record,
                citations=(
                    candidate.source_url,
                    f"artifact://{admission_record.record_directory}",
                ),
            )
            _append_stage_review(stage_reviews, blockers, publisher_review)
            ledger.append_verified(
                AuditEvent(
                    event_type="SKILL_DISCOVERY_DRAFT_QUARANTINED",
                    timestamp=observed_at,
                    snapshot_id=f"{cycle_id}:{draft.skill_name}",
                    payload={
                        "draft": draft,
                        "workspace_component_review": workspace_review,
                        "stage_reviews": (
                            generator_review,
                            reviewer_review,
                            publisher_review,
                        ),
                    },
                )
            )
        report = ContinuousLearningCycleReport(
            cycle_id=cycle_id,
            created_at=observed_at,
            candidates_seen=len(candidates),
            candidates_kept=sum(
                1
                for decision in filter_decisions
                if decision.decision is DiscoveryDecision.KEEP
            ),
            drafts_created=len(drafts),
            filter_decisions=tuple(filter_decisions),
            scores=tuple(scores),
            drafts=tuple(drafts),
            admission_records=tuple(admission_records),
            blockers=tuple(dict.fromkeys(blockers)),
            workspace_component_reviews=tuple(workspace_component_reviews),
            stage_reviews=tuple(stage_reviews),
        )
        self._write_state(report)
        return report

    def _failure_report(
        self,
        cycle_id: str,
        observed_at: datetime,
        error: Exception,
    ) -> ContinuousLearningCycleReport:
        JsonlAuditStore(self.ledger_path).append_verified(
            AuditEvent(
                event_type="SKILL_DISCOVERY_CYCLE_FAILED",
                timestamp=observed_at,
                snapshot_id=cycle_id,
                payload={
                    "error_category": type(error).__name__[:100],
                    "blockers": ("GITHUB_DISCOVERY_UNAVAILABLE",),
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            )
        )
        return ContinuousLearningCycleReport(
            cycle_id=cycle_id,
            created_at=observed_at,
            candidates_seen=0,
            candidates_kept=0,
            drafts_created=0,
            filter_decisions=(),
            scores=(),
            drafts=(),
            admission_records=(),
            blockers=("GITHUB_DISCOVERY_UNAVAILABLE",),
        )

    def _write_state(self, report: ContinuousLearningCycleReport) -> None:
        payload = cast(dict[str, object], to_primitive(report))
        write_json_object_verified(
            self.state_path,
            payload,
            blocker="SKILL_DISCOVERY_STATE_DESTINATION_VERIFY_FAILED",
            subject_id=report.cycle_id,
            indent=2,
        )


def filter_candidate(
    candidate: DiscoveryCandidate,
    *,
    min_stars: int,
    allowed_languages: tuple[str, ...],
    pushed_after: datetime,
) -> DeterministicFilterDecision:
    reasons: list[str] = []
    if candidate.archived:
        reasons.append("ARCHIVED_REPOSITORY")
    if candidate.stars < min_stars:
        reasons.append("STAR_THRESHOLD_NOT_MET")
    if candidate.language.casefold() not in {
        language.casefold() for language in allowed_languages
    }:
        reasons.append("LANGUAGE_NOT_ALLOWED")
    if candidate.pushed_at < pushed_after:
        reasons.append("STALE_REPOSITORY")
    combined = (
        f"{candidate.repository} {candidate.description} {' '.join(candidate.topics)}"
    ).casefold()
    if not any(term in combined for term in _WORKFLOW_TERMS):
        reasons.append("AI_WORKFLOW_SCOPE_NOT_EVIDENT")
    if _contains_authority_drift(combined):
        reasons.append("AUTHORITY_DRIFT_REVIEW_REQUIRED")
    if candidate.pinned_revision is None:
        reasons.append("PINNED_REVISION_REQUIRED")
    if reasons:
        return DeterministicFilterDecision(
            candidate=candidate,
            decision=DiscoveryDecision.REJECT,
            reasons=tuple(dict.fromkeys(reasons)),
        )
    return DeterministicFilterDecision(
        candidate=candidate,
        decision=DiscoveryDecision.KEEP,
        reasons=("DETERMINISTIC_FILTERS_PASSED",),
    )


def build_read_plan(candidate: DiscoveryCandidate) -> DocumentationReadPlan:
    return DocumentationReadPlan(
        candidate=candidate,
        paths=_DEFAULT_READ_PATHS,
    )


def extract_workflow(
    candidate: DiscoveryCandidate,
    documents: tuple[SourceDocument, ...],
    plan: DocumentationReadPlan,
) -> ExtractedWorkflow:
    del plan
    combined = "\n".join(document.text for document in documents)
    lowered = combined.casefold()
    discovered_steps = tuple(
        f"{term}_stage"
        for term in _STEP_TERMS
        if term in lowered or term in candidate.description.casefold()
    )
    steps = discovered_steps[:8] or ("read_documentation", "extract_workflow")
    if len(steps) < 3 and any(document.text.strip() for document in documents):
        steps = (*steps, "human_review")
    failure_modes = ["MISSING_PROJECT_CONTEXT", "HUMAN_REVIEW_REQUIRED"]
    if not documents:
        failure_modes.append("DOCUMENTATION_UNAVAILABLE")
    if _contains_authority_drift(lowered):
        failure_modes.append("AUTHORITY_DRIFT_REVIEW_REQUIRED")
    return ExtractedWorkflow(
        skill_name=_skill_name(candidate.repository),
        goal=_bounded_goal(candidate),
        inputs=("repository_context", "workflow_documentation"),
        steps=tuple(dict.fromkeys(steps)),
        outputs=("quarantined_skill_draft", "review_notes"),
        failure_modes=tuple(dict.fromkeys(failure_modes)),
        source_paths=tuple(document.path for document in documents)
        or ("DOCUMENTATION_UNAVAILABLE",),
        source_code_loaded=False,
    )


def score_workflow(
    workflow: ExtractedWorkflow,
    *,
    documents: tuple[SourceDocument, ...],
    min_score: float,
) -> SkillGovernanceScore:
    lowered_paths = tuple(document.path.casefold() for document in documents)
    lowered_text = "\n".join(document.text.casefold() for document in documents)
    checks = (
        ("README exists", any(path.startswith("readme") for path in lowered_paths)),
        (
            "Examples exist",
            any("example" in path for path in lowered_paths)
            or "example" in lowered_text,
        ),
        (">= 3 workflow steps", len(workflow.steps) >= 3),
        ("Reusable", any(term in lowered_text for term in _WORKFLOW_TERMS)),
        ("General purpose", not _contains_authority_drift(lowered_text)),
    )
    confidence = sum(1 for _, passed in checks if passed) / len(checks)
    blockers = tuple(
        f"CHECK_FAILED:{name.upper().replace(' ', '_')}"
        for name, passed in checks
        if not passed
    )
    if confidence < min_score:
        blockers = (*blockers, "CONFIDENCE_THRESHOLD_NOT_MET")
    blockers = tuple(dict.fromkeys(blockers))
    return SkillGovernanceScore(
        workflow=workflow,
        checks=checks,
        confidence=confidence,
        decision=ScoreDecision.PASS if not blockers else ScoreDecision.REJECT,
        blockers=blockers,
    )


def write_quarantined_skill_draft(
    *,
    candidate: DiscoveryCandidate,
    score: SkillGovernanceScore,
    output_root: Path,
    created_at: datetime,
) -> QuarantinedSkillDraft:
    skill_name = score.workflow.skill_name
    draft_directory = output_root / skill_name
    draft_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "SKILL.md": _skill_markdown(candidate, score, created_at),
        "examples.md": _examples_markdown(score),
        "commands.md": _commands_markdown(),
        "review.md": _review_markdown(candidate, score),
    }
    written: list[str] = []
    for name, content in files.items():
        _write_text_verified(draft_directory / name, content)
        written.append(name)
    metadata = {
        "schema_version": "1.0",
        "source_repository": candidate.repository,
        "source_url": candidate.source_url,
        "pinned_revision": candidate.pinned_revision,
        "confidence": score.confidence,
        "decision": score.decision.value,
        "library_admission_status": "NOT_ADMITTED",
        "library_admission_reasons": ["HUMAN_REVIEW_REQUIRED", "PR_REQUIRED"],
        "library_admission_approval_marker": LIBRARY_ADMISSION_APPROVAL_MARKER,
        "review_rule": "HUMAN_REVIEW_REQUIRED",
        "execution_allowed": False,
        "installation_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    write_json_object_verified(
        draft_directory / "metadata.json",
        metadata,
        blocker="QUARANTINED_SKILL_METADATA_VERIFY_FAILED",
        subject_id=skill_name,
        indent=2,
    )
    written.append("metadata.json")
    return QuarantinedSkillDraft(
        skill_name=skill_name,
        draft_directory=str(draft_directory),
        files=tuple(written),
    )


def workspace_component_evidence_from_draft(
    *,
    candidate: DiscoveryCandidate,
    score: SkillGovernanceScore,
    draft: QuarantinedSkillDraft,
) -> AgentWorkspaceComponentEvidence:
    skill_path = Path(draft.draft_directory) / "SKILL.md"
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except OSError:
        skill_text = (
            f"{candidate.repository}\n{candidate.source_url}\n"
            f"{candidate.pinned_revision}\n{draft.skill_name}"
        )
    combined = "\n".join(
        (
            candidate.description,
            score.workflow.goal,
            " ".join(score.workflow.steps),
            " ".join(score.workflow.failure_modes),
            " ".join(candidate.topics),
        )
    )
    source_path = _logical_draft_skill_path(draft)
    return AgentWorkspaceComponentEvidence(
        component_id=draft.skill_name,
        component_type=AgentWorkspaceComponentType.SKILL,
        source_path=source_path,
        content_sha256=text_sha256(skill_text),
        citations=(
            candidate.source_url,
            f"artifact://{source_path}",
        ),
        declared_authority="RESEARCH_ONLY",
        canary_command=(
            ".\\.venv\\scripts\\python.exe -m pytest "
            "tests\\test_continuous_skill_discovery.py --no-cov -q"
        ),
        canary_expected_blockers=(
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
        credential_required=_contains_authority_drift(combined),
        trading_scope_touched=_touches_trading_scope(combined),
    )


def review_workspace_component_from_draft(
    *,
    candidate: DiscoveryCandidate,
    score: SkillGovernanceScore,
    draft: QuarantinedSkillDraft,
) -> AgentWorkspaceComponentReview:
    return review_agent_workspace_component(
        workspace_component_evidence_from_draft(
            candidate=candidate,
            score=score,
            draft=draft,
        )
    )


def attach_workspace_component_review(
    *,
    draft: QuarantinedSkillDraft,
    review: AgentWorkspaceComponentReview,
) -> QuarantinedSkillDraft:
    review_path = Path(draft.draft_directory) / "workspace-review.json"
    payload = cast(dict[str, object], to_primitive(review))
    write_json_object_verified(
        review_path,
        payload,
        blocker="QUARANTINED_SKILL_WORKSPACE_REVIEW_VERIFY_FAILED",
        subject_id=review.component_id,
        indent=2,
    )
    return replace(draft, files=(*draft.files, "workspace-review.json"))


def write_library_admission_record(
    *,
    candidate: DiscoveryCandidate,
    reasons: tuple[str, ...],
    output_root: Path,
    created_at: datetime,
) -> SkillLibraryAdmissionRecord:
    skill_name = _skill_name(candidate.repository)
    record_directory = output_root / "_admit" / skill_name
    record_directory.mkdir(parents=True, exist_ok=True)
    approval_marker_path = record_directory / LIBRARY_ADMISSION_APPROVAL_MARKER
    marker_present = approval_marker_path.exists()
    status = "READY_FOR_LIBRARY_PR" if marker_present else "NOT_ADMITTED"
    normalized_reasons = tuple(dict.fromkeys(reasons)) or ("HUMAN_REVIEW_REQUIRED",)
    remediation_queries = github_remediation_queries(candidate, normalized_reasons)
    payload = {
        "schema_version": "1.0",
        "skill_name": skill_name,
        "source_repository": candidate.repository,
        "source_url": candidate.source_url,
        "created_at": created_at.isoformat(),
        "status": status,
        "not_admitted_reasons": list(normalized_reasons),
        "github_remediation_queries": list(remediation_queries),
        "approval_marker": LIBRARY_ADMISSION_APPROVAL_MARKER,
        "approval_marker_path": str(approval_marker_path),
        "approval_marker_present": marker_present,
        "review_rule": "HUMAN_REVIEW_REQUIRED",
        "execution_allowed": False,
        "installation_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    write_json_object_verified(
        record_directory / "admission.json",
        payload,
        blocker="SKILL_LIBRARY_ADMISSION_RECORD_VERIFY_FAILED",
        subject_id=skill_name,
        indent=2,
    )
    _write_text_verified(
        record_directory / "not-admitted.md",
        _not_admitted_markdown(candidate, normalized_reasons, marker_present),
    )
    _write_text_verified(
        record_directory / "github-resolution.md",
        _github_resolution_markdown(candidate, remediation_queries),
    )
    return SkillLibraryAdmissionRecord(
        skill_name=skill_name,
        record_directory=str(record_directory),
        status=status,
        reasons=normalized_reasons,
        remediation_queries=remediation_queries,
        approval_marker_present=marker_present,
        files=("admission.json", "not-admitted.md", "github-resolution.md"),
    )


def _skill_markdown(
    candidate: DiscoveryCandidate,
    score: SkillGovernanceScore,
    created_at: datetime,
) -> str:
    workflow = score.workflow
    steps = "\n".join(f"- {step}" for step in workflow.steps)
    return (
        "---\n"
        f"name: {workflow.skill_name}\n"
        f"description: Use when reviewing {candidate.repository} workflow ideas.\n"
        "metadata:\n"
        "  ai4binance.authority: advisory-only\n"
        '  ai4binance.version: "1"\n'
        "  ai4binance.owner: SkillDiscoveryPipeline\n"
        "  ai4binance.trust_level: quarantined\n"
        f"  ai4binance.last_reviewed: {created_at.date().isoformat()}\n"
        "  ai4binance.trigger_examples: continuous discovery review\n"
        "---\n\n"
        "# Quarantined Skill Draft\n\n"
        "This draft is external-source research data. It is not installed, not "
        "trusted, and not executable.\n\n"
        "## Goal\n\n"
        f"{workflow.goal}\n\n"
        "## Workflow Steps\n\n"
        f"{steps}\n\n"
        "## Safety Boundary\n\n"
        "- HUMAN_REVIEW_REQUIRED\n"
        "- RESEARCH_ONLY\n"
        "- execution_allowed=false\n"
        "- installation_allowed=false\n"
        "- LIVE_ORDER_BLOCKED\n"
    )


def _examples_markdown(score: SkillGovernanceScore) -> str:
    checks = "\n".join(
        f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in score.checks
    )
    return (
        "# Examples\n\n"
        "Use this file only to review the extracted workflow shape.\n\n"
        "## Score Checks\n\n"
        f"{checks}\n"
    )


def _commands_markdown() -> str:
    return (
        "# Commands\n\n"
        "No commands are approved for automatic execution.\n\n"
        "```text\n"
        "HUMAN_REVIEW_REQUIRED\n"
        "RESEARCH_ONLY\n"
        "LIVE_ORDER_BLOCKED\n"
        "```\n"
    )


def _review_markdown(
    candidate: DiscoveryCandidate,
    score: SkillGovernanceScore,
) -> str:
    return (
        "# Human Review\n\n"
        f"- Source: {candidate.source_url}\n"
        f"- Pinned revision: {candidate.pinned_revision}\n"
        f"- Confidence: {score.confidence:.2f}\n"
        "- Review rule: HUMAN_REVIEW_REQUIRED\n"
        "- Required review: license, security, sandbox, provenance, ownership\n"
        "- Publication: PR only after explicit human approval\n"
        f"- Library admission marker: {LIBRARY_ADMISSION_APPROVAL_MARKER}\n"
    )


def _not_admitted_markdown(
    candidate: DiscoveryCandidate,
    reasons: tuple[str, ...],
    marker_present: bool,
) -> str:
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    status = "READY_FOR_LIBRARY_PR" if marker_present else "NOT_ADMITTED"
    return (
        "# Library Admission Record\n\n"
        f"- Source: {candidate.source_url}\n"
        f"- Status: {status}\n"
        f"- Approval marker: {LIBRARY_ADMISSION_APPROVAL_MARKER}\n"
        "- Review rule: HUMAN_REVIEW_REQUIRED\n"
        "- Publication: PR only after explicit human approval\n\n"
        "## Not Admitted Reasons\n\n"
        f"{reason_lines}\n"
    )


def _github_resolution_markdown(
    candidate: DiscoveryCandidate,
    remediation_queries: tuple[str, ...],
) -> str:
    query_lines = "\n".join(f"- {query}" for query in remediation_queries)
    return (
        "# GitHub Resolution Research\n\n"
        "Use these credential-free GitHub searches to find documentation, tests, "
        "license notes, or safer workflow evidence before library admission.\n\n"
        f"- Source repository: {candidate.repository}\n"
        f"- Approval marker required: {LIBRARY_ADMISSION_APPROVAL_MARKER}\n\n"
        "## Queries\n\n"
        f"{query_lines}\n"
    )


def _write_text_verified(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = content if content.endswith("\n") else f"{content}\n"
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(expected, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
        observed = path.read_text(encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)
    if observed != expected:
        raise ValueError("QUARANTINED_SKILL_TEXT_VERIFY_FAILED")


def _skill_name(repository: str) -> str:
    raw = repository.split("/", 1)[1].casefold()
    normalized = _SKILL_NAME_CHARS.sub("-", raw).strip("-")
    if not normalized:
        normalized = "external-workflow"
    if not normalized.endswith("-workflow"):
        normalized = f"{normalized}-workflow"
    return normalized[:64].strip("-") or "external-workflow"


def _bounded_goal(candidate: DiscoveryCandidate) -> str:
    description = candidate.description.strip()
    if not description:
        return f"Review reusable workflow ideas from {candidate.repository}."
    return f"Review reusable workflow ideas from {candidate.repository}: {description}"


def _contains_authority_drift(value: str) -> bool:
    lowered = value.casefold()
    return any(term in lowered for term in _AUTHORITY_TERMS)


def _touches_trading_scope(value: str) -> bool:
    lowered = value.casefold()
    return any(
        term in lowered
        for term in (
            "binance",
            "backtest",
            "execution",
            "futures",
            "live order",
            "market",
            "order",
            "risk",
            "signal",
            "spot",
            "strategy",
            "trade",
            "trading",
        )
    )


def _logical_draft_skill_path(draft: QuarantinedSkillDraft) -> str:
    draft_path = Path(draft.draft_directory)
    parts = draft_path.parts
    if "runtime" in parts and "skill_staging" in parts:
        start = parts.index("runtime")
        return "/".join((*parts[start:], "SKILL.md"))
    if "skill_staging" in parts:
        start = parts.index("skill_staging")
        return "/".join((*parts[start:], "SKILL.md"))
    return f"runtime/skill_staging/continuous-discovery/{draft.skill_name}/SKILL.md"


def github_remediation_queries(
    candidate: DiscoveryCandidate,
    reasons: tuple[str, ...],
) -> tuple[str, ...]:
    base_terms = (
        candidate.repository,
        "agent skill workflow",
        "documentation tests license security",
    )
    queries: list[str] = []
    for reason in reasons:
        normalized_reason = reason.replace("CHECK_FAILED:", "").replace("_", " ")
        queries.append(" ".join((*base_terms, normalized_reason)).strip())
    queries.append(
        " ".join(
            (
                candidate.repository,
                "reusable workflow examples validation rubric",
            )
        )
    )
    return tuple(dict.fromkeys(query[:240] for query in queries if query.strip()))


def source_file_candidates(path: Path, now: datetime) -> tuple[DiscoveryCandidate, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("source file must contain a list of candidates")
    candidates: list[DiscoveryCandidate] = []
    for item in payload:
        if not isinstance(item, Mapping):
            raise ValueError("source file candidate must be an object")
        candidates.append(
            DiscoveryCandidate(
                repository=str(item.get("repository", "")),
                source_url=str(item.get("source_url", "")),
                description=str(item.get("description", "")),
                stars=int(item.get("stars", 0)),
                language=str(item.get("language", "Unknown")),
                archived=bool(item.get("archived", False)),
                pushed_at=_parse_datetime(str(item.get("pushed_at", ""))),
                discovered_at=now,
                default_branch=str(item.get("default_branch", "main")),
                pinned_revision=(
                    str(item["pinned_revision"])
                    if item.get("pinned_revision") is not None
                    else None
                ),
                topics=tuple(
                    str(topic)
                    for topic in cast(Sequence[object], item.get("topics", ()))
                ),
            )
        )
    return tuple(candidates)


def source_file_documents(path: Path) -> dict[str, tuple[SourceDocument, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("source file must contain a list of candidates")
    documents: dict[str, tuple[SourceDocument, ...]] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            raise ValueError("source file candidate must be an object")
        repository = str(item.get("repository", ""))
        raw_documents = item.get("documents", ())
        if not isinstance(raw_documents, list):
            documents[repository] = ()
            continue
        parsed: list[SourceDocument] = []
        for document in raw_documents:
            if not isinstance(document, Mapping):
                raise ValueError("source file document must be an object")
            parsed.append(
                SourceDocument(
                    path=str(document.get("path", "")),
                    text=str(document.get("text", "")),
                    truncated=bool(document.get("truncated", False)),
                )
            )
        documents[repository] = tuple(parsed)
    return documents


@dataclass(frozen=True, slots=True)
class StaticCandidateScout:
    candidates: tuple[DiscoveryCandidate, ...]

    def discover(
        self,
        *,
        queries: Sequence[str],
        max_candidates: int,
        now: datetime,
    ) -> tuple[DiscoveryCandidate, ...]:
        del queries, now
        return self.candidates[:max_candidates]


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
