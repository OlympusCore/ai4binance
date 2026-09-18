"""Portfolio and fill helpers for bounded virtual runtime evaluation."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from importlib import import_module
from typing import Protocol, cast

from ai4binance.domain import Action

ZERO = Decimal("0")
ONE = Decimal("1")

_backtest_liquidity = import_module("ai4binance.research.backtesting.liquidity")
assess_liquidity_fill = _backtest_liquidity.assess_liquidity_fill


class _VirtualPortfolioLike(Protocol):
    @property
    def market(self) -> str: ...

    @property
    def open_position_count(self) -> int: ...

    @property
    def max_concurrent_positions(self) -> int: ...

    @property
    def cash_usdt(self) -> Decimal: ...

    @property
    def inventory_quantity(self) -> Decimal: ...


class _VirtualRuntimeRequestLike(Protocol):
    @property
    def quantity(self) -> Decimal: ...

    @property
    def step_size(self) -> Decimal: ...

    @property
    def entry_price(self) -> Decimal: ...

    @property
    def candle_volume(self) -> Decimal | None: ...

    @property
    def liquidity_stress(self) -> object: ...

    @property
    def slippage_ratio(self) -> Decimal: ...

    @property
    def half_spread_ratio(self) -> Decimal: ...

    @property
    def action(self) -> Action: ...

    @property
    def tick_size(self) -> Decimal: ...

    @property
    def minimum_notional(self) -> Decimal: ...

    @property
    def fee_ratio(self) -> Decimal: ...

    @property
    def market(self) -> str: ...

    @property
    def portfolio(self) -> _VirtualPortfolioLike: ...


class _VirtualFillPreviewLike(Protocol):
    @property
    def gross_notional_usdt(self) -> Decimal: ...

    @property
    def fee_usdt(self) -> Decimal: ...


class _VirtualMarketRuntimeLike(Protocol):
    @staticmethod
    def _round_quantity(quantity: Decimal, *, step_size: Decimal) -> Decimal: ...

    @staticmethod
    def _round_price(
        price: Decimal,
        *,
        tick_size: Decimal,
        action: Action,
    ) -> Decimal: ...

    @staticmethod
    def _futures_blockers(
        request: _VirtualRuntimeRequestLike,
        fill_preview: _VirtualFillPreviewLike,
    ) -> tuple[str, ...]: ...


def build_virtual_fill_preview(request: _VirtualRuntimeRequestLike) -> object:
    """Build a virtual fill preview without coupling callers to implementation."""

    research_virtual_runtime = import_module("ai4binance.research.virtual_runtime")
    virtual_market_runtime = cast(
        type[_VirtualMarketRuntimeLike],
        research_virtual_runtime.VirtualMarketRuntime,
    )
    virtual_fill_preview = cast(
        Callable[..., object], research_virtual_runtime.VirtualFillPreview
    )

    rounded_requested_quantity = virtual_market_runtime._round_quantity(
        request.quantity,
        step_size=request.step_size,
    )
    if rounded_requested_quantity <= ZERO:
        return virtual_fill_preview(
            requested_quantity=request.quantity,
            filled_quantity=ZERO,
            remaining_quantity=request.quantity,
            fill_ratio=ZERO,
            execution_price=request.entry_price,
            gross_notional_usdt=ZERO,
            fee_usdt=ZERO,
            slippage_cost_usdt=ZERO,
            price_impact_ratio=ZERO,
            blockers=("STEP_SIZE_ROUNDED_TO_ZERO",),
        )
    filled_quantity = rounded_requested_quantity
    price_impact_ratio = ZERO
    blockers: list[str] = []
    reason_codes: list[str] = []
    if request.candle_volume is not None:
        liquidity = assess_liquidity_fill(
            requested_quantity=rounded_requested_quantity,
            candle_volume=request.candle_volume,
            config=request.liquidity_stress,
        )
        blockers.extend(liquidity.blockers)
        filled_quantity = virtual_market_runtime._round_quantity(
            liquidity.filled_quantity,
            step_size=request.step_size,
        )
        price_impact_ratio = liquidity.price_impact_ratio
        if (
            filled_quantity > ZERO
            and filled_quantity < rounded_requested_quantity
            and not liquidity.blockers
        ):
            reason_codes.append("ENTRY_PARTIALLY_FILLED")
    if filled_quantity <= ZERO:
        blockers.append("LIQUIDITY_FILL_UNAVAILABLE")
        return virtual_fill_preview(
            requested_quantity=request.quantity,
            filled_quantity=ZERO,
            remaining_quantity=request.quantity,
            fill_ratio=ZERO,
            execution_price=request.entry_price,
            gross_notional_usdt=ZERO,
            fee_usdt=ZERO,
            slippage_cost_usdt=ZERO,
            price_impact_ratio=price_impact_ratio,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            blockers=tuple(dict.fromkeys(blockers)),
        )
    total_price_adjustment = (
        request.slippage_ratio + request.half_spread_ratio + price_impact_ratio
    )
    execution_price = request.entry_price * (
        ONE + total_price_adjustment
        if request.action is Action.BUY
        else ONE - total_price_adjustment
    )
    execution_price = virtual_market_runtime._round_price(
        execution_price,
        tick_size=request.tick_size,
        action=request.action,
    )
    gross_notional = execution_price * filled_quantity
    if gross_notional < request.minimum_notional:
        blockers.append("MIN_NOTIONAL_NOT_REACHED")
    return virtual_fill_preview(
        requested_quantity=request.quantity,
        filled_quantity=filled_quantity,
        remaining_quantity=request.quantity - filled_quantity,
        fill_ratio=filled_quantity / request.quantity,
        execution_price=execution_price,
        gross_notional_usdt=gross_notional,
        fee_usdt=gross_notional * request.fee_ratio,
        slippage_cost_usdt=abs(execution_price - request.entry_price) * filled_quantity,
        price_impact_ratio=price_impact_ratio,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def build_virtual_portfolio_blockers(
    request: _VirtualRuntimeRequestLike,
    fill_preview: _VirtualFillPreviewLike,
) -> tuple[str, ...]:
    """Build deterministic portfolio blockers for one virtual runtime request."""

    research_virtual_runtime = import_module("ai4binance.research.virtual_runtime")
    virtual_market_runtime = research_virtual_runtime.VirtualMarketRuntime

    blockers: list[str] = []
    if request.market.strip().upper() != request.portfolio.market:
        blockers.append("PORTFOLIO_MARKET_MISMATCH")
    if (
        request.action is Action.BUY
        and request.portfolio.market == "SPOT"
        and request.portfolio.open_position_count
        >= request.portfolio.max_concurrent_positions
    ):
        blockers.append("PORTFOLIO_CAPACITY_EXCEEDED")
    elif (
        request.portfolio.open_position_count
        >= request.portfolio.max_concurrent_positions
        and request.portfolio.market != "SPOT"
    ):
        blockers.append("PORTFOLIO_CAPACITY_EXCEEDED")
    if request.portfolio.market == "SPOT":
        if request.action is Action.BUY:
            if (
                request.portfolio.cash_usdt
                < fill_preview.gross_notional_usdt + fill_preview.fee_usdt
            ):
                blockers.append("INSUFFICIENT_VIRTUAL_CASH")
        elif request.action is Action.SELL:
            if request.portfolio.inventory_quantity < request.quantity:
                blockers.append("SPOT_INVENTORY_INSUFFICIENT")
    elif request.portfolio.market == "USD_M_FUTURES":
        blockers.extend(virtual_market_runtime._futures_blockers(request, fill_preview))
    return tuple(dict.fromkeys(blockers))
