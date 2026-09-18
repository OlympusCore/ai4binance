"""Directional, funding-aware and liquidation-aware Futures replay tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.research.backtesting import (
    FuturesBacktestConfig,
    FuturesBacktestEngine,
    FuturesBacktestIntent,
    FuturesSignalProvider,
)
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    MissedOpportunityCategory,
    TradeDirection,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation import RuntimeFuturesReplayDataset
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

START = datetime(2026, 9, 1, tzinfo=UTC)
SOURCE_ID = "BINANCE_USD_M_PUBLIC_REST"
SOURCE_URL = "https://fapi.binance.com"
STRATEGY_HASH = "a" * 64


def _candle(
    index: int,
    *,
    open_price: str = "100",
    high: str = "105",
    low: str = "95",
    close: str = "101",
) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=START + timedelta(hours=index),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


def _point(
    metric: DerivativesMetric,
    timestamp: datetime,
    value: str,
) -> MetricPoint:
    return MetricPoint(
        metric=metric,
        timestamp=timestamp,
        value=Decimal(value),
        provenance=Provenance(
            source_id=SOURCE_ID,
            observed_at=START + timedelta(hours=12),
            source_url=SOURCE_URL,
        ),
    )


def _dataset(
    candles: tuple[OHLCVCandle, ...],
    *,
    funding: tuple[tuple[int, str], ...] = ((2, "0.001"),),
) -> RuntimeFuturesReplayDataset:
    series: dict[DerivativesMetric, tuple[MetricPoint, ...]] = {
        DerivativesMetric.OPEN_INTEREST: tuple(
            _point(
                DerivativesMetric.OPEN_INTEREST,
                candle.timestamp,
                str(1000 + index),
            )
            for index, candle in enumerate(candles)
        )
    }
    if funding:
        series[DerivativesMetric.FUNDING_RATE] = tuple(
            _point(
                DerivativesMetric.FUNDING_RATE,
                candles[index].timestamp,
                value,
            )
            for index, value in funding
        )
    return RuntimeFuturesReplayDataset(
        symbol="BTCUSDT",
        candles=candles,
        derivatives=DerivativesDataset(
            symbol="BTCUSDT",
            as_of=START + timedelta(hours=12),
            series=series,
            source=SOURCE_ID,
        ),
    )


def _intent(
    timestamp: datetime,
    direction: TradeDirection,
    *,
    stop_loss: str,
    take_profit: str,
    symbol: str = "BTCUSDT",
) -> FuturesBacktestIntent:
    return FuturesBacktestIntent(
        signal_id=f"signal:{direction.value.lower()}",
        timestamp=timestamp,
        direction=direction,
        stop_loss=Decimal(stop_loss),
        take_profit=Decimal(take_profit),
        strategy_id="RuntimeFuturesAdvisor",
        strategy_version="runtime-futures-advisor-v1",
        strategy_config_hash=STRATEGY_HASH,
        symbol=symbol,
        regime="PRICE_OI_SETUP",
        timeframe="1h",
        snapshot_id="snapshot-1",
        decision_id="decision-1",
    )


def _one_signal_provider(intent: FuturesBacktestIntent) -> FuturesSignalProvider:
    def provider(
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        if len(replay.candles) == 1:
            return intent
        return None

    return provider


def test_futures_config_rejects_unsafe_margin_assumptions() -> None:
    with pytest.raises(ValueError, match="between 1 and 125"):
        FuturesBacktestConfig(leverage=126)
    with pytest.raises(ValueError, match="between 1 and 125"):
        FuturesBacktestConfig(leverage=2.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="below the initial margin ratio"):
        FuturesBacktestConfig(
            leverage=2,
            maintenance_margin_ratio=Decimal("0.5"),
        )
    with pytest.raises(ValueError, match=r"cannot exceed 0\.02"):
        FuturesBacktestConfig(liquidation_fee_ratio=Decimal("0.021"))


def test_futures_engine_requires_funding_history() -> None:
    candles = (_candle(0), _candle(1))
    dataset = _dataset(candles, funding=())

    with pytest.raises(ValueError, match="funding-rate history"):
        FuturesBacktestEngine().run(
            dataset=dataset,
            signal_provider=lambda _replay: None,
        )


@pytest.mark.parametrize(
    ("direction", "stop_loss", "take_profit", "expected_funding_sign"),
    [
        (TradeDirection.LONG, "80", "110", 1),
        (TradeDirection.SHORT, "120", "90", -1),
    ],
)
def test_futures_engine_applies_directional_funding_and_target_pnl(
    direction: TradeDirection,
    stop_loss: str,
    take_profit: str,
    expected_funding_sign: int,
) -> None:
    exit_candle = (
        _candle(2, high="111", low="99", close="109")
        if direction is TradeDirection.LONG
        else _candle(2, high="101", low="89", close="91")
    )
    candles = (
        _candle(0),
        _candle(1, high="104", low="96"),
        exit_candle,
        _candle(3),
    )
    dataset = _dataset(candles)
    intent = _intent(
        candles[0].timestamp,
        direction,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    result = FuturesBacktestEngine().run(
        dataset=dataset,
        signal_provider=_one_signal_provider(intent),
    )

    trade = result.trades[0]
    assert trade.direction is direction
    assert trade.exit_reason is BacktestExitReason.TARGET
    assert trade.funding_cost_usdt * expected_funding_sign > Decimal("0")
    assert trade.net_pnl_usdt == (
        trade.gross_pnl_usdt
        - trade.fee_cost_usdt
        - trade.slippage_cost_usdt
        - trade.funding_cost_usdt
    )
    assert trade.attribution.market == "USD_M_FUTURES"
    assert result.metrics.market == "USD_M_FUTURES"
    assert result.performance_engine_report.spot_metrics is None
    assert result.performance_engine_report.futures_metrics == result.metrics
    assert result.trade_outcomes == (trade.trade_outcome,)


@pytest.mark.parametrize(
    ("direction", "stop_loss", "take_profit", "liquidation_candle"),
    [
        (
            TradeDirection.LONG,
            "60",
            "130",
            _candle(1, high="101", low="40", close="60"),
        ),
        (
            TradeDirection.SHORT,
            "140",
            "70",
            _candle(1, high="160", low="99", close="140"),
        ),
    ],
)
def test_futures_engine_liquidates_before_stop_in_ambiguous_bar(
    direction: TradeDirection,
    stop_loss: str,
    take_profit: str,
    liquidation_candle: OHLCVCandle,
) -> None:
    candles = (_candle(0), liquidation_candle, _candle(2))
    dataset = _dataset(candles)
    intent = _intent(
        candles[0].timestamp,
        direction,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    config = FuturesBacktestConfig(
        leverage=2,
        liquidation_fee_ratio=Decimal("0.01"),
    )

    result = FuturesBacktestEngine(config).run(
        dataset=dataset,
        signal_provider=_one_signal_provider(intent),
    )

    trade = result.trades[0]
    ordinary_exit_fee = trade.exit_price * trade.quantity * config.fee_ratio
    assert trade.exit_reason is BacktestExitReason.LIQUIDATION
    assert trade.exit_fee_usdt > ordinary_exit_fee
    assert trade.closure_review.stop_quality == "LIQUIDATED"
    assert trade.net_pnl_usdt < Decimal("0")
    assert "FUTURES_LIQUIDATION_OCCURRED" in trade.blocker_history
    assert ("FUTURES_LIQUIDATION_OCCURRED", 1) in (
        result.funnel_telemetry.reason_code_counts
    )


def test_futures_engine_rejects_stop_beyond_liquidation() -> None:
    candles = (_candle(0), _candle(1), _candle(2, low="40", close="55"))
    dataset = _dataset(candles)
    intent = _intent(
        candles[0].timestamp,
        TradeDirection.LONG,
        stop_loss="40",
        take_profit="130",
    )

    result = FuturesBacktestEngine().run(
        dataset=dataset,
        signal_provider=_one_signal_provider(intent),
    )

    assert result.trades == ()
    assert result.rejected_signals[0].blockers == ("STOP_BEYOND_LIQUIDATION",)
    assert result.funnel_telemetry.reason_code_counts == (
        ("STOP_BEYOND_LIQUIDATION", 1),
    )
    observation = result.pre_veto_opportunity_ledger.records[0]
    review = result.missed_opportunity_ledger.records[0]
    assert observation.blockers == ()
    assert observation.execution_allowed is False
    assert observation.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert review.pre_veto_observation_id == observation.observation_id
    assert review.counterfactual_result is MissedOpportunityCategory.GOOD_BLOCK
    assert [event["event_type"] for event in result.audit_events] == [
        "OPPORTUNITY_OBSERVED_PRE_VETO",
        "FUTURES_ENTRY_REJECTED",
        "OPPORTUNITY_VETO_REVIEWED",
    ]


def test_futures_engine_marks_profitable_block_as_bad_block() -> None:
    candles = (
        _candle(0),
        _candle(1, high="105", low="99", close="103"),
        _candle(2, high="121", low="100", close="119"),
    )
    dataset = _dataset(candles)
    intent = replace(
        _intent(
            candles[0].timestamp,
            TradeDirection.LONG,
            stop_loss="80",
            take_profit="120",
        ),
        timestamp=candles[1].timestamp,
    )

    result = FuturesBacktestEngine().run(
        dataset=dataset,
        signal_provider=_one_signal_provider(intent),
    )

    observation = result.pre_veto_opportunity_ledger.records[0]
    review = result.missed_opportunity_ledger.records[0]
    assert result.rejected_signals[0].blockers == ("SIGNAL_TIMESTAMP_MISMATCH",)
    assert review.pre_veto_observation_id == observation.observation_id
    assert review.counterfactual_result is MissedOpportunityCategory.BAD_BLOCK
    assert review.forward_net_pnl is not None
    assert review.forward_net_pnl > Decimal("0")
    assert review.improvement_candidate_id is not None


def test_futures_engine_rejects_mismatched_signal_lineage() -> None:
    candles = (_candle(0), _candle(1), _candle(2))
    dataset = _dataset(candles)
    intent = replace(
        _intent(
            candles[0].timestamp,
            TradeDirection.LONG,
            stop_loss="80",
            take_profit="120",
            symbol="ETHUSDT",
        ),
        timestamp=candles[1].timestamp,
        timeframe="4h",
    )

    result = FuturesBacktestEngine().run(
        dataset=dataset,
        signal_provider=_one_signal_provider(intent),
    )

    assert result.trades == ()
    assert result.rejected_signals[0].blockers == (
        "SIGNAL_TIMESTAMP_MISMATCH",
        "SIGNAL_SYMBOL_MISMATCH",
        "SIGNAL_TIMEFRAME_MISMATCH",
    )


def test_futures_engine_exposes_only_replay_prefix_and_is_deterministic() -> None:
    candles = (_candle(0), _candle(1), _candle(2), _candle(3))
    dataset = _dataset(candles)
    observed: list[tuple[int, int, int]] = []

    def provider(
        replay: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        observed.append(
            (
                len(replay.candles),
                len(replay.open_interest),
                len(
                    replay.derivatives.series.get(
                        DerivativesMetric.FUNDING_RATE,
                        (),
                    )
                ),
            )
        )
        return None

    engine = FuturesBacktestEngine()
    first = engine.run(dataset=dataset, signal_provider=provider)
    observed_first = tuple(observed)
    observed.clear()
    second = engine.run(dataset=dataset, signal_provider=provider)

    assert observed_first == ((1, 1, 0), (2, 2, 0), (3, 3, 1), (4, 4, 1))
    assert tuple(observed) == observed_first
    assert first == second
    assert engine.execution_allowed is False
    assert engine.promotion_status == "RESEARCH_ONLY"
    assert engine.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert all(event["execution_allowed"] is False for event in first.audit_events)
