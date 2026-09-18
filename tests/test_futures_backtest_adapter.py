"""Runtime Price/OI to Futures backtest intent adapter tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.research.backtesting import (
    FuturesBacktestEngine,
    FuturesBacktestIntent,
)
from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    TradeDirection,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation import (
    RuntimeFuturesBacktestAdapter,
    RuntimeFuturesBacktestConfig,
    RuntimeFuturesReplayDataset,
    runtime_futures_backtest_engine,
    runtime_futures_strategy_sha256,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    PriceOiRegime,
    Provenance,
)

START = datetime(2026, 9, 1, tzinfo=UTC)
SOURCE_ID = "BINANCE_USD_M_PUBLIC_REST"
SOURCE_URL = "https://fapi.binance.com"


def _replay(
    prices: tuple[str, ...],
    open_interest: tuple[str, ...],
) -> RuntimeFuturesReplayDataset:
    candles = tuple(
        OHLCVCandle(
            timestamp=START + timedelta(hours=index),
            open=Decimal(price),
            high=Decimal(price) + Decimal("5"),
            low=Decimal(price) - Decimal("1"),
            close=Decimal(price),
            volume=Decimal("1000"),
        )
        for index, price in enumerate(prices)
    )
    oi_points = tuple(
        _point(DerivativesMetric.OPEN_INTEREST, candle.timestamp, value)
        for candle, value in zip(candles, open_interest, strict=True)
    )
    funding_points = (
        _point(DerivativesMetric.FUNDING_RATE, candles[0].timestamp, "0.0001"),
    )
    return RuntimeFuturesReplayDataset(
        symbol="BTCUSDT",
        candles=candles,
        derivatives=DerivativesDataset(
            symbol="BTCUSDT",
            as_of=candles[-1].timestamp,
            series={
                DerivativesMetric.OPEN_INTEREST: oi_points,
                DerivativesMetric.FUNDING_RATE: funding_points,
            },
            source=SOURCE_ID,
        ),
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
        provenance=Provenance(SOURCE_ID, timestamp, SOURCE_URL),
    )


@pytest.mark.parametrize(
    ("setup", "prices", "open_interest", "direction"),
    [
        (
            PriceOiRegime.NEW_LONG_PARTICIPATION,
            ("100", "101", "102", "103", "104"),
            ("1000", "1010", "1020", "1030", "1040"),
            TradeDirection.LONG,
        ),
        (
            PriceOiRegime.SHORT_COVERING,
            ("100", "101", "102", "103", "104"),
            ("1040", "1030", "1020", "1010", "1000"),
            TradeDirection.LONG,
        ),
        (
            PriceOiRegime.NEW_SHORT_PRESSURE,
            ("104", "103", "102", "101", "100"),
            ("1000", "1010", "1020", "1030", "1040"),
            TradeDirection.SHORT,
        ),
        (
            PriceOiRegime.DELEVERAGING,
            ("104", "103", "102", "101", "100"),
            ("1040", "1030", "1020", "1010", "1000"),
            TradeDirection.SHORT,
        ),
    ],
)
def test_adapter_maps_price_oi_setup_to_directional_geometry(
    setup: PriceOiRegime,
    prices: tuple[str, ...],
    open_interest: tuple[str, ...],
    direction: TradeDirection,
) -> None:
    replay = _replay(prices, open_interest)
    adapter = RuntimeFuturesBacktestAdapter(RuntimeFuturesBacktestConfig(setup))

    first = adapter(replay)
    second = adapter(replay)

    assert first is not None
    assert first == second
    assert first.direction is direction
    assert first.timestamp == replay.candles[-1].timestamp
    assert first.strategy_id == "RuntimeFuturesAdvisor"
    assert first.strategy_version == "runtime-futures-advisor-v1"
    assert first.strategy_config_hash == adapter.strategy_sha256
    assert first.snapshot_id == replay.dataset_sha256
    assert first.regime == setup.value
    assert first.maximum_holding_bars == 24
    if direction is TradeDirection.LONG:
        assert first.stop_loss == replay.candles[-1].close * Decimal("0.98")
        assert first.take_profit == replay.candles[-1].close * Decimal("1.04")
    else:
        assert first.stop_loss == replay.candles[-1].close * Decimal("1.02")
        assert first.take_profit == replay.candles[-1].close * Decimal("0.96")
    assert adapter.execution_allowed is False
    assert adapter.promotion_status == "RESEARCH_ONLY"
    assert adapter.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_adapter_fails_closed_for_insufficient_flat_and_mismatched_setups() -> None:
    insufficient = _replay(
        ("100", "101", "102", "103"),
        ("1000", "1010", "1020", "1030"),
    )
    adapter = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(PriceOiRegime.NEW_LONG_PARTICIPATION)
    )
    assert adapter(insufficient) is None
    assert adapter.blocker_counts == (("OI_OR_PRICE_HISTORY_INSUFFICIENT", 1),)

    flat = _replay(
        ("100", "100", "100", "100", "100"),
        ("1000", "1000", "1000", "1000", "1000"),
    )
    assert adapter(flat) is None
    assert ("PRICE_OI_DIRECTION_UNAVAILABLE", 1) in adapter.blocker_counts

    mismatched = _replay(
        ("100", "101", "102", "103", "104"),
        ("1040", "1030", "1020", "1010", "1000"),
    )
    assert adapter(mismatched) is None
    assert ("PRICE_OI_SETUP_MISMATCH", 1) in adapter.blocker_counts


def test_adapter_strategy_hash_binds_signal_geometry() -> None:
    baseline = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(PriceOiRegime.NEW_LONG_PARTICIPATION)
    )
    wider_target = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(
            PriceOiRegime.NEW_LONG_PARTICIPATION,
            take_profit_ratio=Decimal("0.06"),
        )
    )

    assert baseline.strategy_sha256 == runtime_futures_strategy_sha256(
        short_lookback=1,
        medium_lookback=4,
    )
    assert baseline.strategy_sha256 != wider_target.strategy_sha256
    with pytest.raises(ValueError, match="risk-reward"):
        RuntimeFuturesBacktestConfig(
            PriceOiRegime.NEW_LONG_PARTICIPATION,
            take_profit_ratio=Decimal("0.03"),
        )
    with pytest.raises(ValueError, match="must be directional"):
        RuntimeFuturesBacktestConfig(PriceOiRegime.FLAT_OR_MIXED)


def test_adapter_output_runs_through_futures_engine_with_exact_lineage() -> None:
    replay = _replay(
        ("100", "101", "102", "103", "104", "105", "106"),
        ("1000", "1010", "1020", "1030", "1040", "1050", "1060"),
    )
    adapter = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(PriceOiRegime.NEW_LONG_PARTICIPATION)
    )
    emitted = False

    def provider(
        prefix: RuntimeFuturesReplayDataset,
    ) -> FuturesBacktestIntent | None:
        nonlocal emitted
        if emitted:
            return None
        intent = adapter(prefix)
        if intent is not None:
            emitted = True
        return intent

    result = FuturesBacktestEngine().run(
        dataset=replay,
        signal_provider=provider,
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_timestamp == replay.candles[5].timestamp
    assert trade.exit_reason is BacktestExitReason.TARGET
    assert trade.direction is TradeDirection.LONG
    assert trade.attribution.strategy_config_hash == adapter.strategy_sha256
    assert trade.attribution.regime == PriceOiRegime.NEW_LONG_PARTICIPATION.value
    assert trade.attribution.market == "USD_M_FUTURES"
    assert result.metrics.market == "USD_M_FUTURES"


def test_runtime_engine_price_normalizes_high_price_replay_quantity() -> None:
    replay = _replay(
        ("40000", "41000", "42000", "43000", "44000", "45000", "46000"),
        ("1000", "1010", "1020", "1030", "1040", "1050", "1060"),
    )
    adapter = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(PriceOiRegime.NEW_LONG_PARTICIPATION)
    )

    result = runtime_futures_backtest_engine(replay).run(
        dataset=replay,
        signal_provider=adapter,
    )

    assert result.assumptions.quantity < Decimal("1")
    assert result.trades
    assert all(
        "INSUFFICIENT_BACKTEST_MARGIN" not in rejected.blockers
        for rejected in result.rejected_signals
    )


def test_runtime_adapter_indexed_path_avoids_prefix_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay = _replay(
        ("100", "101", "102", "103", "104", "105", "106"),
        ("1000", "1010", "1020", "1030", "1040", "1050", "1060"),
    )
    adapter = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(PriceOiRegime.NEW_LONG_PARTICIPATION)
    )

    def unexpected_prefix(*_: object) -> RuntimeFuturesReplayDataset:
        raise AssertionError("indexed provider must not rebuild replay prefixes")

    monkeypatch.setattr(FuturesBacktestEngine, "_replay_prefix", unexpected_prefix)

    result = FuturesBacktestEngine().run(dataset=replay, signal_provider=adapter)

    assert result.trades


def test_indexed_intent_does_not_depend_on_future_candles() -> None:
    baseline = _replay(
        ("100", "101", "102", "103", "104", "105", "106"),
        ("1000", "1010", "1020", "1030", "1040", "1050", "1060"),
    )
    changed_future = _replay(
        ("100", "101", "102", "103", "104", "90", "80"),
        ("1000", "1010", "1020", "1030", "1040", "900", "800"),
    )
    adapter = RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(PriceOiRegime.NEW_LONG_PARTICIPATION)
    )

    first = adapter.intent_at(baseline, 4)
    second = adapter.intent_at(changed_future, 4)

    assert first is not None
    assert first == second
    assert first.snapshot_id.startswith("runtime-prefix:")
