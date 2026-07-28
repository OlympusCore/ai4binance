"""Spot live preview and readiness gates stay fail-closed."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from ai4binance.cli import live as cli_live
from ai4binance.config import Settings
from ai4binance.domain import LiveGateInput
from ai4binance.exchange.models import BookTicker, MarketKline, SymbolInfo
from ai4binance.execution import LiveCommandResult, LiveCommandStatus, SpotOrderPreview
from ai4binance.execution import live_readiness as readiness_mod
from ai4binance.execution.live_readiness import (
    LiveReadinessBuilder,
    LiveReadinessEvidence,
)
from ai4binance.execution.manual_approval import LocalApprovalQueue
from ai4binance.execution.order_preview import SpotOrderPreviewBuilder
from ai4binance.safety import evaluate_live_gate
from ai4binance.validation.summary import ValidationSummaryReader


class PublicClientStub:
    def server_time(self) -> datetime:
        return datetime(2026, 7, 28, tzinfo=UTC)

    def exchange_info(self, symbol: str) -> SymbolInfo:
        return SymbolInfo(
            symbol,
            "TRADING",
            "HOT",
            "USDT",
            {
                "PRICE_FILTER": {
                    "minPrice": "0.000001",
                    "maxPrice": "1",
                    "tickSize": "0.000001",
                },
                "LOT_SIZE": {
                    "minQty": "1",
                    "maxQty": "100000000",
                    "stepSize": "1",
                },
                "MIN_NOTIONAL": {"minNotional": "5"},
            },
        )

    def ticker_price(self, symbol: str) -> Decimal:
        del symbol
        return Decimal("0.01")

    def book_ticker(self, symbol: str) -> BookTicker:
        del symbol
        return BookTicker(Decimal("0.00999"), Decimal("0.01001"))

    def klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> tuple[MarketKline, ...]:
        del symbol, interval, limit
        return ()


class InvalidPricePublicClientStub(PublicClientStub):
    def ticker_price(self, symbol: str) -> Decimal:
        del symbol
        return Decimal("0")

    def book_ticker(self, symbol: str) -> BookTicker:
        del symbol
        return BookTicker(Decimal("0.00999"), Decimal("0.01001"))


class UnavailablePublicClientStub(PublicClientStub):
    def exchange_info(self, symbol: str) -> SymbolInfo:
        del symbol
        raise RuntimeError("public unavailable")


def test_spot_order_preview_rounds_and_hashes_without_authority() -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="hotusdt",
        side="buy",
        order_type="limit",
        quantity=Decimal("1000.9"),
        client_order_id="approved-1",
        price=Decimal("0.010009"),
        time_in_force="GTC",
    )

    assert preview.command.quantity == Decimal("1000")
    assert preview.command.price == Decimal("0.010009")
    assert preview.preview_hash
    assert preview.status == "READY"
    assert preview.execution_allowed is False
    assert "QUANTITY_ROUNDED_DOWN_TO_STEP_SIZE" in preview.warnings


def test_spot_order_preview_warns_when_price_rounds_down_to_tick() -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-price-round",
        price=Decimal("0.0100099"),
        time_in_force="GTC",
    )

    assert preview.command.price == Decimal("0.010009")
    assert "PRICE_ROUNDED_DOWN_TO_TICK_SIZE" in preview.warnings


def test_spot_order_preview_blocks_market_order_filter_and_spread_risk() -> None:
    preview = SpotOrderPreviewBuilder(
        PublicClientStub(),
        spread_cap_bps=Decimal("1"),
    ).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("10"),
        client_order_id="cid-market",
    )

    assert preview.command.price is None
    assert "NOTIONAL_BELOW_MINIMUM" in preview.blockers
    assert "SPREAD_EXCEEDS_LIVE_CAP" in preview.blockers
    assert preview.status == "BLOCKED"


def test_spot_order_preview_blocks_invalid_public_price_evidence() -> None:
    preview = SpotOrderPreviewBuilder(InvalidPricePublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("1000"),
        client_order_id="cid-invalid-price",
    )

    assert "PUBLIC_PRICE_EVIDENCE_INVALID" in preview.blockers
    assert preview.latest_spot_price_confirmed is False


def test_spot_order_preview_rejects_invalid_builder_and_authority_state() -> None:
    with pytest.raises(ValueError, match="spread cap"):
        SpotOrderPreviewBuilder(PublicClientStub(), spread_cap_bps=Decimal("0"))

    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-ready",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    with pytest.raises(ValueError, match="cannot grant execution"):
        SpotOrderPreview(
            command=preview.command,
            validation_price=preview.validation_price,
            latest_spot_price=preview.latest_spot_price,
            bid=preview.bid,
            ask=preview.ask,
            spread_bps=preview.spread_bps,
            blockers=(),
            warnings=(),
            exchange_info_valid=True,
            price_filter_valid=True,
            lot_size_valid=True,
            notional_filter_valid=True,
            tick_size_valid=True,
            step_size_valid=True,
            latest_spot_price_confirmed=True,
            spread_acceptable=True,
            slippage_acceptable=True,
            execution_allowed=True,
        )


def test_live_readiness_uses_written_approval_but_keeps_missing_gates_blocked(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    approval_path.write_text(
        json.dumps(
            {
                "action": {
                    "action_id": "spot-hot-buy",
                    "action_type": "PLACE_SPOT_ORDER",
                    "approval_status": "APPROVED",
                    "asset_or_symbol": "HOTUSDT",
                    "blockers": ["MANUAL_APPROVAL_REQUIRED"],
                    "expected_effect": "Place exact previewed Spot order.",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    "reason": "User written approval for preview hash.",
                    "risk": "Live Spot risk remains gate controlled.",
                    "suggested_notional_usdt": "10",
                },
                "approval": {
                    "action_id": "spot-hot-buy",
                    "action_type": "PLACE_SPOT_ORDER",
                    "approval_id": "approval-live-1",
                    "approval_status": "APPROVED",
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
                "created_at": "2026-07-28T00:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    validation_root = tmp_path / "validation"
    run_card = validation_root / "HOTUSDT" / "15m" / "trend_continuation.run-card.json"
    run_card.parent.mkdir(parents=True)
    run_card.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [["net_return", 1.0]],
                "promotion_status": "STAGED_CANDIDATE",
                "run_id": "run:staged",
                "symbol": "HOTUSDT",
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="approved-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    preflight = {
        "status": "READY",
        "endpoints": (
            {"name": "spot_account", "status": "OK"},
            {"name": "spot_server_time", "status": "OK"},
        ),
    }

    readiness = LiveReadinessBuilder(
        Settings(
            trading_mode="live",
            order_mode="auto",
            allow_auto_live_orders=True,
            manual_approval_queue_path=approval_path,
            validation_artifact_directory=validation_root,
        ),
        LocalApprovalQueue(approval_path),
    ).build(
        preview=preview,
        confirm_live=True,
        approval_id="approval-live-1",
        preflight_report=preflight,
        open_orders=[],
        validation_summary=ValidationSummaryReader(validation_root).summarize(
            "HOTUSDT"
        ),
    )

    assert readiness.approval_status == "APPROVED"
    assert "explicit_user_request" not in readiness.blockers
    assert "latest_signal_exists" in readiness.blockers
    assert "risk_approved" in readiness.blockers
    assert "strategy_promotion_approved" in readiness.blockers
    assert readiness.execution_allowed is False
    assert readiness.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_live_readiness_approval_lookup_continues_and_falls_through(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    approval_path.write_text(
        json.dumps(
            {
                "action": {
                    "action_id": "spot-hot-buy",
                    "action_type": "PLACE_SPOT_ORDER",
                    "approval_status": "APPROVED",
                    "asset_or_symbol": "HOTUSDT",
                    "blockers": ["MANUAL_APPROVAL_REQUIRED"],
                    "expected_effect": "Place exact previewed Spot order.",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    "reason": "User written approval for preview hash.",
                    "risk": "Live Spot risk remains gate controlled.",
                    "suggested_notional_usdt": "10",
                },
                "approval": {
                    "action_id": "spot-hot-buy",
                    "action_type": "PLACE_SPOT_ORDER",
                    "approval_id": "approval-live-1",
                    "approval_status": "APPROVED",
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
                "created_at": "2026-07-28T00:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    builder = LiveReadinessBuilder(Settings(), LocalApprovalQueue(approval_path))

    assert builder._approved("approval-live-1", "HOTUSDT") is True
    assert builder._approved("missing-approval", "HOTUSDT") is False


def test_live_preview_cli_blocks_missing_order_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli_live.run_live_preview_spot(
            Settings(),
            confirm_live=True,
            symbol="HOTUSDT",
            side=None,
            order_type=None,
            quantity=None,
            client_order_id=None,
            price=None,
            time_in_force=None,
            approval_id=None,
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["blockers"] == [
        "ORDER_SIDE_REQUIRED",
        "ORDER_TYPE_REQUIRED",
        "ORDER_QUANTITY_REQUIRED",
        "CLIENT_ORDER_ID_REQUIRED",
    ]
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_live_preview_payload_blocks_invalid_decimal_before_network() -> None:
    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="not-decimal",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        approval_id=None,
    )

    assert payload["blockers"] == ("quantity must be decimal",)


def test_live_preview_payload_blocks_non_finite_decimal_before_network() -> None:
    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="Infinity",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        approval_id=None,
    )

    assert payload["blockers"] == ("quantity must be finite",)


def test_live_preview_decimal_requires_value_before_network() -> None:
    with pytest.raises(ValueError, match="price is required"):
        cli_live._decimal(None, "price")


def test_live_public_client_factory_is_configured_from_settings() -> None:
    client = cli_live._public_client(
        Settings(public_api_base_url="https://api.test.local")
    )

    assert client is not None


def test_live_preview_payload_blocks_missing_limit_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_live, "_public_client", lambda _settings: PublicClientStub()
    )

    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price=None,
        time_in_force="GTC",
        approval_id=None,
    )

    assert payload["blockers"] == ("LIMIT preview requires price",)


def test_live_preview_payload_blocks_unavailable_public_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_live, "_public_client", lambda _settings: UnavailablePublicClientStub()
    )

    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="MARKET",
        quantity="1000",
        client_order_id="cid-1",
        price=None,
        time_in_force=None,
        approval_id=None,
    )

    assert payload["blockers"] == ("public Spot preview evidence is unavailable",)


def test_live_preview_payload_builds_readiness_with_injected_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    write_staged_run_card(validation_root)
    settings = Settings(
        validation_artifact_directory=validation_root,
        manual_approval_queue_path=tmp_path / "approvals.jsonl",
    )
    monkeypatch.setattr(
        cli_live, "_public_client", lambda _settings: PublicClientStub()
    )
    monkeypatch.setattr(
        cli_live,
        "build_preflight_report",
        lambda **_kwargs: {
            "status": "READY",
            "endpoints": (
                {"name": "spot_account", "status": "OK"},
                {"name": "spot_server_time", "status": "OK"},
            ),
        },
    )
    monkeypatch.setattr(cli_live, "_open_orders", lambda _settings, _symbol: [])

    payload = cli_live.live_preview_payload(
        settings,
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        approval_id=None,
    )

    readiness = cast(LiveReadinessEvidence, payload["readiness"])
    preview = cast(SpotOrderPreview, payload["preview"])
    assert preview.preview_hash
    assert "explicit_user_request" in readiness.blockers
    assert "strategy_promotion_approved" in readiness.blockers
    assert payload["execution_allowed"] is False


def test_live_place_requires_exact_preview_hash(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    readiness = LiveReadinessBuilder(
        Settings(),
        LocalApprovalQueue(Path("missing.jsonl")),
    ).build(
        preview=preview,
        confirm_live=True,
        approval_id=None,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(Path("missing")).summarize(
            "HOTUSDT"
        ),
    )
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": readiness.blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    assert (
        cli_live.run_live_place_spot(
            Settings(),
            confirm_live=True,
            symbol="HOTUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1000",
            client_order_id="cid-1",
            price="0.01",
            time_in_force="GTC",
            approval_id=None,
            approved_preview_hash="wrong",
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    assert "ORDER_PREVIEW_HASH_NOT_APPROVED" in payload["blockers"]


def test_live_place_exact_hash_returns_blocked_gate_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    readiness = LiveReadinessBuilder(
        Settings(),
        LocalApprovalQueue(Path("missing.jsonl")),
    ).build(
        preview=preview,
        confirm_live=False,
        approval_id=None,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(Path("missing")).summarize(
            "HOTUSDT"
        ),
    )
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": readiness.blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    result = cli_live.run_live_place_spot(
        Settings(),
        confirm_live=False,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        approval_id=None,
        approved_preview_hash=preview.preview_hash,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["readiness"]["gate_result"]["status"] == "LIVE_ORDER_BLOCKED"


def test_live_place_allowed_gate_still_fails_closed_when_session_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview, readiness = allowed_preview_and_readiness()
    closed: list[bool] = []

    class FakeConnection:
        def __init__(self, *, url: str) -> None:
            self.url = url

        def close(self) -> None:
            closed.append(True)

    class UnavailableSession:
        def __init__(self, *_args: object) -> None:
            raise RuntimeError("session unavailable")

    monkeypatch.setattr(cli_live, "BinanceSpotWsConnection", FakeConnection)
    monkeypatch.setattr(cli_live, "BinanceEd25519SpotSession", UnavailableSession)
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    result = cli_live.run_live_place_spot(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        approval_id="approval-1",
        approved_preview_hash=preview.preview_hash,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert "LIVE_SPOT_SESSION_UNAVAILABLE" in payload["blockers"]
    assert closed == [True]


def test_open_orders_returns_none_when_private_reader_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_reader(_settings: Settings) -> object:
        raise RuntimeError("private reader unavailable")

    monkeypatch.setattr(cli_live, "_private_reader", unavailable_reader)

    assert cli_live._open_orders(Settings(), "HOTUSDT") is None


def test_live_readiness_helpers_fail_closed_on_malformed_evidence() -> None:
    preview, readiness = allowed_preview_and_readiness()

    assert (
        readiness_mod._endpoint_ok({"endpoints": "not-a-list"}, "spot_account") is False
    )
    assert (
        readiness_mod._endpoint_ok(
            {"endpoints": ("bad", {"name": "spot_account", "status": "FAIL"})},
            "spot_account",
        )
        is False
    )
    assert (
        readiness_mod._endpoint_ok(
            {"endpoints": ({"name": "other", "status": "OK"},)},
            "spot_account",
        )
        is False
    )
    assert readiness_mod._open_order_count(({"orderId": 1}, {"orderId": 2})) == 2
    with pytest.raises(ValueError, match="cannot grant execution"):
        LiveReadinessEvidence(
            gate_input=readiness.gate_input,
            gate_result=readiness.gate_result,
            blockers=(),
            approval_status="APPROVED",
            preflight_status="READY",
            open_order_count=0,
            validation_run_count=1,
            staged_candidate_count=1,
            preview_hash=preview.preview_hash,
            execution_allowed=True,
        )


def test_live_place_allowed_gate_returns_executor_blockers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview, readiness = allowed_preview_and_readiness()
    closed: list[bool] = []

    class FakeConnection:
        def __init__(self, *, url: str) -> None:
            self.url = url

        def close(self) -> None:
            closed.append(True)

    class FakeCredentials:
        @classmethod
        def from_environment(cls) -> object:
            return object()

    class FakeSession:
        def __init__(self, *_args: object) -> None:
            self.logged_on = False

        def logon(self) -> None:
            self.logged_on = True

    class FakeExecutor:
        def __init__(self, *_args: object) -> None:
            pass

        def place(self, *_args: object, **_kwargs: object) -> LiveCommandResult:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",),
                "cid-1",
                preview_hash=preview.preview_hash,
            )

    monkeypatch.setattr(cli_live, "BinanceSpotWsConnection", FakeConnection)
    monkeypatch.setattr(cli_live, "BinanceEd25519SpotSession", FakeSession)
    monkeypatch.setattr(cli_live, "Ed25519Credentials", FakeCredentials)
    monkeypatch.setattr(cli_live, "GatedSpotOrderExecutor", FakeExecutor)
    monkeypatch.setattr(cli_live, "_private_reader", lambda _settings: object())
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    result = cli_live.run_live_place_spot(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        approval_id="approval-1",
        approved_preview_hash=preview.preview_hash,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["live_command_result"]["status"] == "LIVE_ORDER_BLOCKED"
    assert payload["blockers"] == ["ORDER_DESTINATION_VERIFIER_UNAVAILABLE"]
    assert closed == [True]


def write_staged_run_card(root: Path) -> None:
    path = root / "HOTUSDT" / "15m" / "trend_continuation.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [["net_return", 1.0]],
                "promotion_status": "STAGED_CANDIDATE",
                "run_id": "run:staged",
                "symbol": "HOTUSDT",
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def allowed_preview_and_readiness() -> tuple[SpotOrderPreview, LiveReadinessEvidence]:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    gate_input = LiveGateInput(**{field.name: True for field in fields(LiveGateInput)})
    gate_result = evaluate_live_gate(gate_input)
    return preview, LiveReadinessEvidence(
        gate_input=gate_input,
        gate_result=gate_result,
        blockers=(),
        approval_status="APPROVED",
        preflight_status="READY",
        open_order_count=0,
        validation_run_count=1,
        staged_candidate_count=1,
        preview_hash=preview.preview_hash,
    )
