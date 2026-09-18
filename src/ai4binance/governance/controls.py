"""Canonical hard-blocker and soft-penalty control primitives."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
DEFAULT_CONTROL_POLICY_VERSION = "control-policy-v1"


class ControlSource(StrEnum):
    DATA_QUALITY = "DATA_QUALITY"
    RISK = "RISK"
    VALIDATION = "VALIDATION"
    GOVERNANCE = "GOVERNANCE"
    LIQUIDITY = "LIQUIDITY"
    EXECUTION = "EXECUTION"
    STRATEGY = "STRATEGY"
    EVIDENCE = "EVIDENCE"
    SECURITY = "SECURITY"
    SCORING = "SCORING"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ControlSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ControlEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    WATCH_ONLY = "WATCH_ONLY"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    BLOCKED = "BLOCKED"
    NO_TRADE = "NO_TRADE"
    LIVE_ORDER_BLOCKED = "LIVE_ORDER_BLOCKED"


class ControlResolutionAuthority(StrEnum):
    DATA_QUALITY_ENGINE = "DATA_QUALITY_ENGINE"
    RISK_ENGINE = "RISK_ENGINE"
    VALIDATION_ENGINE = "VALIDATION_ENGINE"
    GOVERNANCE_CONTROL_PLANE = "GOVERNANCE_CONTROL_PLANE"
    LIQUIDITY_ENGINE = "LIQUIDITY_ENGINE"
    EXECUTION_ENGINE = "EXECUTION_ENGINE"
    SECURITY_ASSURANCE = "SECURITY_ASSURANCE"
    STRATEGY_GOVERNANCE = "STRATEGY_GOVERNANCE"
    EVIDENCE_FABRIC = "EVIDENCE_FABRIC"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class HardBlocker:
    """Binary veto condition that cannot be offset by scores or bonuses."""

    blocker_id: str
    blocker_type: str
    source: ControlSource
    severity: ControlSeverity
    reason_code: str
    evidence_refs: tuple[str, ...]
    policy_ref: str
    policy_version: str = DEFAULT_CONTROL_POLICY_VERSION
    control_ref: str = "control:unknown"
    control_version: str = DEFAULT_CONTROL_POLICY_VERSION
    producer: str = "GovernanceControlPlane"
    source_component: str = "governance.controls"
    scope: str = "GLOBAL"
    active: bool = True
    resolvable: bool = True
    resolution_authority: ControlResolutionAuthority = (
        ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE
    )
    metadata: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        _require_nonblank_values(
            "hard blocker identity",
            (
                self.blocker_id,
                self.blocker_type,
                self.reason_code,
                self.policy_ref,
                self.policy_version,
                self.control_ref,
                self.control_version,
                self.producer,
                self.source_component,
                self.scope,
            ),
        )
        _require_unique_nonblank("hard blocker evidence refs", self.evidence_refs)

    def to_payload(self) -> dict[str, object]:
        return {
            "blocker_id": self.blocker_id,
            "blocker_type": self.blocker_type,
            "source": self.source.value,
            "severity": self.severity.value,
            "reason_code": self.reason_code,
            "evidence_refs": self.evidence_refs,
            "policy_ref": self.policy_ref,
            "policy_version": self.policy_version,
            "control_ref": self.control_ref,
            "control_version": self.control_version,
            "producer": self.producer,
            "source_component": self.source_component,
            "scope": self.scope,
            "active": self.active,
            "resolvable": self.resolvable,
            "resolution_authority": self.resolution_authority.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SoftPenalty:
    """Bounded negative score adjustment that cannot create or clear vetoes."""

    penalty_id: str
    penalty_type: str
    source: ControlSource
    reason_code: str
    value: Decimal
    max_value: Decimal
    evidence_refs: tuple[str, ...]
    policy_ref: str
    policy_version: str = DEFAULT_CONTROL_POLICY_VERSION
    control_ref: str = "control:unknown"
    control_version: str = DEFAULT_CONTROL_POLICY_VERSION
    producer: str = "GovernanceControlPlane"
    source_component: str = "governance.controls"
    scope: str = "GLOBAL"
    penalty_group: str = "DEFAULT"
    metadata: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        _require_nonblank_values(
            "soft penalty identity",
            (
                self.penalty_id,
                self.penalty_type,
                self.reason_code,
                self.policy_ref,
                self.policy_version,
                self.control_ref,
                self.control_version,
                self.producer,
                self.source_component,
                self.scope,
                self.penalty_group,
            ),
        )
        _require_unique_nonblank("soft penalty evidence refs", self.evidence_refs)
        if self.value < ZERO or self.max_value < ZERO or self.value > self.max_value:
            raise ValueError("soft penalty value must be between zero and max_value")

    def to_payload(self) -> dict[str, object]:
        return {
            "penalty_id": self.penalty_id,
            "penalty_type": self.penalty_type,
            "source": self.source.value,
            "reason_code": self.reason_code,
            "value": self.value,
            "max_value": self.max_value,
            "evidence_refs": self.evidence_refs,
            "policy_ref": self.policy_ref,
            "policy_version": self.policy_version,
            "control_ref": self.control_ref,
            "control_version": self.control_version,
            "producer": self.producer,
            "source_component": self.source_component,
            "scope": self.scope,
            "penalty_group": self.penalty_group,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PenaltyGroupCap:
    penalty_group: str
    cap: Decimal

    def __post_init__(self) -> None:
        _require_nonblank_values("penalty group cap", (self.penalty_group,))
        if self.cap < ZERO:
            raise ValueError("penalty group cap must be non-negative")


@dataclass(frozen=True, slots=True)
class SoftPenaltyPolicy:
    """Deterministic cap policy for soft penalties."""

    global_cap: Decimal = Decimal("30")
    group_caps: tuple[PenaltyGroupCap, ...] = ()

    def __post_init__(self) -> None:
        if self.global_cap < ZERO:
            raise ValueError("soft penalty global cap must be non-negative")
        groups = tuple(item.penalty_group for item in self.group_caps)
        if len(set(groups)) != len(groups):
            raise ValueError("soft penalty group caps must be unique")

    def cap_for(self, penalty_group: str) -> Decimal | None:
        for group_cap in self.group_caps:
            if group_cap.penalty_group == penalty_group:
                return group_cap.cap
        return None


@dataclass(frozen=True, slots=True)
class ControlEvaluation:
    """Final shared control result consumed by DGE, Risk and Validation."""

    evaluation_id: str = "control:evaluation:default"
    hard_blockers: tuple[HardBlocker, ...] = ()
    soft_penalties: tuple[SoftPenalty, ...] = ()
    hard_gate_passed: bool = True
    base_score: Decimal = ZERO
    total_penalty: Decimal = ZERO
    adjusted_score: Decimal = ZERO
    eligibility: ControlEligibility = ControlEligibility.ELIGIBLE
    reason_codes: tuple[str, ...] = ()
    policy_version: str = DEFAULT_CONTROL_POLICY_VERSION

    @property
    def active_hard_blocker_count(self) -> int:
        return sum(1 for blocker in self.hard_blockers if blocker.active)

    def __post_init__(self) -> None:
        _require_nonblank_values(
            "control evaluation identity",
            (self.evaluation_id, self.policy_version),
        )
        _require_unique_nonblank(
            "control evaluation hard blocker ids",
            tuple(blocker.blocker_id for blocker in self.hard_blockers),
        )
        _require_unique_nonblank(
            "control evaluation soft penalty ids",
            tuple(penalty.penalty_id for penalty in self.soft_penalties),
        )
        _require_unique_nonblank("control evaluation reason codes", self.reason_codes)
        for name, value in (
            ("base_score", self.base_score),
            ("total_penalty", self.total_penalty),
            ("adjusted_score", self.adjusted_score),
        ):
            _require_score_0_100(name, value)
        if self.active_hard_blocker_count:
            if self.hard_gate_passed:
                raise ValueError("active hard blockers must fail the hard gate")
            if self.eligibility is ControlEligibility.ELIGIBLE:
                raise ValueError("active hard blockers cannot be eligible")
        if not self.active_hard_blocker_count and not self.hard_gate_passed:
            raise ValueError("hard gate cannot fail without active hard blockers")
        if self.adjusted_score > self.base_score:
            raise ValueError("adjusted score cannot exceed base score")

    def to_payload(self) -> dict[str, object]:
        return {
            "evaluation_id": self.evaluation_id,
            "hard_blockers": [item.to_payload() for item in self.hard_blockers],
            "soft_penalties": [item.to_payload() for item in self.soft_penalties],
            "hard_gate_passed": self.hard_gate_passed,
            "active_hard_blocker_count": self.active_hard_blocker_count,
            "base_score": self.base_score,
            "total_penalty": self.total_penalty,
            "adjusted_score": self.adjusted_score,
            "eligibility": self.eligibility.value,
            "reason_codes": self.reason_codes,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class ControlResolution:
    blocker_id: str
    resolution_authority: ControlResolutionAuthority
    evidence_refs: tuple[str, ...]
    resolved: bool = True

    def __post_init__(self) -> None:
        _require_nonblank_values("control resolution identity", (self.blocker_id,))
        _require_unique_nonblank("control resolution evidence refs", self.evidence_refs)


def build_control_evaluation(
    *,
    evaluation_id: str,
    base_score: Decimal,
    hard_blockers: tuple[HardBlocker, ...] = (),
    soft_penalties: tuple[SoftPenalty, ...] = (),
    penalty_policy: SoftPenaltyPolicy | None = None,
    eligibility_when_clear: ControlEligibility = ControlEligibility.ELIGIBLE,
    eligibility_when_blocked: ControlEligibility = ControlEligibility.NO_TRADE,
    policy_version: str = DEFAULT_CONTROL_POLICY_VERSION,
) -> ControlEvaluation:
    """Evaluate hard blockers before applying bounded soft penalties."""

    _require_score_0_100("base_score", base_score)
    selected_penalty_policy = penalty_policy or DEFAULT_SOFT_PENALTY_POLICY
    total_penalty = _capped_penalty_total(soft_penalties, selected_penalty_policy)
    adjusted_score = max(ZERO, base_score - total_penalty)
    active_hard_blockers = tuple(blocker for blocker in hard_blockers if blocker.active)
    eligibility = (
        eligibility_when_blocked if active_hard_blockers else eligibility_when_clear
    )
    reason_codes = tuple(
        dict.fromkeys(
            (
                *(blocker.reason_code for blocker in hard_blockers),
                *(penalty.reason_code for penalty in soft_penalties),
            )
        )
    )
    return ControlEvaluation(
        evaluation_id=evaluation_id,
        hard_blockers=hard_blockers,
        soft_penalties=soft_penalties,
        hard_gate_passed=not active_hard_blockers,
        base_score=base_score,
        total_penalty=total_penalty,
        adjusted_score=adjusted_score,
        eligibility=eligibility,
        reason_codes=reason_codes,
        policy_version=policy_version,
    )


def unknown_control_classification_blocker(
    *,
    reason_code: str,
    evidence_refs: tuple[str, ...] = (),
    policy_ref: str = "policy:control:unknown-classification",
    scope: str = "GLOBAL",
) -> HardBlocker:
    """Represent unknown trading-sensitive classification as a fail-closed veto."""

    return HardBlocker(
        blocker_id=f"hard:{reason_code}",
        blocker_type="UNKNOWN_CONTROL_CLASSIFICATION",
        source=ControlSource.GOVERNANCE,
        severity=ControlSeverity.CRITICAL,
        reason_code="GOV.UNKNOWN_CONTROL_CLASSIFICATION",
        evidence_refs=evidence_refs,
        policy_ref=policy_ref,
        control_ref="control:governance:unknown-control-classification",
        producer="GovernanceControlPlane",
        scope=scope,
        resolvable=True,
        resolution_authority=ControlResolutionAuthority.GOVERNANCE_CONTROL_PLANE,
        metadata={"original_reason_code": reason_code},
    )


def resolve_hard_blockers(
    blockers: tuple[HardBlocker, ...],
    resolutions: tuple[ControlResolution, ...],
) -> tuple[HardBlocker, ...]:
    """Clear only blockers resolved by their declared authority."""

    resolution_index = {resolution.blocker_id: resolution for resolution in resolutions}
    resolved: list[HardBlocker] = []
    for blocker in blockers:
        resolution = resolution_index.get(blocker.blocker_id)
        if resolution is None or not resolution.resolved:
            resolved.append(blocker)
            continue
        if resolution.resolution_authority is not blocker.resolution_authority:
            raise ValueError("hard blocker resolution authority mismatch")
        if not resolution.evidence_refs:
            raise ValueError("hard blocker resolution requires evidence")
        resolved.append(replace(blocker, active=False))
    return tuple(resolved)


def _capped_penalty_total(
    penalties: tuple[SoftPenalty, ...],
    policy: SoftPenaltyPolicy,
) -> Decimal:
    group_totals: dict[str, Decimal] = {}
    for penalty in penalties:
        group_totals[penalty.penalty_group] = (
            group_totals.get(penalty.penalty_group, ZERO) + penalty.value
        )
    capped_group_total = ZERO
    for penalty_group, total in group_totals.items():
        group_cap = policy.cap_for(penalty_group)
        capped_group_total += min(total, group_cap) if group_cap is not None else total
    return min(policy.global_cap, capped_group_total)


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


DEFAULT_SOFT_PENALTY_POLICY = SoftPenaltyPolicy(
    global_cap=Decimal("30"),
    group_caps=(
        PenaltyGroupCap("LIQUIDITY_QUALITY", Decimal("12")),
        PenaltyGroupCap("MARKET_STRUCTURE", Decimal("10")),
        PenaltyGroupCap("EVIDENCE_QUALITY", Decimal("12")),
        PenaltyGroupCap("GOVERNANCE_REVIEW", Decimal("10")),
    ),
)
