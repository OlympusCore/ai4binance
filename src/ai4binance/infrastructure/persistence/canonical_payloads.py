"""Bounded explanation artifacts for existing canonical research receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ai4binance.domain.research.canonical_cycle import (
    CycleArtifactKind,
    CycleArtifactRef,
)
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified

MAX_EXPLANATION_BYTES = 16_000
_EXPLANATION_KINDS = frozenset(
    {
        CycleArtifactKind.DECISION,
        CycleArtifactKind.GOVERNANCE_RESULT,
        CycleArtifactKind.AUDIT_TRAIL,
        CycleArtifactKind.VIRTUAL_SIMULATION_PLAN,
    }
)


def _encoded(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class CanonicalExplanationStore:
    """Preserve produced explanations; never reconstruct or authorize a decision."""

    directory: Path
    boundary: Path

    def path_for(self, reference: CycleArtifactRef) -> Path:
        if reference.artifact_kind not in _EXPLANATION_KINDS:
            raise ValueError("CANONICAL_EXPLANATION_KIND_NOT_ALLOWED")
        key = hashlib.sha256(_encoded(reference.to_payload())).hexdigest()
        path = self.directory / f"{key}.json"
        if not self.directory.resolve().is_relative_to(self.boundary.resolve()):
            raise ValueError("CANONICAL_EXPLANATION_OUTSIDE_BOUNDARY")
        if self.directory.is_symlink() or path.is_symlink():
            raise ValueError("CANONICAL_EXPLANATION_SYMLINK_BLOCKED")
        return path

    @staticmethod
    def _verify(reference: CycleArtifactRef, body: Mapping[str, object]) -> None:
        expected = reference.to_payload()
        if set(body) != {*expected, "payload"} or any(
            body.get(key) != value for key, value in expected.items()
        ):
            raise ValueError("CANONICAL_EXPLANATION_CONTEXT_MISMATCH")
        if (
            not isinstance(body["payload"], dict)
            or len(_encoded(body)) > MAX_EXPLANATION_BYTES
            or hashlib.sha256(_encoded(body["payload"])).hexdigest()
            != reference.payload_sha256
        ):
            raise ValueError("CANONICAL_EXPLANATION_PAYLOAD_INVALID")

    def read(self, reference: CycleArtifactRef) -> dict[str, object] | None:
        path = self.path_for(reference)
        if not path.exists():
            return None
        with path.open("rb") as stream:
            raw = stream.read(MAX_EXPLANATION_BYTES + 2)
        if len(raw) > MAX_EXPLANATION_BYTES + 1:
            raise ValueError("CANONICAL_EXPLANATION_TOO_LARGE")
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("CANONICAL_EXPLANATION_OBJECT_REQUIRED")
        self._verify(reference, body)
        return body

    def save(self, reference: CycleArtifactRef, body: Mapping[str, object]) -> None:
        path = self.path_for(reference)
        self._verify(reference, body)
        previous = self.read(reference)
        if previous is not None:
            if previous != dict(body):
                raise ValueError("CANONICAL_EXPLANATION_IMMUTABLE_CONFLICT")
            return
        write_json_object_verified(
            path,
            body,
            blocker="CANONICAL_EXPLANATION_WRITE_VERIFY_FAILED",
            subject_id=reference.artifact_id,
            durable=True,
        )
        if self.read(reference) != dict(body):
            raise ValueError("CANONICAL_EXPLANATION_WRITE_VERIFY_FAILED")
