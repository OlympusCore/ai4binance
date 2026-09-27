"""Codex completion must consume canonical validation without granting authority."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from ai4binance.governance import repository_validator
from ai4binance.governance.repository_validator import (
    RepositoryFindingKind,
    RepositoryValidationStatus,
)
from ai4binance.ops.quality_gate import (
    load_quality_gate_policy,
    resolve_profile_pytest_arguments,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "codex_governance_hook", ROOT / "scripts/codex_governance_hook.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_snapshot", lambda _root: {"subject": "before"})
    return module


@pytest.fixture(autouse=True)
def canonical_generation_sources(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supply actual policy sources to isolated lifecycle tests."""
    original = hook._generation_context
    monkeypatch.setattr(hook, "_generation_context", lambda _root: original(ROOT))
    authority = hook._authority_context
    monkeypatch.setattr(hook, "_authority_context", lambda _root: authority(ROOT))


def _event(name: str, *, active: bool = False) -> dict[str, object]:
    return {
        "hook_event_name": name,
        "session_id": "test-session",
        "stop_hook_active": active,
    }


def _report(*, blocked: bool) -> SimpleNamespace:
    findings = (
        (
            SimpleNamespace(
                kind=RepositoryFindingKind.TERMINOLOGY_PROHIBITED_TERM,
                path="src/ai4binance/example.py",
                blocker=True,
            ),
        )
        if blocked
        else ()
    )
    return SimpleNamespace(
        findings=findings,
        artifact_count=1,
        status=RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
        if blocked
        else RepositoryValidationStatus.PASS,
    )


def test_read_only_turn_does_not_run_validator_or_claim_compliance(
    hook: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validator = Mock(side_effect=AssertionError("read-only turn must not rescan"))
    monkeypatch.setattr(hook, "validate_repository", validator)
    context = hook.handle_event(_event("UserPromptSubmit"), tmp_path)
    assert "canonical owners" in context["hookSpecificOutput"]["additionalContext"]
    assert hook.handle_event(_event("Stop"), tmp_path) == {}
    validator.assert_not_called()


@pytest.mark.parametrize("blocked", [True, False])
def test_changed_workspace_uses_existing_validator_and_bound_evidence(
    hook: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked: bool,
) -> None:
    hook.handle_event(_event("UserPromptSubmit"), tmp_path)
    monkeypatch.setattr(hook, "_snapshot", lambda _root: {"subject": "after"})
    validator = Mock(return_value=_report(blocked=blocked))
    monkeypatch.setattr(hook, "validate_repository", validator)
    result = hook.handle_event(_event("Stop"), tmp_path)
    validator.assert_called_once_with(tmp_path.resolve())
    if blocked:
        assert result["decision"] == "block"
        assert "TERMINOLOGY_PROHIBITED_TERM" in result["reason"]
        assert "already-authorized" in result["reason"]
    else:
        assert (
            "quality and human approval remain independent" in result["systemMessage"]
        )
    receipts = list((tmp_path / hook.EVIDENCE_ROOT / "runs").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["workspace_attestation"] == {"subject": "after"}
    assert receipt["execution_allowed"] is False
    assert receipt["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_continuation_preserves_failure_and_stops_repeated_repair_loop(
    hook: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        hook, "validate_repository", lambda _root: _report(blocked=True)
    )
    assert hook.handle_event(_event("Stop"), tmp_path)["decision"] == "block"
    hook.handle_event(_event("UserPromptSubmit"), tmp_path)
    blocked = hook.handle_event(_event("Stop", active=True), tmp_path)
    assert blocked["continue"] is False
    assert blocked["stopReason"] == "CODEX_GOVERNANCE_BLOCKED"
    hook.handle_event(_event("UserPromptSubmit"), tmp_path)
    assert hook.handle_event(_event("Stop"), tmp_path)["decision"] == "block"


def test_workspace_drift_cannot_produce_a_successful_receipt(
    hook: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        hook, "_snapshot", Mock(side_effect=[{"subject": "a"}, {"subject": "b"}])
    )
    monkeypatch.setattr(
        hook, "validate_repository", lambda _root: _report(blocked=False)
    )
    result = hook.handle_event(_event("Stop"), tmp_path)
    assert result["decision"] == "block"
    assert "WORKSPACE_CHANGED_DURING_VALIDATION" in result["reason"]


@pytest.mark.parametrize("raw", ["not-json", "[]", '{"hook_event_name":"Stop"}'])
def test_malformed_input_fails_closed_without_echoing_input(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: str,
) -> None:
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(raw))
    assert hook.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["decision"] == "block"
    assert "NOT_VERIFIED" in result["reason"]


def test_validator_exception_prevents_completion(
    hook: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = hook.handle_event
    monkeypatch.setattr(
        hook, "handle_event", lambda payload: original(payload, tmp_path)
    )
    monkeypatch.setattr(
        hook, "validate_repository", Mock(side_effect=OSError("secret"))
    )
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(_event("Stop"))))
    assert hook.main() == 0
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output)["decision"] == "block"


@pytest.mark.parametrize("profile", ["fast", "standard"])
@pytest.mark.parametrize(
    "changed_path",
    [
        ".codex/hooks.json",
        ".codex/config.toml",
        "scripts/codex_governance_hook.py",
        "src/ai4binance/governance/terminology_policy.py",
    ],
)
def test_hook_and_terminology_changes_route_their_behavioral_tests(
    profile: str, changed_path: str
) -> None:
    policy = load_quality_gate_policy(ROOT / "config/quality/gates.yaml")
    selected = resolve_profile_pytest_arguments(policy, profile, ROOT, [changed_path])
    assert "tests/test_codex_governance_hook.py" in selected
    assert "tests/governance/terminology/test_terminology_policy.py" in selected


def test_project_hook_configuration_uses_local_runtime_and_bounded_timeout() -> None:
    config = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    assert set(config["hooks"]) == {"SessionStart", "UserPromptSubmit", "Stop"}
    for groups in config["hooks"].values():
        command = groups[0]["hooks"][0]
        assert command["timeout"] == 180
        assert "git rev-parse --show-toplevel" in command["commandWindows"]
        assert ".venv/Scripts/python.exe" in command["commandWindows"]
        assert "scripts/codex_governance_hook.py" in command["commandWindows"]
        assert "exit 2" in command["commandWindows"]


def test_generation_context_projects_all_canonical_language_responsibilities(
    hook: ModuleType,
) -> None:
    context = hook._generation_context(ROOT)
    expected = {
        "Python 3.14": "Intelligence + orchestration",
        "Rust": "Deterministic CPU performance",
        "CUDA C++": "GPU performance",
        "SQL": "Persistent analytical data",
        "TypeScript": "Human interface",
        "CSS": "Presentation",
        "Go": "High-throughput networking, ingestion, WebSocket/data services",
        "Julia": "Quant research, simulations, numerical algorithms",
        "Java 25+": "Streaming/event systems, long-running backend services",
        "PowerShell": "Windows operations",
        "Bash": "Linux / CI operations",
        "YAML/TOML": "Configuration",
        "JSON Schema": "Contracts",
    }
    for language, responsibility in expected.items():
        assert f"{language}\n    -> {responsibility}" in context
    assert "without discretionary exceptions" in context
    assert "actual content and responsibility" in context
    assert "report BLOCKED" in context
    assert "adoption_evidence_required=True" in context
    assert "forbidden=production_decision_path" in context


@pytest.mark.parametrize("failure", ["missing", "changed", "missing_summary"])
def test_unavailable_language_authority_blocks_prompt_before_baseline_write(
    hook: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    # Load a fresh adapter to exercise the real context reader against bad sources.
    spec = importlib.util.spec_from_file_location(
        "codex_governance_hook_failure", ROOT / "scripts/codex_governance_hook.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_authority_context", lambda _: "")
    fabric = module.load_governance_enforcement_fabric(ROOT)
    policy = module.load_technology_language_policy(ROOT)
    family = next(x for x in fabric.families if x.name == "technology_language")
    path = tmp_path / family.standard_path
    path.parent.mkdir(parents=True)
    if failure != "missing":
        content = b"The canonical summary is unavailable."
        path.write_bytes(content)
        if failure == "missing_summary":
            fabric = replace(
                fabric,
                families=tuple(
                    replace(x, standard_content_sha256=sha256(content).hexdigest())
                    if x.name == family.name
                    else x
                    for x in fabric.families
                ),
            )
    monkeypatch.setattr(module, "load_governance_enforcement_fabric", lambda _: fabric)
    monkeypatch.setattr(module, "load_technology_language_policy", lambda _: policy)
    monkeypatch.setattr(module, "_snapshot", lambda _: {"subject": "before"})
    original = module.handle_event
    monkeypatch.setattr(
        module, "handle_event", lambda payload: original(payload, tmp_path)
    )
    monkeypatch.setattr(
        module.sys, "stdin", io.StringIO(json.dumps(_event("UserPromptSubmit")))
    )
    assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["decision"] == "block"
    assert "NOT_VERIFIED" in output["reason"]
    assert not (tmp_path / module.EVIDENCE_ROOT).exists()


def test_startup_context_includes_verified_authority_and_manual_fallback(
    hook: ModuleType,
) -> None:
    context = hook._startup_context(ROOT)
    assert "Human Owner / Board" in context
    assert "L0_EXTERNAL_MANDATORY_CONSTRAINTS" in context
    assert "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS" in context
    assert "TECHNICAL_TRUTH" in context
    assert "POLICY_ELIGIBILITY" in context
    assert "CONSEQUENTIAL_AUTHORITY" in context
    assert "scripts/codex_governance_hook.py --startup" in context
    assert "Missing, stale, failed," in context
    assert "cannot override higher repository authority" in context
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
    assert config["developer_instructions"] in context


def test_session_resume_does_not_erase_unvalidated_changes(
    hook: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = hook.handle_event(_event("SessionStart"), tmp_path)
    assert first["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    monkeypatch.setattr(hook, "_snapshot", lambda _: {"subject": "after"})
    hook.handle_event(_event("SessionStart"), tmp_path)
    validator = Mock(return_value=_report(blocked=True))
    monkeypatch.setattr(hook, "validate_repository", validator)
    assert hook.handle_event(_event("Stop"), tmp_path)["decision"] == "block"
    validator.assert_called_once()


def test_invalid_authority_stops_session_without_success_context(
    hook: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        hook, "validate_governance_context", lambda _: _report(blocked=True).findings
    )
    original = hook.handle_event
    monkeypatch.setattr(
        hook, "handle_event", lambda payload: original(payload, tmp_path)
    )
    monkeypatch.setattr(
        hook.sys, "stdin", io.StringIO(json.dumps(_event("SessionStart")))
    )
    assert hook.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["continue"] is False
    assert "hookSpecificOutput" not in result


def test_manual_startup_failure_returns_nonzero(
    hook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(hook.sys, "argv", ["codex_governance_hook.py", "--startup"])
    monkeypatch.setattr(
        hook, "_startup_context", Mock(side_effect=ValueError("invalid"))
    )
    assert hook.main() == 2
    assert "NOT_VERIFIED" in capsys.readouterr().out


def test_startup_rejects_workspace_drift(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hook, "_snapshot", Mock(side_effect=[{"id": "a"}, {"id": "b"}]))
    with pytest.raises(ValueError, match="WORKSPACE_CHANGED_DURING_STARTUP"):
        hook._startup_context(ROOT)


@pytest.mark.parametrize("mutation", ["content", "version"])
def test_governed_instruction_reader_rejects_unapproved_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    lock = repository_validator._document_lock_manifest(ROOT)
    assert lock[2] is None
    monkeypatch.setattr(repository_validator, "_document_lock_manifest", lambda _: lock)
    source = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    changed = source + "\nUnauthorized instruction.\n"
    if mutation == "version":
        changed = source.replace("version: 5.0.1", "version: 99.0.0", 1)
    (tmp_path / "AGENTS.md").write_text(changed, encoding="utf-8")
    with pytest.raises(ValueError, match="governed context"):
        repository_validator.read_verified_governed_document(tmp_path, "AGENTS.md")


def test_startup_does_not_accept_an_empty_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fabric validation failed"):
        repository_validator.validate_governance_context(tmp_path)


@pytest.mark.script_subprocess
@pytest.mark.skipif(os.name != "nt", reason="Windows hook bootstrap contract")
def test_windows_hook_command_preserves_stdin_from_a_repository_subdirectory() -> None:
    executable = shutil.which("powershell.exe")
    assert executable is not None
    config = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["Stop"][0]["hooks"][0]["commandWindows"]
    completed = subprocess.run(  # noqa: S603
        [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT / "scripts",
        input="not-json",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["decision"] == "block"
