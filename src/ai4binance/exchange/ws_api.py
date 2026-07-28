"""Ed25519 Binance Spot WebSocket API with a bounded trust surface."""

from __future__ import annotations

import base64
import importlib
import json
import os
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Protocol, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SPOT_WS_URL = "wss://ws-api.binance.com:443/ws-api/v3"
SPOT_TESTNET_WS_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"
APPROVED_WS_URLS = frozenset({SPOT_WS_URL, SPOT_TESTNET_WS_URL})
READ_ONLY_WS_METHODS = frozenset({"account.status", "openOrders.status"})
ORDER_WS_METHODS = frozenset({"order.test", "order.place", "order.cancel"})
_KEY_PARTS = ("secrets", "binance_ed25519_private.pem")
_MAX_KEY_BYTES = 32_768


class SpotWsRequestTransport(Protocol):
    """Injectable request/response boundary used by authenticated sessions."""

    def request(self, method: str, params: Mapping[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
class Ed25519Credentials:
    """Secret-safe API identity backed by one allowlisted PEM path."""

    api_key: str = field(repr=False)
    private_key_path: Path = field(repr=False)
    passphrase: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Ed25519 API key is required")
        if (
            self.private_key_path.is_absolute()
            or tuple(part.casefold() for part in self.private_key_path.parts)
            != _KEY_PARTS
        ):
            raise ValueError("Ed25519 private key path is not allowlisted")

    @classmethod
    def from_environment(cls) -> Ed25519Credentials:
        passphrase = os.environ.get("BINANCE_ED25519_PRIVATE_KEY_PASSPHRASE")
        return cls(
            api_key=os.environ.get("BINANCE_API_KEY", ""),
            private_key_path=Path("Secrets/binance_ed25519_private.pem"),
            passphrase=passphrase or None,
        )

    def load_private_key(self) -> Ed25519PrivateKey:
        expected = (Path.cwd() / "Secrets" / "binance_ed25519_private.pem").resolve()
        try:
            resolved = self.private_key_path.resolve(strict=True)
            if resolved != expected or not resolved.is_file():
                raise ValueError("Ed25519 private key path is not allowlisted")
            payload = resolved.read_bytes()
        except OSError:
            raise ValueError("Ed25519 private key is unavailable") from None
        if len(payload) > _MAX_KEY_BYTES:
            raise ValueError("Ed25519 private key exceeds the size limit")
        try:
            loaded = serialization.load_pem_private_key(
                payload,
                password=self.passphrase.encode() if self.passphrase else None,
            )
        except (TypeError, ValueError):
            raise ValueError("Ed25519 private key cannot be loaded") from None
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("private key must be Ed25519")
        return loaded


def signature_payload(params: Mapping[str, object]) -> str:
    """Return Binance's canonical alphabetically sorted signature payload."""
    pairs = (
        (str(key), _signature_value(value))
        for key, value in params.items()
        if key != "signature" and value is not None
    )
    return "&".join(f"{key}={value}" for key, value in sorted(pairs))


def _signature_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@dataclass(frozen=True, slots=True)
class Ed25519RequestSigner:
    credentials: Ed25519Credentials = field(repr=False)

    def sign(self, params: Mapping[str, object]) -> str:
        signature = self.credentials.load_private_key().sign(
            signature_payload(params).encode("utf-8")
        )
        return base64.b64encode(signature).decode("ascii")


class BinanceWsApiError(RuntimeError):
    """Sanitized exchange failure without echoing request secrets."""

    def __init__(self, status: int, code: int | None = None) -> None:
        self.status = status
        self.code = code
        super().__init__(f"Binance WebSocket API rejected request: {status}/{code}")


@dataclass(slots=True)
class BinanceSpotWsConnection:
    """Synchronous bounded WS request multiplexer for official Binance hosts."""

    url: str = SPOT_WS_URL
    request_timeout_seconds: float = 10.0
    connect_timeout_seconds: float = 10.0
    max_unsolicited_messages: int = 100
    connection_factory: Callable[..., object] | None = field(default=None, repr=False)
    _connection: object | None = field(default=None, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    unsolicited_messages: deque[dict[str, object]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.url not in APPROVED_WS_URLS:
            raise ValueError("Spot WebSocket URL is not allowlisted")
        if not 0.1 <= self.request_timeout_seconds <= 30:
            raise ValueError("WS request timeout is outside the safe range")
        if not 1 <= self.max_unsolicited_messages <= 1_000:
            raise ValueError("WS unsolicited queue bound is invalid")
        self.unsolicited_messages = deque(maxlen=self.max_unsolicited_messages)

    def connect(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            factory = self.connection_factory
            if factory is None:
                module = importlib.import_module("websockets.sync.client")
                factory = cast(Callable[..., object], module.connect)
            self._connection = factory(
                self.url,
                open_timeout=self.connect_timeout_seconds,
                close_timeout=5.0,
                ping_interval=20.0,
                ping_timeout=20.0,
                max_size=2_000_000,
            )

    def close(self) -> None:
        with self._lock:
            connection, self._connection = self._connection, None
            if connection is not None:
                close = getattr(connection, "close", None)
                if callable(close):
                    close()

    def request(self, method: str, params: Mapping[str, object]) -> object:
        if method not in {"session.logon", *READ_ONLY_WS_METHODS, *ORDER_WS_METHODS}:
            raise ValueError("WebSocket API method is not allowlisted")
        with self._lock:
            self.connect()
            if self._connection is None:
                raise RuntimeError("Spot WebSocket connection is unavailable")
            request_id = str(uuid.uuid4())
            payload = {"id": request_id, "method": method, "params": dict(params)}
            sender = getattr(self._connection, "send", None)
            receiver = getattr(self._connection, "recv", None)
            if not callable(sender) or not callable(receiver):
                raise RuntimeError("Spot WebSocket connection contract is invalid")
            sender(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            deadline = time.monotonic() + self.request_timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Spot WebSocket API response timed out")
                raw = receiver(timeout=remaining)
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    message = json.loads(cast(str, raw))
                except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
                    raise ValueError(
                        "Spot WebSocket API returned invalid JSON"
                    ) from None
                if not isinstance(message, dict):
                    raise ValueError("Spot WebSocket API response must be an object")
                normalized = cast(dict[str, object], message)
                if normalized.get("id") != request_id:
                    self.unsolicited_messages.append(normalized)
                    continue
                status = _integer(normalized.get("status"), "status")
                if status != 200:
                    error = normalized.get("error")
                    code = (
                        _integer(error.get("code"), "error code")
                        if isinstance(error, dict) and error.get("code") is not None
                        else None
                    )
                    raise BinanceWsApiError(status, code)
                return normalized.get("result")


@dataclass(slots=True)
class BinanceEd25519SpotSession:
    """Authenticated Spot session; read methods remain separate from live execution."""

    transport: SpotWsRequestTransport
    credentials: Ed25519Credentials = field(repr=False)
    receive_window_ms: int = 60_000
    clock_ms: Callable[[], int] = field(
        default=lambda: int(time.time() * 1_000), repr=False
    )
    _authenticated: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 1_000 <= self.receive_window_ms <= 60_000:
            raise ValueError("receive_window_ms must be between 1000 and 60000")

    def logon(self) -> object:
        params: dict[str, object] = {
            "apiKey": self.credentials.api_key,
            "recvWindow": self.receive_window_ms,
            "timestamp": self.clock_ms(),
        }
        params["signature"] = Ed25519RequestSigner(self.credentials).sign(params)
        result = self.transport.request("session.logon", params)
        self._authenticated = True
        return result

    def account_status(self) -> object:
        return self._read("account.status")

    def open_orders(self, symbol: str | None = None) -> object:
        params = {"symbol": _symbol(symbol)} if symbol is not None else {}
        return self._read("openOrders.status", params)

    def order_test(self, params: Mapping[str, object]) -> object:
        return self._authenticated_request("order.test", params)

    def order_place(self, params: Mapping[str, object]) -> object:
        return self._authenticated_request("order.place", params)

    def order_cancel(self, params: Mapping[str, object]) -> object:
        return self._authenticated_request("order.cancel", params)

    def _read(self, method: str, params: Mapping[str, object] | None = None) -> object:
        if method not in READ_ONLY_WS_METHODS:
            raise ValueError("method is not read-only allowlisted")
        return self._authenticated_request(method, params or {})

    def _authenticated_request(
        self, method: str, params: Mapping[str, object]
    ) -> object:
        if not self._authenticated:
            raise RuntimeError("Ed25519 session is not authenticated")
        controlled = dict(params)
        if any(key in controlled for key in {"apiKey", "signature", "timestamp"}):
            raise ValueError("authenticated control parameters are managed internally")
        controlled["recvWindow"] = self.receive_window_ms
        controlled["timestamp"] = self.clock_ms()
        return self.transport.request(method, controlled)


def _symbol(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or not normalized.isascii() or not normalized.isalnum():
        raise ValueError("symbol must be ASCII alphanumeric")
    return normalized


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"Spot WebSocket API {field_name} is invalid")
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Spot WebSocket API {field_name} is invalid") from None
