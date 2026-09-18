"""Event-driven long Spot backtest engine with conservative fill ordering."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import TYPE_CHECKING, cast, overload

from ai4binance.research.backtesting.exit_engine import VirtualExitEngine
from ai4binance.research.backtesting.liquidity import (
    LiquidityFillDecision,
    assess_liquidity_fill,
)
from ai4binance.research.backtesting.metrics import calculate_metrics
from ai4binance.research.backtesting.models import (
    BacktestConfig,
    BacktestExitReason,
    BacktestIntent,
    BacktestMetrics,
    BacktestResult,
    ClosureReview,
    EquityPoint,
    FalseBreakoutRecord,
    MissedOpportunityCategory,
    MissedOpportunityLedger,
    MissedOpportunityRecord,
    PerformanceEngineReport,
    PreVetoOpportunityLedger,
    PreVetoOpportunityRecord,
    RejectedSignal,
    StagedExitRecord,
    TradeDirection,
    TradeEdgeAggregateView,
    TradeEdgeLedger,
    TradeRecord,
    VirtualMarketFunnelStage,
    VirtualMarketFunnelTelemetry,
)
from ai4binance.schemas import OHLCVCandle

ONE = Decimal("1")
ZERO = Decimal("0")

if TYPE_CHECKING:
    from ai4binance.execution.paper import ExitReason, PaperPosition


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


class _CandleTail(Sequence[OHLCVCandle]):
    """Read-only suffix view used by counterfactual replay without tail copies."""

    __slots__ = ("_candles", "_start")

    def __init__(self, candles: tuple[OHLCVCandle, ...], start: int) -> None:
        self._candles = candles
        self._start = start

    def __len__(self) -> int:
        return len(self._candles) - self._start

    @overload
    def __getitem__(self, index: int) -> OHLCVCandle: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[OHLCVCandle, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> OHLCVCandle | tuple[OHLCVCandle, ...]:
        length = len(self)
        if isinstance(index, slice):
            positions = range(length)[index]
            return tuple(self._candles[self._start + offset] for offset in positions)
        normalized = index + length if index < 0 else index
        if normalized < 0 or normalized >= length:
            raise IndexError("candle tail index out of range")
        return self._candles[self._start + normalized]


@dataclass(slots=True)
class _OpenTrade:
    intent: BacktestIntent
    entry_timestamp: datetime
    entry_reference_price: Decimal
    entry_price: Decimal
    entry_fee: Decimal
    position: "PaperPosition"
    original_quantity: Decimal
    ignored_signals: int = 0
    staged_exits: list[StagedExitRecord] = field(default_factory=list)
    realized_partial_pnl: Decimal = Decimal("0")
    realized_exit_slippage_cost: Decimal = Decimal("0")
    maximum_favorable_excursion: Decimal = Decimal("0")
    maximum_adverse_excursion: Decimal = Decimal("0")
    bars_held: int = 0
    breakeven_armed: bool = False
    blocker_history: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _RejectedCandidate:
    intent: BacktestIntent
    blockers: tuple[str, ...]
    entry_index: int
    pre_veto_observation_id: str


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
        trades: list[TradeRecord] = []
        rejected: list[RejectedSignal] = []
        audit: list[dict[str, object]] = []
        equity_curve: list[EquityPoint] = []
        false_breakouts: list[FalseBreakoutRecord] = []
        rejected_candidates: list[_RejectedCandidate] = []
        pre_veto_observations: list[PreVetoOpportunityRecord] = []
        stage_counts = {stage.value: 0 for stage in VirtualMarketFunnelStage}
        reason_code_counts: dict[str, int] = {}
        pending: BacktestIntent | None = None
        pending_observation_id: str | None = None
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
                    self._record_reason_codes(reason_code_counts, entry_blockers)
                    rejected.append(
                        RejectedSignal(
                            pending.signal_id,
                            pending.timestamp,
                            entry_blockers,
                        )
                    )
                    rejected_candidates.append(
                        _RejectedCandidate(
                            pending,
                            entry_blockers,
                            index,
                            pending_observation_id
                            or self._pre_veto_observation_id(
                                pending,
                                index - 1,
                            ),
                        )
                    )
                    audit.append(
                        self._event("ENTRY_REJECTED", pending.signal_id, candle)
                    )
                else:
                    open_trade = self._open_trade(pending, candle)
                    stage_counts[VirtualMarketFunnelStage.FILLED.value] += 1
                    event_type = (
                        "ENTRY_PARTIALLY_FILLED"
                        if open_trade.original_quantity < self.config.quantity
                        else "ENTRY_FILLED"
                    )
                    audit.append(self._event(event_type, pending.signal_id, candle))
                pending = None
                pending_observation_id = None

            if open_trade is not None:
                self._update_excursions(open_trade, candle)
                open_trade.bars_held += 1
                exit_event = VirtualExitEngine.evaluate_long_exit(
                    intent=open_trade.intent,
                    position=open_trade.position,
                    candle=candle,
                    bars_held=open_trade.bars_held,
                )
                if exit_event is not None:
                    if (
                        exit_event.reason.value == BacktestExitReason.TARGET.value
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
                    stage_counts[VirtualMarketFunnelStage.CLOSED.value] += 1
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
                    if self._breakeven_trigger_reached(open_trade):
                        open_trade.breakeven_armed = True
                    open_trade.position = replace(
                        open_trade.position,
                        trailing_stop=self._updated_trailing_stop(
                            open_trade,
                            candle.close,
                        ),
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
            intent = self._normalize_intent(intent, symbol=symbol, timeframe=timeframe)
            observation = self._pre_veto_observation(intent, candle, index)
            pre_veto_observations.append(observation)
            audit.append(
                self._event(
                    "OPPORTUNITY_OBSERVED_PRE_VETO",
                    observation.observation_id,
                    candle,
                )
            )
            for stage in intent.funnel_stages:
                stage_counts[stage] += 1
            blockers = self._intent_blockers(intent, candle, open_trade, pending)
            if blockers:
                self._record_reason_codes(reason_code_counts, blockers)
                rejected.append(
                    RejectedSignal(intent.signal_id, intent.timestamp, blockers)
                )
                rejected_candidates.append(
                    _RejectedCandidate(
                        intent,
                        blockers,
                        index + 1,
                        observation.observation_id,
                    )
                )
                if open_trade is not None:
                    open_trade.ignored_signals += 1
                    open_trade.blocker_history.extend(blockers)
                continue
            stage_counts[VirtualMarketFunnelStage.VIRTUAL_ORDER.value] += 1
            pending = intent
            pending_observation_id = observation.observation_id

        if pending is not None:
            self._record_reason_codes(reason_code_counts, ("NO_NEXT_BAR",))
            rejected.append(
                RejectedSignal(pending.signal_id, pending.timestamp, ("NO_NEXT_BAR",))
            )
            rejected_candidates.append(
                _RejectedCandidate(
                    pending,
                    ("NO_NEXT_BAR",),
                    len(candles),
                    pending_observation_id
                    or self._pre_veto_observation_id(pending, len(candles) - 1),
                )
            )
        if open_trade is not None:
            last = candles[-1]
            end_exit = VirtualExitEngine.end_of_data_exit(last)
            end_trade = self._close_trade(
                open_trade,
                last,
                end_exit.reason,
                end_exit.price,
            )
            trades.append(end_trade)
            available_cash += end_trade.net_pnl_usdt - open_trade.realized_partial_pnl
            audit.append(self._event(end_exit.reason.value, end_trade.trade_id, last))

        benchmark = self._buy_and_hold_return(candles)
        missed_opportunity_ledger = self._missed_opportunity_ledger(
            tuple(rejected_candidates),
            candles,
        )
        market = self._result_market(tuple(trades), missed_opportunity_ledger)
        metrics = calculate_metrics(
            tuple(trades),
            float(self.config.initial_cash_usdt),
            benchmark,
            tuple(float(point.equity_usdt) for point in equity_curve),
            market=market,
            backtest_duration_seconds=int(
                (candles[-1].timestamp - candles[0].timestamp).total_seconds()
            ),
            missed_opportunity_ledger=missed_opportunity_ledger,
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
            funnel_telemetry=VirtualMarketFunnelTelemetry(
                stage_counts=tuple(
                    (stage.value, stage_counts[stage.value])
                    for stage in VirtualMarketFunnelStage
                ),
                reason_code_counts=tuple(sorted(reason_code_counts.items())),
            ),
            trade_edge_ledger=self._trade_edge_ledger(tuple(trades)),
            trade_outcomes=tuple(trade.trade_outcome for trade in trades),
            performance_engine_report=self._performance_engine_report(metrics),
            missed_opportunity_ledger=missed_opportunity_ledger,
            pre_veto_opportunity_ledger=PreVetoOpportunityLedger(
                records=tuple(pre_veto_observations)
            ),
        )

    @staticmethod
    def _pre_veto_observation_id(intent: BacktestIntent, index: int) -> str:
        return (
            f"pre-veto:{intent.market.lower()}:"
            f"{intent.snapshot_id or intent.signal_id}:"
            f"{index}:{intent.signal_id}"
        )

    @classmethod
    def _pre_veto_observation(
        cls,
        intent: BacktestIntent,
        candle: OHLCVCandle,
        index: int,
    ) -> PreVetoOpportunityRecord:
        return PreVetoOpportunityRecord(
            observation_id=cls._pre_veto_observation_id(intent, index),
            signal_id=intent.signal_id,
            snapshot_id=intent.snapshot_id or intent.signal_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            regime=intent.regime,
            symbol=intent.symbol.strip().upper() or "UNKNOWN_SYMBOL",
            market=intent.market,
            direction=TradeDirection.LONG,
            observed_at=intent.timestamp,
            reference_price=candle.close,
            stop_loss=intent.stop_loss,
            take_profit_levels=intent.targets,
            entry_reason=intent.reason_codes,
            dge_status=intent.dge_status,
        )

    def _open_trade(self, intent: BacktestIntent, candle: OHLCVCandle) -> _OpenTrade:
        from ai4binance.execution.paper import PaperPosition

        fill = self._entry_fill(candle)
        entry = self._round_price(
            candle.open * (ONE + self.config.slippage_ratio + fill.price_impact_ratio),
            rounding=ROUND_UP,
        )
        fee = entry * fill.filled_quantity * self.config.fee_ratio
        return _OpenTrade(
            intent=intent,
            entry_timestamp=candle.timestamp,
            entry_reference_price=candle.open,
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
        entry = self._round_price(
            candle.open * (ONE + self.config.slippage_ratio + fill.price_impact_ratio),
            rounding=ROUND_UP,
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
        if entry * fill.filled_quantity < self.config.minimum_notional:
            blockers.append("MIN_NOTIONAL_NOT_REACHED")
        return tuple(blockers)

    def _close_trade(
        self,
        open_trade: _OpenTrade,
        candle: OHLCVCandle,
        reason: "ExitReason | BacktestExitReason",
        reference_exit_price: Decimal,
    ) -> TradeRecord:
        exit_reason = BacktestExitReason(reason.value)
        exit_price = self._round_price(
            reference_exit_price * (ONE - self.config.slippage_ratio),
            rounding=ROUND_DOWN,
        )
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
        fee_cost = (
            open_trade.entry_fee
            + exit_fee
            + sum(stage.fee_usdt for stage in open_trade.staged_exits)
        )
        slippage_cost = self._entry_slippage_cost(open_trade) + (
            open_trade.realized_exit_slippage_cost
            + (reference_exit_price - exit_price) * remaining_quantity
        )
        funding_cost = self._funding_cost(open_trade.intent)
        gross_pnl = net_pnl + fee_cost + slippage_cost + funding_cost
        risk_at_entry = (
            open_trade.entry_price - open_trade.intent.stop_loss
        ) * open_trade.original_quantity
        planned_rr = ZERO
        if risk_at_entry > ZERO:
            planned_rr = (
                (open_trade.intent.take_profit - open_trade.entry_price)
                * open_trade.original_quantity
            ) / risk_at_entry
        realized_r_multiple = self._realized_r_multiple(open_trade, net_pnl)
        review = self._closure_review(exit_reason, open_trade.ignored_signals)
        blocker_history = tuple(
            dict.fromkeys(
                (*open_trade.intent.blocker_history, *open_trade.blocker_history)
            )
        )
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
            entry_reason=open_trade.intent.reason_codes,
            staged_exits=tuple(open_trade.staged_exits),
            attribution=open_trade.intent.closed_trade_attribution,
            gross_pnl_usdt=gross_pnl,
            fee_cost_usdt=fee_cost,
            slippage_cost_usdt=slippage_cost,
            funding_cost_usdt=funding_cost,
            realized_r_multiple=realized_r_multiple,
            maximum_favorable_excursion=open_trade.maximum_favorable_excursion,
            maximum_adverse_excursion=open_trade.maximum_adverse_excursion,
            holding_period=int(
                (candle.timestamp - open_trade.entry_timestamp).total_seconds()
            ),
            direction=TradeDirection.LONG,
            MAE=open_trade.maximum_adverse_excursion,
            MFE=open_trade.maximum_favorable_excursion,
            holding_time=int(
                (candle.timestamp - open_trade.entry_timestamp).total_seconds()
            ),
            gross_pnl=gross_pnl,
            fees=fee_cost,
            slippage=slippage_cost,
            net_pnl=net_pnl,
            risk_at_entry=risk_at_entry,
            planned_rr=planned_rr,
            entry_score=open_trade.intent.entry_score,
            evidence_score=open_trade.intent.evidence_score,
            dge_status=open_trade.intent.dge_status,
            blocker_history=blocker_history,
        )

    def _partial_exit(
        self,
        open_trade: _OpenTrade,
        candle: OHLCVCandle,
        raw_exit_price: Decimal,
    ) -> StagedExitRecord:
        quantity = open_trade.position.quantity * open_trade.intent.partial_exit_ratio
        exit_price = self._round_price(
            raw_exit_price * (ONE - self.config.slippage_ratio),
            rounding=ROUND_DOWN,
        )
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
        open_trade.realized_exit_slippage_cost += (
            raw_exit_price - exit_price
        ) * quantity
        open_trade.position = replace(
            open_trade.position,
            quantity=open_trade.position.quantity - quantity,
            take_profit_levels=open_trade.position.take_profit_levels[1:],
        )
        return staged

    def _simulate_counterfactual_trade(
        self,
        intent: BacktestIntent,
        candles: Sequence[OHLCVCandle],
    ) -> TradeRecord | None:
        if not candles or "FUTURES" in intent.market.upper():
            return None
        try:
            open_trade = self._open_trade(intent, candles[0])
        except ValueError:
            return None
        if len(intent.targets) == 1:
            return self._simulate_single_target_counterfactual(open_trade, candles)
        return self._simulate_counterfactual_trade_general(open_trade, candles)

    def _simulate_counterfactual_trade_general(
        self,
        open_trade: _OpenTrade,
        candles: Sequence[OHLCVCandle],
    ) -> TradeRecord:
        """Replay staged-target counterfactuals through the canonical engines."""

        for candle in candles:
            self._update_excursions(open_trade, candle)
            open_trade.bars_held += 1
            exit_event = VirtualExitEngine.evaluate_long_exit(
                intent=open_trade.intent,
                position=open_trade.position,
                candle=candle,
                bars_held=open_trade.bars_held,
            )
            if exit_event is not None:
                if (
                    exit_event.reason.value == BacktestExitReason.TARGET.value
                    and len(open_trade.position.take_profit_levels) > 1
                ):
                    self._partial_exit(open_trade, candle, exit_event.price)
                    exit_event = None
                else:
                    return self._close_trade(
                        open_trade,
                        candle,
                        exit_event.reason,
                        exit_event.price,
                    )
            if self._breakeven_trigger_reached(open_trade):
                open_trade.breakeven_armed = True
            open_trade.position = replace(
                open_trade.position,
                trailing_stop=self._updated_trailing_stop(open_trade, candle.close),
            )
        last = candles[-1]
        end_exit = VirtualExitEngine.end_of_data_exit(last)
        return self._close_trade(open_trade, last, end_exit.reason, end_exit.price)

    def _simulate_single_target_counterfactual(
        self,
        open_trade: _OpenTrade,
        candles: Sequence[OHLCVCandle],
    ) -> TradeRecord:
        """Replay the common one-target path without per-bar object replacement."""

        intent = open_trade.intent
        position = open_trade.position
        stop_loss = position.stop_loss
        target = position.take_profit_levels[0]
        trailing_stop = position.trailing_stop
        quantity = open_trade.original_quantity
        maximum_favorable = ZERO
        maximum_adverse = ZERO
        breakeven_armed = False
        initial_risk = (open_trade.entry_price - intent.stop_loss) * quantity
        trigger_threshold = (
            initial_risk * intent.breakeven_trigger_r
            if intent.breakeven_trigger_r is not None and initial_risk > ZERO
            else None
        )
        trailing_distance = (
            intent.trailing_atr_multiple or self.config.trailing_multiplier
        ) * intent.atr
        bars_held = 0

        for candle in candles:
            bars_held += 1
            maximum_favorable = max(
                maximum_favorable,
                max(candle.high - open_trade.entry_price, ZERO) * quantity,
            )
            maximum_adverse = max(
                maximum_adverse,
                max(open_trade.entry_price - candle.low, ZERO) * quantity,
            )
            effective_stop = max(stop_loss, trailing_stop)
            if candle.low <= effective_stop:
                reason = (
                    BacktestExitReason.TRAILING_STOP
                    if trailing_stop > stop_loss
                    else BacktestExitReason.HARD_STOP
                )
                return self._close_single_target_counterfactual(
                    open_trade,
                    candle,
                    reason,
                    min(candle.open, effective_stop),
                    trailing_stop=trailing_stop,
                    bars_held=bars_held,
                    breakeven_armed=breakeven_armed,
                    maximum_favorable=maximum_favorable,
                    maximum_adverse=maximum_adverse,
                )
            if candle.high >= target:
                return self._close_single_target_counterfactual(
                    open_trade,
                    candle,
                    BacktestExitReason.TARGET,
                    target,
                    trailing_stop=trailing_stop,
                    bars_held=bars_held,
                    breakeven_armed=breakeven_armed,
                    maximum_favorable=maximum_favorable,
                    maximum_adverse=maximum_adverse,
                )
            if (
                intent.maximum_holding_bars is not None
                and bars_held > intent.maximum_holding_bars
            ):
                return self._close_single_target_counterfactual(
                    open_trade,
                    candle,
                    BacktestExitReason.TIME_EXIT,
                    candle.close,
                    trailing_stop=trailing_stop,
                    bars_held=bars_held,
                    breakeven_armed=breakeven_armed,
                    maximum_favorable=maximum_favorable,
                    maximum_adverse=maximum_adverse,
                )
            if trigger_threshold is not None and maximum_favorable >= trigger_threshold:
                breakeven_armed = True
            if trailing_stop < candle.close:
                candidate = candle.close - trailing_distance
                units = (candidate / self.config.tick_size).to_integral_value(
                    rounding=ROUND_DOWN
                )
                trailing_stop = max(trailing_stop, units * self.config.tick_size)
            if breakeven_armed:
                trailing_stop = max(trailing_stop, open_trade.entry_price)

        last = candles[-1]
        return self._close_single_target_counterfactual(
            open_trade,
            last,
            BacktestExitReason.END_OF_DATA,
            last.close,
            trailing_stop=trailing_stop,
            bars_held=bars_held,
            breakeven_armed=breakeven_armed,
            maximum_favorable=maximum_favorable,
            maximum_adverse=maximum_adverse,
        )

    def _close_single_target_counterfactual(
        self,
        open_trade: _OpenTrade,
        candle: OHLCVCandle,
        reason: BacktestExitReason,
        reference_exit_price: Decimal,
        *,
        trailing_stop: Decimal,
        bars_held: int,
        breakeven_armed: bool,
        maximum_favorable: Decimal,
        maximum_adverse: Decimal,
    ) -> TradeRecord:
        open_trade.position = replace(
            open_trade.position,
            trailing_stop=trailing_stop,
        )
        open_trade.bars_held = bars_held
        open_trade.breakeven_armed = breakeven_armed
        open_trade.maximum_favorable_excursion = maximum_favorable
        open_trade.maximum_adverse_excursion = maximum_adverse
        return self._close_trade(
            open_trade,
            candle,
            reason,
            reference_exit_price,
        )

    def _missed_opportunity_ledger(
        self,
        rejected_candidates: tuple[_RejectedCandidate, ...],
        candles: tuple[OHLCVCandle, ...],
    ) -> MissedOpportunityLedger:
        records = tuple(
            record
            for record in (
                self._missed_opportunity_record(candidate, candles)
                for candidate in rejected_candidates
            )
            if record is not None
        )
        return MissedOpportunityLedger(records=records)

    def _missed_opportunity_record(
        self,
        rejected_candidate: _RejectedCandidate,
        candles: tuple[OHLCVCandle, ...],
    ) -> MissedOpportunityRecord | None:
        intent = rejected_candidate.intent
        if rejected_candidate.entry_index >= len(candles):
            return self._insufficient_evidence_record(
                intent,
                rejected_candidate.blockers,
                rejected_candidate.pre_veto_observation_id,
            )
        if "DATA_UNAVAILABLE" in rejected_candidate.blockers:
            return self._insufficient_evidence_record(
                intent,
                rejected_candidate.blockers,
                rejected_candidate.pre_veto_observation_id,
            )
        trade = self._simulate_counterfactual_trade(
            intent,
            _CandleTail(candles, rejected_candidate.entry_index),
        )
        if trade is None:
            return self._insufficient_evidence_record(
                intent,
                rejected_candidate.blockers,
                rejected_candidate.pre_veto_observation_id,
            )
        category = self._classify_counterfactual(trade)
        improvement_candidate_id = (
            f"improvement:{intent.strategy_id.lower()}:{intent.regime.lower()}:{intent.signal_id.lower()}"
            if category is MissedOpportunityCategory.BAD_BLOCK
            else None
        )
        outcome = trade.trade_outcome
        return MissedOpportunityRecord(
            signal_id=intent.signal_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            regime=intent.regime,
            symbol=intent.symbol.strip().upper() or "UNKNOWN_SYMBOL",
            market=intent.market,
            direction=TradeDirection.LONG,
            rejected_at=intent.timestamp,
            blockers=rejected_candidate.blockers,
            entry_reason=intent.reason_codes,
            dge_status=intent.dge_status,
            pre_veto_observation_id=rejected_candidate.pre_veto_observation_id,
            counterfactual_result=category,
            forward_trade_outcome=outcome,
            forward_realized_r=trade.realized_r_multiple,
            forward_net_pnl=trade.net_pnl_usdt,
            improvement_candidate_id=improvement_candidate_id,
        )

    @staticmethod
    def _classify_counterfactual(trade: TradeRecord) -> MissedOpportunityCategory:
        if trade.realized_r_multiple > ZERO:
            return MissedOpportunityCategory.BAD_BLOCK
        if trade.realized_r_multiple < ZERO:
            return MissedOpportunityCategory.GOOD_BLOCK
        return MissedOpportunityCategory.NEUTRAL_BLOCK

    @staticmethod
    def _insufficient_evidence_record(
        intent: BacktestIntent,
        blockers: tuple[str, ...],
        pre_veto_observation_id: str,
    ) -> MissedOpportunityRecord:
        return MissedOpportunityRecord(
            signal_id=intent.signal_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            regime=intent.regime,
            symbol=intent.symbol.strip().upper() or "UNKNOWN_SYMBOL",
            market=intent.market,
            direction=TradeDirection.LONG,
            rejected_at=intent.timestamp,
            blockers=blockers,
            entry_reason=intent.reason_codes,
            dge_status=intent.dge_status,
            pre_veto_observation_id=pre_veto_observation_id,
            counterfactual_result=MissedOpportunityCategory.INSUFFICIENT_EVIDENCE,
        )

    @staticmethod
    def _result_market(
        trades: tuple[TradeRecord, ...],
        missed_opportunity_ledger: MissedOpportunityLedger,
    ) -> str:
        if trades:
            return trades[0].attribution.market
        if missed_opportunity_ledger.records:
            return missed_opportunity_ledger.records[0].market
        return "SPOT"

    @staticmethod
    def _performance_engine_report(metrics: BacktestMetrics) -> PerformanceEngineReport:
        if "FUTURES" in metrics.market.upper():
            return PerformanceEngineReport(futures_metrics=metrics)
        return PerformanceEngineReport(spot_metrics=metrics)

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
        requested_quantity = self._round_quantity(self.config.quantity)
        if requested_quantity <= ZERO:
            return LiquidityFillDecision(
                requested_quantity=self.config.quantity,
                filled_quantity=ZERO,
                remaining_quantity=self.config.quantity,
                fill_ratio=ZERO,
                price_impact_ratio=ZERO,
                blockers=("STEP_SIZE_ROUNDED_QUANTITY_IS_ZERO",),
            )
        if self.config.liquidity_stress is None:
            return LiquidityFillDecision(
                requested_quantity=requested_quantity,
                filled_quantity=requested_quantity,
                remaining_quantity=Decimal("0"),
                fill_ratio=ONE,
                price_impact_ratio=Decimal("0"),
                blockers=(),
            )
        assessed = assess_liquidity_fill(
            requested_quantity=requested_quantity,
            candle_volume=candle.volume,
            config=self.config.liquidity_stress,
        )
        rounded_filled = self._round_quantity(assessed.filled_quantity)
        if rounded_filled <= ZERO:
            return replace(
                assessed,
                filled_quantity=ZERO,
                remaining_quantity=requested_quantity,
                fill_ratio=ZERO,
                blockers=tuple(
                    dict.fromkeys(
                        (*assessed.blockers, "STEP_SIZE_ROUNDED_QUANTITY_IS_ZERO")
                    )
                ),
            )
        return replace(
            assessed,
            filled_quantity=rounded_filled,
            remaining_quantity=requested_quantity - rounded_filled,
            fill_ratio=rounded_filled / requested_quantity,
        )

    def _updated_trailing_stop(
        self,
        open_trade: _OpenTrade,
        close: Decimal,
    ) -> Decimal:
        from ai4binance.execution.trailing import update_long_trailing_stop

        current_stop = open_trade.position.trailing_stop
        updated_stop = current_stop
        if current_stop < close:
            updated_stop = update_long_trailing_stop(
                current_stop,
                close,
                open_trade.intent.atr,
                multiplier=(
                    open_trade.intent.trailing_atr_multiple
                    or self.config.trailing_multiplier
                ),
                tick_size=self.config.tick_size,
            ).new_stop
        if open_trade.breakeven_armed:
            updated_stop = max(updated_stop, open_trade.entry_price)
        return updated_stop

    @staticmethod
    def _breakeven_trigger_reached(open_trade: _OpenTrade) -> bool:
        trigger = open_trade.intent.breakeven_trigger_r
        if trigger is None:
            return False
        initial_risk = (
            open_trade.entry_price - open_trade.intent.stop_loss
        ) * open_trade.original_quantity
        if initial_risk <= Decimal("0"):
            return False
        return open_trade.maximum_favorable_excursion >= initial_risk * trigger

    @staticmethod
    def _record_reason_codes(
        reason_counts: dict[str, int],
        reason_codes: tuple[str, ...],
    ) -> None:
        for reason_code in reason_codes:
            reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1

    @staticmethod
    def _funding_cost(intent: BacktestIntent) -> Decimal:
        if "FUTURES" in intent.market.upper():
            return Decimal("0")
        return Decimal("0")

    @staticmethod
    def _entry_slippage_cost(open_trade: _OpenTrade) -> Decimal:
        return (
            open_trade.entry_price - open_trade.entry_reference_price
        ) * open_trade.original_quantity

    @staticmethod
    def _realized_r_multiple(
        open_trade: _OpenTrade,
        net_pnl: Decimal,
    ) -> Decimal:
        initial_risk = (
            open_trade.entry_price - open_trade.intent.stop_loss
        ) * open_trade.original_quantity
        if initial_risk <= Decimal("0"):
            return Decimal("0")
        return net_pnl / initial_risk

    @staticmethod
    def _update_excursions(open_trade: _OpenTrade, candle: OHLCVCandle) -> None:
        quantity = open_trade.original_quantity
        favorable = max(candle.high - open_trade.entry_price, Decimal("0")) * quantity
        adverse = max(open_trade.entry_price - candle.low, Decimal("0")) * quantity
        open_trade.maximum_favorable_excursion = max(
            open_trade.maximum_favorable_excursion,
            favorable,
        )
        open_trade.maximum_adverse_excursion = max(
            open_trade.maximum_adverse_excursion,
            adverse,
        )

    @classmethod
    def _trade_edge_ledger(
        cls,
        trades: tuple[TradeRecord, ...],
    ) -> TradeEdgeLedger:
        return TradeEdgeLedger(
            by_strategy=cls._aggregate_trade_edges(
                trades,
                key_fn=lambda trade: (trade.attribution.strategy_id,),
                view_fn=lambda trade: {"strategy_id": trade.attribution.strategy_id},
            ),
            by_regime=cls._aggregate_trade_edges(
                trades,
                key_fn=lambda trade: (trade.attribution.regime,),
                view_fn=lambda trade: {"regime": trade.attribution.regime},
            ),
            by_strategy_regime=cls._aggregate_trade_edges(
                trades,
                key_fn=lambda trade: (
                    trade.attribution.strategy_id,
                    trade.attribution.regime,
                ),
                view_fn=lambda trade: {
                    "strategy_id": trade.attribution.strategy_id,
                    "regime": trade.attribution.regime,
                },
            ),
            by_symbol=cls._aggregate_trade_edges(
                trades,
                key_fn=lambda trade: (trade.attribution.symbol,),
                view_fn=lambda trade: {"symbol": trade.attribution.symbol},
            ),
            by_timeframe=cls._aggregate_trade_edges(
                trades,
                key_fn=lambda trade: (trade.attribution.timeframe,),
                view_fn=lambda trade: {"timeframe": trade.attribution.timeframe},
            ),
        )

    @staticmethod
    def _aggregate_trade_edges(
        trades: tuple[TradeRecord, ...],
        *,
        key_fn: Callable[[TradeRecord], tuple[str, ...]],
        view_fn: Callable[[TradeRecord], dict[str, str]],
    ) -> tuple[TradeEdgeAggregateView, ...]:
        grouped: dict[tuple[str, ...], list[TradeRecord]] = {}
        for trade in trades:
            grouped.setdefault(key_fn(trade), []).append(trade)
        views: list[TradeEdgeAggregateView] = []
        for key in sorted(grouped):
            group = grouped[key]
            denominator = Decimal(len(group))
            views.append(
                TradeEdgeAggregateView(
                    trade_count=len(group),
                    gross_pnl_usdt=sum(
                        (trade.gross_pnl_usdt for trade in group),
                        start=Decimal("0"),
                    ),
                    fee_cost_usdt=sum(
                        (trade.fee_cost_usdt for trade in group),
                        start=Decimal("0"),
                    ),
                    slippage_cost_usdt=sum(
                        (trade.slippage_cost_usdt for trade in group),
                        start=Decimal("0"),
                    ),
                    funding_cost_usdt=sum(
                        (trade.funding_cost_usdt for trade in group),
                        start=Decimal("0"),
                    ),
                    net_pnl_usdt=sum(
                        (trade.net_pnl_usdt for trade in group),
                        start=Decimal("0"),
                    ),
                    average_realized_r_multiple=(
                        sum(
                            (trade.realized_r_multiple for trade in group),
                            start=Decimal("0"),
                        )
                        / denominator
                    ),
                    average_maximum_favorable_excursion=(
                        sum(
                            (trade.maximum_favorable_excursion for trade in group),
                            start=Decimal("0"),
                        )
                        / denominator
                    ),
                    average_maximum_adverse_excursion=(
                        sum(
                            (trade.maximum_adverse_excursion for trade in group),
                            start=Decimal("0"),
                        )
                        / denominator
                    ),
                    average_holding_period=(
                        sum(
                            (Decimal(trade.holding_period) for trade in group),
                            start=Decimal("0"),
                        )
                        / denominator
                    ),
                    **view_fn(group[0]),
                )
            )
        return tuple(views)

    @staticmethod
    def _normalize_intent(
        intent: BacktestIntent,
        *,
        symbol: str,
        timeframe: str,
    ) -> BacktestIntent:
        normalized_symbol = intent.symbol.strip().upper() or symbol.strip().upper()
        normalized_timeframe = intent.timeframe.strip() or timeframe.strip()
        normalized_snapshot_id = (
            intent.snapshot_id.strip()
            or f"snapshot:{normalized_symbol}:{normalized_timeframe}:{intent.signal_id}"
        )
        normalized_decision_id = (
            intent.decision_id.strip() or f"decision:{intent.signal_id}"
        )
        return replace(
            intent,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            snapshot_id=normalized_snapshot_id,
            decision_id=normalized_decision_id,
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
            BacktestExitReason.HARD_STOP,
            BacktestExitReason.TRAILING_STOP,
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
        if "FUTURES" in intent.market.upper():
            blockers.append("DATA_UNAVAILABLE")
        if intent.timestamp != candle.timestamp:
            blockers.append("SIGNAL_TIMESTAMP_MISMATCH")
        if open_trade is not None:
            blockers.append("POSITION_ALREADY_OPEN")
        if pending is not None:
            blockers.append("ENTRY_ALREADY_PENDING")
        return tuple(blockers)

    def _round_quantity(self, quantity: Decimal) -> Decimal:
        return quantity.quantize(self.config.step_size, rounding=ROUND_DOWN)

    def _round_price(self, price: Decimal, *, rounding: str) -> Decimal:
        return price.quantize(self.config.tick_size, rounding=rounding)

    @staticmethod
    def _closure_review(
        reason: BacktestExitReason,
        ignored_signals: int,
    ) -> ClosureReview:
        trailing_exit = reason is BacktestExitReason.TRAILING_STOP
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
