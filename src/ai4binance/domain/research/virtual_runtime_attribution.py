"""Canonical deterministic virtual-trade attribution contracts and aggregation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")


class BacktestExitReason(StrEnum):
    """Exit reasons not owned by the paper execution primitive."""

    LIQUIDATION = "LIQUIDATION"
    HARD_STOP = "HARD_STOP"
    TARGET = "TARGET"
    TRAILING_STOP = "TRAILING_STOP"
    STRUCTURE_INVALIDATION = "STRUCTURE_INVALIDATION"
    TIME_EXIT = "TIME_EXIT"
    REGIME_EXIT = "REGIME_EXIT"
    MOMENTUM_FAILURE = "MOMENTUM_FAILURE"
    END_OF_DATA = "END_OF_DATA"


class TradeDirection(StrEnum):
    """Deterministic virtual-trade direction labels."""

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class ClosedTradeAttribution:
    """Required deterministic lineage attached to each closed virtual trade."""

    strategy_id: str = "UNSPECIFIED_STRATEGY"
    strategy_version: str = "1"
    strategy_config_version: str = "1"
    strategy_config_hash: str = "default"
    market: str = "SPOT"
    symbol: str = "UNKNOWN_SYMBOL"
    regime: str = "UNKNOWN"
    timeframe: str = "UNKNOWN"
    snapshot_id: str = "UNKNOWN_SNAPSHOT"
    decision_id: str = "UNKNOWN_DECISION"
    opportunity_id: str = "UNKNOWN_OPPORTUNITY"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("strategy_id", self.strategy_id),
            ("strategy_version", self.strategy_version),
            ("strategy_config_version", self.strategy_config_version),
            ("strategy_config_hash", self.strategy_config_hash),
            ("market", self.market),
            ("symbol", self.symbol),
            ("regime", self.regime),
            ("timeframe", self.timeframe),
            ("snapshot_id", self.snapshot_id),
            ("decision_id", self.decision_id),
            ("opportunity_id", self.opportunity_id),
        ):
            if not value.strip():
                raise ValueError(f"closed trade attribution {field_name} is required")


@dataclass(frozen=True, slots=True)
class TradeEdgeAggregateView:
    """Deterministic closed-trade edge summary for one grouping key."""

    trade_count: int
    gross_pnl_usdt: Decimal
    fee_cost_usdt: Decimal
    slippage_cost_usdt: Decimal
    funding_cost_usdt: Decimal
    net_pnl_usdt: Decimal
    average_realized_r_multiple: Decimal
    average_maximum_favorable_excursion: Decimal
    average_maximum_adverse_excursion: Decimal
    average_holding_period: Decimal
    strategy_id: str | None = None
    regime: str | None = None
    symbol: str | None = None
    timeframe: str | None = None

    def __post_init__(self) -> None:
        if self.trade_count < 1:
            raise ValueError("trade edge aggregate requires at least one trade")


@dataclass(frozen=True, slots=True)
class TradeEdgeLedger:
    """Aggregate trade-edge views derived from completed virtual trades."""

    by_strategy: tuple[TradeEdgeAggregateView, ...] = ()
    by_regime: tuple[TradeEdgeAggregateView, ...] = ()
    by_strategy_regime: tuple[TradeEdgeAggregateView, ...] = ()
    by_symbol: tuple[TradeEdgeAggregateView, ...] = ()
    by_timeframe: tuple[TradeEdgeAggregateView, ...] = ()


@dataclass(frozen=True, slots=True)
class VirtualClosedTradeRecord:
    """Canonical closed virtual trade with optimization-safe lineage."""

    trade_id: str
    attribution: ClosedTradeAttribution
    direction: TradeDirection
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    risk_at_entry: Decimal
    entry_reason: tuple[str, ...]
    exit_reason: BacktestExitReason
    dge_decision: str
    risk_policy_version: str
    validation_version: str
    gross_pnl_usdt: Decimal
    fee_cost_usdt: Decimal
    slippage_cost_usdt: Decimal
    funding_cost_usdt: Decimal
    net_pnl_usdt: Decimal
    realized_r_multiple: Decimal
    maximum_favorable_excursion: Decimal
    maximum_adverse_excursion: Decimal
    false_breakout: bool = False

    def __post_init__(self) -> None:
        if not self.trade_id.strip():
            raise ValueError("virtual closed trade identity is required")
        if any(not value.strip() for value in self.entry_reason):
            raise ValueError("virtual closed trade entry reason cannot contain blanks")
        if any(
            not value.strip()
            for value in (
                self.dge_decision,
                self.risk_policy_version,
                self.validation_version,
            )
        ):
            raise ValueError("virtual closed trade governance lineage is required")


@dataclass(frozen=True, slots=True)
class VirtualTradeAttributionAggregate:
    """Closed-trade attribution summary for one grouping key."""

    trade_count: int
    net_pnl_usdt: Decimal
    expectancy_usdt: Decimal
    average_realized_r_multiple: Decimal
    fee_drag_usdt: Decimal
    slippage_drag_usdt: Decimal
    funding_drag_usdt: Decimal
    average_mfe: Decimal
    average_mae: Decimal
    false_breakout_rate: Decimal
    drawdown_contribution_usdt: Decimal
    strategy_id: str | None = None
    regime: str | None = None

    def __post_init__(self) -> None:
        if self.trade_count < 1:
            raise ValueError("virtual trade attribution aggregate requires trades")


@dataclass(frozen=True, slots=True)
class VirtualTradeAttributionLedger:
    """Optimization-safe closed-trade attribution views."""

    closed_trades: tuple[VirtualClosedTradeRecord, ...] = ()
    trade_edge_ledger: TradeEdgeLedger = field(default_factory=TradeEdgeLedger)
    by_strategy: tuple[VirtualTradeAttributionAggregate, ...] = ()
    by_regime: tuple[VirtualTradeAttributionAggregate, ...] = ()
    by_strategy_regime: tuple[VirtualTradeAttributionAggregate, ...] = ()


def build_virtual_trade_attribution_ledger(
    closed_trades: tuple[VirtualClosedTradeRecord, ...],
) -> VirtualTradeAttributionLedger:
    """Aggregate closed trades with stable keys and canonical result objects."""

    return VirtualTradeAttributionLedger(
        closed_trades=closed_trades,
        trade_edge_ledger=TradeEdgeLedger(
            by_strategy=_trade_edge_views(
                closed_trades,
                key_fn=lambda trade: (trade.attribution.strategy_id,),
                view_fn=lambda trade: {"strategy_id": trade.attribution.strategy_id},
            ),
            by_regime=_trade_edge_views(
                closed_trades,
                key_fn=lambda trade: (trade.attribution.regime,),
                view_fn=lambda trade: {"regime": trade.attribution.regime},
            ),
            by_strategy_regime=_trade_edge_views(
                closed_trades,
                key_fn=lambda trade: (
                    trade.attribution.strategy_id,
                    trade.attribution.regime,
                ),
                view_fn=lambda trade: {
                    "strategy_id": trade.attribution.strategy_id,
                    "regime": trade.attribution.regime,
                },
            ),
        ),
        by_strategy=_attribution_views(
            closed_trades,
            key_fn=lambda trade: (trade.attribution.strategy_id,),
            view_fn=lambda trade: {"strategy_id": trade.attribution.strategy_id},
        ),
        by_regime=_attribution_views(
            closed_trades,
            key_fn=lambda trade: (trade.attribution.regime,),
            view_fn=lambda trade: {"regime": trade.attribution.regime},
        ),
        by_strategy_regime=_attribution_views(
            closed_trades,
            key_fn=lambda trade: (
                trade.attribution.strategy_id,
                trade.attribution.regime,
            ),
            view_fn=lambda trade: {
                "strategy_id": trade.attribution.strategy_id,
                "regime": trade.attribution.regime,
            },
        ),
    )


def _trade_edge_views(
    closed_trades: tuple[VirtualClosedTradeRecord, ...],
    *,
    key_fn: Callable[[VirtualClosedTradeRecord], tuple[str, ...]],
    view_fn: Callable[[VirtualClosedTradeRecord], dict[str, str]],
) -> tuple[TradeEdgeAggregateView, ...]:
    grouped: dict[tuple[str, ...], list[VirtualClosedTradeRecord]] = {}
    for trade in closed_trades:
        grouped.setdefault(key_fn(trade), []).append(trade)
    views: list[TradeEdgeAggregateView] = []
    for key in sorted(grouped):
        group = grouped[key]
        denominator = Decimal(len(group))
        first = group[0]
        views.append(
            TradeEdgeAggregateView(
                trade_count=len(group),
                gross_pnl_usdt=sum((trade.gross_pnl_usdt for trade in group), ZERO),
                fee_cost_usdt=sum((trade.fee_cost_usdt for trade in group), ZERO),
                slippage_cost_usdt=sum(
                    (trade.slippage_cost_usdt for trade in group), ZERO
                ),
                funding_cost_usdt=sum(
                    (trade.funding_cost_usdt for trade in group), ZERO
                ),
                net_pnl_usdt=sum((trade.net_pnl_usdt for trade in group), ZERO),
                average_realized_r_multiple=sum(
                    (trade.realized_r_multiple for trade in group), ZERO
                )
                / denominator,
                average_maximum_favorable_excursion=sum(
                    (trade.maximum_favorable_excursion for trade in group), ZERO
                )
                / denominator,
                average_maximum_adverse_excursion=sum(
                    (trade.maximum_adverse_excursion for trade in group), ZERO
                )
                / denominator,
                average_holding_period=sum(
                    (
                        Decimal(
                            int((trade.exit_time - trade.entry_time).total_seconds())
                        )
                        for trade in group
                    ),
                    ZERO,
                )
                / denominator,
                symbol=first.attribution.symbol,
                timeframe=first.attribution.timeframe,
                **view_fn(first),
            )
        )
    return tuple(views)


def _attribution_views(
    closed_trades: tuple[VirtualClosedTradeRecord, ...],
    *,
    key_fn: Callable[[VirtualClosedTradeRecord], tuple[str, ...]],
    view_fn: Callable[[VirtualClosedTradeRecord], dict[str, str]],
) -> tuple[VirtualTradeAttributionAggregate, ...]:
    grouped: dict[tuple[str, ...], list[VirtualClosedTradeRecord]] = {}
    for trade in closed_trades:
        grouped.setdefault(key_fn(trade), []).append(trade)
    views: list[VirtualTradeAttributionAggregate] = []
    for key in sorted(grouped):
        group = grouped[key]
        denominator = Decimal(len(group))
        gross_losses = abs(
            sum(
                (trade.net_pnl_usdt for trade in group if trade.net_pnl_usdt < ZERO),
                ZERO,
            )
        )
        drawdown_contribution = min(
            ZERO if gross_losses == ZERO else gross_losses,
            abs(sum((trade.net_pnl_usdt for trade in group), ZERO)),
        )
        views.append(
            VirtualTradeAttributionAggregate(
                trade_count=len(group),
                net_pnl_usdt=sum((trade.net_pnl_usdt for trade in group), ZERO),
                expectancy_usdt=sum((trade.net_pnl_usdt for trade in group), ZERO)
                / denominator,
                average_realized_r_multiple=sum(
                    (trade.realized_r_multiple for trade in group), ZERO
                )
                / denominator,
                fee_drag_usdt=sum((trade.fee_cost_usdt for trade in group), ZERO),
                slippage_drag_usdt=sum(
                    (trade.slippage_cost_usdt for trade in group), ZERO
                ),
                funding_drag_usdt=sum(
                    (trade.funding_cost_usdt for trade in group), ZERO
                ),
                average_mfe=sum(
                    (trade.maximum_favorable_excursion for trade in group), ZERO
                )
                / denominator,
                average_mae=sum(
                    (trade.maximum_adverse_excursion for trade in group), ZERO
                )
                / denominator,
                false_breakout_rate=Decimal(
                    str(sum(1 for trade in group if trade.false_breakout) / len(group))
                ),
                drawdown_contribution_usdt=drawdown_contribution,
                **view_fn(group[0]),
            )
        )
    return tuple(views)


__all__ = (
    "BacktestExitReason",
    "ClosedTradeAttribution",
    "TradeDirection",
    "TradeEdgeAggregateView",
    "TradeEdgeLedger",
    "VirtualClosedTradeRecord",
    "VirtualTradeAttributionAggregate",
    "VirtualTradeAttributionLedger",
    "build_virtual_trade_attribution_ledger",
)
