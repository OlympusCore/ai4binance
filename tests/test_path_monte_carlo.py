from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.research.backtesting.engine import SignalProvider
from ai4binance.research.backtesting.models import BacktestIntent
from ai4binance.research.backtesting.path_monte_carlo import (
    CandlePathMonteCarloAnalyzer,
    CandlePathMonteCarloReport,
)
from ai4binance.research.backtesting.runtime_economics import (
    BacktestRuntimeEconomicsEvidence,
    BacktestRuntimeReviewerResult,
    review_backtest_runtime_economics,
)
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
    assert first.runtime_economics_review is None


def test_path_monte_carlo_carries_runtime_economics_review() -> None:
    review = review_backtest_runtime_economics(
        BacktestRuntimeEconomicsEvidence(
            artifact_id="artifact:mc-runtime",
            title="Monte Carlo runtime profile",
            source_url="https://example.com/mc-runtime",
            source_sha256="2" * 64,
            hardware_profile="Local RTX 3070 Ti workstation",
            runtime_stack="python 3.12, deterministic Monte Carlo analysis",
            reviewer_result=BacktestRuntimeReviewerResult.PASSED,
            claimed_monthly_cost_usd=0.0,
            measured_latency_ms=750.0,
            measured_simulations_per_second=24.0,
            measured_power_watts=235.0,
            benchmark_citations=("https://example.com/mc-benchmark",),
            privacy_controls=("loopback-only",),
            operational_controls=("bounded-simulations",),
            gpu_available=True,
            gpu_requested=True,
            gpu_used=True,
        )
    )
    analyzer = CandlePathMonteCarloAnalyzer(
        simulations=25, seed=7, runtime_economics_review=review
    )

    result = analyzer.analyze(
        symbol="HOTUSDT",
        timeframe="1h",
        candles=_candles(),
        provider_factory=lambda: lambda history: None,
    )

    assert result.runtime_economics_review == review
    assert result.runtime_economics_review.hardware_profile.startswith("Local RTX")


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
