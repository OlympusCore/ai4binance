"""Human-governed lesson lifecycle with expiry and contradiction barriers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ai4binance.learning.models import LearningSummary, LessonCandidate


class LessonStatus(StrEnum):
    OBSERVED = "OBSERVED"
    DEDUPLICATED = "DEDUPLICATED"
    CONTRADICTION_CHECKED = "CONTRADICTION_CHECKED"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    ACTIVE_LESSON = "ACTIVE_LESSON"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


_FLOW = (
    LessonStatus.OBSERVED,
    LessonStatus.DEDUPLICATED,
    LessonStatus.CONTRADICTION_CHECKED,
    LessonStatus.VALIDATION_PENDING,
    LessonStatus.RESEARCH_ONLY,
    LessonStatus.HUMAN_APPROVED,
    LessonStatus.ACTIVE_LESSON,
)


@dataclass(frozen=True, slots=True)
class GovernedLesson:
    lesson_id: str
    code: str
    rationale: str
    evidence_count: int
    source_artifact_ids: tuple[str, ...]
    observed_at: datetime
    expires_at: datetime
    status: LessonStatus = LessonStatus.OBSERVED
    validation_artifact_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    risk_change_allowed: bool = False
    parameter_change_allowed: bool = False

    def __post_init__(self) -> None:
        if any(
            not item.strip() or len(item) > 2_000
            for item in (self.lesson_id, self.code, self.rationale)
        ):
            raise ValueError("governed lesson identity fields are invalid")
        if self.evidence_count <= 0:
            raise ValueError("governed lesson requires positive evidence")
        if not self.source_artifact_ids or len(set(self.source_artifact_ids)) != len(
            self.source_artifact_ids
        ):
            raise ValueError("governed lesson sources must be non-empty and unique")
        if any(not item.strip() for item in self.source_artifact_ids):
            raise ValueError("governed lesson sources cannot be blank")
        for timestamp in (self.observed_at, self.expires_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("governed lesson timestamps must be timezone-aware")
        if self.expires_at <= self.observed_at:
            raise ValueError("governed lesson expiry must follow observation")
        if len(set(self.validation_artifact_ids)) != len(self.validation_artifact_ids):
            raise ValueError("lesson validation artifacts must be unique")
        if self.status in {LessonStatus.HUMAN_APPROVED, LessonStatus.ACTIVE_LESSON}:
            if self.blockers or not self.validation_artifact_ids:
                raise ValueError("approved lesson requires clean validation evidence")
        if (
            self.execution_allowed
            or self.risk_change_allowed
            or self.parameter_change_allowed
        ):
            raise ValueError("lesson governance cannot change production authority")

    @classmethod
    def from_candidate(
        cls,
        candidate: LessonCandidate,
        *,
        lesson_id: str,
        source_artifact_id: str,
        observed_at: datetime,
        expires_at: datetime,
    ) -> GovernedLesson:
        return cls(
            lesson_id=lesson_id,
            code=candidate.code,
            rationale=candidate.rationale,
            evidence_count=candidate.evidence_count,
            source_artifact_ids=(source_artifact_id,),
            observed_at=observed_at,
            expires_at=expires_at,
        )

    def transition(
        self,
        status: LessonStatus,
        *,
        at: datetime,
        validation_artifact_ids: tuple[str, ...] = (),
        blockers: tuple[str, ...] = (),
        human_approved: bool = False,
    ) -> GovernedLesson:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("lesson transition timestamp must be timezone-aware")
        if status in {LessonStatus.EXPIRED, LessonStatus.REJECTED}:
            if self.status in {LessonStatus.EXPIRED, LessonStatus.REJECTED}:
                raise ValueError("terminal lesson cannot transition")
            return replace(self, status=status, blockers=blockers)
        if self.status not in _FLOW:
            raise ValueError("terminal lesson cannot transition")
        current = _FLOW.index(self.status)
        if current + 1 >= len(_FLOW) or status is not _FLOW[current + 1]:
            raise ValueError("lesson transition must be contiguous")
        merged = tuple(
            dict.fromkeys((*self.validation_artifact_ids, *validation_artifact_ids))
        )
        if status is LessonStatus.RESEARCH_ONLY and not merged:
            raise ValueError("research-only lesson requires validation artifacts")
        if status is LessonStatus.HUMAN_APPROVED and not human_approved:
            raise ValueError("lesson approval requires explicit human approval")
        if status in {LessonStatus.HUMAN_APPROVED, LessonStatus.ACTIVE_LESSON}:
            if blockers:
                raise ValueError("blocked lesson cannot be approved or activated")
            if at >= self.expires_at:
                raise ValueError("expired lesson cannot be approved or activated")
        return replace(
            self,
            status=status,
            validation_artifact_ids=merged,
            blockers=blockers,
        )


def stage_learning_summary(
    summary: LearningSummary,
    *,
    expires_at: datetime,
) -> tuple[GovernedLesson, ...]:
    """Convert advisory summary lessons into unapproved governed candidates."""
    return tuple(
        GovernedLesson.from_candidate(
            candidate,
            lesson_id=f"{summary.summary_id}:{candidate.code.lower()}",
            source_artifact_id=summary.summary_id,
            observed_at=summary.created_at,
            expires_at=expires_at,
        )
        for candidate in summary.lessons
    )
