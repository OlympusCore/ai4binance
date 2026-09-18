"""Append-only, product-separated Binance account monitoring records."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from ai4binance.application.runtime import DualMarketAdvisoryReport
from ai4binance.portfolio.analytics import PortfolioAnalytics
from ai4binance.portfolio.cost_basis import CostBasisReport
from ai4binance.portfolio.futures import FuturesAccountSnapshot, FuturesPosition
from ai4binance.portfolio.orders import AccountOpenOrder
from ai4binance.portfolio.wallet import SpotBalance, WalletSnapshot
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.storage.destination_verification import fail_verification


class ProductType(StrEnum):
    MULTI_PRODUCT = "MULTI_PRODUCT"
    SPOT = "SPOT"
    FUTURES_USDM = "FUTURES_USDM"
    FUTURES_COINM = "FUTURES_COINM"


class SourceType(StrEnum):
    REST = "REST"
    WEBSOCKET = "WEBSOCKET"
    DERIVED = "DERIVED"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True)
class SpotOrderRecord:
    """One Spot order identity for append-only order history."""

    symbol: str
    order_id: str
    client_order_id: str
    side: str
    order_type: str
    status: str
    price: Decimal
    orig_qty: Decimal
    executed_qty: Decimal
    cumulative_quote_qty: Decimal
    order_created_at: datetime
    last_update_at: datetime
    order_list_id: str | None = None
    time_in_force: str | None = None
    stop_price: Decimal | None = None
    final_status: str | None = None
    cancel_reason: str | None = None
    reject_reason: str | None = None
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    expired_at: datetime | None = None
    average_fill_price: Decimal | None = None
    total_commission: Decimal | None = None
    commission_asset: str | None = None
    strategy_id: str | None = None
    signal_id: str | None = None
    manual_or_system: str = "UNKNOWN"

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        for text_value in (
            self.order_id,
            self.client_order_id,
            self.side,
            self.order_type,
            self.status,
            self.manual_or_system,
        ):
            _require_text(text_value)
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("Spot order side is invalid")
        _require_decimal(self.price, "price")
        _require_decimal(self.orig_qty, "orig_qty", positive=True)
        _require_decimal(self.executed_qty, "executed_qty")
        _require_decimal(self.cumulative_quote_qty, "cumulative_quote_qty")
        if self.executed_qty > self.orig_qty:
            raise ValueError("Spot order executed quantity exceeds original quantity")
        for timestamp_value in (
            self.order_created_at,
            self.last_update_at,
            self.filled_at,
            self.cancelled_at,
            self.expired_at,
        ):
            if timestamp_value is not None:
                _require_aware(timestamp_value)
        for decimal_value, name in (
            (self.stop_price, "stop_price"),
            (self.average_fill_price, "average_fill_price"),
            (self.total_commission, "total_commission"),
        ):
            if decimal_value is not None:
                _require_decimal(decimal_value, name)
        for optional_text in (
            self.order_list_id,
            self.time_in_force,
            self.final_status,
            self.cancel_reason,
            self.reject_reason,
            self.commission_asset,
            self.strategy_id,
            self.signal_id,
        ):
            if optional_text is not None:
                _require_text(optional_text)

    @property
    def remaining_qty(self) -> Decimal:
        return self.orig_qty - self.executed_qty


@dataclass(frozen=True, slots=True)
class SpotOrderEventRecord:
    """One Spot order lifecycle event."""

    symbol: str
    order_id: str
    event_type: str
    execution_type: str
    order_status: str
    last_executed_qty: Decimal
    last_executed_price: Decimal
    cumulative_filled_qty: Decimal
    commission: Decimal
    commission_asset: str
    event_sequence: int
    event_time: datetime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        for text_value in (
            self.order_id,
            self.event_type,
            self.execution_type,
            self.order_status,
            self.commission_asset,
        ):
            _require_text(text_value)
        for decimal_value, name in (
            (self.last_executed_qty, "last_executed_qty"),
            (self.last_executed_price, "last_executed_price"),
            (self.cumulative_filled_qty, "cumulative_filled_qty"),
            (self.commission, "commission"),
        ):
            _require_decimal(decimal_value, name)
        if isinstance(self.event_sequence, bool) or self.event_sequence < 0:
            raise ValueError("Spot order event sequence is invalid")
        _require_aware(self.event_time)


@dataclass(frozen=True, slots=True)
class SpotTradeRecord:
    """One immutable Spot fill/trade record."""

    symbol: str
    trade_id: str
    order_id: str
    price: Decimal
    qty: Decimal
    quote_qty: Decimal
    commission: Decimal
    commission_asset: str
    is_buyer: bool
    is_maker: bool
    trade_time: datetime
    order_list_id: str | None = None

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        for text_value in (self.trade_id, self.order_id, self.commission_asset):
            _require_text(text_value)
        for decimal_value, name in (
            (self.price, "price"),
            (self.qty, "qty"),
            (self.quote_qty, "quote_qty"),
            (self.commission, "commission"),
        ):
            _require_decimal(decimal_value, name, positive=name != "commission")
        if not isinstance(self.is_buyer, bool) or not isinstance(self.is_maker, bool):
            raise ValueError("Spot trade maker/buyer flags are invalid")
        if self.order_list_id is not None:
            _require_text(self.order_list_id)
        _require_aware(self.trade_time)


@dataclass(frozen=True, slots=True)
class SpotCapitalFlowRecord:
    """One non-trade Spot balance movement."""

    flow_id: str
    flow_type: str
    asset: str
    amount: Decimal
    direction: str
    transaction_id: str
    source_wallet: str
    destination_wallet: str
    status: str
    event_time: datetime

    def __post_init__(self) -> None:
        for text_value in (
            self.flow_id,
            self.flow_type,
            self.asset,
            self.direction,
            self.transaction_id,
            self.source_wallet,
            self.destination_wallet,
            self.status,
        ):
            _require_text(text_value)
        if self.direction not in {"IN", "OUT", "INTERNAL"}:
            raise ValueError("Spot capital flow direction is invalid")
        _require_decimal(self.amount, "amount", positive=True)
        _require_aware(self.event_time)


@dataclass(frozen=True, slots=True)
class FuturesPositionRecord:
    """One USD-M Futures open position snapshot."""

    symbol: str
    position_side: str
    position_amt: Decimal
    entry_price: Decimal
    mark_price: Decimal
    notional: Decimal
    unrealized_pnl: Decimal
    leverage: int
    margin_type: str
    margin_asset: str
    isolated_margin: Decimal
    position_update_time: datetime
    break_even_price: Decimal | None = None
    liquidation_price: Decimal | None = None
    isolated_wallet: Decimal | None = None
    initial_margin: Decimal | None = None
    maintenance_margin: Decimal | None = None

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_position_side(self.position_side)
        _require_text(self.margin_type)
        _require_text(self.margin_asset)
        _require_decimal(self.position_amt, "position_amt", allow_negative=True)
        if self.position_amt == Decimal("0"):
            raise ValueError("Futures open position amount cannot be zero")
        _require_decimal(self.entry_price, "entry_price")
        _require_decimal(self.mark_price, "mark_price")
        _require_decimal(self.notional, "notional", allow_negative=True)
        _require_decimal(self.unrealized_pnl, "unrealized_pnl", allow_negative=True)
        _require_decimal(self.isolated_margin, "isolated_margin")
        for decimal_value, name in (
            (self.break_even_price, "break_even_price"),
            (self.liquidation_price, "liquidation_price"),
            (self.isolated_wallet, "isolated_wallet"),
            (self.initial_margin, "initial_margin"),
            (self.maintenance_margin, "maintenance_margin"),
        ):
            if decimal_value is not None:
                _require_decimal(decimal_value, name)
        if isinstance(self.leverage, bool) or self.leverage < 1:
            raise ValueError("Futures leverage is invalid")
        _require_aware(self.position_update_time)


@dataclass(frozen=True, slots=True)
class FuturesPositionEventRecord:
    """One USD-M Futures position lifecycle event."""

    symbol: str
    position_side: str
    previous_position_amt: Decimal
    new_position_amt: Decimal
    quantity_delta: Decimal
    previous_entry_price: Decimal
    new_entry_price: Decimal
    realized_pnl_delta: Decimal
    unrealized_pnl: Decimal
    event_reason: str
    event_time: datetime
    event_sequence: int

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_position_side(self.position_side)
        _require_text(self.event_reason)
        for decimal_value, name in (
            (self.previous_position_amt, "previous_position_amt"),
            (self.new_position_amt, "new_position_amt"),
            (self.quantity_delta, "quantity_delta"),
            (self.realized_pnl_delta, "realized_pnl_delta"),
            (self.unrealized_pnl, "unrealized_pnl"),
        ):
            _require_decimal(decimal_value, name, allow_negative=True)
        _require_decimal(self.previous_entry_price, "previous_entry_price")
        _require_decimal(self.new_entry_price, "new_entry_price")
        if isinstance(self.event_sequence, bool) or self.event_sequence < 0:
            raise ValueError("Futures position event sequence is invalid")
        _require_aware(self.event_time)


@dataclass(frozen=True, slots=True)
class FuturesOrderRecord:
    """One USD-M Futures order identity for append-only history."""

    symbol: str
    order_id: str
    client_order_id: str
    side: str
    position_side: str
    order_type: str
    orig_type: str
    status: str
    price: Decimal
    average_price: Decimal
    orig_qty: Decimal
    executed_qty: Decimal
    reduce_only: bool
    close_position: bool
    created_at: datetime
    updated_at: datetime
    time_in_force: str | None = None
    working_type: str | None = None
    price_protect: bool | None = None
    original_order_id: str | None = None
    amendment_number: int | None = None
    cancel_reason: str | None = None
    reject_code: str | None = None
    reject_message: str | None = None
    strategy_id: str | None = None
    signal_id: str | None = None
    manual_or_system: str = "UNKNOWN"

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_position_side(self.position_side)
        for text_value in (
            self.order_id,
            self.client_order_id,
            self.side,
            self.order_type,
            self.orig_type,
            self.status,
            self.manual_or_system,
        ):
            _require_text(text_value)
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("Futures order side is invalid")
        for decimal_value, name in (
            (self.price, "price"),
            (self.average_price, "average_price"),
            (self.orig_qty, "orig_qty"),
            (self.executed_qty, "executed_qty"),
        ):
            _require_decimal(decimal_value, name)
        if self.orig_qty == Decimal("0"):
            raise ValueError("Futures order original quantity cannot be zero")
        if self.executed_qty > self.orig_qty:
            raise ValueError("Futures order executed quantity exceeds original")
        for bool_value in (self.reduce_only, self.close_position):
            if not isinstance(bool_value, bool):
                raise ValueError("Futures order boolean flags are invalid")
        if self.price_protect is not None and not isinstance(self.price_protect, bool):
            raise ValueError("Futures order price_protect flag is invalid")
        if self.amendment_number is not None and (
            isinstance(self.amendment_number, bool) or self.amendment_number < 0
        ):
            raise ValueError("Futures order amendment number is invalid")
        for timestamp_value in (self.created_at, self.updated_at):
            _require_aware(timestamp_value)
        for optional_text in (
            self.time_in_force,
            self.working_type,
            self.original_order_id,
            self.cancel_reason,
            self.reject_code,
            self.reject_message,
            self.strategy_id,
            self.signal_id,
        ):
            if optional_text is not None:
                _require_text(optional_text)

    @property
    def remaining_qty(self) -> Decimal:
        return self.orig_qty - self.executed_qty


@dataclass(frozen=True, slots=True)
class FuturesAlgoOrderRecord:
    """One USD-M Futures conditional/algo order."""

    algo_id: str
    client_algo_id: str
    symbol: str
    side: str
    position_side: str
    algo_type: str
    trigger_price: Decimal
    working_type: str
    quantity: Decimal
    close_position: bool
    reduce_only: bool
    status: str
    created_at: datetime
    activation_price: Decimal | None = None
    callback_rate: Decimal | None = None
    triggered_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_position_side(self.position_side)
        for text_value in (
            self.algo_id,
            self.client_algo_id,
            self.side,
            self.algo_type,
            self.working_type,
            self.status,
        ):
            _require_text(text_value)
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("Futures algo order side is invalid")
        for decimal_value, name in (
            (self.trigger_price, "trigger_price"),
            (self.quantity, "quantity"),
            (self.activation_price, "activation_price"),
            (self.callback_rate, "callback_rate"),
        ):
            if decimal_value is not None:
                _require_decimal(decimal_value, name, positive=name == "quantity")
        for bool_value in (self.close_position, self.reduce_only):
            if not isinstance(bool_value, bool):
                raise ValueError("Futures algo order boolean flags are invalid")
        _require_aware(self.created_at)
        if self.triggered_at is not None:
            _require_aware(self.triggered_at)


@dataclass(frozen=True, slots=True)
class FuturesOrderEventRecord:
    """One USD-M Futures order lifecycle event."""

    symbol: str
    order_id: str
    position_side: str
    event_type: str
    execution_type: str
    order_status: str
    last_executed_qty: Decimal
    last_executed_price: Decimal
    cumulative_filled_qty: Decimal
    commission: Decimal
    commission_asset: str
    realized_pnl: Decimal
    event_sequence: int
    event_time: datetime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_position_side(self.position_side)
        for text_value in (
            self.order_id,
            self.event_type,
            self.execution_type,
            self.order_status,
            self.commission_asset,
        ):
            _require_text(text_value)
        for decimal_value, name in (
            (self.last_executed_qty, "last_executed_qty"),
            (self.last_executed_price, "last_executed_price"),
            (self.cumulative_filled_qty, "cumulative_filled_qty"),
            (self.commission, "commission"),
        ):
            _require_decimal(decimal_value, name)
        _require_decimal(self.realized_pnl, "realized_pnl", allow_negative=True)
        if isinstance(self.event_sequence, bool) or self.event_sequence < 0:
            raise ValueError("Futures order event sequence is invalid")
        _require_aware(self.event_time)


@dataclass(frozen=True, slots=True)
class FuturesTradeRecord:
    """One immutable USD-M Futures fill/trade record."""

    trade_id: str
    order_id: str
    symbol: str
    side: str
    position_side: str
    price: Decimal
    qty: Decimal
    quote_qty: Decimal
    realized_pnl: Decimal
    commission: Decimal
    commission_asset: str
    is_maker: bool
    trade_time: datetime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_position_side(self.position_side)
        for text_value in (
            self.trade_id,
            self.order_id,
            self.side,
            self.commission_asset,
        ):
            _require_text(text_value)
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("Futures trade side is invalid")
        for decimal_value, name in (
            (self.price, "price"),
            (self.qty, "qty"),
            (self.quote_qty, "quote_qty"),
            (self.commission, "commission"),
        ):
            _require_decimal(decimal_value, name, positive=name != "commission")
        _require_decimal(self.realized_pnl, "realized_pnl", allow_negative=True)
        if not isinstance(self.is_maker, bool):
            raise ValueError("Futures trade maker flag is invalid")
        _require_aware(self.trade_time)


@dataclass(frozen=True, slots=True)
class FuturesIncomeRecord:
    """One USD-M Futures income ledger row."""

    income_type: str
    asset: str
    income_amount: Decimal
    transaction_id: str
    income_time: datetime
    symbol: str | None = None
    trade_id: str | None = None
    info: str | None = None

    def __post_init__(self) -> None:
        for text_value in (self.income_type, self.asset, self.transaction_id):
            _require_text(text_value)
        _require_decimal(self.income_amount, "income_amount", allow_negative=True)
        _require_aware(self.income_time)
        if self.symbol is not None:
            _require_symbol(self.symbol)
        for optional_text in (self.trade_id, self.info):
            if optional_text is not None:
                _require_text(optional_text)


@dataclass(frozen=True, slots=True)
class FuturesConfigurationRecord:
    """One USD-M Futures account/symbol configuration snapshot."""

    position_mode: str
    multi_assets_mode: bool
    symbol: str
    leverage: int
    margin_type: str
    notional_bracket: str
    max_notional: Decimal
    fee_tier: str
    bnb_burn_enabled: bool
    effective_from: datetime

    def __post_init__(self) -> None:
        if self.position_mode not in {"ONE_WAY", "HEDGE"}:
            raise ValueError("Futures position mode is invalid")
        if not isinstance(self.multi_assets_mode, bool) or not isinstance(
            self.bnb_burn_enabled, bool
        ):
            raise ValueError("Futures configuration boolean flags are invalid")
        _require_symbol(self.symbol)
        for text_value in (self.margin_type, self.notional_bracket, self.fee_tier):
            _require_text(text_value)
        if isinstance(self.leverage, bool) or self.leverage < 1:
            raise ValueError("Futures configuration leverage is invalid")
        _require_decimal(self.max_notional, "max_notional", positive=True)
        _require_aware(self.effective_from)


@dataclass(frozen=True, slots=True)
class RawApiEventRecord:
    """One redacted raw REST/WebSocket ingestion event identity."""

    product_type: ProductType
    stream_name: str
    event_type: str
    event_time: datetime
    received_at: datetime
    payload_hash: str
    processing_status: str
    payload_stored: bool = False

    def __post_init__(self) -> None:
        if self.product_type is ProductType.MULTI_PRODUCT:
            raise ValueError("raw API event must be product-scoped")
        for text_value in (
            self.stream_name,
            self.event_type,
            self.payload_hash,
            self.processing_status,
        ):
            _require_text(text_value)
        if not isinstance(self.payload_stored, bool):
            raise ValueError("raw API payload storage flag is invalid")
        _require_aware(self.event_time)
        _require_aware(self.received_at)


@dataclass(frozen=True, slots=True)
class ReconciliationResultRecord:
    """One REST-vs-WebSocket reconciliation finding."""

    product_type: ProductType
    entity_type: str
    entity_id: str
    rest_value: object
    stream_value: object
    difference: object
    severity: str
    reconciled_at: datetime
    resolution: str
    data_quality_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.product_type is ProductType.MULTI_PRODUCT:
            raise ValueError("reconciliation result must be product-scoped")
        for text_value in (
            self.entity_type,
            self.entity_id,
            self.severity,
            self.resolution,
        ):
            _require_text(text_value)
        if self.severity not in {"OK", "INFO", "WARNING", "CRITICAL", "BLOCKED"}:
            raise ValueError("reconciliation severity is invalid")
        if any(not issue.strip() for issue in self.data_quality_issues):
            raise ValueError("reconciliation issues cannot be blank")
        _require_aware(self.reconciled_at)


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    """Trace fields shared by Spot, Futures and common sync records."""

    account_id: str
    environment: str
    product_type: ProductType
    snapshot_id: str
    source_type: SourceType
    endpoint: str
    event_time: datetime
    transaction_time: datetime | None
    received_at: datetime
    server_time: datetime | None
    schema_version: str
    raw_payload_hash: str
    sync_run_id: str
    is_reconciled: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.environment not in {"production", "testnet"}:
            raise ValueError("environment must be production or testnet")
        if self.schema_version != "1.0":
            raise ValueError("unsupported accounting schema version")
        identities = (
            self.account_id,
            self.snapshot_id,
            self.endpoint,
            self.raw_payload_hash,
            self.sync_run_id,
        )
        if any(not value.strip() for value in identities):
            raise ValueError("record envelope identity is required")
        for timestamp in (
            self.event_time,
            self.received_at,
            self.created_at,
            self.updated_at,
        ):
            _require_aware(timestamp)
        if self.transaction_time is not None:
            _require_aware(self.transaction_time)
        if self.server_time is not None:
            _require_aware(self.server_time)


@dataclass(frozen=True, slots=True)
class BinanceAccountLedger:
    """Write normalized records into shared, Spot and USD-M Futures ledgers."""

    root: Path
    account_id: str = "default-readonly"
    environment: str = "production"

    def append_runtime_report(self, report: DualMarketAdvisoryReport) -> None:
        """Persist one runtime cycle without merging Spot and Futures semantics."""
        self._append_shared(report)
        if report.spot_wallet is not None:
            self._append_spot(report, report.spot_wallet)
        if report.futures_account is not None:
            self._append_futures(report, report.futures_account)

    def append_spot_order(
        self,
        record: SpotOrderRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/api/v3/allOrders",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one Spot order identity once.

        Returns ``False`` when the product-scoped unique key was already written.
        """
        unique_key = self._spot_unique_key(record.symbol, record.order_id)
        payload = {
            "symbol": record.symbol,
            "order_id": record.order_id,
            "client_order_id": record.client_order_id,
            "order_list_id": record.order_list_id,
            "side": record.side,
            "order_type": record.order_type,
            "time_in_force": record.time_in_force,
            "price": record.price,
            "stop_price": record.stop_price,
            "orig_qty": record.orig_qty,
            "executed_qty": record.executed_qty,
            "remaining_qty": record.remaining_qty,
            "cumulative_quote_qty": record.cumulative_quote_qty,
            "status": record.status,
            "final_status": record.final_status,
            "cancel_reason": record.cancel_reason,
            "reject_reason": record.reject_reason,
            "filled_at": record.filled_at,
            "cancelled_at": record.cancelled_at,
            "expired_at": record.expired_at,
            "average_fill_price": record.average_fill_price,
            "total_commission": record.total_commission,
            "commission_asset": record.commission_asset,
            "strategy_id": record.strategy_id,
            "signal_id": record.signal_id,
            "manual_or_system": record.manual_or_system,
            "order_created_at": record.order_created_at,
            "last_update_at": record.last_update_at,
        }
        return self._append_unique(
            "spot",
            "orders.jsonl",
            "SPOT_ORDER_RECORDED",
            record.last_update_at,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.SPOT,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.last_update_at,
                    transaction_time=record.filled_at,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_spot_order_event(
        self,
        record: SpotOrderEventRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.WEBSOCKET,
        endpoint: str = "spot:user_data_stream:executionReport",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = False,
    ) -> bool:
        """Append one Spot order lifecycle event once."""
        unique_key = ":".join(
            (
                self._spot_unique_key(record.symbol, record.order_id),
                str(record.event_sequence),
                record.execution_type,
                record.event_time.isoformat(),
            )
        )
        payload = {
            "symbol": record.symbol,
            "order_id": record.order_id,
            "event_type": record.event_type,
            "execution_type": record.execution_type,
            "order_status": record.order_status,
            "last_executed_qty": record.last_executed_qty,
            "last_executed_price": record.last_executed_price,
            "cumulative_filled_qty": record.cumulative_filled_qty,
            "commission": record.commission,
            "commission_asset": record.commission_asset,
            "event_sequence": record.event_sequence,
            "event_time": record.event_time,
        }
        return self._append_unique(
            "spot",
            "order_events.jsonl",
            "SPOT_ORDER_EVENT_RECORDED",
            record.event_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.SPOT,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.event_time,
                    transaction_time=record.event_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "raw_event_stored": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_spot_trade(
        self,
        record: SpotTradeRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/api/v3/myTrades",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one Spot fill/trade once."""
        unique_key = ":".join(
            (
                "SPOT",
                self.account_id,
                record.symbol,
                record.trade_id,
            )
        )
        payload = {
            "symbol": record.symbol,
            "trade_id": record.trade_id,
            "order_id": record.order_id,
            "order_list_id": record.order_list_id,
            "price": record.price,
            "qty": record.qty,
            "quote_qty": record.quote_qty,
            "commission": record.commission,
            "commission_asset": record.commission_asset,
            "is_buyer": record.is_buyer,
            "is_maker": record.is_maker,
            "trade_time": record.trade_time,
        }
        return self._append_unique(
            "spot",
            "trades.jsonl",
            "SPOT_TRADE_RECORDED",
            record.trade_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.SPOT,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.trade_time,
                    transaction_time=record.trade_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_spot_capital_flow(
        self,
        record: SpotCapitalFlowRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "spot:capital_flow",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one non-trade Spot balance movement once."""
        unique_key = ":".join(
            (
                "SPOT",
                self.account_id,
                record.flow_type,
                record.transaction_id,
                record.flow_id,
            )
        )
        payload = {
            "flow_id": record.flow_id,
            "flow_type": record.flow_type,
            "asset": record.asset,
            "amount": record.amount,
            "direction": record.direction,
            "transaction_id": record.transaction_id,
            "source_wallet": record.source_wallet,
            "destination_wallet": record.destination_wallet,
            "status": record.status,
            "event_time": record.event_time,
        }
        return self._append_unique(
            "spot",
            "capital_flows.jsonl",
            "SPOT_CAPITAL_FLOW_RECORDED",
            record.event_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.SPOT,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.event_time,
                    transaction_time=record.event_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_position(
        self,
        record: FuturesPositionRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/fapi/v3/positionRisk",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one USD-M Futures open position snapshot once per cycle."""
        unique_key = self._futures_position_unique_key(
            snapshot_id, record.symbol, record.position_side
        )
        payload = {
            "symbol": record.symbol,
            "position_side": record.position_side,
            "position_amt": record.position_amt,
            "entry_price": record.entry_price,
            "break_even_price": record.break_even_price,
            "mark_price": record.mark_price,
            "notional": record.notional,
            "unrealized_pnl": record.unrealized_pnl,
            "liquidation_price": record.liquidation_price,
            "leverage": record.leverage,
            "margin_type": record.margin_type,
            "margin_asset": record.margin_asset,
            "isolated_margin": record.isolated_margin,
            "isolated_wallet": record.isolated_wallet,
            "initial_margin": record.initial_margin,
            "maintenance_margin": record.maintenance_margin,
            "position_update_time": record.position_update_time,
        }
        return self._append_unique(
            "futures_usdm",
            "positions_current.jsonl",
            "FUTURES_USDM_POSITION_RECORDED",
            record.position_update_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.position_update_time,
                    transaction_time=None,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_position_event(
        self,
        record: FuturesPositionEventRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.WEBSOCKET,
        endpoint: str = "futures:user_data_stream:ACCOUNT_UPDATE",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = False,
    ) -> bool:
        """Append one USD-M Futures position lifecycle event once."""
        unique_key = ":".join(
            (
                self._futures_position_unique_key(
                    snapshot_id, record.symbol, record.position_side
                ),
                str(record.event_sequence),
                record.event_reason,
                record.event_time.isoformat(),
            )
        )
        payload = {
            "symbol": record.symbol,
            "position_side": record.position_side,
            "previous_position_amt": record.previous_position_amt,
            "new_position_amt": record.new_position_amt,
            "quantity_delta": record.quantity_delta,
            "previous_entry_price": record.previous_entry_price,
            "new_entry_price": record.new_entry_price,
            "realized_pnl_delta": record.realized_pnl_delta,
            "unrealized_pnl": record.unrealized_pnl,
            "event_reason": record.event_reason,
            "event_time": record.event_time,
            "event_sequence": record.event_sequence,
        }
        return self._append_unique(
            "futures_usdm",
            "position_events.jsonl",
            "FUTURES_USDM_POSITION_EVENT_RECORDED",
            record.event_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.event_time,
                    transaction_time=record.event_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "raw_event_stored": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_order(
        self,
        record: FuturesOrderRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/fapi/v1/allOrders",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one USD-M Futures order identity once."""
        unique_key = self._futures_order_unique_key(record.symbol, record.order_id)
        payload = {
            "symbol": record.symbol,
            "order_id": record.order_id,
            "client_order_id": record.client_order_id,
            "side": record.side,
            "position_side": record.position_side,
            "order_type": record.order_type,
            "orig_type": record.orig_type,
            "price": record.price,
            "average_price": record.average_price,
            "orig_qty": record.orig_qty,
            "executed_qty": record.executed_qty,
            "remaining_qty": record.remaining_qty,
            "reduce_only": record.reduce_only,
            "close_position": record.close_position,
            "time_in_force": record.time_in_force,
            "working_type": record.working_type,
            "price_protect": record.price_protect,
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "original_order_id": record.original_order_id,
            "amendment_number": record.amendment_number,
            "cancel_reason": record.cancel_reason,
            "reject_code": record.reject_code,
            "reject_message": record.reject_message,
            "strategy_id": record.strategy_id,
            "signal_id": record.signal_id,
            "manual_or_system": record.manual_or_system,
        }
        return self._append_unique(
            "futures_usdm",
            "orders.jsonl",
            "FUTURES_USDM_ORDER_RECORDED",
            record.updated_at,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.updated_at,
                    transaction_time=None,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_algo_order(
        self,
        record: FuturesAlgoOrderRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/fapi/v1/openAlgoOrders",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one USD-M Futures conditional/algo order once."""
        unique_key = ":".join(("FUTURES_USDM", self.account_id, record.algo_id))
        event_time = record.triggered_at or record.created_at
        payload = {
            "algo_id": record.algo_id,
            "client_algo_id": record.client_algo_id,
            "symbol": record.symbol,
            "side": record.side,
            "position_side": record.position_side,
            "algo_type": record.algo_type,
            "trigger_price": record.trigger_price,
            "working_type": record.working_type,
            "quantity": record.quantity,
            "close_position": record.close_position,
            "reduce_only": record.reduce_only,
            "activation_price": record.activation_price,
            "callback_rate": record.callback_rate,
            "status": record.status,
            "created_at": record.created_at,
            "triggered_at": record.triggered_at,
        }
        return self._append_unique(
            "futures_usdm",
            "algo_orders.jsonl",
            "FUTURES_USDM_ALGO_ORDER_RECORDED",
            event_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=event_time,
                    transaction_time=record.triggered_at,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_order_event(
        self,
        record: FuturesOrderEventRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.WEBSOCKET,
        endpoint: str = "futures:user_data_stream:ORDER_TRADE_UPDATE",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = False,
    ) -> bool:
        """Append one USD-M Futures order lifecycle event once."""
        unique_key = ":".join(
            (
                self._futures_order_unique_key(record.symbol, record.order_id),
                record.position_side,
                str(record.event_sequence),
                record.execution_type,
                record.event_time.isoformat(),
            )
        )
        payload = {
            "symbol": record.symbol,
            "order_id": record.order_id,
            "position_side": record.position_side,
            "event_type": record.event_type,
            "execution_type": record.execution_type,
            "order_status": record.order_status,
            "last_executed_qty": record.last_executed_qty,
            "last_executed_price": record.last_executed_price,
            "cumulative_filled_qty": record.cumulative_filled_qty,
            "commission": record.commission,
            "commission_asset": record.commission_asset,
            "realized_pnl": record.realized_pnl,
            "event_sequence": record.event_sequence,
            "event_time": record.event_time,
        }
        return self._append_unique(
            "futures_usdm",
            "order_events.jsonl",
            "FUTURES_USDM_ORDER_EVENT_RECORDED",
            record.event_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.event_time,
                    transaction_time=record.event_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "raw_event_stored": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_trade(
        self,
        record: FuturesTradeRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/fapi/v1/userTrades",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one USD-M Futures fill/trade once."""
        unique_key = ":".join(
            ("FUTURES_USDM", self.account_id, record.symbol, record.trade_id)
        )
        payload = {
            "trade_id": record.trade_id,
            "order_id": record.order_id,
            "symbol": record.symbol,
            "side": record.side,
            "position_side": record.position_side,
            "price": record.price,
            "qty": record.qty,
            "quote_qty": record.quote_qty,
            "realized_pnl": record.realized_pnl,
            "commission": record.commission,
            "commission_asset": record.commission_asset,
            "is_maker": record.is_maker,
            "trade_time": record.trade_time,
        }
        return self._append_unique(
            "futures_usdm",
            "trades.jsonl",
            "FUTURES_USDM_TRADE_RECORDED",
            record.trade_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.trade_time,
                    transaction_time=record.trade_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_income(
        self,
        record: FuturesIncomeRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "/fapi/v1/income",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one USD-M Futures income ledger row once."""
        unique_key = ":".join(
            ("FUTURES_USDM", self.account_id, record.income_type, record.transaction_id)
        )
        payload = {
            "income_type": record.income_type,
            "symbol": record.symbol,
            "asset": record.asset,
            "income_amount": record.income_amount,
            "transaction_id": record.transaction_id,
            "trade_id": record.trade_id,
            "info": record.info,
            "income_time": record.income_time,
        }
        return self._append_unique(
            "futures_usdm",
            "income_ledger.jsonl",
            "FUTURES_USDM_INCOME_RECORDED",
            record.income_time,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.income_time,
                    transaction_time=record.income_time,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_futures_configuration(
        self,
        record: FuturesConfigurationRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.REST,
        endpoint: str = "futures:configuration",
        received_at: datetime | None = None,
        server_time: datetime | None = None,
        is_reconciled: bool = True,
    ) -> bool:
        """Append one USD-M Futures configuration snapshot once."""
        unique_key = ":".join(
            (
                "FUTURES_USDM",
                self.account_id,
                snapshot_id,
                record.symbol,
                record.position_mode,
            )
        )
        payload = {
            "position_mode": record.position_mode,
            "multi_assets_mode": record.multi_assets_mode,
            "symbol": record.symbol,
            "leverage": record.leverage,
            "margin_type": record.margin_type,
            "notional_bracket": record.notional_bracket,
            "max_notional": record.max_notional,
            "fee_tier": record.fee_tier,
            "bnb_burn_enabled": record.bnb_burn_enabled,
            "effective_from": record.effective_from,
        }
        return self._append_unique(
            "futures_usdm",
            "configuration_snapshots.jsonl",
            "FUTURES_USDM_CONFIGURATION_RECORDED",
            record.effective_from,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    ProductType.FUTURES_USDM,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.effective_from,
                    transaction_time=None,
                    received_at=received_at,
                    server_time=server_time,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_raw_api_event(
        self,
        record: RawApiEventRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType,
        endpoint: str,
        is_reconciled: bool = False,
    ) -> bool:
        """Append one redacted raw REST/WebSocket event identity once."""
        unique_key = ":".join(
            (
                record.product_type.value,
                record.payload_hash,
                record.event_time.isoformat(),
                record.event_type,
            )
        )
        payload = {
            "product_type": record.product_type,
            "stream_name": record.stream_name,
            "event_type": record.event_type,
            "event_time": record.event_time,
            "received_at": record.received_at,
            "payload_hash": record.payload_hash,
            "payload_stored": record.payload_stored,
            "processing_status": record.processing_status,
        }
        return self._append_unique(
            "shared",
            "raw_api_events.jsonl",
            "RAW_API_EVENT_RECORDED",
            record.received_at,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    record.product_type,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.event_time,
                    transaction_time=record.event_time,
                    received_at=record.received_at,
                    server_time=None,
                    is_reconciled=is_reconciled,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def append_reconciliation_result(
        self,
        record: ReconciliationResultRecord,
        *,
        snapshot_id: str,
        sync_run_id: str,
        source_type: SourceType = SourceType.DERIVED,
        endpoint: str = "accounting:reconciliation",
    ) -> bool:
        """Append one product-scoped reconciliation result once."""
        unique_key = ":".join(
            (
                record.product_type.value,
                self.account_id,
                sync_run_id,
                record.entity_type,
                record.entity_id,
                record.severity,
            )
        )
        payload = {
            "product_type": record.product_type,
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
            "rest_value": record.rest_value,
            "stream_value": record.stream_value,
            "difference": record.difference,
            "severity": record.severity,
            "reconciled_at": record.reconciled_at,
            "resolution": record.resolution,
            "data_quality_issues": record.data_quality_issues,
        }
        return self._append_unique(
            "shared",
            "reconciliation_results.jsonl",
            "RECONCILIATION_RESULT_RECORDED",
            record.reconciled_at,
            unique_key,
            {
                "envelope": self._standalone_envelope(
                    record.product_type,
                    snapshot_id=snapshot_id,
                    sync_run_id=sync_run_id,
                    endpoint=endpoint,
                    source_type=source_type,
                    payload=payload,
                    event_time=record.reconciled_at,
                    transaction_time=None,
                    received_at=record.reconciled_at,
                    server_time=None,
                    is_reconciled=record.severity == "OK",
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _append_shared(self, report: DualMarketAdvisoryReport) -> None:
        envelope = self._envelope(
            report,
            ProductType.MULTI_PRODUCT,
            endpoint="runtime:read_only_cycle",
            source_type=SourceType.DERIVED,
            payload={
                "cycle_id": report.cycle_id,
                "spot_state": report.spot,
                "futures_state": report.futures,
                "blockers": report.blockers,
            },
            is_reconciled=False,
        )
        self._append(
            "shared",
            "api_sync_runs.jsonl",
            "API_SYNC_RUN_RECORDED",
            report.created_at,
            report.cycle_id,
            {
                "envelope": envelope,
                "status": "DEGRADED" if report.blockers else "PASSED",
                "record_count": self._record_count(report),
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )
        self._append(
            "shared",
            "raw_api_events.jsonl",
            "RAW_API_EVENT_RECORDED",
            report.created_at,
            report.cycle_id,
            {
                "envelope": envelope,
                "payload_hash": envelope.raw_payload_hash,
                "payload_stored": False,
                "processing_status": "NORMALIZED_DERIVED_RUNTIME",
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )
        self._append(
            "shared",
            "reconciliation_results.jsonl",
            "RECONCILIATION_RESULT_RECORDED",
            report.created_at,
            report.cycle_id,
            {
                "envelope": envelope,
                "entity_type": "ACCOUNT_RUNTIME_CYCLE",
                "entity_id": report.cycle_id,
                "severity": "BLOCKED" if report.blockers else "OK",
                "differences": report.blockers,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _append_spot(
        self,
        report: DualMarketAdvisoryReport,
        wallet: WalletSnapshot,
    ) -> None:
        account_payload = {
            "can_trade": wallet.can_trade,
            "account_type": wallet.account_status,
            "open_order_count": wallet.open_order_count,
        }
        self._append(
            "spot",
            "account_snapshots.jsonl",
            "SPOT_ACCOUNT_SNAPSHOT_RECORDED",
            wallet.captured_at,
            report.cycle_id,
            {
                "envelope": self._envelope(
                    report,
                    ProductType.SPOT,
                    endpoint="/api/v3/account",
                    source_type=SourceType.REST,
                    payload=account_payload,
                    event_time=wallet.captured_at,
                    is_reconciled=True,
                ),
                **account_payload,
                "execution_allowed": False,
            },
        )
        analytics = report.portfolio_analytics
        for balance in wallet.balances:
            if balance.free + balance.locked <= Decimal("0"):
                continue
            self._append_spot_balance(report, wallet, balance, analytics)
        for order in wallet.open_orders:
            self._append_order(
                "spot",
                "open_orders_current.jsonl",
                "SPOT_OPEN_ORDER_RECORDED",
                report,
                order,
                ProductType.SPOT,
            )
        if report.cost_basis is not None:
            self._append_spot_cost_basis(report, report.cost_basis, analytics)

    def _append_spot_balance(
        self,
        report: DualMarketAdvisoryReport,
        wallet: WalletSnapshot,
        balance: SpotBalance,
        analytics: PortfolioAnalytics | None,
    ) -> None:
        valued = (
            next(
                (
                    item
                    for item in analytics.valued_assets
                    if item.asset == balance.asset
                ),
                None,
            )
            if analytics is not None
            else None
        )
        total = balance.free + balance.locked
        payload = {
            "asset": balance.asset,
            "free_qty": balance.free,
            "locked_qty": balance.locked,
            "total_qty": total,
            "valuation_symbol": f"{balance.asset}USDT",
            "valuation_price": valued.price_usdt if valued is not None else None,
            "market_value_usdt": valued.value_usdt if valued is not None else None,
            "balance_status": (
                "DUST" if Decimal("0") < total < Decimal("1") else "ACTIVE"
            ),
        }
        self._append(
            "spot",
            "balance_snapshots.jsonl",
            "SPOT_BALANCE_SNAPSHOT_RECORDED",
            wallet.captured_at,
            f"{report.cycle_id}:{balance.asset}",
            {
                "envelope": self._envelope(
                    report,
                    ProductType.SPOT,
                    endpoint="/api/v3/account",
                    source_type=SourceType.REST,
                    payload=payload,
                    event_time=wallet.captured_at,
                    is_reconciled=True,
                ),
                **payload,
                "execution_allowed": False,
            },
        )

    def _append_spot_cost_basis(
        self,
        report: DualMarketAdvisoryReport,
        cost: CostBasisReport,
        analytics: PortfolioAnalytics | None,
    ) -> None:
        valued = (
            next(
                (
                    item
                    for item in analytics.valued_assets
                    if item.asset == cost.base_asset
                ),
                None,
            )
            if analytics is not None
            else None
        )
        payload = {
            "asset": cost.base_asset,
            "net_qty": cost.quantity,
            "cost_method": "WEIGHTED_AVERAGE",
            "average_unit_cost": cost.average_cost_quote,
            "market_price": valued.price_usdt if valued is not None else None,
            "market_value": valued.value_usdt if valued is not None else None,
            "unrealized_pnl": (
                valued.unrealized_pnl_usdt if valued is not None else None
            ),
            "realized_pnl": cost.realized_pnl_quote,
            "blockers": cost.blockers,
        }
        self._append(
            "spot",
            "cost_basis_positions.jsonl",
            "SPOT_COST_BASIS_POSITION_RECORDED",
            report.created_at,
            f"{report.cycle_id}:{cost.base_asset}",
            {
                "envelope": self._envelope(
                    report,
                    ProductType.SPOT,
                    endpoint="/api/v3/myTrades",
                    source_type=SourceType.DERIVED,
                    payload=payload,
                    is_reconciled=not cost.blockers,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _append_futures(
        self,
        report: DualMarketAdvisoryReport,
        account: FuturesAccountSnapshot,
    ) -> None:
        account_payload = {
            "can_trade": account.can_trade,
            "total_wallet_balance": account.total_wallet_balance,
            "available_balance": account.available_balance,
            "open_order_count": account.open_order_count,
        }
        self._append(
            "futures_usdm",
            "account_snapshots.jsonl",
            "FUTURES_USDM_ACCOUNT_SNAPSHOT_RECORDED",
            account.captured_at,
            report.cycle_id,
            {
                "envelope": self._envelope(
                    report,
                    ProductType.FUTURES_USDM,
                    endpoint="/fapi/v3/account",
                    source_type=SourceType.REST,
                    payload=account_payload,
                    event_time=account.captured_at,
                    is_reconciled=True,
                ),
                **account_payload,
                "execution_allowed": False,
            },
        )
        self._append(
            "futures_usdm",
            "asset_balances.jsonl",
            "FUTURES_USDM_ASSET_BALANCE_RECORDED",
            account.captured_at,
            f"{report.cycle_id}:USDT",
            {
                "envelope": self._envelope(
                    report,
                    ProductType.FUTURES_USDM,
                    endpoint="/fapi/v3/account",
                    source_type=SourceType.REST,
                    payload=account_payload,
                    event_time=account.captured_at,
                    is_reconciled=True,
                ),
                "asset": "USDT",
                "wallet_balance": account.total_wallet_balance,
                "available_balance": account.available_balance,
                "execution_allowed": False,
            },
        )
        for position in account.positions:
            if position.quantity != Decimal("0"):
                self._append_futures_position(report, account, position)
        for order in account.open_orders:
            self._append_order(
                "futures_usdm",
                "open_orders_current.jsonl",
                "FUTURES_USDM_OPEN_ORDER_RECORDED",
                report,
                order,
                ProductType.FUTURES_USDM,
            )
        self._append_futures_risk(report, account)

    def _append_futures_position(
        self,
        report: DualMarketAdvisoryReport,
        account: FuturesAccountSnapshot,
        position: FuturesPosition,
    ) -> None:
        side = "LONG" if position.quantity > Decimal("0") else "SHORT"
        self.append_futures_position(
            FuturesPositionRecord(
                symbol=position.symbol,
                position_side=side,
                position_amt=position.quantity,
                entry_price=position.entry_price,
                mark_price=position.mark_price or Decimal("0"),
                notional=position.notional or Decimal("0"),
                unrealized_pnl=position.unrealized_pnl,
                liquidation_price=position.liquidation_price,
                leverage=position.leverage or 1,
                margin_type=position.margin_type or "UNKNOWN",
                margin_asset="USDT",
                isolated_margin=position.isolated_margin or Decimal("0"),
                position_update_time=account.captured_at,
            ),
            snapshot_id=report.cycle_id,
            sync_run_id=report.cycle_id,
            received_at=report.created_at,
            is_reconciled=True,
        )

    def _append_futures_risk(
        self,
        report: DualMarketAdvisoryReport,
        account: FuturesAccountSnapshot,
    ) -> None:
        gross = sum(
            (
                abs(item.notional)
                for item in account.positions
                if item.notional is not None
            ),
            Decimal("0"),
        )
        pnl = sum((item.unrealized_pnl for item in account.positions), Decimal("0"))
        effective_leverage = (
            gross / account.total_wallet_balance
            if account.total_wallet_balance > Decimal("0")
            else None
        )
        payload = {
            "gross_exposure": gross,
            "net_exposure": sum(
                (
                    item.notional
                    for item in account.positions
                    if item.notional is not None
                ),
                Decimal("0"),
            ),
            "effective_leverage": effective_leverage,
            "portfolio_unrealized_pnl": pnl,
            "available_margin_pct": (
                account.available_balance / account.total_wallet_balance
                if account.total_wallet_balance > Decimal("0")
                else None
            ),
            "risk_status": "WARNING" if report.futures.blockers else "NORMAL",
            "blockers": report.futures.blockers,
        }
        self._append(
            "futures_usdm",
            "risk_snapshots.jsonl",
            "FUTURES_USDM_RISK_SNAPSHOT_RECORDED",
            account.captured_at,
            report.cycle_id,
            {
                "envelope": self._envelope(
                    report,
                    ProductType.FUTURES_USDM,
                    endpoint="runtime:futures_risk",
                    source_type=SourceType.DERIVED,
                    payload=payload,
                    event_time=account.captured_at,
                    is_reconciled=not report.futures.blockers,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _append_order(
        self,
        product_directory: str,
        filename: str,
        event_type: str,
        report: DualMarketAdvisoryReport,
        order: AccountOpenOrder,
        product_type: ProductType,
    ) -> None:
        expected_market = (
            "SPOT" if product_type is ProductType.SPOT else "USD_M_FUTURES"
        )
        if order.market != expected_market:
            raise ValueError("order product cannot be written to a mismatched ledger")
        payload = {
            "symbol": order.symbol,
            "order_id": order.order_id,
            "client_order_id": order.client_order_id,
            "side": order.side,
            "order_type": order.order_type,
            "price": order.price,
            "orig_qty": order.original_quantity,
            "executed_qty": order.executed_quantity,
            "remaining_qty": order.remaining_quantity,
            "status": order.status,
        }
        endpoint = (
            "/api/v3/openOrders"
            if product_type is ProductType.SPOT
            else "/fapi/v1/openOrders"
        )
        self._append(
            product_directory,
            filename,
            event_type,
            report.created_at,
            f"{report.cycle_id}:{order.market}:{order.symbol}:{order.order_id}",
            {
                "envelope": self._envelope(
                    report,
                    product_type,
                    endpoint=endpoint,
                    source_type=SourceType.REST,
                    payload=payload,
                    is_reconciled=True,
                ),
                **payload,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )

    def _envelope(
        self,
        report: DualMarketAdvisoryReport,
        product_type: ProductType,
        *,
        endpoint: str,
        source_type: SourceType,
        payload: object,
        event_time: datetime | None = None,
        is_reconciled: bool,
    ) -> RecordEnvelope:
        now = event_time or report.created_at
        payload_hash = _hash_payload(payload)
        return RecordEnvelope(
            account_id=self.account_id,
            environment=self.environment,
            product_type=product_type,
            snapshot_id=report.cycle_id,
            source_type=source_type,
            endpoint=endpoint,
            event_time=now,
            transaction_time=None,
            received_at=report.created_at,
            server_time=None,
            schema_version="1.0",
            raw_payload_hash=payload_hash,
            sync_run_id=report.cycle_id,
            is_reconciled=is_reconciled,
            created_at=report.created_at,
            updated_at=report.created_at,
        )

    def _standalone_envelope(
        self,
        product_type: ProductType,
        *,
        snapshot_id: str,
        sync_run_id: str,
        endpoint: str,
        source_type: SourceType,
        payload: object,
        event_time: datetime,
        transaction_time: datetime | None,
        received_at: datetime | None,
        server_time: datetime | None,
        is_reconciled: bool,
    ) -> RecordEnvelope:
        _require_text(snapshot_id)
        _require_text(sync_run_id)
        _require_aware(event_time)
        if received_at is not None:
            _require_aware(received_at)
        if server_time is not None:
            _require_aware(server_time)
        if transaction_time is not None:
            _require_aware(transaction_time)
        created_at = received_at or datetime.now(UTC)
        return RecordEnvelope(
            account_id=self.account_id,
            environment=self.environment,
            product_type=product_type,
            snapshot_id=snapshot_id,
            source_type=source_type,
            endpoint=endpoint,
            event_time=event_time,
            transaction_time=transaction_time,
            received_at=created_at,
            server_time=server_time,
            schema_version="1.0",
            raw_payload_hash=_hash_payload(payload),
            sync_run_id=sync_run_id,
            is_reconciled=is_reconciled,
            created_at=created_at,
            updated_at=created_at,
        )

    def _append(
        self,
        product_directory: str,
        filename: str,
        event_type: str,
        timestamp: datetime,
        snapshot_id: str,
        payload: dict[str, object],
    ) -> None:
        JsonlAuditStore(self.root / product_directory / filename).append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=timestamp,
                snapshot_id=snapshot_id,
                payload=payload,
            )
        )

    def _append_unique(
        self,
        product_directory: str,
        filename: str,
        event_type: str,
        timestamp: datetime,
        unique_key: str,
        payload: dict[str, object],
    ) -> bool:
        _require_text(unique_key)
        key_hash = sha256(unique_key.encode("utf-8")).hexdigest()
        data_path = self.root / product_directory / filename
        index_path = self.root / product_directory / ".indexes" / f"{filename}.keys"
        known = self._known_key_hashes(data_path, index_path)
        if key_hash in known:
            return False
        event_payload = {
            **payload,
            "unique_key": unique_key,
            "unique_key_hash": key_hash,
        }
        JsonlAuditStore(data_path, durable=True).append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=timestamp,
                snapshot_id=unique_key,
                payload=event_payload,
            )
        )
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(key_hash)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if key_hash not in self._index_key_hashes(index_path):
            raise fail_verification(
                "ACCOUNTING_INDEX_DESTINATION_VERIFY_FAILED",
                destination=index_path,
                subject_id=unique_key,
            )
        return True

    @staticmethod
    def _known_key_hashes(data_path: Path, index_path: Path) -> set[str]:
        keys = BinanceAccountLedger._index_key_hashes(index_path)
        if data_path.exists():
            for line in data_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                key_hash = payload.get("unique_key_hash")
                if isinstance(key_hash, str) and key_hash.strip():
                    keys.add(key_hash.strip())
        return keys

    @staticmethod
    def _index_key_hashes(index_path: Path) -> set[str]:
        keys: set[str] = set()
        if index_path.exists():
            for line in index_path.read_text(encoding="utf-8").splitlines():
                normalized = line.strip()
                if normalized:
                    keys.add(normalized)
        return keys

    def _spot_unique_key(self, symbol: str, order_id: str) -> str:
        return ":".join(("SPOT", self.account_id, symbol, order_id))

    def _futures_order_unique_key(self, symbol: str, order_id: str) -> str:
        return ":".join(("FUTURES_USDM", self.account_id, symbol, order_id))

    def _futures_position_unique_key(
        self,
        snapshot_id: str,
        symbol: str,
        position_side: str,
    ) -> str:
        return ":".join(
            ("FUTURES_USDM", self.account_id, snapshot_id, symbol, position_side)
        )

    @staticmethod
    def _record_count(report: DualMarketAdvisoryReport) -> int:
        spot_count = (
            1
            + sum(
                1
                for item in report.spot_wallet.balances
                if item.free + item.locked > Decimal("0")
            )
            + len(report.spot_wallet.open_orders)
            + (1 if report.cost_basis is not None else 0)
            if report.spot_wallet is not None
            else 0
        )
        futures_count = (
            2
            + len(report.futures_account.positions)
            + len(report.futures_account.open_orders)
            if report.futures_account is not None
            else 0
        )
        return 3 + spot_count + futures_count


def _hash_payload(payload: object) -> str:
    primitive = to_primitive(payload)
    encoded = json.dumps(
        primitive,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _require_symbol(value: str) -> None:
    _require_text(value)
    if not value.isascii() or not value.isalnum() or value.upper() != value:
        raise ValueError("Spot symbol must be uppercase ASCII alphanumeric")


def _require_position_side(value: str) -> None:
    _require_text(value)
    if value not in {"LONG", "SHORT", "BOTH"}:
        raise ValueError("Futures position_side is invalid")


def _require_text(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("accounting text fields cannot be blank")


def _require_decimal(
    value: Decimal,
    name: str,
    *,
    allow_negative: bool = False,
    positive: bool = False,
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if positive and value <= Decimal("0"):
        raise ValueError(f"{name} must be positive")
    if not allow_negative and value < Decimal("0"):
        raise ValueError(f"{name} must be non-negative")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("accounting timestamps must be timezone-aware")
