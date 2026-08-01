"""Corrective RAG retrieval quality gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class RetrievalCorrectionAction(StrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    AMBIGUOUS = "AMBIGUOUS"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_text(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True, slots=True)
class RetrievedDocumentScore:
    document_id: str
    relevance_score: float

    def __post_init__(self) -> None:
        _require_text("retrieved document id", self.document_id)
        if not isfinite(self.relevance_score) or not 0.0 <= self.relevance_score <= 1.0:
            raise ValueError("retrieval relevance_score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CorrectiveRagDecision:
    query_id: str
    action: RetrievalCorrectionAction
    accepted_document_ids: tuple[str, ...]
    rejected_document_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    web_fallback_allowed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("corrective rag query id", self.query_id)
        _require_unique_text("accepted document ids", self.accepted_document_ids)
        _require_unique_text("rejected document ids", self.rejected_document_ids)
        _require_unique_text("corrective rag blockers", self.blockers)
        if self.action not in RetrievalCorrectionAction:
            raise ValueError("corrective rag action is invalid")
        if self.execution_allowed:
            raise ValueError("corrective rag cannot authorize execution")
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("corrective rag cannot promote production state")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("corrective rag must remain live blocked")


def evaluate_retrieval_quality(
    *,
    query_id: str,
    scored_documents: tuple[RetrievedDocumentScore, ...],
    lower_threshold: float = 0.35,
    upper_threshold: float = 0.70,
    allow_web_fallback: bool = False,
) -> CorrectiveRagDecision:
    _require_text("corrective rag query id", query_id)
    if not 0.0 <= lower_threshold < upper_threshold <= 1.0:
        raise ValueError("retrieval thresholds must satisfy 0 <= lower < upper <= 1")
    if not scored_documents:
        return CorrectiveRagDecision(
            query_id=query_id,
            action=RetrievalCorrectionAction.INCORRECT,
            accepted_document_ids=(),
            rejected_document_ids=(),
            blockers=(
                "RAG_RETRIEVAL_EMPTY",
                "RAG_WEB_FALLBACK_DISABLED",
                "LIVE_ORDER_BLOCKED",
            ),
            web_fallback_allowed=False,
        )
    best = max(score.relevance_score for score in scored_documents)
    accepted = tuple(
        score.document_id
        for score in scored_documents
        if score.relevance_score >= upper_threshold
    )
    rejected = tuple(
        score.document_id
        for score in scored_documents
        if score.relevance_score < lower_threshold
    )
    if best >= upper_threshold:
        return CorrectiveRagDecision(
            query_id=query_id,
            action=RetrievalCorrectionAction.CORRECT,
            accepted_document_ids=accepted,
            rejected_document_ids=rejected,
            blockers=("LIVE_ORDER_BLOCKED",),
            web_fallback_allowed=False,
        )
    if best < lower_threshold:
        blockers = ["RAG_RETRIEVAL_QUALITY_INSUFFICIENT", "LIVE_ORDER_BLOCKED"]
        if not allow_web_fallback:
            blockers.insert(1, "RAG_WEB_FALLBACK_DISABLED")
        return CorrectiveRagDecision(
            query_id=query_id,
            action=RetrievalCorrectionAction.INCORRECT,
            accepted_document_ids=(),
            rejected_document_ids=tuple(
                score.document_id for score in scored_documents
            ),
            blockers=tuple(blockers),
            web_fallback_allowed=allow_web_fallback,
        )
    return CorrectiveRagDecision(
        query_id=query_id,
        action=RetrievalCorrectionAction.AMBIGUOUS,
        accepted_document_ids=(),
        rejected_document_ids=rejected,
        blockers=(
            "RAG_RETRIEVAL_AMBIGUOUS",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
        web_fallback_allowed=False,
    )
