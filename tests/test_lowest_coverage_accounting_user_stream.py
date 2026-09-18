"""Coverage tests for accounting user-data stream failure boundaries."""

import importlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from urllib.error import URLError

import pytest

from ai4binance.accounting import user_stream
from ai4binance.accounting.records import BinanceAccountLedger, ProductType
from ai4binance.exchange.private import PrivateCredentials

CREDENTIALS = PrivateCredentials("key", "secret")


class Connection:
    def __init__(self, payload: str | bytes) -> None:
        self.payload = payload
        self.closed = False
        self.sent = ""

    def send(self, payload: str) -> None:
        self.sent = payload

    def recv(self, *, timeout: float) -> str | bytes:
        if self.payload in {"MATCH", "BAD_RESULT", "REJECTED"}:
            import json

            response = {
                "id": json.loads(self.sent)["id"],
                "status": 200,
                "result": {"subscriptionId": 1},
            }
            if self.payload == "BAD_RESULT":
                response["result"] = {}
            if self.payload == "REJECTED":
                response["status"] = 400
            return json.dumps(response)
        return self.payload

    def close(self) -> None:
        self.closed = True


def test_spot_session_fail_closed_variants() -> None:
    with pytest.raises(ValueError, match=r"allowlisted|safe range|at least one"):
        user_stream.HmacSpotUserDataStreamSession(CREDENTIALS, url="wss://unsafe")
    with pytest.raises(ValueError, match=r"allowlisted|safe range|at least one"):
        user_stream.HmacSpotUserDataStreamSession(CREDENTIALS, receive_window_ms=999)
    session = user_stream.HmacSpotUserDataStreamSession(
        CREDENTIALS, connection_factory=lambda *_args, **_kwargs: Connection("MATCH")
    )
    with pytest.raises(RuntimeError, match="not open"):
        session._read_json(timeout_seconds=1)
    variants: list[tuple[str | bytes, str]] = [
        (b"\\xff", "invalid JSON"),
        ("[]", "not an object"),
    ]
    for payload, message in variants:
        session._connection = Connection(payload)
        with pytest.raises(RuntimeError, match=message):
            session._read_json(timeout_seconds=1)
    session._connection = Connection('{"event": "bad"}')
    with pytest.raises(RuntimeError, match="did not contain"):
        session.receive_event(timeout_seconds=1)
    session._connection = Connection(
        '{"id": "wrong", "status": 200, "result": {"subscriptionId": 1}}'
    )
    with pytest.raises(RuntimeError, match="unexpected"):
        session.open()
    session._connection = Connection("MATCH")
    session.open()
    assert session._subscription_id == 1
    session._connection = Connection("BAD_RESULT")
    with pytest.raises(RuntimeError, match="subscription id"):
        session.open()
    session._connection = Connection("REJECTED")
    with pytest.raises(RuntimeError, match="rejected"):
        session.open()
    session.close()


def test_listen_key_manager_failures_and_futures_session_variants() -> None:
    for opener, expected in [
        (lambda _request, _timeout: b"", "response is invalid"),
        (lambda _request, _timeout: b"not-json", "invalid JSON"),
        (lambda _request, _timeout: b"[]", "not an object"),
        (
            lambda _request, _timeout: (_ for _ in ()).throw(URLError("offline")),
            "request failed",
        ),
    ]:
        manager = user_stream.BinanceUsdMListenKeyManager(CREDENTIALS, opener=opener)
        with pytest.raises(RuntimeError, match=expected):
            manager.start()
    manager = user_stream.BinanceUsdMListenKeyManager(
        CREDENTIALS, opener=lambda _request, _timeout: b'{"listenKey":"k"}'
    )
    with pytest.raises(ValueError, match=r"allowlisted|safe range|at least one"):
        manager._request("GET")
    with pytest.raises(ValueError, match=r"allowlisted|safe range|at least one"):
        user_stream.FuturesUsdMUserDataStreamSession(manager, base_url="wss://unsafe")
    session = user_stream.FuturesUsdMUserDataStreamSession(
        manager,
        connection_factory=lambda *_args, **_kwargs: Connection('{"data":{"x":1}}'),
    )
    with pytest.raises(RuntimeError, match="not open"):
        session.receive_event(timeout_seconds=1)
    session.open()
    session.open()
    assert session.receive_event(timeout_seconds=1) == {"x": 1}
    session._connection = Connection(b"\\xff")
    with pytest.raises(RuntimeError, match="invalid JSON"):
        session.receive_event(timeout_seconds=1)
    session._connection = Connection("[]")
    with pytest.raises(RuntimeError, match="not an object"):
        session.receive_event(timeout_seconds=1)
    session.close()


@dataclass
class BrokenSession:
    product_type: ProductType = ProductType.SPOT
    fail_open: bool = False
    fail_close: bool = False

    def open(self) -> None:
        if self.fail_open:
            raise RuntimeError("open")

    def receive_event(self, *, timeout_seconds: float) -> Mapping[str, object]:
        raise TimeoutError

    def close(self) -> None:
        if self.fail_close:
            raise RuntimeError("close")


def test_collector_service_rejects_invalid_configuration_and_records_failures(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct")
    with pytest.raises(ValueError, match=r"allowlisted|safe range|at least one"):
        user_stream.AccountingUserStreamCollectorService(ledger, (), 1, 1.0, 0.1)
    for event_limit, seconds, timeout in [(0, 1.0, 0.1), (1, 0.5, 0.1), (1, 1.0, 0.01)]:
        with pytest.raises(ValueError, match=r"allowlisted|safe range|at least one"):
            user_stream.AccountingUserStreamCollectorService(
                ledger, (BrokenSession(),), event_limit, seconds, timeout
            )
    result = user_stream.AccountingUserStreamCollectorService(
        ledger, (BrokenSession(fail_open=True),), 1, 1.0, 0.1
    ).collect_once(sync_run_id="r")
    assert result.status == "DEGRADED"
    assert result.rejected_count == 1
    result = user_stream.AccountingUserStreamCollectorService(
        ledger, (BrokenSession(fail_close=True),), 1, 1.0, 0.1
    ).collect_once(sync_run_id="r2")
    assert any("CLOSE_FAILED" in blocker for blocker in result.blockers)


class EventSession:
    product_type = ProductType.SPOT

    def __init__(self, *, fail_close: bool = False) -> None:
        self.fail_close = fail_close

    def open(self) -> None:
        return None

    def receive_event(self, *, timeout_seconds: float) -> Mapping[str, object]:
        return {
            "e": "executionReport",
            "E": 1784367000000,
            "s": "HOTUSDT",
            "i": 1,
            "x": "TRADE",
            "X": "FILLED",
            "l": "1",
            "L": "1",
            "z": "1",
            "n": "0",
            "N": "USDT",
            "I": 1,
        }

    def close(self) -> None:
        if self.fail_close:
            raise RuntimeError("close")


def test_collector_service_covers_event_and_duplicate_paths(tmp_path: Path) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct")
    service = user_stream.AccountingUserStreamCollectorService(
        ledger, (EventSession(),), 2, 1.0, 0.1
    )
    first = service.collect_once(sync_run_id="same")
    second = service.collect_once(sync_run_id="same")
    assert first.accepted_count == 2
    assert second.duplicate_count == 1
    failing = user_stream.AccountingUserStreamCollectorService(
        ledger, (EventSession(fail_close=True),), 2, 1.0, 0.1
    ).collect_once(sync_run_id="different")
    assert any("CLOSE_FAILED" in blocker for blocker in failing.blockers)


def test_default_connection_factories_and_request_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Module:
        connect = staticmethod(lambda *_args, **_kwargs: Connection("MATCH"))

    monkeypatch.setattr(importlib, "import_module", lambda _name: Module())
    spot = user_stream.HmacSpotUserDataStreamSession(CREDENTIALS)
    spot.open()
    assert spot._subscription_id == 1
    spot.close()
    manager = user_stream.BinanceUsdMListenKeyManager(
        CREDENTIALS, opener=lambda _request, _timeout: b'{"listenKey":"k"}'
    )
    futures = user_stream.FuturesUsdMUserDataStreamSession(manager)
    futures.open()
    futures._connection = Connection('{"x":1}')
    assert futures.receive_event(timeout_seconds=1) == {"x": 1}
    futures.close()
    methods: list[str] = []
    manager = user_stream.BinanceUsdMListenKeyManager(
        CREDENTIALS,
        opener=lambda request, _timeout: _record_request(methods, request.method),
    )
    manager.keepalive()
    manager.close()
    assert methods == ["PUT", "DELETE"]


def test_spot_event_duplicate_subscription_and_timeout_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spot = user_stream.HmacSpotUserDataStreamSession(
        CREDENTIALS,
        connection_factory=lambda *_args, **_kwargs: Connection('{"event":{"ok":1}}'),
    )
    spot._connection = Connection('{"event":{"ok":1}}')
    assert spot.receive_event(timeout_seconds=1) == {"ok": 1}
    ledger = BinanceAccountLedger(tmp_path, account_id="acct")
    service = user_stream.AccountingUserStreamCollectorService(
        ledger, (BrokenSession(),), 2, 1.0, 0.1
    )
    monkeypatch.setattr(
        user_stream.AccountingUserStreamCollectorService,
        "_append_subscription_event",
        lambda *_args: False,
    )
    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    result = service.collect_once(sync_run_id="timeout")
    assert result.duplicate_count == 1


def test_listen_key_http_error_is_translated() -> None:
    from urllib.error import HTTPError

    manager = user_stream.BinanceUsdMListenKeyManager(
        CREDENTIALS,
        opener=lambda _request, _timeout: (_ for _ in ()).throw(
            HTTPError("https://x", 429, "busy", Message(), None)
        ),
    )
    with pytest.raises(RuntimeError, match="HTTP 429"):
        manager.start()


def _record_request(methods: list[str], method: str | None) -> bytes:
    assert method is not None
    methods.append(method)
    return b"{}"
