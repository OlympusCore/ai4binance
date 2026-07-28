"""Deterministic tests for the evidence-backed, draft-only content slice."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.content import (
    ComplianceStatus,
    ContentCompliancePolicy,
    ContentDraftEngine,
    DraftBlockedError,
    DraftQueueStatus,
    EvidenceBackedDraftQueue,
    LocalApprovalQueue,
)
from ai4binance.mcp import EvidenceEnvelope, EvidenceGateway, FreshnessStatus

NOW = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)


def outlook_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "snapshot_id": "market-1",
        "symbol": "HOTUSDT",
        "timestamp": NOW.isoformat(),
        "status": "PARTIAL",
        "market_regime": "TREND",
        "volatility_state": "NORMAL",
        "timeframe_biases": [
            {"timeframe": "1d", "direction": "BULLISH"},
            {"timeframe": "4h", "direction": "NEUTRAL"},
            {"timeframe": "1h", "direction": "BEARISH"},
        ],
        "setups_on_radar": [{"setup_name": "SUPPORT_RECLAIM", "setup_tier": "B"}],
        "no_trade_rationale": "OOS evidence is incomplete",
        "blockers": ["WEAK_OOS_EVIDENCE"],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    data.update(overrides)
    return data


def envelope(**overrides: object) -> EvidenceEnvelope:
    values: dict[str, object] = {
        "artifact_type": "market_outlook",
        "generated_at": NOW,
        "source_artifact": "market-outlook/state.json",
        "source_sha256": "a" * 64,
        "freshness_status": FreshnessStatus.FRESH,
        "blockers": ("WEAK_OOS_EVIDENCE",),
        "data": outlook_data(),
    }
    values.update(overrides)
    return EvidenceEnvelope(**values)  # type: ignore[arg-type]


def engine() -> ContentDraftEngine:
    return ContentDraftEngine(clock=lambda: NOW)


def test_engine_creates_deterministic_sourced_non_publishable_draft() -> None:
    first = engine().create_market_outlook_draft(envelope())
    second = engine().create_market_outlook_draft(envelope())

    assert first == second
    assert first.compliance_status is ComplianceStatus.PASSED
    assert first.queue_status is DraftQueueStatus.REVIEW_REQUIRED
    assert first.publish_allowed is False
    assert first.execution_allowed is False
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert len(first.content) <= 280
    assert "NO_TRADE" in first.content
    assert first.source.source_sha256 == "a" * 64
    assert {claim.source_field for claim in first.claims} == {
        "timeframe_biases",
        "market_regime",
        "volatility_state",
        "setups_on_radar",
        "no_trade_rationale",
    }


@pytest.mark.parametrize(
    ("report", "blocker"),
    [
        (
            envelope(
                freshness_status=FreshnessStatus.STALE,
                blockers=("EVIDENCE_STALE",),
            ),
            "CONTENT_SOURCE_NOT_FRESH",
        ),
        (envelope(artifact_type="quality_triage"), "CONTENT_SOURCE_TYPE_UNSUPPORTED"),
        (
            envelope(data={}),
            "CONTENT_SOURCE_DATA_MISSING",
        ),
    ],
)
def test_engine_blocks_untrusted_source(report: EvidenceEnvelope, blocker: str) -> None:
    with pytest.raises(DraftBlockedError) as raised:
        engine().create_market_outlook_draft(report)

    assert blocker in raised.value.blockers


@pytest.mark.parametrize(
    ("data", "blocker"),
    [
        (outlook_data(timestamp="invalid"), "CONTENT_SOURCE_TIMESTAMP_INVALID"),
        (outlook_data(symbol=""), "CONTENT_SOURCE_SYMBOL_INVALID"),
        (outlook_data(timeframe_biases=[]), "CONTENT_SOURCE_BIASES_INCOMPLETE"),
        (outlook_data(setups_on_radar="bad"), "CONTENT_SOURCE_RADAR_INVALID"),
        (
            outlook_data(no_trade_rationale="garanti kazanç"),
            "CONTENT_PROFIT_PROMISE_BLOCKED",
        ),
        (
            outlook_data(market_regime="https://unsafe.example"),
            "CONTENT_EXTERNAL_LINK_BLOCKED",
        ),
        (
            outlook_data(volatility_state="token=do-not-leak"),
            "CONTENT_SECRET_LIKE_TEXT_BLOCKED",
        ),
    ],
)
def test_engine_blocks_invalid_or_noncompliant_content(
    data: dict[str, object], blocker: str
) -> None:
    with pytest.raises(DraftBlockedError) as raised:
        engine().create_market_outlook_draft(envelope(data=data))

    assert raised.value.blockers == (blocker,)


def test_policy_reports_all_stable_blockers() -> None:
    result = ContentCompliancePolicy(max_characters=8).evaluate(
        "@bad https://bad token=secret garanti kazanç"
    )

    assert result.status is ComplianceStatus.BLOCKED
    assert result.blockers == (
        "CONTENT_LENGTH_EXCEEDED",
        "CONTENT_DISCLAIMER_MISSING",
        "CONTENT_PROFIT_PROMISE_BLOCKED",
        "CONTENT_EXTERNAL_LINK_BLOCKED",
        "CONTENT_MENTION_BLOCKED",
        "CONTENT_SECRET_LIKE_TEXT_BLOCKED",
    )


def test_queue_is_append_only_idempotent_and_requires_explicit_approval(
    tmp_path: Path,
) -> None:
    queue = LocalApprovalQueue(
        tmp_path / "content" / "approval.jsonl", clock=lambda: NOW
    )
    draft = engine().create_market_outlook_draft(envelope())

    assert queue.enqueue(draft) is True
    assert queue.enqueue(draft) is False
    assert queue.pending_ids() == (draft.draft_id,)
    with pytest.raises(ValueError, match="confirmation"):
        queue.approve(
            draft.draft_id,
            approved_by="operator",
            rationale="Reviewed",
            confirmation="yes",
        )

    queue.approve(
        draft.draft_id,
        approved_by="operator",
        rationale="Evidence reviewed locally",
        confirmation="APPROVE_LOCAL_DRAFT",
    )

    assert queue.status(draft.draft_id) is DraftQueueStatus.APPROVED
    assert queue.pending_ids() == ()
    assert len(queue.path.read_text(encoding="utf-8").splitlines()) == 2
    with pytest.raises(ValueError, match="no longer pending"):
        queue.reject(draft.draft_id, rejected_by="operator", rationale="late")


def test_queue_supports_reject_and_expire_without_publish_authority(
    tmp_path: Path,
) -> None:
    rejected = engine().create_market_outlook_draft(envelope())
    expired = replace(rejected, draft_id="b" * 64)
    queue = LocalApprovalQueue(tmp_path / "approval.jsonl", clock=lambda: NOW)
    queue.enqueue(rejected)
    queue.enqueue(expired)

    queue.reject(rejected.draft_id, rejected_by="reviewer", rationale="Not timely")
    queue.expire(expired.draft_id, rationale="Evidence freshness window elapsed")

    assert queue.status(rejected.draft_id) is DraftQueueStatus.REJECTED
    assert queue.status(expired.draft_id) is DraftQueueStatus.EXPIRED
    for line in queue.path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        assert event["payload"]["publish_allowed"] is False
        assert event["payload"]["execution_allowed"] is False


def test_queue_fails_closed_on_tampering_and_secret_like_review_text(
    tmp_path: Path,
) -> None:
    draft = engine().create_market_outlook_draft(envelope())
    path = tmp_path / "approval.jsonl"
    queue = LocalApprovalQueue(path, clock=lambda: NOW)
    queue.enqueue(draft)

    with pytest.raises(ValueError, match="secret-like"):
        queue.reject(
            draft.draft_id,
            rejected_by="operator",
            rationale="api_key=must-not-be-stored",
        )

    event = json.loads(path.read_text(encoding="utf-8"))
    event["payload"]["draft"]["publish_allowed"] = True
    path.write_text(json.dumps(event), encoding="utf-8")

    with pytest.raises(ValueError, match="malformed"):
        queue.status(draft.draft_id)


def test_queue_rejects_malformed_oversized_and_unknown_drafts(tmp_path: Path) -> None:
    path = tmp_path / "approval.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    queue = LocalApprovalQueue(path, clock=lambda: NOW)
    with pytest.raises(ValueError, match="line 1"):
        queue.pending_ids()

    path.write_text("x" * 101, encoding="utf-8")
    bounded = LocalApprovalQueue(path, clock=lambda: NOW, max_queue_bytes=100)
    with pytest.raises(ValueError, match="bounded size"):
        bounded.pending_ids()

    path.unlink()
    with pytest.raises(KeyError, match="not found"):
        queue.expire("c" * 64, rationale="No source")


def test_workflow_connects_evidence_gateway_to_local_queue_without_publish(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifacts" / "market-outlook" / "state.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps(outlook_data()), encoding="utf-8")
    gateway = EvidenceGateway(tmp_path / "artifacts", clock=lambda: NOW)
    queue = LocalApprovalQueue(tmp_path / "approval.jsonl", clock=lambda: NOW)
    workflow = EvidenceBackedDraftQueue(gateway, engine(), queue)

    first = workflow.ingest_market_outlook()
    duplicate = workflow.ingest_market_outlook()

    assert first.enqueued is True
    assert duplicate.enqueued is False
    assert first.publish_attempted is False
    assert first.draft == duplicate.draft
    assert queue.status(first.draft.draft_id) is DraftQueueStatus.REVIEW_REQUIRED


def test_workflow_fails_before_queue_write_when_evidence_is_missing(
    tmp_path: Path,
) -> None:
    queue = LocalApprovalQueue(tmp_path / "approval.jsonl", clock=lambda: NOW)
    workflow = EvidenceBackedDraftQueue(
        EvidenceGateway(tmp_path / "artifacts", clock=lambda: NOW),
        engine(),
        queue,
    )

    with pytest.raises(DraftBlockedError) as raised:
        workflow.ingest_market_outlook()

    assert "CONTENT_SOURCE_NOT_FRESH" in raised.value.blockers
    assert "CONTENT_SOURCE_DATA_MISSING" in raised.value.blockers
    assert queue.path.exists() is False
