from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.research import (
    AlgorithmCandidate,
    AlgorithmCandidateOrigin,
    AlgorithmCandidateStatus,
    AlgorithmValidationEvidence,
    AlgorithmVerificationEvidence,
    VerificationStatus,
)


def origin() -> AlgorithmCandidateOrigin:
    return AlgorithmCandidateOrigin(
        origin_type="AUTO_RESEARCH",
        generator="algorithm_discovery",
        evidence_refs=("evidence:research-intake:1",),
    )


def candidate() -> AlgorithmCandidate:
    return AlgorithmCandidate(
        algorithm_id="adaptive_liquidity_momentum_v001",
        origin=origin(),
        hypothesis=(
            "Momentum persistence conditioned by normalized liquidity imbalance "
            "may improve continuation detection."
        ),
        inputs=(
            "returns",
            "volume",
            "spread",
            "order_book_imbalance",
            "realized_volatility",
        ),
        formula_ref="formula:adaptive_liquidity_momentum:v1",
    )


def test_algorithm_candidate_starts_research_only_and_live_blocked() -> None:
    proposal = candidate()

    assert proposal.status is AlgorithmCandidateStatus.RESEARCH_CANDIDATE
    assert proposal.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert proposal.blockers == ("LIVE_ORDER_BLOCKED",)
    assert proposal.execution_allowed is False
    assert proposal.paper_execution_allowed is False
    assert proposal.live_execution_allowed is False
    assert proposal.self_promotion_allowed is False
    assert proposal.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_algorithm_candidate_can_be_staged_only_without_blockers() -> None:
    staged = replace(
        candidate(),
        status=AlgorithmCandidateStatus.ROBUSTNESS_VALIDATED,
        verification=AlgorithmVerificationEvidence(
            mathematical=VerificationStatus.VERIFIED,
            statistical=VerificationStatus.VERIFIED,
            implementation=VerificationStatus.VERIFIED,
            evidence_refs=("verification:1",),
        ),
        validation=AlgorithmValidationEvidence(
            backtest=VerificationStatus.VERIFIED,
            walk_forward=VerificationStatus.VERIFIED,
            oos=VerificationStatus.VERIFIED,
            robustness=VerificationStatus.VERIFIED,
            regime=VerificationStatus.VERIFIED,
            evidence_refs=("validation:1",),
        ),
        blockers=(),
        promotion_status=ValidationStatus.STAGED_CANDIDATE,
    )

    assert staged.promotion_status is ValidationStatus.STAGED_CANDIDATE
    assert staged.execution_allowed is False
    assert staged.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_algorithm_candidate_rejects_hidden_authority() -> None:
    with pytest.raises(ValueError, match="execution authority"):
        replace(candidate(), execution_allowed=True)
    with pytest.raises(ValueError, match="execution authority"):
        replace(candidate(), paper_execution_allowed=True)
    with pytest.raises(ValueError, match="execution authority"):
        replace(candidate(), live_execution_allowed=True)
    with pytest.raises(ValueError, match="execution authority"):
        replace(candidate(), self_promotion_allowed=True)
    with pytest.raises(ValueError, match="live blocked"):
        replace(candidate(), live_eligibility_status="READY")
    with pytest.raises(ValueError, match="paper or live"):
        replace(candidate(), promotion_status=ValidationStatus.PAPER_APPROVED)


def test_algorithm_candidate_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="algorithm identity"):
        replace(candidate(), algorithm_id=" ")
    with pytest.raises(ValueError, match="algorithm inputs"):
        replace(candidate(), inputs=("returns", "returns"))
    with pytest.raises(ValueError, match="formula reference"):
        replace(candidate(), formula_ref=" ")
    with pytest.raises(ValueError, match="staged algorithm candidate"):
        replace(candidate(), promotion_status=ValidationStatus.STAGED_CANDIDATE)


def test_unavailable_verification_and_validation_require_blockers() -> None:
    with pytest.raises(ValueError, match="verification requires blockers"):
        AlgorithmVerificationEvidence(mathematical=VerificationStatus.UNAVAILABLE)
    with pytest.raises(ValueError, match="validation requires blockers"):
        AlgorithmValidationEvidence(oos=VerificationStatus.FAILED)

    verification = AlgorithmVerificationEvidence(
        mathematical=VerificationStatus.UNAVAILABLE,
        blockers=("WOLFRAM_VERIFICATION_UNAVAILABLE",),
    )
    validation = AlgorithmValidationEvidence(
        oos=VerificationStatus.FAILED,
        blockers=("OOS_VALIDATION_FAILED",),
    )

    assert verification.blockers == ("WOLFRAM_VERIFICATION_UNAVAILABLE",)
    assert validation.blockers == ("OOS_VALIDATION_FAILED",)
