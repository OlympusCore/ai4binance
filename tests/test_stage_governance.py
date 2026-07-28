"""Candidate, validation artifact and controlled-learning governance tests."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from math import inf
from pathlib import Path

import pytest
from test_strategy_risk import approved_candidate

from ai4binance.application.learning_loop import ControlledLearningLoop
from ai4binance.domain import Action, ValidationStatus
from ai4binance.learning.storage import LearningStore
from ai4binance.schemas import AgentStatus
from ai4binance.strategies.arbitration import CandidateArbitrator
from ai4binance.strategies.engine import StrategyEngine
from ai4binance.validation.artifacts import (
    StrategyApprovalArtifact,
    ValidationArtifactRegistry,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def test_candidate_arbitration_ranks_and_blocks_direction_conflict() -> None:
    buy = approved_candidate()
    weaker = replace(buy, candidate_id="candidate-2", score=70.0)
    selection = CandidateArbitrator().select((weaker, buy))
    assert selection.selected == buy
    assert selection.execution_allowed is False

    sell = replace(
        buy,
        candidate_id="candidate-sell",
        action=Action.SELL,
        stop_loss=buy.take_profit_levels[0],
        invalidation_level=buy.take_profit_levels[0],
        trailing_stop=buy.take_profit_levels[0],
        take_profit_levels=(buy.stop_loss,),
        inventory_action="REDUCE_EXISTING_SPOT_INVENTORY",
    )
    conflicted = CandidateArbitrator().select((buy, sell))
    assert conflicted.selected is None
    assert conflicted.blockers == ("CONFLICTING_CANDIDATE_DIRECTIONS",)


def test_candidate_arbitration_rejects_weak_and_ambiguous_candidates() -> None:
    candidate = approved_candidate()
    weak = replace(
        candidate,
        score=50.0,
        confidence=0.4,
        risk_reward=Decimal("1.5"),
    )

    rejected = CandidateArbitrator().select((weak,))

    assert rejected.selected is None
    assert rejected.blockers == (
        "CANDIDATE_SCORE_BELOW_MINIMUM",
        "CANDIDATE_CONFIDENCE_BELOW_MINIMUM",
        "CANDIDATE_RISK_REWARD_BELOW_MINIMUM",
        "NO_QUALIFIED_CANDIDATE",
    )

    close_runner_up = replace(
        candidate,
        candidate_id="candidate-close-runner-up",
        setup_name="breakout_retest",
        score=78.0,
    )
    ambiguous = CandidateArbitrator().select((candidate, close_runner_up))
    assert ambiguous.selected is None
    assert ambiguous.blockers == ("AMBIGUOUS_TOP_CANDIDATES",)
    assert ambiguous.ranked == (candidate, close_runner_up)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("minimum_score", inf),
        ("minimum_confidence", 1.1),
        ("minimum_risk_reward", Decimal("0")),
        ("minimum_score_lead", -1.0),
    ],
)
def test_candidate_arbitrator_rejects_invalid_thresholds(
    field_name: str,
    value: float | Decimal,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        CandidateArbitrator(**{field_name: value})  # type: ignore[arg-type]


def test_validation_artifact_requires_exact_identity_and_never_grants_live() -> None:
    artifact = StrategyApprovalArtifact(
        approval_id="approval-1",
        approved_at=NOW,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="breakout_retest",
        strategy_version="2",
        config_hash="abc",
    )
    registry = ValidationArtifactRegistry((artifact,))
    assert (
        registry.resolve(
            symbol="hotusdt",
            timeframe="1h",
            playbook="breakout_retest",
            strategy_version="2",
            config_hash="abc",
        )
        is ValidationStatus.PAPER_APPROVED
    )
    assert (
        registry.resolve(
            symbol="HOTUSDT",
            timeframe="1h",
            playbook="breakout_retest",
            strategy_version="2",
            config_hash="wrong",
        )
        is ValidationStatus.RESEARCH_ONLY
    )


def test_controlled_learning_loop_is_idempotent_and_execution_blocked(
    tmp_path: Path,
) -> None:
    loop = ControlledLearningLoop(
        LearningStore(tmp_path / "learning.json", tmp_path / "audit.jsonl")
    )
    first = loop.run(created_at=NOW)
    second = loop.run(created_at=NOW)
    assert first.saved is True
    assert second.saved is False
    assert second.execution_allowed is False
    assert second.summary.risk_change_allowed is False


def test_strategy_engine_applies_bounded_whale_fusion_modifier() -> None:
    from test_strategy_risk import evidence, snapshot

    results = evidence(0.8)
    baseline = StrategyEngine().generate(snapshot(), results)[0]
    results["whale"] = replace(
        results["trend"],
        agent_name="whale",
        status=AgentStatus.PARTIAL,
        directional_vote=1.0,
        confidence=1.0,
        hard_gate_eligible=False,
    )

    adjusted = StrategyEngine().generate(snapshot(), results)[0]

    assert adjusted.score == min(100.0, baseline.score + 5.0)
    assert "WHALE_FUSION_ALIGNED_SUPPLEMENTARY" in adjusted.evidence
    assert adjusted.promotion_status is ValidationStatus.RESEARCH_ONLY
