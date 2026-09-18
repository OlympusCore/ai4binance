"""Backtest runtime economics review tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ai4binance.research.backtesting import (
    BacktestRuntimeEconomicsEvidence,
    BacktestRuntimeEconomicsReview,
    BacktestRuntimeEconomicsReviewStatus,
    BacktestRuntimeReviewerResult,
    review_backtest_runtime_economics,
)


def runtime_economics() -> BacktestRuntimeEconomicsEvidence:
    return BacktestRuntimeEconomicsEvidence(
        artifact_id="artifact:backtest-runtime",
        title="Local backtest runtime profile",
        source_url="https://example.com/backtest-runtime",
        source_sha256="1" * 64,
        hardware_profile="Local RTX 3070 Ti workstation",
        runtime_stack="python 3.12, pandas, numpy, deterministic backtest engine",
        reviewer_result=BacktestRuntimeReviewerResult.PASSED,
        claimed_monthly_cost_usd=0.0,
        measured_latency_ms=1250.0,
        measured_simulations_per_second=18.5,
        measured_power_watts=240.0,
        benchmark_citations=("https://example.com/benchmark",),
        privacy_controls=("loopback-only",),
        operational_controls=("bounded-simulations",),
        gpu_available=True,
        gpu_requested=True,
        gpu_used=True,
    )


def test_backtest_runtime_economics_accepts_measured_gpu_profile() -> None:
    review = review_backtest_runtime_economics(runtime_economics())

    assert (
        review.status
        is BacktestRuntimeEconomicsReviewStatus.RESEARCH_ONLY_BACKTEST_RUNTIME
    )
    assert review.promotion_status == "RESEARCH_ONLY_BACKTEST_RUNTIME"
    assert review.hardware_profile == "Local RTX 3070 Ti workstation"
    assert review.measured_latency_ms == 1250.0
    assert review.measured_simulations_per_second == 18.5
    assert review.measured_power_watts == 240.0
    assert review.gpu_available is True
    assert review.gpu_requested is True
    assert review.gpu_used is True
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "BACKTEST_RUNTIME_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.installation_allowed is False
    assert review.provider_switch_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_backtest_runtime_economics_watchlists_missing_measurements_and_controls() -> (
    None
):
    review = review_backtest_runtime_economics(
        replace(
            runtime_economics(),
            measured_power_watts=None,
            privacy_controls=(),
            operational_controls=(),
            reviewer_result=BacktestRuntimeReviewerResult.WATCHLIST,
            rejection_reason="Power, privacy, and operational controls are incomplete.",
        )
    )

    assert review.status is BacktestRuntimeEconomicsReviewStatus.WATCHLIST
    assert "POWER_THERMAL_REVIEW_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_PRIVACY_CONTROL_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_OPERATIONAL_CONTROL_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_REVIEWER_WATCHLIST" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_backtest_runtime_economics_blocks_unavailable_uncited_claim() -> None:
    review = review_backtest_runtime_economics(
        replace(
            runtime_economics(),
            source_available=False,
            benchmark_citations=(),
            claimed_monthly_cost_usd=None,
            measured_latency_ms=None,
            measured_simulations_per_second=None,
            reviewer_result=BacktestRuntimeReviewerResult.REJECTED,
            rejection_reason="Source and benchmark evidence unavailable.",
        )
    )

    assert review.status is BacktestRuntimeEconomicsReviewStatus.BLOCKED
    assert "BACKTEST_RUNTIME_SOURCE_UNAVAILABLE" in review.blockers
    assert "BACKTEST_RUNTIME_BENCHMARK_CITATION_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_COST_MEASUREMENT_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_LATENCY_MEASUREMENT_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_THROUGHPUT_MEASUREMENT_REQUIRED" in review.blockers
    assert "BACKTEST_RUNTIME_REVIEWER_REJECTED" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_backtest_runtime_economics_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(runtime_economics(), source_url="http://user:pass@example.com")
    with pytest.raises(ValueError, match="source hash"):
        replace(runtime_economics(), source_sha256="bad")
    with pytest.raises(ValueError, match="finite and non-negative"):
        replace(runtime_economics(), measured_latency_ms=-1.0)
    with pytest.raises(ValueError, match="benchmark citations"):
        replace(runtime_economics(), benchmark_citations=("same", "same"))
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(runtime_economics(), provider_switch_allowed=True)
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_backtest_runtime_economics(runtime_economics()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="require human review"):
        BacktestRuntimeEconomicsReview(
            artifact_id="artifact",
            title="runtime",
            source_url="https://example.com/runtime",
            source_sha256="f" * 64,
            hardware_profile="local workstation",
            runtime_stack="local loop",
            status=BacktestRuntimeEconomicsReviewStatus.RESEARCH_ONLY_BACKTEST_RUNTIME,
            reviewer_result=BacktestRuntimeReviewerResult.PASSED,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
            benchmark_citations=("https://example.com/runtime",),
            privacy_controls=("LOOPBACK_ONLY",),
            operational_controls=("RUNAWAY_LOOP_BUDGET",),
            claimed_monthly_cost_usd=0.0,
            measured_latency_ms=850.0,
            measured_simulations_per_second=42.0,
            measured_power_watts=310.0,
            rejection_reason="none",
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            review_backtest_runtime_economics(runtime_economics()),
            installation_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            review_backtest_runtime_economics(runtime_economics()),
            live_eligibility_status="PAPER_APPROVED",
        )
