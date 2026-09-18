"""Append-only intent and outcome audit for social publishing."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai4binance.content.publishing_models import (
    PublishReceipt,
    PublishStatus,
    SocialPlatform,
)
from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import fail_verification
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class PublishAttemptState:
    """Replayed state used to prevent duplicate or uncertain sends."""

    intent_exists: bool
    outcome: PublishStatus | None
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class PublishAuditStore:
    """Persist intent before network I/O and result after response validation."""

    path: Path
    maximum_bytes: int = 5_000_000

    def begin(
        self,
        *,
        request_id: str,
        draft_id: str,
        platform: SocialPlatform,
        requested_by: str,
        timestamp: datetime,
    ) -> None:
        if self.attempt(request_id) is not None:
            raise ValueError("publishing request already has an audit event")
        self._append(
            "SOCIAL_PUBLISH_INTENT",
            request_id,
            timestamp,
            {
                "draft_id": draft_id,
                "platform": platform.value,
                "requested_by": requested_by,
            },
        )
        observed = self.attempt(request_id)
        if (
            observed is None
            or not observed.intent_exists
            or observed.outcome is not None
        ):
            raise fail_verification(
                "SOCIAL_PUBLISH_INTENT_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=request_id,
            )

    def complete(self, receipt: PublishReceipt) -> None:
        state = self.attempt(receipt.request_id)
        if state is None or not state.intent_exists or state.outcome is not None:
            raise ValueError("publishing outcome has no open intent")
        event_type = (
            "SOCIAL_PUBLISH_SUCCEEDED"
            if receipt.status is PublishStatus.PUBLISHED
            else "SOCIAL_PUBLISH_FAILED"
        )
        self._append(
            event_type,
            receipt.request_id,
            receipt.requested_at,
            {"receipt": to_primitive(receipt)},
        )
        observed = self.attempt(receipt.request_id)
        expected = (
            PublishStatus.PUBLISHED
            if event_type == "SOCIAL_PUBLISH_SUCCEEDED"
            else PublishStatus.FAILED
        )
        if observed is None or observed.outcome is not expected:
            raise fail_verification(
                "SOCIAL_PUBLISH_OUTCOME_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=receipt.request_id,
            )

    def attempt(self, request_id: str) -> PublishAttemptState | None:
        events = self._events()
        state: PublishAttemptState | None = None
        for event in events:
            if event["snapshot_id"] != request_id:
                continue
            timestamp = self._timestamp(event["timestamp"])
            event_type = event["event_type"]
            if event_type == "SOCIAL_PUBLISH_INTENT":
                if state is not None:
                    raise ValueError("duplicate social publishing intent")
                state = PublishAttemptState(True, None, timestamp)
            else:
                if state is None or state.outcome is not None:
                    raise ValueError("invalid social publishing audit transition")
                outcome = (
                    PublishStatus.PUBLISHED
                    if event_type == "SOCIAL_PUBLISH_SUCCEEDED"
                    else PublishStatus.FAILED
                )
                state = PublishAttemptState(True, outcome, timestamp)
        return state

    def latest_success(self, platform: SocialPlatform) -> datetime | None:
        latest: datetime | None = None
        for event in self._events():
            if event["event_type"] != "SOCIAL_PUBLISH_SUCCEEDED":
                continue
            payload = event["payload"]
            if not isinstance(payload, Mapping):
                raise ValueError("social publishing audit payload is invalid")
            receipt = payload.get("receipt")
            if (
                isinstance(receipt, Mapping)
                and receipt.get("platform") == platform.value
            ):
                timestamp = self._timestamp(event["timestamp"])
                latest = timestamp if latest is None else max(latest, timestamp)
        return latest

    def _append(
        self,
        event_type: str,
        request_id: str,
        timestamp: datetime,
        payload: Mapping[str, object],
    ) -> None:
        JsonlAuditStore(self.path, durable=True).append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=timestamp,
                snapshot_id=request_id,
                payload=payload,
            )
        )

    def _events(self) -> tuple[Mapping[str, object], ...]:
        if not self.path.exists():
            return ()
        if self.path.is_symlink() or self.path.stat().st_size > self.maximum_bytes:
            raise ValueError("social publishing audit is unsafe or oversized")
        events: list[Mapping[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            parsed = json.loads(line)
            if (
                not isinstance(parsed, Mapping)
                or parsed.get("event_type")
                not in {
                    "SOCIAL_PUBLISH_INTENT",
                    "SOCIAL_PUBLISH_SUCCEEDED",
                    "SOCIAL_PUBLISH_FAILED",
                }
                or not isinstance(parsed.get("snapshot_id"), str)
                or not isinstance(parsed.get("payload"), Mapping)
            ):
                raise ValueError("social publishing audit event is invalid")
            self._timestamp(parsed.get("timestamp"))
            events.append(parsed)
        return tuple(events)

    @staticmethod
    def _timestamp(value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("social publishing audit timestamp is invalid")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("social publishing audit timestamp is invalid") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("social publishing audit timestamp is invalid")
        return parsed
