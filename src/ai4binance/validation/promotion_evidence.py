"""Promotion evidence registry and ledger for non-summary promotion sources."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import cast

from ai4binance.domain import ValidationStatus
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore
from ai4binance.validation.summary import ValidationSummary

DEFAULT_MAX_EVIDENCE_AGE = timedelta(days=90)
DEFAULT_FUTURE_TOLERANCE = timedelta(minutes=5)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CODE_REVISION_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class PromotionEvidenceSourceKind(StrEnum):
    """Stable promotion evidence source labels."""

    VALIDATION_SUMMARY = "VALIDATION_SUMMARY"
    VALIDATION_LEDGER = "VALIDATION_LEDGER"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    GOVERNED_ARTIFACT = "GOVERNED_ARTIFACT"


@dataclass(frozen=True, slots=True)
class PromotionEvidenceQuery:
    """Exact strategy and evidence identity required for promotion resolution."""

    strategy_id: str
    strategy_version: str
    strategy_sha256: str
    symbol: str
    market_type: str
    timeframe: str
    parameter_set_sha256: str
    dataset_sha256: str
    code_revision: str
    as_of: datetime

    def __post_init__(self) -> None:
        _normalize_exact_identity(self)
        _require_aware(self.as_of, "promotion query as_of")

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


@dataclass(frozen=True, slots=True)
class PromotionEvidenceRecord:
    """One bounded promotion evidence item from a named source."""

    evidence_id: str
    symbol: str
    source_kind: PromotionEvidenceSourceKind
    source_ref: str
    observed_at: datetime
    promotion_status: ValidationStatus
    timeframe: str | None = None
    blockers: tuple[str, ...] = ()
    strategy_id: str | None = None
    strategy_version: str | None = None
    strategy_sha256: str | None = None
    market_type: str | None = None
    parameter_set_sha256: str | None = None
    dataset_sha256: str | None = None
    code_revision: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.evidence_id, self.symbol, self.source_ref)
        ):
            raise ValueError("promotion evidence identity is required")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.timeframe is not None:
            if not self.timeframe.strip():
                raise ValueError("promotion evidence timeframe cannot be blank")
            object.__setattr__(self, "timeframe", self.timeframe.strip())
        _require_aware(self.observed_at, "promotion evidence timestamp")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
            ValidationStatus.PAPER_APPROVED,
            ValidationStatus.LIVE_ELIGIBLE,
        }:
            raise ValueError("promotion evidence status is invalid")
        exact_values = (
            self.strategy_id,
            self.strategy_version,
            self.strategy_sha256,
            self.market_type,
            self.parameter_set_sha256,
            self.dataset_sha256,
            self.code_revision,
        )
        if any(value is not None for value in exact_values):
            if self.timeframe is None or not all(
                value is not None for value in exact_values
            ):
                raise ValueError("promotion evidence exact identity must be complete")
            _normalize_exact_identity(self)
        if (
            self.promotion_status is ValidationStatus.LIVE_ELIGIBLE
            and not self.is_exact_bound
        ):
            raise ValueError("live-eligible promotion evidence must be exact-bound")
        if (
            self.promotion_status is ValidationStatus.LIVE_ELIGIBLE
            and self.source_kind is not PromotionEvidenceSourceKind.GOVERNED_ARTIFACT
        ):
            raise ValueError("live-eligible promotion requires a governed artifact")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "promotion evidence expiry")
            if self.expires_at <= self.observed_at:
                raise ValueError("promotion evidence expiry must follow observation")
        if self.revoked_at is not None:
            _require_aware(self.revoked_at, "promotion evidence revocation")
            if self.revoked_at < self.observed_at:
                raise ValueError(
                    "promotion evidence revocation cannot predate observation"
                )
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("promotion evidence cannot grant execution authority")

    @property
    def is_exact_bound(self) -> bool:
        return self.exact_subject_key is not None

    @property
    def exact_subject_key(self) -> tuple[str, ...] | None:
        values = (
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
        if any(value is None for value in values):
            return None
        return cast(tuple[str, ...], values)


@dataclass(frozen=True, slots=True)
class PromotionEvidenceRegistry:
    """Resolve only current, exact-bound promotion evidence."""

    records: tuple[PromotionEvidenceRecord, ...] = ()
    max_evidence_age: timedelta = DEFAULT_MAX_EVIDENCE_AGE
    future_tolerance: timedelta = DEFAULT_FUTURE_TOLERANCE

    def __post_init__(self) -> None:
        if self.max_evidence_age <= timedelta(0):
            raise ValueError("promotion evidence age bound must be positive")
        if self.future_tolerance < timedelta(0):
            raise ValueError("promotion future tolerance cannot be negative")

    def resolve(
        self,
        *,
        query: PromotionEvidenceQuery,
    ) -> ValidationStatus:
        matched = tuple(
            record
            for record in self.records
            if record.exact_subject_key == query.subject_key
        )
        if not matched:
            return ValidationStatus.RESEARCH_ONLY
        latest_observed_at = max(
            record.observed_at.astimezone(UTC) for record in matched
        )
        latest_records = tuple(
            record
            for record in matched
            if record.observed_at.astimezone(UTC) == latest_observed_at
        )
        if len(latest_records) != 1:
            return ValidationStatus.RESEARCH_ONLY
        latest = latest_records[0]
        if not self._is_current(latest, query):
            return ValidationStatus.RESEARCH_ONLY
        return latest.promotion_status

    def has_promotion_evidence(
        self,
        *,
        query: PromotionEvidenceQuery,
    ) -> bool:
        return self.resolve(query=query) in {
            ValidationStatus.STAGED_CANDIDATE,
            ValidationStatus.PAPER_APPROVED,
            ValidationStatus.LIVE_ELIGIBLE,
        }

    def _is_current(
        self,
        record: PromotionEvidenceRecord,
        query: PromotionEvidenceQuery,
    ) -> bool:
        as_of = query.as_of.astimezone(UTC)
        observed_at = record.observed_at.astimezone(UTC)
        age = as_of - observed_at
        return not (
            record.blockers
            or age < -self.future_tolerance
            or age > self.max_evidence_age
            or (record.expires_at is not None and record.expires_at <= query.as_of)
            or (record.revoked_at is not None and record.revoked_at <= query.as_of)
        )

    @classmethod
    def from_validation_summary(
        cls, summary: ValidationSummary
    ) -> PromotionEvidenceRegistry:
        records = tuple(
            PromotionEvidenceRecord(
                evidence_id=f"{summary.symbol}:{run.timeframe}:{run.run_id}",
                symbol=summary.symbol,
                source_kind=PromotionEvidenceSourceKind.VALIDATION_SUMMARY,
                source_ref=run.run_id,
                observed_at=datetime.fromisoformat(run.created_at),
                promotion_status=ValidationStatus(run.promotion_status),
                timeframe=run.timeframe,
                blockers=run.blockers,
            )
            for run in summary.runs
        )
        return cls(records)

    @classmethod
    def from_records(
        cls,
        records: Iterable[PromotionEvidenceRecord],
        *,
        max_evidence_age: timedelta = DEFAULT_MAX_EVIDENCE_AGE,
        future_tolerance: timedelta = DEFAULT_FUTURE_TOLERANCE,
    ) -> PromotionEvidenceRegistry:
        return cls(tuple(records), max_evidence_age, future_tolerance)

    def with_record(self, record: PromotionEvidenceRecord) -> PromotionEvidenceRegistry:
        return PromotionEvidenceRegistry(
            (*self.records, record),
            self.max_evidence_age,
            self.future_tolerance,
        )


@dataclass(frozen=True, slots=True)
class PromotionEvidenceLedger:
    """Append-only promotion evidence storage with verified writes."""

    path: Path

    def append(self, record: PromotionEvidenceRecord) -> None:
        JsonlAuditStore(self.path, durable=True).append_verified(
            AuditEvent(
                event_type="PROMOTION_EVIDENCE_RECORDED",
                timestamp=record.observed_at,
                payload={"record": to_primitive(record)},
            )
        )

    def records(self) -> tuple[PromotionEvidenceRecord, ...]:
        if not self.path.exists():
            return ()
        output: list[PromotionEvidenceRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            raw = payload.get("payload")
            if not isinstance(raw, dict):
                continue
            record = raw.get("record")
            if isinstance(record, dict):
                output.append(_record_from_payload(record))
        return tuple(output)

    def as_registry(self) -> PromotionEvidenceRegistry:
        return PromotionEvidenceRegistry.from_records(self.records())

    def append_if_absent(self, record: PromotionEvidenceRecord) -> bool:
        """Append a record only when an identical evidence identity is missing."""
        if any(
            existing.evidence_id == record.evidence_id for existing in self.records()
        ):
            return False
        self.append(record)
        return True


def _record_from_payload(payload: dict[str, object]) -> PromotionEvidenceRecord:
    return PromotionEvidenceRecord(
        evidence_id=str(payload["evidence_id"]),
        symbol=str(payload["symbol"]),
        source_kind=PromotionEvidenceSourceKind(str(payload["source_kind"])),
        source_ref=str(payload["source_ref"]),
        observed_at=datetime.fromisoformat(str(payload["observed_at"])),
        promotion_status=ValidationStatus(str(payload["promotion_status"])),
        timeframe=(
            str(payload["timeframe"]) if payload.get("timeframe") is not None else None
        ),
        blockers=tuple(
            str(item) for item in cast(Iterable[object], payload.get("blockers", ()))
        ),
        strategy_id=_optional_text(payload, "strategy_id"),
        strategy_version=_optional_text(payload, "strategy_version"),
        strategy_sha256=_optional_text(payload, "strategy_sha256"),
        market_type=_optional_text(payload, "market_type"),
        parameter_set_sha256=_optional_text(payload, "parameter_set_sha256"),
        dataset_sha256=_optional_text(payload, "dataset_sha256"),
        code_revision=_optional_text(payload, "code_revision"),
        expires_at=_optional_datetime(payload, "expires_at"),
        revoked_at=_optional_datetime(payload, "revoked_at"),
        execution_allowed=bool(payload.get("execution_allowed", False)),
        live_eligibility_status=str(
            payload.get("live_eligibility_status", "LIVE_ORDER_BLOCKED")
        ),
    )


def _normalize_exact_identity(
    value: PromotionEvidenceQuery | PromotionEvidenceRecord,
) -> None:
    text_fields = ("strategy_id", "strategy_version", "timeframe")
    for field_name in text_fields:
        raw_value = getattr(value, field_name)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"promotion {field_name} is required")
        object.__setattr__(value, field_name, raw_value.strip())
    symbol = value.symbol.strip().upper()
    if not symbol.isascii() or not symbol.isalnum():
        raise ValueError("promotion symbol identity is invalid")
    object.__setattr__(value, "symbol", symbol)
    market_type = value.market_type
    if not isinstance(market_type, str):
        raise ValueError("promotion market type is required")
    normalized_market = market_type.strip().upper()
    if normalized_market not in {"SPOT", "USD_M_FUTURES"}:
        raise ValueError("promotion market type is invalid")
    object.__setattr__(value, "market_type", normalized_market)
    for field_name in (
        "strategy_sha256",
        "parameter_set_sha256",
        "dataset_sha256",
    ):
        raw_value = getattr(value, field_name)
        if not isinstance(raw_value, str) or not _SHA256_PATTERN.fullmatch(raw_value):
            raise ValueError(f"promotion {field_name} is invalid")
    code_revision = value.code_revision
    if not isinstance(code_revision, str) or not _CODE_REVISION_PATTERN.fullmatch(
        code_revision
    ):
        raise ValueError("promotion code revision is invalid")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _optional_datetime(payload: dict[str, object], key: str) -> datetime | None:
    value = payload.get(key)
    return datetime.fromisoformat(str(value)) if value is not None else None
