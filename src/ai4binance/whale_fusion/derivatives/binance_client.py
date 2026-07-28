"""GET-only Binance USD-M public REST collector with typed metric parsing."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai4binance.exchange.errors import (
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeTransportError,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

ALLOWED_PERIODS = frozenset({"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"})
ALLOWED_PATHS = frozenset(
    {
        "/fapi/v1/aggTrades",
        "/fapi/v1/depth",
        "/fapi/v1/fundingRate",
        "/fapi/v1/openInterest",
        "/fapi/v1/premiumIndex",
        "/futures/data/globalLongShortAccountRatio",
        "/futures/data/openInterestHist",
        "/futures/data/takerlongshortRatio",
        "/futures/data/topLongShortAccountRatio",
        "/futures/data/topLongShortPositionRatio",
    }
)


@dataclass(frozen=True, slots=True)
class UsdMFuturesPublicTransport:
    """Bounded public transport that rejects private and write endpoints."""

    base_url: str = "https://fapi.binance.com"
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    max_response_bytes: int = 8_000_000
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)

    def __post_init__(self) -> None:
        normalized = self.base_url.rstrip("/")
        if normalized != "https://fapi.binance.com":
            raise ValueError("USD-M base URL must use the official HTTPS host")
        if self.timeout_seconds <= 0 or not 1 <= self.max_attempts <= 5:
            raise ValueError("USD-M transport retry and timeout bounds are invalid")
        if self.backoff_seconds < 0 or self.max_response_bytes < 1024:
            raise ValueError("USD-M transport bounds are invalid")
        object.__setattr__(self, "base_url", normalized)

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object:
        if path not in ALLOWED_PATHS or "?" in path or "#" in path:
            raise ValueError("only approved Binance USD-M public paths are allowed")
        query = urlencode(sorted((params or {}).items()))
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._request_once(url, path)
            except HTTPError as error:
                retryable = error.code in {418, 429} or 500 <= error.code <= 599
                if not retryable or attempt == self.max_attempts:
                    raise ExchangeHttpError(
                        f"USD-M public HTTP {error.code} at {path}"
                    ) from None
                self.sleeper(self._delay(attempt, error.headers.get("Retry-After")))
            except (TimeoutError, URLError, OSError):
                if attempt == self.max_attempts:
                    raise ExchangeTransportError(
                        f"USD-M public request failed at {path}"
                    ) from None
                self.sleeper(self._delay(attempt, None))
        raise ExchangeTransportError(f"USD-M public request failed at {path}")

    def _request_once(self, url: str, path: str) -> object:
        request = Request(  # noqa: S310  # nosec B310
            url,
            headers={"Accept": "application/json", "User-Agent": "AI4Binance/0.1"},
            method="GET",
        )
        with urlopen(  # noqa: S310  # nosec B310
            request, timeout=self.timeout_seconds
        ) as response:
            payload = response.read(self.max_response_bytes + 1)
        if len(payload) > self.max_response_bytes:
            raise ExchangePayloadError(f"USD-M payload too large at {path}")
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, JSONDecodeError):
            raise ExchangePayloadError(f"invalid USD-M JSON at {path}") from None

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                parsed = max(0.0, float(retry_after))
            except ValueError:
                parsed = 0.0
            if parsed > 0:
                return min(parsed, self.max_backoff_seconds)
        return min(
            self.backoff_seconds * float(2 ** (attempt - 1)),
            self.max_backoff_seconds,
        )


class JsonTransport(Protocol):
    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class BinanceUsdMClient:
    """Parse public USD-M market statistics without credentials or orders."""

    transport: JsonTransport
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)

    def collect(
        self, symbol: str, period: str = "1h", limit: int = 100
    ) -> DerivativesDataset:
        normalized = self._symbol(symbol)
        self._bounds(period, limit)
        series: dict[DerivativesMetric, tuple[MetricPoint, ...]] = {}
        series.update(self._open_interest_series(normalized, period, limit))
        for metric, path in (
            (
                DerivativesMetric.TOP_ACCOUNT_RATIO,
                "/futures/data/topLongShortAccountRatio",
            ),
            (
                DerivativesMetric.TOP_POSITION_RATIO,
                "/futures/data/topLongShortPositionRatio",
            ),
            (
                DerivativesMetric.GLOBAL_ACCOUNT_RATIO,
                "/futures/data/globalLongShortAccountRatio",
            ),
            (
                DerivativesMetric.TAKER_BUY_SELL_RATIO,
                "/futures/data/takerlongshortRatio",
            ),
        ):
            series[metric] = self._history(
                path, normalized, period, limit, metric, self._field(metric)
            )
        series[DerivativesMetric.FUNDING_RATE] = self._history(
            "/fapi/v1/fundingRate",
            normalized,
            period,
            limit,
            DerivativesMetric.FUNDING_RATE,
            "fundingRate",
            timestamp_field="fundingTime",
            include_period=False,
        )
        premium = self._mapping(
            self.transport.get_json("/fapi/v1/premiumIndex", {"symbol": normalized}),
            "premiumIndex",
        )
        timestamp = self._timestamp(premium.get("time"), "premiumIndex.time")
        observed_at = self.clock()
        premium_values: dict[DerivativesMetric, Decimal] = {}
        for metric, field_name in (
            (DerivativesMetric.MARK_PRICE, "markPrice"),
            (DerivativesMetric.INDEX_PRICE, "indexPrice"),
        ):
            value = self._decimal(premium.get(field_name), metric.value)
            premium_values[metric] = value
            series[metric] = (self._point(metric, timestamp, value, observed_at),)
        index_price = premium_values[DerivativesMetric.INDEX_PRICE]
        if index_price != Decimal("0"):
            basis_rate = (
                premium_values[DerivativesMetric.MARK_PRICE] - index_price
            ) / index_price
            series[DerivativesMetric.BASIS_RATE] = (
                self._point(
                    DerivativesMetric.BASIS_RATE,
                    timestamp,
                    basis_rate,
                    observed_at,
                ),
            )
        return DerivativesDataset(normalized, observed_at, series)

    def current_open_interest(self, symbol: str) -> MetricPoint:
        normalized = self._symbol(symbol)
        payload = self._mapping(
            self.transport.get_json("/fapi/v1/openInterest", {"symbol": normalized}),
            "openInterest",
        )
        observed_at = self.clock()
        return self._point(
            DerivativesMetric.OPEN_INTEREST,
            self._timestamp(payload.get("time"), "openInterest.time"),
            payload.get("openInterest"),
            observed_at,
        )

    def order_book_imbalance(self, symbol: str, limit: int = 100) -> MetricPoint:
        """Return public depth notional imbalance in the closed interval [-1, 1]."""
        normalized = self._symbol(symbol)
        if limit not in {5, 10, 20, 50, 100, 500, 1000}:
            raise ValueError("USD-M depth limit is outside approved bounds")
        payload = self._mapping(
            self.transport.get_json(
                "/fapi/v1/depth", {"symbol": normalized, "limit": limit}
            ),
            "depth",
        )
        bid_notional = self._book_notional(payload.get("bids"), "depth.bids")
        ask_notional = self._book_notional(payload.get("asks"), "depth.asks")
        total = bid_notional + ask_notional
        if total <= Decimal("0"):
            raise ExchangePayloadError("depth notional must be positive")
        return self._point(
            DerivativesMetric.ORDER_BOOK_IMBALANCE,
            self.clock(),
            (bid_notional - ask_notional) / total,
            self.clock(),
        )

    def large_aggregate_trades(
        self,
        symbol: str,
        *,
        limit: int = 500,
        minimum_notional: Decimal = Decimal("100000"),
    ) -> tuple[MetricPoint, ...]:
        """Normalize public aggregate trades above a deterministic notional floor."""
        normalized = self._symbol(symbol)
        if not 1 <= limit <= 1000 or minimum_notional <= Decimal("0"):
            raise ValueError("aggregate-trade bounds are invalid")
        payload = self._sequence(
            self.transport.get_json(
                "/fapi/v1/aggTrades", {"symbol": normalized, "limit": limit}
            ),
            "aggTrades",
        )
        observed_at = self.clock()
        points: list[MetricPoint] = []
        for raw in payload:
            row = self._mapping(raw, "aggTrades.row")
            price = self._decimal(row.get("p"), "aggTrades.price")
            quantity = self._decimal(row.get("q"), "aggTrades.quantity")
            notional = price * quantity
            if notional < minimum_notional:
                continue
            buyer_is_maker = row.get("m")
            if not isinstance(buyer_is_maker, bool):
                raise ExchangePayloadError("aggTrades.m must be boolean")
            points.append(
                MetricPoint(
                    DerivativesMetric.LARGE_TRADE_NOTIONAL,
                    self._timestamp(row.get("T"), "aggTrades.time"),
                    notional,
                    Provenance(
                        "BINANCE_USD_M_PUBLIC_REST",
                        observed_at,
                        "https://fapi.binance.com",
                    ),
                    attributes={"aggressor_side": "SELL" if buyer_is_maker else "BUY"},
                )
            )
        return tuple(points)

    def liquidation_event(self, payload: object) -> MetricPoint:
        """Normalize one public force-order WebSocket event without opening a socket."""
        event = self._mapping(payload, "forceOrder")
        order = self._mapping(event.get("o"), "forceOrder.order")
        symbol = self._symbol(str(order.get("s", "")))
        price = self._decimal(order.get("ap"), "forceOrder.average_price")
        if price == Decimal("0"):
            price = self._decimal(order.get("p"), "forceOrder.price")
        quantity = self._decimal(order.get("q"), "forceOrder.quantity")
        side = order.get("S")
        if side not in {"BUY", "SELL"}:
            raise ExchangePayloadError("forceOrder side is invalid")
        observed_at = self.clock()
        return MetricPoint(
            DerivativesMetric.LIQUIDATION_NOTIONAL,
            self._timestamp(event.get("E"), "forceOrder.event_time"),
            price * quantity,
            Provenance(
                "BINANCE_USD_M_PUBLIC_WEBSOCKET",
                observed_at,
                "https://fstream.binance.com",
            ),
            attributes={"symbol": symbol, "side": side},
        )

    def _open_interest_series(
        self, symbol: str, period: str, limit: int
    ) -> dict[DerivativesMetric, tuple[MetricPoint, ...]]:
        payload = self._sequence(
            self.transport.get_json(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": limit},
            ),
            "openInterestHist",
        )
        observed_at = self.clock()
        oi: list[MetricPoint] = []
        oi_value: list[MetricPoint] = []
        for raw in payload:
            row = self._mapping(raw, "openInterestHist.row")
            timestamp = self._timestamp(row.get("timestamp"), "timestamp")
            oi.append(
                self._point(
                    DerivativesMetric.OPEN_INTEREST,
                    timestamp,
                    row.get("sumOpenInterest"),
                    observed_at,
                )
            )
            oi_value.append(
                self._point(
                    DerivativesMetric.OPEN_INTEREST_VALUE,
                    timestamp,
                    row.get("sumOpenInterestValue"),
                    observed_at,
                )
            )
        return {
            DerivativesMetric.OPEN_INTEREST: tuple(oi),
            DerivativesMetric.OPEN_INTEREST_VALUE: tuple(oi_value),
        }

    def _history(
        self,
        path: str,
        symbol: str,
        period: str,
        limit: int,
        metric: DerivativesMetric,
        value_field: str,
        *,
        timestamp_field: str = "timestamp",
        include_period: bool = True,
    ) -> tuple[MetricPoint, ...]:
        params: dict[str, str | int] = {"symbol": symbol, "limit": limit}
        if include_period:
            params["period"] = period
        payload = self._sequence(self.transport.get_json(path, params), path)
        observed_at = self.clock()
        return tuple(
            self._point(
                metric,
                self._timestamp(
                    self._mapping(raw, path).get(timestamp_field), timestamp_field
                ),
                self._mapping(raw, path).get(value_field),
                observed_at,
            )
            for raw in payload
        )

    @classmethod
    def _book_notional(cls, value: object, name: str) -> Decimal:
        levels = cls._sequence(value, name)
        total = Decimal("0")
        for raw in levels:
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise ExchangePayloadError(
                    f"{name} level must contain price and quantity"
                )
            total += cls._decimal(raw[0], f"{name}.price") * cls._decimal(
                raw[1], f"{name}.quantity"
            )
        return total

    @staticmethod
    def _field(metric: DerivativesMetric) -> str:
        return {
            DerivativesMetric.TOP_ACCOUNT_RATIO: "longShortRatio",
            DerivativesMetric.TOP_POSITION_RATIO: "longShortRatio",
            DerivativesMetric.GLOBAL_ACCOUNT_RATIO: "longShortRatio",
            DerivativesMetric.TAKER_BUY_SELL_RATIO: "buySellRatio",
        }[metric]

    @classmethod
    def _point(
        cls,
        metric: DerivativesMetric,
        timestamp: datetime,
        raw_value: object,
        observed_at: datetime,
    ) -> MetricPoint:
        return MetricPoint(
            metric,
            timestamp,
            cls._decimal(raw_value, metric.value),
            Provenance(
                "BINANCE_USD_M_PUBLIC_REST", observed_at, "https://fapi.binance.com"
            ),
        )

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized or not normalized.isascii() or not normalized.isalnum():
            raise ValueError("USD-M symbol must be ASCII alphanumeric")
        return normalized

    @staticmethod
    def _bounds(period: str, limit: int) -> None:
        if period not in ALLOWED_PERIODS or not 1 <= limit <= 500:
            raise ValueError("USD-M period or limit is outside approved bounds")

    @staticmethod
    def _mapping(value: object, name: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ExchangePayloadError(f"{name} must be an object")
        return cast(Mapping[str, object], value)

    @staticmethod
    def _sequence(value: object, name: str) -> Sequence[object]:
        if not isinstance(value, (list, tuple)):
            raise ExchangePayloadError(f"{name} must be an array")
        return cast(Sequence[object], value)

    @staticmethod
    def _timestamp(value: object, name: str) -> datetime:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExchangePayloadError(f"{name} must be an integer timestamp")
        return datetime.fromtimestamp(value / 1000, tz=UTC)

    @staticmethod
    def _decimal(value: object, name: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ExchangePayloadError(f"{name} must be decimal-compatible")
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            raise ExchangePayloadError(f"{name} must be decimal-compatible") from None
        if not parsed.is_finite():
            raise ExchangePayloadError(f"{name} must be finite")
        return parsed
