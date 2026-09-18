"""Deterministic virtual-market candidate ranking tests."""

from dataclasses import replace

from ai4binance.domain import CandidateStatus
from ai4binance.schemas import AgentResult, AgentStatus, DataQuality
from ai4binance.strategies.arbitration import CandidateArbitrator
from ai4binance.strategies.ranking import VirtualMarketCandidateRanker
from tests.test_strategy_risk import agent_result, approved_candidate, snapshot


def _agent(
    name: str,
    *,
    score: float = 80.0,
    confidence: float = 0.8,
    vote: float = 0.8,
    metadata: dict[str, object] | None = None,
) -> AgentResult:
    result = agent_result(name, vote, score=score)
    return replace(
        result,
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        confidence=confidence,
        calculation_metadata=metadata or {},
    )


def test_virtual_market_ranker_keeps_blocked_candidates_out_of_ladder() -> None:
    ranker = VirtualMarketCandidateRanker()
    eligible = approved_candidate()
    blocked = replace(
        approved_candidate(),
        candidate_id="blocked-candidate",
        score=99.0,
        blockers=("ENTRY_TRIGGER_MISSING",),
        status=CandidateStatus.RESEARCH_ONLY,
    )

    ranked = ranker.rank(
        snapshot(),
        {
            "multi_timeframe": _agent("multi_timeframe"),
            "universe_liquidity": _agent("universe_liquidity", score=100.0),
        },
        (blocked, eligible),
    )

    assert ranked[0].candidate_id == eligible.candidate_id
    assert ranked[0].ranking_score is not None
    assert ranked[1].candidate_id == "blocked-candidate"
    assert ranked[1].ranking_score is None


def test_virtual_market_ranker_does_not_invent_historical_edge_bonus() -> None:
    ranker = VirtualMarketCandidateRanker()
    candidate = replace(approved_candidate(), setup_name="trend_continuation")
    baseline_results = {
        "market_regime": _agent("market_regime", metadata={"regime": "TREND"}),
        "multi_timeframe": _agent("multi_timeframe"),
        "universe_liquidity": _agent("universe_liquidity", score=100.0),
    }
    evidence_results = {
        **baseline_results,
        "market_regime": _agent(
            "market_regime",
            metadata={
                "regime": "TREND",
                "strategy_regime_research": {
                    "trend_continuation": {
                        "TREND": {"approved": True, "edge_score": 0.8}
                    }
                },
            },
        ),
    }

    baseline = ranker.rank(snapshot(), baseline_results, (candidate,))[0]
    evidenced = ranker.rank(snapshot(), evidence_results, (candidate,))[0]

    assert baseline.ranking_score is not None
    assert evidenced.ranking_score is not None
    assert evidenced.ranking_score > baseline.ranking_score


def test_virtual_market_ranker_uses_deterministic_tie_breaking_and_limits_to_five() -> (
    None
):
    ranker = VirtualMarketCandidateRanker()
    candidates = tuple(
        replace(
            approved_candidate(),
            candidate_id=f"candidate-z{index}",
            ranking_score=None,
        )
        for index in range(6)
    )
    tied = (
        replace(candidates[0], candidate_id="candidate-b"),
        replace(candidates[1], candidate_id="candidate-a"),
        *candidates[2:],
    )

    ranked = ranker.rank(
        snapshot(),
        {
            "multi_timeframe": _agent("multi_timeframe"),
            "universe_liquidity": _agent("universe_liquidity", score=100.0),
        },
        tied,
    )

    assert len(ranked) == 5
    assert ranked[0].candidate_id == "candidate-a"
    assert ranked[1].candidate_id == "candidate-b"


def test_candidate_arbitrator_prefers_higher_ranking_score_over_raw_score() -> None:
    stronger_rank = replace(
        approved_candidate(),
        candidate_id="ranked-first",
        score=75.0,
        ranking_score=95.0,
    )
    stronger_raw = replace(
        approved_candidate(),
        candidate_id="raw-score-only",
        score=90.0,
        ranking_score=80.0,
    )

    selection = CandidateArbitrator().select((stronger_raw, stronger_rank))

    assert selection.selected is not None
    assert selection.selected.candidate_id == "ranked-first"
