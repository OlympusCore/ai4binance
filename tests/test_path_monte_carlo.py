from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.backtest.engine import SignalProvider
from ai4binance.backtest.models import BacktestIntent
from ai4binance.backtest.path_monte_carlo import (
    CandlePathMonteCarloAnalyzer,
    CandlePathMonteCarloReport,
)
from ai4binance.domain import ValidationStatus
from ai4binance.schemas import OHLCVCandle


def _candles() -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index),
            Decimal("10") + Decimal(index) / 10,
            Decimal("11") + Decimal(index) / 10,
            Decimal("9") + Decimal(index) / 10,
            Decimal("10.5") + Decimal(index) / 10,
            Decimal("1000"),
        )
        for index in range(12)
    )


def test_path_monte_carlo_is_deterministic_and_fail_closed() -> None:
    def factory() -> SignalProvider:
        def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
            if len(history) not in {1, 3, 5, 7, 9}:
                return None
            current = history[-1]
            return BacktestIntent(
                f"signal-{len(history)}",
                current.timestamp,
                current.low - Decimal("1"),
                current.high + Decimal("1"),
                Decimal("0.5"),
            )

        return provider

    analyzer = CandlePathMonteCarloAnalyzer(simulations=25, seed=7)
    first = analyzer.analyze(
        symbol="HOTUSDT", timeframe="1h", candles=_candles(), provider_factory=factory
    )
    second = analyzer.analyze(
        symbol="HOTUSDT", timeframe="1h", candles=_candles(), provider_factory=factory
    )

    assert first == second
    assert first.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert first.execution_allowed is False


def test_path_monte_carlo_rejects_invalid_contracts() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        CandlePathMonteCarloReport(
            24,
            1,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            ("BLOCKED",),
            ValidationStatus.RESEARCH_ONLY,
        )
    with pytest.raises(ValueError, match="status"):
        CandlePathMonteCarloReport(
            25,
            1,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            (),
            ValidationStatus.RESEARCH_ONLY,
        )
    with pytest.raises(ValueError, match="simulations"):
        CandlePathMonteCarloAnalyzer(simulations=2)
    with pytest.raises(ValueError, match="jitter"):
        CandlePathMonteCarloAnalyzer(maximum_price_jitter_ratio=Decimal("0.2"))
    with pytest.raises(ValueError, match="three candles"):
        CandlePathMonteCarloAnalyzer(simulations=25).analyze(
            symbol="HOTUSDT",
            timeframe="1h",
            candles=_candles()[:2],
            provider_factory=lambda: lambda history: None,
        )
