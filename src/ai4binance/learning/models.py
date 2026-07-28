"""Immutable controlled-learning and experiment recommendation models."""

from dataclasses import dataclass
from datetime import datetime

from ai4binance.domain import ValidationStatus


@dataclass(frozen=True, slots=True)
class LessonCandidate:
    code: str
    evidence_count: int
    rationale: str


@dataclass(frozen=True, slots=True)
class ExperimentRecommendation:
    rank: int
    experiment_id: str
    objective: str
    required_validation: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LearningSummary:
    summary_id: str
    created_at: datetime
    lessons: tuple[LessonCandidate, ...]
    experiments: tuple[ExperimentRecommendation, ...]
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    risk_change_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.summary_id.strip():
            raise ValueError("learning summary identity is required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("learning timestamp must be timezone-aware")
        if self.promotion_status is not ValidationStatus.RESEARCH_ONLY:
            raise ValueError("learning output must remain research only")
        if self.execution_allowed or self.risk_change_allowed:
            raise ValueError("learning cannot execute or change risk")
