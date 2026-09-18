"""Tests for deterministic, research-only topic intake decisions."""

from ai4binance.external_intel.technology.research_intake import (
    RESEARCH_TOPICS,
    ResearchAction,
    ResearchAssessment,
    assess_finding,
    research_topics_payload,
)


def _assessment(**overrides: object) -> ResearchAssessment:
    values: dict[str, object] = {
        "finding_id": "finding-1",
        "text": "new deterministic algorithm for analytics",
        "evidence_strength": 0.8,
        "source_authority": 0.8,
        "novelty_score": 0.5,
        "system_relevance": 0.8,
        "canonical_compatibility": 0.8,
        "expected_benefit": 0.8,
        "implementation_cost": 0.4,
        "security_risk": 0.2,
        "trading_risk": 0.2,
    }
    values.update(overrides)
    return assess_finding(**values)  # type: ignore[arg-type]


def test_research_topics_cover_requested_intake_questions() -> None:
    expected_ids = {
        "NEW_ALGORITHM",
        "NEW_PROTOCOL",
        "NEW_MODEL",
        "NEW_AGENT_ARCHITECTURE",
        "NEW_INDICATOR",
        "NEW_EXECUTION_METHOD",
        "NEW_RISK_CONTROL_METHOD",
        "NEW_DATA_SOURCE",
        "NEW_OPTIMIZATION_METHOD",
        "NEW_BACKTESTING_METHOD",
        "NEW_SECURITY_MECHANISM",
        "NEW_BLOCKCHAIN_FEATURE",
        "NEW_MULTI_AGENT_PIPELINE",
        "NEW_METHODOLOGY",
    }

    assert {topic.topic_id for topic in RESEARCH_TOPICS} == expected_ids
    assert {item["topic_id"] for item in research_topics_payload()} == expected_ids
    assert all(
        item["question"] and item["validation_requirement"]
        for item in research_topics_payload()
    )


def test_assessment_has_only_requested_deterministic_actions_and_stays_blocked() -> (
    None
):
    prototype = _assessment()
    watch = _assessment(evidence_strength=0.4)
    research = _assessment(expected_benefit=0.5)
    ignore = _assessment(system_relevance=0.1)
    reject = _assessment(security_risk=0.8)
    validate = _assessment(local_validation_started=True)
    adopt = _assessment(local_validation_completed=True, canonical_compatibility=0.9)

    assert prototype.recommended_action is ResearchAction.PROTOTYPE
    assert watch.recommended_action is ResearchAction.WATCH
    assert research.recommended_action is ResearchAction.RESEARCH
    assert ignore.recommended_action is ResearchAction.IGNORE
    assert reject.recommended_action is ResearchAction.REJECT
    assert validate.recommended_action is ResearchAction.VALIDATE
    assert adopt.recommended_action is ResearchAction.ADOPT_CANDIDATE
    assert prototype.execution_allowed is False
    assert prototype.promotion_status == "RESEARCH_ONLY"
    assert prototype.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_methodology_is_not_misclassified_as_an_algorithm() -> None:
    assessment = _assessment(
        finding_id="finding-methodology",
        text="New methodology for reproducible benchmark validation",
    )

    assert assessment.topic_id == "NEW_METHODOLOGY"


def test_unmatched_finding_uses_the_general_methodology_topic() -> None:
    assessment = _assessment(finding_id="finding-general", text="unclassified finding")

    assert assessment.topic_id == "NEW_METHODOLOGY"
