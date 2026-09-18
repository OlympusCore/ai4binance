from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ai4binance.events import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    TraceabilityRequirement,
    TraceabilityStatus,
    canonical_trace_journal_path,
    canonical_trace_sha256,
)

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VNEXT_REQUIREMENT_IDS = tuple(f"RQ-{index:03d}" for index in range(1, 21))
VNEXT_RQ_002_FULL_EVIDENCE = Path("runtime/quality/20260905T170244Z/summary.json")
VNEXT_RQ_004_FULL_EVIDENCE = Path("runtime/quality/20260905T183547Z/summary.json")
VNEXT_RQ_006_FULL_EVIDENCE = Path("runtime/quality/20260905T191135Z/summary.json")
VNEXT_RQ_007_FULL_EVIDENCE = Path("runtime/quality/20260905T200507Z/summary.json")
VNEXT_RQ_009_FULL_EVIDENCE = Path("runtime/quality/20260905T153839Z/summary.json")
VNEXT_RQ_012_FULL_EVIDENCE = Path("runtime/quality/20260905T205043Z/summary.json")
VNEXT_RQ_013_BLOCKER_EVIDENCE = Path(
    "runtime/artifacts/vnext_convergence/"
    "0adb5228447e9cee6d933c2a73b317397792c93f1d41a5261ba6ae343fb28342/"
    "rq-013-oos-promotion-audit.json"
)
VNEXT_RQ_014_FULL_EVIDENCE = Path("runtime/quality/20260908T145803Z/summary.json")
VNEXT_FULL_ASSURANCE_EVIDENCE = Path("runtime/quality/20260908T215129Z/summary.json")
VNEXT_RQ_015_BLOCKER_EVIDENCE = Path(
    "runtime/artifacts/security/security-weekly-deep-20260908T151017Z.json"
)
VNEXT_RQ_016_BLOCKER_EVIDENCE = Path(
    "runtime/artifacts/vnext_convergence/vnxt-020-r1-preflight/"
    "rq-014-rq-016-convergence-preflight.json"
)
AUDITED_BLOCKER_EVIDENCE = {
    "RQ-013": VNEXT_RQ_013_BLOCKER_EVIDENCE,
    "RQ-015": VNEXT_RQ_015_BLOCKER_EVIDENCE,
    "RQ-016": VNEXT_RQ_016_BLOCKER_EVIDENCE,
}
VNEXT_C3_REPLAY_CLOSURE = Path(
    "runtime/artifacts/vnext_convergence/"
    "244dc9d33780eab069276e9ea376012f00f6d2dcc4881976d9ef4be59ab9d8a8/"
    "c3-replay-closure.json"
)
UNVERIFIED_CONVERGENCE_MARKERS = (
    "PARTIAL",
    "EVIDENCE_STALE",
    "BLOCKED_BY",
    "RUNNING_WITH_BLOCKERS",
    "GOVERNANCE_CONFLICT",
    "RESEARCH_ONLY",
)


def test_vnext_requirement_traceability_is_complete_and_fail_closed() -> None:
    inventory_path = REPOSITORY_ROOT / "config/governance/enforcement_inventory.yaml"
    compliance_path = REPOSITORY_ROOT / "docs/compliance/registry_compliance_matrix.md"
    payload = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    traceability = payload["requirement_traceability"]
    entries = traceability["entries"]
    entrypoint_ids = {entry["entrypoint_id"] for entry in payload["entries"]}
    requirement_ids = tuple(entry["requirement_id"] for entry in entries)

    assert requirement_ids == EXPECTED_VNEXT_REQUIREMENT_IDS
    assert len(set(requirement_ids)) == len(requirement_ids)
    assert traceability["canonical_owner"] == (
        "docs/compliance/registry_compliance_matrix.md"
    )
    assert traceability["source_class"] == "DESIGN_INPUT"
    assert traceability["manifest_id"] == (
        "244dc9d33780eab069276e9ea376012f00f6d2dcc4881976d9ef4be59ab9d8a8"
    )
    assert traceability["invariants"] == {
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

    allowed_statuses = set(traceability["allowed_trace_statuses"])
    for entry in entries:
        assert entry["source_documents"]
        assert entry["canonical_meaning"].strip()
        assert entry["canonical_owner"].strip()
        assert entry["trace_status"] in allowed_statuses
        assert set(entry["enforcement_entrypoints"]) <= entrypoint_ids
        assert len(entry["evidence_sha256"]) == 64
        for reference_key in ("authority_ref", "machine_readable_ref"):
            assert (REPOSITORY_ROOT / entry[reference_key]).is_file()
        evidence_path = Path(entry["evidence_ref"])
        if entry["requirement_id"] in {
            "RQ-001",
            "RQ-003",
            "RQ-005",
            "RQ-008",
            "RQ-010",
            "RQ-011",
            "RQ-019",
            "RQ-020",
        }:
            assert evidence_path == VNEXT_FULL_ASSURANCE_EVIDENCE
        elif entry["requirement_id"] == "RQ-002":
            assert evidence_path == VNEXT_RQ_002_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-004":
            assert evidence_path == VNEXT_RQ_004_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-006":
            assert evidence_path == VNEXT_RQ_006_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-007":
            assert evidence_path == VNEXT_RQ_007_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-009":
            assert evidence_path == VNEXT_RQ_009_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-012":
            assert evidence_path == VNEXT_RQ_012_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-013":
            assert evidence_path == VNEXT_RQ_013_BLOCKER_EVIDENCE
        elif entry["requirement_id"] == "RQ-014":
            assert evidence_path == VNEXT_RQ_014_FULL_EVIDENCE
        elif entry["requirement_id"] == "RQ-015":
            assert evidence_path == VNEXT_RQ_015_BLOCKER_EVIDENCE
        elif entry["requirement_id"] == "RQ-016":
            assert evidence_path == VNEXT_RQ_016_BLOCKER_EVIDENCE
        elif entry["requirement_id"] in {"RQ-017", "RQ-018"}:
            assert evidence_path == VNEXT_C3_REPLAY_CLOSURE
        else:
            assert evidence_path.parts[:4] == (
                "runtime",
                "artifacts",
                "quality",
                "gate",
            )
        assert evidence_path.suffix == ".json"
        for reference_key in ("implementation_refs", "test_refs"):
            assert entry[reference_key]
            assert all(
                (REPOSITORY_ROOT / relative_path).is_file()
                for relative_path in entry[reference_key]
            )
        has_unverified_marker = any(
            marker in entry["convergence_state"]
            for marker in UNVERIFIED_CONVERGENCE_MARKERS
        )
        is_audited_blocker = (
            entry["requirement_id"] in AUDITED_BLOCKER_EVIDENCE
            and entry["trace_status"] == "AUDIT_VERIFIED"
            and evidence_path == AUDITED_BLOCKER_EVIDENCE[entry["requirement_id"]]
        )
        if has_unverified_marker and not is_audited_blocker:
            assert entry["trace_status"] != "AUDIT_VERIFIED"

    compliance_text = compliance_path.read_text(encoding="utf-8")
    assert all(
        compliance_text.count(f"| {requirement_id} |") == 1
        for requirement_id in EXPECTED_VNEXT_REQUIREMENT_IDS
    )
    rq_002 = next(entry for entry in entries if entry["requirement_id"] == "RQ-002")
    assert rq_002["trace_status"] == "AUDIT_VERIFIED"
    assert rq_002["convergence_state"] == "SATISFIED"
    assert rq_002["evidence_ref"] == VNEXT_RQ_002_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-002 | One source of truth and authority / Enterprise Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_004 = next(entry for entry in entries if entry["requirement_id"] == "RQ-004")
    assert rq_004["trace_status"] == "AUDIT_VERIFIED"
    assert rq_004["convergence_state"] == "SATISFIED"
    assert rq_004["evidence_ref"] == VNEXT_RQ_004_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-004 | Deterministic decision chain / Decision Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_006 = next(entry for entry in entries if entry["requirement_id"] == "RQ-006")
    assert rq_006["trace_status"] == "AUDIT_VERIFIED"
    assert rq_006["convergence_state"] == "SATISFIED"
    assert rq_006["evidence_ref"] == VNEXT_RQ_006_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-006 | Governed contract and schema fabric / Contract Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_007 = next(entry for entry in entries if entry["requirement_id"] == "RQ-007")
    assert rq_007["trace_status"] == "AUDIT_VERIFIED"
    assert rq_007["convergence_state"] == "SATISFIED"
    assert rq_007["evidence_ref"] == VNEXT_RQ_007_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-007 | Bounded agent architecture / Agent Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_009 = next(entry for entry in entries if entry["requirement_id"] == "RQ-009")
    assert rq_009["trace_status"] == "AUDIT_VERIFIED"
    assert rq_009["convergence_state"] == "SATISFIED"
    assert rq_009["evidence_ref"] == VNEXT_RQ_009_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-009 | Governed non-authoritative memory / Knowledge Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_012 = next(entry for entry in entries if entry["requirement_id"] == "RQ-012")
    assert rq_012["trace_status"] == "AUDIT_VERIFIED"
    assert rq_012["convergence_state"] == "SATISFIED"
    assert rq_012["evidence_ref"] == VNEXT_RQ_012_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-012 | Virtual market and paper execution / Research Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_013 = next(entry for entry in entries if entry["requirement_id"] == "RQ-013")
    assert rq_013["trace_status"] == "AUDIT_VERIFIED"
    assert rq_013["convergence_state"] == "BLOCKED_BY_OOS_PROMOTION_EVIDENCE"
    assert rq_013["evidence_ref"] == VNEXT_RQ_013_BLOCKER_EVIDENCE.as_posix()
    rq_013_evidence = yaml.safe_load(
        (REPOSITORY_ROOT / VNEXT_RQ_013_BLOCKER_EVIDENCE).read_text(encoding="utf-8")
    )
    assert rq_013_evidence["source_run_card_count"] == 40
    assert rq_013_evidence["promotion_status_counts"] == {
        "RESEARCH_ONLY": 40,
        "STAGED_CANDIDATE": 0,
        "PAPER_APPROVED": 0,
        "LIVE_ELIGIBLE": 0,
    }
    assert rq_013_evidence["blocker_free_run_card_count"] == 0
    assert rq_013_evidence["decision"] == "KEEP_RESEARCH_ONLY"
    assert rq_013_evidence["thresholds_modified"] is False
    assert rq_013_evidence["promotion_performed"] is False
    assert rq_013_evidence["execution_allowed"] is False
    assert rq_013_evidence["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert (
        "| RQ-013 | Research, OOS, and human-governed promotion lifecycle / "
        "Validation Governance | AUDIT_VERIFIED | "
        "BLOCKED_BY_OOS_PROMOTION_EVIDENCE |"
    ) in compliance_text
    rq_014 = next(entry for entry in entries if entry["requirement_id"] == "RQ-014")
    assert rq_014["trace_status"] == "AUDIT_VERIFIED"
    assert rq_014["convergence_state"] == "SATISFIED"
    assert rq_014["evidence_ref"] == VNEXT_RQ_014_FULL_EVIDENCE.as_posix()
    assert (
        "| RQ-014 | Cold-path external intelligence and GitHub Radar / "
        "External Intelligence Governance | AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_015 = next(entry for entry in entries if entry["requirement_id"] == "RQ-015")
    assert rq_015["trace_status"] == "AUDIT_VERIFIED"
    assert rq_015["convergence_state"] == "BLOCKED_BY_EXTERNAL_SECURITY_EVIDENCE"
    assert rq_015["evidence_ref"] == VNEXT_RQ_015_BLOCKER_EVIDENCE.as_posix()
    rq_015_evidence = yaml.safe_load(
        (REPOSITORY_ROOT / VNEXT_RQ_015_BLOCKER_EVIDENCE).read_text(encoding="utf-8")
    )
    assert rq_015_evidence["status"] == "BLOCKED"
    assert set(rq_015_evidence["blockers"]) == {
        "CVE_ADVISORY_SOURCE_MISSING",
        "MFA_PROVIDER_ATTESTATION_MISSING",
        "RESTORE_TEST_EVIDENCE_MISSING",
        "WORM_STORAGE_EVIDENCE_MISSING",
    }
    assert rq_015_evidence["execution_allowed"] is False
    assert rq_015_evidence["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert (
        "| RQ-015 | Security, privacy, and local-only sensitive data / "
        "Security Governance | AUDIT_VERIFIED | "
        "BLOCKED_BY_EXTERNAL_SECURITY_EVIDENCE |"
    ) in compliance_text
    rq_016 = next(entry for entry in entries if entry["requirement_id"] == "RQ-016")
    assert rq_016["trace_status"] == "AUDIT_VERIFIED"
    assert rq_016["convergence_state"] == "BLOCKED_BY_COMPATIBILITY_EVIDENCE"
    assert rq_016["evidence_ref"] == VNEXT_RQ_016_BLOCKER_EVIDENCE.as_posix()
    rq_016_evidence = yaml.safe_load(
        (REPOSITORY_ROOT / VNEXT_RQ_016_BLOCKER_EVIDENCE).read_text(encoding="utf-8")
    )
    rq_016_audit = next(
        audit
        for audit in rq_016_evidence["requirement_audits"]
        if audit["requirement_id"] == "RQ-016"
    )
    architecture = rq_016_audit["architecture_observation"]
    assert architecture["classification_coverage_percent"] == 100.0
    assert architecture["import_cycle_count"] == 0
    assert architecture["blocked_classification_count"] == 516
    assert architecture["target_path_collision_count"] == 16
    assert rq_016_evidence["execution_allowed"] is False
    assert rq_016_evidence["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert (
        "| RQ-016 | Dependency-guarded architecture migration / "
        "Architecture Governance | AUDIT_VERIFIED | "
        "BLOCKED_BY_COMPATIBILITY_EVIDENCE |"
    ) in compliance_text
    rq_017 = next(entry for entry in entries if entry["requirement_id"] == "RQ-017")
    assert rq_017["trace_status"] == "AUDIT_VERIFIED"
    assert rq_017["convergence_state"] == "SATISFIED"
    assert rq_017["evidence_ref"] == VNEXT_C3_REPLAY_CLOSURE.as_posix()
    assert (
        "| RQ-017 | Quality and evidence closure / Quality Governance | "
        "AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_018 = next(entry for entry in entries if entry["requirement_id"] == "RQ-018")
    assert rq_018["trace_status"] == "AUDIT_VERIFIED"
    assert rq_018["convergence_state"] == "SATISFIED"
    assert rq_018["evidence_ref"] == VNEXT_C3_REPLAY_CLOSURE.as_posix()
    assert (
        "| RQ-018 | Documentation factual and lock alignment / "
        "Knowledge Governance | AUDIT_VERIFIED | SATISFIED |"
    ) in compliance_text
    rq_019 = next(entry for entry in entries if entry["requirement_id"] == "RQ-019")
    assert rq_019["trace_status"] == "AUDIT_VERIFIED"
    assert traceability["invariants"]["execution_allowed"] is False
    assert traceability["invariants"]["live_eligibility_status"] == (
        "LIVE_ORDER_BLOCKED"
    )


def test_canonical_trace_journal_round_trips_and_passes_audit(
    tmp_path: Path,
) -> None:
    journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))
    subject_ref = "decision:hotusdt:cycle-1"
    record = CanonicalTraceRecord.create(
        trace_id="trace:decision:1",
        trace_kind=ConsequentialTraceKind.DECISION,
        subject_ref=subject_ref,
        subject_type="DECISION_PROVENANCE_RECORD",
        occurred_at=NOW,
        event_name="DECISION_PROVENANCE_RECORDED",
        event_status="NO_TRADE",
        evidence_refs=("evidence:decision",),
        blockers=("LIVE_ORDER_BLOCKED",),
        related_refs=("policy:decision-1", "uncertainty:decision-1"),
        subject_sha256=canonical_trace_sha256({"decision_id": subject_ref}),
    )

    journal.append(record)
    audit = journal.audit(
        (
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.DECISION,
                subject_ref=subject_ref,
                event_name="DECISION_PROVENANCE_RECORDED",
                subject_type="DECISION_PROVENANCE_RECORD",
            ),
        )
    )

    assert journal.records() == (record,)
    assert audit.status is TraceabilityStatus.PASS
    assert audit.journal_path == canonical_trace_journal_path(tmp_path).resolve()


def test_traceability_audit_blocks_missing_requirement(tmp_path: Path) -> None:
    journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))
    config_path = (tmp_path / "runtime" / "state" / "config.json").resolve()

    audit = journal.audit(
        (
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.CONFIG_CHANGE,
                subject_ref=str(config_path),
                event_name="GOVERNED_PARAMETER_ACTIVATED",
                subject_type="GOVERNED_PARAMETER_STORE",
                approval_ref="approval-1",
            ),
        )
    )

    assert audit.status is TraceabilityStatus.RUNNING_WITH_BLOCKERS
    assert "CANONICAL_TRACE_JOURNAL_EMPTY" in audit.blockers
    assert "CANONICAL_TRACE_REQUIREMENT_MISSING" in audit.blockers
    assert len(audit.missing_requirements) == 1


def test_canonical_trace_record_rejects_governed_change_without_path() -> None:
    with pytest.raises(
        ValueError,
        match="governed/config change trace requires governed paths",
    ):
        CanonicalTraceRecord.create(
            trace_id="trace:config:1",
            trace_kind=ConsequentialTraceKind.CONFIG_CHANGE,
            subject_ref="config/runtime/state.json",
            subject_type="GOVERNED_PARAMETER_STORE",
            occurred_at=NOW,
            event_name="GOVERNED_PARAMETER_ACTIVATED",
            event_status="PAPER_APPROVED",
            evidence_refs=("approval-1",),
            approval_ref="approval-1",
            subject_sha256=canonical_trace_sha256({"revision": 1}),
        )
