from __future__ import annotations

import pytest

from ai4binance.learning.model_adaptation import (
    ModelAdaptationAssessment,
    ModelAdaptationCandidate,
    ModelAdaptationMethod,
    assess_model_adaptation_candidate,
)


def test_model_adaptation_candidate_stays_research_only_until_reviews_exist() -> None:
    candidate = ModelAdaptationCandidate(
        candidate_id="adapter-1",
        method=ModelAdaptationMethod.QLORA,
        base_model_ref="local:model",
        dataset_ref=None,
        evaluation_ref="eval:smoke",
        oos_evidence_ref=None,
        model_card_ref=None,
        red_team_ref=None,
    )

    assessment = assess_model_adaptation_candidate(candidate)

    assert assessment.recommendation == "RESEARCH_ONLY"
    assert "MODEL_ADAPTATION_DATASET_REF_MISSING" in assessment.blockers
    assert "MODEL_ADAPTATION_OOS_EVIDENCE_REF_MISSING" in assessment.blockers
    assert "MODEL_ADAPTATION_RED_TEAM_REF_MISSING" in assessment.blockers
    assert assessment.execution_allowed is False
    assert assessment.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_model_adaptation_candidate_can_only_be_staged_with_evidence() -> None:
    candidate = ModelAdaptationCandidate(
        candidate_id="adapter-2",
        method=ModelAdaptationMethod.LORA,
        base_model_ref="local:model",
        dataset_ref="dataset:curated",
        evaluation_ref="eval:offline",
        oos_evidence_ref="oos:regime-split",
        model_card_ref="model-card:adapter-2",
        red_team_ref="red-team:adapter-2",
        risk_review_ref="risk:adapter-2",
    )

    assessment = assess_model_adaptation_candidate(candidate)

    assert assessment.recommendation == "STAGED_CANDIDATE"
    assert assessment.blockers == ("LIVE_ORDER_BLOCKED",)
    assert "QUALITY_DEPARTMENT_REVIEW" in assessment.required_reviews


def test_model_adaptation_rejects_execution_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize execution"):
        ModelAdaptationCandidate(
            candidate_id="adapter-3",
            method=ModelAdaptationMethod.PEFT,
            base_model_ref="local:model",
            dataset_ref="dataset",
            evaluation_ref="eval",
            oos_evidence_ref="oos",
            model_card_ref="card",
            red_team_ref="red-team",
            execution_allowed=True,
        )


def test_model_adaptation_candidate_validates_identity_and_live_boundaries() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ModelAdaptationCandidate(
            candidate_id="",
            method=ModelAdaptationMethod.PEFT,
            base_model_ref="local:model",
            dataset_ref="dataset",
            evaluation_ref="eval",
            oos_evidence_ref="oos",
            model_card_ref="card",
            red_team_ref="red-team",
        )

    with pytest.raises(ValueError, match="cannot be empty"):
        ModelAdaptationCandidate(
            candidate_id="adapter-4",
            method=ModelAdaptationMethod.PEFT,
            base_model_ref="   ",
            dataset_ref="dataset",
            evaluation_ref="eval",
            oos_evidence_ref="oos",
            model_card_ref="card",
            red_team_ref="red-team",
        )

    with pytest.raises(ValueError, match="cannot promote production state"):
        ModelAdaptationCandidate(
            candidate_id="adapter-5",
            method=ModelAdaptationMethod.PEFT,
            base_model_ref="local:model",
            dataset_ref="dataset",
            evaluation_ref="eval",
            oos_evidence_ref="oos",
            model_card_ref="card",
            red_team_ref="red-team",
            promotion_status="STAGED_CANDIDATE",
        )

    with pytest.raises(ValueError, match="must remain live blocked"):
        ModelAdaptationCandidate(
            candidate_id="adapter-6",
            method=ModelAdaptationMethod.PEFT,
            base_model_ref="local:model",
            dataset_ref="dataset",
            evaluation_ref="eval",
            oos_evidence_ref="oos",
            model_card_ref="card",
            red_team_ref="red-team",
            live_eligibility_status="READY",
        )


def test_model_adaptation_whitespace_references_are_treated_as_missing() -> None:
    candidate = ModelAdaptationCandidate(
        candidate_id="adapter-7",
        method=ModelAdaptationMethod.QLORA,
        base_model_ref="local:model",
        dataset_ref="  ",
        evaluation_ref="  ",
        oos_evidence_ref="oos:ok",
        model_card_ref="  ",
        red_team_ref="  ",
        risk_review_ref="  ",
    )

    assessment = assess_model_adaptation_candidate(candidate)

    assert "MODEL_ADAPTATION_DATASET_REF_MISSING" in assessment.blockers
    assert "MODEL_ADAPTATION_EVALUATION_REF_MISSING" in assessment.blockers
    assert "MODEL_ADAPTATION_MODEL_CARD_REF_MISSING" in assessment.blockers
    assert "MODEL_ADAPTATION_RED_TEAM_REF_MISSING" in assessment.blockers
    assert "MODEL_ADAPTATION_RISK_REVIEW_REF_MISSING" in assessment.blockers


def test_model_adaptation_assessment_contract_rejects_invalid_state() -> None:
    with pytest.raises(ValueError, match="cannot contain blanks"):
        ModelAdaptationAssessment(
            candidate_id="adapter-a",
            method=ModelAdaptationMethod.LORA,
            blockers=("",),
            required_reviews=("QUALITY_DEPARTMENT_REVIEW",),
            recommendation="RESEARCH_ONLY",
        )

    with pytest.raises(ValueError, match="cannot contain blanks"):
        ModelAdaptationAssessment(
            candidate_id="adapter-b",
            method=ModelAdaptationMethod.LORA,
            blockers=("LIVE_ORDER_BLOCKED",),
            required_reviews=("",),
            recommendation="RESEARCH_ONLY",
        )

    with pytest.raises(ValueError, match="cannot authorize execution"):
        ModelAdaptationAssessment(
            candidate_id="adapter-c",
            method=ModelAdaptationMethod.LORA,
            blockers=("LIVE_ORDER_BLOCKED",),
            required_reviews=("QUALITY_DEPARTMENT_REVIEW",),
            recommendation="RESEARCH_ONLY",
            execution_allowed=True,
        )

    with pytest.raises(ValueError, match="cannot promote production state"):
        ModelAdaptationAssessment(
            candidate_id="adapter-d",
            method=ModelAdaptationMethod.LORA,
            blockers=("LIVE_ORDER_BLOCKED",),
            required_reviews=("QUALITY_DEPARTMENT_REVIEW",),
            recommendation="RESEARCH_ONLY",
            promotion_status="STAGED_CANDIDATE",
        )

    with pytest.raises(ValueError, match="must remain live blocked"):
        ModelAdaptationAssessment(
            candidate_id="adapter-e",
            method=ModelAdaptationMethod.LORA,
            blockers=("LIVE_ORDER_BLOCKED",),
            required_reviews=("QUALITY_DEPARTMENT_REVIEW",),
            recommendation="RESEARCH_ONLY",
            live_eligibility_status="READY",
        )
