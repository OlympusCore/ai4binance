from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.backtest.queue_fill import (
    QueueFillRequest,
    RestingSide,
    replay_conservative_queue_fill,
)
from ai4binance.data.aggtrades import AggregateTrade
from ai4binance.exchange.order_book import BookLevel

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _trade(
    identifier: int, quantity: str, *, buyer_is_maker: bool = True
) -> AggregateTrade:
    return AggregateTrade(
        identifier,
        Decimal("1"),
        Decimal(quantity),
        identifier,
        identifier,
        NOW + timedelta(seconds=identifier),
        buyer_is_maker,
    )


def test_conservative_queue_consumes_visible_quantity_before_partial_fill() -> None:
    request = QueueFillRequest(RestingSide.BUY, Decimal("1"), Decimal("5"), NOW)

    report = replay_conservative_queue_fill(
        request,
        initial_levels=(BookLevel(Decimal("1"), Decimal("10")),),
        trades=(_trade(1, "6"), _trade(2, "7")),
    )

    assert report.initial_queue_ahead == Decimal("10")
    assert report.consumed_queue_ahead == Decimal("10")
    assert report.filled_quantity == Decimal("3")
    assert report.fill_ratio == Decimal("0.6")
    assert report.blockers == ("ORDER_NOT_FULLY_FILLED",)
    assert report.execution_allowed is False


def test_conservative_queue_ignores_wrong_aggressor_and_prefill_trades() -> None:
    request = QueueFillRequest(
        RestingSide.BUY, Decimal("1"), Decimal("2"), NOW + timedelta(seconds=2)
    )
    report = replay_conservative_queue_fill(
        request,
        initial_levels=(),
        trades=(_trade(1, "5"), _trade(2, "5", buyer_is_maker=False)),
    )

    assert report.filled_quantity == 0
    assert "NO_MARKETABLE_AGGREGATE_TRADES" in report.blockers


def test_conservative_queue_blocks_trade_sequence_gaps() -> None:
    request = QueueFillRequest(RestingSide.SELL, Decimal("1"), Decimal("1"), NOW)

    report = replay_conservative_queue_fill(
        request,
        initial_levels=(),
        trades=(_trade(1, "1"), _trade(3, "1")),
    )

    assert report.blockers == ("AGGREGATE_TRADE_SEQUENCE_GAP",)
    assert report.filled_quantity == 0


def test_queue_fill_contracts_reject_invalid_requests_and_duplicate_levels() -> None:
    with pytest.raises(ValueError, match="positive"):
        QueueFillRequest(RestingSide.BUY, Decimal("0"), Decimal("1"), NOW)
    request = QueueFillRequest(RestingSide.BUY, Decimal("1"), Decimal("1"), NOW)
    level = BookLevel(Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError, match="unique"):
        replay_conservative_queue_fill(
            request, initial_levels=(level, level), trades=()
        )
