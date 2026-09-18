"""Immutable public exchange response models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from ai4binance.schemas import OHLCVCandle

FilterValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class BookTicker:
    """Best bid and ask for one Spot symbol."""

    bid: Decimal
    ask: Decimal

    def __post_init__(self) -> None:
        if self.bid < Decimal("0") or self.ask < Decimal("0"):
            raise ValueError("bid and ask cannot be negative")
        if self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class MarketKline:
    """Exchange kline carrying both open and close timestamps."""

    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None or self.close_time.tzinfo is None:
            raise ValueError("kline timestamps must be timezone-aware")
        if self.open_time >= self.close_time:
            raise ValueError("kline open_time must precede close_time")
        OHLCVCandle(
            timestamp=self.open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )

    def to_candle(self) -> OHLCVCandle:
        """Drop exchange lifecycle metadata after the candle is confirmed closed."""
        return OHLCVCandle(
            timestamp=self.open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    """Normalized symbol metadata and immutable exchange filters."""

    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    filters: Mapping[str, Mapping[str, FilterValue]]

    def __post_init__(self) -> None:
        if not all(
            item.strip()
            for item in (self.symbol, self.status, self.base_asset, self.quote_asset)
        ):
            raise ValueError("symbol metadata fields cannot be empty")
        frozen_filters = {
            name: MappingProxyType(dict(values))
            for name, values in self.filters.items()
        }
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "filters", MappingProxyType(frozen_filters))
