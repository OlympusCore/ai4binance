"""Spot order preview creation before any live write is attempted."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ai4binance.exchange.client import PublicMarketDataClient
from ai4binance.exchange.errors import ExchangeError
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.execution.live_spot import SpotOrderCommand

ZERO = Decimal("0")
DEFAULT_SPREAD_CAP_BPS = Decimal("50")


@dataclass(frozen=True, slots=True)
class SpotOrderPreview:
    """Hashable Spot order preview with filter evidence and no authority."""

    command: SpotOrderCommand
    validation_price: Decimal
    latest_spot_price: Decimal
    bid: Decimal
    ask: Decimal
    spread_bps: Decimal
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    exchange_info_valid: bool
    price_filter_valid: bool
    lot_size_valid: bool
    notional_filter_valid: bool
    tick_size_valid: bool
    step_size_valid: bool
    latest_spot_price_confirmed: bool
    spread_acceptable: bool
    slippage_acceptable: bool
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def preview_hash(self) -> str:
        return self.command.preview_hash

    @property
    def status(self) -> str:
        return "READY" if not self.blockers else "BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("order preview cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class SpotOrderPreviewBuilder:
    """Create preview evidence from public market data and Spot filters."""

    public_client: PublicMarketDataClient
    spread_cap_bps: Decimal = DEFAULT_SPREAD_CAP_BPS

    def __post_init__(self) -> None:
        if self.spread_cap_bps <= ZERO:
            raise ValueError("spread cap must be positive")

    def build(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        client_order_id: str,
        price: Decimal | None = None,
        time_in_force: str | None = None,
    ) -> SpotOrderPreview:
        normalized_type = order_type.strip().upper()
        blockers: list[str] = []
        warnings: list[str] = []
        try:
            filters = SymbolFilters.from_symbol_info(
                self.public_client.exchange_info(symbol)
            )
            latest = self.public_client.ticker_price(symbol)
            book = self.public_client.book_ticker(symbol)
        except (ValueError, ExchangeError, RuntimeError):
            raise ValueError("public Spot preview evidence is unavailable") from None
        if (
            latest <= ZERO
            or book.bid <= ZERO
            or book.ask <= ZERO
            or book.ask < book.bid
        ):
            blockers.append("PUBLIC_PRICE_EVIDENCE_INVALID")
        spread_bps = (
            ((book.ask - book.bid) / latest) * Decimal("10000")
            if latest > ZERO
            else Decimal("Infinity")
        )
        validation_price = latest if normalized_type == "MARKET" else price
        if validation_price is None:
            raise ValueError("LIMIT preview requires price")
        rounded_price = filters.price.round_down(validation_price)
        rounded_quantity = filters.lot_size.round_down(quantity)
        if rounded_price != validation_price:
            warnings.append("PRICE_ROUNDED_DOWN_TO_TICK_SIZE")
        if rounded_quantity != quantity:
            warnings.append("QUANTITY_ROUNDED_DOWN_TO_STEP_SIZE")
        command_price = rounded_price if normalized_type == "LIMIT" else None
        command = SpotOrderCommand(
            symbol,
            side,
            normalized_type,
            rounded_quantity,
            client_order_id,
            command_price,
            time_in_force,
        )
        filter_blockers = filters.validate_order(rounded_price, rounded_quantity)
        blockers.extend(filter_blockers)
        if spread_bps > self.spread_cap_bps:
            blockers.append("SPREAD_EXCEEDS_LIVE_CAP")
        valid = not filter_blockers and "PUBLIC_PRICE_EVIDENCE_INVALID" not in blockers
        spread_ok = spread_bps <= self.spread_cap_bps
        return SpotOrderPreview(
            command=command,
            validation_price=rounded_price,
            latest_spot_price=latest,
            bid=book.bid,
            ask=book.ask,
            spread_bps=spread_bps,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            exchange_info_valid=True,
            price_filter_valid=valid,
            lot_size_valid=valid,
            notional_filter_valid=valid,
            tick_size_valid=valid,
            step_size_valid=valid,
            latest_spot_price_confirmed=latest > ZERO,
            spread_acceptable=spread_ok,
            slippage_acceptable=spread_ok,
        )
