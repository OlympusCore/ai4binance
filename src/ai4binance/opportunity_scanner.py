"""Report-only Spot/Futures opportunity scanner and ranking contracts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum

from ai4binance.domain.opportunity_observation import OpportunityLifecycleState
from ai4binance.governance.controls import (
    ControlEligibility,
    ControlEvaluation,
    ControlResolutionAuthority,
    ControlSeverity,
    ControlSource,
    HardBlocker,
    SoftPenalty,
    build_control_evaluation,
)
from ai4binance.opportunity_policy import (
    DEFAULT_OPPORTUNITY_GRADE_POLICY,
    classify_opportunity_grade,
)
from ai4binance.opportunity_report import build_report_v2_payload
from ai4binance.scanners.orchestrator import ScannerOrchestrator
from ai4binance.universe.filters import (
    UniverseFilterResult,
    UniverseMarket,
    UniverseSymbol,
)
from ai4binance.universe.token_risk import assess_token_risk

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")


class OpportunityBlockerClass(StrEnum):
    DISCOVERY_EXCLUSION = "DISCOVERY_EXCLUSION"
    CONFIRMATION_GAP = "CONFIRMATION_GAP"
    VALIDATION_GAP = "VALIDATION_GAP"
    EXECUTION_BLOCKER = "EXECUTION_BLOCKER"
    SOFT_PENALTY = "SOFT_PENALTY"


class OpportunityVisibilityState(StrEnum):
    NO_VISIBLE_OPPORTUNITY = "NO_VISIBLE_OPPORTUNITY"
    WATCH_ONLY = "WATCH_ONLY"
    SETUP_FORMING = "SETUP_FORMING"
    CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class OpportunityFunnelStage(StrEnum):
    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    VIRTUAL_ELIGIBLE = "VIRTUAL_ELIGIBLE"


class OpportunityDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WATCH = "WATCH"
    WAIT_FOR_RETEST = "WAIT_FOR_RETEST"


@dataclass(frozen=True, slots=True)
class CandidateRankingPolicy:
    setup_quality_weight: Decimal = Decimal("0.25")
    evidence_quality_weight: Decimal = Decimal("0.20")
    regime_alignment_weight: Decimal = Decimal("0.15")
    liquidity_quality_weight: Decimal = Decimal("0.20")
    execution_quality_weight: Decimal = Decimal("0.10")
    reward_risk_quality_weight: Decimal = Decimal("0.10")
    soft_penalty_weight: Decimal = Decimal("1.00")
    maximum_selected_spot_candidates: int = 3
    maximum_selected_futures_candidates: int = 3

    def __post_init__(self) -> None:
        weights = (
            self.setup_quality_weight,
            self.evidence_quality_weight,
            self.regime_alignment_weight,
            self.liquidity_quality_weight,
            self.execution_quality_weight,
            self.reward_risk_quality_weight,
            self.soft_penalty_weight,
        )
        if any(not value.is_finite() or value < ZERO for value in weights):
            raise ValueError(
                "candidate ranking weights must be finite and non-negative"
            )
        if sum(
            (
                self.setup_quality_weight,
                self.evidence_quality_weight,
                self.regime_alignment_weight,
                self.liquidity_quality_weight,
                self.execution_quality_weight,
                self.reward_risk_quality_weight,
            ),
            ZERO,
        ) != Decimal("1.00"):
            raise ValueError("candidate ranking component weights must sum to 1.00")
        if (
            self.maximum_selected_spot_candidates < 1
            or self.maximum_selected_futures_candidates < 1
        ):
            raise ValueError("candidate ranking selection limits must be positive")


CONFIRMATION_GAP_BLOCKERS = frozenset(
    {
        "ENTRY_TRIGGER_MISSING",
        "SETUP_EVIDENCE_UNAVAILABLE",
        "TRADE_PLAN_INCOMPLETE",
        "VOLUME_CONFIRMATION_MISSING",
        "STRUCTURE_CONFIRMATION_REQUIRED",
        "HTF_CONFIRMATION_REQUIRED",
    }
)

VALIDATION_GAP_BLOCKERS = frozenset(
    {
        "OOS_NOT_COMPLETE",
        "PAPER_VALIDATION_PENDING",
        "PARAMETER_PROMOTION_PENDING",
        "VALIDATION_REQUIRED",
        "VALIDATION_GATE_REQUIRED",
    }
)

EXECUTION_AUTHORITY_BLOCKERS = frozenset(
    {
        "LIVE_ORDER_BLOCKED",
        "NO_READY_CANDIDATE",
    }
)

EXECUTION_ONLY_BLOCKERS = frozenset(
    {
        *CONFIRMATION_GAP_BLOCKERS,
        *VALIDATION_GAP_BLOCKERS,
        *EXECUTION_AUTHORITY_BLOCKERS,
    }
)

DATA_QUALITY_REJECTION_BLOCKERS = frozenset({"DATA_INCOMPLETE"})

LIQUIDITY_REJECTION_BLOCKERS = frozenset(
    {
        "INSUFFICIENT_24H_VOLUME",
        "INSUFFICIENT_ORDER_BOOK_DEPTH",
        "OPEN_INTEREST_INSUFFICIENT",
    }
)

SPREAD_REJECTION_BLOCKERS = frozenset({"SPREAD_EXCEEDS_LIMIT"})

TOKEN_RISK_REJECTION_BLOCKERS = frozenset(
    {
        "STABLECOIN_BASE_EXCLUDED",
        "WRAPPED_TOKEN_EXCLUDED",
        "LEVERAGED_TOKEN_EXCLUDED",
    }
)


@dataclass(frozen=True, slots=True)
class OpportunityFunnelMetrics:
    total_universe: int
    classified: int
    discovered: int
    qualified: int
    virtual_eligible: int
    discovery_eligible: int
    market_quality_pass: int
    setup_detected: int
    b_or_higher: int
    b_plus_or_higher: int
    trade_plan_complete: int
    validation_passed: int
    paper_eligible: int
    accepted: int
    rejected: int
    watch: int
    wait_for_retest: int
    symbols_scanned: int = 0
    raw_candidates: int = 0
    data_quality_rejected: int = 0
    liquidity_rejected: int = 0
    spread_rejected: int = 0
    token_risk_rejected: int = 0
    watch_only: int = 0
    confirmation_pending: int = 0
    paper_executed: int = 0
    raw_symbols_scanned: int = 0
    eligible_symbols: int = 0
    excluded_symbols: int = 0
    forming_setups: int = 0
    qualified_setups: int = 0
    confirmed_setups: int = 0
    watch_only_candidates: int = 0
    risk_rejected_candidates: int = 0
    validation_rejected_candidates: int = 0
    governance_rejected_candidates: int = 0
    virtual_eligible_candidates: int = 0
    virtual_executed_candidates: int = 0
    expired_candidates: int = 0
    invalidated_candidates: int = 0
    excluded_symbols_by_reason: tuple[tuple[str, int], ...] = ()
    reason_code_counts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.total_universe,
            self.classified,
            self.discovered,
            self.qualified,
            self.virtual_eligible,
            self.discovery_eligible,
            self.market_quality_pass,
            self.setup_detected,
            self.b_or_higher,
            self.b_plus_or_higher,
            self.trade_plan_complete,
            self.validation_passed,
            self.paper_eligible,
            self.accepted,
            self.rejected,
            self.watch,
            self.wait_for_retest,
            self.symbols_scanned,
            self.raw_candidates,
            self.data_quality_rejected,
            self.liquidity_rejected,
            self.spread_rejected,
            self.token_risk_rejected,
            self.watch_only,
            self.confirmation_pending,
            self.paper_executed,
            self.raw_symbols_scanned,
            self.eligible_symbols,
            self.excluded_symbols,
            self.forming_setups,
            self.qualified_setups,
            self.confirmed_setups,
            self.watch_only_candidates,
            self.risk_rejected_candidates,
            self.validation_rejected_candidates,
            self.governance_rejected_candidates,
            self.virtual_eligible_candidates,
            self.virtual_executed_candidates,
            self.expired_candidates,
            self.invalidated_candidates,
        )
        if any(value < 0 for value in values):
            raise ValueError("opportunity funnel metrics must be non-negative")
        if self.classified > self.total_universe:
            raise ValueError("classified count cannot exceed total universe")
        for counts in (self.excluded_symbols_by_reason, self.reason_code_counts):
            names = tuple(name for name, _count in counts)
            if (
                len(set(names)) != len(names)
                or any(not name.strip() for name in names)
                or any(count < 1 for _name, count in counts)
            ):
                raise ValueError("opportunity funnel reason counts are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "total_universe": self.total_universe,
            "classified": self.classified,
            "discovered": self.discovered,
            "qualified": self.qualified,
            "virtual_eligible": self.virtual_eligible,
            "discovery_eligible": self.discovery_eligible,
            "market_quality_pass": self.market_quality_pass,
            "setup_detected": self.setup_detected,
            "b_or_higher": self.b_or_higher,
            "b_plus_or_higher": self.b_plus_or_higher,
            "trade_plan_complete": self.trade_plan_complete,
            "validation_passed": self.validation_passed,
            "paper_eligible": self.paper_eligible,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "watch": self.watch,
            "wait_for_retest": self.wait_for_retest,
            "symbols_scanned": self.symbols_scanned,
            "raw_candidates": self.raw_candidates,
            "data_quality_rejected": self.data_quality_rejected,
            "liquidity_rejected": self.liquidity_rejected,
            "spread_rejected": self.spread_rejected,
            "token_risk_rejected": self.token_risk_rejected,
            "watch_only": self.watch_only,
            "confirmation_pending": self.confirmation_pending,
            "paper_executed": self.paper_executed,
            "raw_symbols_scanned": self.raw_symbols_scanned,
            "eligible_symbols": self.eligible_symbols,
            "excluded_symbols": self.excluded_symbols,
            "excluded_symbols_by_reason": dict(self.excluded_symbols_by_reason),
            "forming_setups": self.forming_setups,
            "qualified_setups": self.qualified_setups,
            "confirmed_setups": self.confirmed_setups,
            "watch_only_candidates": self.watch_only_candidates,
            "risk_rejected_candidates": self.risk_rejected_candidates,
            "validation_rejected_candidates": self.validation_rejected_candidates,
            "governance_rejected_candidates": self.governance_rejected_candidates,
            "virtual_eligible_candidates": self.virtual_eligible_candidates,
            "virtual_executed_candidates": self.virtual_executed_candidates,
            "expired_candidates": self.expired_candidates,
            "invalidated_candidates": self.invalidated_candidates,
            "reason_code_counts": dict(self.reason_code_counts),
        }


@dataclass(frozen=True, slots=True)
class OpportunityScanCandidate:
    symbol: str
    market: str
    rank_score: Decimal
    accepted: bool
    blockers: tuple[str, ...]
    liquidity_score: Decimal
    depth_score: Decimal
    spread_score: Decimal
    strategy_id: str = "SCAN_COMPATIBILITY_PREFILTER"
    regime: str = "UNKNOWN"
    signal_score: Decimal = ZERO
    evidence_score: Decimal = ZERO
    risk_reward: Decimal | None = None
    invalidation: str = "NOT_SET"
    expected_holding_period: str = "UNKNOWN"
    market_quality_score: Decimal = ZERO
    opportunity_score: Decimal = ZERO
    discovery_grade: str = "D"
    research_confidence: Decimal = ZERO
    research_state: str = "VALIDATION_REQUIRED"
    lifecycle_state: str = OpportunityLifecycleState.DEVELOPING.value
    opportunity_key: str = ""
    opportunity_instance_id: str = ""
    snapshot_id: str = ""
    timeframe: str = "UNSPECIFIED"
    setup_id: str = "SETUP_UNAVAILABLE"
    direction: str = "WATCH_ONLY"
    discovery_exclusions: tuple[str, ...] = ()
    confirmation_gaps: tuple[str, ...] = ()
    validation_gaps: tuple[str, ...] = ()
    execution_blockers: tuple[str, ...] = ()
    hard_blockers: tuple[str, ...] = ()
    soft_penalties: tuple[str, ...] = ()
    visibility_state: str = OpportunityVisibilityState.WATCH_ONLY.value
    execution_state: str = "NO_TRADE"
    why_visible: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()
    next_safe_action: str = "KEEP_RESEARCH_RADAR_RUNNING"
    upgrade_condition: str = "Clear confirmation gaps and refresh validation evidence."
    invalidation_condition: str = (
        "Discovery exclusion, stale data, or critical risk evidence appears."
    )
    base_score: Decimal = ZERO
    total_penalty: Decimal = ZERO
    adjusted_score: Decimal = ZERO
    eligibility: str = ControlEligibility.WATCH_ONLY.value
    control_evaluation: ControlEvaluation = field(default_factory=ControlEvaluation)
    derivatives_score: Decimal = ZERO
    structure_score: Decimal = ZERO
    momentum_score: Decimal = ZERO
    volume_score: Decimal = ZERO
    volatility_score: Decimal = ZERO
    setup_score: Decimal = ZERO
    multi_timeframe_score: Decimal = ZERO
    evidence_quality_score: Decimal = ZERO
    regime_alignment_score: Decimal = ZERO
    execution_quality_score: Decimal = ZERO
    reward_risk_quality_score: Decimal = ZERO
    raw_discovery_score: Decimal = ZERO
    trade_plan_complete: bool = False
    validation_passed: bool = False
    paper_eligible: bool = False
    deep_setup_evidence_available: bool = False
    asset_risk_status: str = "PASSED"
    funnel_stage: str = OpportunityFunnelStage.DISCOVERED.value
    disposition: str = OpportunityDisposition.WATCH.value
    ranking_eligible: bool = False
    selected_for_virtual_cycle: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.symbol.strip()
            or not self.market.strip()
            or not self.strategy_id.strip()
            or not self.regime.strip()
            or not self.invalidation.strip()
            or not self.expected_holding_period.strip()
        ):
            raise ValueError("opportunity scan candidate identity is required")
        discovery_exclusions = self.discovery_exclusions or self.hard_blockers
        execution_blockers = self.execution_blockers
        confirmation_gaps = self.confirmation_gaps or tuple(
            blocker
            for blocker in execution_blockers
            if blocker in CONFIRMATION_GAP_BLOCKERS
        )
        validation_gaps = self.validation_gaps or tuple(
            blocker
            for blocker in execution_blockers
            if blocker in VALIDATION_GAP_BLOCKERS
        )
        hard_blockers = self.hard_blockers or discovery_exclusions
        blockers = self.blockers or tuple(
            dict.fromkeys((*discovery_exclusions, *execution_blockers))
        )
        if self.discovery_exclusions != discovery_exclusions:
            object.__setattr__(self, "discovery_exclusions", discovery_exclusions)
        if self.confirmation_gaps != confirmation_gaps:
            object.__setattr__(self, "confirmation_gaps", confirmation_gaps)
        if self.validation_gaps != validation_gaps:
            object.__setattr__(self, "validation_gaps", validation_gaps)
        if self.hard_blockers != hard_blockers:
            object.__setattr__(self, "hard_blockers", hard_blockers)
        if self.blockers != blockers:
            object.__setattr__(self, "blockers", blockers)
        if not self.market_quality_score:
            object.__setattr__(self, "market_quality_score", self.base_score)
        if not self.signal_score:
            object.__setattr__(self, "signal_score", self.setup_score)
        if not self.evidence_score:
            object.__setattr__(self, "evidence_score", self.evidence_quality_score)
        if not self.raw_discovery_score:
            object.__setattr__(self, "raw_discovery_score", self.opportunity_score)
        if self.visibility_state == OpportunityVisibilityState.WATCH_ONLY.value:
            object.__setattr__(
                self,
                "visibility_state",
                _visibility_state(
                    discovery_exclusions=discovery_exclusions,
                    confirmation_gaps=confirmation_gaps,
                    validation_gaps=validation_gaps,
                    opportunity_score=self.opportunity_score,
                ).value,
            )
        if not self.why_visible and not discovery_exclusions:
            object.__setattr__(
                self,
                "why_visible",
                _why_visible(
                    market_quality_score=self.market_quality_score,
                    setup_score=self.setup_score,
                    liquidity_score=self.liquidity_score,
                    depth_score=self.depth_score,
                    spread_score=self.spread_score,
                ),
            )
        if not self.supporting_evidence and not discovery_exclusions:
            object.__setattr__(
                self,
                "supporting_evidence",
                _supporting_evidence(
                    market_quality_score=self.market_quality_score,
                    setup_score=self.setup_score,
                    evidence_quality_score=self.evidence_quality_score,
                    deep_setup_evidence_available=self.deep_setup_evidence_available,
                ),
            )
        if not self.counter_evidence:
            object.__setattr__(
                self,
                "counter_evidence",
                tuple(dict.fromkeys((*confirmation_gaps, *validation_gaps))),
            )
        if self.next_safe_action == "KEEP_RESEARCH_RADAR_RUNNING":
            object.__setattr__(
                self,
                "next_safe_action",
                _next_safe_action(
                    discovery_exclusions=discovery_exclusions,
                    confirmation_gaps=confirmation_gaps,
                    validation_gaps=validation_gaps,
                ),
            )
        if not self.snapshot_id:
            object.__setattr__(
                self, "snapshot_id", f"universe:{self.market}:{self.symbol}"
            )
        if not self.opportunity_key:
            object.__setattr__(
                self,
                "opportunity_key",
                ":".join(
                    (
                        self.market,
                        self.symbol,
                        self.timeframe,
                        self.setup_id,
                        self.direction,
                    )
                ),
            )
        if not self.opportunity_instance_id:
            object.__setattr__(
                self,
                "opportunity_instance_id",
                f"{self.opportunity_key}:{self.snapshot_id}",
            )
        virtual_eligible = (
            not discovery_exclusions and not confirmation_gaps and not validation_gaps
        )
        if self.funnel_stage == OpportunityFunnelStage.DISCOVERED.value:
            object.__setattr__(
                self,
                "funnel_stage",
                _funnel_stage(
                    discovery_exclusions=discovery_exclusions,
                    confirmation_gaps=confirmation_gaps,
                    validation_gaps=validation_gaps,
                ).value,
            )
        if self.disposition == OpportunityDisposition.WATCH.value:
            object.__setattr__(
                self,
                "disposition",
                _disposition(
                    discovery_exclusions=discovery_exclusions,
                    confirmation_gaps=confirmation_gaps,
                    validation_gaps=validation_gaps,
                    virtual_eligible=virtual_eligible,
                ).value,
            )
        numeric = (
            self.rank_score,
            self.liquidity_score,
            self.depth_score,
            self.spread_score,
            self.signal_score,
            self.evidence_score,
            self.derivatives_score,
            self.market_quality_score,
            self.opportunity_score,
            self.research_confidence,
            self.structure_score,
            self.momentum_score,
            self.volume_score,
            self.volatility_score,
            self.setup_score,
            self.multi_timeframe_score,
            self.evidence_quality_score,
            self.regime_alignment_score,
            self.execution_quality_score,
            self.reward_risk_quality_score,
            self.raw_discovery_score,
            self.base_score,
            self.total_penalty,
            self.adjusted_score,
        )
        if any(
            not value.is_finite() or value < ZERO or value > ONE_HUNDRED
            for value in numeric
        ):
            raise ValueError("opportunity scan scores must be between 0 and 100")
        if self.risk_reward is not None and (
            not self.risk_reward.is_finite() or self.risk_reward <= ZERO
        ):
            raise ValueError("opportunity scan risk/reward must be positive when set")
        if self.accepted == bool(discovery_exclusions):
            raise ValueError("opportunity discovery acceptance and exclusions disagree")
        if self.control_evaluation.active_hard_blocker_count and self.accepted:
            raise ValueError("excluded scan candidate cannot be accepted")
        if self.execution_allowed or self.paper_eligible:
            raise ValueError("opportunity scan candidate cannot authorize execution")
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity scan candidate cannot authorize execution")

    @property
    def discovery_eligible(self) -> bool:
        return self.accepted

    @property
    def qualified(self) -> bool:
        return self.funnel_stage in {
            OpportunityFunnelStage.QUALIFIED.value,
            OpportunityFunnelStage.VIRTUAL_ELIGIBLE.value,
        }

    @property
    def virtual_eligible(self) -> bool:
        return self.funnel_stage == OpportunityFunnelStage.VIRTUAL_ELIGIBLE.value

    @property
    def execution_eligible(self) -> bool:
        return False

    @property
    def blocker_taxonomy(self) -> dict[str, tuple[str, ...]]:
        return {
            OpportunityBlockerClass.DISCOVERY_EXCLUSION.value: (
                self.discovery_exclusions
            ),
            OpportunityBlockerClass.CONFIRMATION_GAP.value: self.confirmation_gaps,
            OpportunityBlockerClass.VALIDATION_GAP.value: self.validation_gaps,
            OpportunityBlockerClass.EXECUTION_BLOCKER.value: self.execution_blockers,
            OpportunityBlockerClass.SOFT_PENALTY.value: self.soft_penalties,
        }


@dataclass(frozen=True, slots=True)
class OpportunityScanReport:
    command: str
    market: str
    candidates: tuple[OpportunityScanCandidate, ...]
    blockers: tuple[str, ...]
    funnel: OpportunityFunnelMetrics = field(
        default_factory=lambda: OpportunityFunnelMetrics(
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
    )
    snapshot_id: str = "opportunity-scan:empty"
    status: str = "RUNNING_WITH_BLOCKERS"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def accepted_symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.candidates if item.accepted)

    @property
    def rejected_symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.candidates if not item.accepted)

    @property
    def top_opportunities(self) -> tuple[OpportunityScanCandidate, ...]:
        return tuple(
            item
            for item in self.candidates
            if item.discovery_grade in {"A", "B+"} and item.accepted
        )[:5]

    @property
    def developing_setups(self) -> tuple[OpportunityScanCandidate, ...]:
        return tuple(
            item
            for item in self.candidates
            if item.accepted and item.discovery_grade in {"B", "B-", "C"}
        )[:10]

    @property
    def rejected_or_lost_opportunities(self) -> tuple[OpportunityScanCandidate, ...]:
        return tuple(item for item in self.candidates if not item.accepted)

    def __post_init__(self) -> None:
        if self.status not in {"READY", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("opportunity scan report status is invalid")
        if not self.snapshot_id.strip():
            raise ValueError("opportunity scan report snapshot is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity scan report cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        ranked_candidates: list[dict[str, object]] = [
            {
                "symbol": item.symbol,
                "market": item.market,
                "opportunity_key": item.opportunity_key,
                "opportunity_instance_id": item.opportunity_instance_id,
                "snapshot_id": item.snapshot_id,
                "timeframe": item.timeframe,
                "setup_id": item.setup_id,
                "direction": item.direction,
                "strategy_id": item.strategy_id,
                "regime": item.regime,
                "rank_score": item.rank_score,
                "rank_score_basis": "DETERMINISTIC_CANDIDATE_RANK_V1",
                "signal_score": item.signal_score,
                "evidence_score": item.evidence_score,
                "risk_reward": item.risk_reward,
                "invalidation": item.invalidation,
                "expected_holding_period": item.expected_holding_period,
                "market_quality_score": item.market_quality_score,
                "opportunity_score": item.opportunity_score,
                "raw_discovery_score": item.raw_discovery_score,
                "discovery_grade": item.discovery_grade,
                "research_confidence": item.research_confidence,
                "research_state": item.research_state,
                "lifecycle_state": item.lifecycle_state,
                "visibility_state": item.visibility_state,
                "execution_state": item.execution_state,
                "funnel_stage": item.funnel_stage,
                "disposition": item.disposition,
                "accepted": item.accepted,
                "discovery_eligible": item.discovery_eligible,
                "qualified": item.qualified,
                "virtual_eligible": item.virtual_eligible,
                "ranking_eligible": item.ranking_eligible,
                "selected_for_virtual_cycle": item.selected_for_virtual_cycle,
                "execution_eligible": item.execution_eligible,
                "paper_eligible": item.paper_eligible,
                "deep_setup_evidence_available": item.deep_setup_evidence_available,
                "blockers": item.blockers,
                "blocker_taxonomy": item.blocker_taxonomy,
                "discovery_exclusions": item.discovery_exclusions,
                "confirmation_gaps": item.confirmation_gaps,
                "validation_gaps": item.validation_gaps,
                "promotion_requirements": item.validation_gaps,
                "execution_blockers": item.execution_blockers,
                "hard_blockers": item.hard_blockers,
                "soft_penalties": item.soft_penalties,
                "why_visible": item.why_visible,
                "supporting_evidence": item.supporting_evidence,
                "counter_evidence": item.counter_evidence,
                "next_safe_action": item.next_safe_action,
                "upgrade_condition": item.upgrade_condition,
                "invalidation_condition": item.invalidation_condition,
                "base_score": item.base_score,
                "total_penalty": item.total_penalty,
                "adjusted_score": item.adjusted_score,
                "eligibility": item.eligibility,
                "control_evaluation": item.control_evaluation.to_payload(),
                "liquidity_score": item.liquidity_score,
                "depth_score": item.depth_score,
                "spread_score": item.spread_score,
                "derivatives_score": item.derivatives_score,
                "structure_score": item.structure_score,
                "momentum_score": item.momentum_score,
                "volume_score": item.volume_score,
                "volatility_score": item.volatility_score,
                "setup_score": item.setup_score,
                "multi_timeframe_score": item.multi_timeframe_score,
                "evidence_quality_score": item.evidence_quality_score,
                "regime_alignment_score": item.regime_alignment_score,
                "execution_quality_score": item.execution_quality_score,
                "reward_risk_quality_score": item.reward_risk_quality_score,
                "trade_plan_complete": item.trade_plan_complete,
                "validation_passed": item.validation_passed,
                "token_risk_status": item.asset_risk_status,
                "execution_allowed": False,
                "promotion_status": item.promotion_status,
                "live_eligibility_status": item.live_eligibility_status,
            }
            for item in self.candidates
        ]
        return {
            "command": self.command,
            "report_version": "2.0",
            "status": self.status,
            "market": self.market,
            "snapshot_id": self.snapshot_id,
            "funnel": self.funnel.to_payload(),
            "accepted_symbols": self.accepted_symbols,
            "rejected_symbols": self.rejected_symbols,
            "top_opportunity_symbols": tuple(
                item.symbol for item in self.top_opportunities
            ),
            "developing_setup_symbols": tuple(
                item.symbol for item in self.developing_setups
            ),
            "rejected_or_lost_symbols": tuple(
                item.symbol for item in self.rejected_or_lost_opportunities
            ),
            "ranked_candidates": ranked_candidates,
            "opportunity_report_v2": build_report_v2_payload(
                command=self.command,
                status=self.status,
                market=self.market,
                snapshot_id=self.snapshot_id,
                ranked_candidates=ranked_candidates,
                blockers=self.blockers,
            ),
            "blockers": self.blockers,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_opportunity_scan_report(
    command: str,
    *,
    spot_symbols: tuple[UniverseSymbol, ...] = (),
    futures_symbols: tuple[UniverseSymbol, ...] = (),
    orchestrator: ScannerOrchestrator | None = None,
    ranking_policy: CandidateRankingPolicy | None = None,
) -> OpportunityScanReport:
    selected = orchestrator or ScannerOrchestrator()
    if command == "scan-spot":
        raw_results = selected.scan_spot(spot_symbols).results
        market = UniverseMarket.SPOT.value
    elif command == "scan-futures":
        raw_results = selected.scan_futures(futures_symbols).results
        market = UniverseMarket.USD_M_FUTURES.value
    else:
        raw_results = selected.scan_all(
            spot_symbols=spot_symbols,
            futures_symbols=futures_symbols,
        ).results
        market = "ALL"
    snapshot_id = f"opportunity-scan:{command}:{market}"
    candidates = _deduplicate_candidates(
        tuple(sorted((_candidate(item) for item in raw_results), key=_rank))
    )
    candidates = _apply_candidate_ranking(
        candidates,
        ranking_policy or CandidateRankingPolicy(),
    )
    input_blockers = ("SCANNER_INPUT_UNAVAILABLE",) if not candidates else ()
    blockers = tuple(
        dict.fromkeys(
            (
                *(blocker for item in candidates for blocker in item.blockers),
                *input_blockers,
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    return OpportunityScanReport(
        command=command,
        market=market,
        candidates=candidates,
        blockers=blockers,
        funnel=_funnel_metrics(tuple(raw_results), candidates),
        snapshot_id=snapshot_id,
        status=(
            "READY"
            if candidates
            and any(item.accepted for item in candidates)
            and not any(item.discovery_exclusions for item in candidates)
            else "RUNNING_WITH_BLOCKERS"
        ),
    )


def _candidate(result: UniverseFilterResult) -> OpportunityScanCandidate:
    symbol = result.symbol
    token_risk = assess_token_risk(symbol)
    blockers = tuple(dict.fromkeys((*result.blockers, *token_risk.blockers)))
    liquidity = _bounded_score(symbol.quote_volume_24h_usdt, Decimal("1000000"))
    depth = _bounded_score(symbol.depth_0_5_pct_usdt, Decimal("25000"))
    spread = Decimal("100") - min(Decimal("100"), symbol.spread_bps)
    derivatives = (
        _bounded_score(symbol.open_interest_usdt or ZERO, Decimal("1000000"))
        if symbol.market is UniverseMarket.USD_M_FUTURES
        else ZERO
    )
    market_quality_score = max(
        ZERO,
        liquidity * Decimal("0.35")
        + depth * Decimal("0.25")
        + spread * Decimal("0.25")
        + derivatives * Decimal("0.15"),
    )
    discovery_exclusions = _discovery_exclusions(blockers)
    execution_blockers = _execution_blockers(blockers, discovery_exclusions)
    hard_blockers = _hard_blockers(discovery_exclusions, symbol)
    soft_penalties = _soft_penalties(symbol, liquidity, depth, spread)
    control_evaluation = build_control_evaluation(
        evaluation_id=f"control:opportunity-scan:{symbol.market.value}:{symbol.symbol}",
        base_score=market_quality_score,
        hard_blockers=hard_blockers,
        soft_penalties=soft_penalties,
        eligibility_when_clear=ControlEligibility.WATCH_ONLY,
        eligibility_when_blocked=ControlEligibility.NO_TRADE,
    )
    rank_score = control_evaluation.adjusted_score
    confirmation_gaps = _confirmation_gaps(execution_blockers)
    validation_gaps = _validation_gaps(execution_blockers)
    setup_score = ZERO
    evidence_quality_score = _evidence_quality_score(
        discovery_exclusions=discovery_exclusions,
        confirmation_gaps=confirmation_gaps,
        validation_gaps=validation_gaps,
        market_quality_score=market_quality_score,
    )
    opportunity_score = _opportunity_score(
        market_quality_score=control_evaluation.adjusted_score,
        setup_score=setup_score,
        evidence_quality_score=evidence_quality_score,
        discovery_exclusions=discovery_exclusions,
    )
    discovery_grade = _discovery_grade(opportunity_score)
    visibility_state = _visibility_state(
        discovery_exclusions=discovery_exclusions,
        confirmation_gaps=confirmation_gaps,
        validation_gaps=validation_gaps,
        opportunity_score=opportunity_score,
    )
    lifecycle_state = _lifecycle_state(visibility_state)
    research_state = (
        "DISCOVERY_EXCLUDED" if discovery_exclusions else visibility_state.value
    )
    opportunity_key = _opportunity_key(symbol)
    snapshot_id = f"universe:{symbol.market.value}:{symbol.symbol}"
    all_blockers = tuple(dict.fromkeys((*discovery_exclusions, *execution_blockers)))
    return OpportunityScanCandidate(
        symbol=symbol.symbol,
        market=symbol.market.value,
        rank_score=rank_score,
        accepted=not discovery_exclusions,
        blockers=all_blockers,
        strategy_id=(
            "USD_M_MARKET_QUALITY_SCAN"
            if symbol.market is UniverseMarket.USD_M_FUTURES
            else "SPOT_MARKET_QUALITY_SCAN"
        ),
        regime="UNCLASSIFIED",
        market_quality_score=market_quality_score,
        opportunity_score=opportunity_score,
        discovery_grade=discovery_grade,
        research_confidence=evidence_quality_score,
        research_state=research_state,
        lifecycle_state=lifecycle_state,
        opportunity_key=opportunity_key,
        opportunity_instance_id=f"{opportunity_key}:{snapshot_id}",
        snapshot_id=snapshot_id,
        discovery_exclusions=discovery_exclusions,
        confirmation_gaps=confirmation_gaps,
        validation_gaps=validation_gaps,
        execution_blockers=execution_blockers,
        hard_blockers=tuple(blocker.reason_code for blocker in hard_blockers),
        soft_penalties=tuple(penalty.reason_code for penalty in soft_penalties),
        base_score=market_quality_score,
        total_penalty=control_evaluation.total_penalty,
        adjusted_score=control_evaluation.adjusted_score,
        eligibility=control_evaluation.eligibility.value,
        control_evaluation=control_evaluation,
        liquidity_score=liquidity,
        depth_score=depth,
        spread_score=spread,
        signal_score=setup_score,
        evidence_score=evidence_quality_score,
        risk_reward=None,
        invalidation="DISCOVERY_EXCLUSION_OR_EVIDENCE_DECAY",
        expected_holding_period="UNSPECIFIED",
        derivatives_score=derivatives,
        structure_score=ZERO,
        momentum_score=ZERO,
        volume_score=ZERO,
        volatility_score=ZERO,
        setup_score=setup_score,
        multi_timeframe_score=ZERO,
        evidence_quality_score=evidence_quality_score,
        regime_alignment_score=ZERO,
        execution_quality_score=_execution_quality_score(
            discovery_exclusions=discovery_exclusions,
            confirmation_gaps=confirmation_gaps,
            validation_gaps=validation_gaps,
        ),
        reward_risk_quality_score=ZERO,
        raw_discovery_score=opportunity_score,
        deep_setup_evidence_available=False,
        asset_risk_status="PASSED" if token_risk.accepted else "BLOCKED",
    )


def _bounded_score(value: Decimal, baseline: Decimal) -> Decimal:
    if baseline <= ZERO:
        return ZERO
    return min(Decimal("100"), max(ZERO, value * Decimal("100") / baseline))


def _discovery_exclusions(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        blocker for blocker in blockers if blocker not in EXECUTION_ONLY_BLOCKERS
    )


def _execution_blockers(
    blockers: tuple[str, ...],
    discovery_exclusions: tuple[str, ...],
) -> tuple[str, ...]:
    required = (
        "LIVE_ORDER_BLOCKED",
        "SETUP_EVIDENCE_UNAVAILABLE",
        "OOS_NOT_COMPLETE",
        "PAPER_VALIDATION_PENDING",
        "TRADE_PLAN_INCOMPLETE",
    )
    execution_only = tuple(
        blocker for blocker in blockers if blocker in EXECUTION_ONLY_BLOCKERS
    )
    if discovery_exclusions:
        return tuple(dict.fromkeys((*execution_only, "LIVE_ORDER_BLOCKED")))
    return tuple(dict.fromkeys((*execution_only, *required)))


def _confirmation_gaps(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        blocker for blocker in blockers if blocker in CONFIRMATION_GAP_BLOCKERS
    )


def _validation_gaps(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(blocker for blocker in blockers if blocker in VALIDATION_GAP_BLOCKERS)


def _evidence_quality_score(
    *,
    discovery_exclusions: tuple[str, ...],
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
    market_quality_score: Decimal,
) -> Decimal:
    if discovery_exclusions:
        return ZERO
    missing_evidence_penalty = Decimal("6") * Decimal(len(confirmation_gaps)) + Decimal(
        "3"
    ) * Decimal(len(validation_gaps))
    return max(ZERO, min(ONE_HUNDRED, market_quality_score - missing_evidence_penalty))


def _visibility_state(
    *,
    discovery_exclusions: tuple[str, ...],
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
    opportunity_score: Decimal,
) -> OpportunityVisibilityState:
    if discovery_exclusions:
        return OpportunityVisibilityState.INVALIDATED
    if confirmation_gaps:
        return OpportunityVisibilityState.CONFIRMATION_PENDING
    if validation_gaps:
        return OpportunityVisibilityState.VALIDATION_PENDING
    if opportunity_score >= DEFAULT_OPPORTUNITY_GRADE_POLICY.c_threshold:
        return OpportunityVisibilityState.SETUP_FORMING
    return OpportunityVisibilityState.WATCH_ONLY


def _funnel_stage(
    *,
    discovery_exclusions: tuple[str, ...],
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
) -> OpportunityFunnelStage:
    if discovery_exclusions:
        return OpportunityFunnelStage.DISCOVERED
    if confirmation_gaps or validation_gaps:
        return OpportunityFunnelStage.QUALIFIED
    return OpportunityFunnelStage.VIRTUAL_ELIGIBLE


def _disposition(
    *,
    discovery_exclusions: tuple[str, ...],
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
    virtual_eligible: bool,
) -> OpportunityDisposition:
    if discovery_exclusions:
        return OpportunityDisposition.REJECTED
    if confirmation_gaps:
        return OpportunityDisposition.WAIT_FOR_RETEST
    if virtual_eligible:
        return OpportunityDisposition.ACCEPTED
    if validation_gaps:
        return OpportunityDisposition.WATCH
    return OpportunityDisposition.WATCH


def _lifecycle_state(visibility_state: OpportunityVisibilityState) -> str:
    if visibility_state is OpportunityVisibilityState.INVALIDATED:
        return OpportunityLifecycleState.BLOCKED.value
    if visibility_state is OpportunityVisibilityState.CONFIRMATION_PENDING:
        return OpportunityLifecycleState.CONFIRMATION_PENDING.value
    if visibility_state is OpportunityVisibilityState.VALIDATION_PENDING:
        return OpportunityLifecycleState.VALIDATION_PENDING.value
    if visibility_state is OpportunityVisibilityState.SETUP_FORMING:
        return OpportunityLifecycleState.SETUP_FORMING.value
    return OpportunityLifecycleState.DEVELOPING.value


def _why_visible(
    *,
    market_quality_score: Decimal,
    setup_score: Decimal,
    liquidity_score: Decimal,
    depth_score: Decimal,
    spread_score: Decimal,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if market_quality_score >= Decimal("80"):
        reasons.append("MARKET_QUALITY_PASS")
    if setup_score >= Decimal("70"):
        reasons.append("DEEP_SETUP_EVIDENCE_AVAILABLE")
    if liquidity_score >= Decimal("80"):
        reasons.append("LIQUIDITY_ACCEPTABLE")
    if depth_score >= Decimal("80"):
        reasons.append("DEPTH_ACCEPTABLE")
    if spread_score >= Decimal("90"):
        reasons.append("SPREAD_ACCEPTABLE")
    return tuple(reasons) or ("WATCHLIST_RESEARCH_VISIBLE",)


def _supporting_evidence(
    *,
    market_quality_score: Decimal,
    setup_score: Decimal,
    evidence_quality_score: Decimal,
    deep_setup_evidence_available: bool,
) -> tuple[str, ...]:
    setup_evidence = (
        f"SETUP_SCORE={setup_score}"
        if deep_setup_evidence_available
        else "SETUP_EVIDENCE_UNAVAILABLE"
    )
    return (
        f"MARKET_QUALITY_SCORE={market_quality_score}",
        setup_evidence,
        f"EVIDENCE_QUALITY_SCORE={evidence_quality_score}",
    )


def _next_safe_action(
    *,
    discovery_exclusions: tuple[str, ...],
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
) -> str:
    if discovery_exclusions:
        return "DO_NOT_SHOW_AS_ACTIVE_OPPORTUNITY"
    if confirmation_gaps:
        return "WAIT_FOR_CONFIRMATION_AND_REFRESH_RADAR"
    if validation_gaps:
        return "RUN_VALIDATION_QUEUE"
    return "KEEP_RESEARCH_RADAR_RUNNING"


def _opportunity_score(
    *,
    market_quality_score: Decimal,
    setup_score: Decimal,
    evidence_quality_score: Decimal,
    discovery_exclusions: tuple[str, ...],
) -> Decimal:
    if discovery_exclusions or setup_score <= ZERO:
        return ZERO
    return max(
        ZERO,
        min(
            ONE_HUNDRED,
            market_quality_score * Decimal("0.30")
            + setup_score * Decimal("0.45")
            + evidence_quality_score * Decimal("0.25"),
        ),
    )


def _discovery_grade(opportunity_score: Decimal) -> str:
    return classify_opportunity_grade(opportunity_score)


def _opportunity_key(symbol: UniverseSymbol) -> str:
    return ":".join(
        (
            symbol.market.value,
            symbol.symbol,
            "UNSPECIFIED",
            "SETUP_UNAVAILABLE",
            "WATCH_ONLY",
        )
    )


def _deduplicate_candidates(
    candidates: tuple[OpportunityScanCandidate, ...],
) -> tuple[OpportunityScanCandidate, ...]:
    selected: dict[str, OpportunityScanCandidate] = {}
    for candidate in candidates:
        existing = selected.get(candidate.opportunity_key)
        if existing is None or _rank(candidate) < _rank(existing):
            selected[candidate.opportunity_key] = candidate
    return tuple(sorted(selected.values(), key=_rank))


def _funnel_metrics(
    raw_results: tuple[UniverseFilterResult, ...],
    candidates: tuple[OpportunityScanCandidate, ...],
) -> OpportunityFunnelMetrics:
    excluded_reason_counts = Counter(
        blocker for result in raw_results for blocker in result.blockers
    )
    excluded_reason_counts.update(
        blocker
        for candidate in candidates
        for blocker in candidate.discovery_exclusions
    )
    reason_counts = Counter(
        blocker for candidate in candidates for blocker in candidate.blockers
    )
    eligible_symbols = sum(1 for item in candidates if item.discovery_eligible)
    return OpportunityFunnelMetrics(
        total_universe=len(raw_results),
        classified=len(candidates),
        discovered=len(candidates),
        qualified=sum(1 for item in candidates if item.qualified),
        virtual_eligible=sum(1 for item in candidates if item.virtual_eligible),
        discovery_eligible=sum(1 for item in candidates if item.discovery_eligible),
        market_quality_pass=sum(
            1
            for item in candidates
            if item.discovery_eligible and item.market_quality_score >= Decimal("80")
        ),
        setup_detected=sum(
            1
            for item in candidates
            if item.discovery_eligible and item.deep_setup_evidence_available
        ),
        b_or_higher=sum(
            1
            for item in candidates
            if DEFAULT_OPPORTUNITY_GRADE_POLICY.is_b_or_higher(item.discovery_grade)
        ),
        b_plus_or_higher=sum(
            1
            for item in candidates
            if DEFAULT_OPPORTUNITY_GRADE_POLICY.is_b_plus_or_higher(
                item.discovery_grade
            )
        ),
        trade_plan_complete=sum(1 for item in candidates if item.trade_plan_complete),
        validation_passed=sum(1 for item in candidates if item.validation_passed),
        paper_eligible=sum(1 for item in candidates if item.paper_eligible),
        accepted=sum(
            1
            for item in candidates
            if item.disposition == OpportunityDisposition.ACCEPTED.value
        ),
        rejected=sum(
            1
            for item in candidates
            if item.disposition == OpportunityDisposition.REJECTED.value
        ),
        watch=sum(
            1
            for item in candidates
            if item.disposition == OpportunityDisposition.WATCH.value
        ),
        wait_for_retest=sum(
            1
            for item in candidates
            if item.disposition == OpportunityDisposition.WAIT_FOR_RETEST.value
        ),
        symbols_scanned=len(raw_results),
        raw_candidates=len(candidates),
        data_quality_rejected=_count_results_with_blockers(
            raw_results, DATA_QUALITY_REJECTION_BLOCKERS
        ),
        liquidity_rejected=_count_results_with_blockers(
            raw_results, LIQUIDITY_REJECTION_BLOCKERS
        ),
        spread_rejected=_count_results_with_blockers(
            raw_results, SPREAD_REJECTION_BLOCKERS
        ),
        token_risk_rejected=_count_candidates_with_blockers(
            candidates, TOKEN_RISK_REJECTION_BLOCKERS
        ),
        watch_only=sum(
            1
            for item in candidates
            if item.visibility_state == OpportunityVisibilityState.WATCH_ONLY.value
        ),
        confirmation_pending=sum(
            1
            for item in candidates
            if item.visibility_state
            == OpportunityVisibilityState.CONFIRMATION_PENDING.value
        ),
        paper_executed=0,
        raw_symbols_scanned=len(raw_results),
        eligible_symbols=eligible_symbols,
        excluded_symbols=len(raw_results) - eligible_symbols,
        forming_setups=sum(
            1
            for item in candidates
            if item.lifecycle_state == OpportunityLifecycleState.SETUP_FORMING.value
        ),
        qualified_setups=sum(1 for item in candidates if item.qualified),
        confirmed_setups=sum(
            1
            for item in candidates
            if item.lifecycle_state == OpportunityLifecycleState.CONFIRMED.value
        ),
        watch_only_candidates=sum(
            1
            for item in candidates
            if item.visibility_state == OpportunityVisibilityState.WATCH_ONLY.value
        ),
        risk_rejected_candidates=sum(
            1
            for item in candidates
            if any("RISK" in blocker for blocker in item.hard_blockers)
        ),
        validation_rejected_candidates=sum(
            1 for item in candidates if item.validation_gaps
        ),
        governance_rejected_candidates=sum(
            1
            for item in candidates
            if any("GOVERNANCE" in blocker for blocker in item.hard_blockers)
        ),
        virtual_eligible_candidates=sum(
            1 for item in candidates if item.virtual_eligible
        ),
        virtual_executed_candidates=0,
        expired_candidates=sum(
            1
            for item in candidates
            if item.visibility_state == OpportunityVisibilityState.EXPIRED.value
        ),
        invalidated_candidates=sum(
            1
            for item in candidates
            if item.visibility_state == OpportunityVisibilityState.INVALIDATED.value
        ),
        excluded_symbols_by_reason=tuple(sorted(excluded_reason_counts.items())),
        reason_code_counts=tuple(sorted(reason_counts.items())),
    )


def _count_results_with_blockers(
    results: tuple[UniverseFilterResult, ...],
    blockers: frozenset[str],
) -> int:
    return sum(
        1
        for result in results
        if any(blocker in result.blockers for blocker in blockers)
    )


def _count_candidates_with_blockers(
    candidates: tuple[OpportunityScanCandidate, ...],
    blockers: frozenset[str],
) -> int:
    return sum(
        1
        for item in candidates
        if any(blocker in item.blockers for blocker in blockers)
    )


def _apply_candidate_ranking(
    candidates: tuple[OpportunityScanCandidate, ...],
    policy: CandidateRankingPolicy,
) -> tuple[OpportunityScanCandidate, ...]:
    ranked = tuple(
        replace(
            candidate,
            regime_alignment_score=_regime_alignment_score(candidate),
            execution_quality_score=_execution_quality_score(
                discovery_exclusions=candidate.discovery_exclusions,
                confirmation_gaps=candidate.confirmation_gaps,
                validation_gaps=candidate.validation_gaps,
            ),
            reward_risk_quality_score=_reward_risk_quality_score(candidate.risk_reward),
        )
        for candidate in candidates
    )
    ranked = tuple(
        replace(
            candidate,
            rank_score=_candidate_rank_score(candidate, policy),
            ranking_eligible=_ranking_eligible(candidate),
        )
        for candidate in ranked
    )
    selected_keys = _select_top_candidate_keys(ranked, policy)
    selected = tuple(
        replace(
            candidate,
            selected_for_virtual_cycle=candidate.opportunity_key in selected_keys,
        )
        for candidate in ranked
    )
    return tuple(sorted(selected, key=_rank))


def _candidate_rank_score(
    candidate: OpportunityScanCandidate,
    policy: CandidateRankingPolicy,
) -> Decimal:
    if not _ranking_eligible(candidate):
        return ZERO
    weighted_sum = (
        candidate.setup_score * policy.setup_quality_weight
        + candidate.evidence_quality_score * policy.evidence_quality_weight
        + candidate.regime_alignment_score * policy.regime_alignment_weight
        + candidate.market_quality_score * policy.liquidity_quality_weight
        + candidate.execution_quality_score * policy.execution_quality_weight
        + candidate.reward_risk_quality_score * policy.reward_risk_quality_weight
    )
    penalty = candidate.total_penalty * policy.soft_penalty_weight
    return max(ZERO, min(ONE_HUNDRED, weighted_sum - penalty))


def _regime_alignment_score(candidate: OpportunityScanCandidate) -> Decimal:
    if candidate.multi_timeframe_score > ZERO:
        return candidate.multi_timeframe_score
    if candidate.confirmation_gaps:
        return Decimal("25")
    if candidate.validation_gaps:
        return Decimal("50")
    return Decimal("60")


def _execution_quality_score(
    *,
    discovery_exclusions: tuple[str, ...],
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
) -> Decimal:
    if discovery_exclusions:
        return ZERO
    if confirmation_gaps:
        return Decimal("35")
    if validation_gaps:
        return Decimal("55")
    return Decimal("85")


def _reward_risk_quality_score(risk_reward: Decimal | None) -> Decimal:
    if risk_reward is None:
        return ZERO
    return min(ONE_HUNDRED, max(ZERO, (risk_reward - Decimal("1")) * Decimal("50")))


def _ranking_eligible(candidate: OpportunityScanCandidate) -> bool:
    return candidate.virtual_eligible and not candidate.hard_blockers


def _select_top_candidate_keys(
    candidates: tuple[OpportunityScanCandidate, ...],
    policy: CandidateRankingPolicy,
) -> set[str]:
    selected: set[str] = set()
    for market, limit in (
        ("SPOT", policy.maximum_selected_spot_candidates),
        ("USD_M_FUTURES", policy.maximum_selected_futures_candidates),
    ):
        eligible = tuple(
            candidate
            for candidate in candidates
            if candidate.market == market and candidate.ranking_eligible
        )
        ordered = sorted(
            eligible,
            key=lambda candidate: (-candidate.rank_score, candidate.symbol),
        )
        selected.update(candidate.opportunity_key for candidate in ordered[:limit])
    return selected


def _hard_blockers(
    blockers: tuple[str, ...],
    symbol: UniverseSymbol,
) -> tuple[HardBlocker, ...]:
    return tuple(
        HardBlocker(
            blocker_id=f"hard:opportunity-scan:{symbol.symbol}:{blocker}",
            blocker_type="SCANNER_FILTER",
            source=_blocker_source(blocker),
            severity=ControlSeverity.HIGH,
            reason_code=blocker,
            evidence_refs=(f"universe:{symbol.market.value}:{symbol.symbol}",),
            policy_ref="policy:opportunity-scanner:universe-filter",
            resolution_authority=_blocker_resolution_authority(blocker),
        )
        for blocker in blockers
    )


def _soft_penalties(
    symbol: UniverseSymbol,
    liquidity: Decimal,
    depth: Decimal,
    spread: Decimal,
) -> tuple[SoftPenalty, ...]:
    penalties: list[SoftPenalty] = []
    evidence_ref = f"universe:{symbol.market.value}:{symbol.symbol}"
    if liquidity < Decimal("80"):
        penalties.append(
            _soft_penalty(
                symbol,
                "WEAK_RELATIVE_VOLUME",
                Decimal("5"),
                ControlSource.LIQUIDITY,
                "LIQUIDITY_QUALITY",
                evidence_ref,
            )
        )
    if depth < Decimal("80"):
        penalties.append(
            _soft_penalty(
                symbol,
                "SHALLOW_DEPTH",
                Decimal("5"),
                ControlSource.LIQUIDITY,
                "LIQUIDITY_QUALITY",
                evidence_ref,
            )
        )
    if spread < Decimal("90"):
        penalties.append(
            _soft_penalty(
                symbol,
                "MINOR_SPREAD_DEGRADATION",
                Decimal("3"),
                ControlSource.LIQUIDITY,
                "LIQUIDITY_QUALITY",
                evidence_ref,
            )
        )
    return tuple(penalties)


def _soft_penalty(
    symbol: UniverseSymbol,
    reason_code: str,
    value: Decimal,
    source: ControlSource,
    penalty_group: str,
    evidence_ref: str,
) -> SoftPenalty:
    return SoftPenalty(
        penalty_id=f"soft:opportunity-scan:{symbol.symbol}:{reason_code}",
        penalty_type="SCANNER_RANK_ADJUSTMENT",
        source=source,
        reason_code=reason_code,
        value=value,
        max_value=Decimal("10"),
        evidence_refs=(evidence_ref,),
        policy_ref="policy:opportunity-scanner:soft-penalty",
        penalty_group=penalty_group,
    )


def _blocker_source(blocker: str) -> ControlSource:
    if "LIQUIDITY" in blocker or "SPREAD" in blocker or "DEPTH" in blocker:
        return ControlSource.LIQUIDITY
    if "STABLECOIN" in blocker or "LEVERAGED" in blocker or "TOKEN" in blocker:
        return ControlSource.RISK
    return ControlSource.GOVERNANCE


def _blocker_resolution_authority(blocker: str) -> ControlResolutionAuthority:
    source = _blocker_source(blocker)
    if source is ControlSource.LIQUIDITY:
        return ControlResolutionAuthority.LIQUIDITY_ENGINE
    if source is ControlSource.RISK:
        return ControlResolutionAuthority.RISK_ENGINE
    return ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE


def _rank(candidate: OpportunityScanCandidate) -> tuple[bool, Decimal, str]:
    return (not candidate.accepted, -candidate.rank_score, candidate.symbol)
