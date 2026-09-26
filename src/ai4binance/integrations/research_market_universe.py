"""Research-only wallet and public market-cap universe selection."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
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
from ai4binance.domain.universe import classify_asset_eligibility
from ai4binance.integrations.binance.market_universe_provider import (
    BinanceEligibleMarketSnapshot,
    BinanceMarketUniverseProvider,
)
from ai4binance.storage import read_bounded_jsonl_tail

_ZERO = Decimal("0")
RESEARCH_MARKET_UNIVERSE_SOURCE = "BINANCE_WALLET_AND_COINGECKO_MARKET_CAP"


class _RetryableMarketCapError(Exception):
    def __init__(self, final_error: Exception) -> None:
        super().__init__(str(final_error))
        self.final_error = final_error


def _read_market_cap_response(
    request: Request, *, timeout_seconds: float, maximum_bytes: int
) -> list[object]:
    try:
        with urlopen(  # noqa: S310  # nosec B310
            request, timeout=timeout_seconds
        ) as response:
            payload = response.read(maximum_bytes + 1)
    except HTTPError as error:
        if error.code in {418, 429}:
            raise ExchangeRateLimitError(error.code, None, request.full_url) from None
        failure = ExchangeHttpError(
            f"public market-cap HTTP {error.code} at /api/v3/coins/markets"
        )
        if error.code < 500:
            raise failure from None
        raise _RetryableMarketCapError(failure) from None
    except (TimeoutError, URLError, OSError):
        raise _RetryableMarketCapError(
            ExchangeTransportError("public market-cap request failed")
        ) from None
    if len(payload) > maximum_bytes:
        raise ExchangePayloadError("public market-cap payload is too large")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExchangePayloadError("public market-cap JSON is invalid") from None
    if not isinstance(decoded, list):
        raise ExchangePayloadError("public market-cap payload is invalid")
    return decoded


class PublicMarketCapTransport(Protocol):
    """Credential-free JSON transport used only for public market ranking."""

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int | bool] | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ReadOnlyCoinGeckoJsonTransport:
    """Bounded HTTPS GET transport for the public CoinGecko market endpoint."""

    base_url: str = "https://api.coingecko.com"
    timeout_seconds: float = 10.0
    max_attempts: int = 2
    max_response_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        normalized = self.base_url.strip().rstrip("/")
        if normalized != "https://api.coingecko.com":
            raise ValueError("CoinGecko public base URL is outside the allowlist")
        if self.timeout_seconds <= 0 or not 1 <= self.max_attempts <= 3:
            raise ValueError("CoinGecko transport bounds are invalid")
        if not 1024 <= self.max_response_bytes <= 8_000_000:
            raise ValueError("CoinGecko response bound is invalid")
        object.__setattr__(self, "base_url", normalized)

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int | bool] | None = None,
    ) -> object:
        if path != "/api/v3/coins/markets" or "?" in path or "#" in path:
            raise ValueError("CoinGecko path is outside the configured boundary")
        query = urlencode(sorted((params or {}).items()))
        request = Request(  # noqa: S310  # nosec B310
            f"{self.base_url}{path}?{query}",
            headers={"Accept": "application/json", "User-Agent": "AI4Binance/0.1"},
            method="GET",
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                return _read_market_cap_response(
                    request,
                    timeout_seconds=self.timeout_seconds,
                    maximum_bytes=self.max_response_bytes,
                )
            except _RetryableMarketCapError as error:
                if attempt == self.max_attempts:
                    raise error.final_error from None
        raise ExchangeTransportError("public market-cap request failed")


@dataclass(frozen=True, slots=True)
class WalletAssetSnapshot:
    """Secret-safe latest Spot wallet asset selection."""

    assets: tuple[str, ...]
    observed_at: datetime
    sync_run_id: str


def _wallet_record(
    raw: bytes,
) -> tuple[datetime, str, Mapping[str, object]] | None:
    value = json.loads(raw.decode("utf-8"))
    payload = value.get("payload") if isinstance(value, Mapping) else None
    envelope = payload.get("envelope") if isinstance(payload, Mapping) else None
    if not isinstance(payload, Mapping) or not isinstance(envelope, Mapping):
        return None
    sync_run_id = envelope.get("sync_run_id")
    event_time = envelope.get("event_time") or envelope.get("received_at")
    if not isinstance(sync_run_id, str) or not isinstance(event_time, str):
        return None
    parsed = datetime.fromisoformat(event_time)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC), sync_run_id, payload


def _eligible_wallet_asset(
    payload: Mapping[str, object], *, minimum_value_usdt: Decimal
) -> str | None:
    if payload.get("execution_allowed") is not False:
        return None
    asset = payload.get("asset")
    try:
        market_value = Decimal(str(payload.get("market_value_usdt")))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if (
        isinstance(asset, str)
        and asset.isalnum()
        and asset == asset.upper()
        and market_value.is_finite()
        and market_value > minimum_value_usdt
    ):
        return asset
    return None


def _validate_wallet_selection_request(
    path: Path,
    *,
    observed_at: datetime,
    minimum_value_usdt: Decimal,
    maximum_age: timedelta,
) -> None:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("wallet universe observation time must be timezone-aware")
    if (
        not minimum_value_usdt.is_finite()
        or minimum_value_usdt <= _ZERO
        or maximum_age <= timedelta(0)
    ):
        raise ValueError("wallet universe bounds must be positive")
    if path.is_symlink() or not path.is_file():
        raise OSError("wallet balance snapshot is unavailable")


def read_wallet_assets_above_value(
    path: Path,
    *,
    observed_at: datetime,
    minimum_value_usdt: Decimal,
    maximum_age: timedelta,
) -> WalletAssetSnapshot:
    """Read one complete latest Spot snapshot without retaining stale assets."""

    _validate_wallet_selection_request(
        path,
        observed_at=observed_at,
        minimum_value_usdt=minimum_value_usdt,
        maximum_age=maximum_age,
    )
    records: list[tuple[datetime, str, Mapping[str, object]]] = []
    for raw in read_bounded_jsonl_tail(path, max_lines=2_000, max_bytes=16_000_000):
        record = _wallet_record(raw)
        if record is not None:
            records.append(record)
    if not records:
        raise ValueError("wallet balance snapshot contains no valid records")
    latest_time, latest_run, _ = max(records, key=lambda item: item[0])
    age = observed_at.astimezone(UTC) - latest_time
    if age < timedelta(minutes=-1) or age > maximum_age:
        raise ValueError("wallet balance snapshot is stale")
    assets: list[str] = []
    for _, sync_run_id, payload in records:
        if sync_run_id != latest_run:
            continue
        asset = _eligible_wallet_asset(payload, minimum_value_usdt=minimum_value_usdt)
        if asset is not None:
            assets.append(asset)
    return WalletAssetSnapshot(
        assets=tuple(sorted(set(assets))),
        observed_at=latest_time,
        sync_run_id=latest_run,
    )


@dataclass(frozen=True, slots=True)
class ResearchMarketUniverseProvider:
    """Select wallet holdings plus filtered Binance-listed market-cap leaders."""

    binance: BinanceMarketUniverseProvider
    market_cap_transport: PublicMarketCapTransport
    wallet_balance_path: Path
    wallet_minimum_value_usdt: Decimal = Decimal("1")
    wallet_maximum_age: timedelta = timedelta(minutes=30)
    market_cap_asset_limit: int = 20
    market_cap_page_size: int = 100
    clock: Callable[[], datetime] = field(
        default=lambda: datetime.now(UTC), repr=False, compare=False
    )
    cache_filename: str = "universe-v3.json"
    cache_source: str = RESEARCH_MARKET_UNIVERSE_SOURCE

    def __post_init__(self) -> None:
        if not 1 <= self.market_cap_asset_limit <= 50:
            raise ValueError("market-cap asset limit must be between 1 and 50")
        if not self.market_cap_asset_limit <= self.market_cap_page_size <= 250:
            raise ValueError("market-cap page size is invalid")

    @property
    def spot_transport(self) -> object:
        return self.binance.spot_transport

    @property
    def futures_transport(self) -> object:
        return self.binance.futures_transport

    @property
    def coin_m_transport(self) -> None:
        return None

    def eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
        return self.binance.eligible_market_snapshot()

    def priority_eligible_market_snapshot(self) -> BinanceEligibleMarketSnapshot:
        """Return the strict union required by the research collection policy."""

        now = self._now()
        metadata = self.binance.eligible_market_snapshot()
        if metadata.blockers:
            return metadata
        try:
            wallet = read_wallet_assets_above_value(
                self.wallet_balance_path,
                observed_at=now,
                minimum_value_usdt=self.wallet_minimum_value_usdt,
                maximum_age=self.wallet_maximum_age,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._blocked(metadata, "WALLET_UNIVERSE_UNAVAILABLE_OR_STALE")
        try:
            rows = self.market_cap_transport.get_json(
                "/api/v3/coins/markets",
                {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": self.market_cap_page_size,
                    "page": 1,
                    "sparkline": "false",
                    "include_rehypothecated": "false",
                },
            )
            ranked_assets = self._ranked_assets(rows, metadata)
        except (
            ExchangeHttpError,
            ExchangePayloadError,
            ExchangeRateLimitError,
            ExchangeTransportError,
            TypeError,
            ValueError,
        ):
            return self._blocked(metadata, "PUBLIC_MARKET_CAP_UNIVERSE_UNAVAILABLE")
        if len(ranked_assets) < self.market_cap_asset_limit:
            return self._blocked(metadata, "PUBLIC_MARKET_CAP_UNIVERSE_INCOMPLETE")

        spot_by_asset = self._symbols_by_asset(metadata.spot_symbols)
        futures_by_asset = self._symbols_by_asset(metadata.futures_symbols)
        selected_assets: list[str] = []
        excluded = list(metadata.excluded_assets)
        for asset in (*wallet.assets, *ranked_assets):
            classification = classify_asset_eligibility(
                asset,
                spot_symbols=spot_by_asset.get(asset, ()),
                futures_symbols=futures_by_asset.get(asset, ()),
            )
            if classification.eligible:
                selected_assets.append(asset)
            else:
                excluded.append((asset, classification.exclusion_reasons))
        selected = tuple(sorted(set(selected_assets)))
        spot = tuple(
            sorted(
                symbol
                for asset in selected
                if (symbol := self._preferred_symbol(spot_by_asset.get(asset, ())))
            )
        )
        futures = tuple(
            sorted(
                symbol
                for asset in selected
                if (symbol := self._preferred_symbol(futures_by_asset.get(asset, ())))
            )
        )
        if not spot and not futures:
            return self._blocked(metadata, "RESEARCH_MARKET_UNIVERSE_EMPTY")
        return BinanceEligibleMarketSnapshot(
            spot_symbols=spot,
            futures_symbols=futures,
            excluded_assets=tuple(sorted(set(excluded))),
            source=RESEARCH_MARKET_UNIVERSE_SOURCE,
            selected_assets=selected,
            wallet_assets=tuple(
                asset for asset in wallet.assets if asset in frozenset(selected)
            ),
            market_cap_assets=tuple(
                asset for asset in ranked_assets if asset in frozenset(selected)
            ),
        )

    def _ranked_assets(
        self, rows: object, metadata: BinanceEligibleMarketSnapshot
    ) -> tuple[str, ...]:
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError("market-cap rows must be an array")
        spot_by_asset = self._symbols_by_asset(metadata.spot_symbols)
        futures_by_asset = self._symbols_by_asset(metadata.futures_symbols)
        accepted: list[tuple[int, str]] = []
        seen: set[str] = set()
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise ValueError("market-cap row must be an object")
            asset = str(raw.get("symbol", "")).strip().upper()
            name = str(raw.get("name", "")).strip()
            rank = raw.get("market_cap_rank")
            cap = raw.get("market_cap")
            if (
                not asset.isalnum()
                or asset in seen
                or not isinstance(rank, int)
                or rank < 1
                or not isinstance(cap, (int, float))
                or isinstance(cap, bool)
                or not math.isfinite(float(cap))
                or float(cap) <= 0
            ):
                continue
            classification = classify_asset_eligibility(
                asset,
                spot_symbols=spot_by_asset.get(asset, ()),
                futures_symbols=futures_by_asset.get(asset, ()),
                metadata_name=name,
            )
            if not classification.eligible:
                continue
            accepted.append((rank, asset))
            seen.add(asset)
        accepted.sort()
        return tuple(asset for _, asset in accepted[: self.market_cap_asset_limit])

    def _symbols_by_asset(self, symbols: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        quotes = tuple(sorted(self.binance.quote_assets, key=len, reverse=True))
        for symbol in symbols:
            quote = next((item for item in quotes if symbol.endswith(item)), None)
            if quote is None or len(symbol) == len(quote):
                continue
            grouped.setdefault(symbol[: -len(quote)], []).append(symbol)
        return {asset: tuple(sorted(items)) for asset, items in grouped.items()}

    def _preferred_symbol(self, symbols: tuple[str, ...]) -> str | None:
        for quote in self.binance.quote_assets:
            match = next((symbol for symbol in symbols if symbol.endswith(quote)), None)
            if match is not None:
                return match
        return symbols[0] if symbols else None

    def _blocked(
        self, metadata: BinanceEligibleMarketSnapshot, blocker: str
    ) -> BinanceEligibleMarketSnapshot:
        return BinanceEligibleMarketSnapshot(
            spot_symbols=(),
            futures_symbols=(),
            excluded_assets=metadata.excluded_assets,
            blockers=(blocker,),
            source=RESEARCH_MARKET_UNIVERSE_SOURCE,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("research universe clock must be timezone-aware")
        return value.astimezone(UTC)


__all__ = (
    "RESEARCH_MARKET_UNIVERSE_SOURCE",
    "ReadOnlyCoinGeckoJsonTransport",
    "ResearchMarketUniverseProvider",
    "WalletAssetSnapshot",
    "read_wallet_assets_above_value",
)
