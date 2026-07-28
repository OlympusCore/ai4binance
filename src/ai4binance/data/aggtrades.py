"""Revisioned Binance Spot aggregate-trade evidence and candle reconciliation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from math import isfinite

from ai4binance.schemas import OHLCVCandle


@dataclass(frozen=True, slots=True)
class AggregateTrade:
    """One normalized public Spot aggregate trade."""

    aggregate_trade_id: int
    price: Decimal
    quantity: Decimal
    first_trade_id: int
    last_trade_id: int
    timestamp: datetime
    buyer_is_maker: bool

    def __post_init__(self) -> None:
        if self.aggregate_trade_id < 0 or self.first_trade_id < 0:
            raise ValueError("aggregate trade identifiers must be non-negative")
        if self.last_trade_id < self.first_trade_id:
            raise ValueError("aggregate trade ID bounds are invalid")
        if self.price <= 0 or self.quantity <= 0:
            raise ValueError("aggregate trade price and quantity must be positive")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("aggregate trade timestamp must be timezone-aware")

    @property
    def quote_quantity(self) -> Decimal:
        return self.price * self.quantity

    @property
    def aggressive_buy_quantity(self) -> Decimal:
        return Decimal("0") if self.buyer_is_maker else self.quantity


@dataclass(frozen=True, slots=True)
class AggregateTradeRevision:
    """Immutable identity for one normalized aggregate-trade dataset."""

    revision_id: str
    symbol: str
    dataset_revision_id: str
    first_timestamp: str
    last_timestamp: str
    first_aggregate_trade_id: int
    last_aggregate_trade_id: int
    trade_count: int
    aggregate_id_gap_count: int
    base_volume: Decimal
    quote_volume: Decimal
    aggressive_buy_ratio: float
    source_sha256: tuple[str, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.revision_id.startswith("aggtrades:") or self.trade_count < 1:
            raise ValueError("aggregate trade revision identity is invalid")
        if not 0.0 <= self.aggressive_buy_ratio <= 1.0 or not isfinite(
            self.aggressive_buy_ratio
        ):
            raise ValueError("aggregate trade buy ratio is invalid")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("aggregate trade evidence cannot authorize execution")


def build_aggregate_trade_revision(
    *,
    symbol: str,
    dataset_revision_id: str,
    trades: tuple[AggregateTrade, ...],
    source_sha256: tuple[str, ...],
) -> AggregateTradeRevision:
    """Validate chronology and seal aggregate trades into a deterministic revision."""
    normalized = symbol.strip().upper()
    if not normalized.isascii() or not normalized.isalnum():
        raise ValueError("aggregate trade symbol is invalid")
    if not dataset_revision_id.startswith("dataset:"):
        raise ValueError("aggregate trades require a dataset revision")
    if not trades or not source_sha256 or len(set(source_sha256)) != len(source_sha256):
        raise ValueError("aggregate trades and unique source checksums are required")
    if any(len(item) != 64 for item in source_sha256):
        raise ValueError("aggregate trade source checksum is invalid")
    ordered = tuple(sorted(trades, key=lambda item: item.aggregate_trade_id))
    unique_identifiers = {item.aggregate_trade_id for item in trades}
    if ordered != trades or len(unique_identifiers) != len(trades):
        raise ValueError("aggregate trades must be unique and ID ordered")
    if any(right.timestamp < left.timestamp for left, right in pairwise(trades)):
        raise ValueError("aggregate trade timestamps cannot move backwards")
    gap_count = sum(
        max(0, right.aggregate_trade_id - left.aggregate_trade_id - 1)
        for left, right in pairwise(trades)
    )
    base_volume = sum((item.quantity for item in trades), Decimal("0"))
    quote_volume = sum((item.quote_quantity for item in trades), Decimal("0"))
    aggressive_buy = sum(
        (item.aggressive_buy_quantity for item in trades), Decimal("0")
    )
    blockers = ("AGGREGATE_TRADE_ID_GAPS_PRESENT",) if gap_count else ()
    payload = json.dumps(
        {
            "symbol": normalized,
            "dataset_revision_id": dataset_revision_id,
            "source_sha256": source_sha256,
            "trades": [
                {
                    **asdict(item),
                    "price": str(item.price),
                    "quantity": str(item.quantity),
                    "timestamp": item.timestamp.isoformat(),
                }
                for item in trades
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return AggregateTradeRevision(
        revision_id=f"aggtrades:{sha256(payload.encode()).hexdigest()[:24]}",
        symbol=normalized,
        dataset_revision_id=dataset_revision_id,
        first_timestamp=trades[0].timestamp.isoformat(),
        last_timestamp=trades[-1].timestamp.isoformat(),
        first_aggregate_trade_id=trades[0].aggregate_trade_id,
        last_aggregate_trade_id=trades[-1].aggregate_trade_id,
        trade_count=len(trades),
        aggregate_id_gap_count=gap_count,
        base_volume=base_volume,
        quote_volume=quote_volume,
        aggressive_buy_ratio=float(aggressive_buy / base_volume),
        source_sha256=source_sha256,
        blockers=blockers,
    )


@dataclass(frozen=True, slots=True)
class CandleTradeReconciliation:
    """Fail-closed comparison between one closed candle and its public trades."""

    candle_timestamp: datetime
    aggregate_trade_count: int
    reconstructed_open: Decimal | None
    reconstructed_high: Decimal | None
    reconstructed_low: Decimal | None
    reconstructed_close: Decimal | None
    reconstructed_volume: Decimal
    aggressive_buy_ratio: float | None
    relative_volume_error: float
    blockers: tuple[str, ...]
    status: str
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"PASSED", "BLOCKED"}:
            raise ValueError("reconciliation status is invalid")
        if (self.status == "PASSED") is bool(self.blockers):
            raise ValueError("reconciliation blockers must match status")
        if self.execution_allowed:
            raise ValueError("trade reconciliation cannot authorize execution")


def reconcile_candle_trades(
    candle: OHLCVCandle,
    trades: tuple[AggregateTrade, ...],
    *,
    duration: timedelta,
    volume_tolerance: Decimal = Decimal("0.000001"),
) -> CandleTradeReconciliation:
    """Reconstruct OHLCV from trades without accepting out-of-window evidence."""
    if duration <= timedelta(0) or volume_tolerance < 0:
        raise ValueError("reconciliation duration and tolerance are invalid")
    window_end = candle.timestamp + duration
    if any(not candle.timestamp <= item.timestamp < window_end for item in trades):
        raise ValueError("aggregate trade falls outside the candle window")
    if not trades:
        blockers = ("AGGREGATE_TRADES_MISSING",)
        return CandleTradeReconciliation(
            candle.timestamp,
            0,
            None,
            None,
            None,
            None,
            Decimal("0"),
            None,
            1.0,
            blockers,
            "BLOCKED",
        )
    prices = tuple(item.price for item in trades)
    volume = sum((item.quantity for item in trades), Decimal("0"))
    aggressive_buy = sum(
        (item.aggressive_buy_quantity for item in trades), Decimal("0")
    )
    relative_error = abs(volume - candle.volume) / max(candle.volume, Decimal("1e-18"))
    mismatch_blockers: list[str] = []
    reconstructed = (prices[0], max(prices), min(prices), prices[-1])
    expected = (candle.open, candle.high, candle.low, candle.close)
    if reconstructed != expected:
        mismatch_blockers.append("CANDLE_TRADE_OHLC_MISMATCH")
    if relative_error > volume_tolerance:
        mismatch_blockers.append("CANDLE_TRADE_VOLUME_MISMATCH")
    return CandleTradeReconciliation(
        candle_timestamp=candle.timestamp,
        aggregate_trade_count=len(trades),
        reconstructed_open=reconstructed[0],
        reconstructed_high=reconstructed[1],
        reconstructed_low=reconstructed[2],
        reconstructed_close=reconstructed[3],
        reconstructed_volume=volume,
        aggressive_buy_ratio=float(aggressive_buy / volume),
        relative_volume_error=float(relative_error),
        blockers=tuple(mismatch_blockers),
        status="BLOCKED" if mismatch_blockers else "PASSED",
    )
