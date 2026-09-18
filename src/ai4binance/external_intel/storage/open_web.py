"""Append-only Open Web evidence cache with bounded replay."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from ai4binance.external_intel.core.enums import (
    ExtractionMethod,
    RetrievalStatus,
    SourceType,
)
from ai4binance.external_intel.core.models import (
    ExternalEvidence,
    ExternalObservation,
    RetrievedDocument,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, read_bounded_jsonl_tail


@dataclass(frozen=True, slots=True)
class CachedWebRecord:
    observation: ExternalObservation
    document: RetrievedDocument
    evidence: ExternalEvidence


@dataclass(frozen=True, slots=True)
class OpenWebEvidenceStore:
    path: Path

    def append(self, record: CachedWebRecord) -> None:
        primitive = to_primitive(record)
        if not isinstance(primitive, Mapping):
            raise TypeError("open-web cache record must be a mapping")
        JsonlAuditStore(self.path).append_verified(
            AuditEvent(
                event_type="OPEN_WEB_DOCUMENT_RECORDED",
                timestamp=record.document.retrieved_at,
                snapshot_id=record.document.document_id,
                payload=cast(Mapping[str, object], primitive),
            )
        )

    def get(self, canonical_uri: str) -> CachedWebRecord | None:
        if not self.path.exists():
            return None
        for line in reversed(read_bounded_jsonl_tail(self.path, max_lines=5_000)):
            raw = json.loads(line)
            event = _mapping(raw, "cache event")
            if event.get("event_type") != "OPEN_WEB_DOCUMENT_RECORDED":
                continue
            payload = _mapping(event.get("payload"), "cache payload")
            document = _mapping(payload.get("document"), "cached document")
            if document.get("canonical_uri") != canonical_uri:
                continue
            return CachedWebRecord(
                _observation(_mapping(payload.get("observation"), "observation")),
                _document(document),
                _evidence(_mapping(payload.get("evidence"), "evidence")),
            )
        return None


def _observation(value: Mapping[str, object]) -> ExternalObservation:
    published = value.get("published_at")
    return ExternalObservation(
        observation_id=str(value["observation_id"]),
        provider_id=str(value["provider_id"]),
        source_type=SourceType(str(value["source_type"])),
        source_uri=str(value["source_uri"]),
        canonical_uri=str(value["canonical_uri"]),
        title=str(value["title"]),
        content_sha256=str(value["content_sha256"]),
        retrieved_at=_datetime(value["retrieved_at"]),
        published_at=_datetime(published) if published is not None else None,
        author_or_origin=str(value["author_or_origin"]),
        language=str(value["language"]),
        summary=str(value["summary"]),
        query_id=_optional_text(value.get("query_id")),
        query_text=_optional_text(value.get("query_text")),
        raw_reference=str(value["raw_reference"]),
        entities=_strings(value["entities"]),
        symbols=_strings(value["symbols"]),
        event_candidates=_strings(value["event_candidates"]),
        source_credibility=_float(value["source_credibility"]),
        retrieval_confidence=_float(value["retrieval_confidence"]),
        data_quality_status=RetrievalStatus(str(value["data_quality_status"])),
        extraction_method=ExtractionMethod(str(value["extraction_method"])),
    )


def _document(value: Mapping[str, object]) -> RetrievedDocument:
    published = value.get("published_at")
    return RetrievedDocument(
        document_id=str(value["document_id"]),
        observation_id=str(value["observation_id"]),
        canonical_uri=str(value["canonical_uri"]),
        content_sha256=str(value["content_sha256"]),
        title=str(value["title"]),
        retrieved_at=_datetime(value["retrieved_at"]),
        content_type=str(value["content_type"]),
        byte_count=_int(value["byte_count"]),
        text_excerpt=str(value["text_excerpt"]),
        author_or_origin=str(value["author_or_origin"]),
        published_at=_datetime(published) if published is not None else None,
        language=str(value["language"]),
        headings=_strings(value["headings"]),
        references=_strings(value["references"]),
        extraction_method=ExtractionMethod(str(value["extraction_method"])),
        full_text_persisted=bool(value["full_text_persisted"]),
    )


def _evidence(value: Mapping[str, object]) -> ExternalEvidence:
    return ExternalEvidence(
        evidence_id=str(value["evidence_id"]),
        source_type=SourceType(str(value["source_type"])),
        source_uri=str(value["source_uri"]),
        observed_at=_datetime(value["observed_at"]),
        content_sha256=str(value["content_sha256"]),
        citation=str(value["citation"]),
        author_or_origin=str(value["author_or_origin"]),
        reliability=_float(value["reliability"]),
        raw_excerpt=str(value["raw_excerpt"]),
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("cached string sequence must be a list")
    return tuple(str(item) for item in value)


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("cached timestamp must be timezone-aware")
    return parsed


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("cached numeric value is invalid")
    return float(value)


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("cached integer value is invalid")
    return value
