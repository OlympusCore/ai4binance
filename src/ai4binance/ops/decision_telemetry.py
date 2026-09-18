"""Decision telemetry and performance evidence fabric.

This module is intentionally report-only. It records input-process-output-outcome
lineage for research and paper evidence without granting execution authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import cast

from ai4binance.enterprise import GpuTelemetryAssessment
from ai4binance.ops.user_reports import (
    UserReportPaths,
    render_professional_summary,
    user_report_paths,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import (
    VerifiedWriteResult,
    write_json_object_verified,
)
from ai4binance.storage.jsonl import (
    AuditEvent,
    JsonlAuditStore,
)


class LineageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


class DecisionTelemetryStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class MarketType(StrEnum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    ENTERPRISE_SUMMARY = "ENTERPRISE_SUMMARY"


def _coerce_market_type(market_type: MarketType | str) -> MarketType:
    if isinstance(market_type, MarketType):
        return market_type
    normalized = str(market_type).strip().upper()
    try:
        return MarketType(normalized)
    except ValueError as exc:
        raise ValueError(
            "market type must be SPOT, FUTURES, or ENTERPRISE_SUMMARY"
        ) from exc


class OutcomeLifecycle(StrEnum):
    DECISION_RECORDED = "DECISION_RECORDED"
    ACTUAL_PATH_RECORDED = "ACTUAL_PATH_RECORDED"
    WAITING_FOR_OUTCOME = "WAITING_FOR_OUTCOME"
    OUTCOME_OBSERVED = "OUTCOME_OBSERVED"
    COUNTERFACTUAL_COMPLETE = "COUNTERFACTUAL_COMPLETE"
    ATTRIBUTION_COMPLETE = "ATTRIBUTION_COMPLETE"
    TELEMETRY_COMMITTED = "TELEMETRY_COMMITTED"
    AUDITED = "AUDITED"
    LEARNING_EVALUATED = "LEARNING_EVALUATED"
    CLOSED = "CLOSED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INCONSISTENT_LINEAGE = "INCONSISTENT_LINEAGE"
    COUNTERFACTUAL_INVALID = "COUNTERFACTUAL_INVALID"
    ATTRIBUTION_UNRESOLVED = "ATTRIBUTION_UNRESOLVED"
    GOVERNANCE_CONFLICT = "GOVERNANCE_CONFLICT"


class EvidenceQuality(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class CounterfactualType(StrEnum):
    NO_DGE_INTERVENTION = "NO_DGE_INTERVENTION"
    RULE_ABLATION = "RULE_ABLATION"
    BLOCKER_ABLATION = "BLOCKER_ABLATION"
    ALTERNATIVE_CANDIDATE = "ALTERNATIVE_CANDIDATE"
    HOLD_CASH = "HOLD_CASH"
    BENCHMARK = "BENCHMARK"


class AttributionMethod(StrEnum):
    COUNTERFACTUAL_DELTA = "COUNTERFACTUAL_DELTA"
    RULE_ABLATION_DELTA = "RULE_ABLATION_DELTA"
    BENCHMARK_DELTA = "BENCHMARK_DELTA"
    OBSERVATIONAL_ESTIMATE = "OBSERVATIONAL_ESTIMATE"


class OpportunityCostType(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    TIMING = "TIMING"
    BLOCKER = "BLOCKER"
    RISK_VETO = "RISK_VETO"
    VALIDATION_VETO = "VALIDATION_VETO"
    GOVERNANCE_VETO = "GOVERNANCE_VETO"
    STRATEGY_SELECTION = "STRATEGY_SELECTION"
    CAPITAL_ALLOCATION = "CAPITAL_ALLOCATION"
    EXECUTION = "EXECUTION"
    LIQUIDITY = "LIQUIDITY"
    LATENCY = "LATENCY"
    DATA_QUALITY = "DATA_QUALITY"
    STALE_DATA = "STALE_DATA"


class BlockerOutcome(StrEnum):
    PROTECTIVE_BLOCK = "PROTECTIVE_BLOCK"
    FALSE_BLOCK = "FALSE_BLOCK"
    NEUTRAL_BLOCK = "NEUTRAL_BLOCK"
    INDETERMINATE = "INDETERMINATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DecisionEffectivenessClass(StrEnum):
    TAKEN_PROFITABLE = "TAKEN_PROFITABLE"
    TAKEN_LOSS = "TAKEN_LOSS"
    REJECTED_WOULD_PROFIT = "REJECTED_WOULD_PROFIT"
    REJECTED_WOULD_LOSE = "REJECTED_WOULD_LOSE"
    WAIT_IMPROVED_ENTRY = "WAIT_IMPROVED_ENTRY"
    WAIT_MISSED_MOVE = "WAIT_MISSED_MOVE"
    BLOCKED_AVOIDED_LOSS = "BLOCKED_AVOIDED_LOSS"
    BLOCKED_FOREGONE_PROFIT = "BLOCKED_FOREGONE_PROFIT"
    INDETERMINATE = "INDETERMINATE"


class DgeEffectivenessStatus(StrEnum):
    """Non-causal research classification for measured DGE interventions."""

    EFFECTIVE = "EFFECTIVE"
    MIXED = "MIXED"
    INEFFECTIVE = "INEFFECTIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class TelemetryDomain(StrEnum):
    SYSTEM_HEALTH = "SYSTEM_HEALTH"
    DATA_QUALITY = "DATA_QUALITY"
    LINEAGE_COMPLETENESS = "LINEAGE_COMPLETENESS"
    DECISION_EFFECTIVENESS = "DECISION_EFFECTIVENESS"
    BLOCKER_EFFECTIVENESS = "BLOCKER_EFFECTIVENESS"
    RISK_EFFECTIVENESS = "RISK_EFFECTIVENESS"
    VALIDATION_EFFECTIVENESS = "VALIDATION_EFFECTIVENESS"
    DGE_EFFECTIVENESS = "DGE_EFFECTIVENESS"
    EXECUTION_QUALITY = "EXECUTION_QUALITY"
    TRADING_PERFORMANCE = "TRADING_PERFORMANCE"
    OPPORTUNITY_COST = "OPPORTUNITY_COST"
    STRATEGY_DRIFT = "STRATEGY_DRIFT"
    REGIME_DEGRADATION = "REGIME_DEGRADATION"
    LEARNING_EFFECTIVENESS = "LEARNING_EFFECTIVENESS"


class AcceptanceGateStatus(StrEnum):
    PASS = "PASS"  # noqa: S105  # nosec B105
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INFORMATIONAL_ONLY = "INFORMATIONAL_ONLY"


_GENESIS_HASH = "GENESIS"
_NO_TRADE_STATES = frozenset({"NO_TRADE", "WAIT", "WATCH_ONLY"})
_FORBIDDEN_EXECUTION_PREFIXES = ("LIVE_",)


@dataclass(frozen=True, slots=True)
class DecisionInputRecord:
    """Canonical decision-cycle input references."""

    cycle_id: str
    snapshot_id: str
    observed_at: datetime
    source_data_ids: tuple[str, ...]
    feature_versions: Mapping[str, str]
    evidence_ids: tuple[str, ...]
    policy_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        _require_text("cycle id", self.cycle_id)
        _require_text("snapshot id", self.snapshot_id)
        _require_aware_time("input observation", self.observed_at)
        _require_unique_nonblank("source data ids", self.source_data_ids)
        _require_unique_nonblank("evidence ids", self.evidence_ids)
        _require_nonempty_mapping("feature versions", self.feature_versions)
        _require_nonempty_mapping("policy versions", self.policy_versions)

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


@dataclass(frozen=True, slots=True)
class DecisionProcessRecord:
    """Canonical decision-process references and fail-closed authority state."""

    decision_id: str
    risk_assessment_id: str
    validation_id: str
    governance_evidence_ids: tuple[str, ...]
    advisory_signal_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    decision_state: str = "NO_TRADE"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("decision id", self.decision_id)
        _require_text("risk assessment id", self.risk_assessment_id)
        _require_text("validation id", self.validation_id)
        _require_text("decision state", self.decision_state)
        _require_unique_nonblank(
            "governance evidence ids", self.governance_evidence_ids
        )
        _require_unique_nonblank("advisory signal refs", self.advisory_signal_refs)
        _require_unique_nonblank_or_empty("blockers", self.blockers)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("decision telemetry cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["execution_allowed"] = False
        return payload


@dataclass(frozen=True, slots=True)
class DecisionOutcomeRecord:
    """Measured decision outcome, including measurable NO_TRADE counterfactuals."""

    outcome_id: str
    decision_id: str
    observed_at: datetime
    decision_state: str = "NO_TRADE"
    execution_status: str = "NO_ACTION"
    observation_window_minutes: int | None = None
    realized_pnl_usdt: Decimal | None = None
    max_favorable_move_usdt: Decimal | None = None
    max_adverse_move_usdt: Decimal | None = None
    counterfactual_return_usdt: Decimal | None = None
    no_trade_reason: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("outcome id", self.outcome_id)
        _require_text("decision id", self.decision_id)
        _require_text("decision state", self.decision_state)
        _require_text("execution status", self.execution_status)
        _require_aware_time("outcome observation", self.observed_at)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or self.execution_status.startswith(_FORBIDDEN_EXECUTION_PREFIXES)
        ):
            raise ValueError("decision outcome cannot authorize live trading")
        if self.observation_window_minutes is not None and (
            self.observation_window_minutes < 1
        ):
            raise ValueError("observation window must be positive")
        for label, value in (
            ("realized pnl", self.realized_pnl_usdt),
            ("maximum favorable move", self.max_favorable_move_usdt),
            ("maximum adverse move", self.max_adverse_move_usdt),
            ("counterfactual return", self.counterfactual_return_usdt),
        ):
            if value is not None and not value.is_finite():
                raise ValueError(f"{label} must be finite")

    @property
    def measurable_no_trade(self) -> bool:
        return (
            self.decision_state in _NO_TRADE_STATES
            and self.observation_window_minutes is not None
            and self.max_favorable_move_usdt is not None
            and self.max_adverse_move_usdt is not None
            and self.counterfactual_return_usdt is not None
        )

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["execution_allowed"] = False
        payload["measurable_no_trade"] = self.measurable_no_trade
        return payload


@dataclass(frozen=True, slots=True)
class CounterfactualOutcome:
    """Hindsight-safe shadow outcome; never executable and never live authority."""

    counterfactual_id: str
    counterfactual_type: CounterfactualType
    originating_decision_id: str
    snapshot_id: str
    changed_dimension: str
    retained_safety_controls: tuple[str, ...]
    hypothetical_decision_state: str
    hypothetical_economic_outcome_usdt: Decimal
    methodology: str
    assumptions: tuple[str, ...]
    evidence_quality: EvidenceQuality
    confidence: Decimal
    changed_rule_id: str | None = None
    hindsight_safe: bool = True
    cannot_execute: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("counterfactual id", self.counterfactual_id)
        _require_text("originating decision id", self.originating_decision_id)
        _require_text("snapshot id", self.snapshot_id)
        _require_text("changed dimension", self.changed_dimension)
        _require_text("hypothetical decision state", self.hypothetical_decision_state)
        _require_text("counterfactual methodology", self.methodology)
        _require_unique_nonblank(
            "retained safety controls", self.retained_safety_controls
        )
        _require_unique_nonblank("counterfactual assumptions", self.assumptions)
        _require_finite_decimal(
            "hypothetical economic outcome",
            self.hypothetical_economic_outcome_usdt,
        )
        _require_confidence("counterfactual confidence", self.confidence)
        if self.changed_rule_id is not None and not self.changed_rule_id.strip():
            raise ValueError("changed rule id cannot be blank")
        if (
            not self.hindsight_safe
            or not self.cannot_execute
            or self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
            or self.hypothetical_decision_state.startswith(
                _FORBIDDEN_EXECUTION_PREFIXES
            )
        ):
            raise ValueError("counterfactual outcomes cannot authorize execution")

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["execution_allowed"] = False
        return payload


@dataclass(frozen=True, slots=True)
class OutcomeAttribution:
    """Method-bound economic attribution; attribution is evidence, not fact."""

    attribution_id: str
    decision_id: str
    market_type: MarketType
    attribution_method: AttributionMethod
    evidence_quality: EvidenceQuality
    confidence: Decimal
    assumptions: tuple[str, ...]
    opportunity_cost_type: OpportunityCostType | None = None
    market_effect_usdt: Decimal | None = None
    strategy_effect_usdt: Decimal | None = None
    decision_effect_usdt: Decimal | None = None
    governance_effect_usdt: Decimal | None = None
    risk_effect_usdt: Decimal | None = None
    validation_effect_usdt: Decimal | None = None
    execution_effect_usdt: Decimal | None = None
    fee_effect_usdt: Decimal | None = None
    slippage_effect_usdt: Decimal | None = None
    funding_effect_usdt: Decimal | None = None
    latency_effect_usdt: Decimal | None = None
    data_quality_effect_usdt: Decimal | None = None
    avoided_loss_usdt: Decimal | None = None
    foregone_profit_usdt: Decimal | None = None
    opportunity_cost_usdt: Decimal | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        normalized_market_type = _coerce_market_type(self.market_type)
        object.__setattr__(self, "market_type", normalized_market_type)
        _require_text("attribution id", self.attribution_id)
        _require_text("decision id", self.decision_id)
        _require_confidence("attribution confidence", self.confidence)
        _require_unique_nonblank("attribution assumptions", self.assumptions)
        for label, value in (
            ("market effect", self.market_effect_usdt),
            ("strategy effect", self.strategy_effect_usdt),
            ("decision effect", self.decision_effect_usdt),
            ("governance effect", self.governance_effect_usdt),
            ("risk effect", self.risk_effect_usdt),
            ("validation effect", self.validation_effect_usdt),
            ("execution effect", self.execution_effect_usdt),
            ("fee effect", self.fee_effect_usdt),
            ("slippage effect", self.slippage_effect_usdt),
            ("funding effect", self.funding_effect_usdt),
            ("latency effect", self.latency_effect_usdt),
            ("data quality effect", self.data_quality_effect_usdt),
            ("avoided loss", self.avoided_loss_usdt),
            ("foregone profit", self.foregone_profit_usdt),
            ("opportunity cost", self.opportunity_cost_usdt),
        ):
            _require_optional_finite_decimal(label, value)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("outcome attribution cannot authorize trading")

    @property
    def has_economic_evidence(self) -> bool:
        return any(
            value is not None
            for value in (
                self.market_effect_usdt,
                self.strategy_effect_usdt,
                self.decision_effect_usdt,
                self.governance_effect_usdt,
                self.risk_effect_usdt,
                self.validation_effect_usdt,
                self.execution_effect_usdt,
                self.avoided_loss_usdt,
                self.foregone_profit_usdt,
                self.opportunity_cost_usdt,
            )
        )

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["has_economic_evidence"] = self.has_economic_evidence
        payload["execution_allowed"] = False
        return payload


@dataclass(frozen=True, slots=True)
class BlockerEffectivenessRecord:
    """Retrospective blocker effectiveness classification."""

    blocker_id: str
    blocker_type: str
    policy_id: str
    decision_id: str
    outcome_class: BlockerOutcome
    evaluation_horizon_minutes: int
    evidence_quality: EvidenceQuality
    counterfactual_id: str
    avoided_loss_usdt: Decimal | None = None
    foregone_profit_usdt: Decimal | None = None
    changed_rule_id: str | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("blocker id", self.blocker_id)
        _require_text("blocker type", self.blocker_type)
        _require_text("policy id", self.policy_id)
        _require_text("decision id", self.decision_id)
        _require_text("counterfactual id", self.counterfactual_id)
        if self.evaluation_horizon_minutes < 1:
            raise ValueError("blocker evaluation horizon must be positive")
        _require_optional_finite_decimal("avoided loss", self.avoided_loss_usdt)
        _require_optional_finite_decimal("foregone profit", self.foregone_profit_usdt)
        if self.changed_rule_id is not None and not self.changed_rule_id.strip():
            raise ValueError("changed rule id cannot be blank")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("blocker effectiveness cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["execution_allowed"] = False
        return payload


@dataclass(frozen=True, slots=True)
class DecisionEffectivenessRecord:
    """Decision-quality label separated from raw trading PnL."""

    decision_id: str
    market_type: MarketType
    effectiveness_class: DecisionEffectivenessClass
    evidence_quality: EvidenceQuality
    observation_window_minutes: int
    counterfactual_refs: tuple[str, ...]
    attribution_refs: tuple[str, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        normalized_market_type = _coerce_market_type(self.market_type)
        object.__setattr__(self, "market_type", normalized_market_type)
        _require_text("decision id", self.decision_id)
        if self.observation_window_minutes < 1:
            raise ValueError("decision effectiveness window must be positive")
        _require_unique_nonblank(
            "decision effectiveness counterfactual refs",
            self.counterfactual_refs,
        )
        _require_unique_nonblank_or_empty(
            "decision effectiveness attribution refs",
            self.attribution_refs,
        )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("decision effectiveness cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["execution_allowed"] = False
        return payload


@dataclass(frozen=True, slots=True)
class MetricEvidence:
    """One canonical telemetry metric with evidence references."""

    metric_id: str
    domain: TelemetryDomain
    value: Decimal
    unit: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("metric id", self.metric_id)
        _require_text("metric unit", self.unit)
        _require_finite_decimal("metric value", self.value)
        _require_unique_nonblank("metric evidence refs", self.evidence_refs)

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], to_primitive(self))


@dataclass(frozen=True, slots=True)
class CanonicalTelemetrySnapshot:
    """Canonical operational, decision, economic, and governance telemetry."""

    telemetry_id: str
    observed_at: datetime
    market_type: MarketType
    metrics: tuple[MetricEvidence, ...]
    lineage_complete: bool
    evidence_quality: EvidenceQuality
    blockers: tuple[str, ...] = ()
    gate_eligible: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        normalized_market_type = _coerce_market_type(self.market_type)
        object.__setattr__(self, "market_type", normalized_market_type)
        _require_text("telemetry id", self.telemetry_id)
        _require_aware_time("telemetry observation", self.observed_at)
        if not self.metrics:
            raise ValueError("canonical telemetry requires metrics")
        _require_unique_nonblank(
            "telemetry metric ids", tuple(metric.metric_id for metric in self.metrics)
        )
        _require_unique_nonblank_or_empty("telemetry blockers", self.blockers)
        if self.market_type is MarketType.ENTERPRISE_SUMMARY and self.gate_eligible:
            raise ValueError("enterprise summary telemetry cannot be gate eligible")
        if not self.lineage_complete and self.gate_eligible:
            raise ValueError("incomplete lineage cannot be acceptance eligible")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("canonical telemetry cannot authorize trading")

    @property
    def domains(self) -> tuple[TelemetryDomain, ...]:
        return tuple(dict.fromkeys(metric.domain for metric in self.metrics))

    def to_payload(self) -> dict[str, object]:
        return {
            "telemetry_id": self.telemetry_id,
            "observed_at": self.observed_at.isoformat(),
            "market_type": self.market_type.value,
            "domains": [domain.value for domain in self.domains],
            "metrics": [metric.to_payload() for metric in self.metrics],
            "lineage_complete": self.lineage_complete,
            "evidence_quality": self.evidence_quality.value,
            "blockers": list(self.blockers),
            "gate_eligible": self.gate_eligible,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class PerformanceAcceptanceResult:
    """Market-specific acceptance gate result; aggregate summaries cannot mask."""

    result_id: str
    market_type: MarketType
    gate_results: Mapping[str, AcceptanceGateStatus]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    gate_eligible: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        normalized_market_type = _coerce_market_type(self.market_type)
        object.__setattr__(self, "market_type", normalized_market_type)
        _require_text("acceptance result id", self.result_id)
        if not self.gate_results:
            raise ValueError("acceptance result requires gates")
        for gate, status in self.gate_results.items():
            if not str(gate).strip():
                raise ValueError("acceptance gate names cannot be blank")
            if not isinstance(status, AcceptanceGateStatus):
                raise ValueError("acceptance gate status is invalid")
        _require_unique_nonblank("acceptance evidence refs", self.evidence_refs)
        _require_unique_nonblank_or_empty("acceptance blockers", self.blockers)
        if self.market_type is MarketType.ENTERPRISE_SUMMARY and self.gate_eligible:
            raise ValueError("enterprise summaries cannot be acceptance gates")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("performance acceptance cannot authorize trading")

    @property
    def status(self) -> AcceptanceGateStatus:
        if self.market_type is MarketType.ENTERPRISE_SUMMARY:
            return AcceptanceGateStatus.INFORMATIONAL_ONLY
        if self.blockers or not self.gate_eligible:
            return AcceptanceGateStatus.BLOCKED
        if all(
            status is AcceptanceGateStatus.PASS for status in self.gate_results.values()
        ):
            return AcceptanceGateStatus.PASS
        return AcceptanceGateStatus.FAIL

    def to_payload(self) -> dict[str, object]:
        return {
            "result_id": self.result_id,
            "market_type": self.market_type.value,
            "status": self.status.value,
            "gate_results": {
                gate: status.value for gate, status in self.gate_results.items()
            },
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "gate_eligible": self.gate_eligible,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    """Auto-Learn candidate package; implementation and promotion stay locked."""

    candidate_id: str
    originating_findings: tuple[str, ...]
    affected_component: str
    affected_markets: tuple[MarketType, ...]
    affected_regimes: tuple[str, ...]
    baseline_metrics: tuple[MetricEvidence, ...]
    observed_metrics: tuple[MetricEvidence, ...]
    sample_size: int
    evidence_quality: EvidenceQuality
    confidence: Decimal
    hypothesis: str
    proposed_experiment: str
    affected_rule: str | None = None
    economic_delta_usdt: Decimal | None = None
    risk_delta_usdt: Decimal | None = None
    opportunity_cost_delta_usdt: Decimal | None = None
    human_review_required: bool = True
    implementation_status: str = "NOT_AUTHORIZED"
    execution_allowed: bool = False
    risk_change_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("improvement candidate id", self.candidate_id)
        _require_unique_nonblank(
            "improvement candidate originating findings",
            self.originating_findings,
        )
        _require_text("improvement candidate component", self.affected_component)
        if not self.affected_markets:
            raise ValueError("improvement candidate requires affected markets")
        if len(set(self.affected_markets)) != len(self.affected_markets):
            raise ValueError("improvement candidate markets must be unique")
        _require_unique_nonblank(
            "improvement candidate affected regimes", self.affected_regimes
        )
        if not self.baseline_metrics or not self.observed_metrics:
            raise ValueError("improvement candidate requires metric evidence")
        if self.sample_size < 1:
            raise ValueError("improvement candidate sample size must be positive")
        _require_confidence("improvement candidate confidence", self.confidence)
        _require_text("improvement candidate hypothesis", self.hypothesis)
        _require_text(
            "improvement candidate proposed experiment", self.proposed_experiment
        )
        if self.affected_rule is not None and not self.affected_rule.strip():
            raise ValueError("improvement candidate affected rule cannot be blank")
        _require_optional_finite_decimal("economic delta", self.economic_delta_usdt)
        _require_optional_finite_decimal("risk delta", self.risk_delta_usdt)
        _require_optional_finite_decimal(
            "opportunity cost delta",
            self.opportunity_cost_delta_usdt,
        )
        if (
            not self.human_review_required
            or self.implementation_status != "NOT_AUTHORIZED"
            or self.execution_allowed
            or self.risk_change_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("improvement candidates cannot authorize changes")

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload["execution_allowed"] = False
        payload["risk_change_allowed"] = False
        return payload


@dataclass(frozen=True, slots=True)
class DgeRuleEffectivenessMetrics:
    """One-rule-at-a-time DGE shadow outcome aggregation."""

    rule_id: str
    activation_count: int
    evaluated_count: int
    protective_block_count: int
    false_block_count: int
    loss_avoided_usdt: Decimal
    profit_missed_usdt: Decimal
    evidence_refs: tuple[str, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("DGE rule id", self.rule_id)
        _require_unique_nonblank("DGE rule evidence refs", self.evidence_refs)
        for label, count in (
            ("activation count", self.activation_count),
            ("evaluated count", self.evaluated_count),
            ("protective block count", self.protective_block_count),
            ("false block count", self.false_block_count),
        ):
            if count < 0:
                raise ValueError(f"DGE rule {label} cannot be negative")
        if self.evaluated_count > self.activation_count:
            raise ValueError("DGE rule evaluated count exceeds activations")
        if self.protective_block_count + self.false_block_count > self.evaluated_count:
            raise ValueError("DGE rule classified outcomes exceed evaluated outcomes")
        for label, amount in (
            ("loss avoided", self.loss_avoided_usdt),
            ("profit missed", self.profit_missed_usdt),
        ):
            if not amount.is_finite() or amount < Decimal("0"):
                raise ValueError(f"DGE rule {label} must be finite and non-negative")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE rule metrics cannot authorize trading")

    @property
    def counterfactual_coverage(self) -> Decimal:
        if self.activation_count < 1:
            return Decimal("0")
        return _ratio(self.evaluated_count, self.activation_count)

    @property
    def precision(self) -> Decimal | None:
        classified = self.protective_block_count + self.false_block_count
        if classified < 1:
            return None
        return _ratio(self.protective_block_count, classified)

    @property
    def net_value_usdt(self) -> Decimal:
        return self.loss_avoided_usdt - self.profit_missed_usdt

    @property
    def status(self) -> DgeEffectivenessStatus:
        if self.activation_count < 1:
            return DgeEffectivenessStatus.NOT_EVALUABLE
        if self.evaluated_count < self.activation_count:
            return DgeEffectivenessStatus.INSUFFICIENT_EVIDENCE
        if self.protective_block_count and not self.false_block_count:
            return DgeEffectivenessStatus.EFFECTIVE
        if self.false_block_count and not self.protective_block_count:
            return DgeEffectivenessStatus.INEFFECTIVE
        return DgeEffectivenessStatus.MIXED

    def to_payload(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "status": self.status.value,
            "activation_count": self.activation_count,
            "evaluated_count": self.evaluated_count,
            "counterfactual_coverage": str(self.counterfactual_coverage),
            "protective_block_count": self.protective_block_count,
            "false_block_count": self.false_block_count,
            "precision": (str(self.precision) if self.precision is not None else None),
            "loss_avoided_usdt": str(self.loss_avoided_usdt),
            "profit_missed_usdt": str(self.profit_missed_usdt),
            "net_value_usdt": str(self.net_value_usdt),
            "evidence_refs": list(self.evidence_refs),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class DgeEffectivenessMetrics:
    """Deterministic DGE intervention effectiveness metrics."""

    sample_size: int
    intervention_count: int
    protective_block_count: int
    false_block_count: int
    loss_avoided_usdt: Decimal
    profit_missed_usdt: Decimal
    drawdown_without_dge_pct: Decimal
    drawdown_with_dge_pct: Decimal
    counterfactual_expectancy_delta_usdt: Decimal
    computed_at: datetime
    approved_trade_count: int = 0
    approved_trade_loss_count: int = 0
    approved_trade_net_pnl_usdt: Decimal = Decimal("0")
    approved_decision_count: int | None = None
    counterfactual_evaluated_count: int | None = None
    decision_stability_rate: Decimal = Decimal("1")
    replay_match_rate: Decimal = Decimal("1")
    rule_metrics: tuple[DgeRuleEffectivenessMetrics, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_aware_time("DGE metric computation", self.computed_at)
        if self.sample_size < 1:
            raise ValueError("DGE sample size must be positive")
        for label, value in (
            ("intervention count", self.intervention_count),
            ("protective block count", self.protective_block_count),
            ("false block count", self.false_block_count),
            ("approved trade count", self.approved_trade_count),
            ("approved trade loss count", self.approved_trade_loss_count),
        ):
            if value < 0 or value > self.sample_size:
                raise ValueError(f"{label} is outside sample bounds")
        if (
            self.protective_block_count + self.false_block_count
            > self.intervention_count
        ):
            raise ValueError("DGE classified blocks exceed interventions")
        for metric_label, metric_value in (
            ("loss avoided", self.loss_avoided_usdt),
            ("profit missed", self.profit_missed_usdt),
            ("drawdown without DGE", self.drawdown_without_dge_pct),
            ("drawdown with DGE", self.drawdown_with_dge_pct),
            (
                "counterfactual expectancy delta",
                self.counterfactual_expectancy_delta_usdt,
            ),
            ("approved trade net PnL", self.approved_trade_net_pnl_usdt),
            ("decision stability rate", self.decision_stability_rate),
            ("replay match rate", self.replay_match_rate),
        ):
            if not metric_value.is_finite():
                raise ValueError(f"{metric_label} must be finite")
        for metric_label, metric_value in (
            ("decision stability rate", self.decision_stability_rate),
            ("replay match rate", self.replay_match_rate),
        ):
            if not Decimal("0") <= metric_value <= Decimal("1"):
                raise ValueError(f"{metric_label} must be between zero and one")
        if self.approved_trade_loss_count > self.approved_trade_count:
            raise ValueError("DGE approved losing trades exceed approved trades")
        if self.approved_decision_count is not None and not (
            0 <= self.approved_decision_count <= self.sample_size
        ):
            raise ValueError("DGE approved decision count is outside sample bounds")
        if self.counterfactual_evaluated_count is not None and not (
            0 <= self.counterfactual_evaluated_count <= self.intervention_count
        ):
            raise ValueError("DGE counterfactual evaluated count exceeds interventions")
        rule_ids = tuple(metric.rule_id for metric in self.rule_metrics)
        _require_unique_nonblank_or_empty("DGE rule metric ids", rule_ids)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("DGE metrics cannot authorize trading")

    @property
    def block_rate(self) -> Decimal:
        return _ratio(self.intervention_count, self.sample_size)

    @property
    def protective_block_rate(self) -> Decimal:
        return _ratio(self.protective_block_count, self.sample_size)

    @property
    def false_block_rate(self) -> Decimal:
        return _ratio(self.false_block_count, self.sample_size)

    @property
    def net_protection_value_usdt(self) -> Decimal:
        return self.loss_avoided_usdt - self.profit_missed_usdt

    @property
    def approved_count(self) -> int:
        if self.approved_decision_count is not None:
            return self.approved_decision_count
        return self.sample_size - self.intervention_count

    @property
    def counterfactual_coverage(self) -> Decimal:
        if self.intervention_count < 1:
            return Decimal("0")
        evaluated = self.counterfactual_evaluated_count
        if evaluated is None:
            evaluated = self.protective_block_count + self.false_block_count
        return _ratio(evaluated, self.intervention_count)

    @property
    def block_precision(self) -> Decimal | None:
        classified = self.protective_block_count + self.false_block_count
        if classified < 1:
            return None
        return _ratio(self.protective_block_count, classified)

    @property
    def approved_trade_loss_rate(self) -> Decimal | None:
        if self.approved_trade_count < 1:
            return None
        return _ratio(self.approved_trade_loss_count, self.approved_trade_count)

    @property
    def approved_trade_expectancy_usdt(self) -> Decimal | None:
        if self.approved_trade_count < 1:
            return None
        return self.approved_trade_net_pnl_usdt / Decimal(self.approved_trade_count)

    @property
    def status(self) -> DgeEffectivenessStatus:
        if self.intervention_count < 1:
            return DgeEffectivenessStatus.NOT_EVALUABLE
        if self.counterfactual_coverage < Decimal("1"):
            return DgeEffectivenessStatus.INSUFFICIENT_EVIDENCE
        if self.protective_block_count and not self.false_block_count:
            return DgeEffectivenessStatus.EFFECTIVE
        if self.false_block_count and not self.protective_block_count:
            return DgeEffectivenessStatus.INEFFECTIVE
        return DgeEffectivenessStatus.MIXED

    @property
    def drawdown_reduction_pct(self) -> Decimal:
        return self.drawdown_without_dge_pct - self.drawdown_with_dge_pct

    def to_payload(self) -> dict[str, object]:
        payload = cast(dict[str, object], to_primitive(self))
        payload.update(
            {
                "block_rate": str(self.block_rate),
                "protective_block_rate": str(self.protective_block_rate),
                "false_block_rate": str(self.false_block_rate),
                "approved_count": self.approved_count,
                "counterfactual_evaluated_count": (
                    self.counterfactual_evaluated_count
                    if self.counterfactual_evaluated_count is not None
                    else self.protective_block_count + self.false_block_count
                ),
                "counterfactual_coverage": str(self.counterfactual_coverage),
                "block_precision": (
                    str(self.block_precision)
                    if self.block_precision is not None
                    else None
                ),
                "approved_trade_loss_rate": (
                    str(self.approved_trade_loss_rate)
                    if self.approved_trade_loss_rate is not None
                    else None
                ),
                "approved_trade_expectancy_usdt": (
                    str(self.approved_trade_expectancy_usdt)
                    if self.approved_trade_expectancy_usdt is not None
                    else None
                ),
                "net_protection_value_usdt": str(self.net_protection_value_usdt),
                "drawdown_reduction_pct": str(self.drawdown_reduction_pct),
                "status": self.status.value,
                "rule_metrics": [metric.to_payload() for metric in self.rule_metrics],
                "execution_allowed": False,
            }
        )
        return payload


@dataclass(frozen=True, slots=True)
class LineageCompletenessResult:
    """Completeness gate for input-process-output-outcome evidence."""

    status: LineageStatus
    blockers: tuple[str, ...]
    missing_refs: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.status is LineageStatus.COMPLETE

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "complete": self.complete,
            "blockers": list(self.blockers),
            "missing_refs": list(self.missing_refs),
        }


@dataclass(frozen=True, slots=True)
class PerformanceEvidenceSnapshot:
    """One canonical performance evidence snapshot for audit and learning."""

    snapshot_id: str
    observed_at: datetime
    decision_input: DecisionInputRecord
    decision_process: DecisionProcessRecord
    decision_outcome: DecisionOutcomeRecord
    dge_metrics: DgeEffectivenessMetrics
    lineage: LineageCompletenessResult
    lifecycle_state: OutcomeLifecycle = OutcomeLifecycle.TELEMETRY_COMMITTED
    counterfactuals: tuple[CounterfactualOutcome, ...] = ()
    attributions: tuple[OutcomeAttribution, ...] = ()
    blocker_effectiveness: tuple[BlockerEffectivenessRecord, ...] = ()
    decision_effectiveness: tuple[DecisionEffectivenessRecord, ...] = ()
    telemetry_snapshot: CanonicalTelemetrySnapshot | None = None
    gpu_telemetry_assessment: GpuTelemetryAssessment | None = None
    acceptance_results: tuple[PerformanceAcceptanceResult, ...] = ()
    improvement_candidates: tuple[ImprovementCandidate, ...] = ()
    auto_audit_consumable: bool = True
    auto_learn_consumable: bool = True
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("performance snapshot id", self.snapshot_id)
        _require_aware_time("performance snapshot observation", self.observed_at)
        if self.snapshot_id != self.decision_input.snapshot_id:
            raise ValueError("performance snapshot id must match input snapshot id")
        if self.decision_process.decision_id != self.decision_outcome.decision_id:
            raise ValueError("decision process and outcome ids must match")
        self._validate_outcome_graph()
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("performance evidence cannot authorize trading")

    def _validate_outcome_graph(self) -> None:
        decision_id = self.decision_process.decision_id
        counterfactual_ids = tuple(
            counterfactual.counterfactual_id for counterfactual in self.counterfactuals
        )
        attribution_ids = tuple(
            attribution.attribution_id for attribution in self.attributions
        )
        _require_unique_nonblank_or_empty("counterfactual ids", counterfactual_ids)
        _require_unique_nonblank_or_empty("attribution ids", attribution_ids)
        for counterfactual in self.counterfactuals:
            if counterfactual.snapshot_id != self.snapshot_id:
                raise ValueError("counterfactual snapshot id must match snapshot")
            if counterfactual.originating_decision_id != decision_id:
                raise ValueError("counterfactual decision id must match decision")
        for attribution in self.attributions:
            if attribution.decision_id != decision_id:
                raise ValueError("attribution decision id must match decision")
        counterfactual_id_set = set(counterfactual_ids)
        attribution_id_set = set(attribution_ids)
        for blocker in self.blocker_effectiveness:
            if blocker.decision_id != decision_id:
                raise ValueError("blocker effectiveness decision id must match")
            if blocker.counterfactual_id not in counterfactual_id_set:
                raise ValueError(
                    "blocker effectiveness references unknown counterfactual"
                )
        for effectiveness in self.decision_effectiveness:
            if effectiveness.decision_id != decision_id:
                raise ValueError("decision effectiveness decision id must match")
            for ref in effectiveness.counterfactual_refs:
                if ref not in counterfactual_id_set:
                    raise ValueError(
                        "decision effectiveness references unknown counterfactual"
                    )
            for ref in effectiveness.attribution_refs:
                if ref not in attribution_id_set:
                    raise ValueError(
                        "decision effectiveness references unknown attribution"
                    )
        if self.telemetry_snapshot is not None:
            if self.telemetry_snapshot.telemetry_id != self.snapshot_id:
                raise ValueError(
                    "telemetry snapshot id must match performance snapshot"
                )
            if self.telemetry_snapshot.lineage_complete != self.lineage.complete:
                raise ValueError("telemetry lineage state must match lineage gate")
        _require_unique_nonblank_or_empty(
            "acceptance result ids",
            tuple(result.result_id for result in self.acceptance_results),
        )
        _require_unique_nonblank_or_empty(
            "improvement candidate ids",
            tuple(candidate.candidate_id for candidate in self.improvement_candidates),
        )

    @property
    def status(self) -> DecisionTelemetryStatus:
        return (
            DecisionTelemetryStatus.READY
            if self.lineage.complete
            else DecisionTelemetryStatus.BLOCKED
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "snapshot_id": self.snapshot_id,
            "observed_at": self.observed_at.isoformat(),
            "status": self.status.value,
            "decision_input": self.decision_input.to_payload(),
            "decision_process": self.decision_process.to_payload(),
            "decision_outcome": self.decision_outcome.to_payload(),
            "dge_effectiveness": self.dge_metrics.to_payload(),
            "lineage": self.lineage.to_payload(),
            "lifecycle_state": self.lifecycle_state.value,
            "counterfactuals": [
                counterfactual.to_payload() for counterfactual in self.counterfactuals
            ],
            "outcome_attributions": [
                attribution.to_payload() for attribution in self.attributions
            ],
            "blocker_effectiveness": [
                blocker.to_payload() for blocker in self.blocker_effectiveness
            ],
            "decision_effectiveness": [
                effectiveness.to_payload()
                for effectiveness in self.decision_effectiveness
            ],
            "canonical_telemetry": (
                self.telemetry_snapshot.to_payload()
                if self.telemetry_snapshot is not None
                else None
            ),
            "gpu_telemetry_assessment": (
                self.gpu_telemetry_assessment.to_payload()
                if self.gpu_telemetry_assessment is not None
                else None
            ),
            "performance_acceptance": [
                result.to_payload() for result in self.acceptance_results
            ],
            "improvement_candidates": [
                candidate.to_payload() for candidate in self.improvement_candidates
            ],
            "auto_audit_consumable": self.auto_audit_consumable,
            "auto_learn_consumable": self.auto_learn_consumable,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class DecisionTelemetryFabricRecord:
    """Hash-chained telemetry ledger record."""

    fabric_id: str
    observed_at: datetime
    performance_snapshot: PerformanceEvidenceSnapshot
    previous_record_hash: str
    payload_hash: str
    record_hash: str

    def __post_init__(self) -> None:
        _require_text("fabric id", self.fabric_id)
        _require_text("previous record hash", self.previous_record_hash)
        _require_text("payload hash", self.payload_hash)
        _require_text("record hash", self.record_hash)
        _require_aware_time("fabric observation", self.observed_at)

    @classmethod
    def seal(
        cls,
        snapshot: PerformanceEvidenceSnapshot,
        *,
        previous_record_hash: str,
    ) -> DecisionTelemetryFabricRecord:
        payload_hash = _canonical_sha256(snapshot.to_payload())
        fabric_id = f"decision-telemetry:{snapshot.snapshot_id}:{payload_hash[:16]}"
        record_hash = _canonical_sha256(
            {
                "fabric_id": fabric_id,
                "observed_at": snapshot.observed_at.isoformat(),
                "payload_hash": payload_hash,
                "previous_record_hash": previous_record_hash,
                "snapshot_id": snapshot.snapshot_id,
            }
        )
        return cls(
            fabric_id=fabric_id,
            observed_at=snapshot.observed_at,
            performance_snapshot=snapshot,
            previous_record_hash=previous_record_hash,
            payload_hash=payload_hash,
            record_hash=record_hash,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "fabric_id": self.fabric_id,
            "observed_at": self.observed_at.isoformat(),
            "previous_record_hash": self.previous_record_hash,
            "payload_hash": self.payload_hash,
            "record_hash": self.record_hash,
            "performance_snapshot": self.performance_snapshot.to_payload(),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class DecisionTelemetryWriteResult:
    record: DecisionTelemetryFabricRecord
    ledger_write: VerifiedWriteResult
    latest_json_write: VerifiedWriteResult
    latest_markdown_path: Path


@dataclass(frozen=True, slots=True)
class DecisionTelemetryLedger:
    """Append-only telemetry ledger with user-facing latest report output."""

    repository_root: Path
    durable: bool = True

    @property
    def ledger_path(self) -> Path:
        return (
            self.repository_root
            / "runtime"
            / "state"
            / "decision_telemetry"
            / "decision-telemetry.jsonl"
        )

    @property
    def latest_json_path(self) -> Path:
        return self._latest_paths().latest_json_path

    @property
    def latest_markdown_path(self) -> Path:
        return self._latest_paths().latest_markdown_path

    def verify_integrity(self) -> str:
        if not self.ledger_path.exists():
            return _GENESIS_HASH
        raw = self.ledger_path.read_bytes()
        if not raw:
            return _GENESIS_HASH
        if not raw.endswith(b"\n"):
            raise ValueError("decision telemetry ledger has a partial final record")

        expected_previous_hash = _GENESIS_HASH
        for line_number, raw_line in enumerate(raw.splitlines(), start=1):
            if not raw_line.strip():
                raise ValueError(
                    f"decision telemetry ledger line {line_number} is empty"
                )
            event = _mapping_from_json_bytes(
                raw_line,
                label=f"decision telemetry ledger line {line_number}",
            )
            payload = _mapping_field(
                event,
                "payload",
                label=f"decision telemetry ledger line {line_number}",
            )
            snapshot = _mapping_field(
                payload,
                "performance_snapshot",
                label=f"decision telemetry ledger line {line_number}",
            )
            snapshot_id = _text_field(
                snapshot,
                "snapshot_id",
                label=f"decision telemetry ledger line {line_number}",
            )
            observed_at = _text_field(
                payload,
                "observed_at",
                label=f"decision telemetry ledger line {line_number}",
            )
            payload_hash = _text_field(
                payload,
                "payload_hash",
                label=f"decision telemetry ledger line {line_number}",
            )
            previous_record_hash = _text_field(
                payload,
                "previous_record_hash",
                label=f"decision telemetry ledger line {line_number}",
            )
            fabric_id = _text_field(
                payload,
                "fabric_id",
                label=f"decision telemetry ledger line {line_number}",
            )
            record_hash = _text_field(
                payload,
                "record_hash",
                label=f"decision telemetry ledger line {line_number}",
            )
            event_type = _text_field(
                event,
                "event_type",
                label=f"decision telemetry ledger line {line_number}",
            )
            event_timestamp = _text_field(
                event,
                "timestamp",
                label=f"decision telemetry ledger line {line_number}",
            )
            event_snapshot_id = _text_field(
                event,
                "snapshot_id",
                label=f"decision telemetry ledger line {line_number}",
            )

            expected_payload_hash = _canonical_sha256(snapshot)
            expected_fabric_id = (
                f"decision-telemetry:{snapshot_id}:{expected_payload_hash[:16]}"
            )
            expected_record_hash = _canonical_sha256(
                {
                    "fabric_id": expected_fabric_id,
                    "observed_at": observed_at,
                    "payload_hash": expected_payload_hash,
                    "previous_record_hash": expected_previous_hash,
                    "snapshot_id": snapshot_id,
                }
            )
            if event_type != "DECISION_TELEMETRY_EVIDENCE":
                raise ValueError(
                    "decision telemetry ledger line "
                    f"{line_number} event_type is invalid"
                )
            if event_timestamp != observed_at:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} timestamp mismatch"
                )
            if event_snapshot_id != snapshot_id:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} snapshot_id mismatch"
                )
            if previous_record_hash != expected_previous_hash:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} hash chain is broken"
                )
            if payload_hash != expected_payload_hash:
                raise ValueError(
                    "decision telemetry ledger line "
                    f"{line_number} payload hash is invalid"
                )
            if fabric_id != expected_fabric_id:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} fabric_id is invalid"
                )
            if record_hash != expected_record_hash:
                raise ValueError(
                    "decision telemetry ledger line "
                    f"{line_number} record hash is invalid"
                )
            expected_previous_hash = record_hash
        return expected_previous_hash

    def _latest_paths(self) -> UserReportPaths:
        return user_report_paths(
            self.repository_root,
            "audit",
            "performance_evidence",
            file_stem="performance_evidence",
            latest_stem="performance_evidence_latest",
        )

    def append(
        self, snapshot: PerformanceEvidenceSnapshot
    ) -> DecisionTelemetryWriteResult:
        record = DecisionTelemetryFabricRecord.seal(
            snapshot,
            previous_record_hash=self.verify_integrity(),
        )
        payload = record.to_payload()
        ledger_write = JsonlAuditStore(
            self.ledger_path,
            durable=self.durable,
        ).append_verified(
            AuditEvent(
                event_type="DECISION_TELEMETRY_EVIDENCE",
                timestamp=record.observed_at,
                payload=payload,
                snapshot_id=snapshot.snapshot_id,
            )
        )
        latest_json_write = write_json_object_verified(
            self.latest_json_path,
            payload,
            blocker="DECISION_TELEMETRY_LATEST_DESTINATION_VERIFY_FAILED",
            subject_id=f"decision-telemetry:{snapshot.snapshot_id}",
            indent=2,
            durable=self.durable,
        )
        self.latest_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        self.latest_markdown_path.write_text(
            render_performance_evidence_markdown(record),
            encoding="utf-8",
        )
        return DecisionTelemetryWriteResult(
            record=record,
            ledger_write=ledger_write,
            latest_json_write=latest_json_write,
            latest_markdown_path=self.latest_markdown_path,
        )


def evaluate_lineage_completeness(
    decision_input: DecisionInputRecord,
    decision_process: DecisionProcessRecord,
    decision_outcome: DecisionOutcomeRecord,
) -> LineageCompletenessResult:
    """Evaluate mandatory decision-cycle lineage references."""

    missing: list[str] = []
    blockers: list[str] = []

    required_refs: Sequence[tuple[str, object]] = (
        ("snapshot_id", decision_input.snapshot_id),
        ("source_data_ids", decision_input.source_data_ids),
        ("feature_versions", decision_input.feature_versions),
        ("evidence_ids", decision_input.evidence_ids),
        ("policy_versions", decision_input.policy_versions),
        ("risk_assessment_id", decision_process.risk_assessment_id),
        ("validation_id", decision_process.validation_id),
        ("decision_id", decision_process.decision_id),
        ("outcome_id", decision_outcome.outcome_id),
    )
    for name, value in required_refs:
        if not _has_value(value):
            missing.append(name)

    if (
        decision_process.decision_state in _NO_TRADE_STATES
        and not decision_process.blockers
    ):
        missing.append("blockers")
        blockers.append("NO_TRADE_RATIONALE_MISSING")

    if (
        decision_outcome.decision_state in _NO_TRADE_STATES
        and not decision_outcome.measurable_no_trade
    ):
        missing.append("no_trade_outcome_measurement")
        blockers.append("NO_TRADE_OUTCOME_WINDOW_MISSING")

    if decision_process.decision_id != decision_outcome.decision_id:
        missing.append("decision_outcome_join")
        blockers.append("DECISION_OUTCOME_JOIN_MISMATCH")

    if missing:
        blockers.append("LINEAGE_INCOMPLETE")
        return LineageCompletenessResult(
            status=LineageStatus.BLOCKED,
            blockers=tuple(dict.fromkeys(blockers)),
            missing_refs=tuple(dict.fromkeys(missing)),
        )
    return LineageCompletenessResult(
        status=LineageStatus.COMPLETE,
        blockers=(),
        missing_refs=(),
    )


def build_performance_evidence_snapshot(
    *,
    decision_input: DecisionInputRecord,
    decision_process: DecisionProcessRecord,
    decision_outcome: DecisionOutcomeRecord,
    dge_metrics: DgeEffectivenessMetrics,
    counterfactuals: tuple[CounterfactualOutcome, ...] = (),
    attributions: tuple[OutcomeAttribution, ...] = (),
    blocker_effectiveness: tuple[BlockerEffectivenessRecord, ...] = (),
    decision_effectiveness: tuple[DecisionEffectivenessRecord, ...] = (),
    telemetry_snapshot: CanonicalTelemetrySnapshot | None = None,
    gpu_telemetry_assessment: GpuTelemetryAssessment | None = None,
    acceptance_results: tuple[PerformanceAcceptanceResult, ...] = (),
    improvement_candidates: tuple[ImprovementCandidate, ...] = (),
    observed_at: datetime | None = None,
) -> PerformanceEvidenceSnapshot:
    """Build a canonical snapshot with deterministic lineage evaluation."""

    observed = observed_at or datetime.now(UTC)
    _require_aware_time("performance snapshot observation", observed)
    lineage = evaluate_lineage_completeness(
        decision_input,
        decision_process,
        decision_outcome,
    )
    return PerformanceEvidenceSnapshot(
        snapshot_id=decision_input.snapshot_id,
        observed_at=observed,
        decision_input=decision_input,
        decision_process=decision_process,
        decision_outcome=decision_outcome,
        dge_metrics=dge_metrics,
        lineage=lineage,
        counterfactuals=counterfactuals,
        attributions=attributions,
        blocker_effectiveness=blocker_effectiveness,
        decision_effectiveness=decision_effectiveness,
        telemetry_snapshot=telemetry_snapshot,
        gpu_telemetry_assessment=gpu_telemetry_assessment,
        acceptance_results=acceptance_results,
        improvement_candidates=improvement_candidates,
    )


def render_performance_evidence_markdown(
    record: DecisionTelemetryFabricRecord,
) -> str:
    """Render the latest telemetry evidence in the standard human report style."""

    snapshot = record.performance_snapshot
    outcome = snapshot.decision_outcome
    dge = snapshot.dge_metrics
    sections = (
        (
            "Lineage",
            (
                f"- Lineage status: `{snapshot.lineage.status.value}`",
                f"- Missing references: `{len(snapshot.lineage.missing_refs)}`",
                f"- Auto-Audit consumable: `{snapshot.auto_audit_consumable}`",
                f"- Auto-Learn consumable: `{snapshot.auto_learn_consumable}`",
            ),
        ),
        (
            "NO_TRADE Outcome Measurement",
            (
                f"- Observation window: `{outcome.observation_window_minutes}` minutes",
                f"- Maximum favorable move: `{outcome.max_favorable_move_usdt}` USDT",
                f"- Maximum adverse move: `{outcome.max_adverse_move_usdt}` USDT",
                f"- Counterfactual return: `{outcome.counterfactual_return_usdt}` USDT",
                f"- Measurable NO_TRADE: `{outcome.measurable_no_trade}`",
            ),
        ),
        (
            "DGE Effectiveness",
            (
                f"- Intervention count: `{dge.intervention_count}`",
                f"- Block rate: `{dge.block_rate}`",
                f"- Protective block rate: `{dge.protective_block_rate}`",
                f"- False block rate: `{dge.false_block_rate}`",
                f"- Net protection value: `{dge.net_protection_value_usdt}` USDT",
                (
                    f"- Drawdown reduction: `{dge.drawdown_reduction_pct}` "
                    "percentage points"
                ),
            ),
        ),
        (
            "Outcome Graph",
            (
                f"- Lifecycle state: `{snapshot.lifecycle_state.value}`",
                f"- Counterfactual paths: `{len(snapshot.counterfactuals)}`",
                f"- Outcome attributions: `{len(snapshot.attributions)}`",
                f"- Blocker effectiveness records: "
                f"`{len(snapshot.blocker_effectiveness)}`",
                f"- Decision effectiveness records: "
                f"`{len(snapshot.decision_effectiveness)}`",
                f"- Acceptance results: `{len(snapshot.acceptance_results)}`",
                f"- Improvement candidates: `{len(snapshot.improvement_candidates)}`",
            ),
        ),
        (
            "Canonical Telemetry",
            (
                (
                    f"- Telemetry id: `{snapshot.telemetry_snapshot.telemetry_id}`"
                    if snapshot.telemetry_snapshot is not None
                    else "- Telemetry id: `-`"
                ),
                (
                    "- Telemetry domains: `"
                    + ", ".join(
                        domain.value for domain in snapshot.telemetry_snapshot.domains
                    )
                    + "`"
                    if snapshot.telemetry_snapshot is not None
                    else "- Telemetry domains: `-`"
                ),
                (
                    "- Telemetry gate eligible: "
                    f"`{snapshot.telemetry_snapshot.gate_eligible}`"
                    if snapshot.telemetry_snapshot is not None
                    else "- Telemetry gate eligible: `-`"
                ),
            ),
        ),
        (
            "GPU Resource Governance",
            (
                (
                    f"- GPU assessment source: "
                    f"`{snapshot.gpu_telemetry_assessment.source_label}`"
                    if snapshot.gpu_telemetry_assessment is not None
                    else "- GPU assessment source: `-`"
                ),
                (
                    f"- GPU assessment healthy: "
                    f"`{snapshot.gpu_telemetry_assessment.healthy}`"
                    if snapshot.gpu_telemetry_assessment is not None
                    else "- GPU assessment healthy: `-`"
                ),
                (
                    "- GPU assessment blockers: `"
                    + ", ".join(snapshot.gpu_telemetry_assessment.blockers)
                    + "`"
                    if snapshot.gpu_telemetry_assessment is not None
                    else "- GPU assessment blockers: `-`"
                ),
            ),
        ),
        (
            "Ledger Integrity",
            (
                f"- Previous record hash: `{record.previous_record_hash}`",
                f"- Payload hash: `{record.payload_hash}`",
                f"- Record hash: `{record.record_hash}`",
            ),
        ),
    )
    return render_professional_summary(
        title="Decision Telemetry Performance Evidence",
        observed_at=record.observed_at.isoformat(),
        status=snapshot.status.value,
        summary=(
            "This report links the decision input, process, output, and outcome "
            "into a tamper-evident evidence record for audit and learning review."
        ),
        sections=sections,
        blockers=snapshot.lineage.blockers,
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def _canonical_sha256(payload: object) -> str:
    primitive = to_primitive(payload)
    encoded = json.dumps(
        primitive,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping_from_json_bytes(raw: bytes, *, label: str) -> Mapping[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _mapping_field(
    payload: Mapping[str, object],
    field: str,
    *,
    label: str,
) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"{label} field {field} must be an object")
    return cast(Mapping[str, object], value)


def _text_field(payload: Mapping[str, object], field: str, *, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} field {field} must be non-empty text")
    return value


def _has_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence):
        return bool(value)
    return value is not None


def _require_text(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required")


def _require_aware_time(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} timestamp must be timezone-aware")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    if not values:
        raise ValueError(f"{label} are required")
    _require_unique_nonblank_or_empty(label, values)


def _require_unique_nonblank_or_empty(label: str, values: tuple[str, ...]) -> None:
    normalized: list[str] = []
    for value in values:
        if not value.strip():
            raise ValueError(f"{label} cannot contain blank values")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")


def _require_nonempty_mapping(label: str, values: Mapping[str, str]) -> None:
    if not values:
        raise ValueError(f"{label} are required")
    for key, value in values.items():
        if not str(key).strip() or not str(value).strip():
            raise ValueError(f"{label} cannot contain blank keys or values")


def _require_finite_decimal(label: str, value: Decimal) -> None:
    if not value.is_finite():
        raise ValueError(f"{label} must be finite")


def _require_optional_finite_decimal(label: str, value: Decimal | None) -> None:
    if value is not None:
        _require_finite_decimal(label, value)


def _require_confidence(label: str, value: Decimal) -> None:
    _require_finite_decimal(label, value)
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{label} must be between 0 and 1")
