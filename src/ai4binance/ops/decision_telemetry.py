"""Decision telemetry persistence, human reports, and compatibility exports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.domain.evidence.decision_telemetry import (
    _GENESIS_HASH,
    _canonical_sha256,
)
from ai4binance.domain.evidence.decision_telemetry import (
    AcceptanceGateStatus as AcceptanceGateStatus,
)
from ai4binance.domain.evidence.decision_telemetry import (
    AttributionMethod as AttributionMethod,
)
from ai4binance.domain.evidence.decision_telemetry import (
    BlockerEffectivenessRecord as BlockerEffectivenessRecord,
)
from ai4binance.domain.evidence.decision_telemetry import (
    BlockerOutcome as BlockerOutcome,
)
from ai4binance.domain.evidence.decision_telemetry import (
    CanonicalTelemetrySnapshot as CanonicalTelemetrySnapshot,
)
from ai4binance.domain.evidence.decision_telemetry import (
    CounterfactualOutcome as CounterfactualOutcome,
)
from ai4binance.domain.evidence.decision_telemetry import (
    CounterfactualType as CounterfactualType,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionEffectivenessClass as DecisionEffectivenessClass,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionEffectivenessRecord as DecisionEffectivenessRecord,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionInputRecord as DecisionInputRecord,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionOutcomeRecord as DecisionOutcomeRecord,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionProcessRecord as DecisionProcessRecord,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionTelemetryFabricRecord as DecisionTelemetryFabricRecord,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DecisionTelemetryStatus as DecisionTelemetryStatus,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DgeEffectivenessMetrics as DgeEffectivenessMetrics,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DgeEffectivenessStatus as DgeEffectivenessStatus,
)
from ai4binance.domain.evidence.decision_telemetry import (
    DgeRuleEffectivenessMetrics as DgeRuleEffectivenessMetrics,
)
from ai4binance.domain.evidence.decision_telemetry import (
    EvidenceQuality as EvidenceQuality,
)
from ai4binance.domain.evidence.decision_telemetry import (
    ImprovementCandidate as ImprovementCandidate,
)
from ai4binance.domain.evidence.decision_telemetry import (
    LineageCompletenessResult as LineageCompletenessResult,
)
from ai4binance.domain.evidence.decision_telemetry import (
    LineageStatus as LineageStatus,
)
from ai4binance.domain.evidence.decision_telemetry import (
    MarketType as MarketType,
)
from ai4binance.domain.evidence.decision_telemetry import (
    MetricEvidence as MetricEvidence,
)
from ai4binance.domain.evidence.decision_telemetry import (
    OpportunityCostType as OpportunityCostType,
)
from ai4binance.domain.evidence.decision_telemetry import (
    OutcomeAttribution as OutcomeAttribution,
)
from ai4binance.domain.evidence.decision_telemetry import (
    OutcomeLifecycle as OutcomeLifecycle,
)
from ai4binance.domain.evidence.decision_telemetry import (
    PerformanceAcceptanceResult as PerformanceAcceptanceResult,
)
from ai4binance.domain.evidence.decision_telemetry import (
    PerformanceEvidenceSnapshot as PerformanceEvidenceSnapshot,
)
from ai4binance.domain.evidence.decision_telemetry import (
    TelemetryDomain as TelemetryDomain,
)
from ai4binance.domain.evidence.decision_telemetry import (
    build_performance_evidence_snapshot as build_performance_evidence_snapshot,
)
from ai4binance.domain.evidence.decision_telemetry import (
    evaluate_lineage_completeness as evaluate_lineage_completeness,
)
from ai4binance.ops.user_reports import (
    UserReportPaths,
    render_professional_summary,
    user_report_paths,
)
from ai4binance.storage.destination_verification import (
    VerifiedWriteResult,
    write_json_object_verified,
)
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class DecisionTelemetryWriteResult:
    record: DecisionTelemetryFabricRecord
    ledger_write: VerifiedWriteResult
    latest_json_write: VerifiedWriteResult
    latest_markdown_path: Path


@dataclass(frozen=True, slots=True)
class DecisionTelemetryLedger:
    """Append-only telemetry ledger with user-facing latest report output."""

    repository_root: Path
    durable: bool = True

    @property
    def ledger_path(self) -> Path:
        return (
            self.repository_root
            / "runtime"
            / "state"
            / "decision_telemetry"
            / "decision-telemetry.jsonl"
        )

    @property
    def latest_json_path(self) -> Path:
        return self._latest_paths().latest_json_path

    @property
    def latest_markdown_path(self) -> Path:
        return self._latest_paths().latest_markdown_path

    def verify_integrity(self) -> str:
        if not self.ledger_path.exists():
            return _GENESIS_HASH
        raw = self.ledger_path.read_bytes()
        if not raw:
            return _GENESIS_HASH
        if not raw.endswith(b"\n"):
            raise ValueError("decision telemetry ledger has a partial final record")

        expected_previous_hash = _GENESIS_HASH
        for line_number, raw_line in enumerate(raw.splitlines(), start=1):
            if not raw_line.strip():
                raise ValueError(
                    f"decision telemetry ledger line {line_number} is empty"
                )
            event = _mapping_from_json_bytes(
                raw_line,
                label=f"decision telemetry ledger line {line_number}",
            )
            payload = _mapping_field(
                event,
                "payload",
                label=f"decision telemetry ledger line {line_number}",
            )
            snapshot = _mapping_field(
                payload,
                "performance_snapshot",
                label=f"decision telemetry ledger line {line_number}",
            )
            snapshot_id = _text_field(
                snapshot,
                "snapshot_id",
                label=f"decision telemetry ledger line {line_number}",
            )
            observed_at = _text_field(
                payload,
                "observed_at",
                label=f"decision telemetry ledger line {line_number}",
            )
            payload_hash = _text_field(
                payload,
                "payload_hash",
                label=f"decision telemetry ledger line {line_number}",
            )
            previous_record_hash = _text_field(
                payload,
                "previous_record_hash",
                label=f"decision telemetry ledger line {line_number}",
            )
            fabric_id = _text_field(
                payload,
                "fabric_id",
                label=f"decision telemetry ledger line {line_number}",
            )
            record_hash = _text_field(
                payload,
                "record_hash",
                label=f"decision telemetry ledger line {line_number}",
            )
            event_type = _text_field(
                event,
                "event_type",
                label=f"decision telemetry ledger line {line_number}",
            )
            event_timestamp = _text_field(
                event,
                "timestamp",
                label=f"decision telemetry ledger line {line_number}",
            )
            event_snapshot_id = _text_field(
                event,
                "snapshot_id",
                label=f"decision telemetry ledger line {line_number}",
            )

            expected_payload_hash = _canonical_sha256(snapshot)
            expected_fabric_id = (
                f"decision-telemetry:{snapshot_id}:{expected_payload_hash[:16]}"
            )
            expected_record_hash = _canonical_sha256(
                {
                    "fabric_id": expected_fabric_id,
                    "observed_at": observed_at,
                    "payload_hash": expected_payload_hash,
                    "previous_record_hash": expected_previous_hash,
                    "snapshot_id": snapshot_id,
                }
            )
            if event_type != "DECISION_TELEMETRY_EVIDENCE":
                raise ValueError(
                    "decision telemetry ledger line "
                    f"{line_number} event_type is invalid"
                )
            if event_timestamp != observed_at:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} timestamp mismatch"
                )
            if event_snapshot_id != snapshot_id:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} snapshot_id mismatch"
                )
            if previous_record_hash != expected_previous_hash:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} hash chain is broken"
                )
            if payload_hash != expected_payload_hash:
                raise ValueError(
                    "decision telemetry ledger line "
                    f"{line_number} payload hash is invalid"
                )
            if fabric_id != expected_fabric_id:
                raise ValueError(
                    f"decision telemetry ledger line {line_number} fabric_id is invalid"
                )
            if record_hash != expected_record_hash:
                raise ValueError(
                    "decision telemetry ledger line "
                    f"{line_number} record hash is invalid"
                )
            expected_previous_hash = record_hash
        return expected_previous_hash

    def _latest_paths(self) -> UserReportPaths:
        return user_report_paths(
            self.repository_root,
            "audit",
            "performance_evidence",
            file_stem="performance_evidence",
            latest_stem="performance_evidence_latest",
        )

    def append(
        self, snapshot: PerformanceEvidenceSnapshot
    ) -> DecisionTelemetryWriteResult:
        record = DecisionTelemetryFabricRecord.seal(
            snapshot,
            previous_record_hash=self.verify_integrity(),
        )
        payload = record.to_payload()
        ledger_write = JsonlAuditStore(
            self.ledger_path,
            durable=self.durable,
        ).append_verified(
            AuditEvent(
                event_type="DECISION_TELEMETRY_EVIDENCE",
                timestamp=record.observed_at,
                payload=payload,
                snapshot_id=snapshot.snapshot_id,
            )
        )
        latest_json_write = write_json_object_verified(
            self.latest_json_path,
            payload,
            blocker="DECISION_TELEMETRY_LATEST_DESTINATION_VERIFY_FAILED",
            subject_id=f"decision-telemetry:{snapshot.snapshot_id}",
            indent=2,
            durable=self.durable,
        )
        self.latest_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        self.latest_markdown_path.write_text(
            render_performance_evidence_markdown(record),
            encoding="utf-8",
        )
        return DecisionTelemetryWriteResult(
            record=record,
            ledger_write=ledger_write,
            latest_json_write=latest_json_write,
            latest_markdown_path=self.latest_markdown_path,
        )


def render_performance_evidence_markdown(
    record: DecisionTelemetryFabricRecord,
) -> str:
    """Render the latest telemetry evidence in the standard human report style."""

    snapshot = record.performance_snapshot
    outcome = snapshot.decision_outcome
    dge = snapshot.dge_metrics
    sections = (
        (
            "Lineage",
            (
                f"- Lineage status: `{snapshot.lineage.status.value}`",
                f"- Missing references: `{len(snapshot.lineage.missing_refs)}`",
                f"- Auto-Audit consumable: `{snapshot.auto_audit_consumable}`",
                f"- Auto-Learn consumable: `{snapshot.auto_learn_consumable}`",
            ),
        ),
        (
            "NO_TRADE Outcome Measurement",
            (
                f"- Observation window: `{outcome.observation_window_minutes}` minutes",
                f"- Maximum favorable move: `{outcome.max_favorable_move_usdt}` USDT",
                f"- Maximum adverse move: `{outcome.max_adverse_move_usdt}` USDT",
                f"- Counterfactual return: `{outcome.counterfactual_return_usdt}` USDT",
                f"- Measurable NO_TRADE: `{outcome.measurable_no_trade}`",
            ),
        ),
        (
            "DGE Effectiveness",
            (
                f"- Intervention count: `{dge.intervention_count}`",
                f"- Block rate: `{dge.block_rate}`",
                f"- Protective block rate: `{dge.protective_block_rate}`",
                f"- False block rate: `{dge.false_block_rate}`",
                f"- Net protection value: `{dge.net_protection_value_usdt}` USDT",
                (
                    f"- Drawdown reduction: `{dge.drawdown_reduction_pct}` "
                    "percentage points"
                ),
            ),
        ),
        (
            "Outcome Graph",
            (
                f"- Lifecycle state: `{snapshot.lifecycle_state.value}`",
                f"- Counterfactual paths: `{len(snapshot.counterfactuals)}`",
                f"- Outcome attributions: `{len(snapshot.attributions)}`",
                f"- Blocker effectiveness records: "
                f"`{len(snapshot.blocker_effectiveness)}`",
                f"- Decision effectiveness records: "
                f"`{len(snapshot.decision_effectiveness)}`",
                f"- Acceptance results: `{len(snapshot.acceptance_results)}`",
                f"- Improvement candidates: `{len(snapshot.improvement_candidates)}`",
            ),
        ),
        (
            "Canonical Telemetry",
            (
                (
                    f"- Telemetry id: `{snapshot.telemetry_snapshot.telemetry_id}`"
                    if snapshot.telemetry_snapshot is not None
                    else "- Telemetry id: `-`"
                ),
                (
                    "- Telemetry domains: `"
                    + ", ".join(
                        domain.value for domain in snapshot.telemetry_snapshot.domains
                    )
                    + "`"
                    if snapshot.telemetry_snapshot is not None
                    else "- Telemetry domains: `-`"
                ),
                (
                    "- Telemetry gate eligible: "
                    f"`{snapshot.telemetry_snapshot.gate_eligible}`"
                    if snapshot.telemetry_snapshot is not None
                    else "- Telemetry gate eligible: `-`"
                ),
            ),
        ),
        (
            "GPU Resource Governance",
            (
                (
                    f"- GPU assessment source: "
                    f"`{snapshot.gpu_telemetry_assessment.source_label}`"
                    if snapshot.gpu_telemetry_assessment is not None
                    else "- GPU assessment source: `-`"
                ),
                (
                    f"- GPU assessment healthy: "
                    f"`{snapshot.gpu_telemetry_assessment.healthy}`"
                    if snapshot.gpu_telemetry_assessment is not None
                    else "- GPU assessment healthy: `-`"
                ),
                (
                    "- GPU assessment blockers: `"
                    + ", ".join(snapshot.gpu_telemetry_assessment.blockers)
                    + "`"
                    if snapshot.gpu_telemetry_assessment is not None
                    else "- GPU assessment blockers: `-`"
                ),
            ),
        ),
        (
            "Ledger Integrity",
            (
                f"- Previous record hash: `{record.previous_record_hash}`",
                f"- Payload hash: `{record.payload_hash}`",
                f"- Record hash: `{record.record_hash}`",
            ),
        ),
    )
    return render_professional_summary(
        title="Decision Telemetry Performance Evidence",
        observed_at=record.observed_at.isoformat(),
        status=snapshot.status.value,
        summary=(
            "This report links the decision input, process, output, and outcome "
            "into a tamper-evident evidence record for audit and learning review."
        ),
        sections=sections,
        blockers=snapshot.lineage.blockers,
    )


def _mapping_from_json_bytes(raw: bytes, *, label: str) -> Mapping[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _mapping_field(
    payload: Mapping[str, object],
    field: str,
    *,
    label: str,
) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"{label} field {field} must be an object")
    return cast(Mapping[str, object], value)


def _text_field(payload: Mapping[str, object], field: str, *, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} field {field} must be non-empty text")
    return value
