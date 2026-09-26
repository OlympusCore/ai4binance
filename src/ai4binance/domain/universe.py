"""Canonical deterministic universe filter contracts."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")
RESEARCH_MARKET_UNIVERSE_SOURCE = "BINANCE_WALLET_AND_COINGECKO_MARKET_CAP"

_STABLE_BASE_ASSETS = frozenset(
    {
        "USDT",
        "USDC",
        "FDUSD",
        "TUSD",
        "DAI",
        "USDP",
        "BUSD",
        "USTC",
        "EUR",
        "AEUR",
        "EURI",
        "PYUSD",
        "USD1",
        "USDE",
        "USDS",
        "USDG",
        "USDD",
        "RLUSD",
        "FRAX",
        "LUSD",
        "GHO",
        "EURC",
        "U",
    }
)
_WRAPPED_BASES = frozenset({"WBTC", "WETH", "WBNB", "WSOL", "WBETH"})
_LEVERAGED_SUFFIXES = (
    "UP",
    "DOWN",
    "BULL",
    "BEAR",
    "3L",
    "3S",
    "5L",
    "5S",
    "LONG",
    "SHORT",
)


class UniverseMarket(StrEnum):
    SPOT = "SPOT"
    USD_M_FUTURES = "USD_M_FUTURES"


@dataclass(frozen=True, slots=True)
class AssetEligibility:
    """Deterministic asset identity and collection eligibility classification."""

    asset: str
    asset_class: str
    spot_symbols: tuple[str, ...]
    futures_symbols: tuple[str, ...]
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    confidence: float


def classify_asset_eligibility(
    asset: str,
    *,
    spot_symbols: tuple[str, ...] = (),
    futures_symbols: tuple[str, ...] = (),
    metadata_name: str = "",
    liquidity_ok: bool = True,
    data_quality_ok: bool = True,
) -> AssetEligibility:
    """Classify a Binance base asset without granting trading authority."""

    normalized = asset.strip().upper()
    normalized_spot = tuple(
        dict.fromkeys(symbol.strip().upper() for symbol in spot_symbols)
    )
    normalized_futures = tuple(
        dict.fromkeys(symbol.strip().upper() for symbol in futures_symbols)
    )
    exclusions: list[str] = []
    asset_class = "ELIGIBLE_COIN"
    confidence = 0.95
    name = metadata_name.casefold()
    if normalized in _STABLE_BASE_ASSETS:
        asset_class = "STABLECOIN"
        exclusions.append("STABLECOIN_BASE_ASSET")
    elif normalized in _WRAPPED_BASES or "wrapped " in name:
        asset_class = "WRAPPED_ASSET"
        exclusions.append("WRAPPED_ASSET")
        confidence = 0.88
    elif normalized.endswith(_LEVERAGED_SUFFIXES) and not (
        normalized_spot and normalized_futures
    ):
        asset_class = "LEVERAGED_ASSET"
        exclusions.append("LEVERAGED_TOKEN")
        confidence = 0.85
    elif (
        normalized.startswith("W")
        and normalized not in _WRAPPED_BASES
        and not normalized_futures
    ):
        asset_class = "UNKNOWN"
        exclusions.extend(("ASSET_CLASSIFICATION_UNCERTAIN", "MANUAL_REVIEW_REQUIRED"))
        confidence = 0.45
    if not liquidity_ok:
        exclusions.append("LIQUIDITY_FILTER_FAILED")
    if not data_quality_ok:
        exclusions.append("DATA_QUALITY_FILTER_FAILED")
    eligible = not exclusions and bool(normalized_spot or normalized_futures)
    if not eligible and not exclusions:
        exclusions.append("NO_ACTIVE_BINANCE_SYMBOL")
    return AssetEligibility(
        asset=normalized,
        asset_class=asset_class,
        spot_symbols=normalized_spot,
        futures_symbols=normalized_futures,
        eligible=eligible,
        exclusion_reasons=tuple(dict.fromkeys(exclusions)),
        confidence=confidence,
    )


@dataclass(frozen=True, slots=True)
class UniverseFilterPolicy:
    quote_assets: tuple[str, ...] = ("USDT", "USDC")
    futures_margin_assets: tuple[str, ...] = ("USDT",)
    minimum_24h_quote_volume_usdt: Decimal = Decimal("1000000")
    maximum_spread_bps: Decimal = Decimal("50")
    minimum_depth_0_5_pct_usdt: Decimal = Decimal("25000")
    minimum_open_interest_usdt: Decimal = Decimal("1000000")
    maximum_abs_funding_rate: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        quote_assets = tuple(
            dict.fromkeys(item.strip().upper() for item in self.quote_assets)
        )
        margin_assets = tuple(
            dict.fromkeys(item.strip().upper() for item in self.futures_margin_assets)
        )
        if not quote_assets or any(not item.isalnum() for item in quote_assets):
            raise ValueError("quote assets must be non-empty alphanumeric values")
        if not margin_assets or any(not item.isalnum() for item in margin_assets):
            raise ValueError("margin assets must be non-empty alphanumeric values")
        values = (
            self.minimum_24h_quote_volume_usdt,
            self.maximum_spread_bps,
            self.minimum_depth_0_5_pct_usdt,
            self.minimum_open_interest_usdt,
            self.maximum_abs_funding_rate,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("universe filter policy values must be non-negative")
        object.__setattr__(self, "quote_assets", quote_assets)
        object.__setattr__(self, "futures_margin_assets", margin_assets)


@dataclass(frozen=True, slots=True)
class UniverseSymbol:
    symbol: str
    market: UniverseMarket
    base_asset: str
    quote_asset: str
    status: str
    min_notional_usdt: Decimal
    quote_volume_24h_usdt: Decimal
    spread_bps: Decimal
    depth_0_5_pct_usdt: Decimal
    data_quality_ok: bool = True
    contract_type: str | None = None
    margin_asset: str | None = None
    open_interest_usdt: Decimal | None = None
    funding_rate: Decimal | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        base = self.base_asset.strip().upper()
        quote = self.quote_asset.strip().upper()
        status = self.status.strip().upper()
        if not symbol or not symbol.isalnum() or not base or not quote or not status:
            raise ValueError("universe symbol identity is invalid")
        non_negative = (
            self.min_notional_usdt,
            self.quote_volume_24h_usdt,
            self.spread_bps,
            self.depth_0_5_pct_usdt,
            *(value for value in (self.open_interest_usdt,) if value is not None),
        )
        if any(not value.is_finite() or value < ZERO for value in non_negative):
            raise ValueError("universe symbol values must be non-negative")
        if self.funding_rate is not None and not self.funding_rate.is_finite():
            raise ValueError("funding rate must be finite")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "base_asset", base)
        object.__setattr__(self, "quote_asset", quote)
        object.__setattr__(self, "status", status)
        if self.contract_type is not None:
            object.__setattr__(
                self, "contract_type", self.contract_type.strip().upper()
            )
        if self.margin_asset is not None:
            object.__setattr__(self, "margin_asset", self.margin_asset.strip().upper())


@dataclass(frozen=True, slots=True)
class UniverseFilterResult:
    symbol: UniverseSymbol
    accepted: bool
    blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.accepted == bool(self.blockers):
            raise ValueError("universe result acceptance and blockers disagree")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("universe blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("universe filter result cannot grant execution authority")
