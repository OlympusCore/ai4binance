"""Read-only REST/WebSocket ingestion for Binance accounting ledgers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Protocol, cast

from ai4binance.accounting.records import (
    BinanceAccountLedger,
    FuturesAlgoOrderRecord,
    FuturesConfigurationRecord,
    FuturesIncomeRecord,
    FuturesOrderEventRecord,
    FuturesOrderRecord,
    FuturesPositionEventRecord,
    FuturesPositionRecord,
    FuturesTradeRecord,
    ProductType,
    RawApiEventRecord,
    ReconciliationResultRecord,
    SourceType,
    SpotCapitalFlowRecord,
    SpotOrderEventRecord,
    SpotOrderRecord,
    SpotTradeRecord,
)
from ai4binance.reporting import to_primitive

if TYPE_CHECKING:
    from ai4binance.exchange.private import (
        BinancePrivateAccountReader,
        BinanceUsdMPrivateAccountReader,
    )


class AccountingRestSource(Protocol):
    """Read-only REST source boundary; deliberately exposes no order operation."""

    def spot_orders(self) -> object: ...

    def spot_trades(self) -> object: ...

    def spot_capital_flows(self) -> object: ...

    def futures_positions(self) -> object: ...

    def futures_orders(self) -> object: ...

    def futures_algo_orders(self) -> object: ...

    def futures_trades(self) -> object: ...

    def futures_income(self) -> object: ...

    def futures_configurations(self) -> object: ...


@dataclass(slots=True)
class BinanceAccountingRestSource:
    """Production read-only REST adapter for accounting ingestion."""

    spot_reader: BinancePrivateAccountReader
    futures_reader: BinanceUsdMPrivateAccountReader
    symbol: str
    limit: int = 100
    blockers: list[str] | None = None

    def __post_init__(self) -> None:
        self.symbol = _symbol(self.symbol)
        if not 1 <= self.limit <= 1_000:
            raise ValueError("accounting REST limit must be between 1 and 1000")
        if self.blockers is None:
            self.blockers = []

    def spot_orders(self) -> object:
        return self._safe_sequence(
            lambda: self.spot_reader.all_orders(self.symbol, limit=self.limit),
            "SPOT_ORDER_HISTORY_UNAVAILABLE",
        )

    def spot_trades(self) -> object:
        return self._safe_sequence(
            lambda: self.spot_reader.trades(self.symbol, limit=self.limit),
            "SPOT_TRADE_HISTORY_UNAVAILABLE",
        )

    def spot_capital_flows(self) -> object:
        outbound = self._transfer_flows("MAIN_UMFUTURE")
        inbound = self._transfer_flows("UMFUTURE_MAIN")
        return [*outbound, *inbound]

    def futures_positions(self) -> object:
        return self._safe_sequence(
            lambda: self.futures_reader.positions(self.symbol),
            "FUTURES_POSITION_SNAPSHOT_UNAVAILABLE",
        )

    def futures_orders(self) -> object:
        return self._safe_sequence(
            lambda: self.futures_reader.all_orders(self.symbol, limit=self.limit),
            "FUTURES_ORDER_HISTORY_UNAVAILABLE",
        )

    def futures_algo_orders(self) -> object:
        return self._safe_sequence(
            lambda: self.futures_reader.algo_open_orders(self.symbol),
            "FUTURES_ALGO_ORDERS_UNAVAILABLE",
        )

    def futures_trades(self) -> object:
        return self._safe_sequence(
            lambda: self.futures_reader.trades(self.symbol, limit=self.limit),
            "FUTURES_TRADE_HISTORY_UNAVAILABLE",
        )

    def futures_income(self) -> object:
        return self._safe_sequence(
            lambda: self.futures_reader.income(self.symbol, limit=self.limit),
            "FUTURES_INCOME_UNAVAILABLE",
        )

    def futures_configurations(self) -> object:
        bracket_payload = self._safe_sequence(
            lambda: self.futures_reader.leverage_bracket(self.symbol),
            "FUTURES_LEVERAGE_BRACKET_UNAVAILABLE",
        )
        if not bracket_payload:
            return []
        bracket = _mapping(bracket_payload[0], "leverageBracket")
        first_bracket = _mapping(
            _sequence(bracket.get("brackets"), "brackets")[0],
            "bracket",
        )
        return [
            {
                "positionMode": "HEDGE",
                "multiAssetsMode": False,
                "symbol": self.symbol,
                "leverage": "1",
                "marginType": "UNKNOWN",
                "notionalBracket": _id(first_bracket.get("bracket"), "bracket"),
                "maxNotional": _id(
                    first_bracket.get(
                        "notionalCap",
                        first_bracket.get("maxNotionalValue"),
                    ),
                    "notionalCap",
                ),
                "feeTier": "UNKNOWN",
                "bnbBurnEnabled": False,
                "effectiveFrom": int(datetime.now(UTC).timestamp() * 1000),
            }
        ]

    def _transfer_flows(self, transfer_type: str) -> list[dict[str, object]]:
        payload = self._safe_mapping(
            lambda: self.spot_reader.universal_transfers(
                transfer_type,
                limit=min(self.limit, 100),
            ),
            f"SPOT_TRANSFER_HISTORY_UNAVAILABLE:{transfer_type}",
        )
        rows = _sequence(payload.get("rows", ()), "transferRows")
        return [
            _transfer_flow(_mapping(row, "transfer"), transfer_type) for row in rows
        ]

    def _safe_sequence(
        self,
        getter: Callable[[], object],
        blocker: str,
    ) -> Sequence[object]:
        try:
            return _sequence(getter(), blocker)
        except (OSError, RuntimeError, TypeError, ValueError):
            self._add_blocker(blocker)
            return ()

    def _safe_mapping(
        self,
        getter: Callable[[], object],
        blocker: str,
    ) -> Mapping[str, object]:
        try:
            return _mapping(getter(), blocker)
        except (OSError, RuntimeError, TypeError, ValueError):
            self._add_blocker(blocker)
            return {}

    def _add_blocker(self, blocker: str) -> None:
        if self.blockers is None:
            self.blockers = []
        self.blockers.append(blocker)


@dataclass(frozen=True, slots=True)
class CollectorIngestionResult:
    product_type: ProductType
    source_type: SourceType
    sync_run_id: str
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if min(self.accepted_count, self.duplicate_count, self.rejected_count) < 0:
            raise ValueError("collector counters cannot be negative")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("collector ingestion cannot allow live execution")


@dataclass(frozen=True, slots=True)
class AccountingRestCollector:
    """Normalize REST history/snapshot payloads into product-separated ledgers."""

    ledger: BinanceAccountLedger

    def ingest_snapshot(
        self,
        source: AccountingRestSource,
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> CollectorIngestionResult:
        _require_aware(received_at)
        accepted = 0
        duplicates = 0
        rejected = 0
        blockers: list[str] = []
        for endpoint, product_type, rows, handler in (
            (
                "/api/v3/allOrders",
                ProductType.SPOT,
                source.spot_orders(),
                self._append_spot_order,
            ),
            (
                "/api/v3/myTrades",
                ProductType.SPOT,
                source.spot_trades(),
                self._append_spot_trade,
            ),
            (
                "spot:capital_flow",
                ProductType.SPOT,
                source.spot_capital_flows(),
                self._append_spot_capital_flow,
            ),
            (
                "/fapi/v3/positionRisk",
                ProductType.FUTURES_USDM,
                source.futures_positions(),
                self._append_futures_position,
            ),
            (
                "/fapi/v1/allOrders",
                ProductType.FUTURES_USDM,
                source.futures_orders(),
                self._append_futures_order,
            ),
            (
                "/fapi/v1/algo/openOrders",
                ProductType.FUTURES_USDM,
                source.futures_algo_orders(),
                self._append_futures_algo_order,
            ),
            (
                "/fapi/v1/userTrades",
                ProductType.FUTURES_USDM,
                source.futures_trades(),
                self._append_futures_trade,
            ),
            (
                "/fapi/v1/income",
                ProductType.FUTURES_USDM,
                source.futures_income(),
                self._append_futures_income,
            ),
            (
                "futures:configuration",
                ProductType.FUTURES_USDM,
                source.futures_configurations(),
                self._append_futures_configuration,
            ),
        ):
            endpoint_rows = _sequence(rows, endpoint)
            for row in endpoint_rows:
                payload = _mapping(row, endpoint)
                self._append_raw(
                    payload,
                    product_type=product_type,
                    stream_name=endpoint,
                    event_type="REST_SNAPSHOT_ROW",
                    event_time=received_at,
                    received_at=received_at,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                )
                try:
                    written = handler(
                        payload,
                        snapshot_id=snapshot_id,
                        sync_run_id=sync_run_id,
                        received_at=received_at,
                    )
                except ValueError:
                    rejected += 1
                    blockers.append(f"{endpoint}:REST_PAYLOAD_REJECTED")
                    continue
                if written:
                    accepted += 1
                else:
                    duplicates += 1
        source_blockers = getattr(source, "blockers", ())
        if isinstance(source_blockers, Sequence) and not isinstance(
            source_blockers, str
        ):
            blockers.extend(str(item) for item in source_blockers if str(item).strip())
        return CollectorIngestionResult(
            ProductType.MULTI_PRODUCT,
            SourceType.REST,
            sync_run_id,
            accepted,
            duplicates,
            rejected,
            tuple(dict.fromkeys(blockers)),
        )

    def _append_spot_order(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_spot_order(
            _spot_order(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_spot_trade(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_spot_trade(
            _spot_trade(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_spot_capital_flow(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_spot_capital_flow(
            _spot_capital_flow(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_futures_position(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        if _signed_decimal(payload.get("positionAmt"), "positionAmt") == Decimal("0"):
            return False
        return self.ledger.append_futures_position(
            _futures_position(payload, fallback_time=received_at),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_futures_order(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_futures_order(
            _futures_order(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_futures_algo_order(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_futures_algo_order(
            _futures_algo_order(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_futures_trade(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_futures_trade(
            _futures_trade(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_futures_income(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_futures_income(
            _futures_income(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_futures_configuration(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        return self.ledger.append_futures_configuration(
            _futures_configuration(payload),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            received_at=received_at,
        )

    def _append_raw(
        self,
        payload: Mapping[str, object],
        *,
        product_type: ProductType,
        stream_name: str,
        event_type: str,
        event_time: datetime,
        received_at: datetime,
        snapshot_id: str,
        sync_run_id: str,
        endpoint: str,
    ) -> bool:
        return self.ledger.append_raw_api_event(
            RawApiEventRecord(
                product_type=product_type,
                stream_name=stream_name,
                event_type=event_type,
                event_time=event_time,
                received_at=received_at,
                payload_hash=_payload_hash(payload),
                processing_status="REDACTED_HASH_ONLY",
            ),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            source_type=SourceType.REST,
            endpoint=endpoint,
        )


@dataclass(frozen=True, slots=True)
class AccountingWebSocketCollector:
    """Normalize User Data Stream events into product-separated ledgers."""

    ledger: BinanceAccountLedger

    def ingest_event(
        self,
        payload: Mapping[str, object],
        *,
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> CollectorIngestionResult:
        _require_aware(received_at)
        event = _unwrap_event(payload)
        event_type = _text(event.get("e"), "e")
        event_time = _ms_time(event.get("E"), "E", fallback=received_at)
        product_type = _product_for_event(event_type)
        self.ledger.append_raw_api_event(
            RawApiEventRecord(
                product_type=product_type,
                stream_name="user_data_stream",
                event_type=event_type,
                event_time=event_time,
                received_at=received_at,
                payload_hash=_payload_hash(event),
                processing_status="REDACTED_HASH_ONLY",
            ),
            snapshot_id=snapshot_id,
            sync_run_id=sync_run_id,
            source_type=SourceType.WEBSOCKET,
            endpoint="user_data_stream",
        )
        try:
            written = self._route(event, snapshot_id, sync_run_id, received_at)
        except ValueError as error:
            return CollectorIngestionResult(
                product_type,
                SourceType.WEBSOCKET,
                sync_run_id,
                0,
                0,
                1,
                (f"{event_type}:{type(error).__name__}",),
            )
        return CollectorIngestionResult(
            product_type,
            SourceType.WEBSOCKET,
            sync_run_id,
            1 if written else 0,
            0 if written else 1,
            0,
            (),
        )

    def _route(
        self,
        event: Mapping[str, object],
        snapshot_id: str,
        sync_run_id: str,
        received_at: datetime,
    ) -> bool:
        event_type = _text(event.get("e"), "e")
        if event_type == "executionReport":
            return self.ledger.append_spot_order_event(
                _spot_order_event(event),
                snapshot_id=snapshot_id,
                sync_run_id=sync_run_id,
                received_at=received_at,
            )
        if event_type == "balanceUpdate":
            return self.ledger.append_spot_capital_flow(
                _spot_balance_update_flow(event),
                snapshot_id=snapshot_id,
                sync_run_id=sync_run_id,
                source_type=SourceType.WEBSOCKET,
                endpoint="spot:user_data_stream:balanceUpdate",
                received_at=received_at,
                is_reconciled=False,
            )
        if event_type == "ORDER_TRADE_UPDATE":
            return self.ledger.append_futures_order_event(
                _futures_order_event(event),
                snapshot_id=snapshot_id,
                sync_run_id=sync_run_id,
                received_at=received_at,
            )
        if event_type == "ACCOUNT_UPDATE":
            written = False
            account = _mapping(event.get("a"), "a")
            positions = _sequence(account.get("P", ()), "P")
            for index, row in enumerate(positions):
                position = _futures_position_event(
                    _mapping(row, "position"),
                    event,
                    sequence=index,
                )
                written = (
                    self.ledger.append_futures_position_event(
                        position,
                        snapshot_id=snapshot_id,
                        sync_run_id=sync_run_id,
                        received_at=received_at,
                    )
                    or written
                )
            return written
        raise ValueError("unsupported user data stream event")


@dataclass(frozen=True, slots=True)
class AccountingReconciler:
    """Compare REST current-state records with WebSocket-derived state."""

    ledger: BinanceAccountLedger

    def reconcile_futures_positions(
        self,
        rest_positions: Sequence[FuturesPositionRecord],
        stream_positions: Sequence[FuturesPositionRecord],
        *,
        snapshot_id: str,
        sync_run_id: str,
        reconciled_at: datetime,
    ) -> CollectorIngestionResult:
        _require_aware(reconciled_at)
        rest = {
            (item.symbol, item.position_side): item.position_amt
            for item in rest_positions
        }
        stream = {
            (item.symbol, item.position_side): item.position_amt
            for item in stream_positions
        }
        accepted = 0
        duplicates = 0
        for key in sorted(set(rest) | set(stream)):
            rest_value = rest.get(key)
            stream_value = stream.get(key)
            issues: list[str] = []
            if rest_value is None:
                issues.append("POSITION_MISSING_IN_REST")
            if stream_value is None:
                issues.append("POSITION_MISSING_IN_STREAM")
            if (
                rest_value is not None
                and stream_value is not None
                and rest_value != stream_value
            ):
                issues.append("POSITION_AMOUNT_MISMATCH")
            record = ReconciliationResultRecord(
                ProductType.FUTURES_USDM,
                "FUTURES_POSITION",
                f"{key[0]}:{key[1]}",
                rest_value,
                stream_value,
                tuple(issues),
                "OK" if not issues else "WARNING",
                reconciled_at,
                "NO_ACTION" if not issues else "REST_REPLAY_REQUIRED",
                tuple(issues),
            )
            if self.ledger.append_reconciliation_result(
                record,
                snapshot_id=snapshot_id,
                sync_run_id=sync_run_id,
            ):
                accepted += 1
            else:
                duplicates += 1
        return CollectorIngestionResult(
            ProductType.FUTURES_USDM,
            SourceType.DERIVED,
            sync_run_id,
            accepted,
            duplicates,
            0,
            (),
        )


def _spot_order(payload: Mapping[str, object]) -> SpotOrderRecord:
    created = _ms_time(payload.get("time"), "time")
    updated = _ms_time(payload.get("updateTime"), "updateTime", fallback=created)
    executed = _decimal(payload.get("executedQty"), "executedQty")
    quote = _decimal(payload.get("cummulativeQuoteQty", "0"), "cummulativeQuoteQty")
    average = (
        quote / executed if executed > Decimal("0") and quote > Decimal("0") else None
    )
    return SpotOrderRecord(
        symbol=_symbol(payload.get("symbol")),
        order_id=_id(payload.get("orderId"), "orderId"),
        client_order_id=_text(payload.get("clientOrderId"), "clientOrderId"),
        order_list_id=_optional_id(payload.get("orderListId")),
        side=_text(payload.get("side"), "side").upper(),
        order_type=_text(payload.get("type"), "type").upper(),
        time_in_force=_optional_text(payload.get("timeInForce")),
        price=_decimal(payload.get("price"), "price"),
        stop_price=_optional_decimal(payload.get("stopPrice"), "stopPrice"),
        orig_qty=_decimal(payload.get("origQty"), "origQty"),
        executed_qty=executed,
        cumulative_quote_qty=quote,
        status=_text(payload.get("status"), "status").upper(),
        final_status=_optional_text(payload.get("status")),
        average_fill_price=average,
        order_created_at=created,
        last_update_at=updated,
        manual_or_system="UNKNOWN",
    )


def _spot_order_event(payload: Mapping[str, object]) -> SpotOrderEventRecord:
    return SpotOrderEventRecord(
        symbol=_symbol(payload.get("s")),
        order_id=_id(payload.get("i"), "i"),
        event_type=_text(payload.get("e"), "e"),
        execution_type=_text(payload.get("x"), "x").upper(),
        order_status=_text(payload.get("X"), "X").upper(),
        last_executed_qty=_decimal(payload.get("l", "0"), "l"),
        last_executed_price=_decimal(payload.get("L", "0"), "L"),
        cumulative_filled_qty=_decimal(payload.get("z", "0"), "z"),
        commission=_decimal(payload.get("n", "0"), "n"),
        commission_asset=_optional_text(payload.get("N")) or "NONE",
        event_sequence=_integer(payload.get("I", payload.get("E")), "I"),
        event_time=_ms_time(payload.get("E"), "E"),
    )


def _spot_trade(payload: Mapping[str, object]) -> SpotTradeRecord:
    return SpotTradeRecord(
        symbol=_symbol(payload.get("symbol")),
        trade_id=_id(payload.get("id"), "id"),
        order_id=_id(payload.get("orderId"), "orderId"),
        order_list_id=_optional_id(payload.get("orderListId")),
        price=_decimal(payload.get("price"), "price"),
        qty=_decimal(payload.get("qty"), "qty"),
        quote_qty=_decimal(payload.get("quoteQty"), "quoteQty"),
        commission=_decimal(payload.get("commission", "0"), "commission"),
        commission_asset=_text(payload.get("commissionAsset"), "commissionAsset"),
        is_buyer=_bool(payload.get("isBuyer"), "isBuyer"),
        is_maker=_bool(payload.get("isMaker"), "isMaker"),
        trade_time=_ms_time(payload.get("time"), "time"),
    )


def _spot_capital_flow(payload: Mapping[str, object]) -> SpotCapitalFlowRecord:
    return SpotCapitalFlowRecord(
        flow_id=_id(payload.get("flowId", payload.get("id")), "flowId"),
        flow_type=_text(
            payload.get("flowType", payload.get("type")),
            "flowType",
        ).upper(),
        asset=_text(payload.get("asset"), "asset").upper(),
        amount=_decimal(payload.get("amount"), "amount"),
        direction=_text(payload.get("direction"), "direction").upper(),
        transaction_id=_id(
            payload.get("transactionId", payload.get("tranId")),
            "transactionId",
        ),
        source_wallet=_text(payload.get("sourceWallet"), "sourceWallet").upper(),
        destination_wallet=_text(
            payload.get("destinationWallet"), "destinationWallet"
        ).upper(),
        status=_text(payload.get("status"), "status").upper(),
        event_time=_ms_time(payload.get("time", payload.get("eventTime")), "time"),
    )


def _spot_balance_update_flow(payload: Mapping[str, object]) -> SpotCapitalFlowRecord:
    amount = _signed_decimal(payload.get("d"), "d")
    return SpotCapitalFlowRecord(
        flow_id=f"balance-update:{_id(payload.get('T'), 'T')}",
        flow_type="BALANCE_UPDATE",
        asset=_text(payload.get("a"), "a").upper(),
        amount=abs(amount),
        direction="IN" if amount >= Decimal("0") else "OUT",
        transaction_id=_id(payload.get("T"), "T"),
        source_wallet="UNKNOWN",
        destination_wallet="SPOT",
        status="CONFIRMED",
        event_time=_ms_time(payload.get("T"), "T"),
    )


def _transfer_flow(
    payload: Mapping[str, object],
    transfer_type: str,
) -> dict[str, object]:
    source, destination, direction = (
        ("SPOT", "USD_M_FUTURES", "OUT")
        if transfer_type == "MAIN_UMFUTURE"
        else ("USD_M_FUTURES", "SPOT", "IN")
    )
    amount = _decimal(payload.get("amount"), "amount")
    timestamp = payload.get("timestamp", payload.get("time"))
    return {
        "flowId": _id(payload.get("tranId", payload.get("id")), "tranId"),
        "flowType": "SPOT_FUTURES_TRANSFER",
        "asset": _text(payload.get("asset"), "asset").upper(),
        "amount": str(amount),
        "direction": direction,
        "transactionId": _id(payload.get("tranId", payload.get("id")), "tranId"),
        "sourceWallet": source,
        "destinationWallet": destination,
        "status": _optional_text(payload.get("status")) or "CONFIRMED",
        "time": timestamp,
    }


def _futures_position(
    payload: Mapping[str, object],
    *,
    fallback_time: datetime,
) -> FuturesPositionRecord:
    return FuturesPositionRecord(
        symbol=_symbol(payload.get("symbol")),
        position_side=_position_side(payload.get("positionSide", "BOTH")),
        position_amt=_signed_decimal(payload.get("positionAmt"), "positionAmt"),
        entry_price=_decimal(payload.get("entryPrice"), "entryPrice"),
        break_even_price=_optional_decimal(
            payload.get("breakEvenPrice"), "breakEvenPrice"
        ),
        mark_price=_decimal(payload.get("markPrice"), "markPrice"),
        notional=_signed_decimal(payload.get("notional"), "notional"),
        unrealized_pnl=_signed_decimal(
            payload.get("unRealizedProfit", payload.get("unrealizedPnl")),
            "unRealizedProfit",
        ),
        liquidation_price=_optional_decimal(
            payload.get("liquidationPrice"), "liquidationPrice"
        ),
        leverage=_integer(payload.get("leverage"), "leverage"),
        margin_type=_text(payload.get("marginType"), "marginType").upper(),
        margin_asset=_text(payload.get("marginAsset", "USDT"), "marginAsset").upper(),
        isolated_margin=_decimal(payload.get("isolatedMargin", "0"), "isolatedMargin"),
        isolated_wallet=_optional_decimal(
            payload.get("isolatedWallet"), "isolatedWallet"
        ),
        initial_margin=_optional_decimal(payload.get("initialMargin"), "initialMargin"),
        maintenance_margin=_optional_decimal(
            payload.get("maintMargin", payload.get("maintenanceMargin")),
            "maintMargin",
        ),
        position_update_time=_ms_time(
            payload.get("updateTime", payload.get("time")),
            "updateTime",
            fallback=fallback_time,
        ),
    )


def _futures_position_event(
    payload: Mapping[str, object],
    event: Mapping[str, object],
    *,
    sequence: int,
) -> FuturesPositionEventRecord:
    new_amt = _signed_decimal(payload.get("pa"), "pa")
    return FuturesPositionEventRecord(
        symbol=_symbol(payload.get("s")),
        position_side=_position_side(payload.get("ps", "BOTH")),
        previous_position_amt=Decimal("0"),
        new_position_amt=new_amt,
        quantity_delta=new_amt,
        previous_entry_price=Decimal("0"),
        new_entry_price=_decimal(payload.get("ep", "0"), "ep"),
        realized_pnl_delta=_signed_decimal(payload.get("cr", "0"), "cr"),
        unrealized_pnl=_signed_decimal(payload.get("up", "0"), "up"),
        event_reason=_text(_mapping(event.get("a"), "a").get("m"), "m").upper(),
        event_time=_ms_time(event.get("E"), "E"),
        event_sequence=sequence,
    )


def _futures_order(payload: Mapping[str, object]) -> FuturesOrderRecord:
    created = _ms_time(payload.get("time"), "time")
    updated = _ms_time(payload.get("updateTime"), "updateTime", fallback=created)
    return FuturesOrderRecord(
        symbol=_symbol(payload.get("symbol")),
        order_id=_id(payload.get("orderId"), "orderId"),
        client_order_id=_text(payload.get("clientOrderId"), "clientOrderId"),
        side=_text(payload.get("side"), "side").upper(),
        position_side=_position_side(payload.get("positionSide", "BOTH")),
        order_type=_text(payload.get("type"), "type").upper(),
        orig_type=_text(
            payload.get("origType", payload.get("type")), "origType"
        ).upper(),
        status=_text(payload.get("status"), "status").upper(),
        price=_decimal(payload.get("price"), "price"),
        average_price=_decimal(payload.get("avgPrice", "0"), "avgPrice"),
        orig_qty=_decimal(payload.get("origQty"), "origQty"),
        executed_qty=_decimal(payload.get("executedQty"), "executedQty"),
        reduce_only=_bool(payload.get("reduceOnly", False), "reduceOnly"),
        close_position=_bool(payload.get("closePosition", False), "closePosition"),
        time_in_force=_optional_text(payload.get("timeInForce")),
        working_type=_optional_text(payload.get("workingType")),
        price_protect=_optional_bool(payload.get("priceProtect")),
        created_at=created,
        updated_at=updated,
        manual_or_system="UNKNOWN",
    )


def _futures_algo_order(payload: Mapping[str, object]) -> FuturesAlgoOrderRecord:
    created = _ms_time(payload.get("time", payload.get("createdTime")), "time")
    return FuturesAlgoOrderRecord(
        algo_id=_id(payload.get("algoId"), "algoId"),
        client_algo_id=_text(payload.get("clientAlgoId"), "clientAlgoId"),
        symbol=_symbol(payload.get("symbol")),
        side=_text(payload.get("side"), "side").upper(),
        position_side=_position_side(payload.get("positionSide", "BOTH")),
        algo_type=_text(payload.get("type", payload.get("algoType")), "type").upper(),
        trigger_price=_decimal(
            payload.get("triggerPrice", payload.get("stopPrice", "0")),
            "triggerPrice",
        ),
        working_type=_text(payload.get("workingType", "MARK_PRICE"), "workingType"),
        quantity=_decimal(payload.get("quantity", payload.get("origQty")), "quantity"),
        close_position=_bool(payload.get("closePosition", False), "closePosition"),
        reduce_only=_bool(payload.get("reduceOnly", False), "reduceOnly"),
        activation_price=_optional_decimal(
            payload.get("activationPrice"), "activationPrice"
        ),
        callback_rate=_optional_decimal(payload.get("callbackRate"), "callbackRate"),
        status=_text(payload.get("status"), "status").upper(),
        created_at=created,
    )


def _futures_order_event(payload: Mapping[str, object]) -> FuturesOrderEventRecord:
    order = _mapping(payload.get("o"), "o")
    return FuturesOrderEventRecord(
        symbol=_symbol(order.get("s")),
        order_id=_id(order.get("i"), "i"),
        position_side=_position_side(order.get("ps", "BOTH")),
        event_type=_text(payload.get("e"), "e"),
        execution_type=_text(order.get("x"), "x").upper(),
        order_status=_text(order.get("X"), "X").upper(),
        last_executed_qty=_decimal(order.get("l", "0"), "l"),
        last_executed_price=_decimal(order.get("L", "0"), "L"),
        cumulative_filled_qty=_decimal(order.get("z", "0"), "z"),
        commission=_decimal(order.get("n", "0"), "n"),
        commission_asset=_optional_text(order.get("N")) or "NONE",
        realized_pnl=_signed_decimal(order.get("rp", "0"), "rp"),
        event_sequence=_integer(payload.get("T", payload.get("E")), "T"),
        event_time=_ms_time(payload.get("E"), "E"),
    )


def _futures_trade(payload: Mapping[str, object]) -> FuturesTradeRecord:
    return FuturesTradeRecord(
        trade_id=_id(payload.get("id"), "id"),
        order_id=_id(payload.get("orderId"), "orderId"),
        symbol=_symbol(payload.get("symbol")),
        side=_text(payload.get("side"), "side").upper(),
        position_side=_position_side(payload.get("positionSide", "BOTH")),
        price=_decimal(payload.get("price"), "price"),
        qty=_decimal(payload.get("qty"), "qty"),
        quote_qty=_decimal(payload.get("quoteQty"), "quoteQty"),
        realized_pnl=_signed_decimal(payload.get("realizedPnl", "0"), "realizedPnl"),
        commission=_decimal(payload.get("commission", "0"), "commission"),
        commission_asset=_text(payload.get("commissionAsset"), "commissionAsset"),
        is_maker=_bool(payload.get("maker"), "maker"),
        trade_time=_ms_time(payload.get("time"), "time"),
    )


def _futures_income(payload: Mapping[str, object]) -> FuturesIncomeRecord:
    return FuturesIncomeRecord(
        income_type=_text(payload.get("incomeType"), "incomeType").upper(),
        symbol=_optional_symbol(payload.get("symbol")),
        asset=_text(payload.get("asset"), "asset").upper(),
        income_amount=_signed_decimal(payload.get("income"), "income"),
        transaction_id=_id(payload.get("tranId"), "tranId"),
        trade_id=_optional_id(payload.get("tradeId")),
        info=_optional_text(payload.get("info")),
        income_time=_ms_time(payload.get("time"), "time"),
    )


def _futures_configuration(payload: Mapping[str, object]) -> FuturesConfigurationRecord:
    return FuturesConfigurationRecord(
        position_mode=_text(payload.get("positionMode"), "positionMode").upper(),
        multi_assets_mode=_bool(payload.get("multiAssetsMode"), "multiAssetsMode"),
        symbol=_symbol(payload.get("symbol")),
        leverage=_integer(payload.get("leverage"), "leverage"),
        margin_type=_text(payload.get("marginType"), "marginType").upper(),
        notional_bracket=_text(payload.get("notionalBracket"), "notionalBracket"),
        max_notional=_decimal(payload.get("maxNotional"), "maxNotional"),
        fee_tier=_text(payload.get("feeTier"), "feeTier"),
        bnb_burn_enabled=_bool(payload.get("bnbBurnEnabled"), "bnbBurnEnabled"),
        effective_from=_ms_time(payload.get("effectiveFrom"), "effectiveFrom"),
    )


def _unwrap_event(payload: Mapping[str, object]) -> Mapping[str, object]:
    nested = payload.get("event")
    return _mapping(nested, "event") if nested is not None else payload


def _product_for_event(event_type: str) -> ProductType:
    if event_type in {"executionReport", "balanceUpdate", "outboundAccountPosition"}:
        return ProductType.SPOT
    if event_type in {"ORDER_TRADE_UPDATE", "ACCOUNT_UPDATE"}:
        return ProductType.FUTURES_USDM
    raise ValueError("unsupported user data stream event")


def _payload_hash(payload: Mapping[str, object]) -> str:
    import json
    from hashlib import sha256

    encoded = json.dumps(
        to_primitive(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be an array")
    return cast(Sequence[object], value)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _text(value, "optionalText").upper()


def _symbol(value: object) -> str:
    normalized = _text(value, "symbol").upper()
    if not normalized.isascii() or not normalized.isalnum():
        raise ValueError("symbol must be uppercase ASCII alphanumeric")
    return normalized


def _optional_symbol(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _symbol(value)


def _position_side(value: object) -> str:
    side = _text(value, "positionSide").upper()
    if side not in {"LONG", "SHORT", "BOTH"}:
        raise ValueError("positionSide is invalid")
    return side


def _decimal(value: object, name: str) -> Decimal:
    parsed = _signed_decimal(value, name)
    if parsed < Decimal("0"):
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _optional_decimal(value: object, name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value, name)


def _signed_decimal(value: object, name: str) -> Decimal:
    if isinstance(value, float):
        raise ValueError(f"{name} must be text Decimal, not float")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be decimal-compatible") from None
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be integer-compatible")
    try:
        parsed = int(str(value))
    except ValueError:
        raise ValueError(f"{name} must be integer-compatible") from None
    if parsed < 0:
        raise ValueError(f"{name} cannot be negative")
    return parsed


def _id(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be id-compatible")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} cannot be blank")
    return normalized


def _optional_id(value: object) -> str | None:
    if value is None or value == "" or value == -1 or value == "-1":
        return None
    return _id(value, "optionalId")


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    return _bool(value, "optionalBool")


def _ms_time(
    value: object,
    name: str,
    *,
    fallback: datetime | None = None,
) -> datetime:
    if value is None or value == "":
        if fallback is None:
            raise ValueError(f"{name} timestamp is required")
        return fallback
    millis = _integer(value, name)
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("collector timestamps must be timezone-aware")
