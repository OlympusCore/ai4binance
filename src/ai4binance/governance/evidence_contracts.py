"""Schema-bound artifact evidence readers for governed AI4BINANCE reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai4binance.storage import SecretRedactor

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_SOURCES = {
    "quality_triage": (
        Path("Artifacts/quality-triage/state.json"),
        "finished_at",
        ("run_id", "finished_at", "revision", "status", "blockers"),
        120,
    ),
    "market_outlook": (
        Path("Artifacts/market-outlook/state.json"),
        "timestamp",
        ("snapshot_id", "symbol", "timestamp", "status", "blockers"),
        60,
    ),
}


@dataclass(frozen=True, slots=True)
class GovernedArtifactEvidence:
    artifact_type: str
    generated_at: datetime
    source_artifact: str
    source_sha256: str
    freshness_status: str
    blockers: tuple[str, ...]
    data: dict[str, object] | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.artifact_type.strip() or not self.source_artifact.strip():
            raise ValueError("artifact evidence identity is required")
        if self.generated_at.tzinfo is None:
            raise ValueError("artifact evidence timestamp must be timezone-aware")
        if len(self.source_sha256) != 64:
            raise ValueError("artifact evidence source hash is invalid")
        if self.freshness_status not in {"FRESH", "STALE", "MISSING", "INVALID"}:
            raise ValueError("artifact evidence freshness status is invalid")
        if not self.blockers and self.freshness_status != "FRESH":
            raise ValueError("degraded artifact evidence requires blockers")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("artifact evidence cannot authorize trading")


@dataclass(frozen=True, slots=True)
class GovernedArtifactReader:
    repository_root: Path
    maximum_bytes: int = 200_000
    clock: Callable[[], datetime] | None = None

    def read(self, artifact_type: str) -> GovernedArtifactEvidence:
        if artifact_type not in _SOURCES:
            raise ValueError("unknown governed artifact type")
        relative_path, timestamp_field, required_fields, max_age_minutes = _SOURCES[
            artifact_type
        ]
        now = self._now()
        source = self.repository_root / relative_path
        source_name = relative_path.as_posix()
        blocker_prefix = artifact_type.upper()
        if source.is_symlink():
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_SYMLINK_REJECTED",
            )
        try:
            resolved_root = self.repository_root.resolve(strict=True)
            resolved_source = source.resolve(strict=True)
            resolved_source.relative_to(resolved_root)
        except FileNotFoundError:
            return _degraded(
                artifact_type,
                source_name,
                now,
                "MISSING",
                f"{blocker_prefix}_MISSING",
            )
        except ValueError:
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_OUTSIDE_ROOT",
            )
        if not resolved_source.is_file():
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_NOT_FILE",
            )
        size = resolved_source.stat().st_size
        if size > self.maximum_bytes:
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_TOO_LARGE",
            )
        raw = resolved_source.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_INVALID_JSON",
                source_hash,
            )
        if not isinstance(payload, dict) or any(
            field not in payload for field in required_fields
        ):
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_SCHEMA_INVALID",
                source_hash,
            )
        blockers = payload.get("blockers")
        if not isinstance(blockers, list) or not all(
            isinstance(item, str) for item in blockers
        ):
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_BLOCKERS_INVALID",
                source_hash,
            )
        if (
            payload.get("execution_allowed") is not False
            or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_UNSAFE_AUTHORITY",
                source_hash,
            )
        try:
            observed_at = _parse_datetime(payload[timestamp_field])
        except (TypeError, ValueError):
            return _degraded(
                artifact_type,
                source_name,
                now,
                "INVALID",
                f"{blocker_prefix}_TIMESTAMP_INVALID",
                source_hash,
            )
        normalized_blockers = tuple(blockers)
        freshness = "FRESH"
        age = now - observed_at
        if age < timedelta(0) or age > timedelta(minutes=max_age_minutes):
            freshness = "STALE"
            normalized_blockers = (*normalized_blockers, f"{blocker_prefix}_STALE")
        safe_payload = SecretRedactor().redact(payload)
        if not isinstance(safe_payload, dict):
            raise RuntimeError("ARTIFACT_REDACTION_CONTRACT_VIOLATION")
        return GovernedArtifactEvidence(
            artifact_type=artifact_type,
            generated_at=now,
            source_artifact=source_name,
            source_sha256=source_hash,
            freshness_status=freshness,
            blockers=normalized_blockers,
            data=safe_payload,
        )

    def collect_default(self) -> tuple[GovernedArtifactEvidence, ...]:
        return tuple(self.read(artifact_type) for artifact_type in sorted(_SOURCES))

    def _now(self) -> datetime:
        now = self.clock() if self.clock is not None else datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("artifact reader clock must return timezone-aware time")
        return now.astimezone(UTC)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)


def _degraded(
    artifact_type: str,
    source_artifact: str,
    generated_at: datetime,
    freshness_status: str,
    blocker: str,
    source_sha256: str = _EMPTY_SHA256,
) -> GovernedArtifactEvidence:
    return GovernedArtifactEvidence(
        artifact_type=artifact_type,
        generated_at=generated_at,
        source_artifact=source_artifact,
        source_sha256=source_sha256,
        freshness_status=freshness_status,
        blockers=(blocker,),
    )
