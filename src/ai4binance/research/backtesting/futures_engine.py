"""Deterministic long/short USD-M Futures replay backtesting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from ai4binance.research.backtesting.liquidity import (
    LiquidityFillDecision,
    assess_liquidity_fill,
)
from ai4binance.research.backtesting.metrics import calculate_metrics
from ai4binance.research.backtesting.models import (
    BacktestConfig,
    BacktestExitReason,
    BacktestResult,
    ClosedTradeAttribution,
    ClosureReview,
    EquityPoint,
    MissedOpportunityCategory,
    MissedOpportunityLedger,
    MissedOpportunityRecord,
    PerformanceEngineReport,
    PreVetoOpportunityLedger,
    PreVetoOpportunityRecord,
    RejectedSignal,
    TradeDirection,
    TradeRecord,
    VirtualMarketFunnelStage,
    VirtualMarketFunnelTelemetry,
)
from ai4binance.research.virtual_runtime_risk import (
    FuturesRiskBracket,
    isolated_liquidation_price,
    validate_futures_brackets,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
)

ZERO = Decimal("0")
ONE = Decimal("1")
USD_M_FUTURES = "USD_M_FUTURES"
_UPSTREAM_STAGES = frozenset(
    {
        VirtualMarketFunnelStage.DISCOVERED.value,
        VirtualMarketFunnelStage.READY_FOR_RISK.value,
        VirtualMarketFunnelStage.RISK_PASS.value,
        VirtualMarketFunnelStage.VALIDATION_PASS.value,
        VirtualMarketFunnelStage.DGE_PASS.value,
    }
)


@dataclass(frozen=True, slots=True)
class FuturesBacktestConfig(BacktestConfig):
    """Explicit isolated-margin assumptions for USD-M Futures replay."""

    leverage: int = 2
    maintenance_margin_ratio: Decimal = Decimal("0.005")
    liquidation_fee_ratio: Decimal = Decimal("0.005")
    require_mark_price_path: bool = False
    maintenance_brackets: tuple[FuturesRiskBracket, ...] = ()

    def __post_init__(self) -> None:
        BacktestConfig.__post_init__(self)
        if self.require_mark_price_path:
            validate_futures_brackets(self.maintenance_brackets)
        if (
            isinstance(self.leverage, bool)
            or not isinstance(self.leverage, int)
            or not 1 <= self.leverage <= 125
        ):
            raise ValueError("leverage must be an integer between 1 and 125")
        ratios = (self.maintenance_margin_ratio, self.liquidation_fee_ratio)
        if any(not ratio.is_finite() or ratio < ZERO for ratio in ratios):
            raise ValueError("Futures margin ratios must be finite and non-negative")
        if self.maintenance_margin_ratio <= ZERO:
            raise ValueError("maintenance_margin_ratio must be positive")
        if self.liquidation_fee_ratio > Decimal("0.02"):
            raise ValueError("liquidation_fee_ratio cannot exceed 0.02")
        if self.maintenance_margin_ratio >= ONE / Decimal(self.leverage):
            raise ValueError(
                "maintenance margin must remain below the initial margin ratio"
            )


@dataclass(frozen=True, slots=True)
class FuturesBacktestIntent:
    """Directional Futures signal proposed after one replay candle closes."""

    signal_id: str
    timestamp: datetime
    direction: TradeDirection
    stop_loss: Decimal
    take_profit: Decimal
    reason_codes: tuple[str, ...] = ("FUTURES_BACKTEST_SIGNAL",)
    maximum_holding_bars: int | None = None
    strategy_id: str = "UNSPECIFIED_STRATEGY"
    strategy_version: str = "1"
    strategy_config_version: str = "1"
    strategy_config_hash: str = "default"
    symbol: str = ""
    regime: str = "UNKNOWN"
    timeframe: str = "1h"
    snapshot_id: str = ""
    decision_id: str = ""
    opportunity_id: str = ""
    entry_score: Decimal = ZERO
    evidence_score: Decimal = ZERO
    dge_status: str = "UNKNOWN"
    blocker_history: tuple[str, ...] = ()
    funnel_stages: tuple[str, ...] = (
        VirtualMarketFunnelStage.DISCOVERED.value,
        VirtualMarketFunnelStage.READY_FOR_RISK.value,
    )
    market: str = field(default=USD_M_FUTURES, init=False)

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("Futures signal identity is required")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("Futures signal timestamp must be timezone-aware")
        if not isinstance(self.direction, TradeDirection):
            raise ValueError("Futures signal direction must be LONG or SHORT")
        if any(
            not price.is_finite() or price <= ZERO
            for price in (self.stop_loss, self.take_profit)
        ):
            raise ValueError("Futures signal prices must be finite and positive")
        if not self.reason_codes or any(
            not reason.strip() for reason in self.reason_codes
        ):
            raise ValueError("Futures signal reason codes are required")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Futures signal reason codes must be unique")
        if not self.opportunity_id.strip():
            object.__setattr__(
                self,
                "opportunity_id",
                f"opportunity:{self.signal_id}",
            )
        if self.maximum_holding_bars is not None and self.maximum_holding_bars < 1:
            raise ValueError("maximum_holding_bars must be positive when configured")
        for field_name in (
            "strategy_id",
            "strategy_version",
            "strategy_config_version",
            "strategy_config_hash",
            "regime",
            "timeframe",
            "dge_status",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} is required")
        if any(
            not score.is_finite() or score < ZERO
            for score in (self.entry_score, self.evidence_score)
        ):
            raise ValueError("Futures signal scores must be finite and non-negative")
        if len(set(self.blocker_history)) != len(self.blocker_history) or any(
            not blocker.strip() for blocker in self.blocker_history
        ):
            raise ValueError(
                "Futures signal blocker history must be unique and nonblank"
            )
        if (
            not self.funnel_stages
            or len(set(self.funnel_stages)) != len(self.funnel_stages)
            or any(stage not in _UPSTREAM_STAGES for stage in self.funnel_stages)
        ):
            raise ValueError("Futures signal funnel stages are invalid")

    @property
    def closed_trade_attribution(self) -> ClosedTradeAttribution:
        """Return exact Futures lineage for a closed research trade."""

        return ClosedTradeAttribution(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            strategy_config_version=self.strategy_config_version,
            strategy_config_hash=self.strategy_config_hash,
            market=USD_M_FUTURES,
            symbol=self.symbol,
            regime=self.regime,
            timeframe=self.timeframe,
            snapshot_id=self.snapshot_id,
            decision_id=self.decision_id,
            opportunity_id=self.opportunity_id,
        )


FuturesSignalProvider = Callable[
    [RuntimeFuturesReplayDataset], FuturesBacktestIntent | None
]


@dataclass(slots=True)
class _OpenFuturesTrade:
    intent: FuturesBacktestIntent
    entry_timestamp: datetime
    entry_reference_price: Decimal
    entry_price: Decimal
    quantity: Decimal
    entry_fee: Decimal
    initial_margin: Decimal
    liquidation_price: Decimal
    funding_cost: Decimal = ZERO
    last_funding_timestamp: datetime | None = None
    maximum_favorable_excursion: Decimal = ZERO
    maximum_adverse_excursion: Decimal = ZERO
    bars_held: int = 0
    ignored_signals: int = 0
    blocker_history: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ExitDecision:
    reason: BacktestExitReason
    reference_price: Decimal


@dataclass(frozen=True, slots=True)
class _RejectedFuturesCandidate:
    intent: FuturesBacktestIntent
    blockers: tuple[str, ...]
    entry_index: int
    pre_veto_observation_id: str


@dataclass(frozen=True, slots=True)
class FuturesBacktestEngine:
    """Replay isolated Futures positions without granting execution authority."""

    config: FuturesBacktestConfig = field(default_factory=FuturesBacktestConfig)
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)

    def run(
        self,
        *,
        dataset: RuntimeFuturesReplayDataset,
        signal_provider: FuturesSignalProvider,
    ) -> BacktestResult:
        """Run a look-ahead-safe next-bar replay over a governed dataset."""

        self._validate_dataset(dataset)
        candles = dataset.candles
        mark_candles = (
            dataset.mark_candles if self.config.require_mark_price_path else ()
        )
        if mark_candles:
            mark_times = {c.timestamp for c in mark_candles}
            if any(
                p.timestamp not in mark_times
                for p in dataset.derivatives.series[DerivativesMetric.FUNDING_RATE]
            ):
                raise ValueError("funding settlement requires a finer native mark path")
        dataset_sha256 = dataset.dataset_sha256
        funding_points = dataset.derivatives.series[DerivativesMetric.FUNDING_RATE]
        trades: list[TradeRecord] = []
        rejected: list[RejectedSignal] = []
        rejected_candidates: list[_RejectedFuturesCandidate] = []
        pre_veto_observations: list[PreVetoOpportunityRecord] = []
        audit: list[dict[str, object]] = (
            [
                {
                    "event_type": "FUTURES_LIQUIDATION_MODEL",
                    "dataset_sha256": dataset_sha256,
                    "model": "ISOLATED_MARK_OHLC_TIERED_V1"
                    if mark_candles
                    else "LEGACY_CONTRACT_PRICE_APPROXIMATION",
                    "intrabar_order": "UNKNOWN_ADVERSE_FIRST_BOUND",
                    "execution_allowed": False,
                }
            ]
            if mark_candles
            else []
        )
        equity_curve: list[EquityPoint] = []
        stage_counts = {stage.value: 0 for stage in VirtualMarketFunnelStage}
        reason_counts: dict[str, int] = {}
        seen_signal_ids: set[str] = set()
        pending: FuturesBacktestIntent | None = None
        pending_observation_id: str | None = None
        open_trade: _OpenFuturesTrade | None = None
        available_cash = self.config.initial_cash_usdt
        no_trade_count = 0
        indexed_provider = getattr(signal_provider, "intent_at", None)

        for index, candle in enumerate(candles):
            if pending is not None and open_trade is None:
                entry_blockers = self._entry_blockers(pending, candle, available_cash)
                if entry_blockers:
                    self._reject(
                        pending,
                        entry_blockers,
                        rejected,
                        reason_counts,
                    )
                    rejected_candidates.append(
                        _RejectedFuturesCandidate(
                            intent=pending,
                            blockers=entry_blockers,
                            entry_index=index,
                            pre_veto_observation_id=(
                                pending_observation_id
                                or self._pre_veto_observation_id(pending, index - 1)
                            ),
                        )
                    )
                    audit.append(
                        self._event(
                            "FUTURES_ENTRY_REJECTED",
                            pending.signal_id,
                            candle.timestamp,
                            dataset_sha256,
                        )
                    )
                else:
                    open_trade = self._open_trade(pending, candle)
                    stage_counts[VirtualMarketFunnelStage.FILLED.value] += 1
                    event_type = (
                        "FUTURES_ENTRY_PARTIALLY_FILLED"
                        if open_trade.quantity < self.config.quantity
                        else "FUTURES_ENTRY_FILLED"
                    )
                    audit.append(
                        self._event(
                            event_type,
                            pending.signal_id,
                            candle.timestamp,
                            dataset_sha256,
                        )
                    )
                pending = None
                pending_observation_id = None

            if open_trade is not None:
                if mark_candles:
                    self._mark_path_funding(
                        open_trade, funding_points, mark_candles[index]
                    )
                else:
                    self._apply_funding(open_trade, funding_points, candle.timestamp)
                self._update_excursions(open_trade, candle)
                open_trade.bars_held += 1
                exit_decision = self._exit_decision(
                    open_trade, candle, mark_candles[index] if mark_candles else None
                )
                if exit_decision is not None:
                    trade = self._close_trade(
                        open_trade,
                        candle.timestamp,
                        exit_decision,
                    )
                    trades.append(trade)
                    stage_counts[VirtualMarketFunnelStage.CLOSED.value] += 1
                    available_cash += trade.net_pnl_usdt
                    if exit_decision.reason is BacktestExitReason.LIQUIDATION:
                        reason_counts["FUTURES_LIQUIDATION_OCCURRED"] = (
                            reason_counts.get("FUTURES_LIQUIDATION_OCCURRED", 0) + 1
                        )
                    close_event = self._event(
                        exit_decision.reason.value,
                        trade.trade_id,
                        candle.timestamp,
                        dataset_sha256,
                    )
                    close_event["reference_exit_price"] = str(
                        exit_decision.reference_price
                    )
                    audit.append(close_event)
                    open_trade = None

            equity_curve.append(
                self._equity_point(
                    mark_candles[index] if mark_candles else candle,
                    available_cash,
                    open_trade,
                )
            )

            if callable(indexed_provider):
                intent = indexed_provider(dataset, index)
            else:
                replay_prefix = self._replay_prefix(dataset, index + 1)
                intent = signal_provider(replay_prefix)
            if intent is None:
                no_trade_count += 1
                continue
            if not isinstance(intent, FuturesBacktestIntent):
                raise TypeError(
                    "Futures signal provider returned an unsupported intent"
                )
            intent = self._normalize_intent(intent, dataset, dataset_sha256)
            observation = self._pre_veto_observation(intent, candle, index)
            pre_veto_observations.append(observation)
            audit.append(
                self._event(
                    "OPPORTUNITY_OBSERVED_PRE_VETO",
                    observation.observation_id,
                    candle.timestamp,
                    dataset_sha256,
                )
            )
            blockers = self._intent_blockers(
                intent,
                candle.timestamp,
                open_trade,
                seen_signal_ids,
                dataset,
            )
            seen_signal_ids.add(intent.signal_id)
            for stage in intent.funnel_stages:
                stage_counts[stage] += 1
            if blockers:
                self._reject(intent, blockers, rejected, reason_counts)
                rejected_candidates.append(
                    _RejectedFuturesCandidate(
                        intent=intent,
                        blockers=blockers,
                        entry_index=index + 1,
                        pre_veto_observation_id=observation.observation_id,
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
            self._reject(pending, ("NO_NEXT_BAR",), rejected, reason_counts)
            rejected_candidates.append(
                _RejectedFuturesCandidate(
                    intent=pending,
                    blockers=("NO_NEXT_BAR",),
                    entry_index=len(candles),
                    pre_veto_observation_id=(
                        pending_observation_id
                        or self._pre_veto_observation_id(pending, len(candles) - 1)
                    ),
                )
            )
        if open_trade is not None:
            last = candles[-1]
            decision = _ExitDecision(BacktestExitReason.END_OF_DATA, last.close)
            trade = self._close_trade(open_trade, last.timestamp, decision)
            trades.append(trade)
            stage_counts[VirtualMarketFunnelStage.CLOSED.value] += 1
            available_cash += trade.net_pnl_usdt
            audit.append(
                self._event(
                    decision.reason.value,
                    trade.trade_id,
                    last.timestamp,
                    dataset_sha256,
                )
            )

        benchmark = self._buy_and_hold_return(candles)
        missed_opportunity_ledger = self._missed_opportunity_ledger(
            tuple(rejected_candidates),
            candles,
            funding_points,
            mark_candles,
        )
        for record in missed_opportunity_ledger.records:
            review_event = self._event(
                "OPPORTUNITY_VETO_REVIEWED",
                record.pre_veto_observation_id,
                candles[-1].timestamp,
                dataset_sha256,
            )
            review_event["counterfactual_result"] = record.counterfactual_result.value
            review_event["blockers"] = record.blockers
            review_event["forward_net_pnl"] = (
                str(record.forward_net_pnl)
                if record.forward_net_pnl is not None
                else None
            )
            audit.append(review_event)
        metrics = calculate_metrics(
            tuple(trades),
            float(self.config.initial_cash_usdt),
            benchmark,
            tuple(float(point.equity_usdt) for point in equity_curve),
            market=USD_M_FUTURES,
            backtest_duration_seconds=int(
                (candles[-1].timestamp - candles[0].timestamp).total_seconds()
            ),
            missed_opportunity_ledger=missed_opportunity_ledger,
        )
        return BacktestResult(
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            started_at=candles[0].timestamp,
            ended_at=candles[-1].timestamp,
            assumptions=self.config,
            trades=tuple(trades),
            rejected_signals=tuple(rejected),
            no_trade_count=no_trade_count,
            metrics=metrics,
            audit_events=tuple(audit),
            equity_curve=tuple(equity_curve),
            funnel_telemetry=VirtualMarketFunnelTelemetry(
                stage_counts=tuple(
                    (stage.value, stage_counts[stage.value])
                    for stage in VirtualMarketFunnelStage
                ),
                reason_code_counts=tuple(sorted(reason_counts.items())),
            ),
            trade_outcomes=tuple(trade.trade_outcome for trade in trades),
            performance_engine_report=PerformanceEngineReport(futures_metrics=metrics),
            missed_opportunity_ledger=missed_opportunity_ledger,
            pre_veto_opportunity_ledger=PreVetoOpportunityLedger(
                records=tuple(pre_veto_observations)
            ),
        )

    @staticmethod
    def _pre_veto_observation_id(intent: FuturesBacktestIntent, index: int) -> str:
        return (
            f"pre-veto:{USD_M_FUTURES.lower()}:"
            f"{intent.snapshot_id or intent.signal_id}:{index}:{intent.signal_id}"
        )

    @classmethod
    def _pre_veto_observation(
        cls,
        intent: FuturesBacktestIntent,
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
            symbol=intent.symbol,
            market=USD_M_FUTURES,
            direction=intent.direction,
            observed_at=intent.timestamp,
            reference_price=candle.close,
            stop_loss=intent.stop_loss,
            take_profit_levels=(intent.take_profit,),
            entry_reason=intent.reason_codes,
            dge_status=intent.dge_status,
        )

    @staticmethod
    def _validate_dataset(dataset: RuntimeFuturesReplayDataset) -> None:
        if not isinstance(dataset, RuntimeFuturesReplayDataset):
            raise TypeError("Futures backtest requires RuntimeFuturesReplayDataset")
        if dataset.market != USD_M_FUTURES:
            raise ValueError("Futures replay identity is unsupported")
        if len(dataset.candles) < 2:
            raise ValueError("at least two closed Futures candles are required")
        if not dataset.derivatives.series.get(DerivativesMetric.FUNDING_RATE):
            raise ValueError("Futures replay funding-rate history is required")

    @staticmethod
    def _normalize_intent(
        intent: FuturesBacktestIntent,
        dataset: RuntimeFuturesReplayDataset,
        dataset_sha256: str | None = None,
    ) -> FuturesBacktestIntent:
        symbol = intent.symbol.strip().upper() or dataset.symbol
        snapshot_id = intent.snapshot_id.strip() or (
            dataset_sha256 or dataset.dataset_sha256
        )
        decision_id = intent.decision_id.strip() or f"decision:{intent.signal_id}"
        return replace(
            intent,
            symbol=symbol,
            snapshot_id=snapshot_id,
            decision_id=decision_id,
        )

    @staticmethod
    def _intent_blockers(
        intent: FuturesBacktestIntent,
        candle_timestamp: datetime,
        open_trade: _OpenFuturesTrade | None,
        seen_signal_ids: set[str],
        dataset: RuntimeFuturesReplayDataset,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if intent.timestamp != candle_timestamp:
            blockers.append("SIGNAL_TIMESTAMP_MISMATCH")
        if intent.symbol != dataset.symbol:
            blockers.append("SIGNAL_SYMBOL_MISMATCH")
        if intent.timeframe != dataset.timeframe:
            blockers.append("SIGNAL_TIMEFRAME_MISMATCH")
        if intent.signal_id in seen_signal_ids:
            blockers.append("DUPLICATE_SIGNAL_ID")
        if open_trade is not None:
            blockers.append("POSITION_ALREADY_OPEN")
        return tuple(blockers)

    def _entry_blockers(
        self,
        intent: FuturesBacktestIntent,
        candle: OHLCVCandle,
        available_cash: Decimal,
    ) -> tuple[str, ...]:
        fill = self._entry_fill(candle.volume)
        entry = self._entry_price(intent.direction, candle.open, fill)
        blockers = list(fill.blockers)
        if entry <= ZERO:
            blockers.append("INVALID_NEXT_BAR_ENTRY_PRICE")
            return tuple(blockers)
        if intent.direction is TradeDirection.LONG:
            if intent.stop_loss >= entry or intent.take_profit <= entry:
                blockers.append("FUTURES_LONG_GEOMETRY_INVALID")
        elif intent.stop_loss <= entry or intent.take_profit >= entry:
            blockers.append("FUTURES_SHORT_GEOMETRY_INVALID")
        notional = entry * fill.filled_quantity
        initial_margin = notional / Decimal(self.config.leverage)
        entry_fee = notional * self.config.fee_ratio
        if initial_margin + entry_fee > available_cash:
            blockers.append("INSUFFICIENT_BACKTEST_MARGIN")
        if notional < self.config.minimum_notional:
            blockers.append("MIN_NOTIONAL_NOT_REACHED")
        if fill.filled_quantity > ZERO:
            liquidation = self._liquidation_price(
                intent.direction,
                entry,
                fill.filled_quantity,
                initial_margin,
                notional * self.config.maintenance_margin_ratio,
            )
            if (
                intent.direction is TradeDirection.LONG
                and intent.stop_loss <= liquidation
            ) or (
                intent.direction is TradeDirection.SHORT
                and intent.stop_loss >= liquidation
            ):
                blockers.append("STOP_BEYOND_LIQUIDATION")
        return tuple(dict.fromkeys(blockers))

    def _open_trade(
        self,
        intent: FuturesBacktestIntent,
        candle: OHLCVCandle,
    ) -> _OpenFuturesTrade:
        fill = self._entry_fill(candle.volume)
        entry = self._entry_price(intent.direction, candle.open, fill)
        notional = entry * fill.filled_quantity
        initial_margin = notional / Decimal(self.config.leverage)
        maintenance_margin = notional * self.config.maintenance_margin_ratio
        return _OpenFuturesTrade(
            intent=intent,
            entry_timestamp=candle.timestamp,
            entry_reference_price=candle.open,
            entry_price=entry,
            quantity=fill.filled_quantity,
            entry_fee=notional * self.config.fee_ratio,
            initial_margin=initial_margin,
            liquidation_price=self._liquidation_price(
                intent.direction,
                entry,
                fill.filled_quantity,
                initial_margin,
                maintenance_margin,
            ),
            last_funding_timestamp=candle.timestamp,
        )

    def _entry_fill(self, candle_volume: Decimal) -> LiquidityFillDecision:
        quantity = self.config.quantity.quantize(
            self.config.step_size,
            rounding=ROUND_DOWN,
        )
        if quantity <= ZERO:
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
                requested_quantity=quantity,
                filled_quantity=quantity,
                remaining_quantity=ZERO,
                fill_ratio=ONE,
                price_impact_ratio=ZERO,
                blockers=(),
            )
        assessed = assess_liquidity_fill(
            requested_quantity=quantity,
            candle_volume=candle_volume,
            config=self.config.liquidity_stress,
        )
        filled = assessed.filled_quantity.quantize(
            self.config.step_size,
            rounding=ROUND_DOWN,
        )
        if filled <= ZERO:
            return replace(
                assessed,
                filled_quantity=ZERO,
                remaining_quantity=quantity,
                fill_ratio=ZERO,
                blockers=tuple(
                    dict.fromkeys(
                        (*assessed.blockers, "STEP_SIZE_ROUNDED_QUANTITY_IS_ZERO")
                    )
                ),
            )
        return replace(
            assessed,
            filled_quantity=filled,
            remaining_quantity=quantity - filled,
            fill_ratio=filled / quantity,
        )

    def _entry_price(
        self,
        direction: TradeDirection,
        reference_price: Decimal,
        fill: LiquidityFillDecision,
    ) -> Decimal:
        drag = self.config.slippage_ratio + fill.price_impact_ratio
        if direction is TradeDirection.LONG:
            price = reference_price * (ONE + drag)
            rounding = ROUND_UP
        else:
            price = reference_price * (ONE - drag)
            rounding = ROUND_DOWN
        return price.quantize(self.config.tick_size, rounding=rounding)

    def _liquidation_price(
        self,
        direction: TradeDirection,
        entry_price: Decimal,
        quantity: Decimal,
        isolated_margin: Decimal,
        maintenance_margin: Decimal,
    ) -> Decimal:
        if self.config.require_mark_price_path:
            return isolated_liquidation_price(
                long=direction is TradeDirection.LONG,
                entry=entry_price,
                quantity=quantity,
                wallet_margin=isolated_margin,
                brackets=self.config.maintenance_brackets,
            )
        buffer_per_unit = (isolated_margin - maintenance_margin) / quantity
        if direction is TradeDirection.LONG:
            return entry_price - buffer_per_unit
        return entry_price + buffer_per_unit

    def _mark_path_funding(
        self,
        trade: _OpenFuturesTrade,
        points: tuple[MetricPoint, ...],
        mark: OHLCVCandle,
    ) -> None:
        """Settle funding at the observed mark and re-solve every bar's margin."""
        last = trade.last_funding_timestamp or trade.entry_timestamp
        sign = ONE if trade.intent.direction is TradeDirection.LONG else -ONE
        for point in points:
            if last < point.timestamp <= mark.timestamp:
                if point.timestamp != mark.timestamp:
                    raise ValueError(
                        "funding settlement requires a finer native mark path"
                    )
                trade.funding_cost += trade.quantity * mark.open * point.value * sign
                trade.last_funding_timestamp = point.timestamp
        trade.liquidation_price = isolated_liquidation_price(
            long=sign == ONE,
            entry=trade.entry_price,
            quantity=trade.quantity,
            wallet_margin=trade.initial_margin - trade.funding_cost,
            brackets=self.config.maintenance_brackets,
        )

    @staticmethod
    def _apply_funding(
        open_trade: _OpenFuturesTrade,
        funding_points: tuple[MetricPoint, ...],
        candle_timestamp: datetime,
    ) -> None:
        last_timestamp = open_trade.last_funding_timestamp or open_trade.entry_timestamp
        direction_sign = (
            ONE if open_trade.intent.direction is TradeDirection.LONG else -ONE
        )
        notional = open_trade.entry_price * open_trade.quantity
        for point in funding_points:
            if last_timestamp < point.timestamp <= candle_timestamp:
                open_trade.funding_cost += notional * point.value * direction_sign
                open_trade.last_funding_timestamp = point.timestamp

    @staticmethod
    def _update_excursions(
        open_trade: _OpenFuturesTrade,
        candle: OHLCVCandle,
    ) -> None:
        if open_trade.intent.direction is TradeDirection.LONG:
            favorable = max(candle.high - open_trade.entry_price, ZERO)
            adverse = max(open_trade.entry_price - candle.low, ZERO)
        else:
            favorable = max(open_trade.entry_price - candle.low, ZERO)
            adverse = max(candle.high - open_trade.entry_price, ZERO)
        open_trade.maximum_favorable_excursion = max(
            open_trade.maximum_favorable_excursion,
            favorable * open_trade.quantity,
        )
        open_trade.maximum_adverse_excursion = max(
            open_trade.maximum_adverse_excursion,
            adverse * open_trade.quantity,
        )

    @staticmethod
    def _exit_decision(
        open_trade: _OpenFuturesTrade,
        candle: OHLCVCandle,
        mark_candle: OHLCVCandle | None = None,
    ) -> _ExitDecision | None:
        intent = open_trade.intent
        liquidation_candle = mark_candle or candle
        if intent.direction is TradeDirection.LONG:
            if liquidation_candle.low <= open_trade.liquidation_price:
                if mark_candle is not None:
                    open_trade.blocker_history.append(
                        "MARK_OHLC_INTRABAR_ORDER_UNKNOWN"
                    )
                return _ExitDecision(
                    BacktestExitReason.LIQUIDATION,
                    min(liquidation_candle.open, open_trade.liquidation_price),
                )
            if candle.low <= intent.stop_loss:
                return _ExitDecision(BacktestExitReason.HARD_STOP, intent.stop_loss)
            if candle.high >= intent.take_profit:
                return _ExitDecision(BacktestExitReason.TARGET, intent.take_profit)
        else:
            if liquidation_candle.high >= open_trade.liquidation_price:
                if mark_candle is not None:
                    open_trade.blocker_history.append(
                        "MARK_OHLC_INTRABAR_ORDER_UNKNOWN"
                    )
                return _ExitDecision(
                    BacktestExitReason.LIQUIDATION,
                    max(liquidation_candle.open, open_trade.liquidation_price),
                )
            if candle.high >= intent.stop_loss:
                return _ExitDecision(BacktestExitReason.HARD_STOP, intent.stop_loss)
            if candle.low <= intent.take_profit:
                return _ExitDecision(BacktestExitReason.TARGET, intent.take_profit)
        if (
            intent.maximum_holding_bars is not None
            and open_trade.bars_held >= intent.maximum_holding_bars
        ):
            return _ExitDecision(BacktestExitReason.TIME_EXIT, candle.close)
        return None

    def _close_trade(
        self,
        open_trade: _OpenFuturesTrade,
        exit_timestamp: datetime,
        decision: _ExitDecision,
    ) -> TradeRecord:
        direction_sign = (
            ONE if open_trade.intent.direction is TradeDirection.LONG else -ONE
        )
        if open_trade.intent.direction is TradeDirection.LONG:
            raw_exit = decision.reference_price * (ONE - self.config.slippage_ratio)
            exit_price = raw_exit.quantize(self.config.tick_size, rounding=ROUND_DOWN)
            entry_slippage = open_trade.entry_price - open_trade.entry_reference_price
            exit_slippage = decision.reference_price - exit_price
        else:
            raw_exit = decision.reference_price * (ONE + self.config.slippage_ratio)
            exit_price = raw_exit.quantize(self.config.tick_size, rounding=ROUND_UP)
            entry_slippage = open_trade.entry_reference_price - open_trade.entry_price
            exit_slippage = exit_price - decision.reference_price
        gross_pnl = (
            (decision.reference_price - open_trade.entry_reference_price)
            * open_trade.quantity
            * direction_sign
        )
        exit_fee = exit_price * open_trade.quantity * self.config.fee_ratio
        liquidation_fee = ZERO
        if decision.reason is BacktestExitReason.LIQUIDATION:
            liquidation_fee = (
                exit_price * open_trade.quantity * self.config.liquidation_fee_ratio
            )
        fee_cost = open_trade.entry_fee + exit_fee + liquidation_fee
        slippage_cost = (entry_slippage + exit_slippage) * open_trade.quantity
        net_pnl = gross_pnl - fee_cost - slippage_cost - open_trade.funding_cost
        risk_at_entry = (
            abs(open_trade.entry_price - open_trade.intent.stop_loss)
            * open_trade.quantity
        )
        planned_reward = (
            abs(open_trade.intent.take_profit - open_trade.entry_price)
            * open_trade.quantity
        )
        planned_rr = planned_reward / risk_at_entry if risk_at_entry > ZERO else ZERO
        realized_r = net_pnl / risk_at_entry if risk_at_entry > ZERO else ZERO
        holding_seconds = int(
            (exit_timestamp - open_trade.entry_timestamp).total_seconds()
        )
        exit_blockers = (
            ("FUTURES_LIQUIDATION_OCCURRED",)
            if decision.reason is BacktestExitReason.LIQUIDATION
            else ()
        )
        return TradeRecord(
            trade_id=f"trade:{open_trade.intent.signal_id}",
            signal_id=open_trade.intent.signal_id,
            entry_timestamp=open_trade.entry_timestamp,
            exit_timestamp=exit_timestamp,
            entry_price=open_trade.entry_price,
            exit_price=exit_price,
            quantity=open_trade.quantity,
            entry_fee_usdt=open_trade.entry_fee,
            exit_fee_usdt=exit_fee + liquidation_fee,
            net_pnl_usdt=net_pnl,
            return_ratio=net_pnl / (open_trade.initial_margin + open_trade.entry_fee),
            exit_reason=decision.reason,
            closure_review=self._closure_review(
                decision.reason,
                open_trade.ignored_signals,
            ),
            entry_reason=open_trade.intent.reason_codes,
            attribution=open_trade.intent.closed_trade_attribution,
            gross_pnl_usdt=gross_pnl,
            fee_cost_usdt=fee_cost,
            slippage_cost_usdt=slippage_cost,
            funding_cost_usdt=open_trade.funding_cost,
            realized_r_multiple=realized_r,
            maximum_favorable_excursion=open_trade.maximum_favorable_excursion,
            maximum_adverse_excursion=open_trade.maximum_adverse_excursion,
            holding_period=holding_seconds,
            direction=open_trade.intent.direction,
            MAE=open_trade.maximum_adverse_excursion,
            MFE=open_trade.maximum_favorable_excursion,
            holding_time=holding_seconds,
            gross_pnl=gross_pnl,
            fees=fee_cost,
            slippage=slippage_cost,
            net_pnl=net_pnl,
            risk_at_entry=risk_at_entry,
            planned_rr=planned_rr,
            entry_score=open_trade.intent.entry_score,
            evidence_score=open_trade.intent.evidence_score,
            dge_status=open_trade.intent.dge_status,
            blocker_history=tuple(
                dict.fromkeys(
                    (
                        *open_trade.intent.blocker_history,
                        *open_trade.blocker_history,
                        *exit_blockers,
                    )
                )
            ),
        )

    def _equity_point(
        self,
        candle: OHLCVCandle,
        available_cash: Decimal,
        open_trade: _OpenFuturesTrade | None,
    ) -> EquityPoint:
        if open_trade is None:
            return EquityPoint(candle.timestamp, available_cash, ZERO)
        direction_sign = (
            ONE if open_trade.intent.direction is TradeDirection.LONG else -ONE
        )
        gross = (
            (candle.close - open_trade.entry_reference_price)
            * open_trade.quantity
            * direction_sign
        )
        if open_trade.intent.direction is TradeDirection.LONG:
            entry_slippage = open_trade.entry_price - open_trade.entry_reference_price
            estimated_exit = candle.close * (ONE - self.config.slippage_ratio)
            exit_slippage = candle.close - estimated_exit
        else:
            entry_slippage = open_trade.entry_reference_price - open_trade.entry_price
            estimated_exit = candle.close * (ONE + self.config.slippage_ratio)
            exit_slippage = estimated_exit - candle.close
        estimated_fees = (
            open_trade.entry_fee
            + estimated_exit * open_trade.quantity * self.config.fee_ratio
        )
        equity = (
            available_cash
            + gross
            - (entry_slippage + exit_slippage) * open_trade.quantity
            - estimated_fees
            - open_trade.funding_cost
        )
        signed_quantity = (
            open_trade.quantity
            if open_trade.intent.direction is TradeDirection.LONG
            else -open_trade.quantity
        )
        return EquityPoint(candle.timestamp, equity, signed_quantity)

    def _missed_opportunity_ledger(
        self,
        rejected_candidates: tuple[_RejectedFuturesCandidate, ...],
        candles: tuple[OHLCVCandle, ...],
        funding_points: tuple[MetricPoint, ...],
        mark_candles: tuple[OHLCVCandle, ...] = (),
    ) -> MissedOpportunityLedger:
        return MissedOpportunityLedger(
            records=tuple(
                self._missed_opportunity_record(
                    candidate,
                    candles,
                    funding_points,
                    mark_candles,
                )
                for candidate in rejected_candidates
            )
        )

    def _missed_opportunity_record(
        self,
        rejected: _RejectedFuturesCandidate,
        candles: tuple[OHLCVCandle, ...],
        funding_points: tuple[MetricPoint, ...],
        mark_candles: tuple[OHLCVCandle, ...] = (),
    ) -> MissedOpportunityRecord:
        trade = self._simulate_counterfactual_trade(
            rejected,
            candles,
            funding_points,
            mark_candles,
        )
        if trade is None:
            return self._insufficient_evidence_record(rejected)
        category = self._counterfactual_category(trade)
        improvement_candidate_id = (
            f"improvement:{rejected.intent.strategy_id.lower()}:"
            f"{rejected.intent.regime.lower()}:{rejected.intent.signal_id.lower()}"
            if category is MissedOpportunityCategory.BAD_BLOCK
            else None
        )
        return MissedOpportunityRecord(
            signal_id=rejected.intent.signal_id,
            strategy_id=rejected.intent.strategy_id,
            strategy_version=rejected.intent.strategy_version,
            regime=rejected.intent.regime,
            symbol=rejected.intent.symbol,
            market=USD_M_FUTURES,
            direction=rejected.intent.direction,
            rejected_at=rejected.intent.timestamp,
            blockers=rejected.blockers,
            entry_reason=rejected.intent.reason_codes,
            dge_status=rejected.intent.dge_status,
            pre_veto_observation_id=rejected.pre_veto_observation_id,
            counterfactual_result=category,
            forward_trade_outcome=trade.trade_outcome,
            forward_realized_r=trade.realized_r_multiple,
            forward_net_pnl=trade.net_pnl_usdt,
            improvement_candidate_id=improvement_candidate_id,
        )

    def _simulate_counterfactual_trade(
        self,
        rejected: _RejectedFuturesCandidate,
        candles: tuple[OHLCVCandle, ...],
        funding_points: tuple[MetricPoint, ...],
        mark_candles: tuple[OHLCVCandle, ...] = (),
    ) -> TradeRecord | None:
        if rejected.entry_index >= len(candles):
            return None
        entry_candle = candles[rejected.entry_index]
        entry_blockers = set(
            self._entry_blockers(
                rejected.intent,
                entry_candle,
                self.config.initial_cash_usdt,
            )
        )
        if entry_blockers - {"STOP_BEYOND_LIQUIDATION"}:
            return None
        open_trade = self._open_trade(rejected.intent, entry_candle)
        for index in range(rejected.entry_index, len(candles)):
            candle = candles[index]
            if mark_candles:
                self._mark_path_funding(open_trade, funding_points, mark_candles[index])
            else:
                self._apply_funding(open_trade, funding_points, candle.timestamp)
            self._update_excursions(open_trade, candle)
            open_trade.bars_held += 1
            decision = self._exit_decision(
                open_trade, candle, mark_candles[index] if mark_candles else None
            )
            if decision is not None:
                return self._close_trade(open_trade, candle.timestamp, decision)
        last = candles[-1]
        return self._close_trade(
            open_trade,
            last.timestamp,
            _ExitDecision(BacktestExitReason.END_OF_DATA, last.close),
        )

    @staticmethod
    def _counterfactual_category(trade: TradeRecord) -> MissedOpportunityCategory:
        if trade.realized_r_multiple > ZERO:
            return MissedOpportunityCategory.BAD_BLOCK
        if trade.realized_r_multiple < ZERO:
            return MissedOpportunityCategory.GOOD_BLOCK
        return MissedOpportunityCategory.NEUTRAL_BLOCK

    @staticmethod
    def _insufficient_evidence_record(
        rejected: _RejectedFuturesCandidate,
    ) -> MissedOpportunityRecord:
        intent = rejected.intent
        return MissedOpportunityRecord(
            signal_id=intent.signal_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            regime=intent.regime,
            symbol=intent.symbol,
            market=USD_M_FUTURES,
            direction=intent.direction,
            rejected_at=intent.timestamp,
            blockers=rejected.blockers,
            entry_reason=intent.reason_codes,
            dge_status=intent.dge_status,
            pre_veto_observation_id=rejected.pre_veto_observation_id,
            counterfactual_result=MissedOpportunityCategory.INSUFFICIENT_EVIDENCE,
        )

    def _buy_and_hold_return(self, candles: tuple[OHLCVCandle, ...]) -> float:
        first = candles[0]
        last = candles[-1]
        entry = first.open * (ONE + self.config.slippage_ratio)
        exit_price = last.close * (ONE - self.config.slippage_ratio)
        entry_cost = entry * (ONE + self.config.fee_ratio)
        exit_value = exit_price * (ONE - self.config.fee_ratio)
        return float((exit_value - entry_cost) / entry_cost)

    @staticmethod
    def _replay_prefix(
        dataset: RuntimeFuturesReplayDataset,
        length: int,
    ) -> RuntimeFuturesReplayDataset:
        latest_timestamp = dataset.candles[length - 1].timestamp
        series = {
            metric: tuple(
                point for point in points if point.timestamp <= latest_timestamp
            )
            for metric, points in dataset.derivatives.series.items()
        }
        derivatives = DerivativesDataset(
            symbol=dataset.symbol,
            as_of=dataset.derivatives.as_of,
            series=series,
            source=dataset.derivatives.source,
        )
        return RuntimeFuturesReplayDataset(
            symbol=dataset.symbol,
            candles=dataset.candles[:length],
            derivatives=derivatives,
            timeframe=dataset.timeframe,
        )

    @staticmethod
    def _reject(
        intent: FuturesBacktestIntent,
        blockers: tuple[str, ...],
        rejected: list[RejectedSignal],
        reason_counts: dict[str, int],
    ) -> None:
        rejected.append(RejectedSignal(intent.signal_id, intent.timestamp, blockers))
        for blocker in blockers:
            reason_counts[blocker] = reason_counts.get(blocker, 0) + 1

    @staticmethod
    def _closure_review(
        reason: BacktestExitReason,
        ignored_signals: int,
    ) -> ClosureReview:
        return ClosureReview(
            exit_reason=reason,
            lifecycle_error=None,
            stop_quality=(
                "LIQUIDATED"
                if reason is BacktestExitReason.LIQUIDATION
                else "PROTECTIVE"
                if reason is BacktestExitReason.HARD_STOP
                else "NOT_TRIGGERED"
            ),
            trailing_quality="NOT_APPLICABLE",
            ignored_signals=ignored_signals,
            htf_weakness=False,
            volatility_expansion=False,
            level_break=False,
            staged_exit_alternative="NOT_APPLICABLE",
            lesson_candidate=(
                "REVIEW_LIQUIDATION_BUFFER"
                if reason is BacktestExitReason.LIQUIDATION
                else "REVIEW_EXIT_CONTEXT"
            ),
        )

    @staticmethod
    def _event(
        event_type: str,
        identifier: str,
        timestamp: datetime,
        dataset_sha256: str,
    ) -> dict[str, object]:
        return {
            "event_type": event_type,
            "identifier": identifier,
            "timestamp": timestamp,
            "market": USD_M_FUTURES,
            "dataset_sha256": dataset_sha256,
            "execution_allowed": False,
        }
