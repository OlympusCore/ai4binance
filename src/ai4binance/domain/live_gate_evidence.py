"""Canonical immutable live validation resolution and evidence references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ai4binance.domain import ValidationStatus

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class LiveGateEvidenceKind(StrEnum):
    """Independent validation facts required by the live gate."""

    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    TUNING = "TUNING"
    OOS = "OOS"


@dataclass(frozen=True, slots=True)
class LiveGateEvidenceResolution:
    """Secret-safe resolution result for all four validation gates."""

    backtest_approved: bool = False
    walk_forward_approved: bool = False
    tuning_report_approved: bool = False
    oos_approved: bool = False
    validation_bundle_sha256: str | None = None
    evidence_refs: tuple[tuple[str, str, str], ...] = ()
    blockers: tuple[str, ...] = ()
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        flags = (
            self.backtest_approved,
            self.walk_forward_approved,
            self.tuning_report_approved,
            self.oos_approved,
        )
        if any(type(flag) is not bool for flag in flags):
            raise ValueError("live gate evidence approval flags must be boolean")
        if any(flags) and not all(flags):
            raise ValueError("partial live gate validation bundle is not permitted")
        if self.validation_bundle_sha256 is not None:
            object.__setattr__(
                self,
                "validation_bundle_sha256",
                _sha256(
                    self.validation_bundle_sha256,
                    "validation_bundle_sha256",
                ),
            )
        normalized_refs: list[tuple[str, str, str]] = []
        for raw_kind, raw_evidence_id, raw_artifact_sha256 in self.evidence_refs:
            try:
                kind = LiveGateEvidenceKind(raw_kind)
            except ValueError:
                raise ValueError(
                    "live gate evidence reference kind is invalid"
                ) from None
            normalized_refs.append(
                (
                    kind.value,
                    _bounded_text(raw_evidence_id, "evidence_id", maximum=256),
                    _sha256(raw_artifact_sha256, "artifact_sha256"),
                )
            )
        expected_kinds = tuple(kind.value for kind in LiveGateEvidenceKind)
        normalized_refs_tuple = tuple(normalized_refs)
        if normalized_refs_tuple and (
            self.validation_bundle_sha256 is None
            or tuple(item[0] for item in normalized_refs_tuple) != expected_kinds
        ):
            raise ValueError(
                "live gate evidence references are incomplete or unordered"
            )
        object.__setattr__(self, "evidence_refs", normalized_refs_tuple)
        blockers = tuple(
            dict.fromkeys(
                _bounded_text(item, "blocker", maximum=256) for item in self.blockers
            )
        )
        object.__setattr__(self, "blockers", blockers)
        if all(flags) and (
            self.validation_bundle_sha256 is None
            or len(normalized_refs_tuple) != len(LiveGateEvidenceKind)
            or blockers
        ):
            raise ValueError("approved live gate evidence must be complete and clear")
        if (
            self.promotion_status is not ValidationStatus.RESEARCH_ONLY
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("live gate evidence resolution cannot grant authority")


def _bounded_text(value: object, field_name: str, *, maximum: int) -> str:
    normalized = str(value).strip()
    if (
        not normalized
        or len(normalized) > maximum
        or not normalized.isascii()
        or any(character in normalized for character in "\r\n\0")
    ):
        raise ValueError(f"live gate evidence {field_name} is invalid")
    return normalized


def _sha256(value: object, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"live gate evidence {field_name} is invalid")
    return normalized
