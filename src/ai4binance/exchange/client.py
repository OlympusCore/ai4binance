"""Typed public market parser with explicitly separated Spot and USD-M klines."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.exchange.models import BookTicker, FilterValue, MarketKline, SymbolInfo

SUPPORTED_INTERVALS = frozenset(
    {
        "1s",
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    }
)


class JsonTransport(Protocol):
    """Minimal injectable transport used by the public client."""

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> object: ...


class PublicMarketDataClient(Protocol):
    """Read-only exchange contract required by data acquisition."""

    def server_time(self) -> datetime: ...

    def exchange_info(self, symbol: str) -> SymbolInfo: ...

    def ticker_price(self, symbol: str) -> Decimal: ...

    def book_ticker(self, symbol: str) -> BookTicker: ...

    def klines(
        self, symbol: str, interval: str, limit: int
    ) -> tuple[MarketKline, ...]: ...


class BinancePublicClient:
    """Public-only market client with no key or order methods."""

    def __init__(self, transport: JsonTransport) -> None:
        self._transport = transport

    def server_time(self) -> datetime:
        payload = self._mapping(self._transport.get_json("/api/v3/time"), "time")
        milliseconds = self._integer(payload.get("serverTime"), "serverTime")
        return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)

    def exchange_info(self, symbol: str) -> SymbolInfo:
        normalized = self._symbol(symbol)
        payload = self._mapping(
            self._transport.get_json("/api/v3/exchangeInfo", {"symbol": normalized}),
            "exchangeInfo",
        )
        symbols = self._sequence(payload.get("symbols"), "symbols")
        if len(symbols) != 1:
            raise ExchangePayloadError("exchangeInfo must contain exactly one symbol")
        item = self._mapping(symbols[0], "symbol")
        filters_payload = self._sequence(item.get("filters"), "filters")
        parsed_filters: dict[str, Mapping[str, FilterValue]] = {}
        for raw_filter in filters_payload:
            filter_mapping = self._mapping(raw_filter, "filter")
            filter_type = filter_mapping.get("filterType")
            if not isinstance(filter_type, str) or not filter_type:
                raise ExchangePayloadError("exchange filterType is invalid")
            parsed_filters[filter_type] = {
                str(key): self._filter_value(value)
                for key, value in filter_mapping.items()
                if key != "filterType"
            }
        return SymbolInfo(
            symbol=self._string(item.get("symbol"), "symbol"),
            status=self._string(item.get("status"), "status"),
            base_asset=self._string(item.get("baseAsset"), "baseAsset"),
            quote_asset=self._string(item.get("quoteAsset"), "quoteAsset"),
            filters=parsed_filters,
        )

    def ticker_price(self, symbol: str) -> Decimal:
        normalized = self._symbol(symbol)
        payload = self._mapping(
            self._transport.get_json("/api/v3/ticker/price", {"symbol": normalized}),
            "tickerPrice",
        )
        return self._decimal(payload.get("price"), "price")

    def book_ticker(self, symbol: str) -> BookTicker:
        normalized = self._symbol(symbol)
        payload = self._mapping(
            self._transport.get_json(
                "/api/v3/ticker/bookTicker",
                {"symbol": normalized},
            ),
            "bookTicker",
        )
        return BookTicker(
            bid=self._decimal(payload.get("bidPrice"), "bidPrice"),
            ask=self._decimal(payload.get("askPrice"), "askPrice"),
        )

    def klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        *,
        market_type: str = "SPOT",
    ) -> tuple[MarketKline, ...]:
        normalized = self._symbol(symbol)
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(f"unsupported Binance interval: {interval}")
        if not 1 <= limit <= 1000:
            raise ValueError("kline limit must be between 1 and 1000")
        paths = {"SPOT": "/api/v3/klines", "USD_M_FUTURES": "/fapi/v1/klines"}
        if market_type not in paths:
            raise ValueError("public kline market is unsupported")
        payload = self._sequence(
            self._transport.get_json(
                paths[market_type],
                {"symbol": normalized, "interval": interval, "limit": limit},
            ),
            "klines",
        )
        klines: list[MarketKline] = []
        for raw_kline in payload:
            values = self._sequence(raw_kline, "kline")
            if len(values) < 7:
                raise ExchangePayloadError("kline must contain at least seven values")
            klines.append(
                MarketKline(
                    open_time=self._milliseconds(values[0], "kline.open_time"),
                    close_time=self._milliseconds(values[6], "kline.close_time"),
                    open=self._decimal(values[1], "kline.open"),
                    high=self._decimal(values[2], "kline.high"),
                    low=self._decimal(values[3], "kline.low"),
                    close=self._decimal(values[4], "kline.close"),
                    volume=self._decimal(values[5], "kline.volume"),
                )
            )
        return tuple(klines)

    @staticmethod
    def _symbol(value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not normalized.isascii() or not normalized.isalnum():
            raise ValueError("symbol must be non-empty ASCII alphanumeric text")
        return normalized

    @staticmethod
    def _mapping(value: object, field_name: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ExchangePayloadError(f"{field_name} must be an object")
        return cast(Mapping[str, object], value)

    @staticmethod
    def _sequence(value: object, field_name: str) -> Sequence[object]:
        if not isinstance(value, (list, tuple)):
            raise ExchangePayloadError(f"{field_name} must be an array")
        return cast(Sequence[object], value)

    @staticmethod
    def _string(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ExchangePayloadError(f"{field_name} must be non-empty text")
        return value

    @staticmethod
    def _integer(value: object, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExchangePayloadError(f"{field_name} must be an integer")
        return value

    @classmethod
    def _milliseconds(cls, value: object, field_name: str) -> datetime:
        milliseconds = cls._integer(value, field_name)
        return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)

    @staticmethod
    def _decimal(value: object, field_name: str) -> Decimal:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ExchangePayloadError(f"{field_name} must be numeric text")
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            raise ExchangePayloadError(
                f"{field_name} must be decimal-compatible"
            ) from None
        if not parsed.is_finite() or parsed < Decimal("0"):
            raise ExchangePayloadError(f"{field_name} must be finite and non-negative")
        return parsed

    @staticmethod
    def _filter_value(value: object) -> FilterValue:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ExchangePayloadError("exchange filter contains an unsupported value")
