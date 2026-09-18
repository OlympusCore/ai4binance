"""Persistent human-governed lesson lifecycle reconciliation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ai4binance.learning.governance import (
    GovernedLesson,
    LessonStatus,
    stage_learning_summary,
)
from ai4binance.learning.models import LearningSummary
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class LessonTransitionRequest:
    """One explicit local transition request with no production authority."""

    lesson_id: str
    target_status: LessonStatus
    validation_artifact_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    human_approved: bool = False


@dataclass(frozen=True, slots=True)
class GovernedLessonLifecycleStore:
    """Persist governed lessons and append immutable local lifecycle audit events."""

    lessons_path: Path
    audit_path: Path

    def load(self) -> tuple[GovernedLesson, ...]:
        if not self.lessons_path.exists():
            return ()
        payload = json.loads(self.lessons_path.read_text(encoding="utf-8"))
        items = payload.get("lessons") if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            raise ValueError("governed lesson store payload is invalid")
        return tuple(_lesson_from_mapping(item) for item in items)

    def save(self, lessons: tuple[GovernedLesson, ...], *, at: datetime) -> None:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("lesson lifecycle timestamp must be timezone-aware")
        if len({lesson.lesson_id for lesson in lessons}) != len(lessons):
            raise ValueError("governed lesson IDs must be unique")
        primitive = {
            "schema_version": "1.0.0",
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "lessons": to_primitive(lessons),
        }
        write_json_object_verified(
            self.lessons_path,
            primitive,
            blocker="GOVERNED_LESSON_LIFECYCLE_DESTINATION_VERIFY_FAILED",
            subject_id="governed-lesson-lifecycle",
            indent=2,
        )
        audit_store = JsonlAuditStore(
            self.audit_path,
            durable=True,
            tamper_evident=True,
        )
        audit_store.append_verified(
            AuditEvent(
                event_type="GOVERNED_LESSON_LIFECYCLE_PERSISTED",
                timestamp=at,
                payload=primitive,
                snapshot_id="governed-lesson-lifecycle",
            )
        )


@dataclass(frozen=True, slots=True)
class GovernedLessonLifecycleWorker:
    """Stage, explicitly transition, and expire lessons without approving them."""

    store: GovernedLessonLifecycleStore
    expiry_window: timedelta = timedelta(days=30)

    def __post_init__(self) -> None:
        if self.expiry_window <= timedelta(0):
            raise ValueError("lesson expiry window must be positive")

    def reconcile(
        self,
        summary: LearningSummary,
        *,
        at: datetime,
        transitions: Iterable[LessonTransitionRequest] = (),
    ) -> tuple[GovernedLesson, ...]:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("lesson reconciliation timestamp must be timezone-aware")
        lessons = {item.lesson_id: item for item in self.store.load()}
        changed = False
        for item in stage_learning_summary(
            summary,
            expires_at=summary.created_at + self.expiry_window,
        ):
            if item.lesson_id not in lessons:
                lessons[item.lesson_id] = item
                changed = True
        for request in transitions:
            current = lessons.get(request.lesson_id)
            if current is None:
                raise ValueError("lesson transition references an unknown lesson")
            updated = current.transition(
                request.target_status,
                at=at,
                validation_artifact_ids=request.validation_artifact_ids,
                blockers=request.blockers,
                human_approved=request.human_approved,
            )
            lessons[request.lesson_id] = updated
            changed = changed or updated != current
        for lesson_id, current in tuple(lessons.items()):
            terminal = current.status in {LessonStatus.EXPIRED, LessonStatus.REJECTED}
            if not terminal and at >= current.expires_at:
                lessons[lesson_id] = current.transition(
                    LessonStatus.EXPIRED,
                    at=at,
                    blockers=("LESSON_EXPIRED",),
                )
                changed = True
        reconciled = tuple(lessons[key] for key in sorted(lessons))
        if changed:
            self.store.save(reconciled, at=at)
        return reconciled


def _lesson_from_mapping(value: object) -> GovernedLesson:
    if not isinstance(value, Mapping):
        raise ValueError("governed lesson record is invalid")
    try:
        return GovernedLesson(
            lesson_id=_text(value, "lesson_id"),
            code=_text(value, "code"),
            rationale=_text(value, "rationale"),
            evidence_count=_integer(value, "evidence_count"),
            source_artifact_ids=_texts(value, "source_artifact_ids"),
            observed_at=_timestamp(value, "observed_at"),
            expires_at=_timestamp(value, "expires_at"),
            status=LessonStatus(_text(value, "status")),
            validation_artifact_ids=_texts(value, "validation_artifact_ids"),
            blockers=_texts(value, "blockers"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("governed lesson record is invalid") from error


def _text(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(key)
    return item


def _texts(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key, ())
    if not isinstance(item, list) or any(not isinstance(part, str) for part in item):
        raise ValueError(key)
    return tuple(item)


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(key)
    return item


def _timestamp(value: Mapping[str, object], key: str) -> datetime:
    item = _text(value, key)
    parsed = datetime.fromisoformat(item.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(key)
    return parsed
