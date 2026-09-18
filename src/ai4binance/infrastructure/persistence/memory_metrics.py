"""Runtime evidence writer for governed memory metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.domain.memory_metrics import MemoryRuntimeMetricsSnapshot
from ai4binance.infrastructure.persistence.safe_json import (
    AuditEvent,
    JsonlAuditStore,
    VerifiedWriteResult,
    write_json_object_verified,
)


@dataclass(frozen=True, slots=True)
class MemoryRuntimeMetricsEvidenceRecord:
    """Report-only memory metrics evidence; never authority-bearing."""

    record_id: str
    observed_at: datetime
    metrics: MemoryRuntimeMetricsSnapshot
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("memory metrics evidence record id is required")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("memory metrics evidence timestamp must be timezone-aware")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("memory metrics evidence cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "observed_at": self.observed_at.isoformat(),
            "metrics": self.metrics.to_payload(),
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


@dataclass(frozen=True, slots=True)
class MemoryRuntimeMetricsWriteResult:
    record: MemoryRuntimeMetricsEvidenceRecord
    ledger_write: VerifiedWriteResult
    latest_json_write: VerifiedWriteResult
    latest_markdown_path: Path


@dataclass(frozen=True, slots=True)
class MemoryRuntimeMetricsEvidenceWriter:
    """Persist latest memory metrics evidence under runtime paths."""

    repository_root: Path
    durable: bool = True

    @property
    def ledger_path(self) -> Path:
        return (
            self.repository_root
            / "runtime"
            / "state"
            / "memory"
            / "memory-runtime-metrics.jsonl"
        )

    @property
    def latest_json_path(self) -> Path:
        return (
            self.repository_root
            / "runtime"
            / "artifacts"
            / "context"
            / "memory"
            / "memory_runtime_metrics_latest.json"
        )

    @property
    def latest_markdown_path(self) -> Path:
        return (
            self.repository_root
            / "runtime"
            / "reports"
            / "audit"
            / "memory_runtime_metrics_latest.md"
        )

    def write(
        self,
        metrics: MemoryRuntimeMetricsSnapshot,
        *,
        observed_at: datetime | None = None,
    ) -> MemoryRuntimeMetricsWriteResult:
        observed = observed_at or datetime.now(UTC)
        record = MemoryRuntimeMetricsEvidenceRecord(
            record_id=f"memory-runtime-metrics:{observed.isoformat()}",
            observed_at=observed,
            metrics=metrics,
        )
        payload = record.to_payload()
        ledger_write = JsonlAuditStore(
            self.ledger_path,
            durable=self.durable,
            tamper_evident=True,
        ).append_verified(
            AuditEvent(
                event_type="MEMORY_RUNTIME_METRICS",
                timestamp=record.observed_at,
                payload=payload,
                snapshot_id=record.record_id,
            )
        )
        latest_json_write = write_json_object_verified(
            self.latest_json_path,
            payload,
            blocker="MEMORY_RUNTIME_METRICS_LATEST_DESTINATION_VERIFY_FAILED",
            subject_id=record.record_id,
            indent=2,
            durable=self.durable,
        )
        self.latest_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        self.latest_markdown_path.write_text(
            render_memory_runtime_metrics_markdown(record),
            encoding="utf-8",
        )
        return MemoryRuntimeMetricsWriteResult(
            record=record,
            ledger_write=ledger_write,
            latest_json_write=latest_json_write,
            latest_markdown_path=self.latest_markdown_path,
        )


def render_memory_runtime_metrics_markdown(
    record: MemoryRuntimeMetricsEvidenceRecord,
) -> str:
    metrics = record.metrics
    return "\n".join(
        (
            "# Memory Runtime Metrics Evidence",
            "",
            "## ELI10",
            "",
            (
                "This report records governed memory runtime health for audit. "
                "It is evidence only and cannot authorize trading."
            ),
            "",
            "## Metrics",
            "",
            f"- memory_compile_latency_p50: `{metrics.memory_compile_latency_p50}`",
            f"- memory_compile_latency_p95: `{metrics.memory_compile_latency_p95}`",
            f"- memory_retrieval_latency_p95: `{metrics.memory_retrieval_latency_p95}`",
            f"- compiled_context_bytes: `{metrics.compiled_context_bytes}`",
            (
                "- compiled_context_token_estimate: "
                f"`{metrics.compiled_context_token_estimate}`"
            ),
            f"- active_memory_count: `{metrics.active_memory_count}`",
            f"- candidate_memory_count: `{metrics.candidate_memory_count}`",
            f"- memory_conflict_rate: `{metrics.memory_conflict_rate}`",
            f"- stale_memory_rate: `{metrics.stale_memory_rate}`",
            f"- duplicate_rejection_rate: `{metrics.duplicate_rejection_rate}`",
            f"- promotion_rejection_rate: `{metrics.promotion_rejection_rate}`",
            f"- event_count: `{metrics.event_count}`",
            "",
            "## Governance",
            "",
            f"- execution_allowed: `{record.execution_allowed}`",
            f"- promotion_status: `{record.promotion_status}`",
            f"- live_eligibility_status: `{record.live_eligibility_status}`",
            "",
        )
    )
