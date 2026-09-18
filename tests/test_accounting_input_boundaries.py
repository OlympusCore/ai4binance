"""Accounting ingestion rejects malformed values and records degraded evidence."""

from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from ai4binance.accounting import (
    AccountingReconciler,
    AccountingRestCollector,
    AccountingWebSocketCollector,
    BinanceAccountLedger,
)
from ai4binance.accounting.collectors import (
    BinanceAccountingRestSource,
    _futures_position,
)
from tests.test_accounting_collectors import MS, NOW, FakeRestSource, _events


@pytest.mark.parametrize(
    ("method", "field", "value"),
    [
        ("spot_orders", "symbol", "BAD/SYMBOL"),
        ("spot_orders", "clientOrderId", " "),
        ("spot_orders", "price", "-1"),
        ("spot_orders", "price", "invalid"),
        ("spot_orders", "price", "NaN"),
        ("spot_orders", "orderId", True),
        ("spot_orders", "orderId", " "),
        ("spot_orders", "time", None),
        ("spot_orders", "time", True),
        ("spot_orders", "time", "invalid"),
        ("spot_orders", "time", -1),
        ("spot_trades", "isBuyer", "true"),
        ("futures_positions", "positionSide", "INVALID"),
    ],
)
def test_rest_collector_rejects_bad_rows_without_losing_other_products(
    tmp_path: Path, method: str, field: str, value: object
) -> None:
    source = Mock(wraps=FakeRestSource())
    rows = getattr(FakeRestSource(), method)()
    rows[0][field] = value
    getattr(source, method).return_value = rows
    collector = AccountingRestCollector(BinanceAccountLedger(tmp_path))
    result = collector.ingest_snapshot(
        source, snapshot_id="snapshot", sync_run_id="run", received_at=NOW
    )
    assert result.rejected_count == 1
    assert result.accepted_count == 8
    assert len(result.blockers) == 1
    assert result.blockers[0].endswith(":REST_PAYLOAD_REJECTED")
    assert result.execution_allowed is False


def test_rest_collector_ignores_zero_positions_and_preserves_missing_optional_fields(
    tmp_path: Path,
) -> None:
    source = Mock(wraps=FakeRestSource())
    source.futures_positions.return_value = [{"positionAmt": "0"}]
    orders = cast(list[dict[str, object]], FakeRestSource().futures_orders())
    orders[0].pop("updateTime")
    orders[0].pop("priceProtect")
    source.futures_orders.return_value = orders
    income = cast(list[dict[str, object]], FakeRestSource().futures_income())
    income[0]["symbol"] = None
    source.futures_income.return_value = income
    result = AccountingRestCollector(BinanceAccountLedger(tmp_path)).ingest_snapshot(
        source, snapshot_id="snapshot", sync_run_id="run", received_at=NOW
    )
    assert result.rejected_count == 0
    assert result.duplicate_count == 1
    assert result.accepted_count == 8
    assert not (tmp_path / "futures_usdm" / "positions.jsonl").exists()
    for change, message in (
        ({"accepted_count": -1}, "negative"),
        ({"execution_allowed": True}, "live execution"),
        ({"live_eligibility_status": "LIVE"}, "live execution"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(result, **change)


@pytest.mark.parametrize(
    "event",
    [{"e": "executionReport", "E": MS}, {"e": "outboundAccountPosition", "E": MS}],
)
def test_websocket_bad_supported_event_is_recorded_as_rejected(
    tmp_path: Path, event: dict[str, object]
) -> None:
    collector = AccountingWebSocketCollector(BinanceAccountLedger(tmp_path))
    result = collector.ingest_event(
        event, snapshot_id="snapshot", sync_run_id="run", received_at=NOW
    )
    assert result.rejected_count == 1
    assert result.accepted_count == 0
    assert result.blockers == (f"{event['e']}:ValueError",)
    assert len(_events(tmp_path / "shared" / "raw_api_events.jsonl")) == 1


def test_websocket_rejects_unknown_event_and_naive_received_time(
    tmp_path: Path,
) -> None:
    collector = AccountingWebSocketCollector(BinanceAccountLedger(tmp_path))
    with pytest.raises(ValueError, match="unsupported"):
        collector.ingest_event(
            {"e": "UNKNOWN", "E": MS},
            snapshot_id="snapshot",
            sync_run_id="run",
            received_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        collector.ingest_event(
            {"e": "executionReport", "E": MS},
            snapshot_id="snapshot",
            sync_run_id="run",
            received_at=NOW.replace(tzinfo=None),
        )
    assert not list(tmp_path.rglob("*.jsonl"))


@pytest.mark.parametrize(("delta", "direction"), [("25", "IN"), ("-25", "OUT")])
def test_balance_update_retains_signed_cashflow_direction(
    tmp_path: Path, delta: str, direction: str
) -> None:
    collector = AccountingWebSocketCollector(BinanceAccountLedger(tmp_path))
    result = collector.ingest_event(
        {"e": "balanceUpdate", "E": MS, "T": MS, "a": "USDT", "d": delta},
        snapshot_id="snapshot",
        sync_run_id="run",
        received_at=NOW,
    )
    assert result.accepted_count == 1
    events = _events(tmp_path / "spot" / "capital_flows.jsonl")
    assert events[0]["payload"]["direction"] == direction
    assert events[0]["payload"]["amount"] == "25"


@pytest.mark.parametrize("missing_rest", [False, True])
def test_reconciliation_exposes_missing_position_counterpart(
    tmp_path: Path, missing_rest: bool
) -> None:
    position = _futures_position(
        cast(list[dict[str, object]], FakeRestSource().futures_positions())[0],
        fallback_time=NOW,
    )
    rest, stream = ((), (position,)) if missing_rest else ((position,), ())
    result = AccountingReconciler(
        BinanceAccountLedger(tmp_path)
    ).reconcile_futures_positions(
        rest, stream, snapshot_id="snapshot", sync_run_id="run", reconciled_at=NOW
    )
    assert result.accepted_count == 1
    payload = _events(tmp_path / "shared" / "reconciliation_results.jsonl")[0][
        "payload"
    ]
    assert payload["data_quality_issues"] == [
        "POSITION_MISSING_IN_REST" if missing_rest else "POSITION_MISSING_IN_STREAM"
    ]
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_accounting_adapter_exposes_unavailable_futures_endpoints() -> None:
    spot, futures = Mock(), Mock()
    source = BinanceAccountingRestSource(spot, futures, "BTCUSDT")
    for method, reader_method, blocker in (
        ("futures_positions", "positions", "FUTURES_POSITION_SNAPSHOT_UNAVAILABLE"),
        ("futures_orders", "all_orders", "FUTURES_ORDER_HISTORY_UNAVAILABLE"),
        ("futures_algo_orders", "algo_open_orders", "FUTURES_ALGO_ORDERS_UNAVAILABLE"),
        ("futures_trades", "trades", "FUTURES_TRADE_HISTORY_UNAVAILABLE"),
        ("futures_income", "income", "FUTURES_INCOME_UNAVAILABLE"),
    ):
        getattr(futures, reader_method).side_effect = OSError("offline fixture")
        source.blockers = None
        assert getattr(source, method)() == ()
        assert source.blockers == [blocker]
    futures.leverage_bracket.return_value = [
        {"brackets": [{"bracket": 1, "notionalCap": "1000"}]}
    ]
    row = cast(list[dict[str, object]], source.futures_configurations())[0]
    assert row["notionalBracket"] == "1"
    assert row["maxNotional"] == "1000"
