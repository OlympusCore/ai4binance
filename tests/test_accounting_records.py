"""Product-separated Spot accounting record tests."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.accounting import (
    BinanceAccountLedger,
    FuturesAlgoOrderRecord,
    FuturesConfigurationRecord,
    FuturesIncomeRecord,
    FuturesOrderEventRecord,
    FuturesOrderRecord,
    FuturesPositionEventRecord,
    FuturesPositionRecord,
    FuturesTradeRecord,
    SpotCapitalFlowRecord,
    SpotOrderEventRecord,
    SpotOrderRecord,
    SpotTradeRecord,
)
from ai4binance.storage import DestinationVerificationError

NOW = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)


def test_spot_accounting_records_are_idempotent_and_product_scoped(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct-a", environment="testnet")
    order = SpotOrderRecord(
        symbol="HOTUSDT",
        order_id="11",
        client_order_id="client-11",
        side="BUY",
        order_type="LIMIT",
        status="FILLED",
        price=Decimal("0.001"),
        orig_qty=Decimal("1000"),
        executed_qty=Decimal("1000"),
        cumulative_quote_qty=Decimal("1"),
        average_fill_price=Decimal("0.001"),
        total_commission=Decimal("0.001"),
        commission_asset="HOT",
        order_created_at=NOW,
        last_update_at=NOW,
        filled_at=NOW,
        final_status="FILLED",
        manual_or_system="MANUAL",
    )
    trade = SpotTradeRecord(
        symbol="HOTUSDT",
        trade_id="22",
        order_id="11",
        price=Decimal("0.001"),
        qty=Decimal("1000"),
        quote_qty=Decimal("1"),
        commission=Decimal("0.001"),
        commission_asset="HOT",
        is_buyer=True,
        is_maker=False,
        trade_time=NOW,
    )
    flow = SpotCapitalFlowRecord(
        flow_id="flow-1",
        flow_type="SPOT_FUTURES_TRANSFER",
        asset="USDT",
        amount=Decimal("25"),
        direction="OUT",
        transaction_id="tx-1",
        source_wallet="SPOT",
        destination_wallet="USD_M_FUTURES",
        status="CONFIRMED",
        event_time=NOW,
    )

    assert ledger.append_spot_order(
        order, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_spot_order(
        order, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_spot_trade(
        trade, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_spot_trade(
        trade, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_spot_capital_flow(
        flow, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_spot_capital_flow(
        flow, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )

    orders = _events(tmp_path / "spot" / "orders.jsonl")
    trades = _events(tmp_path / "spot" / "trades.jsonl")
    flows = _events(tmp_path / "spot" / "capital_flows.jsonl")
    assert len(orders) == 1
    assert len(trades) == 1
    assert len(flows) == 1
    assert orders[0]["event_type"] == "SPOT_ORDER_RECORDED"
    assert orders[0]["payload"]["envelope"]["product_type"] == "SPOT"
    assert orders[0]["payload"]["unique_key"] == "SPOT:acct-a:HOTUSDT:11"
    assert orders[0]["payload"]["price"] == "0.001"
    assert trades[0]["payload"]["trade_id"] == "22"
    assert flows[0]["payload"]["direction"] == "OUT"
    assert orders[0]["payload"]["execution_allowed"] is False
    assert orders[0]["payload"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert not (tmp_path / "futures_usdm" / "orders.jsonl").exists()


def test_spot_accounting_index_write_must_verify_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct-a", environment="testnet")
    index_path = tmp_path / "spot" / ".indexes" / "orders.jsonl.keys"
    original = Path.read_text

    def tampered_read_text(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        if self == index_path:
            return ""
        return original(self, encoding, errors)

    monkeypatch.setattr(Path, "read_text", tampered_read_text)
    with pytest.raises(DestinationVerificationError, match="ACCOUNTING_INDEX"):
        ledger.append_spot_order(
            SpotOrderRecord(
                symbol="HOTUSDT",
                order_id="11",
                client_order_id="client-11",
                side="BUY",
                order_type="LIMIT",
                status="NEW",
                price=Decimal("0.001"),
                orig_qty=Decimal("1000"),
                executed_qty=Decimal("0"),
                cumulative_quote_qty=Decimal("0"),
                order_created_at=NOW,
                last_update_at=NOW,
            ),
            snapshot_id="sync-1",
            sync_run_id="sync-1",
            received_at=NOW,
        )


def test_spot_order_events_are_unique_by_sequence_and_execution_type(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct-a")
    first = SpotOrderEventRecord(
        symbol="HOTUSDT",
        order_id="11",
        event_type="executionReport",
        execution_type="TRADE",
        order_status="PARTIALLY_FILLED",
        last_executed_qty=Decimal("100"),
        last_executed_price=Decimal("0.001"),
        cumulative_filled_qty=Decimal("100"),
        commission=Decimal("0"),
        commission_asset="HOT",
        event_sequence=1,
        event_time=NOW,
    )
    second = SpotOrderEventRecord(
        symbol="HOTUSDT",
        order_id="11",
        event_type="executionReport",
        execution_type="TRADE",
        order_status="FILLED",
        last_executed_qty=Decimal("900"),
        last_executed_price=Decimal("0.001"),
        cumulative_filled_qty=Decimal("1000"),
        commission=Decimal("0.001"),
        commission_asset="HOT",
        event_sequence=2,
        event_time=NOW,
    )

    assert ledger.append_spot_order_event(
        first, snapshot_id="stream-1", sync_run_id="stream-1", received_at=NOW
    )
    assert not ledger.append_spot_order_event(
        first, snapshot_id="stream-1", sync_run_id="stream-1", received_at=NOW
    )
    assert ledger.append_spot_order_event(
        second, snapshot_id="stream-1", sync_run_id="stream-1", received_at=NOW
    )

    events = _events(tmp_path / "spot" / "order_events.jsonl")
    assert [event["payload"]["event_sequence"] for event in events] == [1, 2]
    assert events[0]["payload"]["raw_event_stored"] is False


def test_spot_accounting_records_reject_float_money_and_bad_identity() -> None:
    with pytest.raises(ValueError, match="finite Decimal"):
        SpotTradeRecord(
            symbol="HOTUSDT",
            trade_id="22",
            order_id="11",
            price=cast(Decimal, 0.001),
            qty=Decimal("1000"),
            quote_qty=Decimal("1"),
            commission=Decimal("0"),
            commission_asset="HOT",
            is_buyer=True,
            is_maker=False,
            trade_time=NOW,
        )
    with pytest.raises(ValueError, match="uppercase ASCII"):
        SpotOrderRecord(
            symbol="hotusdt",
            order_id="11",
            client_order_id="client-11",
            side="BUY",
            order_type="LIMIT",
            status="NEW",
            price=Decimal("0.001"),
            orig_qty=Decimal("1000"),
            executed_qty=Decimal("0"),
            cumulative_quote_qty=Decimal("0"),
            order_created_at=NOW,
            last_update_at=NOW,
        )
    with pytest.raises(ValueError, match="direction"):
        SpotCapitalFlowRecord(
            flow_id="flow-1",
            flow_type="TRANSFER",
            asset="USDT",
            amount=Decimal("1"),
            direction="SIDEWAYS",
            transaction_id="tx-1",
            source_wallet="SPOT",
            destination_wallet="USD_M_FUTURES",
            status="CONFIRMED",
            event_time=NOW,
        )


def test_futures_accounting_records_are_idempotent_and_product_scoped(
    tmp_path: Path,
) -> None:
    ledger = BinanceAccountLedger(tmp_path, account_id="acct-a", environment="testnet")
    position = FuturesPositionRecord(
        symbol="BTCUSDT",
        position_side="LONG",
        position_amt=Decimal("0.01"),
        entry_price=Decimal("65000"),
        break_even_price=Decimal("65010"),
        mark_price=Decimal("65100"),
        notional=Decimal("651"),
        unrealized_pnl=Decimal("1"),
        liquidation_price=Decimal("50000"),
        leverage=3,
        margin_type="CROSS",
        margin_asset="USDT",
        isolated_margin=Decimal("0"),
        initial_margin=Decimal("217"),
        maintenance_margin=Decimal("4"),
        position_update_time=NOW,
    )
    position_event = FuturesPositionEventRecord(
        symbol="BTCUSDT",
        position_side="LONG",
        previous_position_amt=Decimal("0"),
        new_position_amt=Decimal("0.01"),
        quantity_delta=Decimal("0.01"),
        previous_entry_price=Decimal("0"),
        new_entry_price=Decimal("65000"),
        realized_pnl_delta=Decimal("0"),
        unrealized_pnl=Decimal("1"),
        event_reason="POSITION_OPENED",
        event_time=NOW,
        event_sequence=1,
    )
    order = FuturesOrderRecord(
        symbol="BTCUSDT",
        order_id="f-order-1",
        client_order_id="f-client-1",
        side="BUY",
        position_side="LONG",
        order_type="LIMIT",
        orig_type="LIMIT",
        status="NEW",
        price=Decimal("65000"),
        average_price=Decimal("0"),
        orig_qty=Decimal("0.01"),
        executed_qty=Decimal("0"),
        reduce_only=False,
        close_position=False,
        time_in_force="GTC",
        working_type="CONTRACT_PRICE",
        price_protect=True,
        created_at=NOW,
        updated_at=NOW,
        manual_or_system="MANUAL",
    )
    algo = FuturesAlgoOrderRecord(
        algo_id="algo-1",
        client_algo_id="client-algo-1",
        symbol="BTCUSDT",
        side="SELL",
        position_side="LONG",
        algo_type="STOP_MARKET",
        trigger_price=Decimal("63000"),
        working_type="MARK_PRICE",
        quantity=Decimal("0.01"),
        close_position=False,
        reduce_only=True,
        status="NEW",
        created_at=NOW,
    )
    order_event = FuturesOrderEventRecord(
        symbol="BTCUSDT",
        order_id="f-order-1",
        position_side="LONG",
        event_type="ORDER_TRADE_UPDATE",
        execution_type="TRADE",
        order_status="FILLED",
        last_executed_qty=Decimal("0.01"),
        last_executed_price=Decimal("65000"),
        cumulative_filled_qty=Decimal("0.01"),
        commission=Decimal("0.26"),
        commission_asset="USDT",
        realized_pnl=Decimal("0"),
        event_sequence=2,
        event_time=NOW,
    )
    trade = FuturesTradeRecord(
        trade_id="f-trade-1",
        order_id="f-order-1",
        symbol="BTCUSDT",
        side="BUY",
        position_side="LONG",
        price=Decimal("65000"),
        qty=Decimal("0.01"),
        quote_qty=Decimal("650"),
        realized_pnl=Decimal("-0.26"),
        commission=Decimal("0.26"),
        commission_asset="USDT",
        is_maker=False,
        trade_time=NOW,
    )
    income = FuturesIncomeRecord(
        income_type="FUNDING_FEE",
        symbol="BTCUSDT",
        asset="USDT",
        income_amount=Decimal("-0.12"),
        transaction_id="income-1",
        trade_id="f-trade-1",
        info="funding",
        income_time=NOW,
    )
    config = FuturesConfigurationRecord(
        position_mode="HEDGE",
        multi_assets_mode=False,
        symbol="BTCUSDT",
        leverage=3,
        margin_type="CROSS",
        notional_bracket="1",
        max_notional=Decimal("50000"),
        fee_tier="VIP0",
        bnb_burn_enabled=False,
        effective_from=NOW,
    )

    assert ledger.append_futures_position(
        position, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_position(
        position, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_position_event(
        position_event, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_position_event(
        position_event, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_order(
        order, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_order(
        order, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_algo_order(
        algo, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_algo_order(
        algo, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_order_event(
        order_event, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_order_event(
        order_event, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_trade(
        trade, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_trade(
        trade, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_income(
        income, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_income(
        income, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert ledger.append_futures_configuration(
        config, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )
    assert not ledger.append_futures_configuration(
        config, snapshot_id="sync-1", sync_run_id="sync-1", received_at=NOW
    )

    positions = _events(tmp_path / "futures_usdm" / "positions_current.jsonl")
    position_events = _events(tmp_path / "futures_usdm" / "position_events.jsonl")
    orders = _events(tmp_path / "futures_usdm" / "orders.jsonl")
    algos = _events(tmp_path / "futures_usdm" / "algo_orders.jsonl")
    order_events = _events(tmp_path / "futures_usdm" / "order_events.jsonl")
    trades = _events(tmp_path / "futures_usdm" / "trades.jsonl")
    income_events = _events(tmp_path / "futures_usdm" / "income_ledger.jsonl")
    configs = _events(tmp_path / "futures_usdm" / "configuration_snapshots.jsonl")
    assert [
        len(items)
        for items in (
            positions,
            position_events,
            orders,
            algos,
            order_events,
            trades,
            income_events,
            configs,
        )
    ] == [1, 1, 1, 1, 1, 1, 1, 1]
    assert positions[0]["payload"]["envelope"]["product_type"] == "FUTURES_USDM"
    assert (
        positions[0]["payload"]["unique_key"]
        == "FUTURES_USDM:acct-a:sync-1:BTCUSDT:LONG"
    )
    assert positions[0]["payload"]["position_amt"] == "0.01"
    assert trades[0]["payload"]["realized_pnl"] == "-0.26"
    assert income_events[0]["payload"]["income_amount"] == "-0.12"
    assert order_events[0]["payload"]["raw_event_stored"] is False
    assert positions[0]["payload"]["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert not (tmp_path / "spot" / "positions_current.jsonl").exists()


def test_futures_records_reject_wrong_money_types_and_bad_position_side() -> None:
    with pytest.raises(ValueError, match="finite Decimal"):
        FuturesPositionRecord(
            symbol="BTCUSDT",
            position_side="LONG",
            position_amt=cast(Decimal, 0.01),
            entry_price=Decimal("65000"),
            mark_price=Decimal("65100"),
            notional=Decimal("651"),
            unrealized_pnl=Decimal("1"),
            leverage=3,
            margin_type="CROSS",
            margin_asset="USDT",
            isolated_margin=Decimal("0"),
            position_update_time=NOW,
        )
    with pytest.raises(ValueError, match="position_side"):
        FuturesOrderRecord(
            symbol="BTCUSDT",
            order_id="f-order-1",
            client_order_id="f-client-1",
            side="BUY",
            position_side="UP",
            order_type="LIMIT",
            orig_type="LIMIT",
            status="NEW",
            price=Decimal("65000"),
            average_price=Decimal("0"),
            orig_qty=Decimal("0.01"),
            executed_qty=Decimal("0"),
            reduce_only=False,
            close_position=False,
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValueError, match="original quantity"):
        FuturesOrderRecord(
            symbol="BTCUSDT",
            order_id="f-order-1",
            client_order_id="f-client-1",
            side="BUY",
            position_side="LONG",
            order_type="LIMIT",
            orig_type="LIMIT",
            status="NEW",
            price=Decimal("65000"),
            average_price=Decimal("0"),
            orig_qty=Decimal("0"),
            executed_qty=Decimal("0"),
            reduce_only=False,
            close_position=False,
            created_at=NOW,
            updated_at=NOW,
        )


def _events(path: Path) -> list[dict[str, Any]]:
    return [
        cast(dict[str, Any], json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
