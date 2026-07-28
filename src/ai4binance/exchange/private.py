"""Secret-safe request signing for whitelisted Binance Spot read endpoints."""

import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ai4binance.exchange.errors import (
    ExchangeHttpError,
    ExchangePayloadError,
    ExchangeTransportError,
)

READ_ONLY_PRIVATE_PATHS = frozenset(
    {
        "/api/v3/account",
        "/api/v3/allOrders",
        "/api/v3/openOrders",
        "/api/v3/myTrades",
        "/sapi/v1/asset/transfer",
    }
)
READ_ONLY_USD_M_PATHS = frozenset(
    {
        "/fapi/v1/algo/openOrders",
        "/fapi/v1/allOrders",
        "/fapi/v1/income",
        "/fapi/v1/leverageBracket",
        "/fapi/v1/multiAssetsMargin",
        "/fapi/v1/openOrders",
        "/fapi/v1/positionSide/dual",
        "/fapi/v1/userTrades",
        "/fapi/v2/account",
        "/fapi/v2/positionRisk",
        "/fapi/v3/account",
        "/fapi/v3/positionRisk",
    }
)
READ_ONLY_HOST_PATHS = {
    "api.binance.com": READ_ONLY_PRIVATE_PATHS,
    "fapi.binance.com": READ_ONLY_USD_M_PATHS,
}
_CREDENTIAL_FILE_PARTS = ("secrets", "bnc.env")
_CREDENTIAL_FILE_MAX_BYTES = 16_384
_CREDENTIAL_NAMES = frozenset({"BINANCE_API_KEY", "BINANCE_API_SECRET"})
_ENV_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


@dataclass(frozen=True, slots=True)
class PrivateCredentials:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not self.api_secret.strip():
            raise ValueError("Binance private credentials are required")

    @classmethod
    def from_environment(cls) -> "PrivateCredentials":
        return cls(
            api_key=os.environ.get("BINANCE_API_KEY", ""),
            api_secret=os.environ.get("BINANCE_API_SECRET", ""),
        )

    @classmethod
    def from_environment_or_file(cls, path: Path) -> "PrivateCredentials":
        """Load one complete credential pair without mutating process environment."""
        api_key = os.environ.get("BINANCE_API_KEY", "")
        api_secret = os.environ.get("BINANCE_API_SECRET", "")
        if api_key or api_secret:
            return cls(api_key=api_key, api_secret=api_secret)
        return cls.from_file(path)

    @classmethod
    def from_file(cls, path: Path) -> "PrivateCredentials":
        """Read only the two allowlisted credentials from Secrets/bnc.env."""
        resolved = _resolve_credentials_file(path)
        try:
            size = resolved.stat().st_size
            if size > _CREDENTIAL_FILE_MAX_BYTES:
                raise ValueError("Binance credential file exceeds the size limit")
            text = resolved.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Binance credential file must be UTF-8") from None
        except OSError:
            raise ValueError("Binance credential file cannot be read") from None
        values = _parse_credentials_file(text)
        return cls(
            api_key=values.get("BINANCE_API_KEY", ""),
            api_secret=values.get("BINANCE_API_SECRET", ""),
        )


def _resolve_credentials_file(path: Path) -> Path:
    if path.is_absolute() or tuple(part.casefold() for part in path.parts) != (
        _CREDENTIAL_FILE_PARTS
    ):
        raise ValueError("Binance credential file path is not allowlisted")
    expected = (Path.cwd() / "Secrets" / "bnc.env").resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise ValueError("Binance credential file is unavailable") from None
    if resolved != expected or not resolved.is_file():
        raise ValueError("Binance credential file path is not allowlisted")
    return resolved


def _parse_credentials_file(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assignment = _ENV_ASSIGNMENT.fullmatch(line)
        if assignment is None:
            raise ValueError("Binance credential file contains an invalid assignment")
        name, raw_value = assignment.groups()
        if name not in _CREDENTIAL_NAMES:
            continue
        if name in values:
            raise ValueError("Binance credential file contains a duplicate credential")
        value = raw_value.strip()
        if value[:1] in {'"', "'"} or value[-1:] in {'"', "'"}:
            if len(value) < 2 or value[0] != value[-1]:
                raise ValueError("Binance credential file contains invalid quoting")
            value = value[1:-1]
        values[name] = value
    return values


@dataclass(frozen=True, slots=True)
class SignedReadOnlyRequestFactory:
    """Create signed GET requests; reject every trading or write path."""

    credentials: PrivateCredentials = field(repr=False)
    base_url: str = "https://api.binance.com"
    receive_window_ms: int = 60_000
    clock_ms: Callable[[], int] = field(
        default=lambda: int(time.time() * 1000),
        repr=False,
    )

    def __post_init__(self) -> None:
        normalized = self.base_url.rstrip("/")
        if normalized != "https://api.binance.com":
            raise ValueError(
                "private Binance base URL must use the official HTTPS host"
            )
        if not 1_000 <= self.receive_window_ms <= 60_000:
            raise ValueError("receive_window_ms must be between 1000 and 60000")
        object.__setattr__(self, "base_url", normalized)

    def build(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> Request:
        if path not in READ_ONLY_PRIVATE_PATHS:
            raise ValueError("private endpoint is not approved for read-only access")
        supplied = dict(params or {})
        if any(key in supplied for key in {"timestamp", "recvWindow", "signature"}):
            raise ValueError("signed control parameters are managed internally")
        supplied["recvWindow"] = self.receive_window_ms
        supplied["timestamp"] = self.clock_ms()
        query = urlencode(sorted(supplied.items()))
        signature = hmac.new(
            self.credentials.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        url = f"{self.base_url}{path}?{query}&signature={signature}"
        return Request(  # noqa: S310  # nosec B310
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "AI4Binance/0.1",
                "X-MBX-APIKEY": self.credentials.api_key,
            },
            method="GET",
        )


@dataclass(frozen=True, slots=True)
class SignedUsdMReadOnlyRequestFactory:
    """Create signed USD-M GET requests without exposing an order-write path."""

    credentials: PrivateCredentials = field(repr=False)
    base_url: str = "https://fapi.binance.com"
    receive_window_ms: int = 60_000
    clock_ms: Callable[[], int] = field(
        default=lambda: int(time.time() * 1000),
        repr=False,
    )

    def __post_init__(self) -> None:
        normalized = self.base_url.rstrip("/")
        if normalized != "https://fapi.binance.com":
            raise ValueError("USD-M private base URL must use the official HTTPS host")
        if not 1_000 <= self.receive_window_ms <= 60_000:
            raise ValueError("receive_window_ms must be between 1000 and 60000")
        object.__setattr__(self, "base_url", normalized)

    def build(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> Request:
        if path not in READ_ONLY_USD_M_PATHS:
            raise ValueError("USD-M endpoint is not approved for read-only access")
        supplied = dict(params or {})
        if any(key in supplied for key in {"timestamp", "recvWindow", "signature"}):
            raise ValueError("signed control parameters are managed internally")
        supplied["recvWindow"] = self.receive_window_ms
        supplied["timestamp"] = self.clock_ms()
        query = urlencode(sorted(supplied.items()))
        signature = hmac.new(
            self.credentials.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        return Request(  # noqa: S310  # nosec B310
            f"{self.base_url}{path}?{query}&signature={signature}",
            headers={
                "Accept": "application/json",
                "User-Agent": "AI4Binance/0.1",
                "X-MBX-APIKEY": self.credentials.api_key,
            },
            method="GET",
        )


class PrivateRequestTransport(Protocol):
    def get_json(self, request: Request) -> object: ...


def _read_https_response(request: Request, timeout: float, limit: int) -> bytes:
    with urlopen(  # noqa: S310  # nosec B310
        request,
        timeout=timeout,
    ) as response:
        return cast(bytes, response.read(limit + 1))


@dataclass(frozen=True, slots=True)
class UrllibPrivateJsonTransport:
    """Bounded sender accepting only signed read-only Binance requests."""

    timeout_seconds: float = 10.0
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_response_bytes: int = 2_000_000
    response_loader: Callable[[Request, float, int], bytes] = field(
        default=_read_https_response,
        repr=False,
    )
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("private timeout_seconds must be positive")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("private max_attempts must be between 1 and 5")
        if self.backoff_seconds < 0 or self.max_response_bytes < 1024:
            raise ValueError("private transport bounds are invalid")

    def get_json(self, request: Request) -> object:
        path = self._validate_request(request)
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self.response_loader(
                    request,
                    self.timeout_seconds,
                    self.max_response_bytes,
                )
                if len(payload) > self.max_response_bytes:
                    raise ExchangePayloadError(
                        f"private exchange payload too large at {path}"
                    )
                try:
                    return json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, JSONDecodeError):
                    raise ExchangePayloadError(
                        f"invalid private exchange JSON at {path}"
                    ) from None
            except HTTPError as error:
                retryable = error.code in {418, 429} or 500 <= error.code <= 599
                if not retryable or attempt == self.max_attempts:
                    raise ExchangeHttpError(
                        f"private exchange HTTP {error.code} at {path}"
                    ) from None
            except (TimeoutError, URLError, OSError):
                if attempt == self.max_attempts:
                    raise ExchangeTransportError(
                        f"private exchange request failed at {path}"
                    ) from None
            self.sleeper(self.backoff_seconds * float(2 ** (attempt - 1)))
        raise ExchangeTransportError(f"private exchange request failed at {path}")

    @staticmethod
    def _validate_request(request: Request) -> str:
        parsed = urlparse(request.full_url)
        if request.method != "GET":
            raise ValueError("private transport accepts GET only")
        approved_paths = READ_ONLY_HOST_PATHS.get(parsed.netloc)
        if parsed.scheme != "https" or approved_paths is None:
            raise ValueError("private transport accepts official HTTPS host only")
        if parsed.path not in approved_paths:
            raise ValueError("private transport path is not read-only approved")
        if not request.get_header("X-mbx-apikey"):
            raise ValueError("private transport requires API key header")
        query_keys = {item.split("=", 1)[0] for item in parsed.query.split("&")}
        if not {"timestamp", "recvWindow", "signature"} <= query_keys:
            raise ValueError("private transport requires signed query controls")
        return parsed.path


@dataclass(frozen=True, slots=True)
class BinancePrivateAccountReader:
    """Read account state with no order creation surface."""

    requests: SignedReadOnlyRequestFactory
    transport: PrivateRequestTransport

    def account(self) -> object:
        return self.transport.get_json(self.requests.build("/api/v3/account"))

    def open_orders(self, symbol: str | None = None) -> object:
        params = {"symbol": self._symbol(symbol)} if symbol is not None else None
        return self.transport.get_json(
            self.requests.build("/api/v3/openOrders", params)
        )

    def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
        """Read Spot order history only; this method cannot mutate orders."""
        if not 1 <= limit <= 1_000:
            raise ValueError("order history limit must be between 1 and 1000")
        return self.transport.get_json(
            self.requests.build(
                "/api/v3/allOrders",
                {"symbol": self._symbol(symbol), "limit": limit},
            )
        )

    def trades(
        self,
        symbol: str,
        *,
        from_id: int | None = None,
        limit: int = 1_000,
    ) -> object:
        """Read Spot fills only; this method cannot create or mutate orders."""
        if not 1 <= limit <= 1_000:
            raise ValueError("trade history limit must be between 1 and 1000")
        if from_id is not None and from_id < 0:
            raise ValueError("trade history from_id cannot be negative")
        params: dict[str, str | int] = {
            "symbol": self._symbol(symbol),
            "limit": limit,
        }
        if from_id is not None:
            params["fromId"] = from_id
        return self.transport.get_json(self.requests.build("/api/v3/myTrades", params))

    def universal_transfers(
        self,
        transfer_type: str,
        *,
        limit: int = 100,
    ) -> object:
        """Read universal transfer history for Spot/Futures capital flows."""
        normalized = transfer_type.strip().upper()
        if normalized not in {"MAIN_UMFUTURE", "UMFUTURE_MAIN"}:
            raise ValueError("universal transfer type is not approved")
        if not 1 <= limit <= 100:
            raise ValueError("transfer history limit must be between 1 and 100")
        return self.transport.get_json(
            self.requests.build(
                "/sapi/v1/asset/transfer",
                {"type": normalized, "size": limit},
            )
        )

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized or not normalized.isascii() or not normalized.isalnum():
            raise ValueError("symbol must be ASCII alphanumeric")
        return normalized


@dataclass(frozen=True, slots=True)
class BinanceUsdMPrivateAccountReader:
    """Read USD-M account state; deliberately provides no write methods."""

    requests: SignedUsdMReadOnlyRequestFactory
    transport: PrivateRequestTransport

    def account(self) -> object:
        return self.transport.get_json(self.requests.build("/fapi/v2/account"))

    def positions(self, symbol: str | None = None) -> object:
        params = {"symbol": self._symbol(symbol)} if symbol is not None else None
        return self.transport.get_json(
            self.requests.build("/fapi/v2/positionRisk", params)
        )

    def open_orders(self, symbol: str | None = None) -> object:
        params = {"symbol": self._symbol(symbol)} if symbol is not None else None
        return self.transport.get_json(
            self.requests.build("/fapi/v1/openOrders", params)
        )

    def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
        """Read USD-M order history only; this method cannot mutate orders."""
        if not 1 <= limit <= 1_000:
            raise ValueError("USD-M order history limit must be between 1 and 1000")
        return self.transport.get_json(
            self.requests.build(
                "/fapi/v1/allOrders",
                {"symbol": self._symbol(symbol), "limit": limit},
            )
        )

    def trades(self, symbol: str, *, limit: int = 1_000) -> object:
        """Read USD-M fills only; this method cannot create or mutate orders."""
        if not 1 <= limit <= 1_000:
            raise ValueError("USD-M trade history limit must be between 1 and 1000")
        return self.transport.get_json(
            self.requests.build(
                "/fapi/v1/userTrades",
                {"symbol": self._symbol(symbol), "limit": limit},
            )
        )

    def income(self, symbol: str | None = None, *, limit: int = 1_000) -> object:
        """Read USD-M income ledger entries only."""
        if not 1 <= limit <= 1_000:
            raise ValueError("USD-M income limit must be between 1 and 1000")
        params: dict[str, str | int] = {"limit": limit}
        if symbol is not None:
            params["symbol"] = self._symbol(symbol)
        return self.transport.get_json(self.requests.build("/fapi/v1/income", params))

    def algo_open_orders(self, symbol: str | None = None) -> object:
        """Read USD-M conditional/algo open orders if the account API supports it."""
        params = {"symbol": self._symbol(symbol)} if symbol is not None else None
        return self.transport.get_json(
            self.requests.build("/fapi/v1/algo/openOrders", params)
        )

    def leverage_bracket(self, symbol: str | None = None) -> object:
        params = {"symbol": self._symbol(symbol)} if symbol is not None else None
        return self.transport.get_json(
            self.requests.build("/fapi/v1/leverageBracket", params)
        )

    def position_mode(self) -> object:
        return self.transport.get_json(
            self.requests.build("/fapi/v1/positionSide/dual")
        )

    def multi_assets_mode(self) -> object:
        return self.transport.get_json(
            self.requests.build("/fapi/v1/multiAssetsMargin")
        )

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized or not normalized.isascii() or not normalized.isalnum():
            raise ValueError("symbol must be ASCII alphanumeric")
        return normalized
