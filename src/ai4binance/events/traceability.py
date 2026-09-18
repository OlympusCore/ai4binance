"""Canonical trace records and append-only journals for consequential events."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from ai4binance.events.journal import DiskEventJournal
from ai4binance.events.models import DomainEvent

_TRACE_EVENT_TYPE = "CONSEQUENTIAL_TRACE_RECORDED"
_TRACE_AGGREGATE_ID = "AI4BINANCE_CANONICAL_TRACE_JOURNAL"
_TRACE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class ConsequentialTraceKind(StrEnum):
    CONSEQUENTIAL_BEHAVIOR = "CONSEQUENTIAL_BEHAVIOR"
    STATE_TRANSITION = "STATE_TRANSITION"
    DECISION = "DECISION"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    BLOCKER = "BLOCKER"
    GATE = "GATE"
    APPROVAL = "APPROVAL"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    GOVERNED_CHANGE = "GOVERNED_CHANGE"
    EXECUTION_ATTEMPT = "EXECUTION_ATTEMPT"
    LEARNING_CANDIDATE = "LEARNING_CANDIDATE"
    PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"


class TraceabilityStatus(StrEnum):
    PASS = "P" + "ASS"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


def canonical_trace_journal_path(repository_root: Path) -> Path:
    return (
        repository_root.resolve()
        / "runtime"
        / "artifacts"
        / "governance"
        / "trace"
        / "canonical_event_journal.jsonl"
    )


def canonical_trace_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalTraceRecord:
    trace_id: str
    trace_kind: ConsequentialTraceKind
    subject_ref: str
    subject_type: str
    occurred_at: datetime
    event_name: str
    event_status: str
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    related_refs: tuple[str, ...] = ()
    governed_paths: tuple[str, ...] = ()
    approval_ref: str = ""
    subject_sha256: str = ""
    record_sha256: str = ""
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("trace id", self.trace_id)
        _require_text("trace subject_ref", self.subject_ref)
        _require_text("trace subject_type", self.subject_type)
        _require_trace_name("trace event_name", self.event_name)
        _require_text("trace event_status", self.event_status)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("trace timestamp must be timezone-aware")
        _require_unique_nonblank("trace evidence refs", self.evidence_refs)
        _require_unique_nonblank("trace blockers", self.blockers)
        _require_unique_nonblank("trace related refs", self.related_refs)
        _require_unique_nonblank("trace governed paths", self.governed_paths)
        if self.approval_ref:
            _require_text("trace approval_ref", self.approval_ref)
        if self.trace_kind is ConsequentialTraceKind.APPROVAL and not self.approval_ref:
            raise ValueError("approval trace requires approval_ref")
        if (
            self.trace_kind
            in {
                ConsequentialTraceKind.CONFIG_CHANGE,
                ConsequentialTraceKind.GOVERNED_CHANGE,
            }
            and not self.governed_paths
        ):
            raise ValueError("governed/config change trace requires governed paths")
        for name, value in (
            ("trace subject_sha256", self.subject_sha256),
            ("trace record_sha256", self.record_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase sha256 hex digest")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("canonical trace record cannot authorize execution")
        if self.record_sha256 != self.compute_hash(
            trace_id=self.trace_id,
            trace_kind=self.trace_kind,
            subject_ref=self.subject_ref,
            subject_type=self.subject_type,
            occurred_at=self.occurred_at,
            event_name=self.event_name,
            event_status=self.event_status,
            evidence_refs=self.evidence_refs,
            blockers=self.blockers,
            related_refs=self.related_refs,
            governed_paths=self.governed_paths,
            approval_ref=self.approval_ref,
            subject_sha256=self.subject_sha256,
        ):
            raise ValueError("canonical trace record hash is invalid")

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        trace_kind: ConsequentialTraceKind,
        subject_ref: str,
        subject_type: str,
        occurred_at: datetime,
        event_name: str,
        event_status: str,
        evidence_refs: tuple[str, ...],
        blockers: tuple[str, ...] = (),
        related_refs: tuple[str, ...] = (),
        governed_paths: tuple[str, ...] = (),
        approval_ref: str = "",
        subject_sha256: str,
    ) -> CanonicalTraceRecord:
        record_sha256 = cls.compute_hash(
            trace_id=trace_id,
            trace_kind=trace_kind,
            subject_ref=subject_ref,
            subject_type=subject_type,
            occurred_at=occurred_at,
            event_name=event_name,
            event_status=event_status,
            evidence_refs=evidence_refs,
            blockers=blockers,
            related_refs=related_refs,
            governed_paths=governed_paths,
            approval_ref=approval_ref,
            subject_sha256=subject_sha256,
        )
        return cls(
            trace_id=trace_id,
            trace_kind=trace_kind,
            subject_ref=subject_ref,
            subject_type=subject_type,
            occurred_at=occurred_at,
            event_name=event_name,
            event_status=event_status,
            evidence_refs=evidence_refs,
            blockers=blockers,
            related_refs=related_refs,
            governed_paths=governed_paths,
            approval_ref=approval_ref,
            subject_sha256=subject_sha256,
            record_sha256=record_sha256,
        )

    @staticmethod
    def compute_hash(
        *,
        trace_id: str,
        trace_kind: ConsequentialTraceKind,
        subject_ref: str,
        subject_type: str,
        occurred_at: datetime,
        event_name: str,
        event_status: str,
        evidence_refs: tuple[str, ...],
        blockers: tuple[str, ...],
        related_refs: tuple[str, ...],
        governed_paths: tuple[str, ...],
        approval_ref: str,
        subject_sha256: str,
    ) -> str:
        canonical = json.dumps(
            {
                "approval_ref": approval_ref,
                "blockers": blockers,
                "evidence_refs": evidence_refs,
                "event_name": event_name,
                "event_status": event_status,
                "governed_paths": governed_paths,
                "occurred_at": occurred_at.isoformat(),
                "related_refs": related_refs,
                "subject_ref": subject_ref,
                "subject_sha256": subject_sha256,
                "subject_type": subject_type,
                "trace_id": trace_id,
                "trace_kind": trace_kind.value,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "trace_kind": self.trace_kind.value,
            "subject_ref": self.subject_ref,
            "subject_type": self.subject_type,
            "occurred_at": self.occurred_at.isoformat(),
            "event_name": self.event_name,
            "event_status": self.event_status,
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "related_refs": list(self.related_refs),
            "governed_paths": list(self.governed_paths),
            "approval_ref": self.approval_ref,
            "subject_sha256": self.subject_sha256,
            "record_sha256": self.record_sha256,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }

    def to_domain_event(
        self,
        *,
        sequence: int,
        previous_hash: str = "GENESIS",
    ) -> DomainEvent:
        payload = (
            ("approval_ref", self.approval_ref),
            (
                "blockers_json",
                json.dumps(self.blockers, ensure_ascii=True, separators=(",", ":")),
            ),
            (
                "evidence_refs_json",
                json.dumps(
                    self.evidence_refs,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            ),
            ("event_name", self.event_name),
            ("event_status", self.event_status),
            (
                "governed_paths_json",
                json.dumps(
                    self.governed_paths,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            ),
            ("record_sha256", self.record_sha256),
            (
                "related_refs_json",
                json.dumps(
                    self.related_refs,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            ),
            ("subject_ref", self.subject_ref),
            ("subject_sha256", self.subject_sha256),
            ("subject_type", self.subject_type),
            ("trace_id", self.trace_id),
            ("trace_kind", self.trace_kind.value),
        )
        return DomainEvent.create(
            event_id=self.trace_id,
            aggregate_id=_TRACE_AGGREGATE_ID,
            event_type=_TRACE_EVENT_TYPE,
            sequence=sequence,
            occurred_at=self.occurred_at,
            payload=payload,
            previous_hash=previous_hash,
        )

    @classmethod
    def from_domain_event(cls, event: DomainEvent) -> CanonicalTraceRecord:
        if event.event_type != _TRACE_EVENT_TYPE:
            raise ValueError("domain event is not a canonical trace record")
        payload = event.payload_dict()
        return cls(
            trace_id=_required_text(payload.get("trace_id"), "trace_id"),
            trace_kind=ConsequentialTraceKind(
                _required_text(payload.get("trace_kind"), "trace_kind")
            ),
            subject_ref=_required_text(payload.get("subject_ref"), "subject_ref"),
            subject_type=_required_text(payload.get("subject_type"), "subject_type"),
            occurred_at=event.occurred_at,
            event_name=_required_text(payload.get("event_name"), "event_name"),
            event_status=_required_text(payload.get("event_status"), "event_status"),
            evidence_refs=_json_text_tuple(
                payload.get("evidence_refs_json"),
                "trace evidence refs",
            ),
            blockers=_json_text_tuple(
                payload.get("blockers_json"),
                "trace blockers",
            ),
            related_refs=_json_text_tuple(
                payload.get("related_refs_json"),
                "trace related refs",
            ),
            governed_paths=_json_text_tuple(
                payload.get("governed_paths_json"),
                "trace governed paths",
            ),
            approval_ref=str(payload.get("approval_ref", "")),
            subject_sha256=_required_text(
                payload.get("subject_sha256"),
                "subject_sha256",
            ),
            record_sha256=_required_text(payload.get("record_sha256"), "record_sha256"),
        )


@dataclass(frozen=True, slots=True)
class TraceabilityRequirement:
    trace_kind: ConsequentialTraceKind
    subject_ref: str
    event_name: str = ""
    subject_type: str = ""
    approval_ref: str = ""

    def __post_init__(self) -> None:
        _require_text("traceability subject_ref", self.subject_ref)
        if self.event_name:
            _require_trace_name("traceability event_name", self.event_name)
        if self.subject_type:
            _require_text("traceability subject_type", self.subject_type)
        if self.approval_ref:
            _require_text("traceability approval_ref", self.approval_ref)

    def matches(self, record: CanonicalTraceRecord) -> bool:
        return (
            record.trace_kind is self.trace_kind
            and record.subject_ref == self.subject_ref
            and (not self.event_name or record.event_name == self.event_name)
            and (not self.subject_type or record.subject_type == self.subject_type)
            and (not self.approval_ref or record.approval_ref == self.approval_ref)
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "trace_kind": self.trace_kind.value,
            "subject_ref": self.subject_ref,
            "event_name": self.event_name,
            "subject_type": self.subject_type,
            "approval_ref": self.approval_ref,
        }


@dataclass(frozen=True, slots=True)
class TraceabilityAuditReport:
    journal_path: Path
    status: TraceabilityStatus
    requirement_count: int
    record_count: int
    blockers: tuple[str, ...] = ()
    missing_requirements: tuple[TraceabilityRequirement, ...] = ()

    def __post_init__(self) -> None:
        if not self.journal_path.is_absolute():
            raise ValueError("traceability audit journal_path must be absolute")
        if self.requirement_count < 0 or self.record_count < 0:
            raise ValueError("traceability audit counts must be non-negative")
        _require_unique_nonblank("traceability blockers", self.blockers)
        if self.status is TraceabilityStatus.PASS and (
            self.blockers or self.missing_requirements
        ):
            raise ValueError("passing traceability audit cannot contain blockers")
        if (
            self.status is TraceabilityStatus.RUNNING_WITH_BLOCKERS
            and not self.blockers
        ):
            raise ValueError("blocked traceability audit requires blockers")

    def to_payload(self) -> dict[str, object]:
        return {
            "journal_path": str(self.journal_path),
            "status": self.status.value,
            "requirement_count": self.requirement_count,
            "record_count": self.record_count,
            "blockers": list(self.blockers),
            "missing_requirements": [
                requirement.to_payload() for requirement in self.missing_requirements
            ],
        }


@dataclass(slots=True)
class CanonicalTraceJournal:
    path: Path
    durable: bool = False

    def append(self, record: CanonicalTraceRecord) -> DomainEvent:
        journal = self._journal()
        events = journal.load()
        if any(
            existing.payload_dict().get("trace_id") == record.trace_id
            for existing in events
        ):
            raise ValueError("canonical trace_id already exists in journal")
        event = journal.append_next(
            lambda sequence, previous_hash: record.to_domain_event(
                sequence=sequence,
                previous_hash=previous_hash,
            )
        )
        observed = self.records()
        if not observed or observed[-1] != record:
            raise ValueError("canonical trace journal destination verification failed")
        return event

    def append_if_absent(self, record: CanonicalTraceRecord) -> bool:
        if any(existing.trace_id == record.trace_id for existing in self.records()):
            return False
        self.append(record)
        return True

    def records(self) -> tuple[CanonicalTraceRecord, ...]:
        records = tuple(
            CanonicalTraceRecord.from_domain_event(event)
            for event in self._journal().load()
        )
        trace_ids = tuple(record.trace_id for record in records)
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("canonical trace journal contains duplicate trace_ids")
        return records

    def audit(
        self,
        requirements: tuple[TraceabilityRequirement, ...],
    ) -> TraceabilityAuditReport:
        records = self.records()
        missing = tuple(
            requirement
            for requirement in requirements
            if not any(requirement.matches(record) for record in records)
        )
        blockers: list[str] = []
        if requirements and not records:
            blockers.append("CANONICAL_TRACE_JOURNAL_EMPTY")
        if missing:
            blockers.append("CANONICAL_TRACE_REQUIREMENT_MISSING")
        return TraceabilityAuditReport(
            journal_path=self.path.resolve(),
            status=(
                TraceabilityStatus.PASS
                if not blockers
                else TraceabilityStatus.RUNNING_WITH_BLOCKERS
            ),
            requirement_count=len(requirements),
            record_count=len(records),
            blockers=tuple(dict.fromkeys(blockers)),
            missing_requirements=missing,
        )

    def _journal(self) -> DiskEventJournal:
        return DiskEventJournal(self.path.resolve(), durable=self.durable)


def _json_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be encoded as JSON text")
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError(f"{label} JSON payload must decode to a list")
    return tuple(str(item) for item in payload)


def _require_text(label: str, value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _required_text(value: object, label: str) -> str:
    return _require_text(label, value)


def _require_trace_name(label: str, value: str) -> None:
    _require_text(label, value)
    if not _TRACE_NAME_RE.fullmatch(value):
        raise ValueError(f"{label} must be uppercase snake case")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    normalized = tuple(item.strip() for item in values)
    if any(not item for item in normalized):
        raise ValueError(f"{label} must be non-empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique")
