"""Validated outcome-to-memory closure for a completed canonical cycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ai4binance.domain.research.canonical_cycle import (
    CanonicalCycleEnvelope,
    CycleArtifactKind,
    CycleArtifactRef,
)


class LifecycleClosureStep(StrEnum):
    OBSERVED_OUTCOME = "OBSERVED_OUTCOME"
    PROPOSED_CORRECTIVE_LEARNING = "PROPOSED_CORRECTIVE_LEARNING"
    INDEPENDENT_VALIDATION = "INDEPENDENT_VALIDATION"
    MEMORY_DISPOSITION = "MEMORY_DISPOSITION"


class LearningValidationResult(StrEnum):
    PASS = "PASS"  # noqa: S105  # nosec B105
    REJECT = "REJECT"


class MemoryDisposition(StrEnum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class CycleLifecycleReceipt:
    """Bind validated learning to one immutable cycle without auto-admission."""

    receipt_id: str
    cycle_id: str
    snapshot_id: str
    canonical_cycle_sha256: str
    cycle_created_at: datetime
    created_at: datetime
    outcome: CycleArtifactRef
    learning_proposal: CycleArtifactRef
    validation_result: CycleArtifactRef
    memory_disposition_artifact: CycleArtifactRef
    validation_status: LearningValidationResult
    memory_disposition: MemoryDisposition
    learning_producer_id: str
    validator_id: str
    validated_learning_sha256: str
    memory_subject_sha256: str
    blockers: tuple[str, ...] = ()
    completed_steps: tuple[LifecycleClosureStep, ...] = tuple(LifecycleClosureStep)
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not isinstance(self.validation_status, LearningValidationResult):
            raise ValueError("cycle lifecycle validation status is invalid")
        if not isinstance(self.memory_disposition, MemoryDisposition):
            raise ValueError("cycle lifecycle memory disposition is invalid")
        for name in (
            "receipt_id",
            "cycle_id",
            "snapshot_id",
            "learning_producer_id",
            "validator_id",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"cycle lifecycle {name} is required")
        _require_sha256("canonical_cycle_sha256", self.canonical_cycle_sha256)
        _require_sha256("validated_learning_sha256", self.validated_learning_sha256)
        _require_sha256("memory_subject_sha256", self.memory_subject_sha256)
        if (
            self.cycle_created_at.tzinfo is None
            or self.cycle_created_at.utcoffset() != UTC.utcoffset(self.cycle_created_at)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise ValueError("cycle lifecycle created_at must be UTC")
        if self.created_at < self.cycle_created_at:
            raise ValueError("cycle lifecycle cannot precede its canonical cycle")
        if self.learning_producer_id == self.validator_id:
            raise ValueError("cycle lifecycle validator must be independent")
        if self.completed_steps != tuple(LifecycleClosureStep):
            raise ValueError("cycle lifecycle step order is immutable")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("cycle lifecycle blockers cannot contain blanks")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("cycle lifecycle blockers must be unique")
        refs = (
            (self.outcome, CycleArtifactKind.OUTCOME),
            (self.learning_proposal, CycleArtifactKind.LEARNING_PROPOSAL),
            (self.validation_result, CycleArtifactKind.VALIDATION_RESULT),
            (
                self.memory_disposition_artifact,
                CycleArtifactKind.MEMORY_DISPOSITION,
            ),
        )
        for artifact, kind in refs:
            if not isinstance(artifact, CycleArtifactRef):
                raise ValueError("cycle lifecycle artifact reference is invalid")
            if (
                artifact.cycle_id != self.cycle_id
                or artifact.snapshot_id != self.snapshot_id
            ):
                raise ValueError("cycle lifecycle artifact lineage must match")
            if artifact.artifact_kind is not kind:
                raise ValueError("cycle lifecycle artifact kind must match its role")
        if len({artifact.artifact_id for artifact, _kind in refs}) != len(refs):
            raise ValueError("cycle lifecycle artifact identities must be unique")
        if (
            self.validated_learning_sha256 != self.learning_proposal.payload_sha256
            or self.memory_subject_sha256 != self.learning_proposal.payload_sha256
        ):
            raise ValueError("cycle lifecycle validation and memory must bind learning")
        if self.memory_disposition is MemoryDisposition.ADMIT:
            if self.validation_status is not LearningValidationResult.PASS:
                raise ValueError(
                    "memory admission requires independent validation PASS"
                )
            if self.blockers:
                raise ValueError("memory admission cannot contain blockers")
        elif (
            self.validation_status is not LearningValidationResult.REJECT
            or not self.blockers
        ):
            raise ValueError(
                "memory rejection requires rejected validation and blockers"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("cycle lifecycle receipt cannot grant authority")

    @classmethod
    def bind(
        cls,
        *,
        receipt_id: str,
        cycle: CanonicalCycleEnvelope,
        created_at: datetime,
        outcome: CycleArtifactRef,
        learning_proposal: CycleArtifactRef,
        validation_result: CycleArtifactRef,
        memory_disposition_artifact: CycleArtifactRef,
        validation_status: LearningValidationResult,
        memory_disposition: MemoryDisposition,
        learning_producer_id: str,
        validator_id: str,
        blockers: tuple[str, ...] = (),
    ) -> CycleLifecycleReceipt:
        return cls(
            receipt_id=receipt_id,
            cycle_id=cycle.cycle_id,
            snapshot_id=cycle.snapshot_id,
            canonical_cycle_sha256=cycle.semantic_sha256,
            cycle_created_at=cycle.created_at,
            created_at=created_at,
            outcome=outcome,
            learning_proposal=learning_proposal,
            validation_result=validation_result,
            memory_disposition_artifact=memory_disposition_artifact,
            validation_status=validation_status,
            memory_disposition=memory_disposition,
            learning_producer_id=learning_producer_id,
            validator_id=validator_id,
            validated_learning_sha256=learning_proposal.payload_sha256,
            memory_subject_sha256=learning_proposal.payload_sha256,
            blockers=blockers,
        )

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
            "receipt_id": self.receipt_id,
            "cycle_id": self.cycle_id,
            "snapshot_id": self.snapshot_id,
            "canonical_cycle_sha256": self.canonical_cycle_sha256,
            "cycle_created_at": self.cycle_created_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "outcome": self.outcome.to_payload(),
            "learning_proposal": self.learning_proposal.to_payload(),
            "validation_result": self.validation_result.to_payload(),
            "memory_disposition_artifact": (
                self.memory_disposition_artifact.to_payload()
            ),
            "validation_status": self.validation_status.value,
            "memory_disposition": self.memory_disposition.value,
            "learning_producer_id": self.learning_producer_id,
            "validator_id": self.validator_id,
            "validated_learning_sha256": self.validated_learning_sha256,
            "memory_subject_sha256": self.memory_subject_sha256,
            "blockers": list(self.blockers),
            "completed_steps": [step.value for step in self.completed_steps],
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }
        if include_semantic_hash:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload


def _require_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


__all__ = (
    "CycleLifecycleReceipt",
    "LearningValidationResult",
    "LifecycleClosureStep",
    "MemoryDisposition",
)
