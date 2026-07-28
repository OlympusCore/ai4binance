"""Append-only local approval queue for separately gated content publishing."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from ai4binance.content.models import ContentDraft, DraftQueueStatus
from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore, SecretRedactor

_EVENT_TO_STATE = {
    "CONTENT_DRAFT_QUEUED": DraftQueueStatus.REVIEW_REQUIRED,
    "CONTENT_DRAFT_APPROVED": DraftQueueStatus.APPROVED,
    "CONTENT_DRAFT_REJECTED": DraftQueueStatus.REJECTED,
    "CONTENT_DRAFT_EXPIRED": DraftQueueStatus.EXPIRED,
}
_APPROVAL_CONFIRMATION = "APPROVE_LOCAL_DRAFT"
_SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_ -]?key|secret|token|password|authorization)\s*[:=]",
    re.IGNORECASE,
)


@dataclass(slots=True)
class LocalApprovalQueue:
    """Persist review decisions locally without any X publishing adapter."""

    path: Path
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    max_queue_bytes: int = 5_000_000
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_queue_bytes <= 0:
            raise ValueError("max_queue_bytes must be positive")

    def enqueue(self, draft: ContentDraft) -> bool:
        """Append a compliant draft once; return False for an exact duplicate."""
        with self._lock:
            states = self._replay()
            if draft.draft_id in states:
                return False
            self._append(
                "CONTENT_DRAFT_QUEUED",
                draft.draft_id,
                {"draft": to_primitive(draft)},
            )
            return True

    def approve(
        self,
        draft_id: str,
        *,
        approved_by: str,
        rationale: str,
        confirmation: str,
    ) -> None:
        """Record explicit local human approval; publishing remains impossible."""
        if confirmation != _APPROVAL_CONFIRMATION:
            raise ValueError("explicit local approval confirmation is required")
        self._transition(
            draft_id,
            DraftQueueStatus.APPROVED,
            actor=approved_by,
            rationale=rationale,
        )

    def reject(self, draft_id: str, *, rejected_by: str, rationale: str) -> None:
        """Reject one pending draft with an auditable reason."""
        self._transition(
            draft_id,
            DraftQueueStatus.REJECTED,
            actor=rejected_by,
            rationale=rationale,
        )

    def expire(self, draft_id: str, *, rationale: str) -> None:
        """Expire one pending draft without human approval or publishing."""
        self._transition(
            draft_id,
            DraftQueueStatus.EXPIRED,
            actor="system",
            rationale=rationale,
        )

    def status(self, draft_id: str) -> DraftQueueStatus | None:
        """Return current state after strict replay of the append-only log."""
        with self._lock:
            return self._replay().get(draft_id)

    def pending_ids(self) -> tuple[str, ...]:
        """Return pending identifiers in deterministic lexical order."""
        with self._lock:
            states = self._replay()
        return tuple(
            sorted(
                draft_id
                for draft_id, status in states.items()
                if status is DraftQueueStatus.REVIEW_REQUIRED
            )
        )

    def approved_draft_matches(self, draft: ContentDraft) -> bool:
        """Verify approval belongs to the exact immutable queued draft."""
        expected = to_primitive(draft)
        with self._lock:
            states = self._replay()
            if states.get(draft.draft_id) is not DraftQueueStatus.APPROVED:
                return False
            for line in self.path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if (
                    event.get("event_type") == "CONTENT_DRAFT_QUEUED"
                    and event.get("snapshot_id") == draft.draft_id
                ):
                    return bool(event["payload"].get("draft") == expected)
        return False

    def _transition(
        self,
        draft_id: str,
        target: DraftQueueStatus,
        *,
        actor: str,
        rationale: str,
    ) -> None:
        self._validate_identity(draft_id)
        clean_actor = self._bounded_text(actor, "actor", 80)
        clean_rationale = self._bounded_text(rationale, "rationale", 240)
        with self._lock:
            current = self._replay().get(draft_id)
            if current is None:
                raise KeyError("content draft not found")
            if current is not DraftQueueStatus.REVIEW_REQUIRED:
                raise ValueError("content draft is no longer pending review")
            event_type = {
                DraftQueueStatus.APPROVED: "CONTENT_DRAFT_APPROVED",
                DraftQueueStatus.REJECTED: "CONTENT_DRAFT_REJECTED",
                DraftQueueStatus.EXPIRED: "CONTENT_DRAFT_EXPIRED",
            }.get(target)
            if event_type is None:
                raise ValueError("unsupported content queue transition")
            self._append(
                event_type,
                draft_id,
                {"actor": clean_actor, "rationale": clean_rationale},
            )

    def _append(
        self, event_type: str, draft_id: str, payload: Mapping[str, object]
    ) -> None:
        self._validate_identity(draft_id)
        event = AuditEvent(
            event_type=event_type,
            timestamp=self._now(),
            snapshot_id=draft_id,
            payload={
                **payload,
                "publish_allowed": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
        )
        JsonlAuditStore(self.path, redactor=SecretRedactor()).append_verified(event)

    def _replay(self) -> dict[str, DraftQueueStatus]:
        if not self.path.exists():
            return {}
        if self.path.is_symlink():
            raise ValueError("content queue symlink is blocked")
        if self.path.stat().st_size > self.max_queue_bytes:
            raise ValueError("content queue exceeds bounded size")
        states: dict[str, DraftQueueStatus] = {}
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"content queue line {line_number} is invalid"
                ) from error
            if not isinstance(event, Mapping):
                raise ValueError(f"content queue line {line_number} is invalid")
            event_type = event.get("event_type")
            draft_id = event.get("snapshot_id")
            payload = event.get("payload")
            timestamp = event.get("timestamp")
            if (
                not isinstance(event_type, str)
                or event_type not in _EVENT_TO_STATE
                or not isinstance(draft_id, str)
                or not isinstance(payload, Mapping)
                or self._parse_timestamp(timestamp) is None
            ):
                raise ValueError(f"content queue line {line_number} is invalid")
            self._validate_identity(draft_id)
            if (
                payload.get("publish_allowed") is not False
                or payload.get("execution_allowed") is not False
                or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
            ):
                raise ValueError("content queue authority violation")
            target = _EVENT_TO_STATE[event_type]
            current = states.get(draft_id)
            if event_type == "CONTENT_DRAFT_QUEUED":
                queued_draft = payload.get("draft")
                if (
                    current is not None
                    or not isinstance(queued_draft, Mapping)
                    or queued_draft.get("draft_id") != draft_id
                    or queued_draft.get("publish_allowed") is not False
                    or queued_draft.get("execution_allowed") is not False
                    or queued_draft.get("live_eligibility_status")
                    != "LIVE_ORDER_BLOCKED"
                ):
                    raise ValueError("content queue duplicate or malformed draft event")
            elif current is not DraftQueueStatus.REVIEW_REQUIRED:
                raise ValueError("content queue contains an invalid transition")
            states[draft_id] = target
        return states

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("content queue clock must be timezone-aware")
        return value

    @staticmethod
    def _validate_identity(draft_id: str) -> None:
        if len(draft_id) != 64 or any(
            character not in "0123456789abcdef" for character in draft_id
        ):
            raise ValueError("content draft id is invalid")

    @staticmethod
    def _bounded_text(value: str, name: str, limit: int) -> str:
        compact = " ".join(value.split())
        if not compact or len(compact) > limit:
            raise ValueError(f"content queue {name} is invalid")
        if _SECRET_LIKE_PATTERN.search(compact):
            raise ValueError(f"content queue {name} contains secret-like text")
        return compact

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed
