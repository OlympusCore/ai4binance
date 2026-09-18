"""Targeted failure-mode coverage for vNext gap evidence validators."""

from pathlib import Path
from typing import cast

import pytest

from ai4binance.enterprise import vnext_gap_audit as audit
from ai4binance.governance.enforcement.inventory import RequirementTraceabilityRegistry


def test_evidence_validators_reject_missing_or_invalid_inputs() -> None:
    assert "QWEN_RUNTIME_NOT_HEALTHY" in audit._local_qwen_evidence_blockers({})
    assert audit._is_loopback_endpoint("not a url") is False
    assert audit._recovery_radar_evidence_blockers({}) == (
        "RECOVERY_RADAR_NOT_EXECUTED",
    )
    assert audit._recovery_radar_evidence_blockers(
        {"recovery_radar_status": "READY"}
    ) == ("RECOVERY_RADAR_REFERENCE_MISSING",)
    assert audit._realtime_data_plane_evidence_blockers({}) == (
        "EVENT_LEVEL_LATENCY_EVIDENCE_INVALID",
    )
    assert audit._realtime_data_plane_evidence_blockers({"measurement": {}}) == (
        "EVENT_LEVEL_LATENCY_DOMAIN_MISMATCH",
    )
    assert audit._realtime_data_plane_evidence_blockers(
        {"measurement": {"benchmark_name": "market-data-event-latency"}}
    ) == ("EVENT_LEVEL_LATENCY_SAMPLES_MISSING",)
    assert audit._realtime_data_plane_evidence_blockers(
        {
            "measurement": {
                "benchmark_name": "market-data-event-latency",
                "samples_ns_per_operation": [1],
            }
        }
    ) == ("EVENT_LEVEL_LATENCY_SUBJECT_UNBOUND",)
    assert audit._risk_capital_evidence_blockers({}) == (
        "ACCOUNT_WIDE_RECONCILIATION_NOT_READY",
    )
    base: dict[str, object] = {"financial_situation": {"status": "READY"}}
    assert audit._risk_capital_evidence_blockers(base) == (
        "WALLET_POSITION_MANAGEMENT_NOT_READY",
    )
    base["wallet_position_management"] = {"status": "READY"}
    assert audit._risk_capital_evidence_blockers(base) == (
        "RISK_CAPITAL_BLOCKERS_INVALID",
    )
    base["blockers"] = ["runtime:PORTFOLIO_LIMIT"]
    assert audit._risk_capital_evidence_blockers(base) == (
        "RISK_CAPITAL_RUNTIME_BLOCKERS_PRESENT",
    )
    assert audit._oos_automl_evidence_blockers({}) == ("OOS_AUTOML_RUNTIME_BLOCKED",)
    assert audit._oos_automl_evidence_blockers({"status": "READY", "blockers": []}) == (
        "OOS_AUTOML_QUEUE_INVALID",
    )
    assert audit._scanner_evidence_blockers({}) == ("SCANNER_RUNTIME_BLOCKED",)
    assert audit._scanner_evidence_blockers({"status": "READY", "blockers": []}) == (
        "SCANNER_FUNNEL_INVALID",
    )
    assert audit._scanner_evidence_blockers(
        {"status": "READY", "blockers": [], "funnel": {}}
    ) == ("SCANNER_SYMBOL_COVERAGE_EMPTY",)


def test_gap_dataclasses_reject_invalid_authority_and_unsafe_state() -> None:
    with pytest.raises(ValueError, match="identity"):
        audit.VnextCapabilityGap(
            "", "title", "phase", "P1", audit.VnextGapStatus.MISSING, (), (), (), "risk"
        )
    item = audit.VnextCapabilityGap(
        "id", "title", "phase", "P1", audit.VnextGapStatus.MISSING, (), (), (), "risk"
    )
    args = (
        "READY",
        Path.cwd(),
        (item,),
        (),
        "phase",
        (),
        "PASS",
        0,
        0,
        (),
    )
    with pytest.raises(ValueError, match="cannot authorize"):
        audit.VnextGapAuditReport(*args, execution_allowed=True)
    report = audit.VnextGapAuditReport(*args)
    assert report.to_payload()["execution_allowed"] is False


def test_gap_audit_filesystem_and_phase_helpers(tmp_path: Path) -> None:
    assert audit._repository_file(tmp_path, "../escape") is None
    assert audit._repository_file(tmp_path, "missing") is None
    (tmp_path / "present.txt").write_text("x", encoding="utf-8")
    assert audit._repository_file(tmp_path, "present.txt") == tmp_path / "present.txt"
    latest = tmp_path / "runtime/artifacts/quality/gate/latest.json"
    latest.parent.mkdir(parents=True)
    assert audit._load_coverage_policy_result(tmp_path) is None
    latest.write_text("bad", encoding="utf-8")
    assert audit._load_coverage_policy_result(tmp_path) is None
    latest.write_text("[]", encoding="utf-8")
    assert audit._load_coverage_policy_result(tmp_path) is None
    latest.write_text(
        '{"coverage_policy_summary": {"policy_result": " PASS "}}', encoding="utf-8"
    )
    assert audit._load_coverage_policy_result(tmp_path) == "PASS"
    assert (
        audit._evidence_depth(
            code_complete=False,
            has_tests=False,
            runtime_complete=False,
            production_complete=True,
        )
        is audit.VnextEvidenceDepth.PRODUCTION_EVIDENCE
    )
    assert (
        audit._evidence_depth(
            code_complete=False,
            has_tests=False,
            runtime_complete=True,
            production_complete=False,
        )
        is audit.VnextEvidenceDepth.RUNTIME_WIRED
    )
    assert (
        audit._evidence_depth(
            code_complete=True,
            has_tests=True,
            runtime_complete=False,
            production_complete=False,
        )
        is audit.VnextEvidenceDepth.TESTED_CONTRACT
    )
    assert (
        audit._evidence_depth(
            code_complete=False,
            has_tests=False,
            runtime_complete=False,
            production_complete=False,
        )
        is audit.VnextEvidenceDepth.CODE_ONLY
    )
    missing = audit.VnextCapabilityGap(
        "p0", "title", "phase", "P0", audit.VnextGapStatus.MISSING, (), (), (), "risk"
    )
    complete = audit.VnextCapabilityGap(
        "done",
        "title",
        "phase",
        "P1",
        audit.VnextGapStatus.COMPLETE,
        (),
        (),
        (),
        "risk",
    )
    trace = audit._RequirementTraceabilityAudit("PASS", 0, 0, ())
    assert audit._next_phase((missing,), trace) == "p0_EVIDENCE_CLOSURE"
    assert (
        audit._next_phase(
            (complete,), audit._RequirementTraceabilityAudit("MISSING", 0, 0, ("x",))
        )
        == "REQUIREMENT_TRACEABILITY_CLOSURE"
    )
    assert audit._next_phase((complete,), trace) == "VNEXT_EVIDENCE_CLOSURE_COMPLETE"


def test_gap_audit_evidence_loader_and_validation_failures(tmp_path: Path) -> None:
    item = audit.VnextCapabilityGap(
        "id", "title", "phase", "P1", audit.VnextGapStatus.MISSING, (), (), (), "risk"
    )
    args = ("READY", tmp_path, (item,), (), "phase", (), "PASS", 0, 0, ())
    for index, message in [
        (0, "status"),
        (2, "requires"),
        (6, "status"),
        (7, "cannot"),
        (8, "invalid"),
    ]:
        invalid = list(args)
        if index == 0:
            invalid[index] = "BAD"
        elif index == 2:
            invalid[index] = ()
        elif index == 6:
            invalid[index] = "BAD"
        elif index == 7:
            invalid[index] = -1
        else:
            invalid[index] = 1
        with pytest.raises(ValueError, match=message):
            audit.VnextGapAuditReport(*invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unique"):
        audit._require_unique_nonblank("values", ("a", "a"))
    with pytest.raises(ValueError, match="blanks"):
        audit._require_unique_nonblank("values", ("",))
    assert audit._nested_value({"a": "bad"}, "a.b") is None
    assert audit._parse_evidence_timestamp("bad") is None
    assert audit._parse_evidence_timestamp("2026-01-01T00:00:00") is None
    assert audit._load_production_evidence(tmp_path, "missing.json") == (
        None,
        "PRODUCTION_EVIDENCE_INCOMPLETE",
    )
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("[]", encoding="utf-8")
    assert audit._load_production_evidence(tmp_path, "bad.json") == (
        None,
        "PRODUCTION_EVIDENCE_SCHEMA_INVALID",
    )
    payload_path.write_text("bad", encoding="utf-8")
    assert audit._load_production_evidence(tmp_path, "bad.json") == (
        None,
        "PRODUCTION_EVIDENCE_INVALID_JSON",
    )
    payload_path.write_text(
        (
            '{"execution_allowed": false, '
            '"live_eligibility_status": "LIVE_ORDER_BLOCKED", '
            '"updated_at": "bad"}'
        ),
        encoding="utf-8",
    )
    assert audit._production_evidence_blockers(
        tmp_path,
        capability_id="VNEXT-01-LOCAL-QWEN",
        evidence_files=("bad.json",),
        observed_at=__import__("datetime").datetime(
            2026, 1, 1, tzinfo=__import__("datetime").UTC
        ),
    ) == (
        "PRODUCTION_EVIDENCE_TIMESTAMP_INVALID",
        "QWEN_RUNTIME_NOT_HEALTHY",
        "QWEN_LOOPBACK_ENDPOINT_NOT_VERIFIED",
        "QWEN_LISTENER_NOT_VERIFIED",
        "QWEN_PROVIDER_PROCESS_NOT_VERIFIED",
    )


def test_gap_audit_remaining_local_failure_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest = tmp_path / "runtime/artifacts/quality/gate/latest.json"
    latest.parent.mkdir(parents=True)
    latest.write_text('{"coverage_policy_summary": []}', encoding="utf-8")
    assert audit._load_coverage_policy_result(tmp_path) is None
    latest.write_text(
        '{"coverage_policy_summary": {"policy_result": " "}}', encoding="utf-8"
    )
    assert audit._load_coverage_policy_result(tmp_path) is None
    monkeypatch.setattr(
        audit,
        "load_enforcement_inventory",
        lambda _path: type("I", (), {"requirement_traceability": None})(),
    )
    inventory = tmp_path / "config/governance/enforcement_inventory.yaml"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("x", encoding="utf-8")
    assert audit._audit_requirement_traceability(tmp_path).status == "MISSING"
    directory = tmp_path / "directory"
    directory.mkdir()
    assert audit._load_production_evidence(tmp_path, "directory") == (
        None,
        "PRODUCTION_EVIDENCE_NOT_FILE",
    )
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == evidence)
    assert audit._load_production_evidence(tmp_path, "evidence.json") == (
        None,
        "PRODUCTION_EVIDENCE_SYMLINK_REJECTED",
    )
    monkeypatch.undo()
    monkeypatch.setattr(audit, "_load_production_evidence", lambda *_args: (None, None))
    assert audit._production_evidence_blockers(
        tmp_path,
        capability_id="unknown",
        evidence_files=("x",),
        observed_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    ) == ("PRODUCTION_EVIDENCE_INVALID",)
    assert audit._oos_automl_evidence_blockers(
        {"status": "READY", "blockers": ["bad"], "items": []}
    ) == ("OOS_AUTOML_EVIDENCE_BLOCKERS_PRESENT",)
    assert audit._scanner_evidence_blockers(
        {"status": "READY", "blockers": ["bad"], "funnel": {"symbols_scanned": 1}}
    ) == ("SCANNER_EVIDENCE_BLOCKERS_PRESENT",)


def test_gap_audit_reference_and_partial_capability_paths(tmp_path: Path) -> None:
    from types import SimpleNamespace

    entry = SimpleNamespace(
        requirement_id="REQ",
        authority_ref="missing.md",
        machine_readable_ref="missing.yaml",
        implementation_refs=(),
        test_refs=(),
        evidence_ref="missing.json",
    )
    traceability = SimpleNamespace(entries=(entry,))
    blockers = audit._requirement_reference_blockers(
        tmp_path, cast(RequirementTraceabilityRegistry, traceability)
    )
    assert "REQ:AUTHORITY_REF_MISSING" in blockers
    assert "REQ:EVIDENCE_REF_MISSING" in blockers
    evidence = tmp_path / "evidence.json"
    evidence.write_text("bad", encoding="utf-8")
    entry = SimpleNamespace(
        requirement_id="REQ2",
        authority_ref="missing",
        machine_readable_ref="missing",
        implementation_refs=(),
        test_refs=(),
        evidence_ref="evidence.json",
    )
    assert "REQ2:EVIDENCE_REF_INVALID" in audit._requirement_reference_blockers(
        tmp_path,
        cast(RequirementTraceabilityRegistry, SimpleNamespace(entries=(entry,))),
    )
    (tmp_path / "present.py").write_text("pass", encoding="utf-8")
    partial = audit._capability(
        tmp_path,
        capability_id="partial",
        title="title",
        phase="phase",
        priority="P2",
        evidence_files=("present.py",),
        complete_when=("absent.py",),
        runtime_wiring_files=(),
        production_evidence_files=(),
        missing_controls=("missing",),
        proposed_diff=("MODIFY x",),
        risk="LOW",
        observed_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    assert partial.status is audit.VnextGapStatus.PARTIAL
