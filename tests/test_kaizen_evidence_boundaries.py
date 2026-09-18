"""Kaizen evidence must expose malformed, unavailable, and unapproved states."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from ai4binance.ops import kaizen_quality as k
from tests.test_kaizen_quality import NOW


@pytest.fixture(scope="module")
def subjects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("kaizen-boundaries")
    snapshot = k.build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ("runtime:DEGRADED",)),),
        repository_root=root,
    )
    return {
        "snapshot": snapshot,
        "profile": k._RUNTIME_DIRECTORY_PROFILES["runtime/artifacts"],
        "directory": snapshot.runtime_inventory.classifications[0],
        "signal": snapshot.blocker_signals[0],
        "row": k.KaizenTraceabilityMatrixRow(
            "entry", "policy", ("test",), "evidence", "trace", "COVERED", "RECORDED"
        ),
        "contract": k.KaizenAuditContractCheck("contract", "PASS"),
        "benchmark": snapshot.instruction_context_benchmark,
        "check": k.RuntimeKaizenClosureCheck("check", "PASS", "evidence", "pytest"),
        "approval": k.GovernanceApprovalEvidence("C0", "NOT_REQUIRED", 0, 0, False, ()),
        "current": k.CurrentGateEvidence({}, {}, ()),
        "closure": snapshot.closure_gate,
    }


@pytest.mark.parametrize(
    ("kind", "changes", "message"),
    [
        ("profile", {"role": ""}, "role and retention"),
        ("profile", {"validation_status": "INVALID"}, "validation status"),
        ("profile", {"retention_class": "INVALID"}, "retention class"),
        ("profile", {"cleanup_candidate": True}, "cleanup mode"),
        ("profile", {"cleanup_mode": "automatic"}, "cleanup candidate"),
        ("directory", {"path": "src"}, "under runtime"),
        ("directory", {"validation_status": "INVALID"}, "validation status"),
        ("directory", {"retention_class": "INVALID"}, "retention class"),
        (
            "directory",
            {"cleanup_candidate": True, "cleanup_mode": None},
            "cleanup mode",
        ),
        (
            "directory",
            {"cleanup_candidate": False, "cleanup_mode": "delete"},
            "cleanup candidate",
        ),
        (
            "directory",
            {
                "cleanup_candidate": True,
                "cleanup_mode": "review",
                "approval_required_for_cleanup": False,
            },
            "explicit approval",
        ),
        ("signal", {"blocker": ""}, "blocker is required"),
        ("signal", {"occurrences": 0}, "age and occurrences"),
        ("signal", {"age_seconds": -1}, "age and occurrences"),
        ("signal", {"state": "INVALID"}, "state is invalid"),
        ("signal", {"evidence_ref": ""}, "evidence and proof"),
        ("row", {"entrypoint_id": ""}, "entrypoint"),
        ("row", {"tests": ()}, "source and tests"),
        ("row", {"traceability_status": "INVALID"}, "status"),
        ("contract", {"contract_id": ""}, "id is required"),
        ("contract", {"status": "INVALID"}, "status"),
        ("benchmark", {"status": "INVALID"}, "status"),
        (
            "benchmark",
            {"status": "READY", "measurements": (), "blockers": ()},
            "requires measurements",
        ),
        (
            "benchmark",
            {"status": "RUNNING_WITH_BLOCKERS", "blockers": ()},
            "requires blockers",
        ),
        ("benchmark", {"token_estimation_method": "invented"}, "estimation method"),
        ("benchmark", {"execution_allowed": True}, "authorize trading"),
        ("check", {"check_id": ""}, "id is required"),
        ("check", {"status": "INVALID"}, "status"),
        ("check", {"proof_command": ""}, "evidence"),
        ("check", {"blockers": ("UNSAFE",)}, "cannot block"),
        ("check", {"status": "NOT_VERIFIED"}, "must block"),
        ("approval", {"change_class": ""}, "change class"),
        ("approval", {"status": "INVALID"}, "status"),
        ("approval", {"required_approval_count": -1}, "non-negative"),
        ("approval", {"status": "PASS", "hard_veto": True}, "cannot block"),
        ("approval", {"observed_approval_count": 1}, "not-required"),
        ("approval", {"status": "NOT_VERIFIED"}, "requires a veto"),
        ("current", {"quality_gate_payload": None}, "both payloads"),
        ("current", {"blockers": ("MISSING",)}, "cannot block"),
        (
            "current",
            {"quality_gate_payload": None, "governance_gate_payload": None},
            "must be visible",
        ),
        ("closure", {"status": "INVALID"}, "status"),
        ("closure", {"acceptance_status": "INVALID"}, "acceptance"),
        ("closure", {"checks": ()}, "requires checks"),
        ("closure", {"execution_allowed": True}, "authorize trading"),
        ("snapshot", {"snapshot_id": ""}, "id is required"),
        ("snapshot", {"status": "INVALID"}, "status"),
        ("snapshot", {"fast_feedback_commands": ()}, "verification commands"),
        ("snapshot", {"execution_allowed": True}, "authorize trading"),
    ],
)
def test_kaizen_rejects_incoherent_contracts(
    subjects: dict[str, Any], kind: str, changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(subjects[kind], **changes)


@pytest.mark.parametrize(
    ("approval", "blocker"),
    [
        (None, "GOVERNANCE_APPROVAL_EVIDENCE_MALFORMED"),
        (
            {
                "status": "INVALID",
                "required_approval_count": 0,
                "observed_approval_count": 0,
            },
            "GOVERNANCE_APPROVAL_STATUS_INVALID",
        ),
        (
            {
                "status": "PASS",
                "required_approval_count": True,
                "observed_approval_count": 0,
            },
            "GOVERNANCE_APPROVAL_COUNT_INVALID",
        ),
        (
            {
                "status": "PASS",
                "required_approval_count": 2,
                "observed_approval_count": 1,
            },
            "GOVERNANCE_APPROVAL_EVIDENCE_INCONSISTENT",
        ),
        (
            {
                "status": "NOT_REQUIRED",
                "required_approval_count": 1,
                "observed_approval_count": 0,
            },
            "GOVERNANCE_APPROVAL_EVIDENCE_INCONSISTENT",
        ),
        (
            {
                "status": "NOT_VERIFIED",
                "required_approval_count": 0,
                "observed_approval_count": 0,
            },
            "GOVERNANCE_APPROVAL_NOT_VERIFIED",
        ),
    ],
)
def test_malformed_approval_evidence_always_vetoes(
    approval: object, blocker: str
) -> None:
    result = k._governance_approval_evidence({"approval_verification": approval})
    assert result.hard_veto
    assert blocker in result.blockers
    assert result.status in {"NOT_VERIFIED", "RUNNING_WITH_BLOCKERS"}


@pytest.mark.parametrize(
    ("observed", "blockers", "message"),
    [(datetime(2026, 9, 1), ("missing",), "timezone-aware"), (NOW, (" ",), "blanks")],
)
def test_blocker_cycles_require_valid_observations(
    observed: datetime, blockers: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        k._blocker_signals(((observed, blockers),))


def test_kaizen_handles_missing_evidence_and_maps_remediation(tmp_path: Path) -> None:
    assert k._blocker_signals(()) == ()
    assert k._quality_gate_technical_status({}) == ""
    assert (
        k._quality_gate_technical_status({"quality_evidence_gate": {"status": "FAIL"}})
        == "FAIL"
    )
    assert k._string_tuple("blocker") == ("blocker",)
    assert k._string_tuple(None) == ()
    assert (
        k._relative_runtime_path(tmp_path.parent, tmp_path)
        == tmp_path.parent.as_posix()
    )
    assert k._audit_contract_checks({})[0].blockers == (
        "KAIZEN_TRUST_ASSURANCE_MISSING",
    )
    assert k._audit_contract_checks({"trust_assurance": {}})[0].blockers == (
        "KAIZEN_DECISION_PROVENANCE_MISSING",
    )
    assert (
        k._blocker_evidence_ref("opportunities:MISSING")
        == "system-report:opportunities"
    )
    assert k._blocker_evidence_ref("traceability:MISSING") == "canonical-trace-journal"
    assert (
        k._blocker_evidence_ref("audit:MISSING")
        == "continuous-assurance:audit-contract"
    )
    assert "test_privacy_leak_guard.py" in k._blocker_proof_command("privacy:MISSING")
    assert "test_governance_gate.py" in k._blocker_proof_command("traceability:MISSING")


@pytest.mark.parametrize("text", ["{", "[]"])
def test_gate_reader_exposes_corrupt_evidence(tmp_path: Path, text: str) -> None:
    path = tmp_path / "gate.json"
    path.write_text(text, encoding="utf-8")
    assert k._load_current_gate_json_object(
        path, unavailable_blocker="MISSING", malformed_blocker="INVALID"
    ) == (None, "INVALID")
    assert k._load_current_gate_json_object(
        tmp_path / "missing.json",
        unavailable_blocker="MISSING",
        malformed_blocker="INVALID",
    ) == (None, "MISSING")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("valid", ()),
        ("mismatch", ("CURRENT_GATE_EVIDENCE_SUBJECT_MISMATCH",)),
        ("unsafe", ("CURRENT_GATE_EVIDENCE_SAFETY_STATE_INVALID",)),
    ],
)
def test_current_gate_requires_same_subject_and_safe_authority(
    tmp_path: Path, mode: str, expected: tuple[str, ...]
) -> None:
    directory = tmp_path / "runtime/artifacts/quality/gate"
    directory.mkdir(parents=True)
    payload: dict[str, object] = {
        "subject_digest": {"subject_sha256": "a" * 64},
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    (directory / "deterministic_quality_gate_latest.json").write_text(
        json.dumps(payload)
    )
    if mode == "mismatch":
        payload["subject_digest"] = {"subject_sha256": "b" * 64}
    elif mode == "unsafe":
        payload["execution_allowed"] = True
    (directory / "governance_gate_latest.json").write_text(json.dumps(payload))
    evidence = k.load_current_gate_evidence(tmp_path)
    assert evidence.blockers == expected
    assert (evidence.quality_gate_payload is not None) is (mode == "valid")


def test_kaizen_missing_metadata_does_not_create_evidence(tmp_path: Path) -> None:
    assert k._current_gate_subject_sha256({}) is None
    assert (
        k._frontmatter_value("---\ntitle: Test\n---\nowner: outside", "owner") is None
    )
    assert (
        k._nested_payload_status({}, "absent", default="NOT_VERIFIED") == "NOT_VERIFIED"
    )
    assert k._resolve_module_reference("ai4binance.missing", {}) is None
    with pytest.raises(ValueError, match="timezone-aware"):
        k.build_kaizen_quality_snapshot(
            observed_at=datetime(2026, 9, 1),
            blocker_cycles=(),
            repository_root=tmp_path,
        )
