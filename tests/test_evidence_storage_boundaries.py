"""Reject malformed local evidence without granting downstream authority."""

import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.content.queue import LocalApprovalQueue
from ai4binance.local_agent import advisory_evidence
from ai4binance.local_agent.advisory_evidence import LocalAdvisoryFixtureEvidenceStore
from ai4binance.multiops.llmops import usage
from ai4binance.multiops.llmops.usage import ModelUsageLedger
from ai4binance.whale_fusion.social import (
    SocialClassification,
    SocialContradiction,
    SocialIntelligenceEngine,
)
from tests.test_content_draft_queue import NOW, engine, envelope
from tests.test_model_usage_ledger import exact_record
from tests.test_whale_fusion_social import account, post, registry


@pytest.mark.parametrize(
    ("evidence", "audit"),
    [
        ("relative.json", "audit.jsonl"),
        ("wrong.txt", "audit.jsonl"),
        ("evidence.json", "wrong.txt"),
    ],
)
def test_advisory_store_rejects_invalid_destinations(
    tmp_path: Path, evidence: str, audit: str
) -> None:
    destination = (
        Path(evidence) if evidence.startswith("relative") else tmp_path / evidence
    )
    with pytest.raises(ValueError, match="paths are invalid"):
        LocalAdvisoryFixtureEvidenceStore(destination, tmp_path / audit)


def test_advisory_store_rejects_naive_time_before_writing(tmp_path: Path) -> None:
    store = LocalAdvisoryFixtureEvidenceStore(
        tmp_path / "result.json", tmp_path / "audit.jsonl"
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        store.save(cast(Any, None), recorded_at=datetime(2026, 9, 1))
    assert not store.evidence_path.exists()


def test_advisory_store_rejects_invalid_serialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalAdvisoryFixtureEvidenceStore(
        tmp_path / "result.json", tmp_path / "audit.jsonl"
    )
    monkeypatch.setattr(advisory_evidence, "_payload", lambda *args, **kwargs: {})
    monkeypatch.setattr(advisory_evidence, "to_primitive", lambda value: [])
    with pytest.raises(TypeError, match="payload is invalid"):
        store.save(cast(Any, None), recorded_at=NOW)
    assert not store.audit_path.exists()


@pytest.mark.parametrize(
    "event",
    [
        [],
        {"event_type": "WRONG"},
        {"event_type": "MODEL_USAGE_RECORDED", "payload": []},
    ],
)
def test_usage_ledger_rejects_corrupt_events(tmp_path: Path, event: object) -> None:
    ledger = ModelUsageLedger.at_repository(tmp_path)
    assert ledger.read_recent() == ()
    ledger.path.parent.mkdir(parents=True)
    ledger.path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="model usage ledger"):
        ledger.read_recent()


def test_usage_ledger_rejects_serializer_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(usage, "to_primitive", lambda value: [])
    with pytest.raises(TypeError, match="must be a mapping"):
        ModelUsageLedger(tmp_path / "usage.jsonl").append(exact_record())
    assert not (tmp_path / "usage.jsonl").exists()


@pytest.mark.parametrize(
    ("kind", "changes", "message"),
    [
        ("account", {"confidence": Decimal("1.1")}, "confidence"),
        ("account", {"account_id": ""}, "requires"),
        ("event", {"provenance": ()}, "requires"),
        ("classification", {"post_id": ""}, "inconsistent"),
        ("contradiction", {"asset": ""}, "requires"),
        ("post", {"timestamp": datetime(2026, 9, 1)}, "timezone-aware"),
        ("post", {"source_confidence": Decimal("-1")}, "confidence"),
        ("post", {"post_id": ""}, "identity"),
        ("event", {"confidence": Decimal("1.1")}, "confidence"),
        ("event", {"execution_allowed": True}, "authority"),
        ("event", {"promotion_status": "LIVE"}, "authority"),
        ("classification", {"execution_allowed": True}, "authority"),
        ("classification", {"promotion_status": "LIVE"}, "authority"),
        ("contradiction", {"detected_at": datetime(2026, 9, 1)}, "timezone-aware"),
        ("contradiction", {"execution_allowed": True}, "authority"),
        ("contradiction", {"promotion_status": "LIVE"}, "authority"),
    ],
)
def test_social_contracts_reject_untrusted_authority(
    kind: str, changes: dict[str, Any], message: str
) -> None:
    event = (
        SocialIntelligenceEngine(registry())
        .evaluate(post(), as_of=NOW.replace(hour=13))
        .events[0]
    )
    subjects = {
        "account": account(),
        "post": post(),
        "event": event,
        "classification": SocialClassification("post", (), ("BLOCKED",)),
        "contradiction": SocialContradiction("conflict", "BTC", "one", "two", NOW),
    }
    with pytest.raises(ValueError, match=message):
        replace(cast(Any, subjects[kind]), **changes)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timestamp", None),
        ("timestamp", "bad"),
        ("timestamp", "2026-09-01T00:00:00"),
        ("event_type", "UNKNOWN"),
        ("payload", []),
        ("snapshot_id", 3),
    ],
)
def test_queue_replay_rejects_malformed_envelopes(
    tmp_path: Path, field: str, value: object
) -> None:
    queue = LocalApprovalQueue(tmp_path / "queue.jsonl", clock=lambda: NOW)
    draft = engine().create_market_outlook_draft(envelope())
    queue.enqueue(draft)
    event = json.loads(queue.path.read_text())
    event[field] = value
    queue.path.write_text(json.dumps(event), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        queue.pending_ids()


@pytest.mark.parametrize(("text", "message"), [("[]", "invalid"), ("{", "invalid")])
def test_queue_replay_rejects_invalid_json(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "queue.jsonl"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        LocalApprovalQueue(path).pending_ids()


def test_queue_bounds_and_rejected_transitions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        LocalApprovalQueue(tmp_path / "bad", max_queue_bytes=0)
    draft = engine().create_market_outlook_draft(envelope())
    queue = LocalApprovalQueue(tmp_path / "queue.jsonl", clock=lambda: NOW)
    assert not queue.approved_draft_matches(draft)
    with pytest.raises(KeyError, match="not found"):
        queue.reject(draft.draft_id, rejected_by="reviewer", rationale="No evidence")
    queue.enqueue(draft)
    assert not queue.approved_draft_matches(draft)
    queue.approve(
        draft.draft_id,
        approved_by="reviewer",
        rationale="Evidence reviewed",
        confirmation="APPROVE_LOCAL_DRAFT",
    )
    assert queue.approved_draft_matches(draft)
    with pytest.raises(ValueError, match="bounded size"):
        LocalApprovalQueue(queue.path, max_queue_bytes=1).pending_ids()
    for actor in ("", "a" * 81, "password=placeholder"):
        with pytest.raises(ValueError, match="actor"):
            queue.reject(
                draft.draft_id, rejected_by=actor, rationale="Invalid evidence"
            )
    with pytest.raises(ValueError, match="id is invalid"):
        queue.reject("invalid", rejected_by="reviewer", rationale="Invalid evidence")
    with pytest.raises(ValueError, match="timezone-aware"):
        LocalApprovalQueue(
            tmp_path / "naive.jsonl", clock=lambda: datetime(2026, 9, 1)
        ).enqueue(draft)


@pytest.mark.parametrize(
    "mode", ["duplicate", "malformed_draft", "transition", "authority"]
)
def test_queue_replay_rejects_tampered_history(tmp_path: Path, mode: str) -> None:
    queue = LocalApprovalQueue(tmp_path / "queue.jsonl", clock=lambda: NOW)
    draft = engine().create_market_outlook_draft(envelope())
    queue.enqueue(draft)
    original = queue.path.read_text()
    event = json.loads(original)
    if mode == "duplicate":
        text = original + original
    else:
        if mode == "malformed_draft":
            event["payload"]["draft"] = {}
        elif mode == "transition":
            event["event_type"] = "CONTENT_DRAFT_APPROVED"
        else:
            event["payload"]["publish_allowed"] = True
        text = json.dumps(event)
    queue.path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=r"duplicate|malformed|transition|authority"):
        queue.pending_ids()
