from __future__ import annotations

import pytest

from ai4binance.rag_corrective import (
    CorrectiveRagDecision,
    RetrievalCorrectionAction,
    RetrievedDocumentScore,
    evaluate_retrieval_quality,
)


def test_corrective_rag_accepts_high_confidence_retrieval_live_blocked() -> None:
    decision = evaluate_retrieval_quality(
        query_id="q1",
        scored_documents=(
            RetrievedDocumentScore("doc-1", 0.82),
            RetrievedDocumentScore("doc-2", 0.20),
        ),
    )

    assert decision.action is RetrievalCorrectionAction.CORRECT
    assert decision.accepted_document_ids == ("doc-1",)
    assert decision.rejected_document_ids == ("doc-2",)
    assert decision.blockers == ("LIVE_ORDER_BLOCKED",)
    assert decision.execution_allowed is False


def test_corrective_rag_blocks_ambiguous_and_empty_retrieval() -> None:
    ambiguous = evaluate_retrieval_quality(
        query_id="q2",
        scored_documents=(RetrievedDocumentScore("doc-1", 0.45),),
    )
    empty = evaluate_retrieval_quality(query_id="q3", scored_documents=())

    assert ambiguous.action is RetrievalCorrectionAction.AMBIGUOUS
    assert "RAG_RETRIEVAL_AMBIGUOUS" in ambiguous.blockers
    assert "HUMAN_REVIEW_REQUIRED" in ambiguous.blockers
    assert empty.action is RetrievalCorrectionAction.INCORRECT
    assert "RAG_RETRIEVAL_EMPTY" in empty.blockers
    assert "RAG_WEB_FALLBACK_DISABLED" in empty.blockers


def test_corrective_rag_validates_score_range() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        RetrievedDocumentScore("doc", 1.1)


def test_corrective_rag_validates_thresholds_and_query_id() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        evaluate_retrieval_quality(
            query_id="   ",
            scored_documents=(RetrievedDocumentScore("doc-1", 0.5),),
        )

    with pytest.raises(ValueError, match="0 <= lower < upper <= 1"):
        evaluate_retrieval_quality(
            query_id="q-threshold",
            scored_documents=(RetrievedDocumentScore("doc-1", 0.5),),
            lower_threshold=0.8,
            upper_threshold=0.7,
        )


def test_corrective_rag_low_quality_uses_web_fallback_flag() -> None:
    decision = evaluate_retrieval_quality(
        query_id="q-low",
        scored_documents=(
            RetrievedDocumentScore("doc-1", 0.10),
            RetrievedDocumentScore("doc-2", 0.20),
        ),
        allow_web_fallback=True,
    )

    assert decision.action is RetrievalCorrectionAction.INCORRECT
    assert decision.rejected_document_ids == ("doc-1", "doc-2")
    assert decision.web_fallback_allowed is True
    assert "RAG_WEB_FALLBACK_DISABLED" not in decision.blockers
    assert "RAG_RETRIEVAL_QUALITY_INSUFFICIENT" in decision.blockers


def test_corrective_rag_decision_contract_rejects_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        CorrectiveRagDecision(
            query_id="q1",
            action=RetrievalCorrectionAction.CORRECT,
            accepted_document_ids=("doc-1", "doc-1"),
            rejected_document_ids=(),
            blockers=("LIVE_ORDER_BLOCKED",),
        )

    with pytest.raises(ValueError, match="cannot contain blanks"):
        CorrectiveRagDecision(
            query_id="q2",
            action=RetrievalCorrectionAction.CORRECT,
            accepted_document_ids=("doc-1",),
            rejected_document_ids=("",),
            blockers=("LIVE_ORDER_BLOCKED",),
        )

    with pytest.raises(ValueError, match="cannot authorize execution"):
        CorrectiveRagDecision(
            query_id="q3",
            action=RetrievalCorrectionAction.CORRECT,
            accepted_document_ids=("doc-1",),
            rejected_document_ids=(),
            blockers=("LIVE_ORDER_BLOCKED",),
            execution_allowed=True,
        )

    with pytest.raises(ValueError, match="cannot promote production state"):
        CorrectiveRagDecision(
            query_id="q4",
            action=RetrievalCorrectionAction.CORRECT,
            accepted_document_ids=("doc-1",),
            rejected_document_ids=(),
            blockers=("LIVE_ORDER_BLOCKED",),
            promotion_status="STAGED_CANDIDATE",
        )

    with pytest.raises(ValueError, match="must remain live blocked"):
        CorrectiveRagDecision(
            query_id="q5",
            action=RetrievalCorrectionAction.CORRECT,
            accepted_document_ids=("doc-1",),
            rejected_document_ids=(),
            blockers=("LIVE_ORDER_BLOCKED",),
            live_eligibility_status="READY",
        )
