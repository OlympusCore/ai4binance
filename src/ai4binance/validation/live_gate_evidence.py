"""Exact-bound independent validation evidence for live-order gates."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from ai4binance.domain import ValidationStatus
from ai4binance.validation.promotion_evidence import PromotionEvidenceQuery

DEFAULT_MAX_EVIDENCE_AGE = timedelta(days=90)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class LiveGateEvidenceKind(StrEnum):
    """Independent validation facts required by the live gate."""

    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    TUNING = "TUNING"
    OOS = "OOS"


class LiveGateEvidenceSourceKind(StrEnum):
    """Authority classification for validation evidence sources."""

    GOVERNED_ARTIFACT = "GOVERNED_ARTIFACT"
    VALIDATION_ARTIFACT = "VALIDATION_ARTIFACT"


class LiveGateEvidenceVerificationStatus(StrEnum):
    """Explicit validation result carried by one evidence record."""

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class LiveGateEvidenceRecord:
    """One exact-subject validation fact without execution authority."""

    evidence_id: str
    evidence_kind: LiveGateEvidenceKind
    source_kind: LiveGateEvidenceSourceKind
    source_ref: str
    artifact_sha256: str
    observed_at: datetime
    verification_status: LiveGateEvidenceVerificationStatus
    strategy_id: str
    strategy_version: str
    strategy_sha256: str
    symbol: str
    market_type: str
    timeframe: str
    parameter_set_sha256: str
    dataset_sha256: str
    code_revision: str
    blockers: tuple[str, ...] = ()
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_kind, LiveGateEvidenceKind):
            raise ValueError("live gate evidence kind is invalid")
        if not isinstance(self.source_kind, LiveGateEvidenceSourceKind):
            raise ValueError("live gate evidence source kind is invalid")
        if not isinstance(self.verification_status, LiveGateEvidenceVerificationStatus):
            raise ValueError("live gate evidence verification status is invalid")
        object.__setattr__(
            self,
            "evidence_id",
            _bounded_text(self.evidence_id, "evidence_id", maximum=256),
        )
        object.__setattr__(
            self,
            "source_ref",
            _bounded_text(self.source_ref, "source_ref", maximum=1_024),
        )
        object.__setattr__(
            self,
            "artifact_sha256",
            _sha256(self.artifact_sha256, "artifact_sha256"),
        )
        observed_at = _aware_utc(self.observed_at, "observed_at")
        exact_query = PromotionEvidenceQuery(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            strategy_sha256=self.strategy_sha256,
            symbol=self.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            parameter_set_sha256=self.parameter_set_sha256,
            dataset_sha256=self.dataset_sha256,
            code_revision=self.code_revision,
            as_of=observed_at,
        )
        for field_name in (
            "strategy_id",
            "strategy_version",
            "strategy_sha256",
            "symbol",
            "market_type",
            "timeframe",
            "parameter_set_sha256",
            "dataset_sha256",
            "code_revision",
        ):
            object.__setattr__(self, field_name, getattr(exact_query, field_name))
        object.__setattr__(self, "observed_at", observed_at)
        blockers = tuple(
            dict.fromkeys(
                _bounded_text(item, "blocker", maximum=256) for item in self.blockers
            )
        )
        object.__setattr__(self, "blockers", blockers)
        if (
            self.verification_status is LiveGateEvidenceVerificationStatus.VERIFIED
        ) == bool(blockers):
            raise ValueError("live gate evidence verification result is inconsistent")
        if self.expires_at is not None:
            expires_at = _aware_utc(self.expires_at, "expires_at")
            if expires_at <= observed_at:
                raise ValueError("live gate evidence expiry must follow observation")
            object.__setattr__(self, "expires_at", expires_at)
        if self.revoked_at is not None:
            revoked_at = _aware_utc(self.revoked_at, "revoked_at")
            if revoked_at < observed_at:
                raise ValueError(
                    "live gate evidence revocation cannot predate observation"
                )
            object.__setattr__(self, "revoked_at", revoked_at)
        if (
            self.promotion_status is not ValidationStatus.RESEARCH_ONLY
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("live gate evidence cannot grant authority")

    @property
    def subject_key(self) -> tuple[str, ...]:
        return (
            self.strategy_id,
            self.strategy_version,
            self.strategy_sha256,
            self.symbol,
            self.market_type,
            self.timeframe,
            self.parameter_set_sha256,
            self.dataset_sha256,
            self.code_revision,
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the deterministic record representation used by bundle hashing."""
        return {
            "artifact_sha256": self.artifact_sha256,
            "blockers": list(self.blockers),
            "code_revision": self.code_revision,
            "dataset_sha256": self.dataset_sha256,
            "evidence_id": self.evidence_id,
            "evidence_kind": self.evidence_kind.value,
            "execution_allowed": False,
            "expires_at": _timestamp_or_none(self.expires_at),
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "market_type": self.market_type,
            "observed_at": _timestamp(self.observed_at),
            "parameter_set_sha256": self.parameter_set_sha256,
            "promotion_status": ValidationStatus.RESEARCH_ONLY.value,
            "revoked_at": _timestamp_or_none(self.revoked_at),
            "source_kind": self.source_kind.value,
            "source_ref": self.source_ref,
            "strategy_id": self.strategy_id,
            "strategy_sha256": self.strategy_sha256,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "verification_status": self.verification_status.value,
        }


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


@dataclass(frozen=True, slots=True)
class LiveGateEvidenceRegistry:
    """Resolve one current exact record per independent validation class."""

    records: tuple[LiveGateEvidenceRecord, ...] = ()
    max_evidence_age: timedelta = DEFAULT_MAX_EVIDENCE_AGE

    def __post_init__(self) -> None:
        if self.max_evidence_age <= timedelta(0):
            raise ValueError("live gate evidence age bound must be positive")
        if any(
            not isinstance(record, LiveGateEvidenceRecord) for record in self.records
        ):
            raise ValueError("live gate evidence registry records are invalid")
        evidence_ids = tuple(record.evidence_id for record in self.records)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("live gate evidence identity must be unique")

    def canonical_bundle_sha256(
        self,
        *,
        query: PromotionEvidenceQuery,
    ) -> str | None:
        selected, blockers = self._select(query)
        if blockers:
            return None
        return _bundle_sha256(query, selected)

    def resolve(
        self,
        *,
        query: PromotionEvidenceQuery,
        expected_bundle_sha256: str,
    ) -> LiveGateEvidenceResolution:
        selected, blockers = self._select(query)
        if blockers:
            return LiveGateEvidenceResolution(blockers=blockers)
        actual_bundle_sha256 = _bundle_sha256(query, selected)
        evidence_refs = tuple(
            (
                kind.value,
                selected[kind].evidence_id,
                selected[kind].artifact_sha256,
            )
            for kind in LiveGateEvidenceKind
        )
        try:
            expected = _sha256(
                expected_bundle_sha256,
                "expected_bundle_sha256",
            )
        except ValueError:
            return LiveGateEvidenceResolution(
                validation_bundle_sha256=actual_bundle_sha256,
                evidence_refs=evidence_refs,
                blockers=("LIVE_GATE_EVIDENCE_BUNDLE_HASH_INVALID",),
            )
        if actual_bundle_sha256 != expected:
            return LiveGateEvidenceResolution(
                validation_bundle_sha256=actual_bundle_sha256,
                evidence_refs=evidence_refs,
                blockers=("LIVE_GATE_EVIDENCE_BUNDLE_HASH_MISMATCH",),
            )
        return LiveGateEvidenceResolution(
            backtest_approved=True,
            walk_forward_approved=True,
            tuning_report_approved=True,
            oos_approved=True,
            validation_bundle_sha256=actual_bundle_sha256,
            evidence_refs=evidence_refs,
        )

    def _select(
        self,
        query: PromotionEvidenceQuery,
    ) -> tuple[
        dict[LiveGateEvidenceKind, LiveGateEvidenceRecord],
        tuple[str, ...],
    ]:
        selected: dict[LiveGateEvidenceKind, LiveGateEvidenceRecord] = {}
        blockers: list[str] = []
        for kind in LiveGateEvidenceKind:
            matching = tuple(
                record
                for record in self.records
                if record.evidence_kind is kind
                and record.subject_key == query.subject_key
            )
            prefix = f"LIVE_GATE_EVIDENCE_{kind.value}"
            if not matching:
                blockers.append(f"{prefix}_MISSING")
                continue
            latest_at = max(record.observed_at for record in matching)
            latest = tuple(
                record for record in matching if record.observed_at == latest_at
            )
            if len(latest) != 1:
                blockers.append(f"{prefix}_AMBIGUOUS")
                continue
            record = latest[0]
            current_blocker = self._current_blocker(record, query)
            if current_blocker is not None:
                blockers.append(f"{prefix}_{current_blocker}")
                continue
            selected[kind] = record
        return selected, tuple(blockers)

    def _current_blocker(
        self,
        record: LiveGateEvidenceRecord,
        query: PromotionEvidenceQuery,
    ) -> str | None:
        as_of = query.as_of.astimezone(UTC)
        observed_at = record.observed_at.astimezone(UTC)
        if record.source_kind is not LiveGateEvidenceSourceKind.GOVERNED_ARTIFACT:
            return "SOURCE_NOT_GOVERNED"
        if observed_at > as_of:
            return "FUTURE_DATED"
        if as_of - observed_at > self.max_evidence_age:
            return "STALE"
        if record.expires_at is not None and record.expires_at <= as_of:
            return "EXPIRED"
        if record.revoked_at is not None and record.revoked_at <= as_of:
            return "REVOKED"
        if (
            record.verification_status
            is not LiveGateEvidenceVerificationStatus.VERIFIED
        ):
            return "NOT_VERIFIED"
        if record.blockers:
            return "BLOCKED"
        return None


def _bundle_sha256(
    query: PromotionEvidenceQuery,
    selected: dict[LiveGateEvidenceKind, LiveGateEvidenceRecord],
) -> str:
    payload = {
        "evidence": [
            selected[kind].canonical_payload() for kind in LiveGateEvidenceKind
        ],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "promotion_status": ValidationStatus.RESEARCH_ONLY.value,
        "schema_version": "1.0.0",
        "subject": {
            "code_revision": query.code_revision,
            "dataset_sha256": query.dataset_sha256,
            "market_type": query.market_type,
            "parameter_set_sha256": query.parameter_set_sha256,
            "strategy_id": query.strategy_id,
            "strategy_sha256": query.strategy_sha256,
            "strategy_version": query.strategy_version,
            "symbol": query.symbol,
            "timeframe": query.timeframe,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"live gate evidence {field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timestamp_or_none(value: datetime | None) -> str | None:
    return _timestamp(value) if value is not None else None
