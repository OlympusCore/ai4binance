"""Evidence-backed development run cards inspired by strict TDD workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DevelopmentStage(StrEnum):
    SPEC_REGISTERED = "SPEC_REGISTERED"
    TEST_RED_CONFIRMED = "TEST_RED_CONFIRMED"
    MINIMAL_IMPLEMENTATION = "MINIMAL_IMPLEMENTATION"
    SPEC_REVIEW_PASSED = "SPEC_REVIEW_PASSED"
    CODE_REVIEW_PASSED = "CODE_REVIEW_PASSED"
    QUALITY_GATE_PASSED = "QUALITY_GATE_PASSED"
    COMPLETED = "COMPLETED"


_ORDER = tuple(DevelopmentStage)


@dataclass(frozen=True, slots=True)
class StageEvidence:
    stage: DevelopmentStage
    recorded_at: datetime
    artifact_sha256: str
    summary: str
    passed: bool

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("development evidence timestamp must be timezone-aware")
        if not _SHA256.fullmatch(self.artifact_sha256):
            raise ValueError("development evidence hash is invalid")
        if not self.summary.strip() or len(self.summary) > 2_000:
            raise ValueError("development evidence summary is invalid")
        if not self.passed:
            raise ValueError("failed evidence cannot advance a development run")


@dataclass(frozen=True, slots=True)
class DevelopmentRunCard:
    run_id: str
    objective: str
    stage: DevelopmentStage
    evidence: tuple[StageEvidence, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.objective.strip():
            raise ValueError("development run requires identity and objective")
        if len(self.objective) > 2_000:
            raise ValueError("development objective is too large")
        if not self.evidence or self.evidence[-1].stage is not self.stage:
            raise ValueError("development evidence must end at the current stage")
        if tuple(item.stage for item in self.evidence) != _ORDER[: len(self.evidence)]:
            raise ValueError("development evidence stages must be contiguous")
        if self.execution_allowed:
            raise ValueError("development governance cannot authorize trading")

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        objective: str,
        evidence: StageEvidence,
    ) -> DevelopmentRunCard:
        if evidence.stage is not DevelopmentStage.SPEC_REGISTERED:
            raise ValueError("development run must start with a registered spec")
        return cls(run_id, objective, evidence.stage, (evidence,))

    def advance(
        self,
        evidence: StageEvidence,
        *,
        human_approved: bool = False,
    ) -> DevelopmentRunCard:
        current_index = _ORDER.index(self.stage)
        if (
            current_index + 1 >= len(_ORDER)
            or evidence.stage is not _ORDER[current_index + 1]
        ):
            raise ValueError("development stage transition must be contiguous")
        if evidence.stage is DevelopmentStage.COMPLETED and not human_approved:
            raise ValueError("development completion requires human approval")
        return replace(
            self,
            stage=evidence.stage,
            evidence=(*self.evidence, evidence),
        )


@dataclass(frozen=True, slots=True)
class DevelopmentRunCardWriter:
    """Atomically persist a development run card and optional audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, card: DevelopmentRunCard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(card)),
            blocker="DEVELOPMENT_RUN_CARD_DESTINATION_VERIFY_FAILED",
            subject_id=card.run_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="DEVELOPMENT_RUN_CARD_WRITTEN",
                    timestamp=card.evidence[-1].recorded_at,
                    payload={"run_card": card},
                )
            )
