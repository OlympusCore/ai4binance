"""Quality evidence corruption and workspace identity regression contracts."""

import json
import subprocess
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai4binance.governance import constitution_sync as sync
from tests.test_governance_constitution_sync import write_quality_evidence


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verification_status", "STANDARD_VERIFIED"),
        ("canonical_quality_authority", False),
        ("full_assurance_status", "BLOCKED"),
        ("generated_at_utc", ""),
        ("generated_at_utc", "not-a-date"),
        ("workspace_attestation", None),
        ("workspace_attestation", {"repository_root": "relative"}),
        ("execution_allowed", True),
        ("coverage_percent", True),
        ("pytest_pass_count", []),
        (
            "coverage_realism_proof",
            {"markdown_path": "missing.md", "markdown_sha256": "a" * 64},
        ),
    ],
)
def test_incomplete_or_forged_quality_envelope_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    write_quality_evidence(tmp_path)
    assert sync.load_current_quality_gate_evidence(tmp_path) is not None
    path = tmp_path / "runtime/artifacts/quality/gate/latest.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert sync.load_current_quality_gate_evidence(tmp_path) is None


@pytest.mark.parametrize("raw", [b"\xff", b"{", b"[]"])
def test_unreadable_quality_payload_is_rejected(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "runtime/artifacts/quality/gate/latest.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    assert sync.load_current_quality_gate_evidence(tmp_path) is None


def test_quality_read_failure_is_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_quality_evidence(tmp_path)
    monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=OSError("denied")))
    assert sync.load_current_quality_gate_evidence(tmp_path) is None


@pytest.mark.parametrize("kind", ["missing", "failure", "error", "empty"])
def test_git_unavailable_keeps_explicit_uncommitted_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setattr(
        sync, "_git_executable", lambda: None if kind == "missing" else "git"
    )
    runner = Mock(
        return_value=SimpleNamespace(
            returncode=1 if kind == "failure" else 0, stdout=""
        )
    )
    if kind == "error":
        runner.side_effect = OSError("unavailable")
    monkeypatch.setattr(subprocess, "run", runner)
    assert sync._repository_git_commit(tmp_path) == "WORKTREE_UNCOMMITTED"
    assert sync._quality_gate_change_set_sha256(tmp_path) == sha256(b"").hexdigest()


def test_changeset_hash_uses_normalized_sorted_subject_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync, "_git_executable", lambda: "git")
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=SimpleNamespace(
                returncode=0,
                stdout=(
                    "x\n M runtime/transient.json\n M .coverage\n M \n"
                    'R  old.py -> "new.py"\n M src/code.py\n'
                ),
            )
        ),
    )
    expected = " M src/code.py\nR  new.py"
    assert (
        sync._quality_gate_change_set_sha256(tmp_path)
        == sha256(expected.encode()).hexdigest()
    )
    assert sync._parse_git_status_path('"src\\code.py"') == "src/code.py"


@pytest.mark.parametrize(
    "parts", [(".pytest-tmp-1",), (".coverage",), (".coverage.abc",)]
)
def test_transient_measurements_are_excluded_from_subject(
    parts: tuple[str, ...],
) -> None:
    assert sync._quality_gate_attestation_ignores(parts)


@pytest.mark.parametrize("method", [sync._optional_int, sync._optional_float])
def test_numeric_quality_fields_reject_bool_and_containers(
    method: Callable[[object], int | float | None],
) -> None:
    assert method(None) is None
    assert method("42") == 42
    values: tuple[object, ...] = (True, [], {})
    for value in values:
        with pytest.raises(ValueError, match="compatible"):
            method(value)


def test_governed_rule_gaps_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sync,
        "CORE_WRITTEN_RULE_EXPECTATIONS",
        (
            sync.WrittenRuleExpectation("docs/missing.md", ("required",)),
            sync.WrittenRuleExpectation(
                "docs/present.md", ("required",), ("prohibited",)
            ),
        ),
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/present.md").write_text("required prohibited", encoding="utf-8")
    findings = sync._audit_written_rules(tmp_path)
    assert len(findings) == 3
    assert findings[0].severity == "CRITICAL"
    assert findings[1].kind is sync.LooseCodeGapKind.DOCUMENT_WITHOUT_ELI10
    assert "Prohibited legacy fragment" in findings[2].detail
    assert sync._read_tests_blob(tmp_path) == ""
    assert sync._audit_loose_code(tmp_path, ()) == ()


def test_attestation_and_evidence_value_objects_reject_invalid_identity(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        sync.WorkspaceAttestation(Path("relative"), "a" * 64, "head", "b" * 64)
    for fragments in (("a", "a"), (" ",)):
        with pytest.raises(ValueError, match=r"unique|blanks"):
            sync.WrittenRuleExpectation("rule.md", fragments)
    with pytest.raises(ValueError, match="sha256"):
        sync.WorkspaceAttestation(tmp_path, "bad", "head", "b" * 64)
    write_quality_evidence(tmp_path)
    evidence = sync.load_current_quality_gate_evidence(tmp_path)
    assert evidence is not None
    with pytest.raises(ValueError, match="cannot be blank"):
        replace(evidence, generated_at_utc=" ")
    report = sync.GovernanceAlignmentAuditReport(
        sync.GovernanceAlignmentStatus.RUNNING_WITH_BLOCKERS,
        tmp_path,
        (),
        (
            sync.LooseCodeFinding(
                sync.LooseCodeGapKind.QUALITY_EVIDENCE_MISSING, "proof", "Missing"
            ),
        ),
        None,
        ("LIVE_ORDER_BLOCKED",),
    )
    assert report.pytest_pass_count is None
    assert report.to_payload()["execution_allowed"] is False
