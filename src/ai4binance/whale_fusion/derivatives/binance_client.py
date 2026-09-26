"""GET-only Binance USD-M public REST collector with typed metric parsing."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai4binance.core.errors import (
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
        "/fapi/v1/markPriceKlines",
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

    def replay_history(
        self,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        *,
        observed_at: datetime | None = None,
    ) -> DerivativesDataset:
        """Return exact public REST derivatives for a bounded closed replay window.

        This is intentionally not a fill-forward facility.  The caller receives
        only timestamps Binance publishes; replay ingestion verifies that every
        required candle timestamp is present before admitting the dataset.
        """

        normalized = self._symbol(symbol)
        self._bounds(period, 1)
        normalized_start, normalized_end = self._replay_window(start, end, period)
        observation = observed_at or self.clock()
        if observation.tzinfo is None or observation.utcoffset() is None:
            raise ValueError("replay observed_at must be timezone-aware")
        observation = observation.astimezone(UTC)
        if observation < normalized_end:
            raise ValueError("replay observed_at precedes requested history")

        open_interest_rows = self._replay_pages(
            "/futures/data/openInterestHist",
            {"symbol": normalized, "period": period},
            normalized_start,
            normalized_end,
            period=period,
            timestamp_field="timestamp",
        )
        mark_rows = self._replay_pages(
            "/fapi/v1/markPriceKlines",
            {"symbol": normalized, "interval": period},
            normalized_start,
            normalized_end,
            period=period,
            timestamp_field=0,
        )
        funding_rows = self._replay_pages(
            "/fapi/v1/fundingRate",
            {"symbol": normalized},
            normalized_start,
            normalized_end,
            period=None,
            timestamp_field="fundingTime",
        )

        def provenance(path: str) -> Provenance:
            return Provenance(
                "BINANCE_USD_M_PUBLIC_REST",
                observation,
                f"https://fapi.binance.com{path}",
            )

        def mapping(row: object, label: str) -> Mapping[str, object]:
            return self._mapping(row, label)

        open_interest = tuple(
            MetricPoint(
                DerivativesMetric.OPEN_INTEREST,
                self._timestamp(
                    mapping(row, "openInterestHist").get("timestamp"), "timestamp"
                ),
                self._decimal(
                    mapping(row, "openInterestHist").get("sumOpenInterest"),
                    DerivativesMetric.OPEN_INTEREST.value,
                ),
                provenance("/futures/data/openInterestHist"),
            )
            for row in open_interest_rows
        )
        open_interest_value = tuple(
            MetricPoint(
                DerivativesMetric.OPEN_INTEREST_VALUE,
                self._timestamp(
                    mapping(row, "openInterestHist").get("timestamp"), "timestamp"
                ),
                self._decimal(
                    mapping(row, "openInterestHist").get("sumOpenInterestValue"),
                    DerivativesMetric.OPEN_INTEREST_VALUE.value,
                ),
                provenance("/futures/data/openInterestHist"),
            )
            for row in open_interest_rows
        )
        mark_price = tuple(
            MetricPoint(
                DerivativesMetric.MARK_PRICE,
                self._timestamp(self._sequence(row, "markPriceKlines")[0], "openTime"),
                self._decimal(
                    self._sequence(row, "markPriceKlines")[4],
                    DerivativesMetric.MARK_PRICE.value,
                ),
                provenance("/fapi/v1/markPriceKlines"),
                attributes={
                    "mark_open": str(self._sequence(row, "markPriceKlines")[1]),
                    "mark_high": str(self._sequence(row, "markPriceKlines")[2]),
                    "mark_low": str(self._sequence(row, "markPriceKlines")[3]),
                },
            )
            for row in mark_rows
        )
        funding = tuple(
            MetricPoint(
                DerivativesMetric.FUNDING_RATE,
                self._timestamp(
                    mapping(row, "fundingRate").get("fundingTime"), "fundingTime"
                ),
                self._decimal(
                    mapping(row, "fundingRate").get("fundingRate"),
                    DerivativesMetric.FUNDING_RATE.value,
                ),
                provenance("/fapi/v1/fundingRate"),
            )
            for row in funding_rows
        )
        return DerivativesDataset(
            normalized,
            observation,
            {
                DerivativesMetric.MARK_PRICE: mark_price,
                DerivativesMetric.OPEN_INTEREST: open_interest,
                DerivativesMetric.OPEN_INTEREST_VALUE: open_interest_value,
                DerivativesMetric.FUNDING_RATE: funding,
            },
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

    def _replay_pages(
        self,
        path: str,
        base_params: Mapping[str, str | int],
        start: datetime,
        end: datetime,
        *,
        period: str | None,
        timestamp_field: str | int,
    ) -> tuple[object, ...]:
        """Read an exact bounded public history without overlapping pages."""

        cursor = int(start.timestamp() * 1000)
        end_milliseconds = int(end.timestamp() * 1000)
        step = self._period_milliseconds(period) if period is not None else 1
        rows: list[object] = []
        previous_timestamp: int | None = None
        while cursor < end_milliseconds:
            page_end = end_milliseconds
            if period is not None:
                # Binance returns the most recent `limit` points when a wider
                # range is supplied. Bound each request to one exact page so
                # cursor advancement cannot silently skip earlier history.
                page_end = min(end_milliseconds, cursor + (500 * step))
            params = {
                **base_params,
                "startTime": cursor,
                "endTime": page_end - 1,
                "limit": 500,
            }
            payload = self._sequence(self.transport.get_json(path, params), path)
            if not payload:
                break
            last_timestamp: int | None = None
            for row in payload:
                timestamp = self._row_milliseconds(row, path, timestamp_field)
                if not cursor <= timestamp < end_milliseconds:
                    raise ExchangePayloadError(
                        f"{path} replay timestamp is out of range"
                    )
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    raise ExchangePayloadError(
                        f"{path} replay timestamps are not chronological"
                    )
                rows.append(row)
                previous_timestamp = timestamp
                last_timestamp = timestamp
            if last_timestamp is None:
                break
            next_cursor = last_timestamp + step
            if next_cursor <= cursor:
                raise ExchangePayloadError(f"{path} replay pagination did not advance")
            cursor = next_cursor
            if len(payload) < 500:
                break
        return tuple(rows)

    @staticmethod
    def _replay_window(
        start: datetime,
        end: datetime,
        period: str,
    ) -> tuple[datetime, datetime]:
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("replay start must be timezone-aware")
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError("replay end must be timezone-aware")
        normalized_start = start.astimezone(UTC)
        normalized_end = end.astimezone(UTC)
        if (
            normalized_end <= normalized_start
            or normalized_end - normalized_start > timedelta(days=30)
        ):
            raise ValueError("replay history must be between one instant and 30 days")
        period_milliseconds = BinanceUsdMClient._period_milliseconds(period)
        if int(normalized_start.timestamp() * 1000) % period_milliseconds:
            raise ValueError("replay start must align to its requested period")
        if int(normalized_end.timestamp() * 1000) % period_milliseconds:
            raise ValueError("replay end must align to its requested period")
        return normalized_start, normalized_end

    @staticmethod
    def _period_milliseconds(period: str) -> int:
        return {
            "5m": 5 * 60_000,
            "15m": 15 * 60_000,
            "30m": 30 * 60_000,
            "1h": 60 * 60_000,
            "2h": 2 * 60 * 60_000,
            "4h": 4 * 60 * 60_000,
            "6h": 6 * 60 * 60_000,
            "12h": 12 * 60 * 60_000,
            "1d": 24 * 60 * 60_000,
        }[period]

    @classmethod
    def _row_milliseconds(
        cls,
        row: object,
        path: str,
        timestamp_field: str | int,
    ) -> int:
        if isinstance(timestamp_field, str):
            raw = cls._mapping(row, path).get(timestamp_field)
        else:
            values = cls._sequence(row, path)
            if len(values) <= timestamp_field:
                raise ExchangePayloadError(f"{path} replay row is incomplete")
            raw = values[timestamp_field]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ExchangePayloadError(f"{path} replay timestamp is invalid")
        return raw

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
