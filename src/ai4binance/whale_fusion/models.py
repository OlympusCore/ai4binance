"""Immutable WHALE-FUSION taxonomy, provenance and derivatives contracts."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from types import MappingProxyType

ZERO = Decimal("0")


class WhaleEventType(StrEnum):
    WHALE_TO_BINANCE = "WHALE_TO_BINANCE"
    BINANCE_TO_WHALE = "BINANCE_TO_WHALE"
    WHALE_TO_DEX = "WHALE_TO_DEX"
    STABLECOIN_ACCUMULATION = "STABLECOIN_ACCUMULATION"
    STABLECOIN_EXCHANGE_DEPOSIT = "STABLECOIN_EXCHANGE_DEPOSIT"
    TOKEN_ACCUMULATION = "TOKEN_ACCUMULATION"  # noqa: S105  # nosec B105
    TOKEN_DISTRIBUTION = "TOKEN_DISTRIBUTION"  # noqa: S105  # nosec B105
    NEW_WALLET = "NEW_WALLET"
    SPLIT_TRANSFER = "SPLIT_TRANSFER"
    BRIDGE_TRANSFER = "BRIDGE_TRANSFER"
    STAKING_EXIT = "STAKING_EXIT"
    TOKEN_UNLOCK_MOVEMENT = "TOKEN_UNLOCK_MOVEMENT"  # noqa: S105  # nosec B105
    MARKET_MAKER_MOVEMENT = "MARKET_MAKER_MOVEMENT"


class SocialEventType(StrEnum):
    PROJECT_ANNOUNCEMENT = "PROJECT_ANNOUNCEMENT"
    LISTING_CHANGE = "LISTING_CHANGE"
    UNLOCK_GOVERNANCE = "UNLOCK_GOVERNANCE"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    REGULATORY_EVENT = "REGULATORY_EVENT"
    FUND_OR_TREASURY_COMMENT = "FUND_OR_TREASURY_COMMENT"
    MARKET_MAKER_COMMENT = "MARKET_MAKER_COMMENT"
    TRANSFER_EXPLANATION = "TRANSFER_EXPLANATION"
    RUMOR_OR_DENIAL = "RUMOR_OR_DENIAL"


class DerivativesMetric(StrEnum):
    OPEN_INTEREST = "OPEN_INTEREST"
    OPEN_INTEREST_VALUE = "OPEN_INTEREST_VALUE"
    TOP_ACCOUNT_RATIO = "TOP_ACCOUNT_RATIO"
    TOP_POSITION_RATIO = "TOP_POSITION_RATIO"
    GLOBAL_ACCOUNT_RATIO = "GLOBAL_ACCOUNT_RATIO"
    FUNDING_RATE = "FUNDING_RATE"
    TAKER_BUY_SELL_RATIO = "TAKER_BUY_SELL_RATIO"
    BASIS_RATE = "BASIS_RATE"
    MARK_PRICE = "MARK_PRICE"
    INDEX_PRICE = "INDEX_PRICE"
    ORDER_BOOK_IMBALANCE = "ORDER_BOOK_IMBALANCE"
    LARGE_TRADE_NOTIONAL = "LARGE_TRADE_NOTIONAL"
    LIQUIDATION_NOTIONAL = "LIQUIDATION_NOTIONAL"
    ADL_RISK = "ADL_RISK"


class PriceOiRegime(StrEnum):
    NEW_LONG_PARTICIPATION = "NEW_LONG_PARTICIPATION"
    SHORT_COVERING = "SHORT_COVERING"
    NEW_SHORT_PRESSURE = "NEW_SHORT_PRESSURE"
    DELEVERAGING = "DELEVERAGING"
    FLAT_OR_MIXED = "FLAT_OR_MIXED"


@dataclass(frozen=True, slots=True)
class Provenance:
    source_id: str
    observed_at: datetime
    source_url: str

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.source_url.startswith("https://"):
            raise ValueError("provenance requires source_id and HTTPS source_url")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("provenance observed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MetricPoint:
    metric: DerivativesMetric
    timestamp: datetime
    value: Decimal
    provenance: Provenance
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("metric timestamp must be timezone-aware")
        if not self.value.is_finite():
            raise ValueError("metric value must be finite")
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True, slots=True)
class DerivativesDataset:
    symbol: str
    as_of: datetime
    series: Mapping[DerivativesMetric, tuple[MetricPoint, ...]]
    source: str = "BINANCE_USD_M_PUBLIC_REST"

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol or not symbol.isascii() or not symbol.isalnum():
            raise ValueError("dataset symbol must be ASCII alphanumeric")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("dataset as_of must be timezone-aware")
        normalized: dict[DerivativesMetric, tuple[MetricPoint, ...]] = {}
        for metric, points in self.series.items():
            ordered = tuple(points)
            if any(point.metric is not metric for point in ordered):
                raise ValueError("dataset series contains mismatched metric")
            if any(
                current.timestamp <= previous.timestamp
                for previous, current in pairwise(ordered)
            ):
                raise ValueError("dataset series must be strictly chronological")
            normalized[metric] = ordered
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "series", MappingProxyType(normalized))

    def values(self, metric: DerivativesMetric) -> tuple[Decimal, ...]:
        return tuple(point.value for point in self.series.get(metric, ()))


@dataclass(frozen=True, slots=True)
class DerivativesFeatures:
    symbol: str
    as_of: datetime
    oi_change_short: Decimal | None
    oi_change_medium: Decimal | None
    oi_zscore: Decimal | None
    oi_percentile: Decimal | None
    price_oi_regime: PriceOiRegime
    funding_percentile: Decimal | None
    basis_zscore: Decimal | None
    taker_imbalance: Decimal | None
    top_vs_global_divergence: Decimal | None
    mark_index_deviation: Decimal | None
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("derivatives features cannot grant execution authority")
