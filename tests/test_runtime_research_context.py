"""Runtime context ingestion tests for social/news/content support."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from ai4binance.runtime_research_context import (
    RuntimeContextAcquirer,
    RuntimeResearchContextLoader,
    SnapshotAcquirer,
    _TrackedEvidenceObservation,
    _TrackerEntry,
    _TrackingEvidenceStatus,
)
from ai4binance.schemas import MarketSnapshot
from tests.test_cli import public_snapshot


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def _as_tuple(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _as_text_tuple(value: object) -> tuple[str, ...]:
    values = _as_tuple(value)
    return tuple(item for item in values if isinstance(item, str))


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise AssertionError("expected numeric value")
    return float(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError("expected integer value")
    return value


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AssertionError("expected mapping value")
    return cast(Mapping[str, object], value)


def test_runtime_context_loader_attaches_news_and_sentiment(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    news_path = tmp_path / "news-events.jsonl"
    social_path = tmp_path / "social-events.jsonl"
    content_path = tmp_path / "content-events.jsonl"
    _write_jsonl(
        news_path,
        [
            {
                "event_id": "news-1",
                "symbol": "HOTUSDT",
                "title": "Listing approval and launch schedule",
                "impact": "HIGH",
                "scheduled_at": (now + timedelta(hours=2)).isoformat(),
                "retrieved_at": now.isoformat(),
                "source": "news-feed",
                "source_url": "https://news.example/item-1",
            }
        ],
    )
    _write_jsonl(
        social_path,
        [
            {
                "symbol": "HOTUSDT",
                "source": "x",
                "source_url": "https://x.com/example/status/1",
                "as_of": (now - timedelta(minutes=20)).isoformat(),
                "directional_vote": 0.5,
                "score": 62.0,
            }
        ],
    )
    _write_jsonl(
        content_path,
        [
            {
                "symbol": "HOTUSDT",
                "source": "content-brief",
                "source_url": "https://blog.example/research-1",
                "as_of": (now - timedelta(minutes=10)).isoformat(),
                "directional_vote": -0.1,
                "score": 58.0,
                "weight": 2,
            }
        ],
    )

    loader = RuntimeResearchContextLoader(
        news_feed_path=news_path,
        social_feed_path=social_path,
        content_feed_path=content_path,
    )
    enriched = loader.attach(snapshot)

    assert len(_as_tuple(enriched.news_snapshot["high_impact_events"])) == 1
    assert enriched.news_snapshot["source_count"] == 1
    assert "as_of" in enriched.news_snapshot
    assert enriched.sentiment_snapshot["source_count"] == 2
    assert (
        enriched.sentiment_snapshot["as_of"]
        == (now - timedelta(minutes=10)).isoformat()
    )
    assert _as_float(enriched.sentiment_snapshot["directional_vote"]) == 0.1
    assert _as_float(enriched.sentiment_snapshot["score"]) == 59.333333


def test_runtime_context_loader_ignores_invalid_and_stale_rows(tmp_path: Path) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    news_path = tmp_path / "news-events.jsonl"
    social_path = tmp_path / "social-events.jsonl"
    content_path = tmp_path / "content-events.jsonl"
    _write_jsonl(
        news_path,
        [
            {
                "event_id": "news-old",
                "symbol": "HOTUSDT",
                "title": "Old unsupported bulletin",
                "impact": "HIGH",
                "scheduled_at": (now + timedelta(hours=1)).isoformat(),
                "retrieved_at": (now - timedelta(days=2)).isoformat(),
                "source": "news-feed",
                "source_url": "https://news.example/stale",
            },
            {
                "event_id": "news-bad",
                "symbol": "HOTUSDT",
                "title": "Invalid url",
                "impact": "HIGH",
                "scheduled_at": now.isoformat(),
                "retrieved_at": now.isoformat(),
                "source": "news-feed",
                "source_url": "http://insecure.example/bad",
            },
        ],
    )
    _write_jsonl(
        social_path,
        [
            {
                "symbol": "HOTUSDT",
                "source": "x",
                "source_url": "https://x.com/example/status/2",
                "as_of": (now + timedelta(minutes=10)).isoformat(),
                "directional_vote": 0.2,
                "score": 60,
            }
        ],
    )
    _write_jsonl(
        content_path,
        [
            {
                "symbol": "HOTUSDT",
                "source": "content",
                "as_of": now.isoformat(),
                "directional_vote": 3.5,
                "score": 30,
            }
        ],
    )

    loader = RuntimeResearchContextLoader(
        news_feed_path=news_path,
        social_feed_path=social_path,
        content_feed_path=content_path,
    )
    enriched = loader.attach(snapshot)

    assert enriched.news_snapshot["high_impact_events"] == ()
    news_blockers = _as_text_tuple(enriched.news_snapshot["provider_blockers"])
    assert "LOCAL_NEWS_EVENT_INVALID" in news_blockers
    assert "source_count" not in enriched.news_snapshot
    assert "source_count" not in enriched.sentiment_snapshot
    sentiment_blockers = _as_text_tuple(
        enriched.sentiment_snapshot["provider_blockers"]
    )
    assert "LOCAL_SOCIAL_EVENT_INVALID" in sentiment_blockers
    assert "LOCAL_CONTENT_EVENT_INVALID" in sentiment_blockers


@dataclass(frozen=True, slots=True)
class _StubAcquirer:
    snapshot: MarketSnapshot

    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        assert symbol == "HOTUSDT"
        assert timeframes == ("1h",)
        return self.snapshot


def test_runtime_context_acquirer_wraps_base_snapshot(tmp_path: Path) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    social_path = tmp_path / "social-events.jsonl"
    _write_jsonl(
        social_path,
        [
            {
                "symbol": "HOTUSDT",
                "source": "x",
                "source_url": "https://x.com/example/status/3",
                "as_of": (now - timedelta(minutes=5)).isoformat(),
                "directional_vote": 0.25,
                "score": 55.0,
            }
        ],
    )
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=social_path,
        content_feed_path=tmp_path / "content-events.jsonl",
    )
    acquirer = RuntimeContextAcquirer(_StubAcquirer(snapshot), loader)

    enriched = acquirer.acquire("HOTUSDT", ("1h",))

    assert enriched.snapshot_id == snapshot.snapshot_id
    assert cast(int, enriched.sentiment_snapshot["source_count"]) == 1
    assert _as_float(enriched.sentiment_snapshot["directional_vote"]) == 0.25


def test_runtime_context_loader_tracks_progress_without_duplicates(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    social_path = tmp_path / "social-events.jsonl"
    ledger_path = tmp_path / "evidence-ledger.json"
    report_path = tmp_path / "opportunities-latest.json"
    _write_jsonl(
        social_path,
        [
            {
                "event_id": "social-1",
                "symbol": "HOTUSDT",
                "source": "x",
                "source_url": "https://x.com/example/status/4",
                "as_of": (now - timedelta(minutes=5)).isoformat(),
                "directional_vote": 0.3,
                "score": 60.0,
            }
        ],
    )
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=social_path,
        content_feed_path=tmp_path / "content-events.jsonl",
        context_ledger_path=ledger_path,
        opportunity_report_path=report_path,
    )

    first = loader.attach(snapshot)
    first_tracking = _as_mapping(first.sentiment_snapshot["research_tracking"])
    first_feeds = _as_mapping(first_tracking["feeds"])
    first_social = _as_mapping(first_feeds["social"])
    assert _as_int(first_social["new_count"]) == 1
    assert _as_int(first_social["tracked_total"]) == 1

    second = loader.attach(
        replace(
            snapshot,
            snapshot_id=f"{snapshot.snapshot_id}-2",
            created_at=now + timedelta(minutes=1),
        )
    )
    second_tracking = _as_mapping(second.sentiment_snapshot["research_tracking"])
    second_feeds = _as_mapping(second_tracking["feeds"])
    second_social = _as_mapping(second_feeds["social"])
    assert _as_int(second_social["new_count"]) == 0
    assert _as_int(second_social["updated_count"]) == 0
    assert _as_int(second_social["unchanged_count"]) == 1
    assert _as_int(second_social["tracked_total"]) == 1

    _write_jsonl(
        social_path,
        [
            {
                "event_id": "social-1",
                "symbol": "HOTUSDT",
                "source": "x",
                "source_url": "https://x.com/example/status/4",
                "as_of": (now - timedelta(minutes=4)).isoformat(),
                "directional_vote": 0.45,
                "score": 70.0,
            }
        ],
    )
    third = loader.attach(
        replace(
            snapshot,
            snapshot_id=f"{snapshot.snapshot_id}-3",
            created_at=now + timedelta(minutes=2),
        )
    )
    third_tracking = _as_mapping(third.sentiment_snapshot["research_tracking"])
    third_feeds = _as_mapping(third_tracking["feeds"])
    third_social = _as_mapping(third_feeds["social"])
    assert _as_int(third_social["updated_count"]) == 1
    assert _as_int(third_social["tracked_total"]) == 1

    ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    feeds_payload = _as_mapping(_as_mapping(ledger_payload)["feeds"])
    social_entries = _as_mapping(feeds_payload["social"])
    tracked_entry = _as_mapping(social_entries["social-1"])
    assert _as_int(tracked_entry["seen_count"]) == 3
    assert _as_int(tracked_entry["change_count"]) == 1


def test_runtime_context_loader_isolates_technology_and_reports_opportunities(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    technology_path = tmp_path / "technology-events.jsonl"
    report_path = tmp_path / "opportunities-latest.json"
    _write_jsonl(
        technology_path,
        [
            {
                "development_id": "tech-1",
                "symbol": "HOTUSDT",
                "title": "Low-latency inference upgrade launch",
                "impact": "HIGH",
                "as_of": (now - timedelta(minutes=3)).isoformat(),
                "retrieved_at": now.isoformat(),
                "source": "tech-feed",
                "source_url": "https://tech.example/update-1",
                "directional_vote": 0.45,
                "score": 76,
                "opportunity_hint": "Review setup quality thresholds",
            }
        ],
    )

    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
        technology_feed_path=technology_path,
        context_ledger_path=tmp_path / "evidence-ledger.json",
        opportunity_report_path=report_path,
    )
    enriched = loader.attach(snapshot)

    technology_developments = _as_tuple(
        enriched.news_snapshot["technology_developments"]
    )
    assert len(technology_developments) == 1
    technology_item = _as_mapping(technology_developments[0])
    assert technology_item["development_id"] == "tech-1"
    assert technology_item["tracking_status"] == "NEW"

    high_impact_events = _as_tuple(enriched.news_snapshot.get("high_impact_events"))
    event_ids = {
        str(_as_mapping(item).get("event_id", "")) for item in high_impact_events
    }
    assert "tech:tech-1" not in event_ids
    assert "source_count" not in enriched.sentiment_snapshot
    assert "directional_vote" not in enriched.sentiment_snapshot
    assert "score" not in enriched.sentiment_snapshot
    assert "sources" not in enriched.sentiment_snapshot

    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_mapping = _as_mapping(report_payload)
    assert report_mapping["status"] == "ACTIVE"
    assert _as_int(report_mapping["opportunity_count"]) >= 1
    first_opportunity = _as_mapping(_as_tuple(report_mapping["opportunities"])[0])
    assert first_opportunity["category"] == "TECHNOLOGY_DEVELOPMENT"
    assert first_opportunity["ykb_attention_required"] is True
    assert first_opportunity["ykb_question_ne_oldu"] == (
        "Low-latency inference upgrade launch"
    )
    assert first_opportunity["ykb_question_kim_soyledi"] == "tech-feed"
    assert first_opportunity["ykb_question_nereden_dogrulanir"] == (
        "https://tech.example/update-1"
    )
    assert first_opportunity["ykb_question_ai4binance_etkisi"] == "HIGH"
    assert first_opportunity["ykb_opportunity_hint"] == (
        "Review setup quality thresholds"
    )
    assert first_opportunity["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert first_opportunity["primary_source_url"] == "https://tech.example/update-1"
    assert _as_text_tuple(first_opportunity["trace_urls"]) == (
        "https://tech.example/update-1",
    )
    trace_evidence = _as_tuple(first_opportunity["trace_evidence"])
    assert len(trace_evidence) == 1
    assert (
        _as_mapping(trace_evidence[0])["source_url"] == "https://tech.example/update-1"
    )


def test_runtime_context_loader_requires_source_url_for_social_and_content(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    _write_jsonl(
        tmp_path / "social-events.jsonl",
        [
            {
                "event_id": "social-missing-url",
                "symbol": "HOTUSDT",
                "source": "x",
                "as_of": (now - timedelta(minutes=8)).isoformat(),
                "directional_vote": 0.4,
                "score": 62.0,
            }
        ],
    )
    _write_jsonl(
        tmp_path / "content-events.jsonl",
        [
            {
                "event_id": "content-insecure-url",
                "symbol": "HOTUSDT",
                "source": "research-note",
                "source_url": "http://content.example/unsafe",
                "as_of": (now - timedelta(minutes=6)).isoformat(),
                "directional_vote": 0.3,
                "score": 61.0,
            }
        ],
    )

    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
    )
    enriched = loader.attach(snapshot)

    assert "source_count" not in enriched.sentiment_snapshot
    blockers = _as_text_tuple(enriched.sentiment_snapshot["provider_blockers"])
    assert "LOCAL_SOCIAL_EVENT_INVALID" in blockers
    assert "LOCAL_CONTENT_EVENT_INVALID" in blockers


def test_runtime_context_loader_reports_critical_news_with_url_trace(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    news_path = tmp_path / "news-events.jsonl"
    report_path = tmp_path / "opportunities-latest.json"
    _write_jsonl(
        news_path,
        [
            {
                "event_id": "news-critical-1",
                "symbol": "HOTUSDT",
                "title": "Active exploit alert on wallet provider",
                "impact": "CRITICAL",
                "scheduled_at": (now - timedelta(minutes=2)).isoformat(),
                "retrieved_at": now.isoformat(),
                "source": "news-feed",
                "source_url": "https://news.example/critical-1",
            }
        ],
    )

    loader = RuntimeResearchContextLoader(
        news_feed_path=news_path,
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
        context_ledger_path=tmp_path / "evidence-ledger.json",
        opportunity_report_path=report_path,
    )
    loader.attach(snapshot)

    report_payload = _as_mapping(json.loads(report_path.read_text(encoding="utf-8")))
    opportunities = tuple(
        _as_mapping(item) for item in _as_tuple(report_payload["opportunities"])
    )
    risk_opportunity = next(
        item for item in opportunities if item["category"] == "RISK_HARDENING_REVIEW"
    )
    assert risk_opportunity["ykb_attention_required"] is True
    assert risk_opportunity["ykb_attention_reason"] == "CRITICAL_NEWS_OR_RISK_SHIFT"
    assert risk_opportunity["primary_source_url"] == "https://news.example/critical-1"
    assert _as_text_tuple(risk_opportunity["trace_urls"]) == (
        "https://news.example/critical-1",
    )


def test_runtime_context_loader_reports_sentiment_shift_with_url_trace(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    _write_jsonl(
        tmp_path / "social-events.jsonl",
        [
            {
                "event_id": "social-shift-1",
                "symbol": "HOTUSDT",
                "source": "x",
                "source_url": "https://x.com/example/status/9",
                "as_of": (now - timedelta(minutes=15)).isoformat(),
                "directional_vote": 0.55,
                "score": 68.0,
            }
        ],
    )
    _write_jsonl(
        tmp_path / "content-events.jsonl",
        [
            {
                "event_id": "content-shift-1",
                "symbol": "HOTUSDT",
                "source": "research-desk",
                "source_url": "https://content.example/report-9",
                "as_of": (now - timedelta(minutes=12)).isoformat(),
                "directional_vote": 0.35,
                "score": 72.0,
                "weight": 1.4,
            }
        ],
    )
    report_path = tmp_path / "opportunities-latest.json"

    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
        context_ledger_path=tmp_path / "evidence-ledger.json",
        opportunity_report_path=report_path,
    )
    loader.attach(snapshot)

    report_payload = _as_mapping(json.loads(report_path.read_text(encoding="utf-8")))
    opportunities = tuple(
        _as_mapping(item) for item in _as_tuple(report_payload["opportunities"])
    )
    sentiment_opportunity = next(
        item
        for item in opportunities
        if item["opportunity_id"] == "sentiment-shift-setup-review"
    )
    assert sentiment_opportunity["ykb_attention_required"] is True
    assert sentiment_opportunity["ykb_attention_reason"] == "SENTIMENT_SHIFT"
    trace_urls = set(_as_text_tuple(sentiment_opportunity["trace_urls"]))
    assert trace_urls == {
        "https://x.com/example/status/9",
        "https://content.example/report-9",
    }
    assert _as_int(sentiment_opportunity["trace_url_count"]) == 2
    trace_evidence = tuple(
        _as_mapping(item) for item in _as_tuple(sentiment_opportunity["trace_evidence"])
    )
    trace_ids = {str(item["evidence_id"]) for item in trace_evidence}
    assert trace_ids == {"social-shift-1", "content-shift-1"}


def test_runtime_context_loader_rejects_unbounded_configuration() -> None:
    with pytest.raises(ValueError, match="file limit"):
        RuntimeResearchContextLoader(
            news_feed_path=Path("news.jsonl"),
            social_feed_path=Path("social.jsonl"),
            content_feed_path=Path("content.jsonl"),
            max_file_bytes=128,
        )
    with pytest.raises(ValueError, match="maximum age"):
        RuntimeResearchContextLoader(
            news_feed_path=Path("news.jsonl"),
            social_feed_path=Path("social.jsonl"),
            content_feed_path=Path("content.jsonl"),
            max_event_age=timedelta(0),
        )
    with pytest.raises(ValueError, match="tracking capacity"):
        RuntimeResearchContextLoader(
            news_feed_path=Path("news.jsonl"),
            social_feed_path=Path("social.jsonl"),
            content_feed_path=Path("content.jsonl"),
            max_tracking_entries=99,
        )


def test_runtime_context_loader_jsonl_guards_invalid_and_oversized_inputs(
    tmp_path: Path,
) -> None:
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
    )

    invalid_json = tmp_path / "invalid-json.jsonl"
    invalid_json.write_text("{not-json\n", encoding="utf-8")
    rows, blockers = loader._read_jsonl(invalid_json, "LOCAL_TEST_FEED")
    assert rows == ()
    assert blockers == ("LOCAL_TEST_FEED_INVALID",)

    invalid_row = tmp_path / "invalid-row.jsonl"
    invalid_row.write_text("[1, 2, 3]\n", encoding="utf-8")
    rows, blockers = loader._read_jsonl(invalid_row, "LOCAL_TEST_FEED")
    assert rows == ()
    assert blockers == ("LOCAL_TEST_FEED_INVALID",)

    oversized = tmp_path / "oversized.jsonl"
    oversized.write_text("x" * 2048, encoding="utf-8")
    small_loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
        max_file_bytes=1024,
    )
    rows, blockers = small_loader._read_jsonl(oversized, "LOCAL_TEST_FEED")
    assert rows == ()
    assert blockers == ("LOCAL_TEST_FEED_UNSAFE_OR_OVERSIZED",)


def test_runtime_context_loader_static_parsers_reject_unsafe_values() -> None:
    assert RuntimeResearchContextLoader._normalized_symbol(None) is None
    assert RuntimeResearchContextLoader._normalized_symbol(123) == ""
    assert RuntimeResearchContextLoader._normalized_symbol(" hotusdt ") == "HOTUSDT"
    assert RuntimeResearchContextLoader._is_allowed_url("https://example.com/a")
    assert not RuntimeResearchContextLoader._is_allowed_url("http://example.com/a")
    assert not RuntimeResearchContextLoader._is_allowed_url(
        "https://user:pass@example.com/a"
    )
    assert RuntimeResearchContextLoader._timestamp("not-a-date") is None
    assert RuntimeResearchContextLoader._timestamp("2026-08-13T17:00:00") is None
    assert RuntimeResearchContextLoader._decimal(True) is None
    assert RuntimeResearchContextLoader._decimal("nan") is None
    assert RuntimeResearchContextLoader._positive_int(True) is None
    assert RuntimeResearchContextLoader._positive_int(0) is None
    assert RuntimeResearchContextLoader._positive_int(2) == 2
    assert RuntimeResearchContextLoader._non_negative_int(-1) is None
    assert RuntimeResearchContextLoader._non_negative_int(0) == 0
    assert RuntimeResearchContextLoader._title_vote("upgrade and hack") == 0.0
    assert RuntimeResearchContextLoader._title_vote("major hack exploit") == -1.0


def test_runtime_context_loader_fail_closed_report_write_and_opportunity_filters(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
    )
    blocker_path = tmp_path / "report-dir"
    blocker_path.mkdir()

    assert loader._persist_opportunity_report(blocker_path, {"report_id": "r"}) == (
        "LOCAL_RESEARCH_OPPORTUNITY_REPORT_WRITE_FAILED",
    )

    status = _TrackingEvidenceStatus(
        status="NEW",
        first_seen_at=now,
        last_seen_at=now,
        last_change_at=now,
        latest_as_of=now,
        seen_count=1,
        change_count=0,
    )
    weak_technology = _TrackedEvidenceObservation(
        feed="technology",
        evidence_id="tech-weak",
        source="tech",
        source_url="https://tech.example/weak",
        as_of=now,
        summary="Weak development",
        signature="sig",
        directional_vote=Decimal("0.30"),
        score=Decimal("59"),
        impact="HIGH",
    )
    neutral_technology = _TrackedEvidenceObservation(
        feed="technology",
        evidence_id="tech-neutral",
        source="tech",
        source_url="https://tech.example/neutral",
        as_of=now,
        summary="Neutral development",
        signature="sig",
        directional_vote=Decimal("0.01"),
        score=Decimal("80"),
        impact="HIGH",
    )
    assert loader._technology_opportunity(snapshot, weak_technology, status) is None
    assert loader._technology_opportunity(snapshot, neutral_technology, status) is None

    positive_news = _TrackedEvidenceObservation(
        feed="news",
        evidence_id="news-upgrade",
        source="news",
        source_url="https://news.example/upgrade",
        as_of=now,
        summary="Critical launch approval",
        signature="sig",
        impact="CRITICAL",
    )
    assert loader._news_risk_opportunity(snapshot, positive_news, status) is None


def test_runtime_context_loader_returns_original_snapshot_without_context(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "missing-news.jsonl",
        social_feed_path=tmp_path / "missing-social.jsonl",
        content_feed_path=tmp_path / "missing-content.jsonl",
        technology_feed_path=tmp_path / "missing-technology.jsonl",
    )

    assert loader.attach(snapshot) is snapshot


def test_runtime_context_loader_parse_guards_cover_rejected_rows(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
    )

    base_news: dict[str, object] = {
        "event_id": "news-guard",
        "symbol": "HOTUSDT",
        "title": "Launch approval",
        "impact": "HIGH",
        "scheduled_at": now.isoformat(),
        "retrieved_at": now.isoformat(),
        "source": "news",
        "source_url": "https://news.example/guard",
    }
    news_overrides: tuple[dict[str, object], ...] = (
        {"symbol": "ETHUSDT"},
        {"title": ""},
        {"impact": "LOW"},
        {"retrieved_at": (now + timedelta(minutes=1)).isoformat()},
    )
    for news_override in news_overrides:
        news_row: dict[str, object] = {**base_news, **news_override}
        assert loader._parse_news_event(snapshot, news_row) is None

    base_sentiment: dict[str, object] = {
        "symbol": "HOTUSDT",
        "source": "social",
        "source_url": "https://x.com/example/status/guard",
        "as_of": now.isoformat(),
        "directional_vote": 0.4,
        "score": 60,
        "weight": 1,
    }
    sentiment_overrides: tuple[dict[str, object], ...] = (
        {"symbol": "ETHUSDT"},
        {"directional_vote": 2},
        {"score": 101},
        {"weight": -1},
        {"as_of": (now + timedelta(minutes=1)).isoformat()},
        {"as_of": (now - timedelta(days=2, minutes=1)).isoformat()},
    )
    for sentiment_override in sentiment_overrides:
        sentiment_row: dict[str, object] = {**base_sentiment, **sentiment_override}
        assert loader._parse_sentiment_entry(snapshot, sentiment_row, "social") is None

    base_technology: dict[str, object] = {
        "development_id": "tech-guard",
        "symbol": "HOTUSDT",
        "title": "Inference upgrade",
        "source": "tech",
        "source_url": "https://tech.example/guard",
        "as_of": now.isoformat(),
        "retrieved_at": now.isoformat(),
        "impact": "HIGH",
        "directional_vote": 0.4,
        "score": 70,
        "weight": 1,
    }
    fallback = {
        key: value
        for key, value in base_technology.items()
        if key not in {"development_id", "as_of"}
    }
    fallback.update(
        {"event_id": "tech-event-fallback", "scheduled_at": now.isoformat()}
    )
    parsed = loader._parse_technology_development(snapshot, fallback)
    assert parsed is not None
    assert parsed.development_id == "tech-event-fallback"
    assert parsed.as_of == now

    technology_overrides: tuple[dict[str, object], ...] = (
        {"symbol": "ETHUSDT"},
        {"title": ""},
        {"source_url": "http://tech.example/unsafe"},
        {"impact": "UNKNOWN"},
        {"directional_vote": 2},
        {"score": 101},
        {"weight": 0},
        {"as_of": (now + timedelta(minutes=1)).isoformat()},
        {"retrieved_at": (now - timedelta(days=2)).isoformat()},
        {
            "as_of": (now - timedelta(days=2)).isoformat(),
            "retrieved_at": now.isoformat(),
        },
    )
    for technology_override in technology_overrides:
        technology_row: dict[str, object] = {
            **base_technology,
            **technology_override,
        }
        assert loader._parse_technology_development(snapshot, technology_row) is None


def test_runtime_context_loader_tracking_ledger_guards_invalid_payloads(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
    )

    for payload in (
        "{bad json",
        "[]",
        json.dumps({"version": 1}),
        json.dumps({"feeds": {"unknown": {}}}),
        json.dumps({"feeds": {"news": []}}),
        json.dumps({"feeds": {"news": {"news-1": []}}}),
        json.dumps(
            {
                "feeds": {
                    "news": {
                        "news-1": {
                            "signature": "sig",
                            "summary": "",
                            "first_seen_at": now.isoformat(),
                            "last_seen_at": now.isoformat(),
                            "last_change_at": now.isoformat(),
                            "latest_as_of": now.isoformat(),
                            "seen_count": 1,
                            "change_count": 0,
                        }
                    }
                }
            }
        ),
    ):
        path = tmp_path / "ledger-invalid.json"
        path.write_text(payload, encoding="utf-8")
        feeds, blockers = loader._read_tracking_entries(path)
        assert feeds["news"] == {}
        assert blockers == ("LOCAL_RESEARCH_LEDGER_INVALID",)

    valid_path = tmp_path / "ledger-valid.json"
    valid_path.write_text(
        json.dumps(
            {
                "feeds": {
                    "news": {
                        "news-1": {
                            "signature": "sig",
                            "summary": "Launch approval",
                            "first_seen_at": now.isoformat(),
                            "last_seen_at": now.isoformat(),
                            "last_change_at": now.isoformat(),
                            "latest_as_of": now.isoformat(),
                            "seen_count": 1,
                            "change_count": 0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    feeds, blockers = loader._read_tracking_entries(valid_path)
    assert blockers == ()
    assert feeds["news"]["news-1"].summary == "Launch approval"
    report_dir = tmp_path / "ledger-dir"
    report_dir.mkdir()
    assert loader._write_tracking_state(report_dir, {"version": 1}) == (
        "LOCAL_RESEARCH_LEDGER_WRITE_FAILED",
    )


def test_runtime_context_loader_tracking_prunes_caps_and_counts(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
        max_tracking_entries=100,
    )
    stale_entry = _TrackerEntry(
        evidence_id="old",
        signature="old",
        summary="old",
        first_seen_at=now - timedelta(days=2),
        last_seen_at=now - timedelta(days=2),
        last_change_at=now - timedelta(days=2),
        latest_as_of=now - timedelta(days=2),
        seen_count=1,
        change_count=0,
    )
    tracking: dict[str, dict[str, _TrackerEntry]] = {
        "news": {"old": stale_entry},
        "social": {},
        "content": {},
        "technology": {},
    }
    loader._prune_stale_tracking_entries(now, tracking)
    assert tracking["news"] == {}

    capacity_entries = {
        f"news-{index:03d}": _TrackerEntry(
            evidence_id=f"news-{index:03d}",
            signature="sig",
            summary="summary",
            first_seen_at=now - timedelta(minutes=index),
            last_seen_at=now - timedelta(minutes=index),
            last_change_at=now - timedelta(minutes=index),
            latest_as_of=now - timedelta(minutes=index),
            seen_count=1,
            change_count=0,
        )
        for index in range(101)
    }
    tracking = {
        "news": capacity_entries,
        "social": {},
        "content": {},
        "technology": {},
    }
    loader._enforce_tracking_capacity(tracking)
    assert sum(len(feed) for feed in tracking.values()) == 100
    assert "news-100" not in tracking["news"]

    assert loader._tracking_counter({}, "social", "new_count") == 0
    assert (
        loader._tracking_counter({"social": {"new_count": True}}, "social", "new_count")
        == 0
    )
    assert (
        loader._tracking_counter({"social": {"new_count": -1}}, "social", "new_count")
        == 0
    )
    assert (
        loader._tracking_counter({"social": {"new_count": 2}}, "social", "new_count")
        == 2
    )


def test_runtime_context_loader_merges_annotations_and_static_sequences(
    tmp_path: Path,
) -> None:
    snapshot = public_snapshot()
    now = snapshot.created_at
    loader = RuntimeResearchContextLoader(
        news_feed_path=tmp_path / "news-events.jsonl",
        social_feed_path=tmp_path / "social-events.jsonl",
        content_feed_path=tmp_path / "content-events.jsonl",
    )
    status = _TrackingEvidenceStatus(
        status="UPDATED",
        first_seen_at=now - timedelta(minutes=10),
        last_seen_at=now,
        last_change_at=now,
        latest_as_of=now,
        seen_count=3,
        change_count=1,
    )
    payload: dict[str, object] = {
        "technology_developments": [
            {"development_id": "tech-1", "title": "Upgrade"},
            {"development_id": "", "title": "No id"},
        ]
    }
    loader._annotate_technology_developments(
        payload,
        {("technology", "tech-1"): status},
    )
    developments = tuple(
        _as_mapping(item) for item in _as_tuple(payload["technology_developments"])
    )
    assert developments[0]["tracking_status"] == "UPDATED"
    assert developments[0]["change_count"] == 1
    assert "tracking_status" not in developments[1]

    assert loader._mapping_sequence([{"a": 1}, "bad"]) == ({"a": 1},)
    assert loader._mapping_sequence("bad") == ()
    assert loader._text_sequence(["A", "", 5, "B"]) == ("A", "B")
    assert loader._text_sequence("bad") == ()
    assert loader._with_provider_blockers(
        {"provider_blockers": ("A",)},
        ("A", "B"),
    )["provider_blockers"] == ("A", "B")
    assert loader._timestamp(now) == now
    assert loader._timestamp(123) is None
    assert loader._decimal("not-a-number") is None
    assert loader._non_negative_int("0") is None

    merged = loader._merge_news_snapshot(
        {
            "high_impact_events": (
                {
                    "event_id": "same",
                    "scheduled_at": "2026-08-13T10:00:00+00:00",
                    "title": "old",
                },
            ),
            "provider_blockers": ("OLD",),
        },
        {
            "high_impact_events": [
                {
                    "event_id": "same",
                    "scheduled_at": "2026-08-13T11:00:00+00:00",
                    "title": "new",
                },
                {"event_id": "", "scheduled_at": "2026-08-13T12:00:00+00:00"},
            ],
            "provider_blockers": ["NEW", "OLD"],
        },
    )
    events = tuple(
        _as_mapping(item) for item in _as_tuple(merged["high_impact_events"])
    )
    assert events == (
        {
            "event_id": "same",
            "scheduled_at": "2026-08-13T11:00:00+00:00",
            "title": "new",
        },
    )
    assert merged["provider_blockers"] == ("OLD", "NEW")


def test_runtime_context_loader_protocol_default_raises() -> None:
    class _MissingAcquire:
        def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
            return SnapshotAcquirer.acquire(self, symbol, timeframes)

    with pytest.raises(NotImplementedError):
        _MissingAcquire().acquire("HOTUSDT", ("1h",))
