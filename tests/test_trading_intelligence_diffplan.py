"""Causal geometry, shared replay, stress-risk, and held-out evidence regressions."""

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest

from ai4binance.cli.futures_multitf import analyze_futures_snapshot
from ai4binance.data.acquisition import LocalMarketSnapshotTransport
from ai4binance.domain import Action
from ai4binance.intelligence.contracts import (
    ConfirmedSwing,
    PatternHypothesisEvidence,
    ScenarioDirection,
    StructuralLevelEvidence,
    StructureState,
    SwingKind,
    TimeframeStructureEvidence,
)
from ai4binance.intelligence.levels import StructuralLevelMapEngine
from ai4binance.intelligence.patterns import (
    ElliottWaveHypothesisEngine,
    FibonacciConfluenceEngine,
    HarmonicPatternEngine,
)
from ai4binance.intelligence.plan import TradePlanEngine
from ai4binance.intelligence.trading import ScenarioEngine
from ai4binance.intelligence.trend import TrendGeometryEngine
from ai4binance.opportunity_intelligence import (
    ChartPatternLifecycleState,
    detect_chart_pattern,
)
from ai4binance.research.virtual_market import VirtualMarket
from ai4binance.research.virtual_runtime import (
    VirtualMarketRuntime,
    VirtualPortfolioState,
    VirtualPositionSide,
)
from ai4binance.research.virtual_runtime_risk import (
    FuturesLeverageGovernor,
    FuturesRiskBracket,
)
from ai4binance.research_runtime import build_research_application_service
from ai4binance.risk import RiskContext, RiskEngine
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.validation.overfit import (
    OosProbabilityObservation,
    assess_oos_probabilities,
    paired_ablation_delta,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)
from tests.test_historical_replay_runner import START
from tests.test_historical_replay_runner import _snapshot as replay_snapshot
from tests.test_strategy_risk import symbol_filters
from tests.test_technical_agents import NOW, technical_snapshot
from tests.test_trading_intelligence import (
    _candidate,
    _costed_snapshot,
    _evidence_results,
    _result,
)
from tests.test_virtual_runtime import approved_virtual_runtime_request

D = Decimal


def structure(
    prices: tuple[str, ...], *, high_first: bool = False
) -> TimeframeStructureEvidence:
    swings = tuple(
        ConfirmedSwing(
            "1h",
            SwingKind.HIGH if (i % 2 == 0) == high_first else SwingKind.LOW,
            15 + i * 3,
            NOW - timedelta(hours=25 - i * 3),
            NOW - timedelta(hours=22 - i * 3),
            D(price),
            "PIVOT",
            D("1"),
        )
        for i, price in enumerate(prices)
    )
    return TimeframeStructureEvidence(
        "1h",
        StructureState.RANGE,
        "CONFIRMED_SWING_GRAPH",
        min(s.price for s in swings),
        max(s.price for s in swings),
        None,
        0.7,
        swings,
    )


@pytest.mark.parametrize(
    ("prices", "family"),
    [
        (("100", "200", "138.2", "177.64", "121.4"), "GARTLEY"),
        (("100", "200", "150", "180", "111.4"), "BAT"),
    ],
)
def test_harmonic_checks_full_xabcd_and_mirrored_geometry(
    prices: tuple[str, ...], family: str
) -> None:
    for mirrored in (False, True):
        values = tuple(str(D("400") - D(p)) for p in prices) if mirrored else prices
        detected = HarmonicPatternEngine.detect(structure(values, high_first=mirrored))
        assert detected is not None
        assert detected["pattern_family"] == family
        assert detected["directional_vote"] == (-1 if mirrored else 1)
        evidence = PatternHypothesisEvidence(
            "test",
            "HARMONIC_PATTERN",
            ScenarioDirection.LONG,
            "POTENTIAL",
            0.5,
            ("CONFIRMED_SWING_GRAPH",),
            attributes=tuple((k, str(v)) for k, v in detected.items()),
        )
        assert HarmonicPatternEngine().build(evidence).lifecycle_state == "POTENTIAL"
        corrupted = replace(
            evidence,
            attributes=tuple(
                (k, "NaN" if k == "xa_ab" else v) for k, v in evidence.attributes
            ),
        )
        assert HarmonicPatternEngine().build(corrupted).lifecycle_state == "INVALIDATED"


def test_harmonic_label_cannot_replace_missing_ratios() -> None:
    evidence = PatternHypothesisEvidence(
        "test",
        "HARMONIC_PATTERN",
        ScenarioDirection.LONG,
        "POTENTIAL",
        0.5,
        ("TEST",),
        attributes=(("method", "CONFIRMED_XABCD"), ("pattern_family", "BAT")),
    )
    result = HarmonicPatternEngine().build(evidence)
    assert result.lifecycle_state == "INVALIDATED"
    assert result.direction is ScenarioDirection.NEUTRAL


def test_fibonacci_uses_observed_leg_and_elliott_rejects_overlap() -> None:
    evidence = structure(("100", "110", "105", "125", "115", "135"))
    fib = FibonacciConfluenceEngine.detect(evidence)
    assert fib is not None
    assert D(str(fib["retracement_618"])) == D("122.640")
    assert ElliottWaveHypothesisEngine.detect(evidence) is not None
    assert (
        ElliottWaveHypothesisEngine.detect(
            structure(("100", "110", "105", "125", "109", "135"))
        )
        is None
    )
    # Wave three is shorter than both waves one and five.
    assert (
        ElliottWaveHypothesisEngine.detect(
            structure(("100", "120", "115", "130", "125", "150"))
        )
        is None
    )


def test_level_statistics_never_count_contact_before_confirmation() -> None:
    snapshot = technical_snapshot()
    candles = tuple(snapshot.ohlcv_by_timeframe["1h"])
    level = StructuralLevelMapEngine()._level(
        snapshot,
        "1h",
        "support",
        candles[-1].close,
        D(".1"),
        candles,
        0.7,
        None,
        "anchor",
        snapshot.created_at,
    )
    assert level.touch_count == level.break_count == 0
    assert level.rejection_strength == 0
    assert level.volume_context == "NO_TOUCH"


def test_trend_anchors_do_not_move_when_a_later_break_is_observed() -> None:
    evidence = structure(("100", "110", "101", "111"))
    rows = tuple(
        OHLCVCandle(
            NOW - timedelta(hours=40 - i),
            D("105"),
            D("106"),
            D("104"),
            D("105"),
            D("100"),
        )
        for i in range(40)
    )
    snapshot = replace(
        technical_snapshot(), ohlcv_by_timeframe={"1h": rows}, timeframes=("1h",)
    )
    initial = TrendGeometryEngine().build(
        snapshot, (evidence,), _result("trend_channel")
    )
    changed = replace(rows[-1], low=D("89"), close=D("90"))
    broken = TrendGeometryEngine().build(
        replace(snapshot, ohlcv_by_timeframe={"1h": (*rows[:-1], changed)}),
        (evidence,),
        _result("trend_channel"),
    )
    first_support = next(g for g in initial if g.method == "CONFIRMED_PIVOT_SUPPORT")
    broken_support = next(g for g in broken if g.method == "CONFIRMED_PIVOT_SUPPORT")
    assert first_support.geometry_id == broken_support.geometry_id
    assert first_support.anchor_points == broken_support.anchor_points
    assert first_support.channel_width == broken_support.channel_width
    assert broken_support.break_state == "BROKEN"


@pytest.mark.parametrize("short", [False, True])
def test_structural_plan_uses_real_targets_and_conservative_tick_rounding(
    short: bool,
) -> None:
    snapshot = replace(
        _costed_snapshot(),
        market_type="USD_M_FUTURES",
        exchange_filters={"PRICE_FILTER": {"tickSize": ".01"}},
    )
    state = ScenarioEngine().build(_costed_snapshot(), _evidence_results())
    scenario = state.selected_scenario
    assert scenario is not None
    scenario = replace(scenario, invalidation_level=D("1.253") if short else D(".967"))
    level = StructuralLevelEvidence(
        "observed-zone",
        "SUPPORT" if short else "RESISTANCE",
        D(".877") if short else D("1.337"),
        D(".887") if short else D("1.347"),
        "1h",
        2,
        0,
        "FRESH",
        False,
        0.8,
        "CONFIRMED_SWING_GRAPH",
    )
    candidate = replace(_candidate(), market_type="USD_M_FUTURES")
    if short:
        candidate = replace(
            candidate,
            action=Action.SELL,
            stop_loss=D("1.3"),
            invalidation_level=D("1.3"),
            take_profit_levels=(D(".9"),),
        )
    state = replace(state, market_type="USD_M_FUTURES", levels=(level,))
    result = TradePlanEngine().structural_candidate(
        candidate, scenario, state, snapshot
    )
    assert result.take_profit_levels == (D(".89") if short else D("1.33"),)
    assert result.stop_loss == (D("1.25") if short else D(".97"))
    assert result.invalidation_level == scenario.invalidation_level
    assert result.target_sources == ("observed-zone",)
    missing = TradePlanEngine().structural_candidate(
        candidate, scenario, replace(state, levels=()), snapshot
    )
    assert "STRUCTURAL_PLAN_TARGET_UNAVAILABLE" in missing.blockers
    unticked = TradePlanEngine().structural_candidate(
        candidate, scenario, state, replace(snapshot, exchange_filters={})
    )
    assert "STRUCTURAL_PLAN_TICK_SIZE_UNAVAILABLE" in unticked.blockers


def test_historical_execution_settings_do_not_overwrite_market_evidence() -> None:
    event = replay_snapshot(
        START,
        snapshot_id="replay-parity",
        market=VirtualMarket.USD_M_FUTURES,
        execution_context=True,
    )
    assert not event.pipeline_snapshot.derivatives_snapshot
    with pytest.raises(ValueError, match="separately governed"):
        replace(
            event,
            snapshot=replace(
                event.snapshot, derivatives_snapshot={"mark_price": "100"}
            ),
        )
    candles = event.snapshot.ohlcv_by_timeframe["1h"]
    candles = (
        *candles,
        replace(candles[-1], timestamp=START),
        replace(candles[-1], timestamp=START + timedelta(hours=1)),
    )
    source = "BINANCE_USD_M_PUBLIC_REST"
    provenance = Provenance(
        source, START + timedelta(hours=2), "https://fapi.binance.com"
    )
    dataset = RuntimeFuturesReplayDataset(
        event.symbol,
        candles,
        DerivativesDataset(
            event.symbol,
            START + timedelta(hours=2),
            {
                metric: tuple(
                    MetricPoint(
                        metric,
                        c.timestamp,
                        D(value) if c.timestamp < START else D("999999"),
                        provenance,
                    )
                    for c in candles
                )
                for metric, value in (
                    (DerivativesMetric.OPEN_INTEREST, "10000"),
                    (DerivativesMetric.MARK_PRICE, "100"),
                    (DerivativesMetric.INDEX_PRICE, "100"),
                    (DerivativesMetric.FUNDING_RATE, ".001"),
                )
            },
        ),
    )
    binding = replace(event.dataset_bindings[0], dataset_sha256=dataset.dataset_sha256)
    assert event.execution_context is not None
    event = replace(
        event,
        dataset_bindings=(binding,),
        historical_derivatives=dataset,
        execution_context=replace(
            event.execution_context, dataset_sha256=dataset.dataset_sha256
        ),
    )
    assert event.pipeline_snapshot.derivatives_snapshot["open_interest"] == "10000"
    assert event.pipeline_snapshot.derivatives_snapshot["mark_price"] == "100"
    assert "historical_virtual_execution" in event.pipeline_snapshot.market_metadata
    # Compare actual default research and observation owners on identical input.
    snapshot = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    observed = analyze_futures_snapshot(snapshot)
    replayed = build_research_application_service().orchestrator.analyze(snapshot)
    assert observed.trading_intelligence == replayed.trading_intelligence
    assert observed.candidate_setups == replayed.candidate_setups


def test_chart_breakout_failure_is_terminal_for_same_confirmed_anchors() -> None:
    evidence = structure(("100", "110", "100.1"))
    rows = tuple(
        OHLCVCandle(
            NOW - timedelta(hours=40 - i),
            D("105"),
            D("106"),
            D("104"),
            D("105"),
            D("100"),
        )
        for i in range(40)
    )
    # The last pivot is available at NOW - 16h. Trigger then return inside.
    rows = (*rows[:25], replace(rows[25], high=D("112"), close=D("111")), *rows[26:])
    first = detect_chart_pattern(
        rows[:26],
        timeframe="1h",
        snapshot_id="first",
        decision_time=rows[25].timestamp + timedelta(hours=1),
        structure=evidence,
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
    )
    failed = detect_chart_pattern(
        rows,
        timeframe="1h",
        snapshot_id="second",
        decision_time=NOW,
        structure=evidence,
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
    )
    assert first is not None
    assert failed is not None
    assert first.state is ChartPatternLifecycleState.CONFIRMED
    assert failed.state is ChartPatternLifecycleState.FAILED
    assert first.pattern_id == failed.pattern_id
    assert first.observation_id != failed.observation_id


@pytest.mark.parametrize(
    ("prices", "high_first", "family"),
    [
        (("110", "100", "120", "100.2", "110.1"), True, "HEAD_AND_SHOULDERS"),
        (("100", "110", "90", "110.2", "100.1"), False, "INVERSE_HEAD_AND_SHOULDERS"),
        (("110", "100", "108", "102"), True, "CONVERGING_TRIANGLE"),
        (("110", "100", "114", "107"), True, "RISING_WEDGE"),
        (("110", "100", "103", "96"), True, "FALLING_WEDGE"),
    ],
)
def test_confirmed_chart_families(
    prices: tuple[str, ...],
    high_first: bool,
    family: str,
) -> None:
    evidence = structure(prices, high_first=high_first)
    rows = tuple(
        OHLCVCandle(
            NOW - timedelta(hours=40 - i),
            D("105"),
            D("106"),
            D("104"),
            D("105"),
            D("100"),
        )
        for i in range(40)
    )
    pattern = detect_chart_pattern(
        rows,
        timeframe="1h",
        snapshot_id="families",
        decision_time=NOW,
        structure=evidence,
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
    )
    assert pattern is not None
    assert pattern.pattern_type == family


def test_invalid_maintenance_deduction_cannot_remove_the_margin_requirement() -> None:
    with pytest.raises(ValueError, match="maintenance"):
        FuturesRiskBracket(D("0"), D("1000"), 5, D(".005"), D("100"))


class RiskInputs(TypedDict):
    entry: Decimal
    stop: Decimal
    quantity: Decimal
    mark_price: Decimal
    available_margin: Decimal
    risk_budget: Decimal
    round_trip_cost_ratio: Decimal
    adverse_funding_ratio: Decimal
    mark_stress_ratio: Decimal
    brackets: tuple[FuturesRiskBracket, ...]
    strategy_oos_approved: bool
    upstream_blockers: NotRequired[tuple[str, ...]]


def risk_inputs() -> RiskInputs:
    return {
        "entry": D("100"),
        "stop": D("95"),
        "quantity": D("1"),
        "mark_price": D("100"),
        "available_margin": D("50"),
        "risk_budget": D("10"),
        "round_trip_cost_ratio": D(".002"),
        "adverse_funding_ratio": D(".001"),
        "mark_stress_ratio": D(".01"),
        "brackets": (FuturesRiskBracket(D("0"), D("1000"), 10, D(".005"), D("0")),),
        "strategy_oos_approved": True,
    }


def test_structural_leverage_is_minimal_and_never_execution_authority() -> None:
    for stop in (D("95"), D("105")):
        result = FuturesLeverageGovernor().assess_structural_leverage(
            **cast(RiskInputs, {**risk_inputs(), "stop": stop})
        )
        assert result.permitted_leverage == 2
        assert result.initial_margin == D("50")
        assert not result.blockers
        assert not result.execution_allowed


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    [
        ({"brackets": ()}, "FUTURES_RISK_BRACKETS_UNAVAILABLE_OR_INCONSISTENT"),
        ({"strategy_oos_approved": False}, "SIMULATED_LEVERAGE_OOS_APPROVAL_MISSING"),
        ({"risk_budget": D("1")}, "FUTURES_STRESSED_RISK_BUDGET_EXCEEDED"),
        ({"available_margin": D("1")}, "SIMULATED_LEVERAGE_FEASIBILITY_EXCEEDED"),
        ({"mark_price": D("NaN")}, "STRUCTURAL_LEVERAGE_NONFINITE_INPUT"),
        (
            {"available_margin": D("20"), "stop": D("80"), "risk_budget": D("30")},
            "FUTURES_LIQUIDATION_BEFORE_STRESSED_STOP",
        ),
        ({"upstream_blockers": ("RISK_VETO",)}, "RISK_VETO"),
    ],
)
def test_structural_leverage_vetoes(overrides: dict[str, object], blocker: str) -> None:
    result = FuturesLeverageGovernor().assess_structural_leverage(
        **cast(RiskInputs, {**risk_inputs(), **overrides})
    )
    assert result.permitted_leverage is None
    assert blocker in result.blockers


@pytest.mark.parametrize(
    "brackets",
    [
        (FuturesRiskBracket(D("1"), D("1000"), 10, D(".005"), D("0")),),
        (
            FuturesRiskBracket(D("0"), D("90"), 10, D(".005"), D("0")),
            FuturesRiskBracket(D("90"), D("1000"), 5, D(".01"), D(".9")),
        ),
        (
            FuturesRiskBracket(D("0"), D("90"), 5, D(".005"), D("0")),
            FuturesRiskBracket(D("90"), D("1000"), 10, D(".01"), D(".45")),
        ),
    ],
    ids=["missing-zero-floor", "maintenance-discontinuity", "increasing-leverage"],
)
def test_structural_leverage_rejects_invalid_bracket_schedule(
    brackets: tuple[FuturesRiskBracket, ...],
) -> None:
    result = FuturesLeverageGovernor().assess_structural_leverage(
        **cast(RiskInputs, {**risk_inputs(), "brackets": brackets})
    )
    assert result.permitted_leverage is None
    assert result.initial_margin is None
    assert result.blockers == ("FUTURES_RISK_BRACKETS_UNAVAILABLE_OR_INCONSISTENT",)
    assert not result.execution_allowed
    blockers = FuturesLeverageGovernor().structural_margin_blockers(
        context={
            "snapshot_id": "snapshot:test-invalid-brackets",
            "symbol": "BTCUSDT",
            "margin_mode": "ISOLATED",
            "strategy_oos_approved": True,
            "adverse_funding_ratio": ".001",
            "mark_stress_ratio": ".01",
            "brackets": [
                {
                    "notionalFloor": str(tier.notional_floor),
                    "notionalCap": str(tier.notional_cap),
                    "initialLeverage": tier.initial_leverage,
                    "maintMarginRatio": str(tier.maintenance_ratio),
                    "cum": str(tier.cumulative_maintenance),
                }
                for tier in brackets
            ],
        },
        requested_leverage=2,
        snapshot_id="snapshot:test-invalid-brackets",
        symbol="BTCUSDT",
        entry=D("100"),
        stop=D("95"),
        quantity=D("1"),
        mark_price=D("100"),
        available_margin=D("50"),
        round_trip_cost_ratio=D(".002"),
        risk_budget=D("10"),
    )
    assert blockers == result.blockers


def test_structural_leverage_accepts_continuous_maintenance_schedule() -> None:
    brackets = (
        FuturesRiskBracket(D("0"), D("90"), 10, D(".005"), D("0")),
        FuturesRiskBracket(D("90"), D("1000"), 5, D(".01"), D(".45")),
    )
    result = FuturesLeverageGovernor().assess_structural_leverage(
        **cast(RiskInputs, {**risk_inputs(), "brackets": brackets})
    )
    assert result.permitted_leverage == 2
    assert result.initial_margin == D("50")
    assert result.margin_surplus_at_stressed_stop == D("43.21")
    assert not result.blockers
    assert not result.execution_allowed


def test_virtual_structural_plan_requires_bound_margin_proof() -> None:
    request = approved_virtual_runtime_request(
        snapshot_id="snapshot:structural",
        decision_id="dge:structural",
        candidate_id="candidate:structural",
        symbol="BTCUSDT",
        market="USD_M_FUTURES",
        action=Action.BUY,
        quantity=D("1"),
        entry_price=D("100"),
        stop_loss=D("95"),
        take_profit_levels=(D("110"),),
        position_side=VirtualPositionSide.LONG,
        mark_price=D("100"),
        funding_rate=D("0"),
        leverage=2,
        isolated_margin_usdt=D("50"),
        maintenance_margin_ratio=D(".005"),
        require_structural_margin_proof=True,
        structural_risk_budget_usdt=D("10"),
        portfolio=VirtualPortfolioState(
            "virtual:structural", "USD_M_FUTURES", D("1000"), D("1000")
        ),
    )
    runtime = VirtualMarketRuntime()
    missing = runtime.evaluate(request)
    assert missing.trade_intent is None
    assert "STRUCTURAL_MARGIN_EVIDENCE_UNAVAILABLE" in missing.eligibility.blockers
    context = {
        "snapshot_id": request.snapshot_id,
        "symbol": request.symbol,
        "margin_mode": "ISOLATED",
        "strategy_oos_approved": True,
        "adverse_funding_ratio": ".001",
        "mark_stress_ratio": ".01",
        "brackets": [
            {
                "notionalFloor": "0",
                "notionalCap": "1000",
                "initialLeverage": 5,
                "maintMarginRatio": ".005",
                "cum": "0",
            }
        ],
    }
    valid = runtime.evaluate(replace(request, structural_margin_context=context))
    assert valid.trade_intent is not None
    foreign = runtime.evaluate(
        replace(
            request, structural_margin_context={**context, "snapshot_id": "foreign"}
        )
    )
    assert foreign.trade_intent is None
    assert "STRUCTURAL_MARGIN_IDENTITY_OR_MODE_INVALID" in foreign.eligibility.blockers
    excess = runtime.evaluate(
        replace(request, structural_margin_context=context, leverage=5)
    )
    assert excess.trade_intent is None
    assert "FUTURES_LEVERAGE_NOT_MINIMUM_FEASIBLE" in excess.eligibility.blockers


def test_structural_sizing_uses_the_same_stress_budget_before_leverage() -> None:
    candidate = replace(
        _candidate(), market_type="USD_M_FUTURES", evidence=("STRUCTURAL_PLAN_V2",)
    )
    snapshot = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    context = RiskContext(equity_usdt=D("1000"))
    missing = RiskEngine().evaluate(candidate, snapshot, context, symbol_filters())
    assert missing.quantity == 0
    assert "STRUCTURAL_RISK_SIZING_EVIDENCE_UNAVAILABLE" in missing.blockers
    metadata = {
        "mark_price": str(candidate.entry_price),
        "fee_ratio": ".001",
        "slippage_ratio": "0",
        "half_spread_ratio": "0",
        "liquidation_fee_ratio": ".005",
        "structural_margin_context": {
            "snapshot_id": snapshot.snapshot_id,
            "symbol": snapshot.symbol,
            "margin_mode": "ISOLATED",
            "adverse_funding_ratio": ".001",
            "mark_stress_ratio": ".01",
        },
    }
    snapshot = replace(snapshot, derivatives_snapshot=metadata)
    stressed = RiskEngine().evaluate(candidate, snapshot, context, symbol_filters())
    ordinary = RiskEngine().evaluate(
        replace(candidate, evidence=()), snapshot, context, symbol_filters()
    )
    assert 0 < stressed.quantity < ordinary.quantity
    assert context.equity_usdt is not None
    assert (
        stressed.risk_amount_usdt
        <= context.equity_usdt * RiskEngine().config.virtual_market.risk_per_trade_ratio
    )


def observation(identity: str, p: float, won: bool) -> OosProbabilityObservation:
    return OosProbabilityObservation(
        identity,
        "baseline",
        "fold-1",
        "TREND",
        NOW - timedelta(days=2),
        NOW - timedelta(days=1),
        NOW,
        NOW + timedelta(days=1),
        p,
        won,
        2.0 if won else -1.0,
    )


def test_oos_metrics_and_paired_ablation_do_not_promote() -> None:
    rows = (observation("a", 0.8, True), observation("b", 0.2, False))
    metrics = assess_oos_probabilities(rows, minimum_observations=100)
    assert metrics.brier_score == pytest.approx(0.04)
    assert metrics.expected_calibration_error == pytest.approx(0.2)
    assert metrics.sample_size == 2
    assert not metrics.execution_allowed
    assert metrics.blockers == ("OOS_PROBABILITY_SAMPLE_INSUFFICIENT",)
    challenger = tuple(
        replace(o, model_id="challenger", probability=1.0 if o.target_first else 0.0)
        for o in rows
    )
    delta_r, delta_brier, n = paired_ablation_delta(rows, challenger)
    assert delta_r == 0
    assert delta_brier == pytest.approx(-0.04)
    assert n == 2
    with pytest.raises(ValueError, match="cohorts"):
        paired_ablation_delta(rows, challenger[:1])
    with pytest.raises(ValueError, match="unique"):
        assess_oos_probabilities((rows[0], rows[0]), minimum_observations=1)
    with pytest.raises(ValueError, match="leakage"):
        replace(rows[0], trained_through=NOW)


def write_local_sources(tmp_path: Path) -> LocalMarketSnapshotTransport:
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    stamp = int(NOW.timestamp() * 1000)
    sources: dict[str, dict[str, object]] = {
        "premiumIndex.json": {
            "source": "/fapi/v1/premiumIndex",
            "rows": [
                {
                    "symbol": "HOTUSDT",
                    "time": stamp,
                    "markPrice": "1.1",
                    "indexPrice": "1.1",
                    "lastFundingRate": ".001",
                }
            ],
        },
        "ticker-bookTicker.json": {
            "source": "/fapi/v1/ticker/bookTicker",
            "rows": [
                {
                    "symbol": "HOTUSDT",
                    "time": stamp,
                    "bidPrice": "1.09",
                    "askPrice": "1.11",
                }
            ],
        },
        "exchange-info.json": {
            "source": "/fapi/v1/exchangeInfo",
            "payload": {
                "symbols": [
                    {
                        "symbol": "HOTUSDT",
                        "baseAsset": "HOT",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                        "filters": [
                            {
                                "filterType": "PRICE_FILTER",
                                "minPrice": ".01",
                                "maxPrice": "10000",
                                "tickSize": ".01",
                            },
                            {
                                "filterType": "LOT_SIZE",
                                "minQty": "1",
                                "maxQty": "100000",
                                "stepSize": "1",
                            },
                            {
                                "filterType": "MARKET_LOT_SIZE",
                                "minQty": "1",
                                "maxQty": "10000",
                                "stepSize": "1",
                            },
                            {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        ],
                    }
                ]
            },
        },
    }
    for filename, payload in sources.items():
        (metadata / filename).write_text(
            json.dumps({"observed_at": NOW.isoformat(), **payload})
        )
    oi = tmp_path / "HOTUSDT" / "details" / "open_interest"
    oi.mkdir(parents=True)
    (oi / "1.json").write_text(
        json.dumps(
            {
                "source": "/futures/data/openInterestHist",
                "rows": [
                    {"symbol": "HOTUSDT", "timestamp": stamp, "sumOpenInterest": "1000"}
                ],
            }
        )
    )
    return LocalMarketSnapshotTransport(metadata, clock=lambda: NOW)


@pytest.mark.parametrize(
    "source", [None, "/api/v3/exchangeInfo", "/dapi/v1/exchangeInfo"]
)
def test_futures_listing_requires_exact_receipt_source(
    tmp_path: Path, source: str | None
) -> None:
    """Test-only legacy and wrong-market receipts cannot establish Futures identity."""
    transport = write_local_sources(tmp_path)
    path = transport.directory / "exchange-info.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if source is None:
        payload.pop("source")
    else:
        payload["source"] = source
    path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    failure = blocked.market_metadata["futures_liquidity_failure"]
    assert isinstance(failure, Mapping)
    assert failure["reason_code"] == "LOCAL_MARKET_SNAPSHOT_SOURCE_INVALID"
    assert failure["source_filename"] == "exchange-info.json"
    assert not blocked.exchange_filters
    assert blocked.bid is None
    assert blocked.ask is None
    assert "trading_status" not in blocked.market_metadata


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baseAsset", "BTC"),
        ("quoteAsset", "BTC"),
        ("marginAsset", "BTC"),
        ("contractType", "CURRENT_QUARTER"),
        ("contractType", None),
    ],
)
def test_futures_listing_rejects_conflicting_contract_identity(
    tmp_path: Path, field: str, value: str | None
) -> None:
    """Test-only contract fields must agree with the perpetual symbol identity."""
    transport = write_local_sources(tmp_path)
    path = transport.directory / "exchange-info.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["payload"]["symbols"][0][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    failure = blocked.market_metadata["futures_liquidity_failure"]
    assert isinstance(failure, Mapping)
    assert failure["reason_code"] == "FUTURES_LIQUIDITY_LISTING_IDENTITY_INVALID"
    assert not blocked.exchange_filters
    assert blocked.spread is None


@pytest.mark.parametrize(
    "failure",
    [
        "missing_price",
        "missing_lot",
        "missing_market_lot",
        "missing_notional",
        "duplicate",
        "malformed",
        "nonnumeric",
        "nan",
        "infinite",
        "boolean",
        "negative",
        "inverted_price",
        "inverted_lot",
        "zero_lot_step",
        "zero_market_step",
        "missing_field",
        "spot_notional",
    ],
)
def test_futures_listing_rejects_incomplete_or_invalid_filters(
    tmp_path: Path, failure: str
) -> None:
    """Test-only filter mutations retain the source veto without unsafe defaults."""
    transport = write_local_sources(tmp_path)
    path = transport.directory / "exchange-info.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    listing = payload["payload"]["symbols"][0]
    filters = listing["filters"]
    if failure.startswith("missing_") and failure != "missing_field":
        index = {
            "missing_price": 0,
            "missing_lot": 1,
            "missing_market_lot": 2,
            "missing_notional": 3,
        }[failure]
        filters.pop(index)
    elif failure == "duplicate":
        filters.append(dict(filters[0]))
    elif failure == "malformed":
        listing["filters"] = {"PRICE_FILTER": filters[0]}
    elif failure == "missing_field":
        filters[0].pop("tickSize")
    elif failure == "spot_notional":
        filters[3] = {"filterType": "MIN_NOTIONAL", "minNotional": "5"}
    elif failure == "inverted_price":
        filters[0]["minPrice"] = "20000"
    elif failure == "inverted_lot":
        filters[1]["minQty"] = "200000"
    elif failure in {"zero_lot_step", "zero_market_step"}:
        filters[1 if failure == "zero_lot_step" else 2]["stepSize"] = "0"
    else:
        filters[0]["tickSize"] = {
            "nonnumeric": "invalid",
            "nan": "NaN",
            "infinite": "Infinity",
            "boolean": True,
            "negative": "-1",
        }[failure]
    path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    failure_details = blocked.market_metadata["futures_liquidity_failure"]
    assert isinstance(failure_details, Mapping)
    assert failure_details["reason_code"] == "FUTURES_LIQUIDITY_FILTERS_INVALID"
    assert failure_details["source_filename"] == "exchange-info.json"
    assert not blocked.exchange_filters
    assert blocked.spread is None


@pytest.mark.parametrize(
    ("filter_type", "field", "value"),
    [
        ("LOT_SIZE", "minQty", "NaN"),
        ("LOT_SIZE", "stepSize", True),
        ("MARKET_LOT_SIZE", "maxQty", "-1"),
        ("MARKET_LOT_SIZE", "stepSize", "Infinity"),
        ("MIN_NOTIONAL", "notional", "-5"),
        ("MIN_NOTIONAL", "notional", "NaN"),
        ("MIN_NOTIONAL", "notional", None),
    ],
)
def test_futures_filter_validation_covers_quantity_and_notional_values(
    tmp_path: Path, filter_type: str, field: str, value: object
) -> None:
    """Test-only non-price constraints receive the same fail-closed validation."""
    transport = write_local_sources(tmp_path)
    path = transport.directory / "exchange-info.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload["payload"]["symbols"][0]["filters"]:
        if item["filterType"] == filter_type:
            item[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    failure = blocked.market_metadata["futures_liquidity_failure"]
    assert isinstance(failure, Mapping)
    assert failure["reason_code"] == "FUTURES_LIQUIDITY_FILTERS_INVALID"
    assert not blocked.exchange_filters


def test_futures_listing_recovers_only_after_verified_receipt_replacement(
    tmp_path: Path,
) -> None:
    """Test-only source migration restores liquidity without granting authority."""
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate

    transport = write_local_sources(tmp_path)
    book_path = transport.directory / "ticker-bookTicker.json"
    book = json.loads(book_path.read_text(encoding="utf-8"))
    book["rows"][0].update(bidPrice="1.099", askPrice="1.101")
    book_path.write_text(json.dumps(book), encoding="utf-8")
    path = transport.directory / "exchange-info.json"
    valid = json.loads(path.read_text(encoding="utf-8"))
    legacy = dict(valid)
    legacy.pop("source")
    path.write_text(json.dumps(legacy), encoding="utf-8")
    original = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    original = replace(
        original,
        market_metadata={
            **original.market_metadata,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    blocked = transport.attach_futures_context(original)
    assert not blocked.exchange_filters
    path.write_text(json.dumps(valid), encoding="utf-8")
    recovered = transport.attach_futures_context(blocked)
    assert "futures_liquidity_failure" not in recovered.market_metadata
    assert "futures_liquidity_blockers" not in recovered.market_metadata
    notional_filter = recovered.exchange_filters["MIN_NOTIONAL"]
    assert isinstance(notional_filter, Mapping)
    assert notional_filter["notional"] == "5"
    gate = UniverseLiquidityGate(build_default_registry().get("universe_liquidity"))
    result = gate.evaluate_snapshot(recovered)
    assert result.status.value == "SUCCESS"
    assert result.hard_gate_eligible is False
    assert recovered.market_metadata["execution_allowed"] is False
    assert recovered.market_metadata["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_futures_filter_validation_preserves_exchange_disabled_price_rules(
    tmp_path: Path,
) -> None:
    """Test-only exchange zero rules stay valid and unrelated filters stay intact."""
    transport = write_local_sources(tmp_path)
    path = transport.directory / "exchange-info.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    filters = payload["payload"]["symbols"][0]["filters"]
    filters[0].update(minPrice="0", maxPrice="0", tickSize="0")
    filters.append({"filterType": "PERCENT_PRICE", "multiplierUp": "1.15"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    enriched = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    price_filter = enriched.exchange_filters["PRICE_FILTER"]
    percent_filter = enriched.exchange_filters["PERCENT_PRICE"]
    assert isinstance(price_filter, Mapping)
    assert isinstance(percent_filter, Mapping)
    assert price_filter["tickSize"] == "0"
    assert percent_filter["multiplierUp"] == "1.15"
    assert "futures_liquidity_failure" not in enriched.market_metadata


def test_local_futures_sources_are_fresh_symbol_bound_and_replay_safe(
    tmp_path: Path,
) -> None:
    transport = write_local_sources(tmp_path)
    snapshot = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    enriched = transport.attach_futures_context(snapshot)
    assert enriched.derivatives_snapshot["open_interest"] == "1000"
    price_filter = enriched.exchange_filters["PRICE_FILTER"]
    assert isinstance(price_filter, Mapping)
    assert price_filter["tickSize"] == ".01"
    with pytest.raises(ValueError, match="historical"):
        transport.attach_futures_context(
            replace(snapshot, created_at=NOW - timedelta(days=1))
        )
    premium = transport.directory / "premiumIndex.json"
    payload = json.loads(premium.read_text())
    payload["rows"][0]["symbol"] = "BTCUSDT"
    premium.write_text(json.dumps(payload))
    assert not transport.attach_futures_context(snapshot).derivatives_snapshot


def test_futures_liquidity_survives_missing_derivatives_and_reaches_gate(
    tmp_path: Path,
) -> None:
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate
    from ai4binance.schemas import AgentStatus

    transport = write_local_sources(tmp_path)
    # Test-only source intentionally lacks current open-interest observations.
    (tmp_path / "HOTUSDT/details/open_interest/1.json").write_text(
        json.dumps({"source": "/futures/data/openInterestHist", "rows": []}),
        encoding="utf-8",
    )
    book_path = transport.directory / "ticker-bookTicker.json"
    payload = json.loads(book_path.read_text(encoding="utf-8"))
    payload["rows"][0].update(bidPrice="1.099", askPrice="1.101")
    book_path.write_text(json.dumps(payload), encoding="utf-8")
    source = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    snapshot = transport.attach_futures_context(source)
    assert snapshot.market_metadata["trading_status"] == "TRADING"
    assert snapshot.exchange_filters["PRICE_FILTER"] is not None
    assert snapshot.spread == D(".002")
    assert not snapshot.derivatives_snapshot
    assert snapshot.market_metadata["futures_context_blockers"] == (
        "FUTURES_OPEN_INTEREST_UNAVAILABLE",
    )
    from ai4binance.agents.data_quality_gate import DataQualityGate

    quality = DataQualityGate(build_default_registry().get("data_quality")).evaluate(
        snapshot
    )
    assert "FUTURES_OPEN_INTEREST_UNAVAILABLE" in quality.blockers
    assert quality.status is AgentStatus.BLOCKED
    gate = UniverseLiquidityGate(build_default_registry().get("universe_liquidity"))
    assert gate.evaluate_snapshot(snapshot).status is AgentStatus.SUCCESS
    assert not gate.evaluate_snapshot(snapshot).hard_gate_eligible
    assert source.bid != snapshot.bid


@pytest.mark.parametrize(
    "failure", ["valid", "blocked", "stale", "future", "wrong_symbol"]
)
def test_current_oi_receipt_blocks_without_discarding_verified_liquidity(
    tmp_path: Path, failure: str
) -> None:
    transport = write_local_sources(tmp_path)
    current = tmp_path / "HOTUSDT/details/open_interest/current.json"
    legacy = json.loads((current.parent / "1.json").read_text())
    payload = {
        **legacy,
        "symbol": "HOTUSDT",
        "status": "CURRENT",
        "observed_at": NOW.isoformat(),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    if failure == "blocked":
        payload.update(status="BLOCKED", rows=[])
    elif failure in {"stale", "future"}:
        offset = timedelta(hours=-1 if failure == "stale" else 1)
        payload["observed_at"] = (NOW + offset).isoformat()
    elif failure == "wrong_symbol":
        payload["symbol"] = "BTCUSDT"
    current.write_text(json.dumps(payload), encoding="utf-8")
    snapshot = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    assert snapshot.market_metadata["trading_status"] == "TRADING"
    assert snapshot.exchange_filters
    assert snapshot.bid is not None
    if failure == "valid":
        assert snapshot.derivatives_snapshot["open_interest"] == "1000"
        assert "futures_context_blockers" not in snapshot.market_metadata
    else:
        assert not snapshot.derivatives_snapshot
        assert snapshot.market_metadata["futures_context_blockers"]


@pytest.mark.parametrize(
    "failure", ["valid", "stale", "future", "gap", "wrong_symbol", "zero"]
)
def test_current_oi_window_uses_freshest_point_without_accepting_invalid_rows(
    tmp_path: Path, failure: str
) -> None:
    transport = write_local_sources(tmp_path)
    current = tmp_path / "HOTUSDT/details/open_interest/current.json"
    rows = [
        {
            "symbol": "HOTUSDT",
            "timestamp": int((NOW - timedelta(minutes=minutes)).timestamp() * 1000),
            "sumOpenInterest": str(1000 + index),
        }
        for index, minutes in enumerate((17, 12, 7, 2))
    ]
    if failure == "stale":
        for row in rows:
            row["timestamp"] = int(str(row["timestamp"])) - 3_600_000
    elif failure == "future":
        rows[-1]["timestamp"] = int((NOW + timedelta(minutes=3)).timestamp() * 1000)
    elif failure == "gap":
        rows[1]["timestamp"] = int(str(rows[1]["timestamp"])) + 60_000
    elif failure == "wrong_symbol":
        rows[0]["symbol"] = "BTCUSDT"
    elif failure == "zero":
        rows[0]["sumOpenInterest"] = "0"
    current.write_text(
        json.dumps(
            {
                "source": "/futures/data/openInterestHist",
                "symbol": "HOTUSDT",
                "status": "CURRENT",
                "observed_at": (NOW - timedelta(minutes=2)).isoformat(),
                "rows": rows,
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    snapshot = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    assert snapshot.market_metadata["trading_status"] == "TRADING"
    assert snapshot.exchange_filters
    assert snapshot.spread is not None
    if failure == "valid":
        assert snapshot.derivatives_snapshot["open_interest"] == "1003"
        assert (
            snapshot.derivatives_snapshot["as_of"]
            == (NOW - timedelta(minutes=2)).isoformat()
        )
        assert "futures_context_blockers" not in snapshot.market_metadata
    else:
        assert not snapshot.derivatives_snapshot
        assert snapshot.market_metadata["futures_context_blockers"]


@pytest.mark.parametrize(
    "failure",
    [
        "stale",
        "wrong_symbol",
        "crossed",
        "filters",
        "wrong_source",
        "stale_book",
        "future_book",
    ],
)
def test_futures_liquidity_invalid_sources_remove_prior_evidence(
    tmp_path: Path,
    failure: str,
) -> None:
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.universe_liquidity_gate import UniverseLiquidityGate
    from ai4binance.schemas import AgentStatus

    transport = write_local_sources(tmp_path)
    source = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    path = transport.directory / (
        "exchange-info.json" if failure == "filters" else "ticker-bookTicker.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if failure == "stale":
        payload["observed_at"] = (NOW - timedelta(days=2)).isoformat()
    elif failure == "wrong_symbol":
        payload["rows"][0]["symbol"] = "BTCUSDT"
    elif failure == "crossed":
        payload["rows"][0]["bidPrice"] = "2"
    elif failure == "wrong_source":
        payload["source"] = "/api/v3/ticker/bookTicker"
    elif failure in {"stale_book", "future_book"}:
        offset = timedelta(days=-2 if failure == "stale_book" else 1)
        payload["rows"][0]["time"] = int((NOW + offset).timestamp() * 1000)
    else:
        payload["payload"]["symbols"][0]["filters"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")
    snapshot = transport.attach_futures_context(source)
    gate = UniverseLiquidityGate(build_default_registry().get("universe_liquidity"))
    assert gate.evaluate_snapshot(snapshot).status is AgentStatus.BLOCKED
    assert snapshot.bid is None
    assert not snapshot.exchange_filters
    assert "trading_status" not in snapshot.market_metadata
    diagnostic = snapshot.market_metadata["futures_liquidity_failure"]
    assert isinstance(diagnostic, Mapping)
    expected_reasons = {
        "stale": "LOCAL_MARKET_SNAPSHOT_STALE",
        "wrong_symbol": "LOCAL_MARKET_SNAPSHOT_SYMBOL_INVALID",
        "crossed": "FUTURES_LIQUIDITY_SPREAD_INVALID",
        "filters": "FUTURES_LIQUIDITY_FILTERS_INVALID",
        "wrong_source": "LOCAL_MARKET_SNAPSHOT_SOURCE_INVALID",
        "stale_book": "FUTURES_LIQUIDITY_BOOK_STALE_OR_FUTURE",
        "future_book": "FUTURES_LIQUIDITY_BOOK_STALE_OR_FUTURE",
    }
    assert diagnostic["reason_code"] == expected_reasons[failure]
    assert diagnostic["source_filename"] == path.name


@pytest.mark.parametrize("filename", ["exchange-info.json", "ticker-bookTicker.json"])
def test_liquidity_failure_retains_sanitized_source_and_veto(
    tmp_path: Path,
    filename: str,
) -> None:
    """Test-only missing receipts retain their origin without stale fallback."""
    from ai4binance.agents.catalog import build_default_registry
    from ai4binance.agents.data_quality_gate import DataQualityGate

    transport = write_local_sources(tmp_path)
    (transport.directory / filename).rename(
        transport.directory / (filename + ".unavailable")
    )
    snapshot = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    failure = snapshot.market_metadata["futures_liquidity_failure"]
    assert isinstance(failure, Mapping)
    assert failure["source_filename"] == filename
    assert failure["reason_code"] == "LOCAL_MARKET_SNAPSHOT_MISSING"
    assert str(tmp_path) not in str(failure)
    assert snapshot.bid is None
    assert snapshot.ask is None
    assert not snapshot.exchange_filters
    quality = DataQualityGate(build_default_registry().get("data_quality")).evaluate(
        snapshot
    )
    assert (
        f"FUTURES_LIQUIDITY_LOCAL_MARKET_SNAPSHOT_MISSING:{filename}"
        in quality.blockers
    )
    assert quality.status.value == "BLOCKED"


def test_receipt_refresh_after_fixed_cutoff_is_identifiable_and_recoverable(
    tmp_path: Path,
) -> None:
    """Test-only refresh race keeps future evidence closed at the old cutoff."""
    transport = write_local_sources(tmp_path)
    path = transport.directory / "ticker-bookTicker.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    refreshed = NOW + timedelta(seconds=1)
    payload["observed_at"] = refreshed.isoformat()
    payload["rows"][0]["time"] = int(refreshed.timestamp() * 1000)
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = replace(technical_snapshot(), market_type="USD_M_FUTURES")
    blocked = transport.attach_futures_context(original)
    failure = blocked.market_metadata["futures_liquidity_failure"]
    assert isinstance(failure, Mapping)
    assert failure["reason_code"] == "LOCAL_MARKET_SNAPSHOT_FUTURE"
    assert failure["observed_at"] == refreshed.isoformat()
    assert failure["cutoff_at"] == NOW.isoformat()
    assert blocked.bid is None
    assert not blocked.exchange_filters
    recovered = replace(transport, clock=lambda: refreshed).attach_futures_context(
        replace(original, created_at=refreshed)
    )
    assert recovered.bid is not None
    assert recovered.exchange_filters
    assert "futures_liquidity_failure" not in recovered.market_metadata
    assert "futures_liquidity_blockers" not in recovered.market_metadata


def test_liquidity_diagnostics_redact_unknown_exception_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test-only exception text must never become public diagnostic evidence."""
    transport = write_local_sources(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> object:
        raise ValueError("test-only-secret-marker")

    monkeypatch.setattr(LocalMarketSnapshotTransport, "get_json", fail)
    snapshot = transport.attach_futures_context(
        replace(technical_snapshot(), market_type="USD_M_FUTURES")
    )
    assert "test-only-secret-marker" not in str(snapshot.market_metadata)
    diagnostic = snapshot.market_metadata["futures_liquidity_failure"]
    assert isinstance(diagnostic, Mapping)
    assert diagnostic["reason_code"] == "FUTURES_LIQUIDITY_PAYLOAD_INVALID"
    assert not snapshot.exchange_filters
