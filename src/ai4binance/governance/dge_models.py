"""Typed Decision Governance Engine contracts for advisory opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from ai4binance.governance.controls import ControlEvaluation
from ai4binance.governance.execution_authority import (
    BINANCE_MARKET_MANUAL_PROFILE,
    ExecutionAutomationMode,
    ExecutionSurface,
    authority_profile_for_surface,
)

ZERO = Decimal("0")
ONE = Decimal("1")
ONE_HUNDRED = Decimal("100")
DEFAULT_EVALUATION_TIMESTAMP_UTC = "1970-01-01T00:00:00Z"


def _normalize_market_type(market_type: str) -> str:
    normalized = market_type.strip().upper()
    if normalized in {"SPOT", "USD_M_FUTURES", "GOVERNANCE"}:
        return normalized
    raise ValueError("DGE market type must be SPOT or USD_M_FUTURES")


class DgeMarketAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class DgeDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    APPROVED_PAPER_ONLY = "APPROVED_PAPER_ONLY"
    WATCH_ONLY = "WATCH_ONLY"
    WAIT_FOR_RETEST = "WAIT_FOR_RETEST"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    NO_TRADE = "NO_TRADE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class DgeRuleSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HARD = "HARD"
    SOFT = "SOFT"
    CRITICAL = "CRITICAL"


class DgeSetupTier(StrEnum):
    A_STAR = "A*"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    C = "C"
    NO_TRADE = "NO_TRADE"


class EvidenceStatus(StrEnum):
    UNVALIDATED = "UNVALIDATED"
    IS_ONLY = "IS_ONLY"
    OOS_WEAK = "OOS_WEAK"
    OOS_STABLE = "OOS_STABLE"
    REGIME_VALIDATED = "REGIME_VALIDATED"
    PROMOTED = "PROMOTED"


class RulePromotionStatus(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class DgeQualityScores:
    """Deterministic score decomposition used before final governance status."""

    signal_score: Decimal = ZERO
    evidence_score: Decimal = ZERO
    data_quality_score: Decimal = ZERO
    mtf_score: Decimal = ZERO
    regime_score: Decimal = ZERO
    liquidity_score: Decimal = ZERO
    risk_score: Decimal = ZERO
    execution_score: Decimal = ZERO
    confidence_score: Decimal = ZERO
    governance_score: Decimal = ZERO

    def __post_init__(self) -> None:
        for name, value in (
            ("signal_score", self.signal_score),
            ("evidence_score", self.evidence_score),
            ("data_quality_score", self.data_quality_score),
            ("mtf_score", self.mtf_score),
            ("regime_score", self.regime_score),
            ("liquidity_score", self.liquidity_score),
            ("risk_score", self.risk_score),
            ("execution_score", self.execution_score),
            ("confidence_score", self.confidence_score),
            ("governance_score", self.governance_score),
        ):
            _require_score_0_100(name, value)


@dataclass(frozen=True, slots=True)
class DgeMarketPlan:
    """Structure-aware plan fields required for explainable governance."""

    entry: Decimal | None = None
    stop_loss: Decimal | None = None
    invalidation_level: Decimal | None = None
    take_profit_levels: tuple[Decimal, ...] = ()
    trailing_stop: Decimal | None = None
    size_usdt: Decimal | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("entry", self.entry),
            ("stop_loss", self.stop_loss),
            ("invalidation_level", self.invalidation_level),
            ("trailing_stop", self.trailing_stop),
            ("size_usdt", self.size_usdt),
        ):
            if value is not None and value <= ZERO:
                raise ValueError(f"DGE market plan {name} must be positive")
        if any(level <= ZERO for level in self.take_profit_levels):
            raise ValueError("DGE take-profit levels must be positive")
        if len(set(self.take_profit_levels)) != len(self.take_profit_levels):
            raise ValueError("DGE take-profit levels must be unique")


@dataclass(frozen=True, slots=True)
class DgePolicyVersions:
    """Replay-critical version identifiers stored with every DGE decision."""

    policy_version: str = "dge-policy-v1"
    config_version: str = "unconfigured"
    strategy_version: str = "unknown"
    parameter_version: str = "unknown"
    ontology_version: str = "unknown"

    def __post_init__(self) -> None:
        _require_nonblank_values(
            "DGE policy versions",
            (
                self.policy_version,
                self.config_version,
                self.strategy_version,
                self.parameter_version,
                self.ontology_version,
            ),
        )

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.policy_version,
            self.config_version,
            self.strategy_version,
            self.parameter_version,
            self.ontology_version,
        )


@dataclass(frozen=True, slots=True)
class DgeLayerEvaluation:
    """One governance layer result for audit and user-facing explanation."""

    layer_id: str
    status: DgeDecisionStatus
    primary_reason: str
    hard_blockers: tuple[str, ...] = ()
    soft_blockers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.layer_id.strip() or not self.primary_reason.strip():
            raise ValueError("DGE layer evaluation identity is required")
        _require_unique_nonblank("DGE layer hard blockers", self.hard_blockers)
        _require_unique_nonblank("DGE layer soft blockers", self.soft_blockers)
        _require_unique_nonblank("DGE layer evidence refs", self.evidence_refs)


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    """Advisory setup hypothesis before deterministic governance is applied."""

    candidate_id: str
    symbol: str
    market: str
    requested_action: DgeMarketAction
    setup_name: str
    score: Decimal
    confidence: Decimal
    risk_reward: Decimal | None = None
    capital_source: str = "UNKNOWN"
    primary_timeframe: str = "UNKNOWN"
    setup_tier: DgeSetupTier = DgeSetupTier.C
    mtf_bias: str = "UNKNOWN"
    regime: str = "UNKNOWN"
    market_plan: DgeMarketPlan = field(default_factory=DgeMarketPlan)
    evidence_refs: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.candidate_id, self.symbol, self.market, self.setup_name)
        ):
            raise ValueError("DGE candidate identity is required")
        object.__setattr__(self, "market", _normalize_market_type(self.market))
        _require_score_0_100("DGE candidate score", self.score)
        if not ZERO <= self.confidence <= ONE:
            raise ValueError("DGE candidate confidence must be between zero and one")
        if self.risk_reward is not None and self.risk_reward <= ZERO:
            raise ValueError("DGE candidate risk_reward must be positive")
        _require_nonblank_values(
            "DGE candidate market context",
            (self.primary_timeframe, self.mtf_bias, self.regime),
        )
        _require_unique_nonblank("DGE candidate evidence refs", self.evidence_refs)
        if self.execution_allowed:
            raise ValueError("DGE candidate cannot arrive with execution authority")


# Compatibility alias for existing DGE consumers.  The canonical contract name is
# DecisionCandidate; both names intentionally describe the same pre-governance type.
DgeTradeCandidate = DecisionCandidate


@dataclass(frozen=True, slots=True)
class DgeGovernanceContext:
    """Evidence switches required before a candidate can be more than watch-only."""

    context_id: str
    data_snapshot_id: str
    semantic_graph_id: str
    position_context_ref: str
    wallet_verified: bool = False
    snapshot_integrity_verified: bool = True
    data_quality_passed: bool = True
    required_timeframes_present: bool = True
    liquidity_approved: bool = True
    regime_compatible: bool = True
    mtf_aligned: bool = True
    structure_valid: bool = True
    negative_evidence_clear: bool = True
    oos_approved: bool = False
    risk_approved: bool = False
    validation_approved: bool = False
    execution_feasible: bool = False
    human_approval_recorded: bool = False
    position_dependency_bias_detected: bool = False
    no_new_capital_required: bool = True
    execution_surface: ExecutionSurface = ExecutionSurface.BINANCE_MARKET
    blockers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    rule_set_version: str = "dge-rules-v1"
    config_hash: str = "unconfigured"
    evaluation_timestamp_utc: str = DEFAULT_EVALUATION_TIMESTAMP_UTC
    policy_versions: DgePolicyVersions = field(default_factory=DgePolicyVersions)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        required = (
            self.context_id,
            self.data_snapshot_id,
            self.semantic_graph_id,
            self.position_context_ref,
            self.rule_set_version,
            self.config_hash,
            self.evaluation_timestamp_utc,
        )
        if any(not value.strip() for value in required):
            raise ValueError("DGE governance context identity is required")
        _require_unique_nonblank("DGE context blockers", self.blockers)
        _require_unique_nonblank("DGE context evidence refs", self.evidence_refs)
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE context cannot authorize execution")
        authority_profile_for_surface(self.execution_surface)


@dataclass(frozen=True, slots=True)
class DgeRuleResult:
    rule_id: str
    passed: bool
    severity: DgeRuleSeverity
    blockers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("DGE rule identity is required")
        _require_unique_nonblank("DGE rule blockers", self.blockers)
        _require_unique_nonblank("DGE rule evidence refs", self.evidence_refs)
        if self.passed and self.blockers:
            raise ValueError("passed DGE rules cannot have blockers")
        if not self.passed and not self.blockers:
            raise ValueError("failed DGE rules require blockers")


@dataclass(frozen=True, slots=True)
class TradeDecision:
    timestamp_utc: str = DEFAULT_EVALUATION_TIMESTAMP_UTC
    decision_id: str = ""
    candidate_id: str = ""
    symbol: str = ""
    market_type: str = "SPOT"
    requested_action: DgeMarketAction = DgeMarketAction.HOLD
    governed_action: DgeMarketAction = DgeMarketAction.HOLD
    governance_status: DgeDecisionStatus = DgeDecisionStatus.NO_TRADE
    setup_tier: DgeSetupTier = DgeSetupTier.C
    primary_timeframe: str = "UNKNOWN"
    mtf_bias: str = "UNKNOWN"
    regime: str = "UNKNOWN"
    quality_scores: DgeQualityScores = field(default_factory=DgeQualityScores)
    market_plan: DgeMarketPlan = field(default_factory=DgeMarketPlan)
    layer_evaluations: tuple[DgeLayerEvaluation, ...] = ()
    hard_blockers: tuple[str, ...] = ()
    soft_blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    required_changes: tuple[str, ...] = ()
    passed_rules: tuple[str, ...] = ()
    failed_rules: tuple[str, ...] = ()
    reason_summary: str = ""
    evidence_refs: tuple[str, ...] = ()
    control_evaluation: ControlEvaluation = field(default_factory=ControlEvaluation)
    rule_set_version: str = ""
    config_hash: str = ""
    data_snapshot_id: str = ""
    semantic_graph_id: str = ""
    policy_versions: DgePolicyVersions = field(default_factory=DgePolicyVersions)
    execution_surface: ExecutionSurface = ExecutionSurface.BINANCE_MARKET
    authority_profile_id: str = BINANCE_MARKET_MANUAL_PROFILE.authority_profile_id
    automation_mode: ExecutionAutomationMode = (
        ExecutionAutomationMode.HUMAN_HAND_MANUAL_ONLY
    )
    simulated_execution_allowed: bool = False
    paper_execution_allowed: bool = False
    auto_execution_allowed: bool = False
    autonomous_learning_allowed: bool = False
    bounded_self_improvement_allowed: bool = False
    simulated_spot_allowed: bool = False
    simulated_futures_allowed: bool = False
    live_execution_allowed: bool = False
    requires_manual_confirmation: bool = True
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def virtual_simulation_allowed(self) -> bool:
        """Return whether the decision may enter the virtual execution surface."""

        return self.simulated_execution_allowed

    @property
    def auto_simulation_allowed(self) -> bool:
        """Return whether the decision may autonomously simulate execution."""

        return self.auto_execution_allowed

    @property
    def binance_order_allowed(self) -> bool:
        """Return whether the decision may place an external Binance order."""

        return self.execution_allowed

    @property
    def live_order_allowed(self) -> bool:
        """Return whether the decision may place a live order."""

        return self.live_execution_allowed

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "market_type",
            _normalize_market_type(self.market_type),
        )
        required = (
            self.timestamp_utc,
            self.decision_id,
            self.candidate_id,
            self.symbol,
            self.market_type,
            self.primary_timeframe,
            self.mtf_bias,
            self.regime,
            self.reason_summary,
            self.rule_set_version,
            self.config_hash,
            self.data_snapshot_id,
            self.semantic_graph_id,
        )
        if any(not value.strip() for value in required):
            raise ValueError("governed decision identity is required")
        for values in (
            self.hard_blockers,
            self.soft_blockers,
            self.warnings,
            self.required_changes,
            self.passed_rules,
            self.failed_rules,
            self.evidence_refs,
        ):
            _require_unique_nonblank("governed decision lists", values)
        _require_unique_layer_ids(self.layer_evaluations)
        if self.hard_blockers and (
            self.paper_execution_allowed
            or self.simulated_execution_allowed
            or self.auto_execution_allowed
            or self.live_execution_allowed
        ):
            raise ValueError("hard-blocked decisions cannot execute")
        if self.governed_action is DgeMarketAction.NO_TRADE and (
            self.paper_execution_allowed
            or self.simulated_execution_allowed
            or self.auto_execution_allowed
            or self.live_execution_allowed
        ):
            raise ValueError("NO_TRADE decisions cannot execute")
        if self.governance_status in {
            DgeDecisionStatus.NO_TRADE,
            DgeDecisionStatus.DATA_UNAVAILABLE,
            DgeDecisionStatus.LOW_CONFIDENCE,
            DgeDecisionStatus.BLOCKED,
        } and (
            self.simulated_execution_allowed
            or self.autonomous_learning_allowed
            or self.bounded_self_improvement_allowed
            or self.simulated_spot_allowed
            or self.simulated_futures_allowed
            or self.paper_execution_allowed
            or self.auto_execution_allowed
            or self.live_execution_allowed
        ):
            raise ValueError("non-executable DGE statuses cannot execute")
        if self.simulated_execution_allowed and not self.paper_execution_allowed:
            raise ValueError(
                "simulated execution requires the paper execution compatibility flag"
            )
        if self.auto_execution_allowed and not self.simulated_execution_allowed:
            raise ValueError("auto simulation requires simulated execution allowance")
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE cannot authorize live execution")
        authority_profile = authority_profile_for_surface(self.execution_surface)
        if self.authority_profile_id != authority_profile.authority_profile_id:
            raise ValueError("DGE authority profile must match the execution surface")
        if self.automation_mode is not authority_profile.automation_mode:
            raise ValueError("DGE automation mode must match the execution surface")
        decision_profile_enabled = self.paper_execution_allowed
        if self.auto_execution_allowed != (
            authority_profile.auto_execution_allowed and decision_profile_enabled
        ):
            raise ValueError(
                "DGE autonomous simulation must match the execution surface profile"
            )
        if self.simulated_execution_allowed != (
            authority_profile.simulated_execution_allowed and decision_profile_enabled
        ):
            raise ValueError(
                "DGE simulated execution must match the execution surface profile"
            )
        if self.autonomous_learning_allowed != (
            authority_profile.autonomous_learning_allowed and decision_profile_enabled
        ):
            raise ValueError(
                "DGE autonomous learning must match the execution surface profile"
            )
        if self.bounded_self_improvement_allowed != (
            authority_profile.bounded_self_improvement_allowed
            and decision_profile_enabled
        ):
            raise ValueError(
                "DGE self-improvement must match the execution surface profile"
            )
        if self.simulated_spot_allowed != (
            authority_profile.simulated_spot_allowed and decision_profile_enabled
        ):
            raise ValueError(
                "DGE simulated Spot scope must match the execution surface profile"
            )
        if self.simulated_futures_allowed != (
            authority_profile.simulated_futures_allowed and decision_profile_enabled
        ):
            raise ValueError(
                "DGE simulated Futures scope must match the execution surface profile"
            )
        expected_manual = (
            authority_profile.requires_manual_confirmation
            if self.paper_execution_allowed
            else True
        )
        if self.requires_manual_confirmation is not expected_manual:
            raise ValueError(
                "DGE manual confirmation must match the execution surface policy"
            )


# Compatibility alias for existing DGE consumers.  The canonical contract name is
# TradeDecision; both names intentionally describe the same post-governance type.
GovernedDecision = TradeDecision


def deterministic_decision_id(
    candidate: DecisionCandidate,
    context: DgeGovernanceContext,
    failed_rules: tuple[str, ...],
) -> str:
    payload = "|".join(
        (
            candidate.candidate_id,
            candidate.symbol,
            candidate.market,
            candidate.requested_action.value,
            context.execution_surface.value,
            context.context_id,
            context.data_snapshot_id,
            context.semantic_graph_id,
            context.rule_set_version,
            context.config_hash,
            *context.policy_versions.as_tuple(),
            *failed_rules,
        )
    )
    return f"dge:{sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _require_nonblank_values(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _require_score_0_100(name: str, value: Decimal) -> None:
    if not ZERO <= value <= ONE_HUNDRED:
        raise ValueError(f"{name} must be between zero and 100")


def _require_unique_layer_ids(values: tuple[DgeLayerEvaluation, ...]) -> None:
    layer_ids = tuple(value.layer_id for value in values)
    if len(set(layer_ids)) != len(layer_ids):
        raise ValueError("DGE layer evaluations must have unique layer ids")
