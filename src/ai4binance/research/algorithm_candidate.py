"""Research-only algorithm candidate contracts and verification evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.domain import ValidationStatus


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_unique_non_empty(name: str, values: tuple[str, ...]) -> None:
    if not values:
        raise ValueError(f"{name} cannot be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")


class AlgorithmCandidateStatus(StrEnum):
    """Governed lifecycle states before paper or live authority exists."""

    HYPOTHESIS = "HYPOTHESIS"
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    MATH_VERIFIED = "MATH_VERIFIED"
    STATISTICALLY_PLAUSIBLE = "STATISTICALLY_PLAUSIBLE"
    IMPLEMENTED = "IMPLEMENTED"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    ROBUSTNESS_VALIDATED = "ROBUSTNESS_VALIDATED"
    PAPER_CANDIDATE = "PAPER_CANDIDATE"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    DEPRECATED = "DEPRECATED"


class VerificationStatus(StrEnum):
    """Cold-path verification state for one evidence dimension."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class AlgorithmCandidateOrigin:
    """Traceable origin for an advisory algorithm candidate."""

    origin_type: str
    generator: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("algorithm origin type", self.origin_type)
        _require_non_empty("algorithm origin generator", self.generator)
        if self.evidence_refs:
            _require_unique_non_empty(
                "algorithm origin evidence references",
                self.evidence_refs,
            )


@dataclass(frozen=True, slots=True)
class AlgorithmVerificationEvidence:
    """Mathematical, statistical and implementation verification status."""

    mathematical: VerificationStatus = VerificationStatus.PENDING
    statistical: VerificationStatus = VerificationStatus.PENDING
    implementation: VerificationStatus = VerificationStatus.PENDING
    evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_refs:
            _require_unique_non_empty(
                "algorithm verification evidence references",
                self.evidence_refs,
            )
        if self.blockers:
            _require_unique_non_empty("algorithm verification blockers", self.blockers)
        failed_or_missing = {
            VerificationStatus.FAILED,
            VerificationStatus.UNAVAILABLE,
        }
        if (
            self.mathematical in failed_or_missing
            or self.statistical in failed_or_missing
            or self.implementation in failed_or_missing
        ) and not self.blockers:
            raise ValueError("failed or unavailable verification requires blockers")


@dataclass(frozen=True, slots=True)
class AlgorithmValidationEvidence:
    """Validation lifecycle evidence before any paper or live approval."""

    backtest: VerificationStatus = VerificationStatus.PENDING
    walk_forward: VerificationStatus = VerificationStatus.PENDING
    oos: VerificationStatus = VerificationStatus.PENDING
    robustness: VerificationStatus = VerificationStatus.PENDING
    regime: VerificationStatus = VerificationStatus.PENDING
    evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_refs:
            _require_unique_non_empty(
                "algorithm validation evidence references",
                self.evidence_refs,
            )
        if self.blockers:
            _require_unique_non_empty("algorithm validation blockers", self.blockers)
        failed_or_missing = {
            VerificationStatus.FAILED,
            VerificationStatus.UNAVAILABLE,
        }
        if (
            self.backtest in failed_or_missing
            or self.walk_forward in failed_or_missing
            or self.oos in failed_or_missing
            or self.robustness in failed_or_missing
            or self.regime in failed_or_missing
        ) and not self.blockers:
            raise ValueError("failed or unavailable validation requires blockers")


@dataclass(frozen=True, slots=True)
class AlgorithmCandidate:
    """Canonical research-only algorithm proposal with no execution authority."""

    algorithm_id: str
    origin: AlgorithmCandidateOrigin
    hypothesis: str
    inputs: tuple[str, ...]
    formula_ref: str | None = None
    status: AlgorithmCandidateStatus = AlgorithmCandidateStatus.RESEARCH_CANDIDATE
    verification: AlgorithmVerificationEvidence = AlgorithmVerificationEvidence()
    validation: AlgorithmValidationEvidence = AlgorithmValidationEvidence()
    blockers: tuple[str, ...] = ("LIVE_ORDER_BLOCKED",)
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    paper_execution_allowed: bool = False
    live_execution_allowed: bool = False
    self_promotion_allowed: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_non_empty("algorithm identity", self.algorithm_id)
        _require_non_empty("algorithm hypothesis", self.hypothesis)
        _require_unique_non_empty("algorithm inputs", self.inputs)
        if self.formula_ref is not None:
            _require_non_empty("algorithm formula reference", self.formula_ref)
        if self.blockers:
            _require_unique_non_empty("algorithm blockers", self.blockers)
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
        }:
            raise ValueError("algorithm candidate cannot approve paper or live use")
        if self.promotion_status is ValidationStatus.STAGED_CANDIDATE and self.blockers:
            raise ValueError("staged algorithm candidate cannot contain blockers")
        if (
            self.paper_execution_allowed
            or self.live_execution_allowed
            or self.self_promotion_allowed
            or self.execution_allowed
        ):
            raise ValueError("algorithm candidate cannot grant execution authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("algorithm candidate must remain live blocked")
