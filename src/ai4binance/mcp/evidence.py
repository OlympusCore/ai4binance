"""Fail-closed, read-only access to bounded AI4BINANCE evidence artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from ai4binance.storage.jsonl import SecretRedactor

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class FreshnessStatus(StrEnum):
    """Trust state of evidence returned through the MCP boundary."""

    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """Allowlisted artifact contract; callers cannot supply arbitrary paths."""

    artifact_type: str
    relative_path: Path
    timestamp_field: str
    max_age: timedelta
    required_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.artifact_type.strip() or not self.timestamp_field.strip():
            raise ValueError("evidence source identity cannot be empty")
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("evidence source path must be relative and contained")
        if self.max_age <= timedelta(0):
            raise ValueError("evidence max_age must be positive")
        if not self.required_fields or len(set(self.required_fields)) != len(
            self.required_fields
        ):
            raise ValueError("required evidence fields must be non-empty and unique")


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    """Advisory-only envelope that can never grant execution authority."""

    artifact_type: str
    generated_at: datetime
    source_artifact: str
    source_sha256: str
    freshness_status: FreshnessStatus
    blockers: tuple[str, ...]
    data: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "1.0"
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.artifact_type.strip() or not self.source_artifact.strip():
            raise ValueError("evidence envelope identity cannot be empty")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("evidence timestamp must be timezone-aware")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("evidence source hash is invalid")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("MCP evidence cannot promote or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("MCP evidence must remain live blocked")
        if self.freshness_status is not FreshnessStatus.FRESH and not self.blockers:
            raise ValueError("degraded MCP evidence requires blockers")


QUALITY_TRIAGE_SOURCE = EvidenceSource(
    artifact_type="quality_triage",
    relative_path=Path("quality-triage/state.json"),
    timestamp_field="finished_at",
    max_age=timedelta(hours=36),
    required_fields=(
        "run_id",
        "finished_at",
        "revision",
        "status",
        "blockers",
        "execution_allowed",
        "live_eligibility_status",
    ),
)

MARKET_OUTLOOK_SOURCE = EvidenceSource(
    artifact_type="market_outlook",
    relative_path=Path("market-outlook/state.json"),
    timestamp_field="timestamp",
    max_age=timedelta(hours=2),
    required_fields=(
        "snapshot_id",
        "symbol",
        "timestamp",
        "status",
        "blockers",
        "execution_allowed",
        "live_eligibility_status",
    ),
)


@dataclass(slots=True)
class EvidenceGateway:
    """Read only allowlisted JSON evidence with provenance and freshness checks."""

    artifact_root: Path
    max_artifact_bytes: int = 1_000_000
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.max_artifact_bytes <= 0:
            raise ValueError("max_artifact_bytes must be positive")
        self.artifact_root = self.artifact_root.resolve()

    def health_check(self) -> EvidenceEnvelope:
        """Return static server capabilities without touching trading state."""
        data: Mapping[str, object] = {
            "service": "ai4binance-read-only-evidence-mcp",
            "transport": "stdio",
            "tools": (
                "health_check",
                "get_quality_triage",
                "get_market_outlook",
                "get_research_blockers",
            ),
            "read_only": True,
        }
        digest = hashlib.sha256(
            json.dumps(data, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return EvidenceEnvelope(
            artifact_type="mcp_health",
            generated_at=self._now(),
            source_artifact="embedded://mcp/capabilities",
            source_sha256=digest,
            freshness_status=FreshnessStatus.FRESH,
            blockers=(),
            data=data,
        )

    def get_quality_triage(self) -> EvidenceEnvelope:
        """Return the most recent bounded nightly quality report."""
        return self.read(QUALITY_TRIAGE_SOURCE)

    def get_market_outlook(self) -> EvidenceEnvelope:
        """Return the most recent persisted deterministic market outlook."""
        return self.read(MARKET_OUTLOOK_SOURCE)

    def get_research_blockers(self) -> EvidenceEnvelope:
        """Aggregate blockers without creating a signal or execution decision."""
        evidence = (self.get_quality_triage(), self.get_market_outlook())
        blockers = tuple(
            sorted({item for report in evidence for item in report.blockers})
        )
        statuses = {report.freshness_status for report in evidence}
        freshness = self._aggregate_freshness(statuses)
        summaries: Mapping[str, object] = {
            report.artifact_type: {
                "freshness_status": report.freshness_status.value,
                "source_sha256": report.source_sha256,
                "blockers": report.blockers,
            }
            for report in evidence
        }
        combined_hash = hashlib.sha256(
            "".join(report.source_sha256 for report in evidence).encode("ascii")
        ).hexdigest()
        return EvidenceEnvelope(
            artifact_type="research_blockers",
            generated_at=self._now(),
            source_artifact="aggregate://quality-triage,market-outlook",
            source_sha256=combined_hash,
            freshness_status=freshness,
            blockers=blockers,
            data=summaries,
        )

    def read(self, source: EvidenceSource) -> EvidenceEnvelope:
        """Read one predefined source and reject unsafe or malformed evidence."""
        path = (self.artifact_root / source.relative_path).resolve()
        source_name = source.relative_path.as_posix()
        if not self._is_contained(path):
            return self._degraded(source, source_name, "EVIDENCE_PATH_OUTSIDE_ROOT")
        if path.is_symlink():
            return self._degraded(source, source_name, "EVIDENCE_SYMLINK_BLOCKED")
        if not path.is_file():
            return self._degraded(
                source,
                source_name,
                "EVIDENCE_ARTIFACT_MISSING",
                FreshnessStatus.MISSING,
            )
        if path.stat().st_size > self.max_artifact_bytes:
            return self._degraded(source, source_name, "EVIDENCE_ARTIFACT_TOO_LARGE")
        try:
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            parsed = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return self._degraded(source, source_name, "EVIDENCE_ARTIFACT_INVALID")
        if not isinstance(parsed, dict):
            return self._degraded(
                source,
                source_name,
                "EVIDENCE_SCHEMA_INVALID",
                source_sha256=digest,
            )
        data: dict[str, object] = parsed
        if any(field_name not in data for field_name in source.required_fields):
            return self._degraded(
                source,
                source_name,
                "EVIDENCE_SCHEMA_INVALID",
                source_sha256=digest,
            )
        if (
            data.get("execution_allowed") is not False
            or data.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            return self._degraded(
                source,
                source_name,
                "EVIDENCE_AUTHORITY_VIOLATION",
                source_sha256=digest,
            )
        timestamp = self._parse_timestamp(data.get(source.timestamp_field))
        if timestamp is None or timestamp > self._now() + timedelta(minutes=5):
            return self._degraded(
                source,
                source_name,
                "EVIDENCE_TIMESTAMP_INVALID",
                source_sha256=digest,
            )
        artifact_blockers = self._artifact_blockers(data.get("blockers"))
        if artifact_blockers is None:
            return self._degraded(
                source,
                source_name,
                "EVIDENCE_BLOCKERS_INVALID",
                source_sha256=digest,
            )
        stale = self._now() - timestamp > source.max_age
        freshness_blockers = ("EVIDENCE_STALE",) if stale else ()
        redacted = SecretRedactor().redact(data)
        if not isinstance(redacted, Mapping):
            raise RuntimeError("secret redactor changed evidence mapping shape")
        return EvidenceEnvelope(
            artifact_type=source.artifact_type,
            generated_at=self._now(),
            source_artifact=source_name,
            source_sha256=digest,
            freshness_status=(
                FreshnessStatus.STALE if stale else FreshnessStatus.FRESH
            ),
            blockers=tuple(dict.fromkeys((*artifact_blockers, *freshness_blockers))),
            data=redacted,
        )

    def _degraded(
        self,
        source: EvidenceSource,
        source_name: str,
        blocker: str,
        status: FreshnessStatus = FreshnessStatus.INVALID,
        *,
        source_sha256: str = _EMPTY_SHA256,
    ) -> EvidenceEnvelope:
        return EvidenceEnvelope(
            artifact_type=source.artifact_type,
            generated_at=self._now(),
            source_artifact=source_name,
            source_sha256=source_sha256,
            freshness_status=status,
            blockers=(blocker,),
        )

    def _is_contained(self, path: Path) -> bool:
        try:
            return os.path.commonpath((self.artifact_root, path)) == str(
                self.artifact_root
            )
        except ValueError:
            return False

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence gateway clock must be timezone-aware")
        return value

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

    @staticmethod
    def _artifact_blockers(value: object) -> tuple[str, ...] | None:
        if not isinstance(value, list) or len(value) > 128:
            return None
        if any(
            not isinstance(item, str) or not item.strip() or len(item) > 200
            for item in value
        ):
            return None
        return tuple(value)

    @staticmethod
    def _aggregate_freshness(
        statuses: set[FreshnessStatus],
    ) -> FreshnessStatus:
        for status in (
            FreshnessStatus.INVALID,
            FreshnessStatus.MISSING,
            FreshnessStatus.STALE,
        ):
            if status in statuses:
                return status
        return FreshnessStatus.FRESH
