from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.exchange.order_book import (
    BookLevel,
    BookState,
    OrderBookDelta,
    OrderBookSnapshot,
    ReadOnlyOrderBook,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        "HOTUSDT",
        100,
        NOW,
        (BookLevel(Decimal("0.999"), Decimal("100")),),
        (BookLevel(Decimal("1.001"), Decimal("80")),),
    )


def test_order_book_applies_snapshot_and_contiguous_absolute_delta() -> None:
    book = ReadOnlyOrderBook("hotusdt")

    initial = book.apply_snapshot(_snapshot())
    updated = book.apply_delta(
        OrderBookDelta(
            101,
            102,
            NOW + timedelta(milliseconds=10),
            (
                BookLevel(Decimal("0.999"), Decimal("0")),
                BookLevel(Decimal("1"), Decimal("50")),
            ),
            (BookLevel(Decimal("1.001"), Decimal("70")),),
        )
    )

    assert initial.state is BookState.LIVE
    assert updated.accepted is True
    assert updated.best_bid == Decimal("1")
    assert updated.best_ask == Decimal("1.001")
    assert updated.execution_allowed is False


def test_order_book_stops_on_sequence_gap_until_new_snapshot() -> None:
    book = ReadOnlyOrderBook("HOTUSDT")
    book.apply_snapshot(_snapshot())

    gap = book.apply_delta(OrderBookDelta(103, 104, NOW + timedelta(seconds=1), (), ()))
    rejected = book.apply_delta(
        OrderBookDelta(101, 101, NOW + timedelta(seconds=2), (), ())
    )

    assert gap.state is BookState.GAP_DETECTED
    assert gap.blockers == ("ORDER_BOOK_SEQUENCE_GAP",)
    assert rejected.blockers == ("ORDER_BOOK_SNAPSHOT_REQUIRED",)


def test_order_book_blocks_crossed_or_empty_books() -> None:
    crossed = ReadOnlyOrderBook("HOTUSDT").apply_snapshot(
        OrderBookSnapshot(
            "HOTUSDT",
            1,
            NOW,
            (BookLevel(Decimal("1.1"), Decimal("1")),),
            (BookLevel(Decimal("1"), Decimal("1")),),
        )
    )

    assert crossed.state is BookState.DEGRADED
    assert crossed.blockers == ("ORDER_BOOK_CROSSED",)


def test_order_book_rejects_invalid_contracts_and_duplicate_levels() -> None:
    with pytest.raises(ValueError, match="price"):
        BookLevel(Decimal("0"), Decimal("1"))
    with pytest.raises(ValueError, match="identity"):
        OrderBookSnapshot("HOTUSDT", 0, NOW, (), ())
    with pytest.raises(ValueError, match="sequence"):
        OrderBookDelta(2, 1, NOW, (), ())
    with pytest.raises(ValueError, match="symbol"):
        ReadOnlyOrderBook("bad-symbol")
    book = ReadOnlyOrderBook("HOTUSDT")
    with pytest.raises(ValueError, match="symbol mismatch"):
        book.apply_snapshot(replace(_snapshot(), symbol="BTCUSDT"))
    duplicate = replace(_snapshot(), bids=(_snapshot().bids[0], _snapshot().bids[0]))
    with pytest.raises(ValueError, match="unique"):
        book.apply_snapshot(duplicate)


def test_order_book_rejects_old_backward_and_duplicate_delta_prices() -> None:
    book = ReadOnlyOrderBook("HOTUSDT")
    book.apply_snapshot(_snapshot())
    old = book.apply_delta(OrderBookDelta(99, 100, NOW, (), ()))
    assert old.blockers == ("ORDER_BOOK_OLD_DELTA",)
    with pytest.raises(ValueError, match="backwards"):
        book.apply_delta(OrderBookDelta(101, 101, NOW - timedelta(seconds=1), (), ()))
    level = BookLevel(Decimal("0.998"), Decimal("1"))
    with pytest.raises(ValueError, match="unique"):
        book.apply_delta(
            OrderBookDelta(101, 101, NOW + timedelta(seconds=1), (level, level), ())
        )


def test_order_book_blocks_empty_side_and_configured_level_limit() -> None:
    empty = ReadOnlyOrderBook("HOTUSDT").apply_snapshot(
        replace(_snapshot(), bids=(BookLevel(Decimal("0.999"), Decimal("0")),))
    )
    limited = ReadOnlyOrderBook("HOTUSDT", maximum_levels=1).apply_snapshot(
        replace(
            _snapshot(),
            bids=(
                BookLevel(Decimal("0.999"), Decimal("1")),
                BookLevel(Decimal("0.998"), Decimal("1")),
            ),
        )
    )
    assert empty.blockers == ("ORDER_BOOK_SIDE_EMPTY",)
    assert limited.blockers == ("ORDER_BOOK_LEVEL_LIMIT_EXCEEDED",)
