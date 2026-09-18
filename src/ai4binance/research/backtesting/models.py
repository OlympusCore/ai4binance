"""Immutable backtest inputs, lifecycle records and performance reports."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from ai4binance.domain.research.virtual_runtime_attribution import (
    BacktestExitReason as BacktestExitReason,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    ClosedTradeAttribution as ClosedTradeAttribution,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeDirection as TradeDirection,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeEdgeAggregateView as TradeEdgeAggregateView,
)
from ai4binance.domain.research.virtual_runtime_attribution import (
    TradeEdgeLedger as TradeEdgeLedger,
)
from ai4binance.research.backtesting.liquidity import LiquidityStressConfig

ZERO = Decimal("0")


class VirtualMarketFunnelStage(StrEnum):
    """Deterministic virtual-market funnel stages for research telemetry."""

    DISCOVERED = "DISCOVERED"
    READY_FOR_RISK = "READY_FOR_RISK"
    RISK_PASS = "RISK_PASS"  # noqa: S105  # nosec B105
    VALIDATION_PASS = "VALIDATION_PASS"  # noqa: S105  # nosec B105
    DGE_PASS = "DGE_PASS"  # noqa: S105  # nosec B105
    VIRTUAL_ORDER = "VIRTUAL_ORDER"
    FILLED = "FILLED"
    CLOSED = "CLOSED"


class MissedOpportunityCategory(StrEnum):
    """Counterfactual classifications for rejected virtual candidates."""

    GOOD_BLOCK = "GOOD_BLOCK"
    BAD_BLOCK = "BAD_BLOCK"
    NEUTRAL_BLOCK = "NEUTRAL_BLOCK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class PreVetoOpportunityRecord:
    """Immutable opportunity evidence captured before any replay veto is applied."""

    observation_id: str
    signal_id: str
    snapshot_id: str
    strategy_id: str
    strategy_version: str
    regime: str
    symbol: str
    market: str
    direction: TradeDirection
    observed_at: datetime
    reference_price: Decimal
    stop_loss: Decimal
    take_profit_levels: tuple[Decimal, ...]
    entry_reason: tuple[str, ...]
    dge_status: str
    blockers: tuple[str, ...] = ()
    assessment_status: str = "PENDING_FORWARD_REVIEW"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.observation_id,
            self.signal_id,
            self.snapshot_id,
            self.strategy_id,
            self.strategy_version,
            self.regime,
            self.symbol,
            self.market,
            self.dge_status,
        ):
            if not value.strip():
                raise ValueError("pre-veto opportunity identity is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("pre-veto opportunity timestamp must be timezone-aware")
        if not self.take_profit_levels or not self.entry_reason:
            raise ValueError("pre-veto opportunity evidence is required")
        if min(self.reference_price, self.stop_loss, *self.take_profit_levels) <= ZERO:
            raise ValueError("pre-veto opportunity geometry must be positive")
        if self.blockers:
            raise ValueError("pre-veto opportunity cannot contain post-veto blockers")
        if self.assessment_status != "PENDING_FORWARD_REVIEW":
            raise ValueError("pre-veto opportunity must begin pending forward review")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("pre-veto opportunity cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class PreVetoOpportunityLedger:
    """Complete ordered inventory of opportunities observed before replay vetoes."""

    records: tuple[PreVetoOpportunityRecord, ...] = ()

    def __post_init__(self) -> None:
        identities = tuple(record.observation_id for record in self.records)
        if len(set(identities)) != len(identities):
            raise ValueError("pre-veto opportunity identities must be unique")


_UPSTREAM_FUNNEL_STAGES = frozenset(
    {
        VirtualMarketFunnelStage.DISCOVERED.value,
        VirtualMarketFunnelStage.READY_FOR_RISK.value,
        VirtualMarketFunnelStage.RISK_PASS.value,
        VirtualMarketFunnelStage.VALIDATION_PASS.value,
        VirtualMarketFunnelStage.DGE_PASS.value,
    }
)


def default_virtual_market_stage_counts() -> tuple[tuple[str, int], ...]:
    """Return the canonical zeroed virtual-market stage inventory."""

    return tuple((stage.value, 0) for stage in VirtualMarketFunnelStage)


@dataclass(frozen=True, slots=True)
class VirtualMarketFunnelTelemetry:
    """Ordered stage counts plus persisted blocker and rejection reason codes."""

    stage_counts: tuple[tuple[str, int], ...] = field(
        default_factory=default_virtual_market_stage_counts
    )
    reason_code_counts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        expected = tuple(stage.value for stage in VirtualMarketFunnelStage)
        actual = tuple(stage for stage, _count in self.stage_counts)
        if actual != expected:
            raise ValueError("virtual market stage counts must use the canonical order")
        if any(count < 0 for _stage, count in self.stage_counts):
            raise ValueError("virtual market stage counts must be non-negative")
        reason_codes = tuple(reason for reason, _count in self.reason_code_counts)
        if len(set(reason_codes)) != len(reason_codes):
            raise ValueError("virtual market reason codes must be unique")
        if any(not reason.strip() for reason in reason_codes):
            raise ValueError("virtual market reason codes cannot be blank")
        if any(count < 1 for _reason, count in self.reason_code_counts):
            raise ValueError("virtual market reason-code counts must be positive")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Deterministic Spot backtest assumptions."""

    initial_cash_usdt: Decimal = Decimal("1000")
    quantity: Decimal = Decimal("1")
    fee_ratio: Decimal = Decimal("0.001")
    slippage_ratio: Decimal = Decimal("0.0005")
    trailing_multiplier: Decimal = Decimal("1.5")
    tick_size: Decimal = Decimal("0.00000001")
    step_size: Decimal = Decimal("0.00000001")
    minimum_notional: Decimal = Decimal("5")
    liquidity_stress: LiquidityStressConfig | None = None

    def __post_init__(self) -> None:
        if self.initial_cash_usdt <= ZERO or self.quantity <= ZERO:
            raise ValueError("initial cash and quantity must be positive")
        if not ZERO < self.fee_ratio <= Decimal("0.01"):
            raise ValueError("fee_ratio must be between zero and 0.01")
        if not ZERO < self.slippage_ratio <= Decimal("0.02"):
            raise ValueError("slippage_ratio must be between zero and 0.02")
        if self.trailing_multiplier <= ZERO:
            raise ValueError("trailing_multiplier must be positive")
        if self.tick_size <= ZERO:
            raise ValueError("tick_size must be positive")
        if self.step_size <= ZERO:
            raise ValueError("step_size must be positive")
        if self.minimum_notional <= ZERO:
            raise ValueError("minimum_notional must be positive")


@dataclass(frozen=True, slots=True)
class BacktestIntent:
    """Long Spot entry proposed after the referenced candle has closed."""

    signal_id: str
    timestamp: datetime
    stop_loss: Decimal
    take_profit: Decimal
    atr: Decimal
    reason_codes: tuple[str, ...] = ("BACKTEST_SIGNAL",)
    take_profit_levels: tuple[Decimal, ...] = ()
    partial_exit_ratio: Decimal = Decimal("0.5")
    strategy_id: str = "UNSPECIFIED_STRATEGY"
    strategy_version: str = "1"
    strategy_config_version: str = "1"
    strategy_config_hash: str = "default"
    market: str = "SPOT"
    symbol: str = ""
    regime: str = "UNKNOWN"
    timeframe: str = ""
    snapshot_id: str = ""
    decision_id: str = ""
    opportunity_id: str = ""
    breakeven_trigger_r: Decimal | None = None
    trailing_atr_multiple: Decimal | None = None
    maximum_holding_bars: int | None = None
    entry_score: Decimal = ZERO
    evidence_score: Decimal = ZERO
    dge_status: str = "UNKNOWN"
    blocker_history: tuple[str, ...] = ()
    funnel_stages: tuple[str, ...] = (
        VirtualMarketFunnelStage.DISCOVERED.value,
        VirtualMarketFunnelStage.READY_FOR_RISK.value,
    )

    def __post_init__(self) -> None:
        if not self.signal_id.strip() or not self.reason_codes:
            raise ValueError("signal identity and reason codes are required")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("signal timestamp must be timezone-aware")
        if min(self.stop_loss, self.take_profit, self.atr) <= ZERO:
            raise ValueError("signal price geometry values must be positive")
        levels = self.targets
        if tuple(sorted(set(levels))) != levels:
            raise ValueError("take-profit levels must be unique and increasing")
        if not ZERO < self.partial_exit_ratio < Decimal("1"):
            raise ValueError("partial_exit_ratio must be between zero and one")
        for field_name in (
            "strategy_id",
            "strategy_version",
            "strategy_config_version",
            "strategy_config_hash",
            "market",
            "regime",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} is required")
        if self.breakeven_trigger_r is not None and self.breakeven_trigger_r <= ZERO:
            raise ValueError("breakeven_trigger_r must be positive when configured")
        if (
            self.trailing_atr_multiple is not None
            and self.trailing_atr_multiple <= ZERO
        ):
            raise ValueError("trailing_atr_multiple must be positive when configured")
        if self.maximum_holding_bars is not None and self.maximum_holding_bars < 1:
            raise ValueError("maximum_holding_bars must be positive when configured")
        if self.entry_score < ZERO:
            raise ValueError("entry_score must be non-negative")
        if self.evidence_score < ZERO:
            raise ValueError("evidence_score must be non-negative")
        if not self.dge_status.strip():
            raise ValueError("dge_status is required")
        if not self.opportunity_id.strip():
            object.__setattr__(
                self,
                "opportunity_id",
                f"opportunity:{self.signal_id}",
            )
        if len(set(self.blocker_history)) != len(self.blocker_history):
            raise ValueError("blocker_history must be unique")
        if any(not blocker.strip() for blocker in self.blocker_history):
            raise ValueError("blocker_history cannot contain blanks")
        if len(set(self.funnel_stages)) != len(self.funnel_stages):
            raise ValueError("funnel_stages must be unique")
        if not self.funnel_stages:
            raise ValueError("funnel_stages must not be empty")
        if any(stage not in _UPSTREAM_FUNNEL_STAGES for stage in self.funnel_stages):
            raise ValueError("funnel_stages contain unsupported virtual-market stages")

    @property
    def targets(self) -> tuple[Decimal, ...]:
        """Return explicit staged targets or the backward-compatible target."""
        return self.take_profit_levels or (self.take_profit,)

    @property
    def closed_trade_attribution(self) -> ClosedTradeAttribution:
        """Return deterministic closed-trade lineage from the intent metadata."""

        return ClosedTradeAttribution(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            strategy_config_version=self.strategy_config_version,
            strategy_config_hash=self.strategy_config_hash,
            market=self.market,
            symbol=self.symbol.strip().upper() or "UNKNOWN_SYMBOL",
            regime=self.regime,
            timeframe=self.timeframe.strip() or "UNKNOWN",
            snapshot_id=self.snapshot_id.strip() or self.signal_id,
            decision_id=self.decision_id.strip() or f"decision:{self.signal_id}",
            opportunity_id=self.opportunity_id,
        )


@dataclass(frozen=True, slots=True)
class RejectedSignal:
    """Signal that could not enter the event lifecycle."""

    signal_id: str
    timestamp: datetime
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClosureReview:
    """Auditable post-trade lifecycle assessment."""

    exit_reason: BacktestExitReason
    lifecycle_error: str | None
    stop_quality: str
    trailing_quality: str
    ignored_signals: int
    htf_weakness: bool
    volatility_expansion: bool
    level_break: bool
    staged_exit_alternative: str
    lesson_candidate: str

    @property
    def ignored_structure_break(self) -> bool:
        """Canonical closure-review name for ignored structural level breaks."""
        return self.level_break


@dataclass(frozen=True, slots=True)
class StagedExitRecord:
    """One partial take-profit fill inside a complete trade lifecycle."""

    timestamp: datetime
    price: Decimal
    quantity: Decimal
    fee_usdt: Decimal
    realized_pnl_usdt: Decimal


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """End-of-candle mark-to-market account equity."""

    timestamp: datetime
    equity_usdt: Decimal
    position_quantity: Decimal


@dataclass(frozen=True, slots=True)
class FalseBreakoutRecord:
    """Breakout-tagged entry closed by a protective stop."""

    signal_id: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    net_pnl_usdt: Decimal


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """Canonical closure attribution record for one completed virtual trade."""

    trade_id: str
    strategy_id: str
    strategy_version: str
    regime: str
    symbol: str
    market: str
    direction: TradeDirection
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    risk_at_entry: Decimal
    planned_rr: Decimal
    realized_rr: Decimal
    gross_pnl: Decimal
    fee_cost: Decimal
    slippage_cost: Decimal
    funding_cost: Decimal
    net_pnl: Decimal
    mfe: Decimal
    mae: Decimal
    entry_score: Decimal = ZERO
    evidence_score: Decimal = ZERO
    dge_status: str = "UNKNOWN"
    entry_reason: tuple[str, ...] = ("BACKTEST_SIGNAL",)
    exit_reason: BacktestExitReason = BacktestExitReason.END_OF_DATA
    blocker_history: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Complete fee-aware long Spot trade record."""

    trade_id: str
    signal_id: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_fee_usdt: Decimal
    exit_fee_usdt: Decimal
    net_pnl_usdt: Decimal
    return_ratio: Decimal
    exit_reason: BacktestExitReason
    closure_review: ClosureReview
    entry_reason: tuple[str, ...] = ("BACKTEST_SIGNAL",)
    staged_exits: tuple[StagedExitRecord, ...] = ()
    attribution: ClosedTradeAttribution = field(default_factory=ClosedTradeAttribution)
    gross_pnl_usdt: Decimal = ZERO
    fee_cost_usdt: Decimal = ZERO
    slippage_cost_usdt: Decimal = ZERO
    funding_cost_usdt: Decimal = ZERO
    realized_r_multiple: Decimal = ZERO
    maximum_favorable_excursion: Decimal = ZERO
    maximum_adverse_excursion: Decimal = ZERO
    holding_period: int = 0
    direction: TradeDirection = TradeDirection.LONG
    MAE: Decimal = ZERO
    MFE: Decimal = ZERO
    holding_time: int = 0
    gross_pnl: Decimal = ZERO
    fees: Decimal = ZERO
    slippage: Decimal = ZERO
    net_pnl: Decimal = ZERO
    risk_at_entry: Decimal = ZERO
    planned_rr: Decimal = ZERO
    entry_score: Decimal = ZERO
    evidence_score: Decimal = ZERO
    dge_status: str = "UNKNOWN"
    blocker_history: tuple[str, ...] = ()

    @property
    def trade_outcome(self) -> TradeOutcome:
        """Return the canonical learning-friendly closure attribution object."""

        return TradeOutcome(
            trade_id=self.trade_id,
            strategy_id=self.attribution.strategy_id,
            strategy_version=self.attribution.strategy_version,
            regime=self.attribution.regime,
            symbol=self.attribution.symbol,
            market=self.attribution.market,
            direction=self.direction,
            entry_time=self.entry_timestamp,
            exit_time=self.exit_timestamp,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            risk_at_entry=self.risk_at_entry,
            planned_rr=self.planned_rr,
            realized_rr=self.realized_r_multiple,
            gross_pnl=self.gross_pnl_usdt,
            fee_cost=self.fee_cost_usdt,
            slippage_cost=self.slippage_cost_usdt,
            funding_cost=self.funding_cost_usdt,
            net_pnl=self.net_pnl_usdt,
            mfe=self.maximum_favorable_excursion,
            mae=self.maximum_adverse_excursion,
            entry_score=self.entry_score,
            evidence_score=self.evidence_score,
            dge_status=self.dge_status,
            entry_reason=self.entry_reason,
            exit_reason=self.exit_reason,
            blocker_history=self.blocker_history,
        )


@dataclass(frozen=True, slots=True)
class MissedOpportunityRecord:
    """Forward-measured counterfactual result for one rejected candidate."""

    signal_id: str
    strategy_id: str
    strategy_version: str
    regime: str
    symbol: str
    market: str
    direction: TradeDirection
    rejected_at: datetime
    blockers: tuple[str, ...]
    entry_reason: tuple[str, ...]
    dge_status: str
    pre_veto_observation_id: str
    counterfactual_result: MissedOpportunityCategory
    forward_trade_outcome: TradeOutcome | None = None
    forward_realized_r: Decimal | None = None
    forward_net_pnl: Decimal | None = None
    improvement_candidate_id: str | None = None

    def __post_init__(self) -> None:
        if not self.pre_veto_observation_id.strip():
            raise ValueError(
                "missed opportunity requires pre-veto observation identity"
            )


@dataclass(frozen=True, slots=True)
class MissedOpportunityLedger:
    """Append-only counterfactual records for rejected virtual candidates."""

    records: tuple[MissedOpportunityRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    """Core strategy and performance-engine metrics for one market."""

    net_return: float
    max_drawdown: float
    profit_factor: float | None
    expectancy_usdt: float
    sharpe: float | None
    win_rate: float
    trade_count: int
    buy_and_hold_return: float
    market: str = "SPOT"
    sortino: float | None = None
    expectancy_r: float | None = None
    average_win_usdt: float | None = None
    average_loss_usdt: float | None = None
    exposure_ratio: float = 0.0
    turnover_ratio: float = 0.0
    fee_drag_ratio: float = 0.0
    slippage_drag_ratio: float = 0.0
    average_mae_r: float | None = None
    average_mfe_capture: float | None = None
    max_consecutive_losses: int = 0
    time_under_water_seconds: int = 0
    dge_saved_loss_usdt: float = 0.0
    dge_missed_profit_usdt: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.net_return,
            self.max_drawdown,
            self.expectancy_usdt,
            self.win_rate,
            self.buy_and_hold_return,
            self.exposure_ratio,
            self.turnover_ratio,
            self.fee_drag_ratio,
            self.slippage_drag_ratio,
            self.dge_saved_loss_usdt,
            self.dge_missed_profit_usdt,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("backtest metrics must be finite")


@dataclass(frozen=True, slots=True)
class PerformanceEngineReport:
    """Per-market performance outputs with anti-masking invariants."""

    spot_metrics: BacktestMetrics | None = None
    futures_metrics: BacktestMetrics | None = None
    combined_masking_allowed: bool = False
    system_acceptance_operator: str = "SPOT_PASS_AND_FUTURES_PASS"

    def __post_init__(self) -> None:
        if self.combined_masking_allowed:
            raise ValueError("combined market masking is not allowed")
        if self.system_acceptance_operator != "SPOT_PASS_AND_FUTURES_PASS":
            raise ValueError("performance engine operator must preserve anti-masking")


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Reproducible result with lifecycle and rejection evidence."""

    symbol: str
    timeframe: str
    started_at: datetime
    ended_at: datetime
    assumptions: BacktestConfig
    trades: tuple[TradeRecord, ...]
    rejected_signals: tuple[RejectedSignal, ...]
    no_trade_count: int
    metrics: BacktestMetrics
    audit_events: tuple[dict[str, object], ...] = field(default_factory=tuple)
    equity_curve: tuple[EquityPoint, ...] = field(default_factory=tuple)
    false_breakouts: tuple[FalseBreakoutRecord, ...] = field(default_factory=tuple)
    funnel_telemetry: VirtualMarketFunnelTelemetry = field(
        default_factory=VirtualMarketFunnelTelemetry
    )
    trade_edge_ledger: TradeEdgeLedger = field(default_factory=TradeEdgeLedger)
    trade_outcomes: tuple[TradeOutcome, ...] = field(default_factory=tuple)
    performance_engine_report: PerformanceEngineReport = field(
        default_factory=PerformanceEngineReport
    )
    missed_opportunity_ledger: MissedOpportunityLedger = field(
        default_factory=MissedOpportunityLedger
    )
    pre_veto_opportunity_ledger: PreVetoOpportunityLedger = field(
        default_factory=PreVetoOpportunityLedger
    )
