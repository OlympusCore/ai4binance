"""Causal geometry, shared replay, stress-risk, and held-out evidence regressions."""

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest

from ai4binance.application.opportunity_observation import analyze_futures_snapshot
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
            "rows": [
                {
                    "symbol": "HOTUSDT",
                    "time": stamp,
                    "markPrice": "1.1",
                    "indexPrice": "1.1",
                    "lastFundingRate": ".001",
                }
            ]
        },
        "ticker-bookTicker.json": {
            "rows": [{"symbol": "HOTUSDT", "bidPrice": "1.09", "askPrice": "1.11"}]
        },
        "exchange-info.json": {
            "payload": {
                "symbols": [
                    {
                        "symbol": "HOTUSDT",
                        "status": "TRADING",
                        "filters": [{"filterType": "PRICE_FILTER", "tickSize": ".01"}],
                    }
                ]
            }
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
