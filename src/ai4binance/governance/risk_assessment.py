"""Measured risk-assessment contract with explicit residual-risk governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class RiskAssessmentV2Result(StrEnum):
    PASS = "PASS"  # noqa: S105  # nosec B105
    RESTRICT = "RESTRICT"
    BLOCK = "BLOCK"


class RiskEvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVALIDATED = "UNVALIDATED"
    UNKNOWN = "UNKNOWN"


class RiskControlStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    INEFFECTIVE = "INEFFECTIVE"


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True, slots=True)
class RiskRating:
    likelihood: int
    impact: int

    def __post_init__(self) -> None:
        if not 1 <= self.likelihood <= 5 or not 1 <= self.impact <= 5:
            raise ValueError("risk likelihood and impact must be between 1 and 5")

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    def to_payload(self) -> dict[str, int]:
        return {
            "likelihood": self.likelihood,
            "impact": self.impact,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class RiskControlEffectiveness:
    control_id: str
    effectiveness_bps: int
    evidence_sha256: str
    status: RiskControlStatus

    def __post_init__(self) -> None:
        if not self.control_id.strip():
            raise ValueError("risk control_id is required")
        if not 0 <= self.effectiveness_bps <= 10_000:
            raise ValueError(
                "risk control effectiveness_bps must be between 0 and 10000"
            )
        _require_sha256("risk control evidence_sha256", self.evidence_sha256)
        if self.status is RiskControlStatus.INEFFECTIVE and self.effectiveness_bps != 0:
            raise ValueError("ineffective risk control must have zero effectiveness")

    def to_payload(self) -> dict[str, object]:
        return {
            "control_id": self.control_id,
            "effectiveness_bps": self.effectiveness_bps,
            "evidence_sha256": self.evidence_sha256,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RiskAssessmentV2Contract:
    assessment_id: str
    cycle_id: str
    snapshot_id: str
    decision_id: str
    assessed_at: datetime
    owner_id: str
    reviewer_id: str
    affected_parties: tuple[str, ...]
    risk_register_ref: str
    inherent_risk: RiskRating
    current_risk: RiskRating
    residual_risk: RiskRating
    appetite_threshold: int
    controls: tuple[RiskControlEffectiveness, ...]
    evidence_status: RiskEvidenceStatus
    result: RiskAssessmentV2Result
    blockers: tuple[str, ...] = ()
    schema_version: str = "2.0.0"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.schema_version != "2.0.0":
            raise ValueError("risk assessment schema_version must be 2.0.0")
        if not isinstance(self.evidence_status, RiskEvidenceStatus) or not isinstance(
            self.result, RiskAssessmentV2Result
        ):
            raise ValueError("risk assessment status is invalid")
        if not all(
            isinstance(rating, RiskRating)
            for rating in (self.inherent_risk, self.current_risk, self.residual_risk)
        ):
            raise ValueError("risk assessment ratings are invalid")
        if not all(
            isinstance(control, RiskControlEffectiveness) for control in self.controls
        ):
            raise ValueError("risk assessment controls are invalid")
        for name in (
            "assessment_id",
            "cycle_id",
            "snapshot_id",
            "decision_id",
            "owner_id",
            "reviewer_id",
            "risk_register_ref",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"risk assessment {name} is required")
        if self.owner_id == self.reviewer_id:
            raise ValueError("risk assessment owner and reviewer must be distinct")
        if (
            self.assessed_at.tzinfo is None
            or self.assessed_at.utcoffset() != UTC.utcoffset(self.assessed_at)
        ):
            raise ValueError("risk assessment assessed_at must be UTC")
        _require_unique_nonblank(
            "risk assessment affected_parties", self.affected_parties
        )
        _require_unique_nonblank("risk assessment blockers", self.blockers)
        if not self.affected_parties:
            raise ValueError("risk assessment affected_parties cannot be empty")
        if not 1 <= self.appetite_threshold <= 25:
            raise ValueError("risk appetite_threshold must be between 1 and 25")
        control_ids = tuple(control.control_id for control in self.controls)
        _require_unique_nonblank("risk assessment control IDs", control_ids)
        if not self.controls:
            raise ValueError("risk assessment requires controls")
        if self.current_risk.score > self.inherent_risk.score:
            raise ValueError("current risk cannot exceed inherent risk")
        if self.residual_risk.score > self.current_risk.score:
            raise ValueError("residual risk cannot exceed current risk")
        if self.result is RiskAssessmentV2Result.PASS:
            if self.blockers:
                raise ValueError("PASS risk assessment cannot contain blockers")
            if self.residual_risk.score > self.appetite_threshold:
                raise ValueError("PASS residual risk must be within appetite")
            if self.evidence_status is not RiskEvidenceStatus.VERIFIED or any(
                control.status is not RiskControlStatus.VERIFIED
                for control in self.controls
            ):
                raise ValueError("PASS risk assessment requires verified evidence")
        elif not self.blockers:
            raise ValueError("non-PASS risk assessment requires blockers")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("risk assessment cannot grant execution authority")

    @property
    def semantic_sha256(self) -> str:
        canonical = json.dumps(
            self.to_payload(include_semantic_hash=False),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_payload(self, *, include_semantic_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "assessment_id": self.assessment_id,
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "decision_id": self.decision_id,
            "assessed_at": self.assessed_at.isoformat().replace("+00:00", "Z"),
            "owner_id": self.owner_id,
            "reviewer_id": self.reviewer_id,
            "affected_parties": list(self.affected_parties),
            "risk_register_ref": self.risk_register_ref,
            "inherent_risk": self.inherent_risk.to_payload(),
            "current_risk": self.current_risk.to_payload(),
            "residual_risk": self.residual_risk.to_payload(),
            "appetite_threshold": self.appetite_threshold,
            "controls": [control.to_payload() for control in self.controls],
            "evidence_status": self.evidence_status.value,
            "result": self.result.value,
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "live_eligibility_status": self.live_eligibility_status,
        }
        if include_semantic_hash:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload


__all__ = (
    "RiskAssessmentV2Contract",
    "RiskAssessmentV2Result",
    "RiskControlEffectiveness",
    "RiskControlStatus",
    "RiskEvidenceStatus",
    "RiskRating",
)
