"""Local journals reject corrupted fields and inconsistent revision history."""

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from ai4binance.external_intel.core.enums import RetrievalStatus, SourceType
from ai4binance.external_intel.core.models import ExternalEvidence, ExternalObservation
from ai4binance.external_intel.storage.open_web import (
    CachedWebRecord,
    OpenWebEvidenceStore,
)
from ai4binance.infrastructure.persistence.memory import (
    JsonlMemoryConflictStore,
    JsonlMemoryStore,
)
from ai4binance.reporting import to_primitive
from tests.test_memory_projection import _active_memory
from tests.test_open_web_intelligence import NOW, _document


@pytest.fixture
def web_record() -> CachedWebRecord:
    document = _document()
    observation = ExternalObservation(
        observation_id="obs-1",
        provider_id="source",
        source_type=SourceType.WEB_ARTICLE,
        source_uri=document.canonical_uri,
        canonical_uri=document.canonical_uri,
        title=document.title,
        content_sha256=document.content_sha256,
        retrieved_at=NOW,
        author_or_origin="GitHub",
        language="en",
        summary="summary",
        raw_reference=document.canonical_uri,
        source_credibility=0.8,
        retrieval_confidence=0.9,
        data_quality_status=RetrievalStatus.VALID,
    )
    evidence = ExternalEvidence(
        "evidence-1",
        SourceType.WEB_ARTICLE,
        document.canonical_uri,
        NOW,
        document.content_sha256,
        document.canonical_uri,
        "GitHub",
        0.8,
        "Agent security evidence",
    )
    return CachedWebRecord(observation, document, evidence)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("observation", "entities", "BTC", "must be a list"),
        ("observation", "retrieved_at", "2026-01-01T00:00:00", "timezone-aware"),
        ("observation", "source_credibility", True, "numeric"),
        ("observation", "source_credibility", "0.8", "numeric"),
        ("document", "byte_count", True, "integer"),
        ("document", "byte_count", 1.5, "integer"),
    ],
)
def test_web_cache_rejects_malformed_persisted_fields(
    tmp_path: Path,
    web_record: CachedWebRecord,
    section: str,
    field: str,
    value: object,
    message: str,
) -> None:
    store = OpenWebEvidenceStore(tmp_path / "cache.jsonl")
    store.append(web_record)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["payload"][section][field] = value
    store.path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        store.get(web_record.document.canonical_uri)


def test_web_cache_skips_other_events_and_rejects_non_objects(
    tmp_path: Path, web_record: CachedWebRecord
) -> None:
    store = OpenWebEvidenceStore(tmp_path / "cache.jsonl")
    store.path.write_text('{"event_type":"OTHER"}\n', encoding="utf-8")
    assert store.get(web_record.document.canonical_uri) is None
    store.path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        store.get(web_record.document.canonical_uri)


def test_web_cache_restores_optional_publication_and_query_metadata(
    tmp_path: Path, web_record: CachedWebRecord
) -> None:
    record = replace(
        web_record,
        observation=replace(
            web_record.observation,
            published_at=NOW,
            query_id="query-1",
            query_text="bounded research",
        ),
        document=replace(web_record.document, published_at=NOW),
    )
    store = OpenWebEvidenceStore(tmp_path / "cache.jsonl")
    store.append(record)
    assert store.get(record.document.canonical_uri) == record


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("memory_id", 123, "must be text"),
        ("symbol", 123, "must be text"),
        ("source_refs", "source", "text list"),
        ("source_refs", [123], "text list"),
        ("confidence", "0.5", "numeric"),
    ],
)
def test_memory_journal_rejects_malformed_persisted_fields(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    record = _active_memory("memory-1", "Verified local evidence")
    payload = cast(dict[str, object], to_primitive(record))
    payload[field] = value
    path = tmp_path / "memory.jsonl"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        JsonlMemoryStore(path).load_recent()


@pytest.mark.parametrize("raw", ["[]\n", "null\n"])
def test_memory_journal_rejects_non_object_records_on_read_and_append(
    tmp_path: Path, raw: str
) -> None:
    path = tmp_path / "memory.jsonl"
    path.write_text(raw, encoding="utf-8")
    store = JsonlMemoryStore(path)
    with pytest.raises(ValueError, match="must be an object"):
        store.load_recent()
    with pytest.raises(ValueError, match="must be an object"):
        store.append(_active_memory("memory-1", "Verified local evidence"))
    assert path.read_text(encoding="utf-8") == raw


def test_memory_journal_refuses_conflicting_identity_and_nonadvancing_revision(
    tmp_path: Path,
) -> None:
    record = _active_memory("memory-1", "Verified local evidence")
    store = JsonlMemoryStore(tmp_path / "memory.jsonl")
    store.append(record)
    original = store.path.read_bytes()
    for conflicting, message in (
        (_active_memory("memory-1", "Conflicting content"), "conflicting content"),
        (replace(record, blockers=("NEW_BLOCKER",)), "advance recorded time"),
        (
            replace(
                record,
                recorded_at=record.effective_recorded_at + timedelta(seconds=1),
                confidence=0.2,
            ),
            "immutable evidence",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            store.append(conflicting)
        assert store.path.read_bytes() == original
    assert store.load_recent(as_of_system_time=record.event_time) == ()


def test_memory_journal_rejects_duplicate_lineage_and_bounded_record_overflow(
    tmp_path: Path,
) -> None:
    record = _active_memory("memory-1", "Verified local evidence")
    store = JsonlMemoryStore(tmp_path / "memory.jsonl")
    store.append(record)
    line = store.path.read_text(encoding="utf-8")
    store.path.write_text(line + line, encoding="utf-8")
    with pytest.raises(ValueError, match="lineage"):
        store.load_recent()
    with pytest.raises(ValueError, match="lineage"):
        store.append(record)
    with pytest.raises(ValueError, match="bounded read limit"):
        replace(store, max_bytes=100).append(record)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("[]\n", "must be an object"),
        ('{"conflict": []}\n', "conflict must be an object"),
    ],
)
def test_conflict_journal_rejects_invalid_outer_and_nested_records(
    tmp_path: Path, raw: str, message: str
) -> None:
    store = JsonlMemoryConflictStore(tmp_path / "conflicts.jsonl")
    assert store.load_recent() == ()
    store.path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        store.load_recent()
