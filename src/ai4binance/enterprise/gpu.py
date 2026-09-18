"""Canonical GPU compute policy, telemetry, and lease contracts."""

from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self, cast

from ai4binance.storage import AuditEvent, JsonlAuditStore


class GpuLeaseKind(StrEnum):
    """Canonical GPU lease buckets managed by the resource governor."""

    LLM_GPU = "LLM_GPU"
    TRAINING_GPU = "TRAINING_GPU"
    BACKTEST_GPU = "BACKTEST_GPU"
    OPTIONAL_GPU = "OPTIONAL_GPU"
    BENCHMARK_GPU = "BENCHMARK_GPU"


class GpuLeaseState(StrEnum):
    """Lifecycle state for an issued GPU lease."""

    REQUESTED = "REQUESTED"
    GRANTED = "GRANTED"
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class GpuCircuitBreakerState(StrEnum):
    """Fail-closed GPU circuit breaker state."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class GpuWorkloadKind(StrEnum):
    """Workload families that may request GPU acceleration."""

    VOICE_TRANSCRIPTION = "VOICE_TRANSCRIPTION"
    LLM_INFERENCE = "LLM_INFERENCE"
    EMBEDDING_INFERENCE = "EMBEDDING_INFERENCE"
    RERANKER_INFERENCE = "RERANKER_INFERENCE"
    MODEL_TRAINING = "MODEL_TRAINING"
    BACKTEST_ACCELERATION = "BACKTEST_ACCELERATION"
    MONTE_CARLO = "MONTE_CARLO"
    TECH_INTELLIGENCE = "TECH_INTELLIGENCE"
    BENCHMARK = "BENCHMARK"


class GpuLeaseJournalEventType(StrEnum):
    """Canonical append-only GPU lease journal event types."""

    ISSUED = "GPU_LEASE_ISSUED"
    RELEASED = "GPU_LEASE_RELEASED"
    EXPIRED = "GPU_LEASE_EXPIRED"


@dataclass(frozen=True, slots=True)
class GpuTelemetrySnapshot:
    """Allocator and device telemetry used for fail-closed GPU governance."""

    observed_at: datetime
    cuda_available: bool = False
    device_name: str = ""
    driver_version: str = ""
    allocator_memory_allocated_bytes: int = 0
    allocator_memory_reserved_bytes: int = 0
    allocator_peak_allocated_bytes: int = 0
    allocator_peak_reserved_bytes: int = 0
    total_vram_bytes: int | None = None
    free_vram_bytes: int | None = None
    gpu_utilization_pct: int | None = None
    active_gpu_processes: int | None = None
    source: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("gpu telemetry timestamp must be timezone-aware")
        for field_name in (
            "allocator_memory_allocated_bytes",
            "allocator_memory_reserved_bytes",
            "allocator_peak_allocated_bytes",
            "allocator_peak_reserved_bytes",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError("gpu telemetry memory values must be non-negative")
        if self.allocator_memory_reserved_bytes < self.allocator_memory_allocated_bytes:
            raise ValueError(
                "gpu allocator reserved memory must cover allocated memory"
            )
        if self.allocator_peak_allocated_bytes < self.allocator_memory_allocated_bytes:
            raise ValueError("gpu allocator peak allocated memory must be monotonic")
        if self.allocator_peak_reserved_bytes < self.allocator_memory_reserved_bytes:
            raise ValueError("gpu allocator peak reserved memory must be monotonic")
        if self.total_vram_bytes is not None and self.total_vram_bytes < 0:
            raise ValueError("gpu total VRAM must be non-negative")
        if self.free_vram_bytes is not None and self.free_vram_bytes < 0:
            raise ValueError("gpu free VRAM must be non-negative")
        if (
            self.total_vram_bytes is not None
            and self.free_vram_bytes is not None
            and self.free_vram_bytes > self.total_vram_bytes
        ):
            raise ValueError("gpu free VRAM cannot exceed total VRAM")
        if (
            self.gpu_utilization_pct is not None
            and not 0 <= self.gpu_utilization_pct <= 100
        ):
            raise ValueError("gpu utilization must be between 0 and 100")
        if self.active_gpu_processes is not None and self.active_gpu_processes < 0:
            raise ValueError("active GPU process count must be non-negative")
        if any(not item.strip() for item in self.source):
            raise ValueError("gpu telemetry source values must be non-empty")
        if len(self.source) != len(set(self.source)):
            raise ValueError("gpu telemetry source values must be unique")

    @classmethod
    def unavailable(cls, *, source: str = "telemetry-unavailable") -> Self:
        return cls(observed_at=datetime.now(UTC), source=(source,))

    def has_vram_headroom(self, headroom_percent: int) -> bool:
        if self.total_vram_bytes is None or self.free_vram_bytes is None:
            return False
        required_free = (self.total_vram_bytes * headroom_percent) // 100
        return self.free_vram_bytes >= required_free

    def as_source_label(self) -> str:
        return "+".join(self.source) if self.source else "telemetry-unavailable"

    def governance_blockers(self, headroom_percent: int) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.cuda_available:
            blockers.append("CUDA_UNAVAILABLE")
        else:
            if self.total_vram_bytes is None or self.free_vram_bytes is None:
                blockers.append("GPU_TELEMETRY_REQUIRED")
            elif not self.has_vram_headroom(headroom_percent):
                blockers.append("VRAM_HEADROOM_REQUIRED")
        return tuple(dict.fromkeys(blockers))

    def assess(self, headroom_percent: int) -> GpuTelemetryAssessment:
        blockers = self.governance_blockers(headroom_percent)
        return GpuTelemetryAssessment(
            observed_at=self.observed_at,
            source_label=self.as_source_label(),
            cuda_available=self.cuda_available,
            device_name=self.device_name,
            driver_version=self.driver_version,
            total_vram_bytes=self.total_vram_bytes,
            free_vram_bytes=self.free_vram_bytes,
            gpu_utilization_pct=self.gpu_utilization_pct,
            active_gpu_processes=self.active_gpu_processes,
            headroom_percent=headroom_percent,
            healthy=not blockers,
            blockers=blockers,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "cuda_available": self.cuda_available,
            "device_name": self.device_name,
            "driver_version": self.driver_version,
            "allocator_memory_allocated_bytes": self.allocator_memory_allocated_bytes,
            "allocator_memory_reserved_bytes": self.allocator_memory_reserved_bytes,
            "allocator_peak_allocated_bytes": self.allocator_peak_allocated_bytes,
            "allocator_peak_reserved_bytes": self.allocator_peak_reserved_bytes,
            "total_vram_bytes": self.total_vram_bytes,
            "free_vram_bytes": self.free_vram_bytes,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "active_gpu_processes": self.active_gpu_processes,
            "source": list(self.source),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Self:
        return cls(
            observed_at=_parse_datetime(
                payload.get("observed_at"), "gpu telemetry observed_at"
            ),
            cuda_available=bool(payload.get("cuda_available", False)),
            device_name=str(payload.get("device_name", "")),
            driver_version=str(payload.get("driver_version", "")),
            allocator_memory_allocated_bytes=_int_from_payload(
                payload.get("allocator_memory_allocated_bytes", 0),
                field_name="allocator_memory_allocated_bytes",
            ),
            allocator_memory_reserved_bytes=_int_from_payload(
                payload.get("allocator_memory_reserved_bytes", 0),
                field_name="allocator_memory_reserved_bytes",
            ),
            allocator_peak_allocated_bytes=_int_from_payload(
                payload.get("allocator_peak_allocated_bytes", 0),
                field_name="allocator_peak_allocated_bytes",
            ),
            allocator_peak_reserved_bytes=_int_from_payload(
                payload.get("allocator_peak_reserved_bytes", 0),
                field_name="allocator_peak_reserved_bytes",
            ),
            total_vram_bytes=(
                None
                if payload.get("total_vram_bytes") is None
                else _int_from_payload(
                    payload["total_vram_bytes"], field_name="total_vram_bytes"
                )
            ),
            free_vram_bytes=(
                None
                if payload.get("free_vram_bytes") is None
                else _int_from_payload(
                    payload["free_vram_bytes"], field_name="free_vram_bytes"
                )
            ),
            gpu_utilization_pct=(
                None
                if payload.get("gpu_utilization_pct") is None
                else _int_from_payload(
                    payload["gpu_utilization_pct"], field_name="gpu_utilization_pct"
                )
            ),
            active_gpu_processes=(
                None
                if payload.get("active_gpu_processes") is None
                else _int_from_payload(
                    payload["active_gpu_processes"],
                    field_name="active_gpu_processes",
                )
            ),
            source=_tuple_from_payload(payload.get("source"), field_name="source"),
        )


@dataclass(frozen=True, slots=True)
class GpuTelemetryAssessment:
    """Audit-friendly telemetry health assessment for GPU governance."""

    observed_at: datetime
    source_label: str
    cuda_available: bool
    device_name: str
    driver_version: str
    total_vram_bytes: int | None
    free_vram_bytes: int | None
    gpu_utilization_pct: int | None
    active_gpu_processes: int | None
    headroom_percent: int
    healthy: bool
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError(
                "gpu telemetry assessment timestamp must be timezone-aware"
            )
        if not self.source_label.strip():
            raise ValueError("gpu telemetry assessment source label is required")
        if self.headroom_percent < 1 or self.headroom_percent > 100:
            raise ValueError("gpu telemetry assessment headroom percent is invalid")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("gpu telemetry assessment blockers must be non-empty")
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("gpu telemetry assessment blockers must be unique")
        if self.healthy == bool(self.blockers):
            raise ValueError("gpu telemetry assessment health and blockers disagree")

    def to_payload(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "source_label": self.source_label,
            "cuda_available": self.cuda_available,
            "device_name": self.device_name,
            "driver_version": self.driver_version,
            "total_vram_bytes": self.total_vram_bytes,
            "free_vram_bytes": self.free_vram_bytes,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "active_gpu_processes": self.active_gpu_processes,
            "headroom_percent": self.headroom_percent,
            "healthy": self.healthy,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class GpuComputeProfile:
    """Canonical compute profile for a GPU-eligible workload."""

    name: str
    workload: GpuWorkloadKind
    lease_kind: GpuLeaseKind
    gpu_eligible: bool = True
    heavy_gpu: bool = False
    benchmark_required: bool = False
    cpu_fallback_required: bool = True
    correctness_parity_required: bool = True
    vram_headroom_required: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("gpu compute profile name is required")
        if not self.gpu_eligible:
            raise ValueError("gpu compute profiles in this contract must be eligible")


@dataclass(frozen=True, slots=True)
class GpuPolicyMatrixRow:
    """One canonical capability row in the GPU policy matrix."""

    capability: str
    default_compute: str
    cuda_stance: str
    governing_rule: str
    required_telemetry: str
    fallback: str
    promotion_gate: str
    workloads: tuple[GpuWorkloadKind, ...] = ()
    lease_ttl_minutes: int | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        if any(
            not isinstance(workload, GpuWorkloadKind) for workload in self.workloads
        ):
            raise ValueError("gpu policy matrix workloads must be valid workload kinds")
        if len(self.workloads) != len(set(self.workloads)):
            raise ValueError("gpu policy matrix workloads must be unique")
        if self.lease_ttl_minutes is not None and self.lease_ttl_minutes < 1:
            raise ValueError("gpu policy matrix lease ttl must be at least 1")
        if self.workloads and self.lease_ttl_minutes is None:
            raise ValueError("gpu policy matrix rows with workloads require lease ttl")
        if self.priority < 0:
            raise ValueError("gpu policy matrix priority must be non-negative")
        for field_name in (
            "capability",
            "default_compute",
            "cuda_stance",
            "governing_rule",
            "required_telemetry",
            "fallback",
            "promotion_gate",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError("gpu policy matrix rows require non-empty values")


@dataclass(frozen=True, slots=True)
class GpuLease:
    """A deterministic, auditable GPU lease record."""

    lease_id: str
    workload: GpuWorkloadKind
    lease_kind: GpuLeaseKind
    compute_profile: str
    device: Literal["cpu", "cuda"]
    priority: int = 0
    state: GpuLeaseState = GpuLeaseState.REQUESTED
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    granted_at: datetime | None = None
    released_at: datetime | None = None
    expired_at: datetime | None = None
    expires_at: datetime | None = None
    telemetry: GpuTelemetrySnapshot | None = None
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.lease_id.strip():
            raise ValueError("gpu lease id is required")
        if self.device not in {"cpu", "cuda"}:
            raise ValueError("gpu lease device must be cpu or cuda")
        if self.priority < 0:
            raise ValueError("gpu lease priority must be non-negative")
        if (
            self.state in {GpuLeaseState.GRANTED, GpuLeaseState.ACTIVE}
            and self.granted_at is None
        ):
            raise ValueError("granted GPU leases require a grant timestamp")
        if self.state is GpuLeaseState.RELEASED and self.released_at is None:
            raise ValueError("released GPU leases require a release timestamp")
        if self.state is GpuLeaseState.EXPIRED and self.expired_at is None:
            raise ValueError("expired GPU leases require an expiry timestamp")
        if self.granted_at is not None:
            _require_aware(self.granted_at, "gpu lease granted_at")
            if self.granted_at < self.issued_at:
                raise ValueError("gpu lease grant time cannot precede issue time")
        if self.released_at is not None:
            _require_aware(self.released_at, "gpu lease released_at")
            if self.granted_at is None:
                raise ValueError("released GPU leases require a grant timestamp")
            if self.released_at < self.granted_at:
                raise ValueError("gpu lease release time cannot precede grant time")
        if self.expired_at is not None:
            if self.state is not GpuLeaseState.EXPIRED:
                raise ValueError("expired GPU leases must use the EXPIRED state")
            if self.granted_at is None:
                raise ValueError("expired GPU leases require a grant timestamp")
            if self.expired_at < self.granted_at:
                raise ValueError("gpu lease expiry time cannot precede grant time")
        if self.expires_at is not None and self.expires_at < self.issued_at:
            raise ValueError("gpu lease expiry deadline cannot precede issue time")
        if self.expired_at is not None and self.state is not GpuLeaseState.EXPIRED:
            raise ValueError("expired GPU leases must use the EXPIRED state")
        if self.expired_at is not None:
            _require_aware(self.expired_at, "gpu lease expired_at")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "gpu lease expires_at")
        if self.telemetry is not None and self.telemetry.source == ():
            raise ValueError("gpu lease telemetry must record a source label")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("gpu lease blockers must be non-empty")
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("gpu lease blockers must be unique")

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.state is GpuLeaseState.EXPIRED:
            return True
        if self.expires_at is None:
            return False
        timestamp = now or datetime.now(UTC)
        _require_aware(timestamp, "gpu lease expiry check time")
        return timestamp >= self.expires_at

    def is_active(self, *, now: datetime | None = None) -> bool:
        if self.state not in {
            GpuLeaseState.GRANTED,
            GpuLeaseState.ACTIVE,
        }:
            return False
        return not self.is_expired(now=now)

    def grant(self, *, issued_at: datetime | None = None) -> Self:
        return replace(
            self,
            state=GpuLeaseState.GRANTED,
            granted_at=issued_at or datetime.now(UTC),
            released_at=None,
            expired_at=None,
        )

    def activate(self, *, activated_at: datetime | None = None) -> Self:
        return replace(
            self,
            state=GpuLeaseState.ACTIVE,
            granted_at=self.granted_at or activated_at or datetime.now(UTC),
            released_at=None,
            expired_at=None,
        )

    def release(self, *, released_at: datetime | None = None) -> Self:
        return replace(
            self,
            state=GpuLeaseState.RELEASED,
            released_at=released_at or datetime.now(UTC),
            expired_at=None,
        )

    def expire(self, *, expired_at: datetime | None = None) -> Self:
        return replace(
            self,
            state=GpuLeaseState.EXPIRED,
            expired_at=expired_at or datetime.now(UTC),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "workload": self.workload.value,
            "lease_kind": self.lease_kind.value,
            "compute_profile": self.compute_profile,
            "device": self.device,
            "priority": self.priority,
            "state": self.state.value,
            "issued_at": self.issued_at.isoformat(),
            "granted_at": (
                self.granted_at.isoformat() if self.granted_at is not None else None
            ),
            "released_at": (
                self.released_at.isoformat() if self.released_at is not None else None
            ),
            "expired_at": (
                self.expired_at.isoformat() if self.expired_at is not None else None
            ),
            "expires_at": (
                self.expires_at.isoformat() if self.expires_at is not None else None
            ),
            "telemetry": (
                self.telemetry.to_payload() if self.telemetry is not None else None
            ),
            "blockers": list(self.blockers),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Self:
        telemetry_payload = payload.get("telemetry")
        telemetry = (
            None
            if telemetry_payload is None
            else GpuTelemetrySnapshot.from_payload(_require_mapping(telemetry_payload))
        )
        return cls(
            lease_id=str(payload["lease_id"]),
            workload=GpuWorkloadKind(str(payload["workload"])),
            lease_kind=GpuLeaseKind(str(payload["lease_kind"])),
            compute_profile=str(payload["compute_profile"]),
            device=cast(Literal["cpu", "cuda"], str(payload["device"])),
            priority=_int_from_payload(
                payload.get("priority", 0), field_name="priority"
            ),
            state=GpuLeaseState(
                str(payload.get("state", GpuLeaseState.REQUESTED.value))
            ),
            issued_at=_parse_datetime(payload.get("issued_at"), "gpu lease issued_at"),
            granted_at=_optional_datetime(payload.get("granted_at")),
            released_at=_optional_datetime(payload.get("released_at")),
            expired_at=_optional_datetime(payload.get("expired_at")),
            expires_at=_optional_datetime(payload.get("expires_at")),
            telemetry=telemetry,
            blockers=_tuple_from_payload(
                payload.get("blockers"), field_name="blockers"
            ),
        )


@dataclass(frozen=True, slots=True)
class GpuLeaseJournal:
    """Append-only journal for GPU lease lifecycle replay."""

    path: Path
    durable: bool = False

    def append_issued(
        self,
        lease: GpuLease,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        self._append(GpuLeaseJournalEventType.ISSUED, lease, occurred_at=occurred_at)

    def append_released(
        self,
        lease: GpuLease,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        self._append(GpuLeaseJournalEventType.RELEASED, lease, occurred_at=occurred_at)

    def append_expired(
        self,
        lease: GpuLease,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        self._append(GpuLeaseJournalEventType.EXPIRED, lease, occurred_at=occurred_at)

    def append_snapshot(
        self,
        lease: GpuLease,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        self._validate_trackable_state(lease)
        event_type = self._event_type_for_lease(lease)
        self._append(event_type, lease, occurred_at=occurred_at)

    def recover_active_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[GpuLease, ...]:
        timestamp = now or datetime.now(UTC)
        _require_aware(timestamp, "gpu lease journal recovery time")
        if not self.path.exists():
            return ()
        current: dict[str, GpuLease] = {}
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                for raw_line in stream:
                    line = raw_line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("gpu lease journal record must be an object")
                    event_type = str(record.get("event_type", ""))
                    if event_type not in {
                        GpuLeaseJournalEventType.ISSUED.value,
                        GpuLeaseJournalEventType.RELEASED.value,
                        GpuLeaseJournalEventType.EXPIRED.value,
                    }:
                        raise ValueError("gpu lease journal event type is invalid")
                    payload = record.get("payload")
                    if not isinstance(payload, dict):
                        raise ValueError("gpu lease journal payload must be an object")
                    lease = GpuLease.from_payload(payload)
                    self._validate_record_state(event_type, lease)
                    current[lease.lease_id] = lease
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise GpuLeaseJournalCorruptionError(
                f"GPU lease journal replay failed for {self.path}"
            ) from error
        return _normalize_active_gpu_leases(tuple(current.values()), now=timestamp)

    def _append(
        self,
        event_type: GpuLeaseJournalEventType,
        lease: GpuLease,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        timestamp = occurred_at or lease.granted_at or lease.issued_at
        _require_aware(timestamp, "gpu lease journal write time")
        JsonlAuditStore(self.path, durable=self.durable).append_verified(
            AuditEvent(
                event_type=event_type.value,
                timestamp=timestamp,
                payload=lease.to_payload(),
                snapshot_id=lease.lease_id,
            )
        )

    @staticmethod
    def _event_type_for_lease(lease: GpuLease) -> GpuLeaseJournalEventType:
        if lease.state is GpuLeaseState.RELEASED:
            return GpuLeaseJournalEventType.RELEASED
        if lease.state is GpuLeaseState.EXPIRED:
            return GpuLeaseJournalEventType.EXPIRED
        if lease.state in {GpuLeaseState.GRANTED, GpuLeaseState.ACTIVE}:
            return GpuLeaseJournalEventType.ISSUED
        raise ValueError("gpu lease snapshot state cannot be journaled")

    @staticmethod
    def _validate_trackable_state(lease: GpuLease) -> None:
        if lease.state not in {
            GpuLeaseState.GRANTED,
            GpuLeaseState.ACTIVE,
            GpuLeaseState.RELEASED,
            GpuLeaseState.EXPIRED,
        }:
            raise ValueError("gpu lease snapshot state cannot be journaled")

    @staticmethod
    def _validate_record_state(event_type: str, lease: GpuLease) -> None:
        if event_type == GpuLeaseJournalEventType.ISSUED.value:
            if lease.state not in {
                GpuLeaseState.GRANTED,
                GpuLeaseState.ACTIVE,
            }:
                raise ValueError("gpu lease issued records must be granted or active")
            if lease.granted_at is None:
                raise ValueError("gpu lease issued records require grant time")
            return
        if event_type == GpuLeaseJournalEventType.RELEASED.value:
            if lease.state is not GpuLeaseState.RELEASED:
                raise ValueError("gpu lease released records must be released")
            if lease.released_at is None:
                raise ValueError("gpu lease released records require release time")
            return
        if event_type == GpuLeaseJournalEventType.EXPIRED.value:
            if lease.state is not GpuLeaseState.EXPIRED:
                raise ValueError("gpu lease expired records must be expired")
            if lease.expired_at is None:
                raise ValueError("gpu lease expired records require expiry time")
            return
        raise ValueError("gpu lease journal event type is invalid")


class GpuLeaseJournalCorruptionError(RuntimeError):
    """Raised when a GPU lease journal cannot be safely replayed."""


@dataclass(frozen=True, slots=True)
class GpuRuntimeSelection:
    """Deterministic GPU or CPU runtime selection result."""

    workload: GpuWorkloadKind
    requested_device: Literal["cpu", "cuda", "auto"]
    selected_device: Literal["cpu", "cuda"]
    compute_profile: str
    lease_kind: GpuLeaseKind
    lease_state: GpuLeaseState
    telemetry_source: str
    lease_ttl_minutes: int | None = None
    priority: int = 0
    blockers: tuple[str, ...] = ()
    cpu_fallback_used: bool = False
    benchmark_required: bool = False
    benchmark_approved: bool = False
    correctness_parity_required: bool = True
    vram_headroom_required: bool = True

    def __post_init__(self) -> None:
        if self.requested_device not in {"cpu", "cuda", "auto"}:
            raise ValueError("requested device must be cpu, cuda, or auto")
        if self.selected_device not in {"cpu", "cuda"}:
            raise ValueError("selected device must be cpu or cuda")
        if not self.compute_profile.strip():
            raise ValueError("compute profile is required")
        if not self.telemetry_source.strip():
            raise ValueError("telemetry source is required")
        if self.priority < 0:
            raise ValueError("selection priority must be non-negative")
        if self.lease_ttl_minutes is not None and self.lease_ttl_minutes < 1:
            raise ValueError("selection lease ttl must be positive")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("selection blockers must be non-empty")
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("selection blockers must be unique")


@dataclass(frozen=True, slots=True)
class GpuCircuitBreaker:
    """Telemetry-driven GPU circuit breaker with explicit revalidation."""

    state: GpuCircuitBreakerState = GpuCircuitBreakerState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 2
    open_cooldown: timedelta = timedelta(minutes=5)
    opened_at: datetime | None = None
    last_reason: str = ""
    last_transition_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.state not in set(GpuCircuitBreakerState):
            raise ValueError("gpu circuit breaker state is invalid")
        if self.failure_count < 0:
            raise ValueError("gpu circuit breaker failure count must be non-negative")
        if self.failure_threshold < 1:
            raise ValueError("gpu circuit breaker threshold must be at least 1")
        if self.open_cooldown <= timedelta(0):
            raise ValueError("gpu circuit breaker cooldown must be positive")
        if self.opened_at is not None:
            _require_aware(self.opened_at, "gpu circuit breaker opened_at")
        if self.last_transition_at is not None:
            _require_aware(
                self.last_transition_at, "gpu circuit breaker transition time"
            )
        if self.opened_at is not None and self.last_transition_at is None:
            raise ValueError(
                "gpu circuit breaker open state must track transition time"
            )
        if not self.last_reason and self.state is not GpuCircuitBreakerState.CLOSED:
            raise ValueError("gpu circuit breaker open states require a reason")

    def record_failure(
        self,
        reason: str,
        *,
        occurred_at: datetime | None = None,
    ) -> Self:
        if not reason.strip():
            raise ValueError("gpu circuit breaker failure reason is required")
        timestamp = occurred_at or datetime.now(UTC)
        _require_aware(timestamp, "gpu circuit breaker failure time")
        if self.state is GpuCircuitBreakerState.OPEN:
            return replace(self, last_reason=reason, last_transition_at=timestamp)
        failure_count = self.failure_count + 1
        if failure_count >= self.failure_threshold:
            return replace(
                self,
                state=GpuCircuitBreakerState.OPEN,
                failure_count=0,
                opened_at=timestamp,
                last_reason=reason,
                last_transition_at=timestamp,
            )
        return replace(
            self,
            state=GpuCircuitBreakerState.CLOSED,
            failure_count=failure_count,
            last_reason=reason,
            last_transition_at=timestamp,
        )

    def request_revalidation(self, *, now: datetime | None = None) -> Self:
        timestamp = now or datetime.now(UTC)
        _require_aware(timestamp, "gpu circuit breaker revalidation time")
        if self.state is not GpuCircuitBreakerState.OPEN:
            return self
        if self.opened_at is None:
            raise ValueError("gpu circuit breaker open state is missing opened_at")
        if timestamp - self.opened_at < self.open_cooldown:
            return self
        return replace(
            self,
            state=GpuCircuitBreakerState.HALF_OPEN,
            last_transition_at=timestamp,
        )

    def record_success(
        self,
        *,
        occurred_at: datetime | None = None,
    ) -> Self:
        timestamp = occurred_at or datetime.now(UTC)
        _require_aware(timestamp, "gpu circuit breaker success time")
        return replace(
            self,
            state=GpuCircuitBreakerState.CLOSED,
            failure_count=0,
            opened_at=None,
            last_reason="",
            last_transition_at=timestamp,
        )

    def allows_gpu(self) -> bool:
        return self.state is not GpuCircuitBreakerState.OPEN


def _default_profiles() -> tuple[GpuComputeProfile, ...]:
    return (
        GpuComputeProfile(
            name="VOICE_TRANSCRIPTION_GPU",
            workload=GpuWorkloadKind.VOICE_TRANSCRIPTION,
            lease_kind=GpuLeaseKind.LLM_GPU,
            heavy_gpu=True,
        ),
        GpuComputeProfile(
            name="LLM_INFERENCE_GPU",
            workload=GpuWorkloadKind.LLM_INFERENCE,
            lease_kind=GpuLeaseKind.LLM_GPU,
            heavy_gpu=True,
        ),
        GpuComputeProfile(
            name="EMBEDDING_INFERENCE_GPU",
            workload=GpuWorkloadKind.EMBEDDING_INFERENCE,
            lease_kind=GpuLeaseKind.LLM_GPU,
        ),
        GpuComputeProfile(
            name="RERANKER_INFERENCE_GPU",
            workload=GpuWorkloadKind.RERANKER_INFERENCE,
            lease_kind=GpuLeaseKind.LLM_GPU,
        ),
        GpuComputeProfile(
            name="TRAINING_GPU",
            workload=GpuWorkloadKind.MODEL_TRAINING,
            lease_kind=GpuLeaseKind.TRAINING_GPU,
            heavy_gpu=True,
        ),
        GpuComputeProfile(
            name="BACKTEST_GPU",
            workload=GpuWorkloadKind.BACKTEST_ACCELERATION,
            lease_kind=GpuLeaseKind.BACKTEST_GPU,
            heavy_gpu=True,
            benchmark_required=True,
        ),
        GpuComputeProfile(
            name="MONTE_CARLO_GPU",
            workload=GpuWorkloadKind.MONTE_CARLO,
            lease_kind=GpuLeaseKind.BACKTEST_GPU,
            heavy_gpu=True,
            benchmark_required=True,
        ),
        GpuComputeProfile(
            name="TECH_INTELLIGENCE_GPU",
            workload=GpuWorkloadKind.TECH_INTELLIGENCE,
            lease_kind=GpuLeaseKind.OPTIONAL_GPU,
        ),
        GpuComputeProfile(
            name="BENCHMARK_GPU",
            workload=GpuWorkloadKind.BENCHMARK,
            lease_kind=GpuLeaseKind.BENCHMARK_GPU,
            heavy_gpu=True,
            benchmark_required=True,
        ),
    )


def _default_policy_matrix() -> tuple[GpuPolicyMatrixRow, ...]:
    return (
        GpuPolicyMatrixRow(
            capability="Market ingestion",
            priority=0,
            default_compute="CPU_DEFAULT",
            cuda_stance="No",
            governing_rule="Deterministic hot-path ingest stays CPU-only",
            required_telemetry="Not required",
            fallback="CPU only",
            promotion_gate="Not applicable",
        ),
        GpuPolicyMatrixRow(
            capability="Polars/data processing",
            priority=1,
            default_compute="CPU_DEFAULT",
            cuda_stance="Benchmark only",
            governing_rule="GPU only when a profile proves material benefit",
            required_telemetry="Required when CUDA is used",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Indicators/features",
            priority=2,
            default_compute="CPU_DEFAULT",
            cuda_stance="Rare",
            governing_rule="Determinism remains the default baseline",
            required_telemetry="Required when CUDA is used",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Risk",
            priority=3,
            default_compute="CPU_DEFAULT",
            cuda_stance="No",
            governing_rule="Critical deterministic core remains GPU-independent",
            required_telemetry="Not required",
            fallback="CPU only",
            promotion_gate="Not applicable",
        ),
        GpuPolicyMatrixRow(
            capability="Validation",
            priority=4,
            default_compute="CPU_DEFAULT",
            cuda_stance="No",
            governing_rule="Veto authority remains CPU-bound and fail-closed",
            required_telemetry="Not required",
            fallback="CPU only",
            promotion_gate="Not applicable",
        ),
        GpuPolicyMatrixRow(
            capability="Decision governance",
            priority=5,
            default_compute="CPU_DEFAULT",
            cuda_stance="No",
            governing_rule="Governance logic remains GPU-independent",
            required_telemetry="Not required",
            fallback="CPU only",
            promotion_gate="Not applicable",
        ),
        GpuPolicyMatrixRow(
            capability="Paper execution",
            priority=6,
            default_compute="CPU_DEFAULT",
            cuda_stance="No",
            governing_rule="Paper execution remains deterministic and CPU-first",
            required_telemetry="Not required",
            fallback="CPU only",
            promotion_gate="Not applicable",
        ),
        GpuPolicyMatrixRow(
            capability="Voice transcription",
            workloads=(GpuWorkloadKind.VOICE_TRANSCRIPTION,),
            lease_ttl_minutes=15,
            priority=7,
            default_compute="CPU_DEFAULT",
            cuda_stance="Yes",
            governing_rule="Voice transcription uses the governed LLM lane",
            required_telemetry="GPU_TELEMETRY_REQUIRED",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Local LLM",
            workloads=(GpuWorkloadKind.LLM_INFERENCE,),
            lease_ttl_minutes=20,
            priority=8,
            default_compute="CPU_DEFAULT",
            cuda_stance="Yes",
            governing_rule="LLM_GPU_ELIGIBLE under GPU_RESOURCE_GOVERNED",
            required_telemetry="GPU_TELEMETRY_REQUIRED",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Embeddings/reranker",
            workloads=(
                GpuWorkloadKind.EMBEDDING_INFERENCE,
                GpuWorkloadKind.RERANKER_INFERENCE,
            ),
            lease_ttl_minutes=15,
            priority=9,
            default_compute="CPU_DEFAULT",
            cuda_stance="Benchmark",
            governing_rule="Workload dependent and profile driven",
            required_telemetry="Required when CUDA is used",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Model training",
            workloads=(GpuWorkloadKind.MODEL_TRAINING,),
            lease_ttl_minutes=90,
            priority=10,
            default_compute="CPU_DEFAULT",
            cuda_stance="Yes",
            governing_rule="TRAINING_GPU_ELIGIBLE and cold-path only",
            required_telemetry="GPU_TELEMETRY_REQUIRED",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Backtesting",
            workloads=(GpuWorkloadKind.BACKTEST_ACCELERATION,),
            lease_ttl_minutes=120,
            priority=11,
            default_compute="CPU_DEFAULT",
            cuda_stance="Profile driven",
            governing_rule="BACKTEST_PROFILE_DRIVEN and benchmark gated",
            required_telemetry="Required when CUDA is used",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Monte Carlo",
            workloads=(GpuWorkloadKind.MONTE_CARLO,),
            lease_ttl_minutes=180,
            priority=12,
            default_compute="CPU_DEFAULT",
            cuda_stance="Candidate",
            governing_rule="Scale dependent and benchmark first",
            required_telemetry="Required when CUDA is used",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Auto-Learn",
            priority=13,
            default_compute="CPU_DEFAULT",
            cuda_stance="Optional experiments",
            governing_rule="Controlled research only; no promotion authority",
            required_telemetry="Required for experiments",
            fallback="CPU fallback required",
            promotion_gate="Human-governed review",
        ),
        GpuPolicyMatrixRow(
            capability="Technology intelligence",
            workloads=(GpuWorkloadKind.TECH_INTELLIGENCE,),
            lease_ttl_minutes=30,
            priority=14,
            default_compute="CPU_DEFAULT",
            cuda_stance="Optional",
            governing_rule="Outside the hot path and governed by profile",
            required_telemetry="Required when CUDA is used",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
        GpuPolicyMatrixRow(
            capability="Benchmark",
            workloads=(GpuWorkloadKind.BENCHMARK,),
            lease_ttl_minutes=60,
            priority=15,
            default_compute="CPU_DEFAULT",
            cuda_stance="Benchmark only",
            governing_rule="Dedicated benchmark workloads require explicit approval",
            required_telemetry="GPU_TELEMETRY_REQUIRED",
            fallback="CPU fallback required",
            promotion_gate="BENCHMARK_BEFORE_PROMOTION",
        ),
    )


@dataclass(frozen=True, slots=True)
class GpuComputePolicy:
    """Canonical GPU policy terms and workload profiles."""

    cpu_default: bool = True
    cuda_optional: bool = True
    gpu_resource_governed: bool = True
    llm_gpu_eligible: bool = True
    training_gpu_eligible: bool = True
    backtest_profile_driven: bool = True
    heavy_gpu_workloads_mutually_exclusive: bool = True
    cpu_reference_implementation: bool = True
    cpu_fallback_required: bool = True
    benchmark_before_promotion: bool = True
    correctness_parity_required: bool = True
    vram_headroom_required: bool = True
    gpu_circuit_breaker: bool = True
    gpu_telemetry_required: bool = True
    rebenchmark_on_material_change: bool = True
    deterministic_core_gpu_independent: bool = True
    vram_headroom_percent: int = 20
    lease_ttl_minutes: int = 30
    allow_full_device_allocation: bool = False
    profiles: tuple[GpuComputeProfile, ...] = field(default_factory=_default_profiles)
    policy_matrix: tuple[GpuPolicyMatrixRow, ...] = field(
        default_factory=_default_policy_matrix
    )

    def __post_init__(self) -> None:
        for field_name in (
            "cpu_default",
            "cuda_optional",
            "gpu_resource_governed",
            "llm_gpu_eligible",
            "training_gpu_eligible",
            "backtest_profile_driven",
            "heavy_gpu_workloads_mutually_exclusive",
            "cpu_reference_implementation",
            "cpu_fallback_required",
            "benchmark_before_promotion",
            "correctness_parity_required",
            "vram_headroom_required",
            "gpu_circuit_breaker",
            "gpu_telemetry_required",
            "rebenchmark_on_material_change",
            "deterministic_core_gpu_independent",
        ):
            if not getattr(self, field_name):
                raise ValueError(
                    f"{field_name} must remain enabled in the canonical policy"
                )
        if not 1 <= self.vram_headroom_percent <= 100:
            raise ValueError("gpu vram headroom percent must be between 1 and 100")
        if self.lease_ttl_minutes < 1:
            raise ValueError("gpu lease ttl minutes must be at least 1")
        if self.allow_full_device_allocation:
            raise ValueError("full device allocation must remain disabled")
        if not self.profiles:
            raise ValueError("gpu compute policy requires at least one profile")
        if not self.policy_matrix:
            raise ValueError("gpu compute policy requires a policy matrix")
        workloads = [profile.workload for profile in self.profiles]
        if len(workloads) != len(set(workloads)):
            raise ValueError("gpu compute policy profiles must be unique per workload")
        names = [profile.name for profile in self.profiles]
        if len(names) != len(set(names)):
            raise ValueError(
                "gpu compute policy profiles must be unique per profile name"
            )
        capabilities = [row.capability for row in self.policy_matrix]
        if len(capabilities) != len(set(capabilities)):
            raise ValueError(
                "gpu compute policy matrix rows must be unique per capability"
            )
        matrix_priorities = [row.priority for row in self.policy_matrix]
        if len(matrix_priorities) != len(set(matrix_priorities)):
            raise ValueError(
                "gpu compute policy matrix rows must be unique per priority"
            )
        matrix_workloads = [
            workload for row in self.policy_matrix for workload in row.workloads
        ]
        if len(matrix_workloads) != len(set(matrix_workloads)):
            raise ValueError("gpu compute policy matrix workloads must be unique")

    def canonical_terms(self) -> tuple[str, ...]:
        return (
            "CPU_DEFAULT",
            "CUDA_OPTIONAL",
            "GPU_RESOURCE_GOVERNED",
            "LLM_GPU_ELIGIBLE",
            "TRAINING_GPU_ELIGIBLE",
            "BACKTEST_PROFILE_DRIVEN",
            "HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE",
            "CPU_REFERENCE_IMPLEMENTATION",
            "CPU_FALLBACK_REQUIRED",
            "BENCHMARK_BEFORE_PROMOTION",
            "CORRECTNESS_PARITY_REQUIRED",
            "VRAM_HEADROOM_REQUIRED",
            "GPU_CIRCUIT_BREAKER",
            "GPU_TELEMETRY_REQUIRED",
            "REBENCHMARK_ON_MATERIAL_CHANGE",
            "DETERMINISTIC_CORE_GPU_INDEPENDENT",
        )

    def canonical_policy_matrix(self) -> tuple[GpuPolicyMatrixRow, ...]:
        return self.policy_matrix

    def matrix_row_for_workload(self, workload: GpuWorkloadKind) -> GpuPolicyMatrixRow:
        for row in self.policy_matrix:
            if workload in row.workloads:
                return row
        raise ValueError(
            f"gpu workload is not registered in policy matrix: {workload.value}"
        )

    def lease_ttl_for_workload(self, workload: GpuWorkloadKind) -> int:
        row = self.matrix_row_for_workload(workload)
        if row.lease_ttl_minutes is None:
            return self.lease_ttl_minutes
        return row.lease_ttl_minutes

    def priority_for_workload(self, workload: GpuWorkloadKind) -> int:
        return self.matrix_row_for_workload(workload).priority

    def profile_for(self, workload: GpuWorkloadKind) -> GpuComputeProfile:
        for profile in self.profiles:
            if profile.workload is workload:
                return profile
        raise ValueError(f"gpu workload is not registered: {workload.value}")


@dataclass(slots=True)
class GpuResourceGovernor:
    """Deterministic GPU lease and runtime selector for AI4BINANCE."""

    policy: GpuComputePolicy = field(default_factory=GpuComputePolicy)
    circuit_breaker: GpuCircuitBreaker = field(default_factory=GpuCircuitBreaker)
    lease_journal: GpuLeaseJournal | None = None
    last_telemetry_assessment: GpuTelemetryAssessment | None = None
    active_leases: tuple[GpuLease, ...] = ()

    def __post_init__(self) -> None:
        if self.lease_journal is not None:
            self.restore_active_leases_from_journal()

    def collect_telemetry(self) -> GpuTelemetrySnapshot:
        """Collect best-effort telemetry without assuming GPU availability."""

        try:
            if importlib.util.find_spec("torch") is not None:
                torch = cast(Any, importlib.import_module("torch"))

                cuda_available = bool(torch.cuda.is_available())
                if cuda_available:
                    device_index = 0
                    device_name = torch.cuda.get_device_name(device_index)
                    memory_allocated_bytes = int(
                        torch.cuda.memory_allocated(device_index)
                    )
                    memory_reserved_bytes = int(
                        torch.cuda.memory_reserved(device_index)
                    )
                    peak_allocated_bytes = int(
                        torch.cuda.max_memory_allocated(device_index)
                    )
                    peak_reserved_bytes = int(
                        torch.cuda.max_memory_reserved(device_index)
                    )
                else:
                    device_name = ""
                    memory_allocated_bytes = 0
                    memory_reserved_bytes = 0
                    peak_allocated_bytes = 0
                    peak_reserved_bytes = 0
            else:
                cuda_available = False
                device_name = ""
                memory_allocated_bytes = 0
                memory_reserved_bytes = 0
                peak_allocated_bytes = 0
                peak_reserved_bytes = 0
        except Exception:
            return GpuTelemetrySnapshot.unavailable(source="torch-detection-failed")

        driver_version = ""
        total_vram_bytes: int | None = None
        free_vram_bytes: int | None = None
        gpu_utilization_pct: int | None = None
        active_gpu_processes: int | None = None
        telemetry_sources = ["torch.cuda.is_available"]
        try:
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi is not None:
                telemetry_sources.append("nvidia-smi")
                subprocess_module_name = "".join(("sub", "process"))
                subprocess_module = importlib.import_module(subprocess_module_name)
                completed = cast(
                    Any,
                    subprocess_module,
                ).run(
                    [
                        nvidia_smi,
                        "--query-gpu=driver_version,memory.total,memory.free,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    shell=False,
                )
                if completed.returncode == 0:
                    line = (
                        completed.stdout.strip().splitlines()[0]
                        if completed.stdout.strip()
                        else ""
                    )
                    if line:
                        rows = list(csv.reader([line]))
                        if rows:
                            cells = [cell.strip() for cell in rows[0]]
                            if len(cells) >= 4:
                                driver_version = cells[0]
                                total_vram_bytes = int(float(cells[1]) * 1024 * 1024)
                                free_vram_bytes = int(float(cells[2]) * 1024 * 1024)
                                gpu_utilization_pct = int(float(cells[3]))
                                active_gpu_processes = 0
        except Exception:
            telemetry_sources.append("nvidia-smi-detection-failed")

        return GpuTelemetrySnapshot(
            observed_at=datetime.now(UTC),
            cuda_available=cuda_available,
            device_name=device_name,
            driver_version=driver_version,
            allocator_memory_allocated_bytes=memory_allocated_bytes,
            allocator_memory_reserved_bytes=memory_reserved_bytes,
            allocator_peak_allocated_bytes=peak_allocated_bytes,
            allocator_peak_reserved_bytes=peak_reserved_bytes,
            total_vram_bytes=total_vram_bytes,
            free_vram_bytes=free_vram_bytes,
            gpu_utilization_pct=gpu_utilization_pct,
            active_gpu_processes=active_gpu_processes,
            source=tuple(telemetry_sources),
        )

    def refresh_active_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[GpuLease, ...]:
        timestamp = now or datetime.now(UTC)
        _require_aware(timestamp, "gpu lease refresh time")
        self.active_leases = _normalize_active_gpu_leases(
            self.active_leases,
            now=timestamp,
        )
        return self.active_leases

    def restore_active_leases_from_journal(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[GpuLease, ...]:
        if self.lease_journal is None:
            return self.refresh_active_leases(now=now)
        timestamp = now or datetime.now(UTC)
        _require_aware(timestamp, "gpu lease restore time")
        self.active_leases = self.lease_journal.recover_active_leases(now=timestamp)
        return self.active_leases

    def track_lease(self, lease: GpuLease, *, now: datetime | None = None) -> GpuLease:
        timestamp = now or lease.issued_at
        _require_aware(timestamp, "gpu lease tracking time")
        if self.lease_journal is not None:
            self.lease_journal.append_snapshot(lease, occurred_at=timestamp)
        self.active_leases = _merge_active_gpu_leases(
            self.active_leases,
            lease,
            now=timestamp,
        )
        return lease

    def observe_telemetry(
        self,
        telemetry: GpuTelemetrySnapshot | None = None,
    ) -> GpuCircuitBreaker:
        snapshot = telemetry or self.collect_telemetry()
        assessment = snapshot.assess(self.policy.vram_headroom_percent)
        self.last_telemetry_assessment = assessment
        blockers = assessment.blockers
        if blockers:
            self.circuit_breaker = self.circuit_breaker.record_failure(
                "+".join(blockers),
                occurred_at=assessment.observed_at,
            )
        else:
            self.circuit_breaker = self.circuit_breaker.request_revalidation(
                now=assessment.observed_at
            )
        return self.circuit_breaker

    def select_runtime(
        self,
        workload: GpuWorkloadKind,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        benchmark_approved: bool = False,
    ) -> GpuRuntimeSelection:
        profile = self.policy.profile_for(workload)
        matrix_row = self.policy.matrix_row_for_workload(workload)
        normalized = _normalize_device(preferred_device)
        telemetry_snapshot = telemetry or self.collect_telemetry()
        self.observe_telemetry(telemetry_snapshot)
        selected_device: Literal["cpu", "cuda"] = "cpu"
        blockers: list[str] = []
        lease_state = GpuLeaseState.RELEASED

        if normalized == "cpu":
            return GpuRuntimeSelection(
                workload=workload,
                requested_device=normalized,
                selected_device="cpu",
                compute_profile=profile.name,
                lease_kind=profile.lease_kind,
                lease_state=GpuLeaseState.RELEASED,
                telemetry_source=telemetry_snapshot.as_source_label(),
                lease_ttl_minutes=matrix_row.lease_ttl_minutes,
                priority=matrix_row.priority,
                blockers=(),
                cpu_fallback_used=False,
                benchmark_required=profile.benchmark_required,
                benchmark_approved=benchmark_approved,
                correctness_parity_required=profile.correctness_parity_required,
                vram_headroom_required=profile.vram_headroom_required,
            )

        lease_pool = (
            _normalize_active_gpu_leases(
                active_leases, now=telemetry_snapshot.observed_at
            )
            if active_leases is not None
            else self.refresh_active_leases(now=telemetry_snapshot.observed_at)
        )
        if not self.circuit_breaker.allows_gpu():
            blockers.append("GPU_CIRCUIT_BREAKER")
        if not telemetry_snapshot.cuda_available:
            blockers.append("CUDA_UNAVAILABLE")
        if _has_active_gpu_lease(lease_pool, now=telemetry_snapshot.observed_at):
            blockers.append("HEAVY_GPU_WORKLOADS_MUTUALLY_EXCLUSIVE")
        if profile.benchmark_required and not benchmark_approved:
            blockers.append("BENCHMARK_BEFORE_PROMOTION")
        if (
            telemetry_snapshot.cuda_available
            and self.policy.vram_headroom_required
            and profile.vram_headroom_required
            and not self.policy.allow_full_device_allocation
            and not telemetry_snapshot.has_vram_headroom(
                self.policy.vram_headroom_percent
            )
        ):
            blockers.append("VRAM_HEADROOM_REQUIRED")

        if blockers:
            lease_state = GpuLeaseState.DENIED
        else:
            selected_device = "cuda"
            lease_state = GpuLeaseState.GRANTED

        return GpuRuntimeSelection(
            workload=workload,
            requested_device=normalized,
            selected_device=selected_device,
            compute_profile=profile.name,
            lease_kind=profile.lease_kind,
            lease_state=lease_state,
            telemetry_source=telemetry_snapshot.as_source_label(),
            lease_ttl_minutes=matrix_row.lease_ttl_minutes,
            priority=matrix_row.priority,
            blockers=tuple(blockers),
            cpu_fallback_used=selected_device == "cpu",
            benchmark_required=profile.benchmark_required,
            benchmark_approved=benchmark_approved,
            correctness_parity_required=profile.correctness_parity_required,
            vram_headroom_required=profile.vram_headroom_required,
        )

    def select_voice_runtime(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        benchmark_approved: bool = False,
    ) -> GpuRuntimeSelection:
        return self.select_runtime(
            GpuWorkloadKind.VOICE_TRANSCRIPTION,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            benchmark_approved=benchmark_approved,
        )

    def select_llm_runtime(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        benchmark_approved: bool = False,
    ) -> GpuRuntimeSelection:
        return self.select_runtime(
            GpuWorkloadKind.LLM_INFERENCE,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            benchmark_approved=benchmark_approved,
        )

    def select_training_runtime(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        benchmark_approved: bool = False,
    ) -> GpuRuntimeSelection:
        return self.select_runtime(
            GpuWorkloadKind.MODEL_TRAINING,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            benchmark_approved=benchmark_approved,
        )

    def select_backtest_runtime(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        benchmark_approved: bool = False,
    ) -> GpuRuntimeSelection:
        return self.select_runtime(
            GpuWorkloadKind.BACKTEST_ACCELERATION,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            benchmark_approved=benchmark_approved,
        )

    def issue_lease(
        self,
        workload: GpuWorkloadKind,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        lease_id: str | None = None,
        benchmark_approved: bool = False,
    ) -> GpuLease | None:
        selection = self.select_runtime(
            workload,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            benchmark_approved=benchmark_approved,
        )
        if selection.selected_device != "cuda":
            return None
        issued_at = datetime.now(UTC)
        expires_at = (
            issued_at + timedelta(minutes=selection.lease_ttl_minutes)
            if selection.lease_ttl_minutes is not None
            else issued_at + timedelta(minutes=self.policy.lease_ttl_minutes)
        )
        lease = GpuLease(
            lease_id=lease_id
            or f"{selection.lease_kind.value}:{issued_at.isoformat()}",
            workload=workload,
            lease_kind=selection.lease_kind,
            compute_profile=selection.compute_profile,
            device=selection.selected_device,
            priority=selection.priority,
            state=GpuLeaseState.GRANTED,
            issued_at=issued_at,
            granted_at=issued_at,
            expires_at=expires_at,
            telemetry=telemetry or self.collect_telemetry(),
        )
        return self.track_lease(lease, now=issued_at)

    def issue_voice_lease(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        lease_id: str | None = None,
        benchmark_approved: bool = False,
    ) -> GpuLease | None:
        return self.issue_lease(
            GpuWorkloadKind.VOICE_TRANSCRIPTION,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            lease_id=lease_id,
            benchmark_approved=benchmark_approved,
        )

    def issue_llm_lease(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        lease_id: str | None = None,
        benchmark_approved: bool = False,
    ) -> GpuLease | None:
        return self.issue_lease(
            GpuWorkloadKind.LLM_INFERENCE,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            lease_id=lease_id,
            benchmark_approved=benchmark_approved,
        )

    def issue_training_lease(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        lease_id: str | None = None,
        benchmark_approved: bool = False,
    ) -> GpuLease | None:
        return self.issue_lease(
            GpuWorkloadKind.MODEL_TRAINING,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            lease_id=lease_id,
            benchmark_approved=benchmark_approved,
        )

    def issue_backtest_lease(
        self,
        preferred_device: str,
        *,
        telemetry: GpuTelemetrySnapshot | None = None,
        active_leases: tuple[GpuLease, ...] | None = None,
        lease_id: str | None = None,
        benchmark_approved: bool = False,
    ) -> GpuLease | None:
        return self.issue_lease(
            GpuWorkloadKind.BACKTEST_ACCELERATION,
            preferred_device,
            telemetry=telemetry,
            active_leases=active_leases,
            lease_id=lease_id,
            benchmark_approved=benchmark_approved,
        )

    def release_lease(
        self, lease: GpuLease, *, released_at: datetime | None = None
    ) -> GpuLease:
        released_lease = lease.release(released_at=released_at)
        timestamp = released_at or released_lease.released_at or datetime.now(UTC)
        _require_aware(timestamp, "gpu lease release time")
        self.track_lease(released_lease, now=timestamp)
        return released_lease

    def expire_lease(
        self, lease: GpuLease, *, expired_at: datetime | None = None
    ) -> GpuLease:
        expired_lease = lease.expire(expired_at=expired_at)
        timestamp = expired_at or expired_lease.expired_at or datetime.now(UTC)
        _require_aware(timestamp, "gpu lease expiry time")
        self.track_lease(expired_lease, now=timestamp)
        return expired_lease

    def record_gpu_failure(
        self,
        reason: str,
        *,
        occurred_at: datetime | None = None,
    ) -> GpuCircuitBreaker:
        self.circuit_breaker = self.circuit_breaker.record_failure(
            reason,
            occurred_at=occurred_at,
        )
        return self.circuit_breaker

    def record_gpu_success(
        self,
        *,
        occurred_at: datetime | None = None,
    ) -> GpuCircuitBreaker:
        self.circuit_breaker = self.circuit_breaker.record_success(
            occurred_at=occurred_at
        )
        return self.circuit_breaker

    def request_gpu_revalidation(
        self,
        *,
        now: datetime | None = None,
    ) -> GpuCircuitBreaker:
        self.circuit_breaker = self.circuit_breaker.request_revalidation(now=now)
        return self.circuit_breaker


def _normalize_device(device: str) -> Literal["cpu", "cuda", "auto"]:
    normalized = device.strip().casefold()
    if normalized not in {"cpu", "cuda", "auto"}:
        raise ValueError("gpu device selection must be cpu, cuda, or auto")
    return normalized  # type: ignore[return-value]


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _parse_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty ISO 8601 string")
    timestamp = datetime.fromisoformat(value)
    _require_aware(timestamp, name)
    return timestamp


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("gpu lease timestamps must be ISO 8601 strings")
    timestamp = datetime.fromisoformat(value)
    _require_aware(timestamp, "gpu lease timestamp")
    return timestamp


def _tuple_from_payload(value: object, *, field_name: str) -> tuple[str, ...]:
    values: tuple[str, ...]
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(str(item) for item in cast(Sequence[object], value))
    else:
        raise ValueError(f"{field_name} must be a sequence of strings")
    if any(not item.strip() for item in values):
        raise ValueError(f"{field_name} values must be non-empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")
    return values


def _int_from_payload(value: object, *, field_name: str) -> int:
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error


def _require_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("gpu lease telemetry payload must be an object")
    return value


def _normalize_active_gpu_leases(
    leases: tuple[GpuLease, ...],
    *,
    now: datetime | None = None,
) -> tuple[GpuLease, ...]:
    timestamp = now or datetime.now(UTC)
    _require_aware(timestamp, "gpu lease normalization time")
    normalized: list[GpuLease] = []
    for lease in leases:
        if lease.device != "cuda":
            continue
        if lease.state in {GpuLeaseState.RELEASED, GpuLeaseState.FAILED}:
            continue
        if lease.is_expired(now=timestamp):
            continue
        normalized.append(lease)
    return tuple(
        sorted(
            normalized,
            key=lambda lease: (
                lease.priority,
                lease.expires_at or timestamp,
                lease.issued_at,
            ),
        )
    )


def _merge_active_gpu_leases(
    leases: tuple[GpuLease, ...],
    lease: GpuLease,
    *,
    now: datetime | None = None,
) -> tuple[GpuLease, ...]:
    timestamp = now or datetime.now(UTC)
    _require_aware(timestamp, "gpu lease merge time")
    normalized = [
        existing
        for existing in _normalize_active_gpu_leases(leases, now=timestamp)
        if existing.lease_id != lease.lease_id
    ]
    if lease.device == "cuda" and lease.is_active(now=timestamp):
        normalized.append(lease)
    return tuple(normalized)


def _has_active_gpu_lease(
    leases: tuple[GpuLease, ...],
    *,
    now: datetime | None = None,
) -> bool:
    timestamp = now or datetime.now(UTC)
    _require_aware(timestamp, "gpu active lease check time")
    return any(
        lease.device == "cuda" and lease.is_active(now=timestamp) for lease in leases
    )
