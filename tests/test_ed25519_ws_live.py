"""Ed25519 WS and explicit live-order gate regression tests."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from ai4binance.domain import LiveGateInput
from ai4binance.exchange.ws_api import (
    BinanceEd25519SpotSession,
    BinanceSpotWsConnection,
    BinanceWsApiError,
    Ed25519Credentials,
    Ed25519RequestSigner,
    _integer,
    signature_payload,
)
from ai4binance.execution.live_spot import (
    GatedSpotOrderExecutor,
    LiveCommandStatus,
    OrderDestinationVerification,
    ReadOnlySpotOrderHistoryVerifier,
    SpotOrderCommand,
)


class RecordingWsTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def request(self, method: str, params: Mapping[str, object]) -> object:
        self.calls.append((method, params))
        return {"orderId": 42} if method.startswith("order.") else {"ok": True}


def credentials() -> Ed25519Credentials:
    return Ed25519Credentials("public", Path("Secrets/binance_ed25519_private.pem"))


def all_live_gates() -> LiveGateInput:
    values = dict.fromkeys(LiveGateInput.__dataclass_fields__, True)
    return LiveGateInput(**values)


def command() -> SpotOrderCommand:
    return SpotOrderCommand(
        "hotusdt",
        "buy",
        "limit",
        Decimal("1000"),
        "ai4b-approved-1",
        Decimal("0.001"),
        "GTC",
    )


def test_signature_payload_is_sorted_and_secret_independent() -> None:
    assert (
        signature_payload(
            {"timestamp": 2, "apiKey": "key", "recvWindow": 5, "signature": "drop"}
        )
        == "apiKey=key&recvWindow=5&timestamp=2"
    )
    assert signature_payload({"enabled": True, "disabled": False, "drop": None}) == (
        "disabled=false&enabled=true"
    )


def write_key(tmp_path: Path, key: object, password: bytes | None = None) -> Path:
    key_dir = tmp_path / "Secrets"
    key_dir.mkdir()
    encryption: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    payload = key.private_bytes(  # type: ignore[attr-defined]
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        encryption,
    )
    path = key_dir / "binance_ed25519_private.pem"
    path.write_bytes(payload)
    return path


def test_ed25519_credentials_load_and_sign_from_allowlisted_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    write_key(tmp_path, private_key, b"passphrase")
    creds = Ed25519Credentials(
        "public", Path("Secrets/binance_ed25519_private.pem"), "passphrase"
    )
    signature = Ed25519RequestSigner(creds).sign({"timestamp": 7, "apiKey": "public"})
    private_key.public_key().verify(
        __import__("base64").b64decode(signature), b"apiKey=public&timestamp=7"
    )


def test_ed25519_environment_and_key_failures_are_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", "public")
    monkeypatch.setenv("BINANCE_ED25519_PRIVATE_KEY_PASSPHRASE", "secret")
    creds = Ed25519Credentials.from_environment()
    assert creds.api_key == "public"
    assert creds.passphrase == os.environ["BINANCE_ED25519_PRIVATE_KEY_PASSPHRASE"]
    with pytest.raises(ValueError, match="unavailable"):
        creds.load_private_key()

    key_dir = tmp_path / "Secrets"
    key_dir.mkdir()
    key_path = key_dir / "binance_ed25519_private.pem"
    key_path.write_bytes(b"x" * 32_769)
    with pytest.raises(ValueError, match="size limit"):
        creds.load_private_key()
    key_path.write_text("not a PEM", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be loaded"):
        creds.load_private_key()


def test_ed25519_rejects_blank_identity_and_non_ed25519_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="API key is required"):
        Ed25519Credentials(" ", Path("Secrets/binance_ed25519_private.pem"))
    monkeypatch.chdir(tmp_path)
    write_key(tmp_path, generate_private_key(public_exponent=65_537, key_size=2048))
    with pytest.raises(ValueError, match="must be Ed25519"):
        credentials().load_private_key()


def test_ws_url_key_path_and_method_allowlists_fail_closed() -> None:
    with pytest.raises(ValueError, match="URL is not allowlisted"):
        BinanceSpotWsConnection("wss://evil.invalid/ws")
    with pytest.raises(ValueError, match="path is not allowlisted"):
        Ed25519Credentials("key", Path("other.pem"))
    with pytest.raises(ValueError, match="timeout"):
        BinanceSpotWsConnection(request_timeout_seconds=31)
    with pytest.raises(ValueError, match="queue bound"):
        BinanceSpotWsConnection(max_unsolicited_messages=0)


class FakeWsConnection:
    def __init__(self, *, response: object = None, unsolicited: bool = False) -> None:
        self.sent: list[str] = []
        self.response = response
        self.unsolicited = unsolicited
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self, *, timeout: float) -> str | bytes:
        request_id = json.loads(self.sent[-1])["id"]
        if self.unsolicited:
            self.unsolicited = False
            return json.dumps({"event": "balanceUpdate"})
        response = self.response
        if response is None:
            response = {"id": request_id, "status": 200, "result": {"ok": True}}
        elif isinstance(response, dict):
            response = {**response, "id": request_id}
        rendered = json.dumps(response)
        return rendered.encode() if isinstance(response, dict) else rendered

    def close(self) -> None:
        self.closed = True


def test_ws_connection_matches_responses_and_retains_bounded_events() -> None:
    fake = FakeWsConnection(unsolicited=True)
    factory_calls: list[tuple[object, ...]] = []

    def factory(*args: object, **kwargs: object) -> object:
        factory_calls.append((*args, kwargs))
        return fake

    connection = BinanceSpotWsConnection(connection_factory=factory)
    assert connection.request("account.status", {}) == {"ok": True}
    assert list(connection.unsolicited_messages) == [{"event": "balanceUpdate"}]
    connection.connect()
    assert len(factory_calls) == 1
    connection.close()
    assert fake.closed is True
    connection.close()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"status": 400, "error": {"code": -1100}}, BinanceWsApiError),
        (["not", "an", "object"], ValueError),
        ("not-json", ValueError),
    ],
)
def test_ws_connection_sanitizes_invalid_exchange_responses(
    response: object, error: type[Exception]
) -> None:
    fake = FakeWsConnection(response=response)
    connection = BinanceSpotWsConnection(
        connection_factory=lambda *args, **kwargs: fake
    )
    with pytest.raises(error):
        connection.request("account.status", {})


def test_ws_connection_rejects_methods_and_invalid_connection_contract() -> None:
    with pytest.raises(ValueError, match="method is not allowlisted"):
        BinanceSpotWsConnection(
            connection_factory=lambda *args, **kwargs: object()
        ).request("order.unsafe", {})
    with pytest.raises(RuntimeError, match="contract is invalid"):
        BinanceSpotWsConnection(
            connection_factory=lambda *args, **kwargs: object()
        ).request("account.status", {})


class InvalidJsonWsConnection(FakeWsConnection):
    def recv(self, *, timeout: float) -> bytes:
        return b"\xff"


def test_ws_connection_and_integer_parser_reject_malformed_protocol_values() -> None:
    connection = BinanceSpotWsConnection(
        connection_factory=lambda *args, **kwargs: InvalidJsonWsConnection()
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        connection.request("account.status", {})
    with pytest.raises(ValueError, match="status is invalid"):
        _integer(True, "status")
    with pytest.raises(ValueError, match="status is invalid"):
        _integer("not-an-integer", "status")


def test_ws_default_factory_unavailable_connection_and_timeout_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeWsConnection()
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            "ai4binance.exchange.ws_api.importlib.import_module",
            lambda name: SimpleNamespace(connect=lambda *args, **kwargs: fake),
        )
        default_connection = BinanceSpotWsConnection()
        default_connection.connect()
        default_connection.close()
    assert fake.closed is True

    with pytest.raises(RuntimeError, match="connection is unavailable"):
        BinanceSpotWsConnection(
            connection_factory=lambda *args, **kwargs: None
        ).request("account.status", {})

    timeout_fake = FakeWsConnection()
    ticks = iter((0.0, 31.0))
    monkeypatch.setattr(
        "ai4binance.exchange.ws_api.time.monotonic", lambda: next(ticks)
    )
    with pytest.raises(TimeoutError, match="response timed out"):
        BinanceSpotWsConnection(
            connection_factory=lambda *args, **kwargs: timeout_fake
        ).request("account.status", {})


def test_authenticated_read_methods_require_logon_without_replacing_wallet_reader() -> (
    None
):
    transport = RecordingWsTransport()
    session = BinanceEd25519SpotSession(transport, credentials(), clock_ms=lambda: 7)
    with pytest.raises(RuntimeError, match="not authenticated"):
        session.account_status()
    session._authenticated = True
    assert session.account_status() == {"ok": True}
    assert session.open_orders("hotusdt") == {"ok": True}
    assert transport.calls[0][0] == "account.status"
    assert transport.calls[1][1]["symbol"] == "HOTUSDT"
    assert session.open_orders() == {"ok": True}
    with pytest.raises(ValueError, match="ASCII alphanumeric"):
        session.open_orders("HOT/USDT")
    with pytest.raises(ValueError, match="control parameters"):
        session.order_test({"apiKey": "override"})
    with pytest.raises(ValueError, match="read-only allowlisted"):
        session._read("order.place")


def test_session_logon_signs_and_all_authenticated_methods_are_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_key(tmp_path, Ed25519PrivateKey.generate())
    transport = RecordingWsTransport()
    session = BinanceEd25519SpotSession(transport, credentials(), clock_ms=lambda: 123)
    assert session.logon() == {"ok": True}
    assert transport.calls[0][0] == "session.logon"
    assert "signature" in transport.calls[0][1]
    assert session.order_test({"symbol": "HOTUSDT"}) == {"orderId": 42}
    assert session.order_place({"symbol": "HOTUSDT"}) == {"orderId": 42}
    assert session.order_cancel({"symbol": "HOTUSDT"}) == {"orderId": 42}
    with pytest.raises(ValueError, match="between 1000 and 60000"):
        BinanceEd25519SpotSession(transport, credentials(), receive_window_ms=999)


class RecordingOrderSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def order_test(self, params: Mapping[str, object]) -> object:
        self.calls.append("test")
        return {}

    def order_place(self, params: Mapping[str, object]) -> object:
        self.calls.append("place")
        return {"orderId": 99}

    def order_cancel(self, params: Mapping[str, object]) -> object:
        self.calls.append("cancel")
        return {"orderId": 99}


class RecordingOrderVerifier:
    def __init__(self, result: OrderDestinationVerification | None = None) -> None:
        self.result = result or OrderDestinationVerification.accepted()
        self.calls: list[str] = []

    def verify_placed(
        self, command: SpotOrderCommand, exchange_order_id: str
    ) -> OrderDestinationVerification:
        self.calls.append(f"place:{command.client_order_id}:{exchange_order_id}")
        return self.result

    def verify_cancelled(
        self, *, symbol: str, client_order_id: str, exchange_order_id: str
    ) -> OrderDestinationVerification:
        self.calls.append(f"cancel:{symbol}:{client_order_id}:{exchange_order_id}")
        return self.result


def test_live_place_is_blocked_by_default_and_does_not_touch_exchange() -> None:
    session = RecordingOrderSession()
    order = command()
    result = GatedSpotOrderExecutor(session).place(
        order, LiveGateInput(), approved_preview_hash=order.preview_hash
    )
    assert result.status is LiveCommandStatus.BLOCKED
    assert "explicit_user_request" in result.blockers
    assert session.calls == []


def test_live_place_requires_exact_preview_hash_even_when_all_gates_are_true() -> None:
    session = RecordingOrderSession()
    result = GatedSpotOrderExecutor(session).place(
        command(), all_live_gates(), approved_preview_hash="wrong"
    )
    assert result.blockers == ("ORDER_PREVIEW_HASH_NOT_APPROVED",)
    assert session.calls == []


def test_live_place_requires_destination_verifier_before_exchange_write() -> None:
    session = RecordingOrderSession()
    order = command()
    result = GatedSpotOrderExecutor(session).place(
        order, all_live_gates(), approved_preview_hash=order.preview_hash
    )
    assert result.status is LiveCommandStatus.BLOCKED
    assert result.blockers == ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",)
    assert session.calls == []


def test_explicitly_approved_place_runs_test_before_place_and_validates_ack() -> None:
    session = RecordingOrderSession()
    order = command()
    verifier = RecordingOrderVerifier()
    result = GatedSpotOrderExecutor(session, verifier).place(
        order, all_live_gates(), approved_preview_hash=order.preview_hash
    )
    assert result.status is LiveCommandStatus.SUBMITTED
    assert result.exchange_order_id == "99"
    assert session.calls == ["test", "place"]
    assert verifier.calls == ["place:ai4b-approved-1:99"]


def test_live_place_requires_read_back_after_exchange_ack() -> None:
    session = RecordingOrderSession()
    order = command()
    verifier = RecordingOrderVerifier(
        OrderDestinationVerification.failed("ORDER_DESTINATION_READ_BACK_MISSING")
    )
    result = GatedSpotOrderExecutor(session, verifier).place(
        order, all_live_gates(), approved_preview_hash=order.preview_hash
    )
    assert result.status is LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED
    assert result.blockers == ("ORDER_DESTINATION_READ_BACK_MISSING",)
    assert session.calls == ["test", "place"]


def test_cancel_is_also_blocked_without_all_live_gates() -> None:
    session = RecordingOrderSession()
    result = GatedSpotOrderExecutor(session).cancel(
        symbol="HOTUSDT",
        client_order_id="known",
        gate_input=LiveGateInput(explicit_user_request=True),
    )
    assert result.status is LiveCommandStatus.BLOCKED
    assert session.calls == []


@pytest.mark.parametrize(
    ("symbol", "side", "quantity", "client_id", "price", "time_in_force"),
    [
        ("HOT/USDT", "BUY", Decimal("1"), "safe-id", Decimal("1"), "GTC"),
        ("HOTUSDT", "HOLD", Decimal("1"), "safe-id", Decimal("1"), "GTC"),
        ("HOTUSDT", "BUY", Decimal("0"), "safe-id", Decimal("1"), "GTC"),
        ("HOTUSDT", "BUY", Decimal("1"), "", Decimal("1"), "GTC"),
        ("HOTUSDT", "BUY", Decimal("1"), "safe-id", None, "GTC"),
        ("HOTUSDT", "BUY", Decimal("1"), "safe-id", Decimal("1"), "DAY"),
    ],
)
def test_order_command_rejects_invalid_limit_fields(
    symbol: str,
    side: str,
    quantity: Decimal,
    client_id: str,
    price: Decimal | None,
    time_in_force: str | None,
) -> None:
    with pytest.raises(ValueError, match=r"order|LIMIT"):
        SpotOrderCommand(
            symbol,
            side,
            "LIMIT",
            quantity,
            client_id,
            price,
            time_in_force,
        )


def test_market_order_rejects_limit_fields_and_cancel_validates_identity() -> None:
    with pytest.raises(ValueError, match="cannot contain"):
        SpotOrderCommand("HOTUSDT", "BUY", "MARKET", Decimal("1"), "safe", Decimal("1"))
    session = RecordingOrderSession()
    result = GatedSpotOrderExecutor(session).cancel(
        symbol="HOT/USDT", client_order_id=" ", gate_input=all_live_gates()
    )
    assert result.blockers == ("ORDER_SYMBOL_INVALID", "CLIENT_ORDER_ID_INVALID")
    assert session.calls == []


def test_explicitly_approved_cancel_calls_exchange() -> None:
    session = RecordingOrderSession()
    verifier = RecordingOrderVerifier()
    result = GatedSpotOrderExecutor(session, verifier).cancel(
        symbol="hotusdt", client_order_id="known", gate_input=all_live_gates()
    )
    assert result.status is LiveCommandStatus.CANCELLED
    assert result.exchange_order_id == "99"
    assert session.calls == ["cancel"]
    assert verifier.calls == ["cancel:HOTUSDT:known:99"]


def test_live_cancel_requires_destination_verifier_before_exchange_write() -> None:
    session = RecordingOrderSession()
    result = GatedSpotOrderExecutor(session).cancel(
        symbol="HOTUSDT", client_order_id="known", gate_input=all_live_gates()
    )
    assert result.status is LiveCommandStatus.BLOCKED
    assert result.blockers == ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",)
    assert session.calls == []


def test_live_cancel_requires_read_back_after_exchange_ack() -> None:
    session = RecordingOrderSession()
    verifier = RecordingOrderVerifier(
        OrderDestinationVerification.failed(
            "ORDER_CANCEL_DESTINATION_STATUS_UNVERIFIED"
        )
    )
    result = GatedSpotOrderExecutor(session, verifier).cancel(
        symbol="HOTUSDT", client_order_id="known", gate_input=all_live_gates()
    )
    assert result.status is LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED
    assert result.blockers == ("ORDER_CANCEL_DESTINATION_STATUS_UNVERIFIED",)
    assert session.calls == ["cancel"]


def test_read_only_history_verifier_matches_client_and_exchange_order_id() -> None:
    class Reader:
        def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
            assert symbol == "HOTUSDT"
            assert limit == 100
            return [
                {"clientOrderId": "other", "orderId": 99, "status": "FILLED"},
                {
                    "clientOrderId": "ai4b-approved-1",
                    "orderId": 99,
                    "status": "NEW",
                },
            ]

    result = ReadOnlySpotOrderHistoryVerifier(Reader()).verify_placed(command(), "99")
    assert result.verified is True


def test_order_destination_verification_rejects_inconsistent_state() -> None:
    with pytest.raises(ValueError, match="cannot contain blockers"):
        OrderDestinationVerification(True, ("BLOCKER",))
    with pytest.raises(ValueError, match="requires blockers"):
        OrderDestinationVerification(False)


def test_read_only_history_verifier_validates_bounds_and_history_shape() -> None:
    class Reader:
        def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
            return {"not": "a-list"}

    with pytest.raises(ValueError, match="history limit"):
        ReadOnlySpotOrderHistoryVerifier(Reader(), history_limit=0)
    with pytest.raises(RuntimeError, match="read-back must be a list"):
        ReadOnlySpotOrderHistoryVerifier(Reader()).verify_placed(command(), "99")


def test_read_only_history_verifier_blocks_missing_destination_record() -> None:
    class Reader:
        def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
            return []

    result = ReadOnlySpotOrderHistoryVerifier(Reader()).verify_placed(command(), "99")
    assert result.blockers == ("ORDER_DESTINATION_READ_BACK_MISSING",)


def test_read_only_history_verifier_blocks_unverified_statuses() -> None:
    class Reader:
        def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
            return [
                {
                    "clientOrderId": "ai4b-approved-1",
                    "orderId": 99,
                    "status": "UNKNOWN",
                }
            ]

    verifier = ReadOnlySpotOrderHistoryVerifier(Reader())
    assert verifier.verify_placed(command(), "99").blockers == (
        "ORDER_DESTINATION_STATUS_UNVERIFIED",
    )
    assert verifier.verify_cancelled(
        symbol="HOTUSDT", client_order_id="ai4b-approved-1", exchange_order_id="99"
    ).blockers == ("ORDER_CANCEL_DESTINATION_STATUS_UNVERIFIED",)


def test_read_only_history_verifier_accepts_cancel_terminal_state() -> None:
    class Reader:
        def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
            return [
                "ignored",
                {"clientOrderId": "known", "orderId": 99, "status": "CANCELED"},
            ]

    result = ReadOnlySpotOrderHistoryVerifier(Reader()).verify_cancelled(
        symbol="HOTUSDT", client_order_id="known", exchange_order_id="99"
    )
    assert result.verified is True


class InvalidAckOrderSession(RecordingOrderSession):
    def __init__(self, response: object) -> None:
        super().__init__()
        self.response = response

    def order_place(self, params: Mapping[str, object]) -> object:
        self.calls.append("place")
        return self.response


@pytest.mark.parametrize("response", [None, {}, {"orderId": " "}])
def test_live_place_rejects_invalid_exchange_acknowledgement(response: object) -> None:
    session = InvalidAckOrderSession(response)
    order = command()
    with pytest.raises(RuntimeError, match="exchange order response"):
        GatedSpotOrderExecutor(session, RecordingOrderVerifier()).place(
            order, all_live_gates(), approved_preview_hash=order.preview_hash
        )
