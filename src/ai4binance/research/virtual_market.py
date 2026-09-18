"""Virtual-market research performance and acceptance contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Self, cast

import yaml

from ai4binance.governance.blockers import (
    BLOCKER_REGISTRY_PATH,
    BlockerDefinition,
    load_blocker_registry,
)
from ai4binance.governance.execution_authority import (
    VIRTUAL_MARKET_AUTO_PROFILE,
    ExecutionAutomationMode,
    ExecutionSurface,
    authority_profile_for_surface,
)
from ai4binance.ops.user_reports import render_professional_summary
from ai4binance.research.equity_metrics import (
    EquityObservation,
    calculate_equity_returns,
    calculate_periodic_sharpe,
)

ZERO = Decimal("0")
ONE = Decimal("1")
DEFAULT_INITIAL_EQUITY_USDT = Decimal("1000")
MAX_ACCEPTANCE_POLICY_BYTES = 64_000
DEFAULT_HARD_FAIL_GATES = (
    "REPLAY_STATE_HASH_MISSING",
    "DECISION_REPRODUCIBILITY_FAILED",
    "CRITICAL_DATA_GAPS_PRESENT",
    "DUPLICATE_ECONOMIC_EVENTS_APPLIED",
    "LOOKAHEAD_VIOLATIONS_PRESENT",
    "FUTURES_LIQUIDATION_OCCURRED",
)
DEFAULT_SYSTEM_ACCEPTANCE_OPERATOR = "SPOT_PASS_AND_FUTURES_PASS"
RESEARCH_CANDIDATE_STAGE = "RESEARCH_CANDIDATE"
EXISTING_FINAL_ACCEPTANCE_STAGE = "EXISTING_FINAL_ACCEPTANCE"
DEFAULT_REQUIRED_COST_STRESS_SCENARIOS = ("BASE", "COST_1_5X", "COST_2X")
ACCEPTANCE_BLOCKER_CANONICAL_CODES: Mapping[str, str] = {
    "REPLAY_STATE_HASH_MISSING": "EVID.PROVENANCE_MISSING",
    "DECISION_REPRODUCIBILITY_FAILED": "VAL.ROBUSTNESS_NOT_VALIDATED",
    "CRITICAL_DATA_GAPS_PRESENT": "DATA.SNAPSHOT_INCOMPLETE",
    "DUPLICATE_ECONOMIC_EVENTS_APPLIED": "DATA.DATA_QUALITY_FAILED",
    "LOOKAHEAD_VIOLATIONS_PRESENT": "DATA.DATA_QUALITY_FAILED",
    "CRITICAL_DATA_QUALITY_FAILURE_PRESENT": "DATA.DATA_QUALITY_FAILED",
    "OBSERVATION_WINDOW_INSUFFICIENT": "VAL.OOS_NOT_VALIDATED",
    "TRADE_SAMPLE_INSUFFICIENT": "VAL.OOS_NOT_VALIDATED",
    "NET_RETURN_NOT_POSITIVE": "STRAT.NOT_APPROVED_FOR_STAGE",
    "MODELED_COST_EXPECTANCY_NOT_POSITIVE": "STRAT.NOT_APPROVED_FOR_STAGE",
    "OOS_EXPECTANCY_NOT_POSITIVE": "VAL.OOS_NOT_VALIDATED",
    "COST_STRESS_EVIDENCE_MISSING": "EVID.CRITICAL_EVIDENCE_MISSING",
    "COST_STRESS_SCENARIOS_INCOMPLETE": "EVID.CRITICAL_EVIDENCE_MISSING",
    "REGIME_LEVEL_ATTRIBUTION_MISSING": "EVID.CRITICAL_EVIDENCE_MISSING",
    "FRAGILE_EDGE": "STRAT.NOT_APPROVED_FOR_STAGE",
    "DAILY_SHARPE_UNAVAILABLE": "EVID.CRITICAL_EVIDENCE_MISSING",
    "DAILY_SHARPE_BELOW_THRESHOLD": "VAL.OOS_NOT_VALIDATED",
    "PROFIT_FACTOR_UNAVAILABLE": "EVID.CRITICAL_EVIDENCE_MISSING",
    "PROFIT_FACTOR_BELOW_THRESHOLD": "VAL.OOS_NOT_VALIDATED",
    "MAX_DRAWDOWN_ABOVE_THRESHOLD": "RISK.RISK_LIMIT_EXCEEDED",
    "FUTURES_LIQUIDATION_OCCURRED": "RISK.VETO",
    "FUTURES_MARGIN_UTILIZATION_UNAVAILABLE": "EVID.CRITICAL_EVIDENCE_MISSING",
    "FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD": "RISK.RISK_LIMIT_EXCEEDED",
    "SYSTEM_FAIL": "STRAT.NOT_APPROVED_FOR_STAGE",
    "SYSTEM_INSUFFICIENT_EVIDENCE": "VAL.OOS_NOT_VALIDATED",
    "SYSTEM_DATA_UNAVAILABLE": "DATA.SNAPSHOT_INCOMPLETE",
    "SYSTEM_NON_REPRODUCIBLE": "VAL.ROBUSTNESS_NOT_VALIDATED",
    "SYSTEM_NOT_EVALUATED": "EVID.CRITICAL_EVIDENCE_MISSING",
}
STATUS_BLOCKER_CLASSES: tuple[tuple[AcceptanceStatus, tuple[str, ...]], ...]


class VirtualMarket(StrEnum):
    """Research markets that must remain independently evaluated."""

    SPOT = "SPOT"
    USD_M_FUTURES = "USD_M_FUTURES"


def derive_virtual_runtime_priority_signal(
    *,
    surface_kind: str,
    status: str,
    blockers: Sequence[str] = (),
    has_counterfactual_pnl: bool = False,
    has_counterfactual_r: bool = False,
    has_net_return: bool = False,
    has_max_drawdown: bool = False,
    has_oos_expectancy: bool = False,
) -> str:
    """Derive a fail-closed virtual-runtime triage signal from canonical evidence."""

    normalized_surface_kind = surface_kind.strip().upper() or "UNKNOWN"
    normalized_status = status.strip().upper() or "UNKNOWN"
    normalized_blockers = tuple(
        dict.fromkeys(str(item).strip() for item in blockers if str(item).strip())
    )
    if normalized_surface_kind == "NO_TRADE" and (
        has_counterfactual_pnl or has_counterfactual_r
    ):
        return "COUNTERFACTUAL_REVIEW_PRIORITY"
    if "FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD" in normalized_blockers:
        return "FUTURES_MARGIN_DISCIPLINE_PRIORITY"
    if "MAX_DRAWDOWN_ABOVE_THRESHOLD" in normalized_blockers:
        return "DRAWDOWN_REDUCTION_PRIORITY"
    if "TRADE_SAMPLE_INSUFFICIENT" in normalized_blockers:
        return "SAMPLE_BUILD_PRIORITY"
    if (
        "DAILY_SHARPE_UNAVAILABLE" in normalized_blockers
        or "PROFIT_FACTOR_UNAVAILABLE" in normalized_blockers
    ):
        return "ACCEPTANCE_EVIDENCE_GAP_PRIORITY"
    if (
        "DAILY_SHARPE_BELOW_THRESHOLD" in normalized_blockers
        or "PROFIT_FACTOR_BELOW_THRESHOLD" in normalized_blockers
    ):
        return "PERFORMANCE_TUNING_PRIORITY"
    if (
        normalized_surface_kind == "RESEARCH"
        and normalized_status == "READY_WITH_BLOCKERS"
        and has_net_return
        and has_max_drawdown
        and has_oos_expectancy
    ):
        return "RESEARCH_FOLLOW_UP_PRIORITY"
    if normalized_status in {"READY", "READY_WITH_BLOCKERS", "RESEARCH_ONLY"}:
        return "MONITOR"
    return "UNAVAILABLE"


def _coerce_virtual_market(market: VirtualMarket | str) -> VirtualMarket:
    if isinstance(market, VirtualMarket):
        return market
    normalized = str(market).strip().upper()
    if normalized == VirtualMarket.SPOT.value:
        return VirtualMarket.SPOT
    if normalized == VirtualMarket.USD_M_FUTURES.value:
        return VirtualMarket.USD_M_FUTURES
    raise ValueError("virtual market must be SPOT or USD_M_FUTURES")


class AcceptanceStatus(StrEnum):
    """Fail-closed research acceptance states."""

    PASS = "PASS"  # noqa: S105  # nosec B105
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    NON_REPRODUCIBLE = "NON_REPRODUCIBLE"
    NOT_EVALUATED = "NOT_EVALUATED"


STATUS_BLOCKER_CLASSES = (
    (
        AcceptanceStatus.NON_REPRODUCIBLE,
        (
            "REPLAY_STATE_HASH_MISSING",
            "DECISION_REPRODUCIBILITY_FAILED",
        ),
    ),
    (
        AcceptanceStatus.DATA_UNAVAILABLE,
        (
            "CRITICAL_DATA_GAPS_PRESENT",
            "DAILY_SHARPE_UNAVAILABLE",
            "PROFIT_FACTOR_UNAVAILABLE",
            "FUTURES_MARGIN_UTILIZATION_UNAVAILABLE",
        ),
    ),
)
SYSTEM_STATUS_BLOCKERS: Mapping[AcceptanceStatus, str] = {
    AcceptanceStatus.FAIL: "SYSTEM_FAIL",
    AcceptanceStatus.INSUFFICIENT_EVIDENCE: "SYSTEM_INSUFFICIENT_EVIDENCE",
    AcceptanceStatus.DATA_UNAVAILABLE: "SYSTEM_DATA_UNAVAILABLE",
    AcceptanceStatus.NON_REPRODUCIBLE: "SYSTEM_NON_REPRODUCIBLE",
    AcceptanceStatus.NOT_EVALUATED: "SYSTEM_NOT_EVALUATED",
}


def required_acceptance_blocker_mappings() -> tuple[str, ...]:
    """Return the blocker reasons that must stay wired to canonical taxonomy."""

    return tuple(
        dict.fromkeys(
            (
                *DEFAULT_HARD_FAIL_GATES,
                *(
                    blocker
                    for _, blockers in STATUS_BLOCKER_CLASSES
                    for blocker in blockers
                ),
            )
        )
    )


def required_system_status_blockers() -> tuple[str, ...]:
    """Return the only synthetic system blocker reasons allowed by the model."""

    return tuple(SYSTEM_STATUS_BLOCKERS.values())


MARKET_STATUS_BLOCKER_PRECEDENCE: tuple[
    tuple[AcceptanceStatus, tuple[str, ...]], ...
] = (
    (
        AcceptanceStatus.NON_REPRODUCIBLE,
        (
            "REPLAY_STATE_HASH_MISSING",
            "DECISION_REPRODUCIBILITY_FAILED",
        ),
    ),
    (
        AcceptanceStatus.DATA_UNAVAILABLE,
        (
            "CRITICAL_DATA_GAPS_PRESENT",
            "DAILY_SHARPE_UNAVAILABLE",
            "PROFIT_FACTOR_UNAVAILABLE",
            "FUTURES_MARGIN_UTILIZATION_UNAVAILABLE",
        ),
    ),
)
SYSTEM_STATUS_PRECEDENCE: tuple[AcceptanceStatus, ...] = (
    AcceptanceStatus.DATA_UNAVAILABLE,
    AcceptanceStatus.NON_REPRODUCIBLE,
    AcceptanceStatus.FAIL,
    AcceptanceStatus.INSUFFICIENT_EVIDENCE,
    AcceptanceStatus.NOT_EVALUATED,
)


def _require_virtual_market_research_only_authority(
    *,
    context: str,
    execution_allowed: bool,
    promotion_status: str,
    live_eligibility_status: str,
    execution_surface: ExecutionSurface,
) -> None:
    if (
        execution_allowed
        or promotion_status != "RESEARCH_ONLY"
        or live_eligibility_status != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError(f"{context} cannot authorize execution")
    if execution_surface is not ExecutionSurface.VIRTUAL_MARKET:
        raise ValueError(f"{context} must target VIRTUAL_MARKET")


def _require_virtual_market_policy_authority(
    *,
    context: str,
    execution_surface: ExecutionSurface,
    authority_profile_id: str,
    automation_mode: ExecutionAutomationMode,
) -> None:
    authority_profile = authority_profile_for_surface(execution_surface)
    if authority_profile.authority_profile_id != authority_profile_id:
        raise ValueError(f"{context} authority profile must match VIRTUAL_MARKET")
    if authority_profile.automation_mode is not automation_mode:
        raise ValueError(f"{context} automation mode must match VIRTUAL_MARKET")


@dataclass(frozen=True, slots=True)
class DailyEquityPoint:
    """UTC daily account-equity observation for portfolio-level statistics."""

    timestamp: datetime
    equity_usdt: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("daily equity timestamp must be timezone-aware")
        if self.equity_usdt <= ZERO:
            raise ValueError("daily equity must be positive")


@dataclass(frozen=True, slots=True)
class CostStressScenarioEvidence:
    """Modeled execution-cost evidence for one deterministic stress scenario."""

    scenario: str
    expectancy_after_costs_usdt: Decimal

    def __post_init__(self) -> None:
        if not self.scenario.strip():
            raise ValueError("cost stress scenario identity is required")
        _require_finite_decimal(
            "cost stress expectancy after costs",
            self.expectancy_after_costs_usdt,
        )


@dataclass(frozen=True, slots=True)
class RegimeAttribution:
    """Regime-level profitability attribution required for research evidence."""

    regime: str
    trade_count: int
    expectancy_usdt: Decimal

    def __post_init__(self) -> None:
        if not self.regime.strip():
            raise ValueError("regime attribution identity is required")
        _require_nonnegative_int("regime attribution trade count", self.trade_count)
        _require_finite_decimal("regime attribution expectancy", self.expectancy_usdt)


@dataclass(frozen=True, slots=True)
class ResearchCandidatePolicy:
    """Research-stage minimum profitability evidence without execution authority."""

    minimum_modeled_cost_expectancy_usdt: Decimal = ZERO
    minimum_oos_expectancy_usdt: Decimal = ZERO
    required_cost_stress_scenarios: tuple[str, ...] = (
        DEFAULT_REQUIRED_COST_STRESS_SCENARIOS
    )
    require_regime_level_attribution: bool = True

    def __post_init__(self) -> None:
        _require_finite_decimal(
            "minimum modeled cost expectancy",
            self.minimum_modeled_cost_expectancy_usdt,
        )
        _require_finite_decimal(
            "minimum OOS expectancy",
            self.minimum_oos_expectancy_usdt,
        )
        _require_unique_nonblank(
            "research candidate required cost stress scenarios",
            self.required_cost_stress_scenarios,
        )


@dataclass(frozen=True, slots=True)
class MarketPerformanceEvidence:
    """Market-specific performance evidence; never a combined portfolio result."""

    market: VirtualMarket
    session_id: str
    portfolio_id: str
    generation: int
    configured_start_at: datetime
    feature_warmup_start: datetime
    last_replayed_at: datetime
    initial_equity_usdt: Decimal
    ending_equity_usdt: Decimal
    net_return: Decimal
    max_drawdown: Decimal
    daily_sharpe: Decimal | None
    profit_factor: Decimal | None
    completed_trades: int
    observation_days: int
    modeled_cost_expectancy_usdt: Decimal = ZERO
    oos_expectancy_usdt: Decimal = ZERO
    critical_data_gaps: int = 0
    critical_data_quality_failure: bool = False
    applied_duplicate_economic_events: int = 0
    lookahead_violations: int = 0
    liquidation_events: int = 0
    fragile_edge: bool = False
    cost_stress_evidence: tuple[CostStressScenarioEvidence, ...] = ()
    regime_attribution: tuple[RegimeAttribution, ...] = ()
    peak_margin_utilization: Decimal | None = None
    replay_state_hash: str = ""
    decision_reproducibility_rate: Decimal = ONE
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        normalized_market = _coerce_virtual_market(self.market)
        object.__setattr__(self, "market", normalized_market)
        for value in (self.session_id, self.portfolio_id):
            if not value.strip():
                raise ValueError("market performance identity is required")
        for timestamp in (
            self.configured_start_at,
            self.feature_warmup_start,
            self.last_replayed_at,
        ):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("market performance timestamps must be timezone-aware")
        if self.feature_warmup_start > self.configured_start_at:
            raise ValueError("feature warm-up cannot start after configured start")
        if self.generation < 1:
            raise ValueError("market performance generation must be positive")
        if not ZERO < self.initial_equity_usdt <= DEFAULT_INITIAL_EQUITY_USDT:
            raise ValueError(
                "virtual market initial equity must be positive and at most 1000 USDT"
            )
        if self.ending_equity_usdt <= ZERO:
            raise ValueError("ending equity must be positive")
        _require_decimal_ratio(
            "net return",
            self.net_return,
            min_value=Decimal("-1"),
            max_value=None,
        )
        _require_decimal_ratio("max drawdown", self.max_drawdown)
        _require_optional_nonnegative("profit factor", self.profit_factor)
        _require_optional_nonnegative(
            "peak margin utilization",
            self.peak_margin_utilization,
        )
        _require_finite_decimal(
            "modeled cost expectancy",
            self.modeled_cost_expectancy_usdt,
        )
        _require_finite_decimal("OOS expectancy", self.oos_expectancy_usdt)
        _require_decimal_ratio(
            "decision reproducibility rate",
            self.decision_reproducibility_rate,
        )
        _require_nonnegative_int("completed trades", self.completed_trades)
        _require_nonnegative_int("observation days", self.observation_days)
        _require_nonnegative_int("critical data gaps", self.critical_data_gaps)
        _require_nonnegative_int(
            "applied duplicate economic events",
            self.applied_duplicate_economic_events,
        )
        _require_nonnegative_int("lookahead violations", self.lookahead_violations)
        _require_nonnegative_int("liquidation events", self.liquidation_events)
        _require_unique_nonblank(
            "cost stress evidence scenarios",
            tuple(item.scenario for item in self.cost_stress_evidence),
        )
        _require_unique_nonblank(
            "regime attribution identities",
            tuple(item.regime for item in self.regime_attribution),
        )
        if normalized_market is VirtualMarket.SPOT:
            if self.liquidation_events:
                raise ValueError("Spot evidence cannot contain liquidation events")
            if self.peak_margin_utilization is not None:
                raise ValueError("Spot evidence cannot contain margin utilization")
        if self.daily_sharpe is not None:
            _require_finite_decimal("daily Sharpe", self.daily_sharpe)
        _require_virtual_market_research_only_authority(
            context="market performance evidence",
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            execution_surface=self.execution_surface,
        )


@dataclass(frozen=True, slots=True)
class AcceptancePolicy:
    """Versioned research thresholds applied independently per market."""

    policy_id: str = "virtual-market-research-acceptance-v1"
    minimum_observation_days: int = 365
    minimum_completed_trades: int = 100
    minimum_daily_sharpe: Decimal = Decimal("1.00")
    minimum_profit_factor: Decimal = Decimal("1.25")
    maximum_spot_drawdown: Decimal = Decimal("0.15")
    maximum_futures_drawdown: Decimal = Decimal("0.12")
    maximum_futures_margin_utilization: Decimal = Decimal("0.75")
    research_candidate: ResearchCandidatePolicy = field(
        default_factory=ResearchCandidatePolicy
    )
    hard_fail_gates: tuple[str, ...] = DEFAULT_HARD_FAIL_GATES
    system_acceptance_operator: str = DEFAULT_SYSTEM_ACCEPTANCE_OPERATOR
    combined_pnl_gate_allowed: bool = False
    combined_sharpe_gate_allowed: bool = False
    combined_equity_gate_allowed: bool = False
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET
    authority_profile_id: str = VIRTUAL_MARKET_AUTO_PROFILE.authority_profile_id
    automation_mode: ExecutionAutomationMode = (
        ExecutionAutomationMode.BOUNDED_AUTONOMOUS_SIMULATION
    )

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("acceptance policy identity is required")
        if self.minimum_observation_days < 1 or self.minimum_completed_trades < 1:
            raise ValueError("acceptance policy minimum evidence must be positive")
        _require_finite_decimal("minimum daily Sharpe", self.minimum_daily_sharpe)
        _require_finite_decimal("minimum profit factor", self.minimum_profit_factor)
        _require_decimal_ratio("maximum Spot drawdown", self.maximum_spot_drawdown)
        _require_decimal_ratio(
            "maximum Futures drawdown",
            self.maximum_futures_drawdown,
        )
        _require_decimal_ratio(
            "maximum Futures margin utilization",
            self.maximum_futures_margin_utilization,
        )
        _require_unique_nonblank(
            "acceptance policy hard fail gates",
            self.hard_fail_gates,
        )
        if self.hard_fail_gates != DEFAULT_HARD_FAIL_GATES:
            raise ValueError(
                "acceptance policy hard fail gates must match the canonical set"
            )
        if self.system_acceptance_operator != DEFAULT_SYSTEM_ACCEPTANCE_OPERATOR:
            raise ValueError(
                "acceptance policy system acceptance operator is unsupported"
            )
        if (
            self.combined_pnl_gate_allowed
            or self.combined_sharpe_gate_allowed
            or self.combined_equity_gate_allowed
        ):
            raise ValueError("acceptance policy cannot enable combined market gates")
        _require_virtual_market_research_only_authority(
            context="acceptance policy",
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            execution_surface=self.execution_surface,
        )
        _require_virtual_market_policy_authority(
            context="acceptance policy",
            execution_surface=self.execution_surface,
            authority_profile_id=self.authority_profile_id,
            automation_mode=self.automation_mode,
        )


@dataclass(frozen=True, slots=True)
class MarketAcceptanceResult:
    """Independent market acceptance result with blocker-first semantics."""

    market: VirtualMarket
    status: AcceptanceStatus
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    policy_id: str
    canonical_blocker_codes: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        normalized_market = _coerce_virtual_market(self.market)
        object.__setattr__(self, "market", normalized_market)
        _require_unique_nonblank("market acceptance blockers", self.blockers)
        canonical_codes = (
            self.canonical_blocker_codes
            or canonical_acceptance_blocker_codes(self.blockers)
        )
        _require_unique_nonblank(
            "market acceptance canonical blockers", canonical_codes
        )
        object.__setattr__(self, "canonical_blocker_codes", canonical_codes)
        _require_unique_nonblank("market acceptance evidence refs", self.evidence_refs)
        if not self.policy_id.strip():
            raise ValueError("market acceptance policy identity is required")
        if self.status is AcceptanceStatus.PASS and self.blockers:
            raise ValueError("passing market acceptance cannot contain blockers")
        if self.status is not AcceptanceStatus.PASS and not self.blockers:
            raise ValueError("blocked market acceptance requires blockers")
        _require_virtual_market_research_only_authority(
            context="market acceptance result",
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            execution_surface=self.execution_surface,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "market": self.market.value,
            "status": self.status.value,
            "blockers": self.blockers,
            "evidence_refs": self.evidence_refs,
            "policy_id": self.policy_id,
            "canonical_blocker_codes": self.canonical_blocker_codes,
            "execution_allowed": self.execution_allowed,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
            "execution_surface": self.execution_surface.value,
        }


@dataclass(frozen=True, slots=True)
class ResearchCandidateResult:
    """Stage-1 profitability evidence with no final-acceptance authority."""

    market: VirtualMarket
    stage: str
    status: AcceptanceStatus
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    policy_id: str
    canonical_blocker_codes: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        normalized_market = _coerce_virtual_market(self.market)
        object.__setattr__(self, "market", normalized_market)
        if self.stage != RESEARCH_CANDIDATE_STAGE:
            raise ValueError("research candidate stage must be RESEARCH_CANDIDATE")
        _require_unique_nonblank("research candidate blockers", self.blockers)
        canonical_codes = (
            self.canonical_blocker_codes
            or canonical_acceptance_blocker_codes(self.blockers)
        )
        _require_unique_nonblank(
            "research candidate canonical blockers", canonical_codes
        )
        object.__setattr__(self, "canonical_blocker_codes", canonical_codes)
        _require_unique_nonblank("research candidate evidence refs", self.evidence_refs)
        if not self.policy_id.strip():
            raise ValueError("research candidate policy identity is required")
        if self.status is AcceptanceStatus.PASS and self.blockers:
            raise ValueError("passing research candidate cannot contain blockers")
        if self.status is not AcceptanceStatus.PASS and not self.blockers:
            raise ValueError("blocked research candidate requires blockers")
        _require_virtual_market_research_only_authority(
            context="research candidate result",
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            execution_surface=self.execution_surface,
        )


@dataclass(frozen=True, slots=True)
class SystemResearchAcceptance:
    """System result derived only from independent Spot and Futures acceptance."""

    spot: MarketAcceptanceResult
    futures: MarketAcceptanceResult
    status: AcceptanceStatus
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    canonical_blocker_codes: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        if self.spot.market is not VirtualMarket.SPOT:
            raise ValueError("system acceptance requires Spot acceptance evidence")
        if self.futures.market is not VirtualMarket.USD_M_FUTURES:
            raise ValueError("system acceptance requires Futures acceptance evidence")
        _require_unique_nonblank("system acceptance blockers", self.blockers)
        canonical_codes = (
            self.canonical_blocker_codes
            or canonical_acceptance_blocker_codes(self.blockers)
        )
        _require_unique_nonblank(
            "system acceptance canonical blockers", canonical_codes
        )
        object.__setattr__(self, "canonical_blocker_codes", canonical_codes)
        _require_unique_nonblank("system acceptance evidence refs", self.evidence_refs)
        if self.status is AcceptanceStatus.PASS and self.blockers:
            raise ValueError("passing system acceptance cannot contain blockers")
        if self.status is not AcceptanceStatus.PASS and not self.blockers:
            raise ValueError("blocked system acceptance requires blockers")
        system_blockers = tuple(
            blocker for blocker in self.blockers if blocker.startswith("SYSTEM_")
        )
        _require_system_status_blockers(self.status, system_blockers)
        _require_virtual_market_research_only_authority(
            context="system acceptance",
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            execution_surface=self.execution_surface,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "surface_kind": "SYSTEM_ACCEPTANCE",
            "status": self.status.value,
            "blockers": self.blockers,
            "evidence_refs": self.evidence_refs,
            "canonical_blocker_codes": self.canonical_blocker_codes,
            "execution_allowed": self.execution_allowed,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
            "execution_surface": self.execution_surface.value,
            "spot": self.spot.to_payload(),
            "futures": self.futures.to_payload(),
        }

    @classmethod
    def derive(
        cls,
        spot: MarketAcceptanceResult,
        futures: MarketAcceptanceResult,
    ) -> Self:
        """Derive system status without accepting combined PnL or Sharpe inputs."""

        status = _derive_system_status(spot.status, futures.status)
        blockers = tuple(dict.fromkeys((*spot.blockers, *futures.blockers)))
        if status is not AcceptanceStatus.PASS:
            blockers = tuple(dict.fromkeys((*blockers, SYSTEM_STATUS_BLOCKERS[status])))
        return cls(
            spot=spot,
            futures=futures,
            status=status,
            blockers=blockers,
            evidence_refs=tuple(
                dict.fromkeys((*spot.evidence_refs, *futures.evidence_refs))
            ),
        )


def render_system_acceptance_markdown(acceptance: SystemResearchAcceptance) -> str:
    """Render a report that keeps Spot and Futures acceptance visible separately."""

    spot = acceptance.spot
    futures = acceptance.futures
    spot_blockers = ", ".join(spot.blockers) if spot.blockers else "NONE"
    spot_evidence_refs = ", ".join(spot.evidence_refs)
    futures_blockers = ", ".join(futures.blockers) if futures.blockers else "NONE"
    futures_evidence_refs = ", ".join(futures.evidence_refs)
    system_blockers = ", ".join(acceptance.blockers) if acceptance.blockers else "NONE"
    canonical_blockers = (
        ", ".join(acceptance.canonical_blocker_codes)
        if acceptance.canonical_blocker_codes
        else "NONE"
    )
    return render_professional_summary(
        title="Virtual System Acceptance RESEARCH",
        observed_at=" / ".join(acceptance.evidence_refs[:2]) or "system-acceptance",
        status=acceptance.status.value,
        summary=(
            "This report keeps Spot and USD_M Futures acceptance separate. "
            "The system gate passes only when both markets pass; any failing "
            "market blocks the system result."
        ),
        sections=(
            (
                "Overview",
                (
                    "- Surface kind: `SYSTEM_ACCEPTANCE`",
                    f"- System status: `{acceptance.status.value}`",
                    "- Execution: `NO_TRADE`",
                    f"- Promotion: `{acceptance.promotion_status}`",
                    f"- Live eligibility: `{acceptance.live_eligibility_status}`",
                ),
            ),
            (
                "Spot Acceptance",
                (
                    f"- Market: `{spot.market.value}`",
                    f"- Status: `{spot.status.value}`",
                    f"- Blockers: `{spot_blockers}`",
                    f"- Evidence refs: `{spot_evidence_refs}`",
                ),
            ),
            (
                "USD_M Futures Acceptance",
                (
                    f"- Market: `{futures.market.value}`",
                    f"- Status: `{futures.status.value}`",
                    f"- Blockers: `{futures_blockers}`",
                    f"- Evidence refs: `{futures_evidence_refs}`",
                ),
            ),
            (
                "System Blockers",
                (
                    f"- Blockers: `{system_blockers}`",
                    f"- Canonical blockers: `{canonical_blockers}`",
                ),
            ),
        ),
        blockers=acceptance.blockers,
    )


@dataclass(frozen=True, slots=True)
class TwoStageProfitabilityEvidence:
    """Research-stage evidence paired with the unchanged final acceptance result."""

    research_candidate: ResearchCandidateResult
    final_acceptance: MarketAcceptanceResult
    stage_sequence: tuple[str, str] = (
        RESEARCH_CANDIDATE_STAGE,
        EXISTING_FINAL_ACCEPTANCE_STAGE,
    )
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        if self.research_candidate.market is not self.final_acceptance.market:
            raise ValueError("two-stage profitability evidence must target one market")
        if self.stage_sequence != (
            RESEARCH_CANDIDATE_STAGE,
            EXISTING_FINAL_ACCEPTANCE_STAGE,
        ):
            raise ValueError("two-stage profitability sequence is unsupported")
        _require_virtual_market_research_only_authority(
            context="two-stage profitability evidence",
            execution_allowed=self.execution_allowed,
            promotion_status=self.promotion_status,
            live_eligibility_status=self.live_eligibility_status,
            execution_surface=self.execution_surface,
        )


def evaluate_market_acceptance(
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy | None = None,
) -> MarketAcceptanceResult:
    """Evaluate one market without reading the other market's performance."""

    active_policy = policy or load_acceptance_policy()
    blockers: list[str] = []
    if not evidence.replay_state_hash.strip():
        blockers.append("REPLAY_STATE_HASH_MISSING")
    if evidence.decision_reproducibility_rate != ONE:
        blockers.append("DECISION_REPRODUCIBILITY_FAILED")
    if evidence.critical_data_gaps:
        blockers.append("CRITICAL_DATA_GAPS_PRESENT")
    if evidence.applied_duplicate_economic_events:
        blockers.append("DUPLICATE_ECONOMIC_EVENTS_APPLIED")
    if evidence.lookahead_violations:
        blockers.append("LOOKAHEAD_VIOLATIONS_PRESENT")
    if evidence.observation_days < active_policy.minimum_observation_days:
        blockers.append("OBSERVATION_WINDOW_INSUFFICIENT")
    if evidence.completed_trades < active_policy.minimum_completed_trades:
        blockers.append("TRADE_SAMPLE_INSUFFICIENT")
    if evidence.net_return <= ZERO:
        blockers.append("NET_RETURN_NOT_POSITIVE")
    if evidence.daily_sharpe is None:
        blockers.append("DAILY_SHARPE_UNAVAILABLE")
    elif evidence.daily_sharpe < active_policy.minimum_daily_sharpe:
        blockers.append("DAILY_SHARPE_BELOW_THRESHOLD")
    if evidence.profit_factor is None:
        blockers.append("PROFIT_FACTOR_UNAVAILABLE")
    elif evidence.profit_factor < active_policy.minimum_profit_factor:
        blockers.append("PROFIT_FACTOR_BELOW_THRESHOLD")
    _append_drawdown_blocker(blockers, evidence, active_policy)
    _append_futures_blockers(blockers, evidence, active_policy)
    status = _market_status_from_blockers(tuple(blockers))
    return MarketAcceptanceResult(
        market=evidence.market,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_refs=(evidence.session_id, evidence.replay_state_hash),
        policy_id=active_policy.policy_id,
    )


def evaluate_research_candidate(
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy | None = None,
) -> ResearchCandidateResult:
    """Evaluate stage-1 profitability evidence without granting final acceptance."""

    active_policy = policy or load_acceptance_policy()
    candidate_policy = active_policy.research_candidate
    blockers: list[str] = []
    if not evidence.replay_state_hash.strip():
        blockers.append("REPLAY_STATE_HASH_MISSING")
    if evidence.decision_reproducibility_rate != ONE:
        blockers.append("DECISION_REPRODUCIBILITY_FAILED")
    if evidence.critical_data_gaps:
        blockers.append("CRITICAL_DATA_GAPS_PRESENT")
    if (
        evidence.critical_data_quality_failure
        or evidence.applied_duplicate_economic_events
    ):
        blockers.append("CRITICAL_DATA_QUALITY_FAILURE_PRESENT")
    if evidence.lookahead_violations:
        blockers.append("LOOKAHEAD_VIOLATIONS_PRESENT")
    if evidence.observation_days < active_policy.minimum_observation_days:
        blockers.append("OBSERVATION_WINDOW_INSUFFICIENT")
    if evidence.completed_trades < active_policy.minimum_completed_trades:
        blockers.append("TRADE_SAMPLE_INSUFFICIENT")
    if (
        evidence.modeled_cost_expectancy_usdt
        <= candidate_policy.minimum_modeled_cost_expectancy_usdt
    ):
        blockers.append("MODELED_COST_EXPECTANCY_NOT_POSITIVE")
    if evidence.oos_expectancy_usdt <= candidate_policy.minimum_oos_expectancy_usdt:
        blockers.append("OOS_EXPECTANCY_NOT_POSITIVE")
    if not evidence.cost_stress_evidence:
        blockers.append("COST_STRESS_EVIDENCE_MISSING")
    else:
        required = set(candidate_policy.required_cost_stress_scenarios)
        actual = {item.scenario for item in evidence.cost_stress_evidence}
        if actual != required:
            blockers.append("COST_STRESS_SCENARIOS_INCOMPLETE")
    if candidate_policy.require_regime_level_attribution and not any(
        item.trade_count > 0 for item in evidence.regime_attribution
    ):
        blockers.append("REGIME_LEVEL_ATTRIBUTION_MISSING")
    _append_drawdown_blocker(blockers, evidence, active_policy)
    _append_futures_blockers(blockers, evidence, active_policy)
    if evidence.fragile_edge:
        blockers.append("FRAGILE_EDGE")
    status = _market_status_from_blockers(tuple(blockers))
    return ResearchCandidateResult(
        market=evidence.market,
        stage=RESEARCH_CANDIDATE_STAGE,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_refs=(evidence.session_id, evidence.replay_state_hash),
        policy_id=active_policy.policy_id,
    )


def evaluate_two_stage_profitability_evidence(
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy | None = None,
) -> TwoStageProfitabilityEvidence:
    """Return research-stage evidence plus the unchanged final acceptance result."""

    active_policy = policy or load_acceptance_policy()
    research_candidate = evaluate_research_candidate(evidence, active_policy)
    final_acceptance = evaluate_market_acceptance(evidence, active_policy)
    return TwoStageProfitabilityEvidence(
        research_candidate=research_candidate,
        final_acceptance=final_acceptance,
    )


def calculate_daily_returns(
    equity_curve: tuple[DailyEquityPoint, ...],
) -> tuple[Decimal, ...]:
    """Calculate daily return ratios from validated equity observations."""

    return calculate_equity_returns(cast(Sequence[EquityObservation], equity_curve))


def calculate_daily_sharpe(daily_returns: tuple[Decimal, ...]) -> Decimal | None:
    """Calculate a 365-day annualized Sharpe from daily return observations."""

    return calculate_periodic_sharpe(daily_returns, periods_per_year=365)


def default_acceptance_policy_path(repository_root: Path | None = None) -> Path:
    """Return the repository-local virtual-market acceptance policy path."""

    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "research" / "virtual_market_acceptance.yaml"


def default_blocker_registry_path(repository_root: Path | None = None) -> Path:
    """Return the repository-local canonical blocker registry path."""

    root = (repository_root or Path.cwd()).resolve()
    return root / BLOCKER_REGISTRY_PATH


def canonical_acceptance_blocker_codes(blockers: tuple[str, ...]) -> tuple[str, ...]:
    """Map virtual-market acceptance blockers to canonical blocker codes."""

    return tuple(
        dict.fromkeys(
            ACCEPTANCE_BLOCKER_CANONICAL_CODES.get(
                blocker,
                "GOV.UNKNOWN_CONTROL_CLASSIFICATION",
            )
            for blocker in blockers
        )
    )


def load_acceptance_blocker_definitions(
    blockers: tuple[str, ...],
    registry_path: Path | None = None,
) -> tuple[BlockerDefinition, ...]:
    """Resolve virtual-market acceptance blockers through the canonical registry."""

    registry = load_blocker_registry(
        (registry_path or default_blocker_registry_path()).resolve()
    )
    return tuple(
        registry.require_canonical_code(blocker_code)
        for blocker_code in canonical_acceptance_blocker_codes(blockers)
    )


def load_acceptance_policy(path: Path | None = None) -> AcceptancePolicy:
    """Load the research-only acceptance policy from the governed YAML contract."""

    resolved = (path or default_acceptance_policy_path()).resolve()
    if resolved.stat().st_size > MAX_ACCEPTANCE_POLICY_BYTES:
        raise ValueError("virtual-market acceptance policy exceeds the bounded size")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("virtual-market acceptance policy must be a mapping")
    payload = cast(Mapping[str, object], raw)
    authority = _mapping(payload.get("authority"), "authority")
    execution_surface = ExecutionSurface(
        _required_string(
            authority.get("execution_surface"),
            "execution_surface",
        )
    )
    authority_profile_id = _required_string(
        authority.get("authority_profile_id"),
        "authority_profile_id",
    )
    automation_mode = ExecutionAutomationMode(
        _required_string(
            authority.get("automation_mode"),
            "automation_mode",
        )
    )
    _require_virtual_market_research_only_authority(
        context="virtual-market acceptance policy",
        execution_allowed=_required_bool(
            authority.get("execution_allowed"),
            "execution_allowed",
        ),
        promotion_status=_required_string(
            authority.get("promotion_status"),
            "promotion_status",
        ),
        live_eligibility_status=_required_string(
            authority.get("live_eligibility_status"),
            "live_eligibility_status",
        ),
        execution_surface=execution_surface,
    )
    _require_virtual_market_policy_authority(
        context="virtual-market acceptance policy",
        execution_surface=execution_surface,
        authority_profile_id=authority_profile_id,
        automation_mode=automation_mode,
    )
    minimum_evidence = _mapping(payload.get("minimum_evidence"), "minimum_evidence")
    research_candidate_gates = _optional_mapping(
        payload.get("research_candidate_gates"),
        "research_candidate_gates",
    )
    performance_gates = _mapping(
        payload.get("performance_gates"),
        "performance_gates",
    )
    risk_gates = _mapping(payload.get("risk_gates"), "risk_gates")
    anti_masking = _mapping(payload.get("anti_masking"), "anti_masking")
    return AcceptancePolicy(
        policy_id=_required_string(payload.get("policy_id"), "policy_id"),
        minimum_observation_days=_required_int(
            minimum_evidence.get("minimum_observation_days"),
            "minimum_observation_days",
        ),
        minimum_completed_trades=_required_int(
            minimum_evidence.get("minimum_completed_trades"),
            "minimum_completed_trades",
        ),
        minimum_daily_sharpe=_required_decimal(
            performance_gates.get("minimum_daily_sharpe"),
            "minimum_daily_sharpe",
        ),
        minimum_profit_factor=_required_decimal(
            performance_gates.get("minimum_profit_factor"),
            "minimum_profit_factor",
        ),
        maximum_spot_drawdown=_required_decimal(
            risk_gates.get("maximum_spot_drawdown"),
            "maximum_spot_drawdown",
        ),
        maximum_futures_drawdown=_required_decimal(
            risk_gates.get("maximum_futures_drawdown"),
            "maximum_futures_drawdown",
        ),
        maximum_futures_margin_utilization=_required_decimal(
            risk_gates.get("maximum_futures_margin_utilization"),
            "maximum_futures_margin_utilization",
        ),
        research_candidate=ResearchCandidatePolicy(
            minimum_modeled_cost_expectancy_usdt=_optional_decimal_with_default(
                research_candidate_gates.get("minimum_modeled_cost_expectancy_usdt"),
                "minimum_modeled_cost_expectancy_usdt",
                ZERO,
            ),
            minimum_oos_expectancy_usdt=_optional_decimal_with_default(
                research_candidate_gates.get("minimum_oos_expectancy_usdt"),
                "minimum_oos_expectancy_usdt",
                ZERO,
            ),
            required_cost_stress_scenarios=_optional_string_tuple_with_default(
                research_candidate_gates.get("required_cost_stress_scenarios"),
                "required_cost_stress_scenarios",
                DEFAULT_REQUIRED_COST_STRESS_SCENARIOS,
            ),
            require_regime_level_attribution=_optional_bool_with_default(
                research_candidate_gates.get("require_regime_level_attribution"),
                "require_regime_level_attribution",
                True,
            ),
        ),
        hard_fail_gates=_required_string_tuple(
            payload.get("hard_fail_gates"),
            "hard_fail_gates",
        ),
        system_acceptance_operator=_required_string(
            anti_masking.get("system_acceptance_operator"),
            "system_acceptance_operator",
        ),
        combined_pnl_gate_allowed=_required_bool(
            anti_masking.get("combined_pnl_gate_allowed"),
            "combined_pnl_gate_allowed",
        ),
        combined_sharpe_gate_allowed=_required_bool(
            anti_masking.get("combined_sharpe_gate_allowed"),
            "combined_sharpe_gate_allowed",
        ),
        combined_equity_gate_allowed=_required_bool(
            anti_masking.get("combined_equity_gate_allowed"),
            "combined_equity_gate_allowed",
        ),
        execution_surface=ExecutionSurface(
            _required_string(
                authority.get("execution_surface"),
                "execution_surface",
            )
        ),
        authority_profile_id=authority_profile_id,
        automation_mode=automation_mode,
    )


def _append_drawdown_blocker(
    blockers: list[str],
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy,
) -> None:
    max_allowed = (
        policy.maximum_spot_drawdown
        if evidence.market is VirtualMarket.SPOT
        else policy.maximum_futures_drawdown
    )
    if evidence.max_drawdown > max_allowed:
        blockers.append("MAX_DRAWDOWN_ABOVE_THRESHOLD")


def _append_futures_blockers(
    blockers: list[str],
    evidence: MarketPerformanceEvidence,
    policy: AcceptancePolicy,
) -> None:
    if evidence.market is not VirtualMarket.USD_M_FUTURES:
        return
    if evidence.liquidation_events:
        blockers.append("FUTURES_LIQUIDATION_OCCURRED")
    if evidence.peak_margin_utilization is None:
        blockers.append("FUTURES_MARGIN_UTILIZATION_UNAVAILABLE")
    elif evidence.peak_margin_utilization > policy.maximum_futures_margin_utilization:
        blockers.append("FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD")


def _market_status_from_blockers(blockers: tuple[str, ...]) -> AcceptanceStatus:
    if not blockers:
        return AcceptanceStatus.PASS
    for status, classified_blockers in MARKET_STATUS_BLOCKER_PRECEDENCE:
        if any(blocker in classified_blockers for blocker in blockers):
            return status
    if any(blocker.endswith("_INSUFFICIENT") for blocker in blockers):
        return AcceptanceStatus.INSUFFICIENT_EVIDENCE
    return AcceptanceStatus.FAIL


def _derive_system_status(
    spot_status: AcceptanceStatus,
    futures_status: AcceptanceStatus,
) -> AcceptanceStatus:
    if spot_status is AcceptanceStatus.PASS and futures_status is AcceptanceStatus.PASS:
        return AcceptanceStatus.PASS
    for status in SYSTEM_STATUS_PRECEDENCE:
        if status in {spot_status, futures_status}:
            return status
    return AcceptanceStatus.NOT_EVALUATED


def _require_system_status_blockers(
    status: AcceptanceStatus,
    system_blockers: tuple[str, ...],
) -> None:
    allowed = set(required_system_status_blockers())
    unexpected = tuple(blocker for blocker in system_blockers if blocker not in allowed)
    if unexpected:
        raise ValueError("system acceptance contains unknown synthetic blocker")
    if status is AcceptanceStatus.PASS:
        if system_blockers:
            raise ValueError(
                "passing system acceptance cannot contain synthetic blockers"
            )
        return
    expected = SYSTEM_STATUS_BLOCKERS[status]
    if system_blockers != (expected,):
        raise ValueError("system acceptance synthetic blockers must match status")


def _require_decimal_ratio(
    name: str,
    value: Decimal,
    *,
    min_value: Decimal = ZERO,
    max_value: Decimal | None = ONE,
) -> None:
    _require_finite_decimal(name, value)
    if value < min_value or (max_value is not None and value > max_value):
        if max_value is None:
            raise ValueError(f"{name} must be at least {min_value}")
        raise ValueError(f"{name} must be between {min_value} and {max_value}")


def _require_optional_nonnegative(name: str, value: Decimal | None) -> None:
    if value is None:
        return
    _require_finite_decimal(name, value)
    if value < ZERO:
        raise ValueError(f"{name} cannot be negative")


def _require_finite_decimal(name: str, value: Decimal) -> None:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")


def _require_nonnegative_int(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"virtual-market acceptance policy {name} must be a mapping")
    return cast(Mapping[str, object], value)


def _optional_mapping(value: object, name: str) -> Mapping[str, object]:
    if value is None:
        return {}
    return _mapping(value, name)


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"virtual-market acceptance policy {name} is required")
    return value


def _required_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"virtual-market acceptance policy {name} must be an integer")
    return value


def _required_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"virtual-market acceptance policy {name} must be a boolean")
    return value


def _required_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"virtual-market acceptance policy {name} must be a string")
    decimal_value = Decimal(value)
    _require_finite_decimal(name, decimal_value)
    return decimal_value


def _required_string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"virtual-market acceptance policy {name} must be a list")
    values = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(
            f"virtual-market acceptance policy {name} must contain non-empty strings"
        )
    return values


def _optional_string_tuple_with_default(
    value: object,
    name: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None:
        return default
    return _required_string_tuple(value, name)


def _optional_bool_with_default(value: object, name: str, default: bool) -> bool:
    if value is None:
        return default
    return _required_bool(value, name)


def _optional_decimal_with_default(
    value: object,
    name: str,
    default: Decimal,
) -> Decimal:
    if value is None:
        return default
    return _required_decimal(value, name)
