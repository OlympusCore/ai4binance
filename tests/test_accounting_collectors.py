"""REST/WebSocket accounting collector ingestion tests."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import ai4binance.accounting.ui_reports as accounting_ui_reports
from ai4binance.accounting import (
    AccountingFileReconciler,
    AccountingReconciler,
    AccountingRestCollector,
    AccountingUiReportBuilder,
    AccountingUserStreamCollectorService,
    AccountingWebSocketCollector,
    BinanceAccountLedger,
    FuturesPositionRecord,
    HmacSpotUserDataStreamSession,
    ProductType,
    RawApiEventRecord,
    ReconciliationResultRecord,
    SourceType,
)
from ai4binance.accounting.user_stream import (
    BinanceUsdMListenKeyManager,
    FuturesUsdMUserDataStreamSession,
)
from ai4binance.exchange.private import PrivateCredentials

NOW = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
MS = 1_784_367_000_000


@dataclass(frozen=True, slots=True)
class FakeRestSource:
    bad_spot_order_price: bool = False

    def spot_orders(self) -> object:
        return [
            {
                "symbol": "HOTUSDT",
                "orderId": 11,
                "clientOrderId": "client-11",
                "side": "BUY",
                "type": "LIMIT",
                "status": "FILLED",
                "price": 0.001 if self.bad_spot_order_price else "0.001",
                "origQty": "1000",
                "executedQty": "1000",
                "cummulativeQuoteQty": "1",
                "time": MS,
                "updateTime": MS,
            }
        ]

    def spot_trades(self) -> object:
        return [
            {
                "symbol": "HOTUSDT",
                "id": 22,
                "orderId": 11,
                "price": "0.001",
                "qty": "1000",
                "quoteQty": "1",
                "commission": "0.001",
                "commissionAsset": "HOT",
                "isBuyer": True,
                "isMaker": False,
                "time": MS,
            }
        ]

    def spot_capital_flows(self) -> object:
        return [
            {
                "flowId": "flow-1",
                "flowType": "SPOT_FUTURES_TRANSFER",
                "asset": "USDT",
                "amount": "25",
                "direction": "OUT",
                "transactionId": "tx-1",
                "sourceWallet": "SPOT",
                "destinationWallet": "USD_M_FUTURES",
                "status": "CONFIRMED",
                "time": MS,
            }
        ]

    def futures_positions(self) -> object:
        return [
            {
                "symbol": "BTCUSDT",
                "positionSide": "LONG",
                "positionAmt": "0.01",
                "entryPrice": "65000",
                "breakEvenPrice": "65010",
                "markPrice": "65100",
                "notional": "651",
                "unRealizedProfit": "1",
                "liquidationPrice": "50000",
                "leverage": "3",
                "marginType": "CROSS",
                "marginAsset": "USDT",
                "isolatedMargin": "0",
                "updateTime": MS,
            }
        ]

    def futures_orders(self) -> object:
        return [
            {
                "symbol": "BTCUSDT",
                "orderId": "f-order-1",
                "clientOrderId": "f-client-1",
                "side": "BUY",
                "positionSide": "LONG",
                "type": "LIMIT",
                "origType": "LIMIT",
                "status": "NEW",
                "price": "65000",
                "avgPrice": "0",
                "origQty": "0.01",
                "executedQty": "0",
                "reduceOnly": False,
                "closePosition": False,
                "timeInForce": "GTC",
                "workingType": "CONTRACT_PRICE",
                "priceProtect": True,
                "time": MS,
                "updateTime": MS,
            }
        ]

    def futures_algo_orders(self) -> object:
        return [
            {
                "algoId": "algo-1",
                "clientAlgoId": "client-algo-1",
                "algoType": "CONDITIONAL",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "positionSide": "LONG",
                "orderType": "STOP_MARKET",
                "triggerPrice": "63000",
                "workingType": "MARK_PRICE",
                "quantity": "0.01",
                "closePosition": False,
                "reduceOnly": True,
                "algoStatus": "NEW",
                "createTime": MS,
            }
        ]

    def futures_trades(self) -> object:
        return [
            {
                "id": "f-trade-1",
                "orderId": "f-order-1",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "positionSide": "LONG",
                "price": "65000",
                "qty": "0.01",
                "quoteQty": "650",
                "realizedPnl": "-0.26",
                "commission": "0.26",
                "commissionAsset": "USDT",
                "maker": False,
                "time": MS,
            }
        ]

    def futures_income(self) -> object:
        return [
            {
                "incomeType": "FUNDING_FEE",
                "symbol": "BTCUSDT",
                "asset": "USDT",
                "income": "-0.12",
                "tranId": "income-1",
                "tradeId": "f-trade-1",
                "info": "funding",
                "time": MS,
            }
        ]

    def futures_configurations(self) -> object:
        return [
            {
                "positionMode": "HEDGE",
                "multiAssetsMode": False,
                "symbol": "BTCUSDT",
                "leverage": "3",
                "marginType": "CROSS",
                "notionalBracket": "1",
                "maxNotional": "50000",
                "feeTier": "VIP0",
                "bnbBurnEnabled": False,
                "effectiveFrom": MS,
            }
        ]


def test_rest_collector_ingests_all_products_and_blocks_duplicate_replay(
    tmp_path: Path,
) -> None:
    collector = AccountingRestCollector(
        BinanceAccountLedger(tmp_path, account_id="acct-a", environment="testnet")
    )

    first = collector.ingest_snapshot(
        FakeRestSource(), snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    second = collector.ingest_snapshot(
        FakeRestSource(), snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )

    assert first.accepted_count == 9
    assert first.duplicate_count == 0
    assert first.rejected_count == 0
    assert second.accepted_count == 0
    assert second.duplicate_count == 9
    assert second.rejected_count == 0
    assert _events(tmp_path / "spot" / "orders.jsonl")[0]["payload"]["price"] == "0.001"
    assert (
        _events(tmp_path / "futures_usdm" / "positions_current.jsonl")[0]["payload"][
            "unique_key"
        ]
        == "FUTURES_USDM:acct-a:sync-1:BTCUSDT:LONG"
    )
    assert len(_events(tmp_path / "shared" / "raw_api_events.jsonl")) == 9
    algo_payload = _events(tmp_path / "futures_usdm" / "algo_orders.jsonl")[0][
        "payload"
    ]
    assert algo_payload["algo_type"] == "STOP_MARKET"
    assert algo_payload["status"] == "NEW"
    assert algo_payload["envelope"]["endpoint"] == "/fapi/v1/openAlgoOrders"
    assert not (tmp_path / "spot" / "positions_current.jsonl").exists()
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_rest_collector_rejects_wrong_financial_types_without_killing_cycle(
    tmp_path: Path,
) -> None:
    collector = AccountingRestCollector(BinanceAccountLedger(tmp_path))

    result = collector.ingest_snapshot(
        FakeRestSource(bad_spot_order_price=True),
        snapshot_id="sync-1",
        sync_run_id="sync-1",
        received_at=NOW,
    )

    assert result.accepted_count == 8
    assert result.rejected_count == 1
    assert "/api/v3/allOrders:REST_PAYLOAD_REJECTED" in result.blockers
    assert not (tmp_path / "spot" / "orders.jsonl").exists()
    assert (tmp_path / "futures_usdm" / "positions_current.jsonl").exists()


def test_websocket_collector_routes_spot_and_futures_events_idempotently(
    tmp_path: Path,
) -> None:
    collector = AccountingWebSocketCollector(
        BinanceAccountLedger(tmp_path, account_id="acct-a")
    )
    spot_event = {
        "e": "executionReport",
        "E": MS,
        "s": "HOTUSDT",
        "i": 11,
        "x": "TRADE",
        "X": "FILLED",
        "l": "1000",
        "L": "0.001",
        "z": "1000",
        "n": "0.001",
        "N": "HOT",
        "I": 101,
    }
    futures_event = {
        "e": "ORDER_TRADE_UPDATE",
        "E": MS,
        "T": MS,
        "o": {
            "s": "BTCUSDT",
            "i": "f-order-1",
            "ps": "LONG",
            "x": "TRADE",
            "X": "FILLED",
            "l": "0.01",
            "L": "65000",
            "z": "0.01",
            "n": "0.26",
            "N": "USDT",
            "rp": "-0.26",
        },
    }
    account_update = {
        "e": "ACCOUNT_UPDATE",
        "E": MS,
        "a": {
            "m": "ORDER",
            "P": [
                {
                    "s": "BTCUSDT",
                    "ps": "LONG",
                    "pa": "0.01",
                    "ep": "65000",
                    "cr": "0",
                    "up": "1",
                }
            ],
        },
    }

    assert (
        collector.ingest_event(
            spot_event, snapshot_id="ws-1", sync_run_id="ws-1", received_at=NOW
        ).accepted_count
        == 1
    )
    assert (
        collector.ingest_event(
            spot_event, snapshot_id="ws-1", sync_run_id="ws-1", received_at=NOW
        ).duplicate_count
        == 1
    )
    assert (
        collector.ingest_event(
            futures_event, snapshot_id="ws-1", sync_run_id="ws-1", received_at=NOW
        ).accepted_count
        == 1
    )
    assert (
        collector.ingest_event(
            account_update, snapshot_id="ws-1", sync_run_id="ws-1", received_at=NOW
        ).accepted_count
        == 1
    )

    assert len(_events(tmp_path / "spot" / "order_events.jsonl")) == 1
    assert len(_events(tmp_path / "futures_usdm" / "order_events.jsonl")) == 1
    assert len(_events(tmp_path / "futures_usdm" / "position_events.jsonl")) == 1
    assert len(_events(tmp_path / "shared" / "raw_api_events.jsonl")) == 3


def test_reconciler_records_open_position_mismatch_and_replay_idempotency(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct-a")
    reconciler = AccountingReconciler(ledger)
    rest = (
        FuturesPositionRecord(
            symbol="BTCUSDT",
            position_side="LONG",
            position_amt=Decimal("0.01"),
            entry_price=Decimal("65000"),
            mark_price=Decimal("65100"),
            notional=Decimal("651"),
            unrealized_pnl=Decimal("1"),
            leverage=3,
            margin_type="CROSS",
            margin_asset="USDT",
            isolated_margin=Decimal("0"),
            position_update_time=NOW,
        ),
    )
    stream = (
        FuturesPositionRecord(
            symbol="BTCUSDT",
            position_side="LONG",
            position_amt=Decimal("0.02"),
            entry_price=Decimal("65000"),
            mark_price=Decimal("65100"),
            notional=Decimal("1302"),
            unrealized_pnl=Decimal("2"),
            leverage=3,
            margin_type="CROSS",
            margin_asset="USDT",
            isolated_margin=Decimal("0"),
            position_update_time=NOW,
        ),
    )

    first = reconciler.reconcile_futures_positions(
        rest, stream, snapshot_id="sync-1", sync_run_id="sync-1", reconciled_at=NOW
    )
    second = reconciler.reconcile_futures_positions(
        rest, stream, snapshot_id="sync-1", sync_run_id="sync-1", reconciled_at=NOW
    )

    assert first.accepted_count == 1
    assert second.duplicate_count == 1
    event = _events(tmp_path / "shared" / "reconciliation_results.jsonl")[0]
    assert event["payload"]["severity"] == "WARNING"
    assert event["payload"]["data_quality_issues"] == ["POSITION_AMOUNT_MISMATCH"]
    assert event["payload"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


class FakeUserStreamWs:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = messages
        self.sent: list[str] = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self, *, timeout: float) -> str:
        if not self.messages:
            raise TimeoutError
        message = self.messages.pop(0)
        if ("id" in message or "status" in message) and self.sent:
            message = {**message, "id": json.loads(self.sent[-1])["id"]}
        return json.dumps(message)

    def close(self) -> None:
        self.closed = True


def test_user_stream_service_records_subscription_and_websocket_events(
    tmp_path: Path,
) -> None:
    credentials = PrivateCredentials("api-key", "api-secret")
    spot_ws = FakeUserStreamWs(
        [
            {"status": 200, "result": {"subscriptionId": 1}},
            {
                "event": {
                    "e": "executionReport",
                    "E": MS,
                    "s": "HOTUSDT",
                    "i": 11,
                    "x": "TRADE",
                    "X": "FILLED",
                    "l": "1000",
                    "L": "0.001",
                    "z": "1000",
                    "n": "0.001",
                    "N": "HOT",
                    "I": 101,
                }
            },
        ]
    )
    futures_ws = FakeUserStreamWs(
        [
            {
                "e": "ORDER_TRADE_UPDATE",
                "E": MS,
                "T": MS,
                "o": {
                    "s": "BTCUSDT",
                    "i": "f-order-1",
                    "ps": "LONG",
                    "x": "TRADE",
                    "X": "FILLED",
                    "l": "0.01",
                    "L": "65000",
                    "z": "0.01",
                    "n": "0.26",
                    "N": "USDT",
                    "rp": "-0.26",
                },
            }
        ]
    )
    manager = BinanceUsdMListenKeyManager(
        credentials,
        opener=lambda request, timeout: (
            b'{"listenKey":"listen-key"}' if request.method == "POST" else b"{}"
        ),
    )
    service = AccountingUserStreamCollectorService(
        ledger=BinanceAccountLedger(tmp_path, account_id="acct-a"),
        sessions=(
            HmacSpotUserDataStreamSession(
                credentials,
                clock_ms=lambda: MS,
                connection_factory=lambda *args, **kwargs: spot_ws,
            ),
            FuturesUsdMUserDataStreamSession(
                manager,
                connection_factory=lambda *args, **kwargs: futures_ws,
            ),
        ),
        event_limit=6,
        collect_seconds=1.0,
        receive_timeout_seconds=0.1,
    )

    result = service.collect_once(sync_run_id="ws-live-1")

    assert result.accepted_count == 4
    assert result.rejected_count == 0
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert len(_events(tmp_path / "shared" / "raw_api_events.jsonl")) == 4
    assert len(_events(tmp_path / "spot" / "order_events.jsonl")) == 1
    assert len(_events(tmp_path / "futures_usdm" / "order_events.jsonl")) == 1
    assert spot_ws.closed is True
    assert futures_ws.closed is True


def test_file_reconciler_and_ui_report_use_rest_and_websocket_evidence(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct-a")
    rest_result = AccountingRestCollector(ledger).ingest_snapshot(
        FakeRestSource(), snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    websocket = AccountingWebSocketCollector(ledger)
    websocket.ingest_event(
        {
            "e": "executionReport",
            "E": MS,
            "s": "HOTUSDT",
            "i": 11,
            "x": "TRADE",
            "X": "FILLED",
            "l": "1000",
            "L": "0.001",
            "z": "1000",
            "n": "0.001",
            "N": "HOT",
            "I": 101,
        },
        snapshot_id="ws-1",
        sync_run_id="ws-1",
        received_at=NOW,
    )
    ledger.append_raw_api_event(
        _subscription_event(ProductType.FUTURES_USDM),
        snapshot_id="ws-1",
        sync_run_id="ws-1",
        source_type=SourceType.WEBSOCKET,
        endpoint="user_data_stream:subscription",
        is_reconciled=True,
    )
    ledger.append_reconciliation_result(
        ReconciliationResultRecord(
            product_type=ProductType.SPOT,
            entity_type="STREAM_HEALTH",
            entity_id="SPOT",
            rest_value=None,
            stream_value=None,
            difference=("old",),
            severity="BLOCKED",
            reconciled_at=NOW,
            resolution="OLD_REPLAY_REQUIRED",
            data_quality_issues=("OLD_STREAM_BLOCKER",),
        ),
        snapshot_id="old-rec",
        sync_run_id="old-rec",
    )

    summary = AccountingFileReconciler(
        ledger,
        freshness_seconds=86_400,
    ).reconcile_latest(
        snapshot_id="rec-1",
        sync_run_id="rec-1",
        observed_at=NOW,
    )
    report = AccountingUiReportBuilder(
        tmp_path,
        tmp_path / "ui",
        freshness_seconds=86_400,
    ).write(NOW)

    assert rest_result.accepted_count == 9
    assert summary.status == "CLEAN"
    assert report["status"] == "CLEAN"
    assert len(cast(tuple[dict[str, object], ...], report["channels"])) == 4
    assert cast(dict[str, object], report["reconciliation"])[
        "history_severity_counts"
    ] == {"BLOCKED": 1, "OK": 3}
    assert Path(cast(str, report["html_path"])).is_file()
    assert Path(cast(str, report["json_path"])).is_file()
    assert "LIVE_ORDER_BLOCKED" in Path(cast(str, report["html_path"])).read_text(
        encoding="utf-8"
    )


def _subscription_event(product_type: ProductType) -> "RawApiEventRecord":
    return RawApiEventRecord(
        product_type=product_type,
        stream_name="user_data_stream",
        event_type="USER_STREAM_SUBSCRIBED",
        event_time=NOW,
        received_at=NOW,
        payload_hash=f"hash-{product_type.value}",
        processing_status="SUBSCRIPTION_ACTIVE",
    )


def _events(path: Path) -> list[dict[str, Any]]:
    assert accounting_ui_reports.AccountingUiReportBuilder is AccountingUiReportBuilder
    return [
        cast(dict[str, Any], json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
