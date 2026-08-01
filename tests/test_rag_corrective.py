from __future__ import annotations

import pytest

from ai4binance.rag_corrective import (
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
