"""Event-driven long Spot backtest engine with conservative fill ordering."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import cast, overload

from ai4binance.backtest.liquidity import LiquidityFillDecision, assess_liquidity_fill
from ai4binance.backtest.metrics import calculate_metrics
from ai4binance.backtest.models import (
    BacktestConfig,
    BacktestExitReason,
    BacktestIntent,
    BacktestResult,
    ClosureReview,
    EquityPoint,
    FalseBreakoutRecord,
    RejectedSignal,
    StagedExitRecord,
    TradeRecord,
)
from ai4binance.execution.paper import ExitReason, PaperBroker, PaperPosition
from ai4binance.execution.trailing import update_long_trailing_stop
from ai4binance.schemas import OHLCVCandle

ONE = Decimal("1")


SignalProvider = Callable[[tuple[OHLCVCandle, ...]], BacktestIntent | None]


class _CandleHistory(Sequence[OHLCVCandle]):
    """Read-only prefix view that avoids copying the complete history each bar."""

    __slots__ = ("_candles", "_length")

    def __init__(self, candles: tuple[OHLCVCandle, ...], length: int) -> None:
        self._candles = candles
        self._length = length

    def __len__(self) -> int:
        return self._length

    @overload
    def __getitem__(self, index: int) -> OHLCVCandle: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[OHLCVCandle, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> OHLCVCandle | tuple[OHLCVCandle, ...]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self._length)
            return self._candles[start:stop:step]
        normalized = index + self._length if index < 0 else index
        if normalized < 0 or normalized >= self._length:
            raise IndexError("candle history index out of range")
        return self._candles[normalized]


@dataclass(slots=True)
class _OpenTrade:
    intent: BacktestIntent
    entry_timestamp: datetime
    entry_price: Decimal
    entry_fee: Decimal
    position: PaperPosition
    original_quantity: Decimal
    ignored_signals: int = 0
    staged_exits: list[StagedExitRecord] = field(default_factory=list)
    realized_partial_pnl: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class BacktestEngine:
    """Run deterministic next-bar-open entries and stop-first exits."""

    config: BacktestConfig = field(default_factory=BacktestConfig)

    def run(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        signal_provider: SignalProvider,
    ) -> BacktestResult:
        self._validate_inputs(symbol, timeframe, candles)
        broker = PaperBroker(
            fee_ratio=self.config.fee_ratio,
            slippage_ratio=self.config.slippage_ratio,
        )
        trades: list[TradeRecord] = []
        rejected: list[RejectedSignal] = []
        audit: list[dict[str, object]] = []
        equity_curve: list[EquityPoint] = []
        false_breakouts: list[FalseBreakoutRecord] = []
        pending: BacktestIntent | None = None
        open_trade: _OpenTrade | None = None
        no_trade_count = 0
        available_cash = self.config.initial_cash_usdt

        for index, candle in enumerate(candles):
            if pending is not None and open_trade is None:
                entry_blockers = self._entry_blockers(
                    pending,
                    candle,
                    available_cash,
                )
                if entry_blockers:
                    rejected.append(
                        RejectedSignal(
                            pending.signal_id,
                            pending.timestamp,
                            entry_blockers,
                        )
                    )
                    audit.append(
                        self._event("ENTRY_REJECTED", pending.signal_id, candle)
                    )
                else:
                    open_trade = self._open_trade(pending, candle)
                    event_type = (
                        "ENTRY_PARTIALLY_FILLED"
                        if open_trade.original_quantity < self.config.quantity
                        else "ENTRY_FILLED"
                    )
                    audit.append(self._event(event_type, pending.signal_id, candle))
                pending = None

            if open_trade is not None:
                exit_event = broker.evaluate_long_exit(open_trade.position, candle)
                if exit_event is not None:
                    if (
                        exit_event.reason is ExitReason.TAKE_PROFIT_EXIT
                        and len(open_trade.position.take_profit_levels) > 1
                    ):
                        staged = self._partial_exit(
                            open_trade,
                            candle,
                            exit_event.price,
                        )
                        available_cash += staged.realized_pnl_usdt
                        audit.append(
                            self._event(
                                "PARTIAL_TAKE_PROFIT",
                                open_trade.intent.signal_id,
                                candle,
                            )
                        )
                        exit_event = None
                if exit_event is not None:
                    trade = self._close_trade(
                        open_trade,
                        candle,
                        exit_event.reason,
                        exit_event.price,
                    )
                    trades.append(trade)
                    available_cash += (
                        trade.net_pnl_usdt - open_trade.realized_partial_pnl
                    )
                    false_breakout = self._false_breakout(open_trade, trade)
                    if false_breakout is not None:
                        false_breakouts.append(false_breakout)
                    audit.append(
                        self._event(exit_event.reason.value, trade.trade_id, candle)
                    )
                    open_trade = None
                if open_trade is not None:
                    open_trade.position = replace(
                        open_trade.position,
                        trailing_stop=update_long_trailing_stop(
                            open_trade.position.trailing_stop,
                            candle.close,
                            open_trade.intent.atr,
                            multiplier=self.config.trailing_multiplier,
                            tick_size=self.config.tick_size,
                        ).new_stop,
                    )

            equity_curve.append(self._equity_point(candle, available_cash, open_trade))

            history = cast(
                tuple[OHLCVCandle, ...],
                _CandleHistory(candles, index + 1),
            )
            intent = signal_provider(history)
            if intent is None:
                no_trade_count += 1
                continue
            blockers = self._intent_blockers(intent, candle, open_trade, pending)
            if blockers:
                rejected.append(
                    RejectedSignal(intent.signal_id, intent.timestamp, blockers)
                )
                if open_trade is not None:
                    open_trade.ignored_signals += 1
                continue
            pending = intent

        if pending is not None:
            rejected.append(
                RejectedSignal(pending.signal_id, pending.timestamp, ("NO_NEXT_BAR",))
            )
        if open_trade is not None:
            last = candles[-1]
            end_trade = self._close_trade(
                open_trade,
                last,
                BacktestExitReason.END_OF_DATA_EXIT,
                last.close * (ONE - self.config.slippage_ratio),
            )
            trades.append(end_trade)
            available_cash += end_trade.net_pnl_usdt - open_trade.realized_partial_pnl
            audit.append(self._event("END_OF_DATA_EXIT", end_trade.trade_id, last))

        benchmark = self._buy_and_hold_return(candles)
        metrics = calculate_metrics(
            tuple(trades),
            float(self.config.initial_cash_usdt),
            benchmark,
            tuple(float(point.equity_usdt) for point in equity_curve),
        )
        return BacktestResult(
            symbol=symbol.strip().upper(),
            timeframe=timeframe,
            started_at=candles[0].timestamp,
            ended_at=candles[-1].timestamp,
            assumptions=self.config,
            trades=tuple(trades),
            rejected_signals=tuple(rejected),
            no_trade_count=no_trade_count,
            metrics=metrics,
            audit_events=tuple(audit),
            equity_curve=tuple(equity_curve),
            false_breakouts=tuple(false_breakouts),
        )

    def _open_trade(self, intent: BacktestIntent, candle: OHLCVCandle) -> _OpenTrade:
        fill = self._entry_fill(candle)
        entry = candle.open * (
            ONE + self.config.slippage_ratio + fill.price_impact_ratio
        )
        fee = entry * fill.filled_quantity * self.config.fee_ratio
        return _OpenTrade(
            intent=intent,
            entry_timestamp=candle.timestamp,
            entry_price=entry,
            entry_fee=fee,
            position=PaperPosition(
                candidate_id=intent.signal_id,
                symbol="BACKTEST",
                entry_price=entry,
                quantity=fill.filled_quantity,
                stop_loss=intent.stop_loss,
                trailing_stop=intent.stop_loss,
                take_profit_levels=intent.targets,
            ),
            original_quantity=fill.filled_quantity,
        )

    def _entry_blockers(
        self,
        intent: BacktestIntent,
        candle: OHLCVCandle,
        available_cash: Decimal,
    ) -> tuple[str, ...]:
        fill = self._entry_fill(candle)
        entry = candle.open * (
            ONE + self.config.slippage_ratio + fill.price_impact_ratio
        )
        required_cash = entry * fill.filled_quantity * (ONE + self.config.fee_ratio)
        blockers: list[str] = []
        blockers.extend(fill.blockers)
        invalid_geometry = intent.stop_loss >= entry or any(
            target <= entry for target in intent.targets
        )
        if invalid_geometry:
            blockers.append("INVALID_NEXT_BAR_GEOMETRY")
        if required_cash > available_cash:
            blockers.append("INSUFFICIENT_BACKTEST_CASH")
        return tuple(blockers)

    def _close_trade(
        self,
        open_trade: _OpenTrade,
        candle: OHLCVCandle,
        reason: ExitReason | BacktestExitReason,
        raw_exit_price: Decimal,
    ) -> TradeRecord:
        exit_reason = BacktestExitReason(reason.value)
        exit_price = raw_exit_price
        if exit_reason is not BacktestExitReason.END_OF_DATA_EXIT:
            exit_price *= ONE - self.config.slippage_ratio
        remaining_quantity = open_trade.position.quantity
        exit_fee = exit_price * remaining_quantity * self.config.fee_ratio
        entry_cost = (
            open_trade.entry_price * remaining_quantity
            + open_trade.entry_fee * (remaining_quantity / open_trade.original_quantity)
        )
        exit_value = exit_price * remaining_quantity - exit_fee
        remaining_pnl = exit_value - entry_cost
        net_pnl = open_trade.realized_partial_pnl + remaining_pnl
        full_entry_cost = (
            open_trade.entry_price * open_trade.original_quantity + open_trade.entry_fee
        )
        return_ratio = net_pnl / full_entry_cost
        review = self._closure_review(exit_reason, open_trade.ignored_signals)
        return TradeRecord(
            trade_id=f"trade:{open_trade.intent.signal_id}",
            signal_id=open_trade.intent.signal_id,
            entry_timestamp=open_trade.entry_timestamp,
            exit_timestamp=candle.timestamp,
            entry_price=open_trade.entry_price,
            exit_price=exit_price,
            quantity=open_trade.original_quantity,
            entry_fee_usdt=open_trade.entry_fee,
            exit_fee_usdt=exit_fee
            + sum(stage.fee_usdt for stage in open_trade.staged_exits),
            net_pnl_usdt=net_pnl,
            return_ratio=return_ratio,
            exit_reason=exit_reason,
            closure_review=review,
            staged_exits=tuple(open_trade.staged_exits),
        )

    def _partial_exit(
        self,
        open_trade: _OpenTrade,
        candle: OHLCVCandle,
        raw_exit_price: Decimal,
    ) -> StagedExitRecord:
        quantity = open_trade.position.quantity * open_trade.intent.partial_exit_ratio
        exit_price = raw_exit_price * (ONE - self.config.slippage_ratio)
        fee = exit_price * quantity * self.config.fee_ratio
        entry_fee = open_trade.entry_fee * (quantity / open_trade.original_quantity)
        pnl = (
            exit_price * quantity
            - fee
            - (open_trade.entry_price * quantity + entry_fee)
        )
        staged = StagedExitRecord(candle.timestamp, exit_price, quantity, fee, pnl)
        open_trade.staged_exits.append(staged)
        open_trade.realized_partial_pnl += pnl
        open_trade.position = replace(
            open_trade.position,
            quantity=open_trade.position.quantity - quantity,
            take_profit_levels=open_trade.position.take_profit_levels[1:],
        )
        return staged

    def _equity_point(
        self,
        candle: OHLCVCandle,
        available_cash: Decimal,
        open_trade: _OpenTrade | None,
    ) -> EquityPoint:
        if open_trade is None:
            return EquityPoint(candle.timestamp, available_cash, Decimal("0"))
        quantity = open_trade.position.quantity
        estimated_exit = candle.close * quantity * (ONE - self.config.fee_ratio)
        remaining_cost = open_trade.entry_price * quantity + open_trade.entry_fee * (
            quantity / open_trade.original_quantity
        )
        unrealized = estimated_exit - remaining_cost
        return EquityPoint(candle.timestamp, available_cash + unrealized, quantity)

    def _entry_fill(self, candle: OHLCVCandle) -> LiquidityFillDecision:
        if self.config.liquidity_stress is None:
            return LiquidityFillDecision(
                requested_quantity=self.config.quantity,
                filled_quantity=self.config.quantity,
                remaining_quantity=Decimal("0"),
                fill_ratio=ONE,
                price_impact_ratio=Decimal("0"),
                blockers=(),
            )
        return assess_liquidity_fill(
            requested_quantity=self.config.quantity,
            candle_volume=candle.volume,
            config=self.config.liquidity_stress,
        )

    @staticmethod
    def _false_breakout(
        open_trade: _OpenTrade,
        trade: TradeRecord,
    ) -> FalseBreakoutRecord | None:
        breakout_tagged = any(
            "BREAKOUT" in reason for reason in open_trade.intent.reason_codes
        )
        stopped = trade.exit_reason in {
            BacktestExitReason.STOP_LOSS_EXIT,
            BacktestExitReason.TRAILING_STOP_EXIT,
        }
        if not breakout_tagged or not stopped:
            return None
        return FalseBreakoutRecord(
            trade.signal_id,
            trade.entry_timestamp,
            trade.exit_timestamp,
            trade.net_pnl_usdt,
        )

    @staticmethod
    def _intent_blockers(
        intent: BacktestIntent,
        candle: OHLCVCandle,
        open_trade: _OpenTrade | None,
        pending: BacktestIntent | None,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if intent.timestamp != candle.timestamp:
            blockers.append("SIGNAL_TIMESTAMP_MISMATCH")
        if open_trade is not None:
            blockers.append("POSITION_ALREADY_OPEN")
        if pending is not None:
            blockers.append("ENTRY_ALREADY_PENDING")
        return tuple(blockers)

    @staticmethod
    def _closure_review(
        reason: BacktestExitReason,
        ignored_signals: int,
    ) -> ClosureReview:
        trailing_exit = reason is BacktestExitReason.TRAILING_STOP_EXIT
        return ClosureReview(
            exit_reason=reason,
            lifecycle_error=None,
            stop_quality="PROTECTIVE" if "STOP" in reason.value else "NOT_TRIGGERED",
            trailing_quality="TRIGGERED" if trailing_exit else "NOT_TRIGGERED",
            ignored_signals=ignored_signals,
            htf_weakness=False,
            volatility_expansion=False,
            level_break=False,
            staged_exit_alternative="REVIEW_REQUIRED",
            lesson_candidate="REVIEW_EXIT_CONTEXT",
        )

    def _buy_and_hold_return(self, candles: tuple[OHLCVCandle, ...]) -> float:
        entry = candles[0].open * (ONE + self.config.slippage_ratio)
        exit_price = candles[-1].close * (ONE - self.config.slippage_ratio)
        entry_cost = entry * (ONE + self.config.fee_ratio)
        exit_value = exit_price * (ONE - self.config.fee_ratio)
        return float((exit_value - entry_cost) / entry_cost)

    @staticmethod
    def _event(
        event_type: str,
        identifier: str,
        candle: OHLCVCandle,
    ) -> dict[str, object]:
        return {
            "event_type": event_type,
            "identifier": identifier,
            "timestamp": candle.timestamp,
        }

    @staticmethod
    def _validate_inputs(
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
    ) -> None:
        if not symbol.strip() or not timeframe.strip():
            raise ValueError("symbol and timeframe are required")
        if len(candles) < 2:
            raise ValueError("at least two closed candles are required")
        timestamps = [candle.timestamp for candle in candles]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            raise ValueError("candles must be unique and strictly chronological")
