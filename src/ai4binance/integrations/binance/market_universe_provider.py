"""Read-only Binance market universe provider for scanner inputs."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai4binance.core.errors import (
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeRateLimitError,
    ExchangeTransportError,
)
from ai4binance.domain.universe import (
    UniverseMarket,
    UniverseSymbol,
    classify_asset_eligibility,
)

_ZERO = Decimal("0")
_HUGE_SPREAD_BPS = Decimal("1000000")
_PUBLIC_SYMBOL_PATTERN = re.compile(r"^[^\W_]{2,24}$")


class PublicJsonTransport(Protocol):
    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class BinanceUniverseSnapshot:
    """Spot and USD-M Futures universe symbols built from public market data."""

    spot_symbols: tuple[UniverseSymbol, ...]
    futures_symbols: tuple[UniverseSymbol, ...]
    blockers: tuple[str, ...] = ()
    source: str = "BINANCE_PUBLIC_MARKET_DATA"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("Binance universe blockers cannot contain blanks")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("Binance universe snapshot cannot grant execution")


@dataclass(frozen=True, slots=True)
class BinanceEligibleMarketSnapshot:
    """Low-bandwidth active symbol set for public market-data collection."""

    spot_symbols: tuple[str, ...]
    futures_symbols: tuple[str, ...]
    excluded_assets: tuple[tuple[str, tuple[str, ...]], ...] = ()
    blockers: tuple[str, ...] = ()
    source: str = "BINANCE_PUBLIC_EXCHANGE_INFO"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    coin_m_contracts: tuple[tuple[str, str, str], ...] = ()
    selected_assets: tuple[str, ...] = ()
    wallet_assets: tuple[str, ...] = ()
    market_cap_assets: tuple[str, ...] = ()

    @property
    def coin_m_symbols(self) -> tuple[str, ...]:
        return tuple(item[0] for item in self.coin_m_contracts)

    def __post_init__(self) -> None:
        _validate_coin_m_contracts(self.coin_m_contracts)
        _validate_market_symbols(self.spot_symbols, self.futures_symbols)
        if self.spot_symbols != tuple(
            sorted(set(self.spot_symbols))
        ) or self.futures_symbols != tuple(sorted(set(self.futures_symbols))):
            raise ValueError("eligible market symbols must be sorted and unique")
        if any(
            not asset.isalnum()
            or not reasons
            or any(not reason.strip() for reason in reasons)
            for asset, reasons in self.excluded_assets
        ):
            raise ValueError("eligible market exclusions are invalid")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("eligible market blockers cannot contain blanks")
        _validate_market_assets(
            self.selected_assets,
            self.wallet_assets,
            self.market_cap_assets,
        )
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("eligible market snapshot cannot grant execution")


def _validate_coin_m_contracts(
    contracts: tuple[tuple[str, str, str], ...],
) -> None:
    symbols = tuple(item[0] for item in contracts)
    if symbols != tuple(sorted(set(symbols))):
        raise ValueError("COIN-M identities must be sorted and unique")
    for symbol, pair, contract in contracts:
        if (
            not re.fullmatch(r"[A-Z0-9]{2,24}_(?:PERP|[0-9]{6})", symbol)
            or not pair.isalnum()
            or not symbol.startswith(pair + "_")
            or contract not in {"PERPETUAL", "CURRENT_QUARTER", "NEXT_QUARTER"}
        ):
            raise ValueError("COIN-M contract identity is invalid")


def _validate_market_symbols(
    spot_symbols: tuple[str, ...], futures_symbols: tuple[str, ...]
) -> None:
    for symbol in (*spot_symbols, *futures_symbols):
        if not _PUBLIC_SYMBOL_PATTERN.fullmatch(symbol) or symbol != symbol.upper():
            raise ValueError("eligible market symbol identity is invalid")


def _validate_market_assets(*groups: tuple[str, ...]) -> None:
    for assets in groups:
        if assets != tuple(dict.fromkeys(assets)) or any(
            not asset.isalnum() or asset != asset.upper() for asset in assets
        ):
            raise ValueError("eligible market asset identities are invalid")


@dataclass(frozen=True, slots=True)
class ReadOnlyBinanceJsonTransport:
    """HTTPS GET-only transport for public Spot or Futures market endpoints."""

    base_url: str
    allowed_prefixes: tuple[str, ...]
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    max_response_bytes: int = 8_000_000
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    response_headers_observer: Callable[[Mapping[str, str]], None] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        normalized_url = self.base_url.strip().rstrip("/")
        prefixes = tuple(prefix for prefix in self.allowed_prefixes if prefix)
        if not normalized_url.startswith("https://") or "@" in normalized_url:
            raise ValueError("Binance public base_url must be credential-free HTTPS")
        if not prefixes:
            raise ValueError("Binance transport requires allowed path prefixes")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.backoff_seconds < 0 or self.max_backoff_seconds <= 0:
            raise ValueError("backoff values must be non-negative and bounded")
        if self.max_response_bytes < 1024:
            raise ValueError("max_response_bytes is too small")
        object.__setattr__(self, "base_url", normalized_url)
        object.__setattr__(self, "allowed_prefixes", prefixes)

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        """Fetch one public API path and return decoded JSON."""
        if "?" in path or "#" in path or not path.startswith(self.allowed_prefixes):
            raise ValueError("path is outside the configured Binance public boundary")
        query = urlencode(sorted((params or {}).items()))
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._request_once(url, path)
            except HTTPError as error:
                if error.code in {418, 429}:
                    raise ExchangeRateLimitError(
                        error.code,
                        self._parse_retry_after(error.headers.get("Retry-After")),
                        path,
                    ) from None
                retryable = 500 <= error.code <= 599
                if not retryable or attempt == self.max_attempts:
                    raise ExchangeHttpError(
                        f"public Binance HTTP {error.code} at {path}"
                    ) from None
                self.sleeper(
                    self._retry_delay(attempt, error.headers.get("Retry-After"))
                )
            except (TimeoutError, URLError, OSError):
                if attempt == self.max_attempts:
                    raise ExchangeTransportError(
                        f"public Binance request failed at {path}"
                    ) from None
                self.sleeper(self._retry_delay(attempt, None))
        raise ExchangeTransportError(f"public Binance request failed at {path}")

    def _request_once(self, url: str, path: str) -> object:
        request = Request(  # noqa: S310  # nosec B310
            url,
            headers={"Accept": "application/json", "User-Agent": "AI4Binance/0.1"},
            method="GET",
        )
        with urlopen(  # noqa: S310  # nosec B310
            request,
            timeout=self.timeout_seconds,
        ) as response:
            payload = response.read(self.max_response_bytes + 1)
            if self.response_headers_observer is not None:
                self.response_headers_observer(dict(response.headers.items()))
        if len(payload) > self.max_response_bytes:
            raise ExchangePayloadError(f"public Binance payload too large at {path}")
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, JSONDecodeError):
            raise ExchangePayloadError(
                f"invalid public Binance JSON at {path}"
            ) from None

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                parsed = max(0.0, float(retry_after))
            except ValueError:
                parsed = 0.0
            if parsed > 0:
                return min(parsed, self.max_backoff_seconds)
        exponential = self.backoff_seconds * float(2 ** (attempt - 1))
        return float(min(exponential, self.max_backoff_seconds))

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None


@dataclass(frozen=True, slots=True)
class BinanceMarketUniverseProvider:
    """Build bounded real scanner inputs from public Binance market data."""

    spot_transport: PublicJsonTransport
    futures_transport: PublicJsonTransport
    quote_assets: tuple[str, ...] = ("USDT", "USDC")
    max_symbols_per_market: int = 80
    coin_m_transport: PublicJsonTransport | None = None
    futures_symbol_exclusions: tuple[str, ...] = ()

    def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
        """Return active eligible symbols using exchange metadata only.

        This intentionally avoids ticker, book, premium, and per-symbol open-interest
        calls. It is the bounded discovery path for bulk public-data collection, not
        a substitute for the scanner's liquidity and data-quality gates.
        """

        try:
            spot_info = _mapping(
                self.spot_transport.get_json(
                    "/api/v3/exchangeInfo",
                    {"symbolStatus": "TRADING", "showPermissionSets": "false"},
                ),
                "spot.exchangeInfo",
            )
            futures_info = _mapping(
                self.futures_transport.get_json("/fapi/v1/exchangeInfo"),
                "futures.exchangeInfo",
            )
            spot_by_asset = self._active_spot_listings(spot_info)
            futures_by_asset = self._active_futures_listings(futures_info)
            coin_contracts: list[tuple[str, str, str]] = []
            if self.coin_m_transport is not None:
                coin_info = _mapping(
                    self.coin_m_transport.get_json("/dapi/v1/exchangeInfo"),
                    "coin_m.exchangeInfo",
                )
                for raw in _sequence(coin_info.get("symbols"), "coin_m.symbols"):
                    item = _mapping(raw, "coin_m.symbol")
                    symbol, asset = (
                        _text(item.get("symbol")),
                        _text(item.get("baseAsset")),
                    )
                    if (
                        item.get("contractStatus", item.get("status")) == "TRADING"
                        and item.get("quoteAsset") == "USD"
                        and item.get("marginAsset") == asset
                        and item.get("contractType")
                        in {"PERPETUAL", "CURRENT_QUARTER", "NEXT_QUARTER"}
                        and classify_asset_eligibility(
                            asset, futures_symbols=(symbol,)
                        ).eligible
                    ):
                        coin_contracts.append(
                            (
                                symbol,
                                _text(item.get("pair")),
                                _text(item.get("contractType")),
                            )
                        )
        except (ExchangeHttpError, ExchangePayloadError, ExchangeTransportError):
            return BinanceEligibleMarketSnapshot(
                spot_symbols=(),
                futures_symbols=(),
                blockers=("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",),
            )

        accepted_spot: list[str] = []
        accepted_futures: list[str] = []
        excluded: list[tuple[str, tuple[str, ...]]] = []
        for asset in sorted(set(spot_by_asset) | set(futures_by_asset)):
            classification = classify_asset_eligibility(
                asset,
                spot_symbols=tuple(sorted(spot_by_asset.get(asset, ()))),
                futures_symbols=tuple(sorted(futures_by_asset.get(asset, ()))),
            )
            if classification.eligible:
                accepted_spot.extend(classification.spot_symbols)
                accepted_futures.extend(
                    symbol
                    for symbol in classification.futures_symbols
                    if symbol not in self.futures_symbol_exclusions
                )
            else:
                excluded.append((asset, classification.exclusion_reasons))
        blockers = (
            ("PUBLIC_MARKET_UNIVERSE_EMPTY",)
            if not accepted_spot and not accepted_futures and not coin_contracts
            else ()
        )
        return BinanceEligibleMarketSnapshot(
            spot_symbols=tuple(sorted(set(accepted_spot))),
            futures_symbols=tuple(sorted(set(accepted_futures))),
            excluded_assets=tuple(excluded),
            blockers=blockers,
            coin_m_contracts=tuple(sorted(set(coin_contracts))),
        )

    def top_volume_eligible_market_snapshot(
        self, *, max_symbols_per_market: int
    ) -> BinanceEligibleMarketSnapshot:
        """Return the eligible Spot and USD-M symbols with the highest 24h quote volume.

        This bounded, read-only collection path makes one public bulk ticker
        request per market. Missing ticker evidence blocks collection rather than
        widening the universe back to metadata-only symbols.
        """

        if not 1 <= max_symbols_per_market <= 50:
            raise ValueError(
                "top-volume market universe limit must be between 1 and 50"
            )
        metadata = self.eligible_market_snapshot()
        if metadata.blockers:
            return metadata
        try:
            spot_volumes = _by_symbol(
                _sequence(
                    self.spot_transport.get_json("/api/v3/ticker/24hr"),
                    "spot.24hr",
                )
            )
            futures_volumes = _by_symbol(
                _sequence(
                    self.futures_transport.get_json("/fapi/v1/ticker/24hr"),
                    "futures.24hr",
                )
            )
        except (ExchangeHttpError, ExchangePayloadError, ExchangeTransportError):
            return BinanceEligibleMarketSnapshot(
                spot_symbols=(),
                futures_symbols=(),
                excluded_assets=metadata.excluded_assets,
                blockers=("PUBLIC_MARKET_LIQUIDITY_UNIVERSE_UNAVAILABLE",),
                coin_m_contracts=metadata.coin_m_contracts,
            )

        spot_symbols = _top_volume_symbols(
            metadata.spot_symbols, spot_volumes, max_symbols_per_market
        )
        futures_symbols = _top_volume_symbols(
            metadata.futures_symbols, futures_volumes, max_symbols_per_market
        )
        if not spot_symbols or not futures_symbols:
            return BinanceEligibleMarketSnapshot(
                spot_symbols=(),
                futures_symbols=(),
                excluded_assets=metadata.excluded_assets,
                blockers=("PUBLIC_MARKET_LIQUIDITY_UNIVERSE_EMPTY",),
                coin_m_contracts=metadata.coin_m_contracts,
            )
        return BinanceEligibleMarketSnapshot(
            spot_symbols=spot_symbols,
            futures_symbols=futures_symbols,
            excluded_assets=metadata.excluded_assets,
            source="BINANCE_PUBLIC_24H_QUOTE_VOLUME",
            coin_m_contracts=metadata.coin_m_contracts,
        )

    def _active_spot_listings(
        self,
        exchange_info: Mapping[str, object],
    ) -> dict[str, list[str]]:
        listings: dict[str, list[str]] = {}
        for raw_item in _sequence(exchange_info.get("symbols"), "spot.symbols"):
            item = _mapping(raw_item, "spot.symbol")
            symbol = _text(item.get("symbol"))
            if _is_active_spot_listing(item, self.quote_assets):
                listings.setdefault(_text(item.get("baseAsset")), []).append(symbol)
        return listings

    def _active_futures_listings(
        self,
        exchange_info: Mapping[str, object],
    ) -> dict[str, list[str]]:
        listings: dict[str, list[str]] = {}
        for raw_item in _sequence(exchange_info.get("symbols"), "futures.symbols"):
            item = _mapping(raw_item, "futures.symbol")
            symbol = _text(item.get("symbol"))
            if _is_active_usd_m_futures_listing(item, self.quote_assets):
                listings.setdefault(_text(item.get("baseAsset")), []).append(symbol)
        return listings

    def snapshot(self, priority_symbols: Sequence[str] = ()) -> BinanceUniverseSnapshot:
        """Return Spot and Futures symbols without private credentials or orders."""
        priorities = _normalized_symbols(priority_symbols)
        try:
            spot_symbols = self._spot_symbols(priorities)
            futures_symbols = self._futures_symbols(priorities)
        except (ExchangeHttpError, ExchangePayloadError, ExchangeTransportError):
            return BinanceUniverseSnapshot(
                spot_symbols=(),
                futures_symbols=(),
                blockers=("PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",),
            )
        blockers = (
            ("PUBLIC_MARKET_UNIVERSE_EMPTY",)
            if not spot_symbols and not futures_symbols
            else ()
        )
        return BinanceUniverseSnapshot(
            spot_symbols=spot_symbols,
            futures_symbols=futures_symbols,
            blockers=blockers,
        )

    def _spot_symbols(self, priorities: tuple[str, ...]) -> tuple[UniverseSymbol, ...]:
        exchange_info = _mapping(
            self.spot_transport.get_json("/api/v3/exchangeInfo"),
            "spot.exchangeInfo",
        )
        tickers = _by_symbol(
            _sequence(
                self.spot_transport.get_json("/api/v3/ticker/24hr"),
                "spot.24hr",
            )
        )
        books = _by_symbol(
            _sequence(
                self.spot_transport.get_json("/api/v3/ticker/bookTicker"),
                "spot.bookTicker",
            )
        )
        candidates = []
        for raw_item in _sequence(exchange_info.get("symbols"), "spot.symbols"):
            item = _mapping(raw_item, "spot.symbol")
            symbol = _text(item.get("symbol"))
            if not _is_active_spot_listing(item, self.quote_assets):
                continue
            ticker = tickers.get(symbol, {})
            candidates.append(
                UniverseSymbol(
                    symbol=symbol,
                    market=UniverseMarket.SPOT,
                    base_asset=_text(item.get("baseAsset")),
                    quote_asset=_text(item.get("quoteAsset")),
                    status=_text(item.get("status")),
                    min_notional_usdt=_min_notional(item),
                    quote_volume_24h_usdt=_decimal(ticker.get("quoteVolume")),
                    spread_bps=_spread_bps(books.get(symbol, {})),
                    depth_0_5_pct_usdt=_top_of_book_depth_usdt(books.get(symbol, {})),
                    data_quality_ok=symbol in tickers and symbol in books,
                )
            )
        return _bounded_priority_sorted(
            candidates,
            priorities,
            self.max_symbols_per_market,
        )

    def spot_symbols(
        self, priority_symbols: Sequence[str] = ()
    ) -> tuple[UniverseSymbol, ...]:
        """Reuse canonical liquidity ordering for a bounded Spot-only consumer."""
        return self._spot_symbols(_normalized_symbols(priority_symbols))

    def _futures_symbols(
        self,
        priorities: tuple[str, ...],
    ) -> tuple[UniverseSymbol, ...]:
        exchange_info = _mapping(
            self.futures_transport.get_json("/fapi/v1/exchangeInfo"),
            "futures.exchangeInfo",
        )
        tickers = _by_symbol(
            _sequence(
                self.futures_transport.get_json("/fapi/v1/ticker/24hr"),
                "futures.24hr",
            )
        )
        books = _by_symbol(
            _sequence(
                self.futures_transport.get_json("/fapi/v1/ticker/bookTicker"),
                "futures.bookTicker",
            )
        )
        premiums = _by_symbol(
            _sequence(
                self.futures_transport.get_json("/fapi/v1/premiumIndex"),
                "futures.premiumIndex",
            )
        )
        raw_candidates = []
        for raw_item in _sequence(exchange_info.get("symbols"), "futures.symbols"):
            item = _mapping(raw_item, "futures.symbol")
            symbol = _text(item.get("symbol"))
            if not _is_active_usd_m_futures_listing(item, self.quote_assets):
                continue
            ticker = tickers.get(symbol, {})
            raw_candidates.append(
                (
                    symbol in priorities,
                    _decimal(ticker.get("quoteVolume")),
                    item,
                    ticker,
                )
            )
        selected = tuple(
            item
            for _, _, item, _ in sorted(
                raw_candidates,
                key=lambda value: (
                    not value[0],
                    -value[1],
                    _text(value[2].get("symbol")),
                ),
            )[: self.max_symbols_per_market]
        )
        symbols = []
        for item in selected:
            symbol = _text(item.get("symbol"))
            ticker = tickers.get(symbol, {})
            book = books.get(symbol, {})
            premium = premiums.get(symbol, {})
            open_interest = self._open_interest_usdt(
                symbol,
                _decimal(ticker.get("lastPrice")),
            )
            symbols.append(
                UniverseSymbol(
                    symbol=symbol,
                    market=UniverseMarket.USD_M_FUTURES,
                    base_asset=_text(item.get("baseAsset")),
                    quote_asset=_text(item.get("quoteAsset")),
                    status=_text(item.get("status")),
                    min_notional_usdt=_ZERO,
                    quote_volume_24h_usdt=_decimal(ticker.get("quoteVolume")),
                    spread_bps=_spread_bps(book),
                    depth_0_5_pct_usdt=_top_of_book_depth_usdt(book),
                    data_quality_ok=(
                        symbol in tickers
                        and symbol in books
                        and symbol in premiums
                        and open_interest > _ZERO
                    ),
                    contract_type=_text(item.get("contractType")),
                    margin_asset=_text(item.get("marginAsset")),
                    open_interest_usdt=open_interest,
                    funding_rate=_signed_decimal(premium.get("lastFundingRate")),
                )
            )
        return tuple(symbols)

    def _open_interest_usdt(self, symbol: str, last_price: Decimal) -> Decimal:
        if last_price <= _ZERO:
            return _ZERO
        try:
            payload = _mapping(
                self.futures_transport.get_json(
                    "/fapi/v1/openInterest",
                    {"symbol": symbol},
                ),
                "futures.openInterest",
            )
        except (ExchangeHttpError, ExchangePayloadError, ExchangeTransportError):
            return _ZERO
        return _decimal(payload.get("openInterest")) * last_price


def _bounded_priority_sorted(
    candidates: Sequence[UniverseSymbol],
    priorities: tuple[str, ...],
    limit: int,
) -> tuple[UniverseSymbol, ...]:
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.symbol not in priorities,
                -item.quote_volume_24h_usdt,
                item.symbol,
            ),
        )[:limit]
    )


def _top_volume_symbols(
    eligible_symbols: Sequence[str],
    tickers: Mapping[str, Mapping[str, object]],
    limit: int,
) -> tuple[str, ...]:
    """Select a deterministic positive-volume subset and retain snapshot ordering."""

    ranked = sorted(
        (
            (symbol, _decimal(tickers.get(symbol, {}).get("quoteVolume")))
            for symbol in eligible_symbols
            if _decimal(tickers.get(symbol, {}).get("quoteVolume")) > _ZERO
        ),
        key=lambda value: (-value[1], value[0]),
    )[:limit]
    return tuple(sorted(symbol for symbol, _ in ranked))


def _normalized_symbols(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(value.strip().upper() for value in values if value.strip())
    )


def _is_quote_allowed(quote_asset: str, allowed: tuple[str, ...]) -> bool:
    return quote_asset.upper() in {item.upper() for item in allowed}


def _is_active_spot_listing(
    item: Mapping[str, object],
    quote_assets: tuple[str, ...],
) -> bool:
    """Accept only symbols Binance currently exposes as Spot-tradable."""

    permissions = {
        _text(value)
        for value in _sequence(item.get("permissions", ()), "spot.permissions")
    }
    return (
        bool(_text(item.get("symbol")))
        and bool(_text(item.get("baseAsset")))
        and _text(item.get("status")) == "TRADING"
        and _is_quote_allowed(_text(item.get("quoteAsset")), quote_assets)
        and (not permissions or "SPOT" in permissions)
        and item.get("isSpotTradingAllowed", True) is not False
    )


def _is_active_usd_m_futures_listing(
    item: Mapping[str, object],
    quote_assets: tuple[str, ...],
) -> bool:
    """Accept only active USD-M perpetual contracts for Futures research."""

    quote_asset = _text(item.get("quoteAsset"))
    return (
        bool(_text(item.get("symbol")))
        and bool(_text(item.get("baseAsset")))
        and _text(item.get("status")) == "TRADING"
        and _text(item.get("contractType")) == "PERPETUAL"
        and _is_quote_allowed(quote_asset, quote_assets)
        and _text(item.get("marginAsset")) == quote_asset
    )


def _by_symbol(values: Sequence[object]) -> dict[str, Mapping[str, object]]:
    records: dict[str, Mapping[str, object]] = {}
    for value in values:
        item = _mapping(value, "market record")
        symbol = _text(item.get("symbol"))
        if symbol:
            records[symbol] = item
    return records


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExchangePayloadError(f"{field_name} must be an object")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, list | tuple):
        raise ExchangePayloadError(f"{field_name} must be an array")
    return value


def _text(value: object) -> str:
    return str(value or "").strip().upper()


def _decimal(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        return _ZERO
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _ZERO
    if not parsed.is_finite() or parsed < _ZERO:
        return _ZERO
    return parsed


def _signed_decimal(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        return _ZERO
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _ZERO
    return parsed if parsed.is_finite() else _ZERO


def _spread_bps(book: Mapping[str, object]) -> Decimal:
    bid = _decimal(book.get("bidPrice"))
    ask = _decimal(book.get("askPrice"))
    if bid <= _ZERO or ask <= _ZERO or ask < bid:
        return _HUGE_SPREAD_BPS
    midpoint = (bid + ask) / Decimal("2")
    if midpoint <= _ZERO:
        return _HUGE_SPREAD_BPS
    return (ask - bid) * Decimal("10000") / midpoint


def _top_of_book_depth_usdt(book: Mapping[str, object]) -> Decimal:
    bid = _decimal(book.get("bidPrice"))
    ask = _decimal(book.get("askPrice"))
    bid_qty = _decimal(book.get("bidQty"))
    ask_qty = _decimal(book.get("askQty"))
    return min(bid * bid_qty, ask * ask_qty)


def _min_notional(item: Mapping[str, object]) -> Decimal:
    for raw_filter in _sequence(item.get("filters", ()), "spot.symbol.filters"):
        filter_item = _mapping(raw_filter, "spot.symbol.filter")
        if _text(filter_item.get("filterType")) in {"MIN_NOTIONAL", "NOTIONAL"}:
            value = _decimal(filter_item.get("minNotional"))
            if value > _ZERO:
                return value
    return _ZERO
