"""Strategy playbook, candidate and capital-risk tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.risk import (
    RiskAssessment,
    RiskConfig,
    RiskContext,
    RiskEngine,
    VirtualMarketPositionSizingPolicy,
)
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
)
from ai4binance.strategies.engine import StrategyEngine
from ai4binance.strategies.regime_router import (
    DeterministicRegimeRouter,
    RoutedMarketRegime,
)
from ai4binance.strategies.registry import (
    GovernedStrategyRegistry,
    GovernedStrategyRegistryEntry,
    PlaybookRegistry,
    StrategyPlaybook,
    VirtualStrategyDefinition,
    VirtualStrategyPortfolioRegistry,
    build_governed_strategy_registry,
    build_playbook_registry,
    build_virtual_strategy_portfolio_registry,
)

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


def write_validation_run_card(
    root: Path,
    *,
    symbol: str,
    timeframe: str,
    playbook: str,
    promotion_status: str,
    blockers: tuple[str, ...] = (),
) -> Path:
    path = root / symbol / timeframe / f"{playbook}.run-card.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        f"runtime/artifacts/research/backtest/validation/{symbol}/{timeframe}/{playbook}.jsonl",
                        "abc",
                    ]
                ],
                "blockers": list(blockers),
                "created_at": NOW.isoformat(),
                "execution_allowed": False,
                "hypothesis_id": f"hyp:{playbook}:{timeframe}",
                "metrics": [("net_return", 0.0)],
                "promotion_status": promotion_status,
                "run_id": f"run:{playbook}:{timeframe}",
                "symbol": symbol,
                "timeframe": timeframe,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def snapshot(
    *,
    spread: str = "0.2",
    inventory: bool = False,
    market_type: str = "Spot",
) -> MarketSnapshot:
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
        market_type=market_type,
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


def market_regime_result(
    regime: str,
    *,
    vote: float,
    atr_ratio: str = "0.02",
) -> AgentResult:
    return AgentResult(
        agent_name="market_regime",
        agent_version="1",
        snapshot_id="strategy-snapshot",
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframes=("1h",),
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=vote,
        score=80.0,
        confidence=0.8,
        evidence=("EMA_ATR_REGIME",),
        reason_codes=("MARKET_REGIME_CLASSIFIED",),
        calculation_metadata={"regime": regime, "atr_ratio": atr_ratio},
    )


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


def test_virtual_strategy_portfolio_registry_is_bounded_to_four_families() -> None:
    registry = build_virtual_strategy_portfolio_registry()

    assert tuple(item.strategy_id for item in registry.strategies) == (
        "TREND_PULLBACK",
        "BREAKOUT_RETEST",
        "MOMENTUM_CONTINUATION",
        "MEAN_REVERSION",
    )
    assert registry.resolve_playbook("pullback_continuation").strategy_id == (
        "TREND_PULLBACK"
    )
    assert registry.resolve_playbook("compression_breakout").strategy_id == (
        "BREAKOUT_RETEST"
    )
    assert registry.resolve_playbook("trend_continuation").strategy_id == (
        "MOMENTUM_CONTINUATION"
    )
    assert registry.resolve_playbook("range_rotation").strategy_id == "MEAN_REVERSION"
    assert all(
        item.promotion_status is ValidationStatus.RESEARCH_ONLY
        and item.live_eligibility_status == "LIVE_ORDER_BLOCKED"
        and item.bounded_simulation_only is True
        for item in registry.strategies
    )
    assert registry.get("TREND_PULLBACK").supported_regimes == ("TREND_UP",)
    assert registry.get("MEAN_REVERSION").supported_regimes == ("RANGE",)

    with pytest.raises(ValueError, match="one family"):
        VirtualStrategyPortfolioRegistry(
            (
                VirtualStrategyDefinition(
                    strategy_id="A",
                    strategy_version="1",
                    supported_markets=("SPOT",),
                    supported_regimes=("TREND",),
                    entry_rule="ENTRY",
                    invalidation_rule="INVALIDATION",
                    exit_rule="EXIT",
                    risk_profile="A_V1",
                    playbooks=("shared_playbook",),
                ),
                VirtualStrategyDefinition(
                    strategy_id="B",
                    strategy_version="1",
                    supported_markets=("SPOT",),
                    supported_regimes=("TREND",),
                    entry_rule="ENTRY",
                    invalidation_rule="INVALIDATION",
                    exit_rule="EXIT",
                    risk_profile="B_V1",
                    playbooks=("shared_playbook",),
                ),
            )
        )


def test_governed_registry_stays_research_only() -> None:
    registry = build_governed_strategy_registry()

    assert tuple(item.strategy_id for item in registry.strategies) == (
        "TREND_PULLBACK",
        "BREAKOUT_RETEST",
        "MOMENTUM_CONTINUATION",
        "MEAN_REVERSION",
    )
    trend = registry.resolve_playbook("trend_continuation")
    assert trend.strategy_id == "MOMENTUM_CONTINUATION"
    assert trend.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert trend.missing_evidence_refs == ()
    assert trend.parameter_set_ref.endswith("trend_continuation.run-card.json")
    assert trend.paper_ref.endswith("runtime/artifacts/research/backtest/validation")
    assert trend.owner == "Enterprise Strategy Governance"
    assert trend.evidence_complete is True
    assert trend.paper_ready is False


def test_governed_strategy_registry_requires_complete_evidence_for_paper_approval() -> (
    None
):
    base = build_governed_strategy_registry().get("MOMENTUM_CONTINUATION")
    with pytest.raises(ValueError, match="paper approval requires complete"):
        GovernedStrategyRegistryEntry(
            strategy_id=base.strategy_id,
            version=base.version,
            implementation_ref=base.implementation_ref,
            parameter_set_ref=base.parameter_set_ref,
            market_scope=base.market_scope,
            regime_scope=base.regime_scope,
            dataset_revision=base.dataset_revision,
            backtest_ref=base.backtest_ref,
            walk_forward_ref=base.walk_forward_ref,
            oos_ref=base.oos_ref,
            robustness_ref=base.robustness_ref,
            paper_ref=base.paper_ref,
            owner=base.owner,
            playbooks=base.playbooks,
            promotion_status=ValidationStatus.PAPER_APPROVED,
        )


def test_governed_strategy_registry_can_promote_when_paper_evidence_is_approved(
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    write_validation_run_card(
        validation_root,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="trend_continuation",
        promotion_status="PAPER_APPROVED",
    )
    write_validation_run_card(
        validation_root,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="volatility_expansion",
        promotion_status="PAPER_APPROVED",
    )
    base = build_governed_strategy_registry().get("MOMENTUM_CONTINUATION")
    complete = replace(
        base,
        parameter_set_ref=(
            validation_root / "HOTUSDT" / "1h" / "trend_continuation.run-card.json"
        ).as_posix(),
        dataset_revision=validation_root.as_posix(),
        backtest_ref=(
            validation_root / "HOTUSDT" / "1h" / "trend_continuation.run-card.json"
        ).as_posix(),
        walk_forward_ref=validation_root.as_posix(),
        oos_ref=validation_root.as_posix(),
        robustness_ref=validation_root.as_posix(),
        paper_ref=validation_root.as_posix(),
    )
    registry = GovernedStrategyRegistry(
        tuple(
            complete if item.strategy_id == complete.strategy_id else item
            for item in build_governed_strategy_registry().strategies
        )
    )
    promoted = registry.with_promotion(
        "MOMENTUM_CONTINUATION",
        ValidationStatus.PAPER_APPROVED,
    )

    assert promoted.get("MOMENTUM_CONTINUATION").promotion_status is (
        ValidationStatus.PAPER_APPROVED
    )
    assert promoted.resolve_playbook("trend_continuation").paper_ready is True


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
    trend_up = {"market_regime": market_regime_result("STRONG_UPTREND", vote=0.8)}
    ready = engine.generate(snapshot(), {**evidence(0.8), **trend_up})[0]
    assert ready.status is CandidateStatus.READY_FOR_RISK
    assert ready.action is Action.BUY
    assert ready.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert ready.risk_reward == Decimal("2")
    assert (
        ready.candidate_id
        == engine.generate(snapshot(), {**evidence(0.8), **trend_up})[0].candidate_id
    )
    assert "VIRTUAL_STRATEGY_ID:MOMENTUM_CONTINUATION" in ready.evidence
    assert "VIRTUAL_STRATEGY_VERSION:1" in ready.evidence
    assert "REGIME_ROUTE:TREND_UP" in ready.evidence

    waiting = engine.generate(snapshot(), {**evidence(0.8, trigger=False), **trend_up})[
        0
    ]
    assert waiting.status is CandidateStatus.WAIT_FOR_RETEST
    assert waiting.blockers == ("ENTRY_TRIGGER_MISSING",)
    assert "VIRTUAL_STRATEGY_ID:MOMENTUM_CONTINUATION" in waiting.evidence


def test_strategy_engine_requires_governed_family_approval_for_paper_status(
    tmp_path: Path,
) -> None:
    from ai4binance.validation.artifacts import (
        StrategyApprovalArtifact,
        ValidationArtifactRegistry,
    )

    trend_up = {"market_regime": market_regime_result("STRONG_UPTREND", vote=0.8)}
    approval_registry = ValidationArtifactRegistry(
        (
            StrategyApprovalArtifact(
                approval_id="approval-1",
                approved_at=NOW,
                symbol="HOTUSDT",
                timeframe="1h",
                playbook="trend_continuation",
                strategy_version="1",
                config_hash="default",
            ),
        )
    )
    playbook_registry = build_playbook_registry().with_promotion(
        "trend_continuation",
        ValidationStatus.PAPER_APPROVED,
    )
    incomplete = StrategyEngine(
        registry=playbook_registry,
        approval_registry=approval_registry,
    ).generate(snapshot(), {**evidence(0.8), **trend_up})[0]
    validation_root = tmp_path / "validation"
    write_validation_run_card(
        validation_root,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="trend_continuation",
        promotion_status="PAPER_APPROVED",
    )
    write_validation_run_card(
        validation_root,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="volatility_expansion",
        promotion_status="PAPER_APPROVED",
    )
    governed_base = build_governed_strategy_registry().get("MOMENTUM_CONTINUATION")
    governed_registry = GovernedStrategyRegistry(
        (
            replace(
                governed_base,
                parameter_set_ref=(
                    validation_root
                    / "HOTUSDT"
                    / "1h"
                    / "trend_continuation.run-card.json"
                ).as_posix(),
                dataset_revision=validation_root.as_posix(),
                backtest_ref=(
                    validation_root
                    / "HOTUSDT"
                    / "1h"
                    / "trend_continuation.run-card.json"
                ).as_posix(),
                walk_forward_ref=validation_root.as_posix(),
                oos_ref=validation_root.as_posix(),
                robustness_ref=validation_root.as_posix(),
                paper_ref=validation_root.as_posix(),
                promotion_status=ValidationStatus.PAPER_APPROVED,
            ),
            *(
                item
                for item in build_governed_strategy_registry().strategies
                if item.strategy_id != "MOMENTUM_CONTINUATION"
            ),
        )
    )
    complete = StrategyEngine(
        registry=playbook_registry,
        approval_registry=approval_registry,
        governed_registry=governed_registry,
    ).generate(snapshot(), {**evidence(0.8), **trend_up})[0]

    assert incomplete.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert complete.promotion_status is ValidationStatus.PAPER_APPROVED


def test_strategy_engine_blocks_naked_spot_sell_candidate() -> None:
    candidate = StrategyEngine().generate(
        snapshot(),
        {
            **evidence(-0.8),
            "market_regime": market_regime_result("STRONG_DOWNTREND", vote=-0.8),
        },
    )[0]
    assert candidate.action is Action.SELL
    assert candidate.status is CandidateStatus.RESEARCH_ONLY
    assert "REGIME_ROUTE_SPOT_DEFENSIVE_CASH" in candidate.blockers


def test_deterministic_regime_router_classifies_and_waits_unknown() -> None:
    router = DeterministicRegimeRouter()

    trend_up = router.decide(
        {"market_regime": market_regime_result("WEAK_UPTREND", vote=0.4)}
    )
    transition = router.decide(
        {"market_regime": market_regime_result("UNMAPPED", vote=0.05)}
    )
    unknown = router.decide({})

    assert trend_up.regime is RoutedMarketRegime.TREND_UP
    assert trend_up.allowed_strategy_ids == (
        "TREND_PULLBACK",
        "BREAKOUT_RETEST",
        "MOMENTUM_CONTINUATION",
    )
    assert transition.regime is RoutedMarketRegime.TRANSITION
    assert transition.wait_reason == "REGIME_ROUTE_WAIT_TRANSITION"
    assert unknown.regime is RoutedMarketRegime.UNKNOWN
    assert unknown.wait_reason == "REGIME_ROUTE_WAIT_UNKNOWN"


def test_deterministic_regime_router_covers_remaining_regime_routes() -> None:
    router = DeterministicRegimeRouter()

    range_decision = router.decide(
        {"market_regime": market_regime_result("RANGE", vote=0.0)}
    )
    high_volatility = router.decide(
        {"market_regime": market_regime_result("ABNORMAL_MARKET", vote=-0.4)}
    )
    low_volatility = router.decide(
        {"market_regime": market_regime_result("COMPRESSION", vote=0.0)}
    )
    unusable = router.decide(
        {
            "market_regime": replace(
                market_regime_result("STRONG_UPTREND", vote=0.8),
                status=AgentStatus.FAILED,
            )
        }
    )

    assert range_decision.regime is RoutedMarketRegime.RANGE
    assert range_decision.allowed_strategy_ids == ("MEAN_REVERSION",)
    assert high_volatility.regime is RoutedMarketRegime.HIGH_VOLATILITY
    assert high_volatility.reduced_risk is True
    assert low_volatility.regime is RoutedMarketRegime.LOW_VOLATILITY
    assert low_volatility.wait_reason == "REGIME_ROUTE_WAIT_LOW_VOLATILITY"
    assert unusable.regime is RoutedMarketRegime.UNKNOWN


def test_regime_router_blocks_disallowed_strategy_and_action() -> None:
    router = DeterministicRegimeRouter()
    candidate = approved_candidate()

    strategy_blocked = router.route_candidate(
        snapshot(),
        candidate,
        strategy_id="MEAN_REVERSION",
        decision=router.decide(
            {"market_regime": market_regime_result("STRONG_UPTREND", vote=0.8)}
        ),
    )
    action_blocked = router.route_candidate(
        snapshot(market_type="USD_M_FUTURES"),
        replace(candidate, action=Action.BUY),
        strategy_id="BREAKOUT_RETEST",
        decision=router.decide(
            {"market_regime": market_regime_result("STRONG_DOWNTREND", vote=-0.8)}
        ),
    )

    assert strategy_blocked.status is CandidateStatus.WAIT_FOR_RETEST
    assert strategy_blocked.blockers == ("REGIME_ROUTE_STRATEGY_BLOCKED:TREND_UP",)
    assert action_blocked.status is CandidateStatus.WAIT_FOR_RETEST
    assert action_blocked.blockers == ("REGIME_ROUTE_ACTION_BLOCKED:TREND_DOWN:BUY",)


def test_regime_router_rejects_invalid_metadata_values() -> None:
    router = DeterministicRegimeRouter()
    result = market_regime_result("UNMAPPED", vote=0.1)

    assert (
        router._decimal_metadata(replace(result, calculation_metadata={}), "x") is None
    )
    assert (
        router._decimal_metadata(
            replace(result, calculation_metadata={"atr_ratio": True}),
            "atr_ratio",
        )
        is None
    )
    assert (
        router._decimal_metadata(
            replace(result, calculation_metadata={"atr_ratio": object()}),
            "atr_ratio",
        )
        is None
    )
    assert (
        router._decimal_metadata(
            replace(result, calculation_metadata={"atr_ratio": "bad"}),
            "atr_ratio",
        )
        is None
    )
    assert (
        router._decimal_metadata(
            replace(result, calculation_metadata={"atr_ratio": "-1"}),
            "atr_ratio",
        )
        is None
    )


def test_strategy_engine_allows_futures_short_in_trend_down() -> None:
    candidate = StrategyEngine().generate(
        snapshot(market_type="USD_M_FUTURES"),
        {
            **evidence(-0.8),
            "market_regime": market_regime_result("STRONG_DOWNTREND", vote=-0.8),
        },
    )[0]

    assert candidate.action is Action.SELL
    assert candidate.status is CandidateStatus.READY_FOR_RISK
    assert candidate.blockers == ()
    assert "REGIME_ROUTE:TREND_DOWN" in candidate.evidence


def test_strategy_engine_waits_when_regime_is_unknown() -> None:
    candidate = StrategyEngine().generate(
        snapshot(),
        {
            **evidence(0.8),
            "market_regime": market_regime_result("UNMAPPED", vote=0.3, atr_ratio="0"),
        },
    )[0]

    assert candidate.status is CandidateStatus.WAIT_FOR_RETEST
    assert candidate.blockers == ("REGIME_ROUTE_WAIT_UNKNOWN",)


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


def test_virtual_market_risk_engine_allows_research_only_candidate() -> None:
    candidate = replace(
        approved_candidate(),
        promotion_status=ValidationStatus.RESEARCH_ONLY,
    )
    assessment = RiskEngine().evaluate(
        candidate,
        snapshot(),
        RiskContext(equity_usdt=Decimal("1000")),
        symbol_filters(),
        execution_surface=ExecutionSurface.VIRTUAL_MARKET,
    )

    assert assessment.approved is True
    assert "STRATEGY_NOT_PROMOTED" not in assessment.blockers
    assert assessment.quantity == Decimal("1.000")
    assert assessment.risk_amount_usdt == Decimal("5.000")


def test_risk_assessment_can_be_recovered_from_risk_agent_metadata() -> None:
    result = AgentResult(
        agent_name="risk",
        agent_version="1",
        snapshot_id="strategy-snapshot",
        timestamp=NOW,
        symbol="HOTUSDT",
        timeframes=("1h",),
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=0.0,
        score=100.0,
        confidence=1.0,
        reason_codes=("RISK_APPROVED",),
        calculation_metadata={
            "candidate_id": "candidate-1",
            "approved": True,
            "size_usdt": "100.000",
            "quantity": "1.000",
            "risk_amount_usdt": "5.000",
        },
    )

    assessment = RiskAssessment.from_agent_result(result)

    assert assessment is not None
    assert assessment.approved is True
    assert assessment.candidate_id == "candidate-1"
    assert assessment.quantity == Decimal("1.000")
    assert assessment.size_usdt == Decimal("100.000")
    assert assessment.risk_amount_usdt == Decimal("5.000")


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


def test_risk_config_rejects_non_positive_limits_and_loss_count() -> None:
    with pytest.raises(ValueError, match="risk limits"):
        RiskConfig(max_trade_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="repeated_loss_limit"):
        RiskConfig(repeated_loss_limit=0)
    with pytest.raises(ValueError, match="virtual market risk ratios"):
        VirtualMarketPositionSizingPolicy(risk_per_trade_ratio=Decimal("0"))
    with pytest.raises(ValueError, match="maximum_positions"):
        VirtualMarketPositionSizingPolicy(maximum_positions=0)


def test_risk_context_rejects_invalid_optional_values() -> None:
    with pytest.raises(ValueError, match="daily_loss_usdt"):
        RiskContext(daily_loss_usdt=Decimal("-1"))
    with pytest.raises(ValueError, match="estimated_slippage_ratio"):
        RiskContext(estimated_slippage_ratio=Decimal("-0.01"))
    with pytest.raises(ValueError, match="equity_usdt"):
        RiskContext(equity_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="inventory_quantity"):
        RiskContext(inventory_quantity=Decimal("-1"))
    with pytest.raises(ValueError, match="consecutive_losses"):
        RiskContext(consecutive_losses=-1)
    with pytest.raises(ValueError, match="open_risk_usdt"):
        RiskContext(open_risk_usdt=Decimal("-1"))
    with pytest.raises(ValueError, match="open_position_count"):
        RiskContext(open_position_count=-1)


def test_risk_assessment_rejects_invalid_approved_state() -> None:
    with pytest.raises(ValueError, match="candidate_id"):
        RiskAssessment(" ", approved=False)
    with pytest.raises(ValueError, match="cannot be negative"):
        RiskAssessment("candidate-1", approved=False, size_usdt=Decimal("-1"))
    with pytest.raises(ValueError, match="cannot contain blockers"):
        RiskAssessment("candidate-1", approved=True, blockers=("BLOCKED",))
    with pytest.raises(ValueError, match="must be positive"):
        RiskAssessment("candidate-1", approved=True)


def test_risk_engine_blocks_unknown_equity_and_missing_spread() -> None:
    assessment = RiskEngine().evaluate(
        approved_candidate(),
        replace(snapshot(), spread=None),
        RiskContext(),
        symbol_filters(),
    )

    assert assessment.approved is False
    assert assessment.size_usdt == Decimal("0")
    assert assessment.quantity == Decimal("0")
    assert assessment.risk_amount_usdt == Decimal("0")
    assert assessment.blockers == ("EQUITY_UNKNOWN", "SPREAD_EXCEEDS_LIMIT")


def test_risk_engine_caps_spot_sell_to_inventory() -> None:
    assessment = RiskEngine(
        RiskConfig(
            max_trade_usdt=Decimal("1000"),
            max_open_position_size_usdt=Decimal("1000"),
        )
    ).evaluate(
        replace(
            approved_candidate(),
            action=Action.SELL,
            entry_zone=PriceZone(Decimal("100"), Decimal("100")),
            stop_loss=Decimal("105"),
            invalidation_level=Decimal("105"),
            take_profit_levels=(Decimal("90"),),
            trailing_stop=Decimal("104"),
            inventory_action="SELL",
        ),
        snapshot(),
        RiskContext(equity_usdt=Decimal("1000"), inventory_quantity=Decimal("0.5")),
        symbol_filters(),
    )

    assert assessment.approved is True
    assert assessment.quantity == Decimal("0.500")
    assert assessment.size_usdt == Decimal("50.000")
    assert assessment.risk_amount_usdt == Decimal("2.500")


def test_strategy_engine_uses_no_inventory_action_for_futures_sell() -> None:
    results = {
        **evidence(-0.8),
        "market_regime": market_regime_result("STRONG_DOWNTREND", vote=-0.8),
    }

    candidate = StrategyEngine().generate(
        snapshot(market_type="USD_M_FUTURES"),
        results,
    )[0]

    assert candidate.action is Action.SELL
    assert candidate.status is CandidateStatus.READY_FOR_RISK
    assert candidate.inventory_action == "NONE"
    assert candidate.blockers == ()


def test_virtual_market_sizing_uses_invalidation_before_position_size() -> None:
    candidate = replace(
        approved_candidate(),
        invalidation_level=Decimal("99"),
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("95"),
        take_profit_levels=(Decimal("102"),),
    )
    assessment = RiskEngine(
        RiskConfig(
            max_trade_usdt=Decimal("100"),
            max_open_position_size_usdt=Decimal("1000"),
            max_inventory_allocation_ratio=Decimal("1"),
            virtual_market=VirtualMarketPositionSizingPolicy(
                risk_per_trade_ratio=Decimal("0.005"),
                maximum_open_risk_ratio=Decimal("1"),
                maximum_positions=4,
            ),
        )
    ).evaluate(
        candidate,
        snapshot(),
        RiskContext(equity_usdt=Decimal("1000")),
        symbol_filters(),
    )

    assert assessment.approved is True
    assert assessment.quantity == Decimal("5.000")
    assert assessment.size_usdt == Decimal("500.000")
    assert assessment.risk_amount_usdt == Decimal("5.000")


def test_virtual_market_sizing_blocks_open_risk_and_position_count() -> None:
    assessment = RiskEngine(
        RiskConfig(
            max_open_position_size_usdt=Decimal("1000"),
            max_inventory_allocation_ratio=Decimal("1"),
            virtual_market=VirtualMarketPositionSizingPolicy(
                risk_per_trade_ratio=Decimal("0.005"),
                maximum_open_risk_ratio=Decimal("0.02"),
                maximum_positions=4,
            ),
        )
    ).evaluate(
        approved_candidate(),
        snapshot(),
        RiskContext(
            equity_usdt=Decimal("1000"),
            open_risk_usdt=Decimal("18"),
            open_position_count=4,
        ),
        symbol_filters(),
    )

    assert assessment.approved is False
    assert "MAX_OPEN_POSITIONS_EXCEEDED" in assessment.blockers
    assert "MAX_OPEN_RISK_EXCEEDED" in assessment.blockers


def test_risk_engine_blocks_zero_rounded_quantity_and_allocation_overrun() -> None:
    zero_quantity_filters = SymbolFilters.from_symbol_info(
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
                    "minQty": "1",
                    "maxQty": "1000",
                    "stepSize": "1",
                },
                "MIN_NOTIONAL": {"minNotional": "10"},
            },
        )
    )
    rounded = RiskEngine().evaluate(
        approved_candidate(),
        snapshot(),
        RiskContext(equity_usdt=Decimal("100")),
        zero_quantity_filters,
    )
    assert "ROUNDED_QUANTITY_IS_ZERO" in rounded.blockers
    assert "PRICE_AND_QUANTITY_MUST_BE_POSITIVE" in rounded.blockers

    allocation = RiskEngine().evaluate(
        approved_candidate(),
        snapshot(),
        RiskContext(
            equity_usdt=Decimal("1000"),
            current_exposure_usdt=Decimal("200"),
        ),
        symbol_filters(),
    )
    assert allocation.approved is False
    assert "MAX_INVENTORY_ALLOCATION_EXCEEDED" in allocation.blockers
