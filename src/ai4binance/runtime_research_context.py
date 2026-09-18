"""File-backed social/news/content context attached to runtime snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import urlparse

from ai4binance.reporting import to_primitive
from ai4binance.schemas import MarketSnapshot
from ai4binance.storage import write_json_object_verified

_POSITIVE_NEWS_TOKENS = (
    "approval",
    "partnership",
    "launch",
    "listing",
    "upgrade",
    "inflow",
)
_NEGATIVE_NEWS_TOKENS = (
    "hack",
    "exploit",
    "outage",
    "delay",
    "lawsuit",
    "ban",
    "delist",
    "breach",
    "liquidation",
)
_TRACKER_VERSION = 1
_TRACKING_FEEDS: tuple[str, ...] = ("news", "social", "content", "technology")
_TrackingStatus = Literal["NEW", "UPDATED", "UNCHANGED"]


@dataclass(frozen=True, slots=True)
class _ParsedNewsEvent:
    event_id: str
    title: str
    impact: str
    source: str
    source_url: str
    scheduled_at: datetime
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class _ParsedSentimentEntry:
    evidence_id: str
    origin: str
    source: str
    source_url: str
    as_of: datetime
    weight: Decimal
    directional_vote: Decimal
    score: Decimal


@dataclass(frozen=True, slots=True)
class _ParsedTechnologyDevelopment:
    development_id: str
    title: str
    impact: str
    source: str
    source_url: str
    as_of: datetime
    retrieved_at: datetime
    directional_vote: Decimal
    score: Decimal
    weight: Decimal
    category: str
    opportunity_hint: str


@dataclass(frozen=True, slots=True)
class _TrackedEvidenceObservation:
    feed: str
    evidence_id: str
    source: str
    source_url: str
    as_of: datetime
    summary: str
    signature: str
    directional_vote: Decimal | None = None
    score: Decimal | None = None
    impact: str | None = None
    category: str = ""
    opportunity_hint: str = ""


@dataclass(slots=True)
class _TrackerEntry:
    evidence_id: str
    signature: str
    summary: str
    first_seen_at: datetime
    last_seen_at: datetime
    last_change_at: datetime
    latest_as_of: datetime
    seen_count: int
    change_count: int


@dataclass(slots=True)
class _FeedCycleStats:
    observed_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    latest_as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class _TrackingEvidenceStatus:
    status: _TrackingStatus
    first_seen_at: datetime
    last_seen_at: datetime
    last_change_at: datetime
    latest_as_of: datetime
    seen_count: int
    change_count: int


@dataclass(frozen=True, slots=True)
class _SectionBuildResult:
    payload: dict[str, object]
    observations: tuple[_TrackedEvidenceObservation, ...]


@dataclass(frozen=True, slots=True)
class _TechnologyBuildResult:
    payload: dict[str, object]
    observations: tuple[_TrackedEvidenceObservation, ...]


@dataclass(frozen=True, slots=True)
class _TrackingCycleResult:
    state_payload: dict[str, object]
    feed_summary: dict[str, dict[str, object]]
    evidence_status: dict[tuple[str, str], _TrackingEvidenceStatus]
    changed: tuple[_TrackedEvidenceObservation, ...]


@dataclass(frozen=True, slots=True)
class RuntimeResearchContextLoader:
    """Attach local research context without introducing execution authority."""

    news_feed_path: Path
    social_feed_path: Path
    content_feed_path: Path
    max_file_bytes: int = 2_000_000
    max_event_age: timedelta = timedelta(hours=24)
    technology_feed_path: Path | None = None
    context_ledger_path: Path | None = None
    opportunity_report_path: Path | None = None
    max_tracking_entries: int = 5_000

    def __post_init__(self) -> None:
        if self.max_file_bytes < 1_024:
            raise ValueError("runtime research context file limit is too small")
        if self.max_event_age <= timedelta(0):
            raise ValueError("runtime research context maximum age must be positive")
        if not 100 <= self.max_tracking_entries <= 200_000:
            raise ValueError("runtime research tracking capacity must be bounded")

    def attach(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Return a new immutable snapshot enriched with local context."""
        technology = self._build_technology_context(snapshot)
        news_section = self._build_news_snapshot(snapshot)
        sentiment_section = self._build_sentiment_snapshot(snapshot)

        observations = (
            *news_section.observations,
            *sentiment_section.observations,
            *technology.observations,
        )
        tracker_path = self._resolve_runtime_path(
            self.context_ledger_path,
            "evidence-ledger.json",
        )
        tracker_entries, tracker_blockers = self._read_tracking_entries(tracker_path)
        tracking = self._update_tracking(snapshot, tracker_entries, tuple(observations))
        tracker_write_blockers = self._write_tracking_state(
            tracker_path,
            tracking.state_payload,
        )
        shared_blockers = tuple(
            dict.fromkeys((*tracker_blockers, *tracker_write_blockers))
        )

        has_context = bool(
            observations
            or news_section.payload
            or sentiment_section.payload
            or technology.payload
            or shared_blockers
        )
        if not has_context:
            return snapshot

        report = self._build_opportunity_report(
            snapshot=snapshot,
            tracking=tracking,
            sentiment_payload=sentiment_section.payload,
            technology_payload=technology.payload,
        )
        report_path = self._resolve_runtime_path(
            self.opportunity_report_path,
            "opportunities-latest.json",
        )
        report_blockers = self._persist_opportunity_report(report_path, report)
        all_blockers = tuple(dict.fromkeys((*shared_blockers, *report_blockers)))
        report_summary: dict[str, object] = {
            "path": str(report_path),
            "generated_at": report["generated_at"],
            "status": report["status"],
            "opportunity_count": report["opportunity_count"],
        }

        incoming_news = dict(news_section.payload)
        if technology.payload:
            incoming_news = self._merge_news_snapshot(incoming_news, technology.payload)
        incoming_news = self._inject_tracking_metadata(
            incoming_news,
            observed_at=snapshot.created_at,
            feed_summary=tracking.feed_summary,
            changed_count=len(tracking.changed),
        )
        incoming_news["opportunity_report"] = report_summary
        self._annotate_technology_developments(
            incoming_news,
            tracking.evidence_status,
        )
        incoming_news = self._with_provider_blockers(incoming_news, all_blockers)

        incoming_sentiment = dict(sentiment_section.payload)
        incoming_sentiment = self._inject_tracking_metadata(
            incoming_sentiment,
            observed_at=snapshot.created_at,
            feed_summary=tracking.feed_summary,
            changed_count=len(tracking.changed),
        )
        incoming_sentiment["opportunity_report"] = report_summary
        incoming_sentiment = self._with_provider_blockers(
            incoming_sentiment,
            all_blockers,
        )

        merged_news = dict(snapshot.news_snapshot)
        if incoming_news:
            merged_news = self._merge_news_snapshot(merged_news, incoming_news)

        merged_sentiment = dict(snapshot.sentiment_snapshot)
        if incoming_sentiment:
            merged_sentiment.update(incoming_sentiment)

        if merged_news == dict(snapshot.news_snapshot) and merged_sentiment == dict(
            snapshot.sentiment_snapshot
        ):
            return snapshot
        return replace(
            snapshot,
            news_snapshot=merged_news,
            sentiment_snapshot=merged_sentiment,
        )

    def _build_news_snapshot(self, snapshot: MarketSnapshot) -> _SectionBuildResult:
        rows, blockers = self._read_jsonl(self.news_feed_path, "LOCAL_NEWS_FEED")
        events: list[_ParsedNewsEvent] = []
        vote_weight = Decimal("0")
        weighted_vote = Decimal("0")
        retrieved_times: list[datetime] = []
        parse_blockers: list[str] = []

        for row in rows:
            event = self._parse_news_event(snapshot, row)
            if event is None:
                parse_blockers.append("LOCAL_NEWS_EVENT_INVALID")
                continue
            events.append(event)
            retrieved_times.append(event.retrieved_at)
            weight = Decimal("2") if event.impact == "CRITICAL" else Decimal("1")
            vote = self._title_vote(event.title)
            weighted_vote += Decimal(str(vote)) * weight
            vote_weight += weight

        if not events and not blockers and not parse_blockers:
            return _SectionBuildResult({}, ())

        deduped = {item.event_id: item for item in events}
        ordered = sorted(
            deduped.values(),
            key=lambda item: (item.scheduled_at, item.event_id),
        )
        events_payload = tuple(
            {
                "event_id": item.event_id,
                "title": item.title,
                "scheduled_at": item.scheduled_at,
                "impact": item.impact,
                "source": item.source,
                "source_url": item.source_url,
            }
            for item in ordered
        )
        observations = tuple(self._news_observation(item) for item in ordered)
        all_blockers = tuple(dict.fromkeys((*blockers, *parse_blockers)))
        payload: dict[str, object] = {
            "high_impact_events": events_payload,
            "provider_blockers": all_blockers,
        }
        if not retrieved_times:
            return _SectionBuildResult(payload, observations)

        directional_vote = (
            float(weighted_vote / vote_weight) if vote_weight > Decimal("0") else 0.0
        )
        score = max(0.0, min(100.0, 50.0 + abs(directional_vote) * 50.0))
        as_of = max(retrieved_times)
        payload.update(
            {
                "source_count": len(events_payload),
                "directional_vote": round(directional_vote, 6),
                "score": round(score, 6),
                "as_of": as_of.isoformat(),
            }
        )
        return _SectionBuildResult(payload, observations)

    def _build_sentiment_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> _SectionBuildResult:
        social_rows, social_blockers = self._read_jsonl(
            self.social_feed_path,
            "LOCAL_SOCIAL_FEED",
        )
        content_rows, content_blockers = self._read_jsonl(
            self.content_feed_path,
            "LOCAL_CONTENT_FEED",
        )
        entries: list[_ParsedSentimentEntry] = []
        parse_blockers: list[str] = []
        observations: list[_TrackedEvidenceObservation] = []

        for row in social_rows:
            parsed = self._parse_sentiment_entry(snapshot, row, "social")
            if parsed is None:
                parse_blockers.append("LOCAL_SOCIAL_EVENT_INVALID")
                continue
            entries.append(parsed)
            observations.append(self._sentiment_observation(parsed))
        for row in content_rows:
            parsed = self._parse_sentiment_entry(snapshot, row, "content")
            if parsed is None:
                parse_blockers.append("LOCAL_CONTENT_EVENT_INVALID")
                continue
            entries.append(parsed)
            observations.append(self._sentiment_observation(parsed))

        blockers = tuple(
            dict.fromkeys((*social_blockers, *content_blockers, *parse_blockers))
        )
        if not entries:
            empty_payload: dict[str, object] = (
                {"provider_blockers": blockers} if blockers else {}
            )
            return _SectionBuildResult(empty_payload, tuple(observations))

        total_weight = Decimal("0")
        weighted_vote = Decimal("0")
        weighted_score = Decimal("0")
        latest = entries[0].as_of
        sources: set[str] = set()
        for entry in entries:
            total_weight += entry.weight
            weighted_vote += entry.directional_vote * entry.weight
            weighted_score += entry.score * entry.weight
            latest = max(latest, entry.as_of)
            sources.add(entry.source)
        payload: dict[str, object] = {
            "source_count": len(entries),
            "directional_vote": round(float(weighted_vote / total_weight), 6),
            "score": round(float(weighted_score / total_weight), 6),
            "as_of": latest.isoformat(),
            "sources": tuple(sorted(sources)),
            "provider_blockers": blockers,
        }
        return _SectionBuildResult(payload, tuple(observations))

    def _build_technology_context(
        self,
        snapshot: MarketSnapshot,
    ) -> _TechnologyBuildResult:
        rows, blockers = self._read_jsonl(
            self._resolve_technology_feed_path(),
            "LOCAL_TECHNOLOGY_FEED",
        )
        developments: list[_ParsedTechnologyDevelopment] = []
        parse_blockers: list[str] = []
        for row in rows:
            parsed = self._parse_technology_development(snapshot, row)
            if parsed is None:
                parse_blockers.append("LOCAL_TECHNOLOGY_EVENT_INVALID")
                continue
            developments.append(parsed)

        if not developments and not blockers and not parse_blockers:
            return _TechnologyBuildResult({}, ())

        deduped = {item.development_id: item for item in developments}
        ordered = sorted(
            deduped.values(),
            key=lambda item: (item.as_of, item.development_id),
        )
        all_blockers = tuple(dict.fromkeys((*blockers, *parse_blockers)))

        observations = tuple(self._technology_observation(item) for item in ordered)
        developments_payload = tuple(
            {
                "development_id": item.development_id,
                "title": item.title,
                "impact": item.impact,
                "source": item.source,
                "source_url": item.source_url,
                "as_of": item.as_of.isoformat(),
                "retrieved_at": item.retrieved_at.isoformat(),
                "directional_vote": round(float(item.directional_vote), 6),
                "score": round(float(item.score), 6),
                "category": item.category,
                "opportunity_hint": item.opportunity_hint,
            }
            for item in ordered
        )
        payload: dict[str, object] = {
            "technology_developments": developments_payload,
            "technology_source_count": len(developments_payload),
            "provider_blockers": all_blockers,
        }
        if ordered:
            payload["technology_as_of"] = ordered[-1].as_of.isoformat()
        return _TechnologyBuildResult(payload, observations)

    def _parse_news_event(
        self,
        snapshot: MarketSnapshot,
        row: Mapping[str, object],
    ) -> _ParsedNewsEvent | None:
        symbol = self._normalized_symbol(row.get("symbol"))
        if symbol not in {None, "ALL", snapshot.symbol}:
            return None
        event_id = self._required_text(row.get("event_id"))
        title = self._required_text(row.get("title"))
        impact = self._required_text(row.get("impact"))
        source = self._required_text(row.get("source"))
        source_url = self._required_text(row.get("source_url"))
        scheduled_at = self._timestamp(row.get("scheduled_at"))
        retrieved_at = self._timestamp(row.get("retrieved_at"))
        if (
            event_id is None
            or title is None
            or impact is None
            or source is None
            or source_url is None
            or scheduled_at is None
            or retrieved_at is None
        ):
            return None
        normalized_impact = impact.upper()
        if normalized_impact not in {"HIGH", "CRITICAL"}:
            return None
        if not self._is_allowed_url(source_url):
            return None
        if retrieved_at > snapshot.created_at:
            return None
        if snapshot.created_at - retrieved_at > self.max_event_age:
            return None
        return _ParsedNewsEvent(
            event_id=event_id,
            title=title,
            impact=normalized_impact,
            source=source,
            source_url=source_url,
            scheduled_at=scheduled_at,
            retrieved_at=retrieved_at,
        )

    def _parse_sentiment_entry(
        self,
        snapshot: MarketSnapshot,
        row: Mapping[str, object],
        origin: str,
    ) -> _ParsedSentimentEntry | None:
        symbol = self._normalized_symbol(row.get("symbol"))
        if symbol not in {None, "ALL", snapshot.symbol}:
            return None
        directional_vote = self._decimal(row.get("directional_vote"))
        score = self._decimal(row.get("score"))
        as_of = self._timestamp(row.get("as_of"))
        source = self._required_text(row.get("source")) or origin
        source_url = self._required_text(row.get("source_url"))
        weight = self._decimal(row.get("weight")) or Decimal("1")
        if (
            directional_vote is None
            or score is None
            or as_of is None
            or source_url is None
        ):
            return None
        if not self._is_allowed_url(source_url):
            return None
        if not Decimal("-1") <= directional_vote <= Decimal("1"):
            return None
        if not Decimal("0") <= score <= Decimal("100"):
            return None
        if weight <= Decimal("0"):
            return None
        if as_of > snapshot.created_at:
            return None
        if snapshot.created_at - as_of > self.max_event_age:
            return None
        evidence_id = self._required_text(row.get("event_id"))
        if evidence_id is None:
            evidence_id = self._synthetic_sentiment_evidence_id(
                origin=origin,
                source=source,
                source_url=source_url,
                as_of=as_of,
                directional_vote=directional_vote,
                score=score,
            )
        return _ParsedSentimentEntry(
            evidence_id=evidence_id,
            origin=origin,
            source=source,
            source_url=source_url,
            as_of=as_of,
            weight=weight,
            directional_vote=directional_vote,
            score=score,
        )

    def _parse_technology_development(
        self,
        snapshot: MarketSnapshot,
        row: Mapping[str, object],
    ) -> _ParsedTechnologyDevelopment | None:
        symbol = self._normalized_symbol(row.get("symbol"))
        if symbol not in {None, "ALL", snapshot.symbol}:
            return None
        development_id = self._required_text(row.get("development_id"))
        if development_id is None:
            development_id = self._required_text(row.get("event_id"))
        title = self._required_text(row.get("title"))
        source = self._required_text(row.get("source"))
        source_url = self._required_text(row.get("source_url"))
        category = self._required_text(row.get("category")) or "technology"
        opportunity_hint = self._required_text(row.get("opportunity_hint")) or ""
        as_of = self._timestamp(row.get("as_of"))
        if as_of is None:
            as_of = self._timestamp(row.get("scheduled_at"))
        retrieved_at = self._timestamp(row.get("retrieved_at")) or as_of
        impact = self._required_text(row.get("impact")) or "MEDIUM"
        directional_vote = self._decimal(row.get("directional_vote"))
        score = self._decimal(row.get("score"))
        weight = self._decimal(row.get("weight"))

        if (
            development_id is None
            or title is None
            or source is None
            or source_url is None
            or as_of is None
            or retrieved_at is None
        ):
            return None
        if not self._is_allowed_url(source_url):
            return None

        normalized_impact = impact.upper()
        if normalized_impact not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            return None

        default_vote = self._default_vote_for_impact(normalized_impact)
        default_score = self._default_score_for_impact(normalized_impact)
        default_weight = self._default_weight_for_impact(normalized_impact)
        resolved_vote = (
            directional_vote if directional_vote is not None else default_vote
        )
        resolved_score = score if score is not None else default_score
        resolved_weight = weight if weight is not None else default_weight

        if not Decimal("-1") <= resolved_vote <= Decimal("1"):
            return None
        if not Decimal("0") <= resolved_score <= Decimal("100"):
            return None
        if resolved_weight <= Decimal("0"):
            return None
        if retrieved_at > snapshot.created_at or as_of > snapshot.created_at:
            return None
        if snapshot.created_at - retrieved_at > self.max_event_age:
            return None
        if snapshot.created_at - as_of > self.max_event_age:
            return None

        return _ParsedTechnologyDevelopment(
            development_id=development_id,
            title=title,
            impact=normalized_impact,
            source=source,
            source_url=source_url,
            as_of=as_of,
            retrieved_at=retrieved_at,
            directional_vote=resolved_vote,
            score=resolved_score,
            weight=resolved_weight,
            category=category,
            opportunity_hint=opportunity_hint,
        )

    def _read_tracking_entries(
        self,
        path: Path,
    ) -> tuple[dict[str, dict[str, _TrackerEntry]], tuple[str, ...]]:
        feeds: dict[str, dict[str, _TrackerEntry]] = {
            feed: {} for feed in _TRACKING_FEEDS
        }
        absolute = path if path.is_absolute() else Path.cwd() / path
        if not absolute.exists():
            return feeds, ()
        try:
            loaded = json.loads(absolute.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return feeds, ("LOCAL_RESEARCH_LEDGER_INVALID",)
        if not isinstance(loaded, Mapping):
            return feeds, ("LOCAL_RESEARCH_LEDGER_INVALID",)

        invalid = False
        raw_feeds = loaded.get("feeds")
        if not isinstance(raw_feeds, Mapping):
            return feeds, ("LOCAL_RESEARCH_LEDGER_INVALID",)

        for feed_name, raw_feed_entries in raw_feeds.items():
            if not isinstance(feed_name, str) or feed_name not in feeds:
                invalid = True
                continue
            if not isinstance(raw_feed_entries, Mapping):
                invalid = True
                continue
            parsed_feed: dict[str, _TrackerEntry] = {}
            for evidence_id, raw_entry in raw_feed_entries.items():
                if not isinstance(evidence_id, str):
                    invalid = True
                    continue
                parsed = self._tracker_entry_from_payload(evidence_id, raw_entry)
                if parsed is None:
                    invalid = True
                    continue
                parsed_feed[evidence_id] = parsed
            feeds[feed_name] = parsed_feed

        blockers: tuple[str, ...] = (
            ("LOCAL_RESEARCH_LEDGER_INVALID",) if invalid else ()
        )
        return feeds, blockers

    def _update_tracking(
        self,
        snapshot: MarketSnapshot,
        previous: dict[str, dict[str, _TrackerEntry]],
        observations: tuple[_TrackedEvidenceObservation, ...],
    ) -> _TrackingCycleResult:
        tracking: dict[str, dict[str, _TrackerEntry]] = {
            feed: dict(previous.get(feed, {})) for feed in _TRACKING_FEEDS
        }
        stats: dict[str, _FeedCycleStats] = {
            feed: _FeedCycleStats() for feed in _TRACKING_FEEDS
        }
        statuses: dict[tuple[str, str], _TrackingStatus] = {}
        changed: list[_TrackedEvidenceObservation] = []

        for observation in observations:
            if observation.feed not in tracking:
                continue
            feed_entries = tracking[observation.feed]
            feed_stats = stats[observation.feed]
            feed_stats.observed_count += 1
            if (
                feed_stats.latest_as_of is None
                or observation.as_of > feed_stats.latest_as_of
            ):
                feed_stats.latest_as_of = observation.as_of

            existing = feed_entries.get(observation.evidence_id)
            if existing is None:
                feed_entries[observation.evidence_id] = _TrackerEntry(
                    evidence_id=observation.evidence_id,
                    signature=observation.signature,
                    summary=observation.summary,
                    first_seen_at=snapshot.created_at,
                    last_seen_at=snapshot.created_at,
                    last_change_at=snapshot.created_at,
                    latest_as_of=observation.as_of,
                    seen_count=1,
                    change_count=0,
                )
                status: _TrackingStatus = "NEW"
                feed_stats.new_count += 1
                changed.append(observation)
            else:
                existing.last_seen_at = snapshot.created_at
                existing.latest_as_of = max(existing.latest_as_of, observation.as_of)
                existing.seen_count += 1
                existing.summary = observation.summary
                if existing.signature == observation.signature:
                    status = "UNCHANGED"
                    feed_stats.unchanged_count += 1
                else:
                    existing.signature = observation.signature
                    existing.last_change_at = snapshot.created_at
                    existing.change_count += 1
                    status = "UPDATED"
                    feed_stats.updated_count += 1
                    changed.append(observation)
            statuses[(observation.feed, observation.evidence_id)] = status

        self._prune_stale_tracking_entries(snapshot.created_at, tracking)
        self._enforce_tracking_capacity(tracking)

        evidence_status: dict[tuple[str, str], _TrackingEvidenceStatus] = {}
        for identity, status in statuses.items():
            feed_name, evidence_id = identity
            entry = tracking.get(feed_name, {}).get(evidence_id)
            if entry is None:
                continue
            evidence_status[identity] = _TrackingEvidenceStatus(
                status=status,
                first_seen_at=entry.first_seen_at,
                last_seen_at=entry.last_seen_at,
                last_change_at=entry.last_change_at,
                latest_as_of=entry.latest_as_of,
                seen_count=entry.seen_count,
                change_count=entry.change_count,
            )

        feed_summary = {
            feed: self._feed_cycle_summary_payload(stats[feed], len(tracking[feed]))
            for feed in _TRACKING_FEEDS
        }
        state_payload: dict[str, object] = {
            "version": _TRACKER_VERSION,
            "updated_at": snapshot.created_at.isoformat(),
            "max_event_age_seconds": int(self.max_event_age.total_seconds()),
            "max_tracking_entries": self.max_tracking_entries,
            "feeds": {
                feed: {
                    evidence_id: self._tracker_entry_payload(entry)
                    for evidence_id, entry in sorted(feed_entries.items())
                }
                for feed, feed_entries in tracking.items()
            },
        }
        return _TrackingCycleResult(
            state_payload=state_payload,
            feed_summary=feed_summary,
            evidence_status=evidence_status,
            changed=tuple(changed),
        )

    def _write_tracking_state(
        self,
        path: Path,
        payload: dict[str, object],
    ) -> tuple[str, ...]:
        absolute = path if path.is_absolute() else Path.cwd() / path
        try:
            primitive = cast(dict[str, object], to_primitive(payload))
            write_json_object_verified(
                absolute,
                primitive,
                blocker="LOCAL_RESEARCH_LEDGER_VERIFY_FAILED",
                subject_id="runtime-research-ledger",
                indent=2,
            )
        except (OSError, TypeError, ValueError):
            return ("LOCAL_RESEARCH_LEDGER_WRITE_FAILED",)
        return ()

    def _build_opportunity_report(
        self,
        *,
        snapshot: MarketSnapshot,
        tracking: _TrackingCycleResult,
        sentiment_payload: Mapping[str, object],
        technology_payload: Mapping[str, object],
    ) -> dict[str, object]:
        opportunities: dict[str, dict[str, object]] = {}
        sentiment_changed = tuple(
            observation
            for observation in tracking.changed
            if observation.feed in {"social", "content"}
        )

        for observation in tracking.changed:
            status = tracking.evidence_status.get(
                (observation.feed, observation.evidence_id)
            )
            if status is None:
                continue
            if observation.feed == "technology":
                opportunity = self._technology_opportunity(
                    snapshot, observation, status
                )
                if opportunity is not None:
                    traced_opportunity = self._with_url_traceability(
                        opportunity,
                        (observation,),
                    )
                    opportunity_id = self._required_text(
                        traced_opportunity.get("opportunity_id")
                    )
                    if opportunity_id is not None:
                        opportunities[opportunity_id] = traced_opportunity
            elif observation.feed == "news":
                opportunity = self._news_risk_opportunity(snapshot, observation, status)
                if opportunity is not None:
                    traced_opportunity = self._with_url_traceability(
                        opportunity,
                        (observation,),
                    )
                    opportunity_id = self._required_text(
                        traced_opportunity.get("opportunity_id")
                    )
                    if opportunity_id is not None:
                        opportunities[opportunity_id] = traced_opportunity

        social_updates = self._tracking_counter(
            tracking.feed_summary, "social", "new_count"
        )
        social_updates += self._tracking_counter(
            tracking.feed_summary,
            "social",
            "updated_count",
        )
        content_updates = self._tracking_counter(
            tracking.feed_summary,
            "content",
            "new_count",
        )
        content_updates += self._tracking_counter(
            tracking.feed_summary,
            "content",
            "updated_count",
        )
        sentiment_vote = self._decimal(sentiment_payload.get("directional_vote"))
        sentiment_score = self._decimal(sentiment_payload.get("score"))
        if (
            social_updates + content_updates > 0
            and sentiment_vote is not None
            and sentiment_score is not None
            and sentiment_score >= Decimal("55")
            and abs(sentiment_vote) >= Decimal("0.2")
        ):
            sentiment_opportunity: dict[str, object] = {
                "opportunity_id": "sentiment-shift-setup-review",
                "category": "SETUP_QUALITY_REVIEW",
                "title": "Sentiment shift detected in social/content evidence",
                "detected_at": snapshot.created_at.isoformat(),
                "as_of": sentiment_payload.get("as_of"),
                "tracking_status": "UPDATED",
                "directional_vote": round(float(sentiment_vote), 6),
                "score": round(float(sentiment_score), 6),
                "social_updates": social_updates,
                "content_updates": content_updates,
                "ykb_attention_required": True,
                "ykb_attention_reason": "SENTIMENT_SHIFT",
                "recommended_action": (
                    "REVIEW_SETUP_QUALITY_UPSIDE"
                    if sentiment_vote > 0
                    else "REVIEW_SETUP_QUALITY_DOWNSIDE"
                ),
                "priority": "MEDIUM",
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
            opportunities["sentiment-shift-setup-review"] = self._with_url_traceability(
                sentiment_opportunity, sentiment_changed
            )

        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        ordered = tuple(
            payload
            for _, payload in sorted(
                opportunities.items(),
                key=lambda item: (
                    priority_order.get(str(item[1].get("priority", "LOW")), 3),
                    item[0],
                ),
            )
        )

        report_status = "ACTIVE" if ordered else "NO_ACTION"
        return {
            "report_id": f"runtime-research-opportunities:{snapshot.snapshot_id}",
            "snapshot_id": snapshot.snapshot_id,
            "generated_at": snapshot.created_at.isoformat(),
            "status": report_status,
            "opportunity_count": len(ordered),
            "opportunities": ordered,
            "tracking": {
                "changed_count": len(tracking.changed),
                "feeds": tracking.feed_summary,
            },
            "technology_as_of": technology_payload.get("technology_as_of"),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def _with_url_traceability(
        self,
        payload: Mapping[str, object],
        observations: tuple[_TrackedEvidenceObservation, ...],
    ) -> dict[str, object]:
        trace_entries = tuple(
            {
                "feed": item.feed,
                "evidence_id": item.evidence_id,
                "source": item.source,
                "source_url": item.source_url,
                "as_of": item.as_of.isoformat(),
                "summary": item.summary,
            }
            for item in sorted(
                observations,
                key=lambda item: (
                    item.feed,
                    item.evidence_id,
                    item.source_url,
                ),
            )
        )
        trace_urls = tuple(dict.fromkeys(item["source_url"] for item in trace_entries))
        enriched = dict(payload)
        enriched["trace_evidence"] = trace_entries
        enriched["trace_urls"] = trace_urls
        enriched["trace_url_count"] = len(trace_urls)
        enriched["primary_source_url"] = trace_urls[0] if trace_urls else None
        return enriched

    def _technology_opportunity(
        self,
        snapshot: MarketSnapshot,
        observation: _TrackedEvidenceObservation,
        status: _TrackingEvidenceStatus,
    ) -> dict[str, object] | None:
        if observation.directional_vote is None or observation.score is None:
            return None
        if observation.score < Decimal("60"):
            return None
        if Decimal("-0.15") < observation.directional_vote < Decimal("0.15"):
            return None
        direction = "UPSIDE" if observation.directional_vote >= 0 else "DOWNSIDE"
        action = (
            "REVIEW_SETUP_QUALITY_UPSIDE"
            if direction == "UPSIDE"
            else "REVIEW_DOWNSIDE_RISK_HARDENING"
        )
        priority = (
            "HIGH"
            if observation.impact in {"CRITICAL", "HIGH"}
            or observation.score >= Decimal("75")
            else "MEDIUM"
        )
        title = f"Technology evidence {status.status.lower()}: {observation.summary}"
        return {
            "opportunity_id": f"tech-{observation.evidence_id}",
            "category": "TECHNOLOGY_DEVELOPMENT",
            "title": title,
            "detected_at": snapshot.created_at.isoformat(),
            "as_of": observation.as_of.isoformat(),
            "source": observation.source,
            "source_url": observation.source_url,
            "evidence_feed": observation.feed,
            "evidence_id": observation.evidence_id,
            "tracking_status": status.status,
            "first_seen_at": status.first_seen_at.isoformat(),
            "last_seen_at": status.last_seen_at.isoformat(),
            "last_change_at": status.last_change_at.isoformat(),
            "change_count": status.change_count,
            "seen_count": status.seen_count,
            "directional_vote": round(float(observation.directional_vote), 6),
            "score": round(float(observation.score), 6),
            "impact": observation.impact,
            "category_label": observation.category,
            "opportunity_hint": observation.opportunity_hint,
            "evidence_source_url": observation.source_url,
            "ykb_attention_required": True,
            "ykb_attention_reason": "TECHNOLOGY_DEVELOPMENT_OPPORTUNITY",
            "ykb_question_ne_oldu": observation.summary,
            "ykb_question_kim_soyledi": observation.source,
            "ykb_question_nereden_dogrulanir": observation.source_url,
            "ykb_question_ne_zaman": observation.as_of.isoformat(),
            "ykb_question_ai4binance_etkisi": observation.impact or "UNKNOWN",
            "ykb_opportunity_hint": observation.opportunity_hint,
            "recommended_action": action,
            "priority": priority,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def _news_risk_opportunity(
        self,
        snapshot: MarketSnapshot,
        observation: _TrackedEvidenceObservation,
        status: _TrackingEvidenceStatus,
    ) -> dict[str, object] | None:
        if observation.impact != "CRITICAL":
            return None
        if self._title_vote(observation.summary) >= 0:
            return None
        return {
            "opportunity_id": f"risk-news-{observation.evidence_id}",
            "category": "RISK_HARDENING_REVIEW",
            "title": f"Critical downside news update: {observation.summary}",
            "detected_at": snapshot.created_at.isoformat(),
            "as_of": observation.as_of.isoformat(),
            "source": observation.source,
            "source_url": observation.source_url,
            "evidence_feed": observation.feed,
            "evidence_id": observation.evidence_id,
            "tracking_status": status.status,
            "first_seen_at": status.first_seen_at.isoformat(),
            "last_change_at": status.last_change_at.isoformat(),
            "evidence_source_url": observation.source_url,
            "ykb_attention_required": True,
            "ykb_attention_reason": "CRITICAL_NEWS_OR_RISK_SHIFT",
            "recommended_action": "REVIEW_STOP_GUARDS_AND_EXPOSURE_LIMITS",
            "priority": "HIGH",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def _persist_opportunity_report(
        self,
        path: Path,
        payload: dict[str, object],
    ) -> tuple[str, ...]:
        absolute = path if path.is_absolute() else Path.cwd() / path
        try:
            primitive = cast(dict[str, object], to_primitive(payload))
            report_id = self._required_text(primitive.get("report_id"))
            write_json_object_verified(
                absolute,
                primitive,
                blocker="LOCAL_RESEARCH_OPPORTUNITY_REPORT_VERIFY_FAILED",
                subject_id=report_id or "runtime-research-opportunities",
                indent=2,
            )
        except (OSError, TypeError, ValueError):
            return ("LOCAL_RESEARCH_OPPORTUNITY_REPORT_WRITE_FAILED",)
        return ()

    def _inject_tracking_metadata(
        self,
        payload: dict[str, object],
        *,
        observed_at: datetime,
        feed_summary: dict[str, dict[str, object]],
        changed_count: int,
    ) -> dict[str, object]:
        updated = dict(payload)
        updated["research_tracking"] = {
            "observed_at": observed_at.isoformat(),
            "changed_count": changed_count,
            "feeds": feed_summary,
        }
        return updated

    def _annotate_technology_developments(
        self,
        payload: dict[str, object],
        evidence_status: Mapping[tuple[str, str], _TrackingEvidenceStatus],
    ) -> None:
        raw_developments = payload.get("technology_developments")
        developments = self._mapping_sequence(raw_developments)
        if not developments:
            return

        annotated: list[dict[str, object]] = []
        for development in developments:
            entry = dict(development)
            development_id = self._required_text(development.get("development_id"))
            if development_id is not None:
                status = evidence_status.get(("technology", development_id))
                if status is not None:
                    entry.update(
                        {
                            "tracking_status": status.status,
                            "first_seen_at": status.first_seen_at.isoformat(),
                            "last_seen_at": status.last_seen_at.isoformat(),
                            "last_change_at": status.last_change_at.isoformat(),
                            "change_count": status.change_count,
                            "seen_count": status.seen_count,
                        }
                    )
            annotated.append(entry)
        payload["technology_developments"] = tuple(annotated)

    def _prune_stale_tracking_entries(
        self,
        observed_at: datetime,
        tracking: dict[str, dict[str, _TrackerEntry]],
    ) -> None:
        for feed_entries in tracking.values():
            stale_ids = [
                evidence_id
                for evidence_id, entry in feed_entries.items()
                if observed_at - entry.last_seen_at > self.max_event_age
            ]
            for evidence_id in stale_ids:
                feed_entries.pop(evidence_id, None)

    def _enforce_tracking_capacity(
        self,
        tracking: dict[str, dict[str, _TrackerEntry]],
    ) -> None:
        total = sum(len(feed_entries) for feed_entries in tracking.values())
        if total <= self.max_tracking_entries:
            return

        oldest: list[tuple[datetime, str, str]] = []
        for feed, feed_entries in tracking.items():
            for evidence_id, entry in feed_entries.items():
                oldest.append((entry.last_seen_at, feed, evidence_id))
        oldest.sort(key=lambda item: (item[0], item[1], item[2]))

        overflow = total - self.max_tracking_entries
        for _, feed, evidence_id in oldest[:overflow]:
            tracking.get(feed, {}).pop(evidence_id, None)

    def _tracker_entry_from_payload(
        self,
        evidence_id: str,
        payload: object,
    ) -> _TrackerEntry | None:
        if not isinstance(payload, Mapping):
            return None
        signature = self._required_text(payload.get("signature"))
        summary = self._required_text(payload.get("summary"))
        first_seen_at = self._timestamp(payload.get("first_seen_at"))
        last_seen_at = self._timestamp(payload.get("last_seen_at"))
        last_change_at = self._timestamp(payload.get("last_change_at"))
        latest_as_of = self._timestamp(payload.get("latest_as_of"))
        seen_count = self._positive_int(payload.get("seen_count"))
        change_count = self._non_negative_int(payload.get("change_count"))
        if (
            signature is None
            or summary is None
            or first_seen_at is None
            or last_seen_at is None
            or last_change_at is None
            or latest_as_of is None
            or seen_count is None
            or change_count is None
        ):
            return None
        return _TrackerEntry(
            evidence_id=evidence_id,
            signature=signature,
            summary=summary,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            last_change_at=last_change_at,
            latest_as_of=latest_as_of,
            seen_count=seen_count,
            change_count=change_count,
        )

    @staticmethod
    def _tracker_entry_payload(entry: _TrackerEntry) -> dict[str, object]:
        return {
            "signature": entry.signature,
            "summary": entry.summary,
            "first_seen_at": entry.first_seen_at.isoformat(),
            "last_seen_at": entry.last_seen_at.isoformat(),
            "last_change_at": entry.last_change_at.isoformat(),
            "latest_as_of": entry.latest_as_of.isoformat(),
            "seen_count": entry.seen_count,
            "change_count": entry.change_count,
        }

    @staticmethod
    def _feed_cycle_summary_payload(
        stats: _FeedCycleStats,
        tracked_total: int,
    ) -> dict[str, object]:
        return {
            "tracked_total": tracked_total,
            "observed_count": stats.observed_count,
            "new_count": stats.new_count,
            "updated_count": stats.updated_count,
            "unchanged_count": stats.unchanged_count,
            "latest_as_of": (
                stats.latest_as_of.isoformat()
                if stats.latest_as_of is not None
                else None
            ),
        }

    @staticmethod
    def _tracking_counter(
        feed_summary: Mapping[str, Mapping[str, object]],
        feed: str,
        field: str,
    ) -> int:
        feed_payload = feed_summary.get(feed)
        if not isinstance(feed_payload, Mapping):
            return 0
        value = feed_payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value if value >= 0 else 0

    def _news_observation(self, event: _ParsedNewsEvent) -> _TrackedEvidenceObservation:
        signature = self._stable_hash(
            {
                "title": event.title,
                "impact": event.impact,
                "source": event.source,
                "source_url": event.source_url,
                "scheduled_at": event.scheduled_at.isoformat(),
                "retrieved_at": event.retrieved_at.isoformat(),
            }
        )
        return _TrackedEvidenceObservation(
            feed="news",
            evidence_id=event.event_id,
            source=event.source,
            source_url=event.source_url,
            as_of=event.retrieved_at,
            summary=event.title,
            signature=signature,
            impact=event.impact,
        )

    def _sentiment_observation(
        self,
        entry: _ParsedSentimentEntry,
    ) -> _TrackedEvidenceObservation:
        signature = self._stable_hash(
            {
                "origin": entry.origin,
                "source": entry.source,
                "source_url": entry.source_url,
                "as_of": entry.as_of.isoformat(),
                "directional_vote": str(entry.directional_vote),
                "score": str(entry.score),
                "weight": str(entry.weight),
            }
        )
        return _TrackedEvidenceObservation(
            feed=entry.origin,
            evidence_id=entry.evidence_id,
            source=entry.source,
            source_url=entry.source_url,
            as_of=entry.as_of,
            summary=f"{entry.source}:{entry.origin}",
            signature=signature,
            directional_vote=entry.directional_vote,
            score=entry.score,
        )

    def _technology_observation(
        self,
        development: _ParsedTechnologyDevelopment,
    ) -> _TrackedEvidenceObservation:
        signature = self._stable_hash(
            {
                "title": development.title,
                "impact": development.impact,
                "source": development.source,
                "source_url": development.source_url,
                "as_of": development.as_of.isoformat(),
                "directional_vote": str(development.directional_vote),
                "score": str(development.score),
                "weight": str(development.weight),
                "category": development.category,
                "opportunity_hint": development.opportunity_hint,
            }
        )
        return _TrackedEvidenceObservation(
            feed="technology",
            evidence_id=development.development_id,
            source=development.source,
            source_url=development.source_url,
            as_of=development.as_of,
            summary=development.title,
            signature=signature,
            directional_vote=development.directional_vote,
            score=development.score,
            impact=development.impact,
            category=development.category,
            opportunity_hint=development.opportunity_hint,
        )

    def _resolve_technology_feed_path(self) -> Path:
        return self._resolve_runtime_path(
            self.technology_feed_path,
            "technology-events.jsonl",
        )

    def _resolve_runtime_path(
        self,
        configured_path: Path | None,
        default_name: str,
    ) -> Path:
        candidate = (
            configured_path
            if configured_path is not None
            else self.news_feed_path.with_name(default_name)
        )
        return candidate if candidate.is_absolute() else Path.cwd() / candidate

    @staticmethod
    def _required_text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @staticmethod
    def _normalized_symbol(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return ""
        normalized = value.strip().upper()
        return normalized if normalized else ""

    @staticmethod
    def _is_allowed_url(value: str) -> bool:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _positive_int(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if value > 0 else None

    @staticmethod
    def _non_negative_int(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if value >= 0 else None

    @staticmethod
    def _title_vote(title: str) -> float:
        normalized = title.casefold()
        positive_hits = sum(token in normalized for token in _POSITIVE_NEWS_TOKENS)
        negative_hits = sum(token in normalized for token in _NEGATIVE_NEWS_TOKENS)
        if positive_hits == negative_hits:
            return 0.0
        return 1.0 if positive_hits > negative_hits else -1.0

    @staticmethod
    def _default_vote_for_impact(impact: str) -> Decimal:
        defaults = {
            "LOW": Decimal("0"),
            "MEDIUM": Decimal("0.1"),
            "HIGH": Decimal("0.25"),
            "CRITICAL": Decimal("0.4"),
        }
        return defaults[impact]

    @staticmethod
    def _default_score_for_impact(impact: str) -> Decimal:
        defaults = {
            "LOW": Decimal("50"),
            "MEDIUM": Decimal("60"),
            "HIGH": Decimal("70"),
            "CRITICAL": Decimal("80"),
        }
        return defaults[impact]

    @staticmethod
    def _default_weight_for_impact(impact: str) -> Decimal:
        defaults = {
            "LOW": Decimal("1"),
            "MEDIUM": Decimal("1.25"),
            "HIGH": Decimal("1.75"),
            "CRITICAL": Decimal("2.25"),
        }
        return defaults[impact]

    @staticmethod
    def _synthetic_sentiment_evidence_id(
        *,
        origin: str,
        source: str,
        source_url: str,
        as_of: datetime,
        directional_vote: Decimal,
        score: Decimal,
    ) -> str:
        raw = {
            "origin": origin,
            "source": source,
            "source_url": source_url,
            "as_of": as_of.isoformat(),
            "directional_vote": str(directional_vote),
            "score": str(score),
        }
        encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()[:24]
        return f"{origin}:{digest}"

    @staticmethod
    def _stable_hash(payload: Mapping[str, object]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
        if isinstance(value, tuple):
            candidates = value
        elif isinstance(value, list):
            candidates = tuple(value)
        else:
            return ()
        return tuple(item for item in candidates if isinstance(item, Mapping))

    @staticmethod
    def _text_sequence(value: object) -> tuple[str, ...]:
        if isinstance(value, tuple):
            candidates = value
        elif isinstance(value, list):
            candidates = tuple(value)
        else:
            return ()
        return tuple(item for item in candidates if isinstance(item, str) and item)

    def _read_jsonl(
        self,
        path: Path,
        blocker_prefix: str,
    ) -> tuple[tuple[Mapping[str, object], ...], tuple[str, ...]]:
        absolute = path if path.is_absolute() else Path.cwd() / path
        if not absolute.exists():
            return (), ()
        try:
            if absolute.is_symlink() or absolute.stat().st_size > self.max_file_bytes:
                return (), (f"{blocker_prefix}_UNSAFE_OR_OVERSIZED",)
            rows: list[Mapping[str, object]] = []
            for line in absolute.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, Mapping):
                    rows.append(cast(Mapping[str, object], parsed))
                else:
                    return (), (f"{blocker_prefix}_INVALID",)
        except (OSError, json.JSONDecodeError):
            return (), (f"{blocker_prefix}_INVALID",)
        return tuple(rows), ()

    @staticmethod
    def _with_provider_blockers(
        payload: dict[str, object],
        blockers: tuple[str, ...],
    ) -> dict[str, object]:
        if not blockers:
            return payload
        updated = dict(payload)
        existing = RuntimeResearchContextLoader._text_sequence(
            updated.get("provider_blockers")
        )
        updated["provider_blockers"] = tuple(dict.fromkeys((*existing, *blockers)))
        return updated

    @staticmethod
    def _merge_news_snapshot(
        existing: dict[str, object],
        incoming: dict[str, object],
    ) -> dict[str, object]:
        existing_events = existing.get("high_impact_events")
        incoming_events = incoming.get("high_impact_events")
        existing_seq = RuntimeResearchContextLoader._mapping_sequence(existing_events)
        incoming_seq = RuntimeResearchContextLoader._mapping_sequence(incoming_events)

        merged: dict[str, Mapping[str, object]] = {}
        for raw in (*existing_seq, *incoming_seq):
            event_id = raw.get("event_id")
            if isinstance(event_id, str) and event_id.strip():
                merged[event_id] = raw

        merged_snapshot = dict(existing)
        merged_snapshot.update(incoming)
        merged_snapshot["high_impact_events"] = tuple(
            sorted(
                merged.values(),
                key=lambda item: (
                    str(item.get("scheduled_at", "")),
                    str(item.get("event_id", "")),
                ),
            )
        )

        blockers = [
            *RuntimeResearchContextLoader._text_sequence(
                existing.get("provider_blockers")
            ),
            *RuntimeResearchContextLoader._text_sequence(
                incoming.get("provider_blockers")
            ),
        ]
        merged_snapshot["provider_blockers"] = tuple(dict.fromkeys(blockers))
        return merged_snapshot


@dataclass(frozen=True, slots=True)
class RuntimeContextAcquirer:
    """Decorator that enriches acquired snapshots with local research context."""

    base_acquirer: SnapshotAcquirer
    context_loader: RuntimeResearchContextLoader

    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        acquired = self.base_acquirer.acquire(symbol, timeframes)
        return self.context_loader.attach(acquired)


class SnapshotAcquirer(Protocol):
    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        raise NotImplementedError
