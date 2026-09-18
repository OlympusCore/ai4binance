from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.cli import main
from ai4binance.enterprise.vnext_gap_audit import (
    VnextCapabilityGap,
    VnextClaimStatus,
    VnextEvidenceDepth,
    VnextGapAuditReport,
    VnextGapStatus,
    _production_evidence_blockers,
    build_vnext_gap_audit,
)
from ai4binance.governance.constitution_sync import (
    build_quality_gate_workspace_attestation,
)

NOW = datetime(2026, 9, 12, 2, 0, tzinfo=UTC)


def _write_quality_evidence(
    root: Path,
    *,
    status: str = "TECHNICAL_QUALITY_PASS",
    coverage_policy_result: str = "PASS",
) -> None:
    proof_path = root / "runtime/artifacts/quality/gate/coverage_summary.md"
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text("coverage proof", encoding="utf-8")
    proof_hash = sha256(proof_path.read_bytes()).hexdigest()
    payload = {
        "schema_version": 2,
        "status": status,
        "verification_status": "FULL_VERIFIED",
        "canonical_quality_authority": True,
        "full_assurance_status": "FULL_ASSURANCE_GREEN",
        "generated_at_utc": "2026-09-02T00:00:00+00:00",
        "command": "quality",
        "pytest_pass_count": 1,
        "coverage_percent": 90.0,
        "coverage_source": "coverage.py json totals.percent_covered",
        "coverage_policy_summary": {
            "policy_result": coverage_policy_result,
        },
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "coverage_realism_proof": {
            "markdown_path": "runtime/artifacts/quality/gate/coverage_summary.md",
            "markdown_sha256": proof_hash,
        },
        "workspace_attestation": build_quality_gate_workspace_attestation(
            root
        ).to_payload(),
    }
    evidence_path = root / "runtime/artifacts/quality/gate/latest.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")


def _quality_baseline(report: VnextGapAuditReport) -> VnextCapabilityGap:
    return next(
        item
        for item in report.capabilities
        if item.capability_id == "VNEXT-00A-QUALITY-BASELINE"
    )


def test_vnext_gap_audit_maps_local_evidence_without_execution() -> None:
    root = Path(__file__).resolve().parents[1]

    report = build_vnext_gap_audit(root)
    payload = report.to_payload()

    assert payload["command"] == "vnext-gap-audit"
    assert payload["source_profile"] == "AI4BINANCE_ENTERPRISEAI_VNEXT_V1_2"
    assert report.summary_counts[VnextGapStatus.COMPLETE.value] >= 1
    assert report.status in {"READY", "RUNNING_WITH_BLOCKERS"}
    assert "VNEXT-00B-UNIVERSAL-ENFORCEMENT" not in report.top_gaps
    assert any(
        item.capability_id == "VNEXT-02-RECOVERY-RADAR" for item in report.capabilities
    )
    quality_baseline = _quality_baseline(report)
    assert quality_baseline.claim_verifier == "QUALITY_BASELINE"
    assert quality_baseline.claim_status in {
        VnextClaimStatus.PARTIAL,
        VnextClaimStatus.VERIFIED,
    }
    assert quality_baseline.status in {VnextGapStatus.PARTIAL, VnextGapStatus.COMPLETE}
    enforcement_closure = next(
        item
        for item in report.capabilities
        if item.capability_id == "VNEXT-00B-UNIVERSAL-ENFORCEMENT"
    )
    assert enforcement_closure.claim_verifier == "ENFORCEMENT_CLOSURE"
    assert enforcement_closure.claim_status is VnextClaimStatus.VERIFIED
    assert enforcement_closure.status is VnextGapStatus.COMPLETE
    assert enforcement_closure.missing_controls == ()
    assert enforcement_closure.proposed_diff == ()
    recovery = next(
        item
        for item in report.capabilities
        if item.capability_id == "VNEXT-02-RECOVERY-RADAR"
    )
    assert recovery.evidence_depth in {
        VnextEvidenceDepth.TESTED_CONTRACT,
        VnextEvidenceDepth.RUNTIME_WIRED,
        VnextEvidenceDepth.PRODUCTION_EVIDENCE,
    }
    assert recovery.runtime_wiring in {"VERIFIED", "WIRED", "NOT_VERIFIED"}
    scanner = next(
        item
        for item in report.capabilities
        if item.capability_id == "VNEXT-08-SPOT-FUTURES-SCANNER"
    )
    assert scanner.production_artifact_status in {"MISSING", "VERIFIED"}
    assert scanner.eval_status in {"EVIDENCE_GAP", "PRODUCTION_EVIDENCE_VERIFIED"}
    assert (
        "MULTI_SYMBOL_LIQUIDITY_FILTERED_SCAN_MISSING" not in scanner.missing_controls
    )
    assert "TOKEN_RISK_FILTERS_INCOMPLETE" not in scanner.missing_controls
    oos_automl = next(
        item
        for item in report.capabilities
        if item.capability_id == "VNEXT-07-OOS-AUTOML"
    )
    assert oos_automl.status in {VnextGapStatus.COMPLETE, VnextGapStatus.PARTIAL}
    assert oos_automl.production_artifact_status in {"MISSING", "VERIFIED"}
    runner_admission = next(
        item
        for item in report.capabilities
        if item.capability_id == "VNEXT-09-MULTIOPS-RUNNER-ADMISSION"
    )
    assert runner_admission.status is VnextGapStatus.COMPLETE
    assert runner_admission.runtime_wiring == "VERIFIED"
    assert report.summary_counts[VnextGapStatus.RESEARCH_ONLY.value] == 0
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "LIVE_ORDER_BLOCKED" in report.blockers
    assert report.status == "RUNNING_WITH_BLOCKERS"
    assert report.next_phase.endswith("_EVIDENCE_CLOSURE")
    assert report.requirement_traceability_status == "RUNNING_WITH_BLOCKERS"
    assert report.requirement_traceability_entry_count == 20
    assert report.requirement_traceability_converged_count == 17
    assert (
        "RQ-013:CONVERGENCE_BLOCKED_BY_OOS_PROMOTION_EVIDENCE"
        in report.requirement_traceability_blockers
    )
    assert not any(
        blocker.startswith("RQ-014:")
        for blocker in report.requirement_traceability_blockers
    )
    assert (
        "RQ-015:CONVERGENCE_BLOCKED_BY_EXTERNAL_SECURITY_EVIDENCE"
        in report.requirement_traceability_blockers
    )
    assert (
        "RQ-016:CONVERGENCE_BLOCKED_BY_COMPATIBILITY_EVIDENCE"
        in report.requirement_traceability_blockers
    )
    assert payload["requirement_traceability"] == {
        "status": "RUNNING_WITH_BLOCKERS",
        "entry_count": 20,
        "converged_count": 17,
        "blockers": list(report.requirement_traceability_blockers),
    }
    quality_baseline_blocker = (
        "VNEXT-00A-QUALITY-BASELINE:CURRENT_QUALITY_BASELINE_FAILED"
    )
    if quality_baseline.claim_status is VnextClaimStatus.VERIFIED:
        assert quality_baseline.missing_controls == ()
        assert quality_baseline_blocker not in report.blockers
    else:
        assert quality_baseline.claim_status is VnextClaimStatus.PARTIAL
        assert quality_baseline.missing_controls in {
            ("CURRENT_QUALITY_BASELINE_FAILED",),
            ("CURRENT_QUALITY_COVERAGE_POLICY_NOT_PASS",),
        }
        assert any(
            blocker.startswith("VNEXT-00A-QUALITY-BASELINE:")
            for blocker in report.blockers
        )
    assert not any(
        blocker.startswith("VNEXT-00B-UNIVERSAL-ENFORCEMENT:")
        for blocker in report.blockers
    )


def test_vnext_gap_audit_accepts_current_canonical_quality_evidence(
    tmp_path: Path,
) -> None:
    _write_quality_evidence(tmp_path)

    report = build_vnext_gap_audit(tmp_path)
    quality_baseline = _quality_baseline(report)

    assert quality_baseline.status is VnextGapStatus.COMPLETE
    assert quality_baseline.claim_status is VnextClaimStatus.VERIFIED
    assert quality_baseline.production_artifact_status == "VERIFIED"
    assert quality_baseline.eval_status == "TECHNICAL_QUALITY_PASS"


def test_vnext_gap_audit_rejects_stale_or_failed_quality_evidence(
    tmp_path: Path,
) -> None:
    _write_quality_evidence(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/changed.py").write_text("value = 1\n", encoding="utf-8")

    stale_report = build_vnext_gap_audit(tmp_path)
    stale_quality = _quality_baseline(stale_report)
    assert stale_quality.status is VnextGapStatus.PARTIAL
    assert stale_quality.eval_status == "MISSING_OR_STALE"

    _write_quality_evidence(tmp_path, status="QUALITY_GATE_FAILED")
    failed_report = build_vnext_gap_audit(tmp_path)
    failed_quality = _quality_baseline(failed_report)
    assert failed_quality.status is VnextGapStatus.PARTIAL
    assert failed_quality.production_artifact_status == "MISSING"


def test_vnext_gap_audit_exposes_coverage_policy_debt_as_a_blocker(
    tmp_path: Path,
) -> None:
    _write_quality_evidence(tmp_path, coverage_policy_result="BASELINE_DEBT")

    report = build_vnext_gap_audit(tmp_path)
    quality_baseline = _quality_baseline(report)

    assert quality_baseline.status is VnextGapStatus.PARTIAL
    assert quality_baseline.claim_status is VnextClaimStatus.PARTIAL
    assert quality_baseline.missing_controls == (
        "CURRENT_QUALITY_COVERAGE_POLICY_NOT_PASS",
    )
    assert quality_baseline.eval_status == "COVERAGE_POLICY_BASELINE_DEBT"
    assert report.status == "RUNNING_WITH_BLOCKERS"


def test_vnext_gap_audit_reports_missing_controls_in_empty_workspace(
    tmp_path: Path,
) -> None:
    report = build_vnext_gap_audit(tmp_path)

    assert report.status == "RUNNING_WITH_BLOCKERS"
    assert report.summary_counts[VnextGapStatus.MISSING.value] > 0
    assert report.capabilities[0].missing_controls
    assert all(not item.evidence_files for item in report.capabilities)
    assert all(
        item.evidence_depth is VnextEvidenceDepth.CODE_ONLY
        for item in report.capabilities
        if item.claim_verifier == "FILE_PRESENCE"
    )
    assert report.execution_allowed is False
    assert report.requirement_traceability_status == "MISSING"
    assert report.requirement_traceability_blockers == (
        "REQUIREMENT_TRACEABILITY_MISSING",
    )


def test_vnext_gap_audit_rejects_naive_observation_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_vnext_gap_audit(
            tmp_path,
            observed_at=datetime(2026, 9, 12, 2, 0),
        )


def test_vnext_gap_audit_fails_closed_on_invalid_requirement_traceability(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "config/governance/enforcement_inventory.yaml"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text("requirement_traceability: [\n", encoding="utf-8")

    report = build_vnext_gap_audit(tmp_path)

    assert report.status == "RUNNING_WITH_BLOCKERS"
    assert report.requirement_traceability_status == "INVALID"
    assert report.requirement_traceability_blockers == (
        "REQUIREMENT_TRACEABILITY_INVALID",
    )
    assert "REQUIREMENT_TRACEABILITY_INVALID" in report.blockers
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def _write_production_evidence(
    root: Path,
    relative_path: str,
    payload: dict[str, object],
) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _safe_production_payload(**values: object) -> dict[str, object]:
    return {
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        **values,
    }


@pytest.mark.parametrize(
    ("capability_id", "relative_path", "payload"),
    [
        (
            "VNEXT-01-LOCAL-QWEN",
            "runtime/state/qwen-prompter-health.json",
            _safe_production_payload(
                updated_at=NOW.isoformat(),
                status="RUNNING",
                blockers=[],
                endpoint="http://127.0.0.1:8080",
                listener_pids=[101],
                provider_pid=102,
            ),
        ),
        (
            "VNEXT-02-RECOVERY-RADAR",
            "runtime/artifacts/user_reports/ykb/latest.json",
            _safe_production_payload(
                observed_at=NOW.isoformat(),
                recovery_radar_status="RUNNING_WITH_BLOCKERS",
                recovery_radar_ref="artifact://recovery/latest.json",
            ),
        ),
        (
            "VNEXT-05-REALTIME-DATA-PLANE",
            "runtime/artifacts/benchmarks/latency/latency-latest.json",
            _safe_production_payload(
                measurement={
                    "benchmark_name": "market-data-event-latency",
                    "code_revision": "abcdef1",
                    "measured_at": NOW.isoformat(),
                    "samples_ns_per_operation": [100.0],
                }
            ),
        ),
        (
            "VNEXT-06-RISK-CAPITAL",
            "runtime/artifacts/user_reports/ykb/latest.json",
            _safe_production_payload(
                observed_at=NOW.isoformat(),
                blockers=["LIVE_ORDER_BLOCKED"],
                financial_situation={"status": "READY"},
                wallet_position_management={"status": "READY_FOR_REVIEW"},
            ),
        ),
        (
            "VNEXT-07-OOS-AUTOML",
            "runtime/artifacts/validation/recovery-queue-latest.json",
            _safe_production_payload(
                generated_at_utc=NOW.isoformat(),
                status="QUEUED",
                blockers=["LIVE_ORDER_BLOCKED"],
                items=[],
            ),
        ),
        (
            "VNEXT-08-SPOT-FUTURES-SCANNER",
            "runtime/artifacts/decisions/scanner/scan-latest.json",
            _safe_production_payload(
                observed_at=NOW.isoformat(),
                status="READY",
                blockers=["LIVE_ORDER_BLOCKED"],
                funnel={"symbols_scanned": 10},
            ),
        ),
    ],
)
def test_vnext_production_evidence_requires_fresh_semantic_success(
    tmp_path: Path,
    capability_id: str,
    relative_path: str,
    payload: dict[str, object],
) -> None:
    _write_production_evidence(tmp_path, relative_path, payload)

    assert (
        _production_evidence_blockers(
            tmp_path,
            capability_id=capability_id,
            evidence_files=(relative_path,),
            observed_at=NOW,
        )
        == ()
    )


def test_vnext_production_evidence_rejects_stale_blocked_and_wrong_domain(
    tmp_path: Path,
) -> None:
    qwen_path = "runtime/state/qwen-prompter-health.json"
    _write_production_evidence(
        tmp_path,
        qwen_path,
        _safe_production_payload(
            updated_at=(NOW - timedelta(hours=1)).isoformat(),
            status="STARTING",
            blockers=[],
            endpoint="",
            listener_pids=[],
            provider_pid=None,
        ),
    )
    qwen_blockers = _production_evidence_blockers(
        tmp_path,
        capability_id="VNEXT-01-LOCAL-QWEN",
        evidence_files=(qwen_path,),
        observed_at=NOW,
    )
    assert "PRODUCTION_EVIDENCE_STALE" in qwen_blockers
    assert "QWEN_RUNTIME_NOT_HEALTHY" in qwen_blockers
    assert "QWEN_LOOPBACK_ENDPOINT_NOT_VERIFIED" in qwen_blockers

    latency_path = "runtime/artifacts/benchmarks/latency/latency-latest.json"
    _write_production_evidence(
        tmp_path,
        latency_path,
        _safe_production_payload(
            measurement={
                "benchmark_name": "virtual-market-evaluate",
                "code_revision": "workspace-local",
                "measured_at": NOW.isoformat(),
                "samples_ns_per_operation": [100.0],
            }
        ),
    )
    assert "EVENT_LEVEL_LATENCY_DOMAIN_MISMATCH" in _production_evidence_blockers(
        tmp_path,
        capability_id="VNEXT-05-REALTIME-DATA-PLANE",
        evidence_files=(latency_path,),
        observed_at=NOW,
    )


def test_vnext_production_evidence_rejects_unsafe_or_incomplete_runtime(
    tmp_path: Path,
) -> None:
    scanner_path = "runtime/artifacts/decisions/scanner/scan-latest.json"
    _write_production_evidence(
        tmp_path,
        scanner_path,
        {
            **_safe_production_payload(
                observed_at=NOW.isoformat(),
                status="RUNNING_WITH_BLOCKERS",
                blockers=["PUBLIC_MARKET_UNIVERSE_UNAVAILABLE"],
                funnel={"symbols_scanned": 0},
            ),
            "execution_allowed": True,
        },
    )
    assert _production_evidence_blockers(
        tmp_path,
        capability_id="VNEXT-08-SPOT-FUTURES-SCANNER",
        evidence_files=(scanner_path,),
        observed_at=NOW,
    ) == ("PRODUCTION_EVIDENCE_UNSAFE_AUTHORITY",)

    queue_path = "runtime/artifacts/validation/recovery-queue-latest.json"
    _write_production_evidence(
        tmp_path,
        queue_path,
        _safe_production_payload(
            status="QUEUED_WITH_BLOCKERS",
            blockers=["RECOVERY_VALIDATION_ARTIFACTS_MISSING"],
            items=[],
        ),
    )
    queue_blockers = _production_evidence_blockers(
        tmp_path,
        capability_id="VNEXT-07-OOS-AUTOML",
        evidence_files=(queue_path,),
        observed_at=NOW,
    )
    assert "PRODUCTION_EVIDENCE_TIMESTAMP_INVALID" in queue_blockers
    assert "OOS_AUTOML_RUNTIME_BLOCKED" in queue_blockers


def test_vnext_gap_audit_cli_is_report_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["vnext-audit", "--format", "text"])

    output = capsys.readouterr().out
    assert exit_code in {0, 2}
    assert "vNext v1.2 gap audit" in output
    assert "vNext v1.2 gap audit" in output

    assert main(["gap-audit"]) in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "vnext-gap-audit"
    assert "evidence_depth" in payload["capabilities"][0]
    assert "claim_status" in payload["capabilities"][0]
    assert "claim_verifier" in payload["capabilities"][0]
    assert "production_artifact_status" in payload["capabilities"][0]
    assert payload["execution_allowed"] is False
    assert payload["status"] in {"READY", "RUNNING_WITH_BLOCKERS"}
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
