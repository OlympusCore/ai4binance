"""Sequence-aware, read-only Binance Spot order-book reconstruction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class BookState(StrEnum):
    EMPTY = "EMPTY"
    LIVE = "LIVE"
    GAP_DETECTED = "GAP_DETECTED"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        if (
            not self.price.is_finite()
            or not self.quantity.is_finite()
            or self.price <= 0
            or self.quantity < 0
        ):
            raise ValueError("book level price and quantity are invalid")


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    symbol: str
    last_update_id: int
    observed_at: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    sequence_bridged: bool = False

    def __post_init__(self) -> None:
        if self.last_update_id < 1 or not self.symbol.strip():
            raise ValueError("order-book snapshot identity is invalid")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("order-book snapshot timestamp must be timezone-aware")
        if not self.bids or not self.asks:
            raise ValueError("order-book snapshot must contain both sides")


@dataclass(frozen=True, slots=True)
class OrderBookDelta:
    first_update_id: int
    last_update_id: int
    event_time: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    previous_update_id: int | None = None

    def __post_init__(self) -> None:
        if self.first_update_id < 1 or self.last_update_id < self.first_update_id:
            raise ValueError("order-book delta sequence is invalid")
        if self.previous_update_id is not None and self.previous_update_id < 0:
            raise ValueError("order-book previous sequence is invalid")
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("order-book delta timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OrderBookObservation:
    state: BookState
    accepted: bool
    last_update_id: int | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    spread_bps: Decimal | None
    top_imbalance: Decimal | None
    blockers: tuple[str, ...]
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("public order-book evidence cannot authorize execution")


@dataclass(slots=True)
class ReadOnlyOrderBook:
    """Apply absolute-quantity depth updates and fail closed on sequence gaps."""

    symbol: str
    maximum_levels: int = 5_000
    futures_sequence: bool = False
    state: BookState = field(default=BookState.EMPTY, init=False)
    last_update_id: int | None = field(default=None, init=False)
    last_event_at: datetime | None = field(default=None, init=False)
    _bids: dict[Decimal, Decimal] = field(default_factory=dict, init=False, repr=False)
    _asks: dict[Decimal, Decimal] = field(default_factory=dict, init=False, repr=False)
    _bridged: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        normalized = self.symbol.strip().upper()
        if not re.fullmatch(r"[^\W_]{2,24}(?:_(?:PERP|[0-9]{6}))?", normalized):
            raise ValueError("order-book symbol is invalid")
        if not 1 <= self.maximum_levels <= 100_000:
            raise ValueError("order-book maximum levels are invalid")
        self.symbol = normalized

    def apply_snapshot(self, snapshot: OrderBookSnapshot) -> OrderBookObservation:
        if snapshot.symbol != self.symbol:
            raise ValueError("order-book snapshot symbol mismatch")
        self._bids = self._levels(snapshot.bids)
        self._asks = self._levels(snapshot.asks)
        self.last_update_id = snapshot.last_update_id
        self.last_event_at = snapshot.observed_at
        self._bridged = snapshot.sequence_bridged
        return self._validate_and_observe()

    def apply_delta(self, delta: OrderBookDelta) -> OrderBookObservation:
        if self.state is not BookState.LIVE or self.last_update_id is None:
            return self._observation(False, "ORDER_BOOK_SNAPSHOT_REQUIRED")
        if self.last_event_at is not None and delta.event_time < self.last_event_at:
            raise ValueError("order-book event time cannot move backwards")
        expected = self.last_update_id + (
            0 if self.futures_sequence and not self._bridged else 1
        )
        if delta.last_update_id < expected:
            return self._observation(False, "ORDER_BOOK_OLD_DELTA")
        valid_sequence = delta.first_update_id <= expected <= delta.last_update_id
        if self.futures_sequence:
            valid_sequence = delta.previous_update_id is not None and (
                delta.previous_update_id == self.last_update_id
                if self._bridged
                else valid_sequence
            )
        if not valid_sequence:
            self.state = BookState.GAP_DETECTED
            return self._observation(False, "ORDER_BOOK_SEQUENCE_GAP")
        self._apply_side(self._bids, delta.bids)
        self._apply_side(self._asks, delta.asks)
        self.last_update_id = delta.last_update_id
        self.last_event_at = delta.event_time
        self._bridged = True
        return self._validate_and_observe()

    def levels(self) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
        bids = tuple(
            BookLevel(price, quantity)
            for price, quantity in sorted(self._bids.items(), reverse=True)
        )
        asks = tuple(
            BookLevel(price, quantity) for price, quantity in sorted(self._asks.items())
        )
        return bids, asks

    def _validate_and_observe(self) -> OrderBookObservation:
        if not self._bids or not self._asks:
            self.state = BookState.DEGRADED
            return self._observation(False, "ORDER_BOOK_SIDE_EMPTY")
        if (
            len(self._bids) > self.maximum_levels
            or len(self._asks) > self.maximum_levels
        ):
            self.state = BookState.DEGRADED
            return self._observation(False, "ORDER_BOOK_LEVEL_LIMIT_EXCEEDED")
        if max(self._bids) >= min(self._asks):
            self.state = BookState.DEGRADED
            return self._observation(False, "ORDER_BOOK_CROSSED")
        self.state = BookState.LIVE
        return self._observation(True)

    def _observation(self, accepted: bool, *blockers: str) -> OrderBookObservation:
        if not self._bids or not self._asks:
            best_bid = best_ask = spread = imbalance = None
        else:
            best_bid, best_ask = max(self._bids), min(self._asks)
            midpoint = (best_bid + best_ask) / 2
            spread = (best_ask - best_bid) / midpoint * Decimal("10000")
            bid_quantity = self._bids[best_bid]
            ask_quantity = self._asks[best_ask]
            total = bid_quantity + ask_quantity
            imbalance = (
                (bid_quantity - ask_quantity) / total if total > 0 else Decimal("0")
            )
        return OrderBookObservation(
            self.state,
            accepted,
            self.last_update_id,
            best_bid,
            best_ask,
            spread,
            imbalance,
            tuple(blockers),
        )

    @staticmethod
    def _levels(levels: tuple[BookLevel, ...]) -> dict[Decimal, Decimal]:
        if len({item.price for item in levels}) != len(levels):
            raise ValueError("order-book levels must have unique prices")
        return {item.price: item.quantity for item in levels if item.quantity > 0}

    @staticmethod
    def _apply_side(
        side: dict[Decimal, Decimal], levels: tuple[BookLevel, ...]
    ) -> None:
        if len({item.price for item in levels}) != len(levels):
            raise ValueError("order-book delta prices must be unique")
        for item in levels:
            if item.quantity == 0:
                side.pop(item.price, None)
            else:
                side[item.price] = item.quantity
