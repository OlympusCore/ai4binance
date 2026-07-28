"""Deterministic domain contracts for decisions and live safety gates."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from typing import ClassVar


class Action(StrEnum):
    """Spot actions emitted by the deterministic decision layer."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


class Decision(StrEnum):
    """Validation-agent decision states from the platform contract."""

    MARKET = "MARKET"
    WAIT_FOR_RETEST = "WAIT_FOR_RETEST"
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_ONLY = "PAPER_ONLY"
    EXECUTION_NOT_ALLOWED = "EXECUTION_NOT_ALLOWED"
    LIVE_ORDER_BLOCKED = "LIVE_ORDER_BLOCKED"


class ExecutionStatus(StrEnum):
    """Execution permission states."""

    EXECUTION_NOT_ALLOWED = "EXECUTION_NOT_ALLOWED"
    LIVE_ORDER_BLOCKED = "LIVE_ORDER_BLOCKED"
    EXECUTION_ALLOWED = "EXECUTION_ALLOWED"


class SetupTier(StrEnum):
    """Validation-first setup quality tiers."""

    A_STAR = "A*"
    A = "A"
    B = "B"
    C = "C"
    NO_TRADE = "NO_TRADE"


class ValidationStatus(StrEnum):
    """Validation evidence available for a decision."""

    UNVALIDATED = "UNVALIDATED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    STAGED_CANDIDATE = "STAGED_CANDIDATE"
    PAPER_APPROVED = "PAPER_APPROVED"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    REJECTED = "REJECTED"


class CandidateStatus(StrEnum):
    """Research candidate lifecycle before deterministic validation."""

    WAIT_FOR_RETEST = "WAIT_FOR_RETEST"
    READY_FOR_RISK = "READY_FOR_RISK"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    REJECTED = "REJECTED"


DEFAULT_SIGNAL_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC)
ZERO = Decimal("0")


def _validate_score(field_name: str, value: float) -> None:
    """Validate the documented zero-to-100 score scale."""
    if not isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError(f"{field_name} must be finite and between 0 and 100")


@dataclass(frozen=True, slots=True)
class SignalSubScores:
    """Required deterministic score-family outputs on a zero-to-100 scale."""

    trend_score: float = 0.0
    volatility_score: float = 0.0
    momentum_score: float = 0.0
    volume_score: float = 0.0
    price_action_score: float = 0.0
    structure_score: float = 0.0
    fib_score: float = 0.0
    pattern_score: float = 0.0
    cycle_score: float = 0.0
    mtf_score: float = 0.0
    sentiment_score: float = 0.0
    risk_penalty_score: float = 0.0

    SCORE_FIELDS: ClassVar[tuple[str, ...]] = (
        "trend_score",
        "volatility_score",
        "momentum_score",
        "volume_score",
        "price_action_score",
        "structure_score",
        "fib_score",
        "pattern_score",
        "cycle_score",
        "mtf_score",
        "sentiment_score",
        "risk_penalty_score",
    )

    def __post_init__(self) -> None:
        """Reject non-finite and out-of-range family scores."""
        for score_name in self.SCORE_FIELDS:
            _validate_score(score_name, getattr(self, score_name))


@dataclass(frozen=True, slots=True)
class AgentScore:
    """Immutable score attached to one specialist agent."""

    agent_name: str
    score: float

    def __post_init__(self) -> None:
        """Validate agent identity and score range."""
        if not self.agent_name.strip():
            raise ValueError("agent_name cannot be empty")
        _validate_score("score", self.score)


@dataclass(frozen=True, slots=True)
class PriceZone:
    """Inclusive price zone without false single-price precision."""

    lower: Decimal
    upper: Decimal

    def __post_init__(self) -> None:
        """Reject negative or inverted zones."""
        if self.lower < ZERO or self.upper < ZERO:
            raise ValueError("price zone values cannot be negative")
        if self.lower > self.upper:
            raise ValueError("price zone lower cannot exceed upper")


@dataclass(frozen=True, slots=True)
class TradeCandidate:
    """Immutable strategy proposal with no execution authority."""

    candidate_id: str
    snapshot_id: str
    timestamp: datetime
    symbol: str
    timeframe: str
    action: Action
    setup_name: str
    status: CandidateStatus
    entry_zone: PriceZone
    invalidation_level: Decimal
    stop_loss: Decimal
    take_profit_levels: tuple[Decimal, ...]
    trailing_stop: Decimal
    atr: Decimal
    risk_reward: Decimal
    score: float
    confidence: float
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    inventory_action: str = "NONE"
    evidence: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate identity, geometry and Spot inventory semantics."""
        for field_name in (
            "candidate_id",
            "snapshot_id",
            "symbol",
            "timeframe",
            "setup_name",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("candidate timestamp must be timezone-aware")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.action not in {Action.BUY, Action.SELL}:
            raise ValueError("trade candidate action must be BUY or SELL")
        if self.action is Action.SELL and self.inventory_action == "NONE":
            raise ValueError("Spot SELL candidate requires inventory_action")
        for field_name in (
            "invalidation_level",
            "stop_loss",
            "trailing_stop",
            "atr",
            "risk_reward",
        ):
            if getattr(self, field_name) <= ZERO:
                raise ValueError(f"{field_name} must be positive")
        if not self.take_profit_levels or any(
            target <= ZERO for target in self.take_profit_levels
        ):
            raise ValueError("take_profit_levels must contain positive values")
        _validate_score("score", self.score)
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")
        entry = self.entry_price
        if self.action is Action.BUY:
            if self.stop_loss >= entry or any(
                target <= entry for target in self.take_profit_levels
            ):
                raise ValueError("BUY candidate geometry is invalid")
        elif self.stop_loss <= entry or any(
            target >= entry for target in self.take_profit_levels
        ):
            raise ValueError("SELL candidate geometry is invalid")
        if self.status is CandidateStatus.READY_FOR_RISK and self.blockers:
            raise ValueError("READY_FOR_RISK candidate cannot contain blockers")

    @property
    def entry_price(self) -> Decimal:
        """Return the deterministic midpoint used for risk calculations."""
        return (self.entry_zone.lower + self.entry_zone.upper) / Decimal("2")


@dataclass(frozen=True, slots=True)
class Signal:
    """Immutable, complete and auditable validation decision output."""

    symbol: str
    timeframes: tuple[str, ...]
    timestamp: datetime = DEFAULT_SIGNAL_TIMESTAMP
    snapshot_id: str = "no-snapshot"
    trade_id: str = "no-trade"
    market_type: str = "Spot"
    latest_price: Decimal | None = None
    regime: str = "UNKNOWN"
    htf_bias: str = "UNKNOWN"
    tactical_bias: str = "UNKNOWN"
    execution_bias: str = "UNKNOWN"
    action: Action = Action.NO_TRADE
    decision_state: Decision = Decision.NO_TRADE
    setup_name: str = "NONE"
    setup_tier: SetupTier = SetupTier.NO_TRADE
    sub_scores: SignalSubScores = field(default_factory=SignalSubScores)
    final_signal_score: float = 0.0
    confidence: float = 0.0
    agent_scores: tuple[AgentScore, ...] = field(default_factory=tuple)
    independent_confluence_count: int = 0
    support_zones: tuple[PriceZone, ...] = field(default_factory=tuple)
    resistance_zones: tuple[PriceZone, ...] = field(default_factory=tuple)
    entry_zone: PriceZone | None = None
    invalidation_level: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit_levels: tuple[Decimal, ...] = field(default_factory=tuple)
    trailing_stop: Decimal | None = None
    atr: Decimal | None = None
    risk_reward: Decimal | None = None
    size_usdt: Decimal = ZERO
    inventory_action: str = "NONE"
    reason_codes: tuple[str, ...] = ("DEFAULT_NO_TRADE",)
    reason_summary: str = "Default safe signal: NO_TRADE."
    supporting_evidence: tuple[str, ...] = field(default_factory=tuple)
    counter_evidence: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    execution_allowed: bool = False
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED

    def __post_init__(self) -> None:
        """Validate score, identity, Spot semantics and execution safety."""
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be empty")
        object.__setattr__(self, "symbol", normalized_symbol)
        if not self.timeframes or any(not item.strip() for item in self.timeframes):
            raise ValueError("timeframes must contain non-empty values")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.snapshot_id.strip() or not self.trade_id.strip():
            raise ValueError("snapshot_id and trade_id cannot be empty")
        if not self.reason_codes or any(not item.strip() for item in self.reason_codes):
            raise ValueError("reason_codes must contain deterministic values")
        _validate_score("final_signal_score", self.final_signal_score)
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")
        if self.independent_confluence_count < 0:
            raise ValueError("independent_confluence_count cannot be negative")
        self._validate_numeric_fields()
        self._validate_decision_consistency()
        self._validate_setup_tier()
        self._validate_spot_semantics()
        self._validate_execution_permission()

    def _validate_numeric_fields(self) -> None:
        """Reject impossible market and risk values without guessing intent."""
        for field_name in (
            "latest_price",
            "invalidation_level",
            "stop_loss",
            "trailing_stop",
            "atr",
            "risk_reward",
            "size_usdt",
        ):
            value = getattr(self, field_name)
            if value is not None and value < ZERO:
                raise ValueError(f"{field_name} cannot be negative")
        for take_profit in self.take_profit_levels:
            if take_profit < ZERO:
                raise ValueError("take_profit_levels cannot contain negative values")

    def _validate_spot_semantics(self) -> None:
        """Prevent naked-short semantics in Spot decisions."""
        is_inventory_sell = (
            self.action is Action.SELL
            and self.inventory_action.strip().upper() == "NONE"
        )
        if is_inventory_sell:
            raise ValueError("Spot SELL requires an explicit inventory_action")

    def _validate_decision_consistency(self) -> None:
        """Reject contradictory action and terminal decision combinations."""
        required_actions = {
            Decision.BUY: Action.BUY,
            Decision.SELL: Action.SELL,
            Decision.HOLD: Action.HOLD,
            Decision.NO_TRADE: Action.NO_TRADE,
        }
        required_action = required_actions.get(self.decision_state)
        if required_action is not None and self.action is not required_action:
            raise ValueError("action and decision_state are inconsistent")

    def _validate_setup_tier(self) -> None:
        """Ensure assigned tiers cannot exceed their documented score evidence."""
        minimum_scores = {
            SetupTier.A_STAR: 85.0,
            SetupTier.A: 78.0,
            SetupTier.B: 70.0,
            SetupTier.C: 60.0,
        }
        minimum_score = minimum_scores.get(self.setup_tier)
        if minimum_score is not None and self.final_signal_score < minimum_score:
            raise ValueError("setup_tier exceeds final_signal_score evidence")

    def _validate_execution_permission(self) -> None:
        """Require a complete, validated A-tier context before execution."""
        if not self.execution_allowed:
            return
        if self.action not in {Action.BUY, Action.SELL}:
            raise ValueError("only BUY or inventory SELL can allow execution")
        if self.decision_state not in {Decision.BUY, Decision.SELL, Decision.MARKET}:
            raise ValueError("decision_state cannot allow execution")
        if self.setup_tier not in {SetupTier.A_STAR, SetupTier.A}:
            raise ValueError("only A* or A setup tiers can allow execution")
        if self.validation_status is not ValidationStatus.LIVE_ELIGIBLE:
            raise ValueError("execution requires LIVE_ELIGIBLE validation status")
        if self.blockers:
            raise ValueError("execution cannot be allowed while blockers exist")
        missing_context = [
            field_name
            for field_name in (
                "latest_price",
                "entry_zone",
                "invalidation_level",
                "stop_loss",
                "trailing_stop",
                "atr",
                "risk_reward",
            )
            if getattr(self, field_name) is None
        ]
        if not self.take_profit_levels:
            missing_context.append("take_profit_levels")
        if self.size_usdt <= ZERO:
            missing_context.append("size_usdt")
        if missing_context:
            joined_context = ", ".join(missing_context)
            raise ValueError(f"execution context is incomplete: {joined_context}")


@dataclass(frozen=True, slots=True)
class LiveGateInput:
    """Every prerequisite required before a real Spot order is considered."""

    live_mode: bool = False
    auto_mode: bool = False
    allow_auto_live_orders: bool = False
    confirm_live: bool = False
    explicit_user_request: bool = False
    api_valid: bool = False
    account_status_valid: bool = False
    server_time_valid: bool = False
    exchange_info_valid: bool = False
    price_filter_valid: bool = False
    lot_size_valid: bool = False
    notional_filter_valid: bool = False
    tick_size_valid: bool = False
    step_size_valid: bool = False
    latest_spot_price_confirmed: bool = False
    spread_acceptable: bool = False
    slippage_acceptable: bool = False
    balances_known: bool = False
    inventory_known: bool = False
    no_conflicting_open_orders: bool = False
    latest_signal_exists: bool = False
    signal_not_expired: bool = False
    entry_not_missed: bool = False
    backtest_approved: bool = False
    walk_forward_approved: bool = False
    tuning_report_approved: bool = False
    oos_approved: bool = False
    risk_approved: bool = False
    strategy_promotion_approved: bool = False
    daily_loss_limit_clear: bool = False
    cooldown_clear: bool = False
    circuit_breaker_clear: bool = False
    decision_logged: bool = False
    order_preview_created: bool = False
    user_authorization_recorded: bool = False


@dataclass(frozen=True, slots=True)
class LiveGateResult:
    """Fail-closed live gate evaluation result."""

    status: ExecutionStatus
    blockers: tuple[str, ...]
