"""Dependency-neutral aggregate for one completed canonical research cycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

MAX_BOUNDED_OBSERVATIONS = 64


class CanonicalCycleStep(StrEnum):
    """Immutable order of the root-governance cycle invariant."""

    ONE_CYCLE = "ONE_CYCLE"
    ONE_CANONICAL_SNAPSHOT = "ONE_CANONICAL_SNAPSHOT"
    ONE_SHARED_STATE = "ONE_SHARED_STATE"
    MANY_BOUNDED_OBSERVATIONS = "MANY_BOUNDED_OBSERVATIONS"
    ONE_DETERMINISTIC_DECISION = "ONE_DETERMINISTIC_DECISION"
    ONE_RISK_ASSESSMENT = "ONE_RISK_ASSESSMENT"
    ONE_GOVERNANCE_RESULT = "ONE_GOVERNANCE_RESULT"
    ZERO_OR_ONE_EXECUTION_PLAN = "ZERO_OR_ONE_EXECUTION_PLAN"
    ONE_AUDIT_TRAIL = "ONE_AUDIT_TRAIL"


class CycleExecutionSurface(StrEnum):
    """Execution surfaces represented by the cycle receipt."""

    BINANCE_MARKET = "BINANCE_MARKET"
    VIRTUAL_MARKET = "VIRTUAL_MARKET"


class CycleGovernanceStatus(StrEnum):
    """Bounded governance outcomes consumed by research orchestration."""

    APPROVED_PAPER_ONLY = "APPROVED_PAPER_ONLY"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    NO_TRADE = "NO_TRADE"


class CycleArtifactKind(StrEnum):
    """Typed artifact roles carried by one completed canonical cycle."""

    CANONICAL_SNAPSHOT = "CANONICAL_SNAPSHOT"
    SHARED_STATE = "SHARED_STATE"
    OBSERVATION = "OBSERVATION"
    DECISION = "DECISION"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    GOVERNANCE_RESULT = "GOVERNANCE_RESULT"
    VIRTUAL_SIMULATION_PLAN = "VIRTUAL_SIMULATION_PLAN"
    BINANCE_MANUAL_PLAN = "BINANCE_MANUAL_PLAN"
    AUDIT_TRAIL = "AUDIT_TRAIL"
    OUTCOME = "OUTCOME"
    LEARNING_PROPOSAL = "LEARNING_PROPOSAL"
    VALIDATION_RESULT = "VALIDATION_RESULT"
    MEMORY_DISPOSITION = "MEMORY_DISPOSITION"


@dataclass(frozen=True, slots=True)
class CycleArtifactRef:
    """Hash-bound reference to one artifact inside a canonical cycle."""

    artifact_id: str
    artifact_kind: CycleArtifactKind
    cycle_id: str
    snapshot_id: str
    payload_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_kind, CycleArtifactKind):
            raise ValueError("cycle artifact kind is invalid")
        for name, value in (
            ("artifact_id", self.artifact_id),
            ("cycle_id", self.cycle_id),
            ("snapshot_id", self.snapshot_id),
        ):
            if not value.strip():
                raise ValueError(f"cycle artifact {name} is required")
        if len(self.payload_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.payload_sha256
        ):
            raise ValueError("cycle artifact payload_sha256 must be lowercase SHA-256")

    def to_payload(self) -> dict[str, str]:
        """Return the deterministic artifact-reference payload."""

        return {
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind.value,
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class CanonicalCycleEnvelope:
    """Bind one complete canonical cycle without granting execution authority."""

    cycle_id: str
    snapshot_id: str
    created_at: datetime
    execution_surface: CycleExecutionSurface
    governance_status: CycleGovernanceStatus
    canonical_snapshot: CycleArtifactRef
    shared_state: CycleArtifactRef
    observations: tuple[CycleArtifactRef, ...]
    decision: CycleArtifactRef
    risk_assessment: CycleArtifactRef
    governance_result: CycleArtifactRef
    execution_plan: CycleArtifactRef | None
    audit_trail: CycleArtifactRef
    blockers: tuple[str, ...] = ()
    completed_steps: tuple[CanonicalCycleStep, ...] = tuple(CanonicalCycleStep)
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.cycle_id.strip() or not self.snapshot_id.strip():
            raise ValueError("canonical cycle envelope identity is required")
        if not isinstance(self.execution_surface, CycleExecutionSurface):
            raise ValueError("canonical cycle execution surface is invalid")
        if not isinstance(self.governance_status, CycleGovernanceStatus):
            raise ValueError("canonical cycle governance status is invalid")
        utc_offset = self.created_at.utcoffset()
        if self.created_at.tzinfo is None or utc_offset is None:
            raise ValueError(
                "canonical cycle envelope timestamp must be timezone-aware"
            )
        if utc_offset.total_seconds() != 0:
            raise ValueError("canonical cycle envelope timestamp must be UTC")
        if self.completed_steps != tuple(CanonicalCycleStep):
            raise ValueError("canonical cycle envelope step order is immutable")
        if not 1 <= len(self.observations) <= MAX_BOUNDED_OBSERVATIONS:
            raise ValueError(
                "canonical cycle observations must be non-empty and bounded"
            )
        if len({item.artifact_id for item in self.observations}) != len(
            self.observations
        ):
            raise ValueError("canonical cycle observation identities must be unique")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("canonical cycle blockers cannot contain blanks")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("canonical cycle blockers must be unique")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("canonical cycle envelope cannot grant live authority")

        role_refs = (
            (self.canonical_snapshot, CycleArtifactKind.CANONICAL_SNAPSHOT),
            (self.shared_state, CycleArtifactKind.SHARED_STATE),
            *((item, CycleArtifactKind.OBSERVATION) for item in self.observations),
            (self.decision, CycleArtifactKind.DECISION),
            (self.risk_assessment, CycleArtifactKind.RISK_ASSESSMENT),
            (self.governance_result, CycleArtifactKind.GOVERNANCE_RESULT),
            (self.audit_trail, CycleArtifactKind.AUDIT_TRAIL),
        )
        if self.execution_plan is not None:
            if not isinstance(self.execution_plan, CycleArtifactRef):
                raise ValueError("canonical cycle artifact reference is invalid")
            role_refs = (
                *role_refs,
                (self.execution_plan, self.execution_plan.artifact_kind),
            )
        for artifact, expected_kind in role_refs:
            if not isinstance(artifact, CycleArtifactRef):
                raise ValueError("canonical cycle artifact reference is invalid")
            if artifact.cycle_id != self.cycle_id:
                raise ValueError("canonical cycle artifact cycle_id must match")
            if artifact.snapshot_id != self.snapshot_id:
                raise ValueError("canonical cycle artifact snapshot_id must match")
            if artifact.artifact_kind is not expected_kind:
                raise ValueError("canonical cycle artifact kind must match its role")
        artifact_ids = tuple(artifact.artifact_id for artifact, _kind in role_refs)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("canonical cycle artifact identities must be unique")

        if (
            self.governance_status is CycleGovernanceStatus.APPROVED_PAPER_ONLY
            and self.blockers
            and self.execution_plan is not None
        ):
            raise ValueError("execution plan cannot coexist with governance blockers")
        if self.execution_plan is None:
            return
        if self.governance_status is not CycleGovernanceStatus.APPROVED_PAPER_ONLY:
            raise ValueError("execution plan requires paper-only governance approval")
        if self.execution_surface is CycleExecutionSurface.VIRTUAL_MARKET:
            if (
                self.execution_plan.artifact_kind
                is not CycleArtifactKind.VIRTUAL_SIMULATION_PLAN
            ):
                raise ValueError(
                    "virtual execution plan must remain bounded simulation"
                )
            return
        if (
            self.execution_plan.artifact_kind
            is not CycleArtifactKind.BINANCE_MANUAL_PLAN
        ):
            raise ValueError("Binance execution plan must remain manual-only")

    @property
    def semantic_sha256(self) -> str:
        """Hash the complete deterministic cycle receipt."""

        canonical = json.dumps(
            self.to_payload(include_semantic_hash=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_payload(self, *, include_semantic_hash: bool = True) -> dict[str, object]:
        """Return the secret-safe deterministic cycle receipt payload."""

        payload: dict[str, object] = {
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at.isoformat(),
            "execution_surface": self.execution_surface.value,
            "governance_status": self.governance_status.value,
            "canonical_snapshot": self.canonical_snapshot.to_payload(),
            "shared_state": self.shared_state.to_payload(),
            "observations": [item.to_payload() for item in self.observations],
            "decision": self.decision.to_payload(),
            "risk_assessment": self.risk_assessment.to_payload(),
            "governance_result": self.governance_result.to_payload(),
            "execution_plan": (
                None
                if self.execution_plan is None
                else self.execution_plan.to_payload()
            ),
            "audit_trail": self.audit_trail.to_payload(),
            "blockers": list(self.blockers),
            "completed_steps": [step.value for step in self.completed_steps],
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        if include_semantic_hash:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload


__all__ = (
    "MAX_BOUNDED_OBSERVATIONS",
    "CanonicalCycleEnvelope",
    "CanonicalCycleStep",
    "CycleArtifactKind",
    "CycleArtifactRef",
    "CycleExecutionSurface",
    "CycleGovernanceStatus",
)
