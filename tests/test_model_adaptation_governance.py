from __future__ import annotations

import pytest

from ai4binance.learning.model_adaptation import (
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
