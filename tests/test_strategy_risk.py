"""Strategy playbook, candidate and capital-risk tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.domain import (
    Action,
    CandidateStatus,
    PriceZone,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import SymbolInfo
from ai4binance.risk import RiskConfig, RiskContext, RiskEngine
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
)
from ai4binance.strategies.engine import StrategyEngine
from ai4binance.strategies.registry import (
    PlaybookRegistry,
    StrategyPlaybook,
    build_playbook_registry,
)

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


def snapshot(*, spread: str = "0.2", inventory: bool = False) -> MarketSnapshot:
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW - timedelta(hours=60 - index),
            open=Decimal("99") + Decimal(index) / Decimal("60"),
            high=Decimal("101") + Decimal(index) / Decimal("60"),
            low=Decimal("98") + Decimal(index) / Decimal("60"),
            close=Decimal("100") + Decimal(index) / Decimal("60"),
            volume=Decimal("100"),
        )
        for index in range(60)
    )
    return MarketSnapshot(
        snapshot_id="strategy-snapshot",
        created_at=NOW,
        exchange="Binance",
        market_type="Spot",
        symbol="HOTUSDT",
        timeframes=("1h",),
        ohlcv_by_timeframe={"1h": candles},
        latest_price=Decimal("100"),
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        spread=Decimal(spread),
        exchange_filters={
            "PRICE_FILTER": {
                "minPrice": "0.01",
                "maxPrice": "1000",
                "tickSize": "0.01",
            },
            "LOT_SIZE": {
                "minQty": "0.001",
                "maxQty": "1000",
                "stepSize": "0.001",
            },
            "MIN_NOTIONAL": {"minNotional": "10"},
        },
        data_quality=DataQuality.DATA_VALID,
        inventory_summary={"quantity": "5"} if inventory else {},
        market_metadata={
            "trading_status": "TRADING",
            "base_asset": "HOT",
            "quote_asset": "USDT",
        },
    )


def agent_result(name: str, vote: float, *, score: float = 80.0) -> AgentResult:
    return AgentResult(
        agent_name=name,
        agent_version="1",
        snapshot_id="strategy-snapshot",
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframes=("1h",),
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=vote,
        score=score,
        confidence=0.8,
        evidence=(f"{name.upper()}_EVIDENCE",),
        reason_codes=("TEST",),
    )


def evidence(direction: float, *, trigger: bool = True) -> dict[str, AgentResult]:
    results = {
        "trend": agent_result("trend", direction),
        "market_structure": agent_result("market_structure", direction),
        "multi_timeframe": agent_result("multi_timeframe", direction),
        "confluence": agent_result("confluence", direction, score=82.0),
    }
    if trigger:
        results["price_action"] = agent_result("price_action", direction, score=70.0)
    return results


def approved_candidate() -> TradeCandidate:
    return TradeCandidate(
        candidate_id="candidate-1",
        snapshot_id="strategy-snapshot",
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframe="1h",
        action=Action.BUY,
        setup_name="trend_continuation",
        status=CandidateStatus.READY_FOR_RISK,
        entry_zone=PriceZone(Decimal("100"), Decimal("100")),
        invalidation_level=Decimal("95"),
        stop_loss=Decimal("95"),
        take_profit_levels=(Decimal("110"),),
        trailing_stop=Decimal("95"),
        atr=Decimal("3.333333"),
        risk_reward=Decimal("2"),
        score=80.0,
        confidence=0.8,
        promotion_status=ValidationStatus.PAPER_APPROVED,
        evidence=("TEST",),
    )


def symbol_filters() -> SymbolFilters:
    return SymbolFilters.from_symbol_info(
        SymbolInfo(
            "HOTUSDT",
            "TRADING",
            "HOT",
            "USDT",
            {
                "PRICE_FILTER": {
                    "minPrice": "0.01",
                    "maxPrice": "1000",
                    "tickSize": "0.01",
                },
                "LOT_SIZE": {
                    "minQty": "0.001",
                    "maxQty": "1000",
                    "stepSize": "0.001",
                },
                "MIN_NOTIONAL": {"minNotional": "10"},
            },
        )
    )


def test_playbook_registry_contains_all_required_playbooks() -> None:
    registry = build_playbook_registry()
    assert len(registry.playbooks) == 20
    assert registry.get("trend_continuation").implemented is True
    assert sum(item.implemented for item in registry.playbooks) == 10
    assert registry.get("compression_breakout").implemented is True
    with pytest.raises(ValueError, match="unique"):
        PlaybookRegistry((registry.playbooks[0], registry.playbooks[0]))


def test_playbook_rejects_direct_live_registration() -> None:
    base = build_playbook_registry().playbooks[0]
    with pytest.raises(ValueError, match="directly as live"):
        StrategyPlaybook(
            name="unsafe",
            compatible_regimes=base.compatible_regimes,
            required_agents=base.required_agents,
            minimum_evidence=1,
            entry_trigger=base.entry_trigger,
            invalidation_rule=base.invalidation_rule,
            stop_rule=base.stop_rule,
            target_rule=base.target_rule,
            trailing_rule=base.trailing_rule,
            rejection_rules=base.rejection_rules,
            required_oos_evidence=base.required_oos_evidence,
            promotion_status=ValidationStatus.LIVE_ELIGIBLE,
        )


def test_strategy_engine_generates_research_candidate_and_wait_state() -> None:
    engine = StrategyEngine()
    ready = engine.generate(snapshot(), evidence(0.8))[0]
    assert ready.status is CandidateStatus.READY_FOR_RISK
    assert ready.action is Action.BUY
    assert ready.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert ready.risk_reward == Decimal("2")
    assert (
        ready.candidate_id == engine.generate(snapshot(), evidence(0.8))[0].candidate_id
    )

    waiting = engine.generate(snapshot(), evidence(0.8, trigger=False))[0]
    assert waiting.status is CandidateStatus.WAIT_FOR_RETEST
    assert waiting.blockers == ("ENTRY_TRIGGER_MISSING",)


def test_strategy_engine_blocks_naked_spot_sell_candidate() -> None:
    candidate = StrategyEngine().generate(snapshot(), evidence(-0.8))[0]
    assert candidate.action is Action.SELL
    assert candidate.status is CandidateStatus.RESEARCH_ONLY
    assert "INVENTORY_UNKNOWN_FOR_SPOT_SELL" in candidate.blockers


def test_risk_engine_approves_only_promoted_complete_context() -> None:
    assessment = RiskEngine().evaluate(
        approved_candidate(),
        snapshot(),
        RiskContext(equity_usdt=Decimal("1000")),
        symbol_filters(),
    )
    assert assessment.approved is True
    assert assessment.size_usdt == Decimal("100.000")
    assert assessment.quantity == Decimal("1.000")
    assert assessment.risk_amount_usdt == Decimal("5.000")


def test_risk_engine_returns_all_relevant_blockers() -> None:
    research = replace(
        approved_candidate(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    assessment = RiskEngine().evaluate(
        research,
        snapshot(spread="1"),
        RiskContext(
            equity_usdt=Decimal("1000"),
            daily_loss_usdt=Decimal("40"),
            estimated_slippage_ratio=Decimal("0.01"),
            consecutive_losses=3,
            cooldown_active=True,
        ),
        symbol_filters(),
    )
    assert assessment.approved is False
    assert "STRATEGY_NOT_PROMOTED" in assessment.blockers
    assert "DAILY_LOSS_LIMIT_REACHED" in assessment.blockers
    assert "REPEATED_LOSS_CIRCUIT_BREAKER" in assessment.blockers
    assert "STOP_LOSS_COOLDOWN_ACTIVE" in assessment.blockers
    assert "SLIPPAGE_EXCEEDS_LIMIT" in assessment.blockers
    assert "SPREAD_EXCEEDS_LIMIT" in assessment.blockers


def test_risk_engine_evaluates_only_first_five_arbitrated_candidates() -> None:
    candidates = tuple(
        replace(approved_candidate(), candidate_id=f"candidate-{index}")
        for index in range(6)
    )
    assessments = RiskEngine().evaluate_many(
        candidates,
        snapshot(),
        RiskContext(equity_usdt=Decimal("1000")),
        symbol_filters(),
    )

    assert tuple(item.candidate_id for item in assessments) == tuple(
        f"candidate-{index}" for index in range(5)
    )
    with pytest.raises(ValueError, match="between one and five"):
        RiskEngine().evaluate_many(
            candidates,
            snapshot(),
            RiskContext(equity_usdt=Decimal("1000")),
            symbol_filters(),
            limit=6,
        )


def test_risk_config_and_candidate_geometry_fail_closed() -> None:
    with pytest.raises(ValueError, match="risk ratios"):
        RiskConfig(max_risk_per_trade=Decimal("2"))
    with pytest.raises(ValueError, match="BUY candidate geometry"):
        replace(approved_candidate(), stop_loss=Decimal("101"))
