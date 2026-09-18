"""Verified local persistence for redacted advisory fixture run evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified

if TYPE_CHECKING:
    from ai4binance.local_agent.advisory_runner import LocalAdvisoryFixtureRunnerResult


@dataclass(frozen=True, slots=True)
class LocalAdvisoryFixtureEvidenceStore:
    """Write redacted fixture outcomes atomically with tamper-evident audit."""

    evidence_path: Path
    audit_path: Path

    def __post_init__(self) -> None:
        if (
            not self.evidence_path.is_absolute()
            or not self.audit_path.is_absolute()
            or self.evidence_path.suffix != ".json"
            or self.audit_path.suffix != ".jsonl"
        ):
            raise ValueError("local advisory fixture evidence paths are invalid")

    def save(
        self,
        result: LocalAdvisoryFixtureRunnerResult,
        *,
        recorded_at: datetime,
    ) -> None:
        """Persist no prompts or response text, only redacted outcome evidence."""
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError(
                "local advisory fixture evidence timestamp must be timezone-aware"
            )
        payload = to_primitive(_payload(result, recorded_at=recorded_at))
        if not isinstance(payload, dict):
            raise TypeError("local advisory fixture evidence payload is invalid")
        write_json_object_verified(
            self.evidence_path,
            payload,
            blocker="LOCAL_ADVISORY_FIXTURE_EVIDENCE_DESTINATION_VERIFY_FAILED",
            subject_id=result.admission.run_card.run_card_id,
            indent=2,
        )
        JsonlAuditStore(
            self.audit_path,
            durable=True,
            tamper_evident=True,
        ).append_verified(
            AuditEvent(
                event_type="LOCAL_ADVISORY_FIXTURE_EVIDENCE_PERSISTED",
                timestamp=recorded_at,
                payload=payload,
                snapshot_id=result.admission.run_card.run_card_id,
            )
        )


def _payload(
    result: LocalAdvisoryFixtureRunnerResult,
    *,
    recorded_at: datetime,
) -> dict[str, object]:
    fixture_runs: tuple[dict[str, object], ...] = ()
    if result.harness_report is not None:
        fixture_runs = tuple(
            {
                "fixture_id": fixture_run.fixture_id,
                "status": fixture_run.status,
                "blockers": fixture_run.blockers,
                "trace_id": fixture_run.trace.trace_id if fixture_run.trace else None,
                "input_sha256": (
                    fixture_run.trace.input_sha256 if fixture_run.trace else None
                ),
                "output_sha256": (
                    fixture_run.trace.output_sha256 if fixture_run.trace else None
                ),
                "evaluation_passed": (
                    fixture_run.evaluation.passed if fixture_run.evaluation else None
                ),
            }
            for fixture_run in result.harness_report.fixture_runs
        )
    return {
        "schema_version": "1.0.0",
        "recorded_at": recorded_at.isoformat(),
        "runner_id": result.admission.runner_id,
        "job_id": result.admission.job_id,
        "run_card_id": result.admission.run_card.run_card_id,
        "admission_status": result.admission.status.value,
        "admission_blockers": result.admission.blockers,
        "status": result.status,
        "blockers": result.blockers,
        "fixture_runs": fixture_runs,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
