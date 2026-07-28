"""Exchange resilience, reconciliation and proposal-only risk tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.exchange.resilience import RateLimitBudget, assess_server_time
from ai4binance.portfolio.reconciliation import OpenOrderView, reconcile_open_orders
from ai4binance.portfolio.risk_budget import (
    PortfolioRiskPolicy,
    PositionExposure,
    assess_current_exposure,
    assess_proposed_exposure,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def test_rate_limit_budget_blocks_and_resets_deterministically() -> None:
    budget = RateLimitBudget(10, timedelta(minutes=1))
    assert budget.consume(7, NOW).remaining_weight == 3
    blocked = budget.consume(4, NOW + timedelta(seconds=10))
    assert blocked.allowed is False
    assert blocked.blockers == ("EXCHANGE_RATE_LIMIT_BUDGET_EXHAUSTED",)
    assert blocked.retry_after_seconds == 50.0
    reset = budget.consume(4, NOW + timedelta(minutes=1))
    assert reset.allowed is True
    assert reset.used_weight == 4


def test_server_time_drift_is_explicit() -> None:
    assert assess_server_time(10_000, 10_500).acceptable is True
    blocked = assess_server_time(10_000, 12_000)
    assert blocked.blockers == ("EXCHANGE_SERVER_TIME_DRIFT",)


def test_open_order_reconciliation_reports_all_mismatch_classes() -> None:
    local = (
        OpenOrderView("known", "HOTUSDT", Decimal("2")),
        OpenOrderView("missing", "HOTUSDT", Decimal("1")),
    )
    exchange = (
        OpenOrderView("known", "HOTUSDT", Decimal("1.5")),
        OpenOrderView("unknown", "HOTUSDT", Decimal("1")),
    )
    report = reconcile_open_orders(local, exchange)
    assert report.missing_on_exchange == ("missing",)
    assert report.unknown_on_exchange == ("unknown",)
    assert report.quantity_mismatches == ("known",)
    assert report.execution_allowed is False


def test_portfolio_risk_allows_small_proposal_and_blocks_concentration() -> None:
    current = (PositionExposure("HOTUSDT", "trend", "alts", Decimal("180")),)
    allowed = assess_proposed_exposure(
        current,
        PositionExposure("BTCUSDT", "reclaim", "majors", Decimal("50")),
    )
    assert allowed.approved_for_proposal is True
    assert allowed.execution_allowed is False

    blocked = assess_proposed_exposure(
        current,
        PositionExposure("HOTUSDT", "trend", "alts", Decimal("140")),
        PortfolioRiskPolicy(),
    )
    assert "SYMBOL_EXPOSURE_LIMIT_EXCEEDED" in blocked.blockers
    assert "CORRELATION_GROUP_LIMIT_EXCEEDED" in blocked.blockers
    assert "STRATEGY_EXPOSURE_LIMIT_EXCEEDED" in blocked.blockers


def test_current_portfolio_risk_reports_observed_limit_breaches() -> None:
    current = (
        PositionExposure("HOTUSDT", "inventory", "alts", Decimal("280")),
        PositionExposure("XRPUSDT", "inventory", "alts", Decimal("40")),
    )

    report = assess_current_exposure(current)

    assert report.approved_for_proposal is False
    assert report.gross_after_usdt == Decimal("320")
    assert "SYMBOL_EXPOSURE_LIMIT_EXCEEDED" in report.blockers
    assert "CORRELATION_GROUP_LIMIT_EXCEEDED" in report.blockers
    assert "STRATEGY_EXPOSURE_LIMIT_EXCEEDED" in report.blockers


def test_resilience_contracts_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimitBudget(0, timedelta(seconds=1))
    with pytest.raises(ValueError, match="unique"):
        reconcile_open_orders(
            (
                OpenOrderView("same", "HOTUSDT", Decimal("1")),
                OpenOrderView("same", "HOTUSDT", Decimal("2")),
            ),
            (),
        )
    with pytest.raises(ValueError, match="positive"):
        PortfolioRiskPolicy(maximum_gross_usdt=Decimal("0"))
    with pytest.raises(ValueError, match="configured budget"):
        RateLimitBudget(10, timedelta(seconds=1)).consume(11, NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        RateLimitBudget(10, timedelta(seconds=1)).consume(1, NOW.replace(tzinfo=None))
    budget = RateLimitBudget(10, timedelta(seconds=1))
    budget.consume(1, NOW)
    with pytest.raises(ValueError, match="time cannot move backwards"):
        budget.consume(1, NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="server-time"):
        assess_server_time(-1, 1)
    with pytest.raises(ValueError, match="identity"):
        OpenOrderView("", "HOTUSDT", Decimal("1"))
    with pytest.raises(ValueError, match="positive"):
        OpenOrderView("id", "HOTUSDT", Decimal("0"))
    with pytest.raises(ValueError, match="invalid"):
        PositionExposure("", "trend", "alts", Decimal("1"))
