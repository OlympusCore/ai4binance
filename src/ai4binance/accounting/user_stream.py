"""Read-only Binance User Data Stream sessions for accounting ingestion."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai4binance.accounting.collectors import (
    AccountingWebSocketCollector,
)
from ai4binance.accounting.records import (
    BinanceAccountLedger,
    ProductType,
    RawApiEventRecord,
    SourceType,
)
from ai4binance.exchange.private import PrivateCredentials

SPOT_WS_API_URLS = frozenset(
    {
        "wss://ws-api.binance.com:443/ws-api/v3",
        "wss://ws-api.testnet.binance.vision/ws-api/v3",
    }
)
FUTURES_PRIVATE_WS_URL = "wss://fstream.binance.com/private"
FUTURES_LISTEN_KEY_URL = "https://fapi.binance.com/fapi/v1/listenKey"


class WebSocketLike(Protocol):
    def send(self, payload: str) -> None: ...

    def recv(self, *, timeout: float) -> str | bytes: ...

    def close(self) -> None: ...


class UserDataStreamSession(Protocol):
    product_type: ProductType

    def open(self) -> None: ...

    def receive_event(self, *, timeout_seconds: float) -> Mapping[str, object]: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class WebSocketCollectionSummary:
    status: str
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"


@dataclass(slots=True)
class HmacSpotUserDataStreamSession:
    """Spot WebSocket API user-stream subscription using HMAC credentials."""

    credentials: PrivateCredentials = field(repr=False)
    url: str = "wss://ws-api.binance.com:443/ws-api/v3"
    receive_window_ms: int = 60_000
    clock_ms: Callable[[], int] = field(
        default=lambda: int(time.time() * 1000),
        repr=False,
    )
    connection_factory: Callable[..., object] | None = field(default=None, repr=False)
    product_type: ProductType = ProductType.SPOT
    _connection: WebSocketLike | None = field(default=None, init=False, repr=False)
    _subscription_id: int | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.url not in SPOT_WS_API_URLS:
            raise ValueError("Spot user-data WebSocket URL is not allowlisted")
        if not 1_000 <= self.receive_window_ms <= 60_000:
            raise ValueError("Spot user-data recvWindow is outside the safe range")

    def open(self) -> None:
        if self._connection is None:
            self._connection = cast(WebSocketLike, self._connect(self.url))
        params: dict[str, object] = {
            "apiKey": self.credentials.api_key,
            "recvWindow": self.receive_window_ms,
            "timestamp": self.clock_ms(),
        }
        params["signature"] = _hmac_signature(self.credentials.api_secret, params)
        request_id = str(uuid.uuid4())
        self._connection.send(
            json.dumps(
                {
                    "id": request_id,
                    "method": "userDataStream.subscribe.signature",
                    "params": params,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        response = self._read_json(timeout_seconds=10.0)
        if response.get("id") != request_id:
            raise RuntimeError("Spot user-data stream returned an unexpected response")
        if response.get("status") != 200:
            raise RuntimeError("Spot user-data stream subscription was rejected")
        result = response.get("result")
        if not isinstance(result, dict) or not isinstance(
            result.get("subscriptionId"),
            int,
        ):
            raise RuntimeError("Spot user-data stream subscription id is invalid")
        self._subscription_id = int(result["subscriptionId"])

    def receive_event(self, *, timeout_seconds: float) -> Mapping[str, object]:
        message = self._read_json(timeout_seconds=timeout_seconds)
        event = message.get("event")
        if isinstance(event, dict):
            return cast(Mapping[str, object], event)
        raise RuntimeError("Spot user-data stream message did not contain an event")

    def close(self) -> None:
        connection, self._connection = self._connection, None
        self._subscription_id = None
        if connection is not None:
            connection.close()

    def _connect(self, url: str) -> object:
        factory = self.connection_factory
        if factory is None:
            module = importlib.import_module("websockets.sync.client")
            factory = cast(Callable[..., object], module.connect)
        return factory(
            url,
            open_timeout=10.0,
            close_timeout=5.0,
            ping_interval=20.0,
            ping_timeout=20.0,
            max_size=2_000_000,
        )

    def _read_json(self, *, timeout_seconds: float) -> dict[str, object]:
        if self._connection is None:
            raise RuntimeError("Spot user-data stream is not open")
        raw = self._connection.recv(timeout=timeout_seconds)
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            message = json.loads(raw)
        except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
            raise RuntimeError("Spot user-data stream returned invalid JSON") from None
        if not isinstance(message, dict):
            raise RuntimeError("Spot user-data stream message is not an object")
        return cast(dict[str, object], message)


@dataclass(frozen=True, slots=True)
class BinanceUsdMListenKeyManager:
    """Manage USD-M Futures listenKey without exposing order endpoints."""

    credentials: PrivateCredentials = field(repr=False)
    timeout_seconds: float = 10.0
    opener: Callable[[Request, float], bytes] = field(
        default=lambda request, timeout: cast(
            bytes,
            urlopen(request, timeout=timeout).read(4096),  # noqa: S310  # nosec B310
        ),
        repr=False,
    )

    def start(self) -> str:
        payload = self._request("POST")
        listen_key = payload.get("listenKey")
        if not isinstance(listen_key, str) or not listen_key.strip():
            raise RuntimeError("USD-M listenKey response is invalid")
        return listen_key

    def keepalive(self) -> None:
        self._request("PUT")

    def close(self) -> None:
        self._request("DELETE")

    def _request(self, method: str) -> dict[str, object]:
        if method not in {"POST", "PUT", "DELETE"}:
            raise ValueError("USD-M listenKey method is not allowlisted")
        request = Request(  # noqa: S310  # nosec B310
            FUTURES_LISTEN_KEY_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "AI4Binance/0.1",
                "X-MBX-APIKEY": self.credentials.api_key,
            },
            method=method,
        )
        try:
            raw = self.opener(request, self.timeout_seconds)
        except HTTPError as error:
            raise RuntimeError(f"USD-M listenKey HTTP {error.code}") from None
        except (TimeoutError, URLError, OSError):
            raise RuntimeError("USD-M listenKey request failed") from None
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("USD-M listenKey response is invalid JSON") from None
        if not isinstance(payload, dict):
            raise RuntimeError("USD-M listenKey response is not an object")
        return cast(dict[str, object], payload)


@dataclass(slots=True)
class FuturesUsdMUserDataStreamSession:
    """USD-M Futures private stream based on listenKey and /private/ws."""

    listen_key_manager: BinanceUsdMListenKeyManager
    base_url: str = FUTURES_PRIVATE_WS_URL
    connection_factory: Callable[..., object] | None = field(default=None, repr=False)
    product_type: ProductType = ProductType.FUTURES_USDM
    _connection: WebSocketLike | None = field(default=None, init=False, repr=False)
    _listen_key: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.base_url != FUTURES_PRIVATE_WS_URL:
            raise ValueError("USD-M private WebSocket URL is not allowlisted")

    def open(self) -> None:
        if self._connection is not None:
            return
        self._listen_key = self.listen_key_manager.start()
        url = (
            f"{self.base_url}/ws?"
            f"{urlencode({'listenKey': self._listen_key})}"
            "&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE"
        )
        self._connection = cast(WebSocketLike, self._connect(url))

    def receive_event(self, *, timeout_seconds: float) -> Mapping[str, object]:
        if self._connection is None:
            raise RuntimeError("USD-M user-data stream is not open")
        raw = self._connection.recv(timeout=timeout_seconds)
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            message = json.loads(raw)
        except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
            raise RuntimeError("USD-M user-data stream returned invalid JSON") from None
        if isinstance(message, dict) and isinstance(message.get("data"), dict):
            return cast(Mapping[str, object], message["data"])
        if isinstance(message, dict):
            return cast(Mapping[str, object], message)
        raise RuntimeError("USD-M user-data stream message is not an object")

    def close(self) -> None:
        connection, self._connection = self._connection, None
        listen_key, self._listen_key = self._listen_key, None
        if connection is not None:
            connection.close()
        if listen_key is not None:
            self.listen_key_manager.close()

    def _connect(self, url: str) -> object:
        factory = self.connection_factory
        if factory is None:
            module = importlib.import_module("websockets.sync.client")
            factory = cast(Callable[..., object], module.connect)
        return factory(
            url,
            open_timeout=10.0,
            close_timeout=5.0,
            ping_interval=20.0,
            ping_timeout=20.0,
            max_size=2_000_000,
        )


@dataclass(frozen=True, slots=True)
class AccountingUserStreamCollectorService:
    """Open read-only user streams and append normalized WebSocket records."""

    ledger: BinanceAccountLedger
    sessions: tuple[UserDataStreamSession, ...]
    event_limit: int
    collect_seconds: float
    receive_timeout_seconds: float

    def __post_init__(self) -> None:
        if not self.sessions:
            raise ValueError("at least one user-data stream session is required")
        if not 1 <= self.event_limit <= 10_000:
            raise ValueError("WebSocket event_limit is outside the safe range")
        if not 1.0 <= self.collect_seconds <= 3_600.0:
            raise ValueError("WebSocket collect_seconds is outside the safe range")
        if not 0.1 <= self.receive_timeout_seconds <= 60.0:
            raise ValueError("WebSocket receive timeout is outside the safe range")

    def collect_once(self, *, sync_run_id: str) -> WebSocketCollectionSummary:
        accepted = 0
        duplicates = 0
        rejected = 0
        blockers: list[str] = []
        collector = AccountingWebSocketCollector(self.ledger)
        deadline = time.monotonic() + self.collect_seconds
        opened: list[UserDataStreamSession] = []
        now = datetime.now(UTC)
        try:
            for session in self.sessions:
                try:
                    session.open()
                    opened.append(session)
                    if self._append_subscription_event(session, sync_run_id, now):
                        accepted += 1
                    else:
                        duplicates += 1
                except (OSError, RuntimeError, ValueError) as error:
                    rejected += 1
                    blockers.append(
                        f"{session.product_type.value}_WEBSOCKET_OPEN_FAILED:{type(error).__name__}"
                    )
            while (
                accepted + duplicates < self.event_limit and time.monotonic() < deadline
            ):
                made_progress = False
                for session in opened:
                    if accepted + duplicates >= self.event_limit:
                        break
                    try:
                        event = session.receive_event(
                            timeout_seconds=self.receive_timeout_seconds
                        )
                    except TimeoutError:
                        continue
                    except (OSError, RuntimeError, ValueError) as error:
                        blockers.append(
                            f"{session.product_type.value}_WEBSOCKET_EVENT_FAILED:{type(error).__name__}"
                        )
                        continue
                    result = collector.ingest_event(
                        event,
                        snapshot_id=sync_run_id,
                        sync_run_id=sync_run_id,
                        received_at=datetime.now(UTC),
                    )
                    accepted += result.accepted_count
                    duplicates += result.duplicate_count
                    rejected += result.rejected_count
                    blockers.extend(result.blockers)
                    made_progress = True
                if not made_progress and not opened:
                    break
        finally:
            for session in reversed(opened):
                try:
                    session.close()
                except (OSError, RuntimeError, ValueError):
                    blockers.append(
                        f"{session.product_type.value}_WEBSOCKET_CLOSE_FAILED"
                    )
        return WebSocketCollectionSummary(
            "COLLECTED" if not blockers and rejected == 0 else "DEGRADED",
            accepted,
            duplicates,
            rejected,
            tuple(dict.fromkeys(blockers)),
        )

    def _append_subscription_event(
        self,
        session: UserDataStreamSession,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_raw_api_event(
            RawApiEventRecord(
                product_type=session.product_type,
                stream_name="user_data_stream",
                event_type="USER_STREAM_SUBSCRIBED",
                event_time=received_at,
                received_at=received_at,
                payload_hash=hashlib.sha256(
                    f"{session.product_type.value}:{sync_run_id}".encode()
                ).hexdigest(),
                processing_status="SUBSCRIPTION_ACTIVE",
            ),
            snapshot_id=sync_run_id,
            sync_run_id=sync_run_id,
            source_type=SourceType.WEBSOCKET,
            endpoint="user_data_stream:subscription",
            is_reconciled=True,
        )


def _hmac_signature(secret: str, params: Mapping[str, object]) -> str:
    query = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if key != "signature" and value is not None
    )
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
