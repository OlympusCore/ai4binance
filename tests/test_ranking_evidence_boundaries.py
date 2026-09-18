"""Ranking must not invent evidence from malformed metadata."""

from dataclasses import replace
from decimal import Decimal

import pytest

from ai4binance.strategies.ranking import VirtualMarketCandidateRanker
from tests.test_candidate_ranking import _agent
from tests.test_strategy_risk import approved_candidate, snapshot


@pytest.mark.parametrize("limit", [0, 6])
def test_ranker_rejects_unbounded_candidate_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="between one and five"):
        VirtualMarketCandidateRanker(max_candidates=limit)


@pytest.mark.parametrize("value", [None, True, [], "bad", "NaN", "Infinity", "-1"])
def test_ranker_rejects_invalid_portfolio_numbers(value: object) -> None:
    assert VirtualMarketCandidateRanker._decimal(value) is None


@pytest.mark.parametrize("value", [True, "1", None, float("nan"), float("inf")])
def test_ranker_rejects_invalid_edge_numbers(value: object) -> None:
    assert VirtualMarketCandidateRanker._float(value) is None


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"trend_continuation": []},
        {"trend_continuation": {"TREND": []}},
        {"trend_continuation": {"TREND": {"approved": False, "edge_score": 1}}},
        {"trend_continuation": {"TREND": {"approved": True, "edge_score": -1}}},
    ],
)
def test_missing_or_unapproved_research_cannot_improve_rank(evidence: object) -> None:
    ranker = VirtualMarketCandidateRanker()
    candidate = replace(approved_candidate(), setup_name="trend_continuation")
    agents = {
        "market_regime": _agent(
            "market_regime",
            metadata={"regime": "TREND", "strategy_regime_research": evidence},
        )
    }
    assert ranker._historical_edge_bonus(agents, candidate) == 0
    result = ranker.rank(snapshot(), agents, (candidate,))[0]
    assert result.blockers == candidate.blockers
    assert result.status == candidate.status


def test_ranker_handles_missing_market_evidence_and_concentration() -> None:
    ranker = VirtualMarketCandidateRanker()
    candidate = approved_candidate()
    assert ranker._regime_fit({}, candidate) == 0
    assert ranker._mtf_alignment({}, 1) == 0
    assert ranker._liquidity_quality(snapshot(), {}) == 0
    assert ranker._mapping_metadata(None, "research") is None
    assert ranker._string_metadata(None, "regime") is None
    assert ranker._decimal(Decimal("0.5")) == Decimal("0.5")
    concentrated = replace(
        snapshot(),
        wallet_summary={"equity_usdt": "100"},
        inventory_summary={"exposure_usdt": "100"},
        market_metadata={"correlation_penalty_ratio": "1"},
    )
    assert ranker._portfolio_penalty(concentrated, candidate) == 10
    assert (
        ranker.rank(concentrated, {}, (candidate,))[0].ranking_score
        < ranker.rank(snapshot(), {}, (candidate,))[0].ranking_score
    )
