"""Contracts for quarantine-first continuous Agent Skill discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

_SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SHA_OR_REVISION = re.compile(r"^[0-9A-Za-z._/-]{1,128}$")
LIBRARY_ADMISSION_APPROVAL_MARKER = ".çzüö"


class DiscoveryDecision(StrEnum):
    KEEP = "KEEP"
    REJECT = "REJECT"


class ScoreDecision(StrEnum):
    PASS = "SCORE_ACCEPTED"  # noqa: S105  # nosec B105
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    """One external repository candidate treated only as hostile input data."""

    repository: str
    source_url: str
    description: str
    stars: int
    language: str
    archived: bool
    pushed_at: datetime
    discovered_at: datetime
    default_branch: str = "main"
    pinned_revision: str | None = None
    topics: tuple[str, ...] = ()
    source_kind: str = "GITHUB_REPOSITORY"
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            repository=self.repository,
            source_url=self.source_url,
            language=self.language,
            default_branch=self.default_branch,
            source_kind=self.source_kind,
        )
        _require_https(self.source_url, "candidate source")
        _require_aware(self.pushed_at)
        _require_aware(self.discovered_at)
        if "/" not in self.repository or self.repository.count("/") != 1:
            raise ValueError("candidate repository must be owner/name")
        if self.stars < 0:
            raise ValueError("candidate stars cannot be negative")
        if self.pinned_revision is not None and not _SHA_OR_REVISION.fullmatch(
            self.pinned_revision
        ):
            raise ValueError("candidate pinned revision is invalid")
        _require_unique_text(self.topics, "candidate topics")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class DeterministicFilterDecision:
    candidate: DiscoveryCandidate
    decision: DiscoveryDecision
    reasons: tuple[str, ...]
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.reasons:
            raise ValueError("filter decision requires at least one reason")
        _require_unique_text(self.reasons, "filter reasons")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class DocumentationReadPlan:
    candidate: DiscoveryCandidate
    paths: tuple[str, ...]
    max_bytes_per_file: int = 128_000
    source_code_loaded: bool = False
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not 1 <= self.max_bytes_per_file <= 512_000:
            raise ValueError("read plan byte limit is invalid")
        _require_unique_text(self.paths, "read plan paths")
        for path in self.paths:
            if path.startswith(("/", "\\")) or ".." in Path(path).parts:
                raise ValueError("read plan paths must be relative and bounded")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class SourceDocument:
    path: str
    text: str
    truncated: bool = False

    def __post_init__(self) -> None:
        _require_text(path=self.path)
        if len(self.text.encode("utf-8")) > 512_000:
            raise ValueError("source document is too large")


@dataclass(frozen=True, slots=True)
class ExtractedWorkflow:
    skill_name: str
    goal: str
    inputs: tuple[str, ...]
    steps: tuple[str, ...]
    outputs: tuple[str, ...]
    failure_modes: tuple[str, ...]
    source_paths: tuple[str, ...]
    source_code_loaded: bool = False
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _SKILL_NAME.fullmatch(self.skill_name):
            raise ValueError("workflow skill name is invalid")
        _require_text(goal=self.goal)
        for label, values in (
            ("workflow inputs", self.inputs),
            ("workflow steps", self.steps),
            ("workflow outputs", self.outputs),
            ("workflow failure modes", self.failure_modes),
            ("workflow source paths", self.source_paths),
        ):
            _require_unique_text(values, label)
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class SkillGovernanceScore:
    workflow: ExtractedWorkflow
    checks: tuple[tuple[str, bool], ...]
    confidence: float
    decision: ScoreDecision
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.checks or len({name for name, _ in self.checks}) != len(
            self.checks
        ):
            raise ValueError("score checks must be non-empty and unique")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("score confidence must be between zero and one")
        _require_unique_text(self.blockers, "score blockers")
        if self.decision is ScoreDecision.PASS and self.blockers:
            raise ValueError("passing score cannot contain blockers")
        if self.decision is ScoreDecision.REJECT and not self.blockers:
            raise ValueError("rejected score requires blockers")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class QuarantinedSkillDraft:
    skill_name: str
    draft_directory: str
    files: tuple[str, ...]
    review_rule: str = "HUMAN_REVIEW_REQUIRED"
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _SKILL_NAME.fullmatch(self.skill_name):
            raise ValueError("draft skill name is invalid")
        _require_text(
            draft_directory=self.draft_directory,
            review_rule=self.review_rule,
        )
        _require_unique_text(self.files, "draft files")
        if self.review_rule != "HUMAN_REVIEW_REQUIRED":
            raise ValueError("quarantined drafts require human review")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class SkillLibraryAdmissionRecord:
    skill_name: str
    record_directory: str
    status: str
    reasons: tuple[str, ...]
    remediation_queries: tuple[str, ...]
    approval_marker: str = LIBRARY_ADMISSION_APPROVAL_MARKER
    approval_marker_present: bool = False
    files: tuple[str, ...] = ()
    review_rule: str = "HUMAN_REVIEW_REQUIRED"
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _SKILL_NAME.fullmatch(self.skill_name):
            raise ValueError("admission skill name is invalid")
        _require_text(
            record_directory=self.record_directory,
            status=self.status,
            approval_marker=self.approval_marker,
            review_rule=self.review_rule,
        )
        _require_unique_text(self.reasons, "admission reasons")
        _require_unique_text(self.remediation_queries, "admission remediation queries")
        _require_unique_text(self.files, "admission files")
        if self.approval_marker != LIBRARY_ADMISSION_APPROVAL_MARKER:
            raise ValueError("library admission marker is invalid")
        if self.review_rule != "HUMAN_REVIEW_REQUIRED":
            raise ValueError("library admission requires human review")
        if self.status == "READY_FOR_LIBRARY_PR" and not self.approval_marker_present:
            raise ValueError("ready library admission requires approval marker")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


@dataclass(frozen=True, slots=True)
class ContinuousLearningCycleReport:
    cycle_id: str
    created_at: datetime
    candidates_seen: int
    candidates_kept: int
    drafts_created: int
    filter_decisions: tuple[DeterministicFilterDecision, ...]
    scores: tuple[SkillGovernanceScore, ...]
    drafts: tuple[QuarantinedSkillDraft, ...]
    admission_records: tuple[SkillLibraryAdmissionRecord, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    installation_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(cycle_id=self.cycle_id)
        _require_aware(self.created_at)
        if (
            self.candidates_seen < 0
            or self.candidates_kept < 0
            or self.drafts_created < 0
        ):
            raise ValueError("cycle counts cannot be negative")
        if self.candidates_kept > self.candidates_seen:
            raise ValueError("kept candidates cannot exceed seen candidates")
        if self.drafts_created != len(self.drafts):
            raise ValueError("draft count must match drafts")
        _require_unique_text(self.blockers, "cycle blockers")
        _require_no_authority(
            execution_allowed=self.execution_allowed,
            installation_allowed=self.installation_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
        )


def _require_text(**values: str) -> None:
    if any(not value.strip() or len(value) > 2_000 for value in values.values()):
        raise ValueError("continuous discovery text fields are invalid")


def _require_unique_text(values: tuple[str, ...], label: str) -> None:
    if len(set(values)) != len(values) or any(not value.strip() for value in values):
        raise ValueError(f"{label} must contain unique non-empty values")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("continuous discovery timestamps must be timezone-aware")


def _require_https(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username:
        raise ValueError(f"{label} must be credential-free HTTPS")


def _require_no_authority(
    *,
    execution_allowed: bool,
    installation_allowed: bool,
    promotion_status: str,
    live_eligibility_status: str,
) -> None:
    if execution_allowed or installation_allowed:
        raise ValueError("continuous discovery cannot grant execution authority")
    if promotion_status != "RESEARCH_ONLY":
        raise ValueError("continuous discovery cannot promote beyond research")
    if live_eligibility_status != "LIVE_ORDER_BLOCKED":
        raise ValueError("continuous discovery must remain live blocked")
