"""Quality gate profile policy, selector, and compact telemetry tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.ops.quality_gate import (
    AffectedScopeResolutionError,
    QualityStepTelemetry,
    build_compact_quality_console_summary,
    first_actionable_error,
    load_quality_gate_policy,
    resolve_affected_pytest_arguments,
    resolve_profile_pytest_arguments,
    resolve_standard_pytest_arguments,
)
from ai4binance.ops.quality_gate.cli import main as quality_gate_main

pytestmark = [
    pytest.mark.contract,
    pytest.mark.governance,
    pytest.mark.unit,
]

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "quality" / "gates.yaml"
REQUIRED_TESTS = (
    "tests/test_artifact_hygiene_scripts.py",
    "tests/test_maintainability_ratchet.py",
    "tests/test_powershell_source_hygiene.py",
    "tests/test_quality_gate_profiles.py",
    "tests/test_sqlite_query_contracts.py",
    "tests/test_governance_constitution_sync.py",
    "tests/test_repository_validator.py",
)


def test_quality_gate_policy_locks_profile_authority_and_tooling() -> None:
    policy = load_quality_gate_policy(POLICY_PATH)

    assert set(policy.profiles) == {"fast", "standard", "full"}
    assert policy.profiles["fast"].verification_status == "FAST_VERIFIED"
    assert policy.profiles["fast"].type_check == "dmypy"
    assert policy.profiles["fast"].canonical_quality_authority is False
    assert policy.profiles["fast"].execution_trigger == "per_change"
    assert policy.profiles["standard"].type_check == "mypy"
    assert policy.profiles["standard"].execution_trigger == "affected_module"
    assert policy.profiles["full"].verification_status == "FULL_VERIFIED"
    assert policy.profiles["full"].execution_trigger == "milestone_pr_release"
    assert policy.profiles["full"].canonical_quality_authority is True
    assert policy.required_tests == REQUIRED_TESTS
    assert {mapping.name for mapping in policy.standard_impact_mappings} == {
        "instruction_contracts",
        "changed_tests",
        "critical_architecture_conformance",
        "critical_authority_layer_development",
        "critical_governance",
        "critical_enforcement_inventory",
        "critical_semantic_governance_enforcement_fabric",
        "kaizen_culture",
        "lean_process",
        "six_sigma_performance",
        "critical_contracts",
        "critical_risk_decision_execution_validation",
    }
    instruction_mapping = next(
        mapping
        for mapping in policy.standard_impact_mappings
        if mapping.name == "instruction_contracts"
    )
    assert instruction_mapping.path_prefixes == (
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "docs/providers/instruction_claude_provider.md",
        "docs/providers/instruction_codex_provider.md",
        "src/ai4binance/governance/AGENTS.md",
        "tests/AGENTS.md",
    )
    changed_tests_mapping = next(
        mapping
        for mapping in policy.standard_impact_mappings
        if mapping.name == "changed_tests"
    )
    assert changed_tests_mapping.tests_from_changed_paths is True


def test_quality_gate_selector_resolves_affected_and_standard_scopes() -> None:
    policy = load_quality_gate_policy(POLICY_PATH)

    quality_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("scripts/maintenance_hygiene.ps1",),
    )
    governance_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/governance/gate.py",),
    )
    architecture_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/governance/dge_engine.py",),
    )
    docs_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("docs/workflows/runbook_quality_gate_profiles.md",),
    )
    enforcement_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("config/governance/enforcement_inventory.yaml",),
    )
    fabric_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("config/governance/governance_enforcement_fabric.yaml",),
    )
    culture_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/ops/kaizen_quality.py",),
    )
    instruction_args = {
        path: resolve_affected_pytest_arguments(policy, ROOT, (path,))
        for path in (
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            "docs/providers/instruction_claude_provider.md",
            "docs/providers/instruction_codex_provider.md",
            "src/ai4binance/governance/AGENTS.md",
            "tests/AGENTS.md",
        )
    }
    standard_args = resolve_profile_pytest_arguments(
        policy,
        "standard",
        ROOT,
        ("scripts/quality.ps1",),
    )

    assert quality_args == (
        "tests/test_artifact_hygiene_scripts.py",
        "tests/test_powershell_source_hygiene.py",
        "--no-cov",
    )
    quality_wrapper_args = resolve_affected_pytest_arguments(
        policy,
        ROOT,
        ("scripts/quality.ps1", "config/quality/gates.yaml", "pyproject.toml"),
    )
    assert quality_wrapper_args == (
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_isolates_coverage_artifacts",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_runs_gate_steps_in_governed_order",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_profiles_preserve_canonical_full_authority",
        "tests/test_artifact_hygiene_scripts.py::test_quality_gate_profile_config_separates_fast_standard_full",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_fast_affected_mapping_is_fail_closed",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_final_metadata_tracks_completion_step",
        "tests/test_quality_gate_profiles.py",
        "--no-cov",
    )
    assert governance_args == (
        "tests/test_governance_constitution_sync.py",
        "tests/test_repository_validator.py",
        "--no-cov",
    )
    assert architecture_args == (
        "tests/governance/architecture/test_logical_architecture_registry.py",
        "tests/test_dge_models.py",
        "tests/test_dge_engine.py",
        "tests/test_research_application.py",
        "--no-cov",
    )
    assert docs_args == (
        "tests/test_docs_hygiene.py",
        "tests/test_repository_validator.py",
        "--no-cov",
    )
    assert enforcement_args == (
        "tests/test_governed_object_enforcement.py",
        "tests/test_quality_gate_profiles.py",
        "--no-cov",
    )
    assert fabric_args == (
        "tests/governance/terminology/test_governance_enforcement_fabric.py",
        "tests/governance/architecture/test_technology_language_policy.py",
        "tests/test_repository_validator.py",
        "--no-cov",
    )
    assert culture_args == (
        "tests/test_kaizen_quality.py",
        "--no-cov",
    )
    expected_instruction_args = (
        "tests/test_governance_constitution_sync.py",
        "tests/test_docs_hygiene.py",
        "tests/test_kaizen_quality.py",
        "tests/test_repository_validator.py",
        "--no-cov",
    )
    assert all(
        selected_args == expected_instruction_args
        for selected_args in instruction_args.values()
    )
    assert standard_args == (
        *REQUIRED_TESTS,
        "--no-cov",
    )


def test_standard_scope_adds_critical_impacted_contract_and_determinism_tests() -> None:
    policy = load_quality_gate_policy(POLICY_PATH)

    governance_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/governance/gate.py",),
    )
    architecture_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/governance/dge_engine.py",),
    )
    risk_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/risk/limits.py",),
    )
    contracts_args = resolve_profile_pytest_arguments(
        policy,
        "standard",
        ROOT,
        ("schemas/governance/repository_artifact.schema.json",),
    )
    enforcement_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/governance/enforcement/engine.py",),
    )
    fabric_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/governance/governance_enforcement_fabric.py",),
    )
    performance_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("src/ai4binance/ops/performance.py",),
    )
    instruction_args = {
        path: resolve_standard_pytest_arguments(policy, ROOT, (path,))
        for path in (
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            "docs/providers/instruction_claude_provider.md",
            "docs/providers/instruction_codex_provider.md",
            "src/ai4binance/governance/AGENTS.md",
            "tests/AGENTS.md",
        )
    }
    changed_test_args = resolve_standard_pytest_arguments(
        policy,
        ROOT,
        ("tests/test_kaizen_quality.py",),
    )

    assert governance_args == (
        *REQUIRED_TESTS,
        "tests/test_governance_gate.py",
        "tests/test_determinism_replay_qaqc.py",
        "tests/test_agent_evidence_contracts.py",
        "--no-cov",
    )
    assert architecture_args == (
        *REQUIRED_TESTS,
        "tests/governance/architecture/test_logical_architecture_registry.py",
        "tests/test_dge_models.py",
        "tests/test_dge_engine.py",
        "tests/test_research_application.py",
        "--no-cov",
    )
    assert risk_args == (
        *REQUIRED_TESTS,
        "tests/test_strategy_risk.py",
        "tests/test_execution_authority.py",
        "tests/test_execution_envelope.py",
        "tests/test_validation_integrity.py",
        "tests/test_determinism_replay_qaqc.py",
        "--no-cov",
    )
    assert contracts_args == (
        *REQUIRED_TESTS,
        "tests/test_enterprise_contracts.py",
        "tests/test_agent_evidence_contracts.py",
        "tests/test_determinism_replay_qaqc.py",
        "tests/contract/schema/test_market_snapshot_wire_contract.py",
        "--no-cov",
    )
    assert enforcement_args == (
        *REQUIRED_TESTS,
        "tests/test_governed_object_enforcement.py",
        "tests/test_governance_gate.py",
        "tests/test_requirement_assurance_chain.py",
        "--no-cov",
    )
    assert fabric_args == (
        *REQUIRED_TESTS,
        "tests/governance/terminology/test_governance_enforcement_fabric.py",
        "tests/governance/architecture/test_technology_language_policy.py",
        "tests/governance/authority/test_authority_development.py",
        "tests/governance/architecture/test_logical_architecture_registry.py",
        "tests/test_governed_object_enforcement.py",
        "tests/test_kaizen_quality.py",
        "tests/test_lean_governance.py",
        "tests/test_performance_guard.py",
        "tests/test_requirement_assurance_chain.py",
        "tests/test_governance_gate.py",
        "tests/test_determinism_replay_qaqc.py",
        "--no-cov",
    )
    assert performance_args == (
        *REQUIRED_TESTS,
        "tests/test_lean_governance.py",
        "tests/test_performance_guard.py",
        "--no-cov",
    )
    expected_instruction_args = (
        *REQUIRED_TESTS,
        "tests/test_docs_hygiene.py",
        "tests/test_kaizen_quality.py",
        "--no-cov",
    )
    assert all(
        selected_args == expected_instruction_args
        for selected_args in instruction_args.values()
    )
    assert changed_test_args == (
        *REQUIRED_TESTS,
        "tests/test_kaizen_quality.py",
        "--no-cov",
    )


def test_quality_gate_selector_fails_closed_for_unknown_affected_scope() -> None:
    policy = load_quality_gate_policy(POLICY_PATH)

    with pytest.raises(AffectedScopeResolutionError) as error:
        resolve_affected_pytest_arguments(
            policy,
            ROOT,
            ("src/ai4binance/unknown/new_module.py",),
        )

    assert error.value.escalate_to == "standard"
    assert error.value.unknown_paths == ("src/ai4binance/unknown/new_module.py",)
    assert "Run scripts\\quality.ps1 -Profile standard or -Profile full" in str(
        error.value
    )


def test_quality_gate_cli_returns_json_and_nonzero_escalation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = quality_gate_main(
        (
            "select-tests",
            "--repository-root",
            str(ROOT),
            "--config",
            str(POLICY_PATH),
            "--profile",
            "fast",
            "--changed-path",
            "scripts/quality.ps1",
        )
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["pytest_arguments"] == [
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_isolates_coverage_artifacts",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_runs_gate_steps_in_governed_order",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_profiles_preserve_canonical_full_authority",
        "tests/test_artifact_hygiene_scripts.py::test_quality_gate_profile_config_separates_fast_standard_full",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_fast_affected_mapping_is_fail_closed",
        "tests/test_artifact_hygiene_scripts.py::test_quality_script_final_metadata_tracks_completion_step",
        "tests/test_quality_gate_profiles.py",
        "--no-cov",
    ]

    exit_code = quality_gate_main(
        (
            "select-tests",
            "--repository-root",
            str(ROOT),
            "--config",
            str(POLICY_PATH),
            "--profile",
            "fast",
            "--changed-path",
            "unknown/path.txt",
        )
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unknown/path.txt" in captured.err


def test_compact_quality_telemetry_uses_exact_bounded_schemas() -> None:
    started = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    step = QualityStepTelemetry(
        step_id="pytest",
        name="Pytest",
        started_at_utc=started,
        ended_at_utc=started + timedelta(seconds=2),
        wall_time_ms=2000,
        exit_code=1,
        status="FAIL",
        artifact_path="runtime/quality/run/pytest.log",
        output_tail="AssertionError: secret=abc",
    )

    failed_summary = build_compact_quality_console_summary(
        status="QUALITY_GATE_FAILED",
        profile="fast",
        run_id="quality-1",
        duration_ms=2500,
        selected_test_count=1,
        evidence_path="runtime/quality/latest.json",
        steps=(
            {
                "step_id": step.step_id,
                "status": step.status,
                "wall_time_ms": step.wall_time_ms,
                "exit_code": step.exit_code,
                "artifact_path": step.artifact_path,
                "first_actionable_error": "AssertionError: secret=abc",
            },
        ),
        error="token=hidden",
    )

    assert failed_summary == {
        "failed_step": "pytest",
        "exit_code": 1,
        "first_actionable_error": "AssertionError: secret=[REDACTED]",
        "evidence_path": "runtime/quality/latest.json",
    }

    passed_summary = build_compact_quality_console_summary(
        status="FAST_PROFILE_PASS",
        profile="fast",
        run_id="quality-1",
        duration_ms=2500,
        selected_test_count=1,
        evidence_path="runtime/quality/latest.json",
        steps=(
            {"step_id": "ruff", "status": "PASS"},
            {"step_id": "pytest", "status": "PASS"},
            {"step_id": "ruff", "status": "PASS"},
        ),
    )

    assert passed_summary == {
        "profile": "fast",
        "run_id": "quality-1",
        "status": "FAST_PROFILE_PASS",
        "duration": 2500,
        "tools": ("ruff", "pytest"),
        "selected_test_count": 1,
        "evidence_path": "runtime/quality/latest.json",
    }
    assert first_actionable_error("ok\napi_key=secret\nFAILED test_x") == (
        "FAILED test_x"
    )


def test_compact_quality_telemetry_rejects_negative_test_count() -> None:
    with pytest.raises(ValueError, match="selected_test_count must be non-negative"):
        build_compact_quality_console_summary(
            status="FAST_PROFILE_PASS",
            profile="fast",
            run_id="quality-1",
            duration_ms=1,
            selected_test_count=-1,
            evidence_path="runtime/quality/latest.json",
            steps=(),
        )


def test_quality_gate_module_entrypoint_returns_cli_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.ops.quality_gate import __main__ as entrypoint
    from ai4binance.ops.quality_gate import cli

    monkeypatch.setattr(cli, "main", lambda: 7)
    source = Path(entrypoint.__file__).read_text(encoding="utf-8")
    exec(  # noqa: S102
        compile(source, entrypoint.__file__, "exec"),
        {"__name__": "import_only"},
    )
    with pytest.raises(SystemExit) as raised:
        exec(  # noqa: S102
            compile(source, entrypoint.__file__, "exec"),
            {"__name__": "__main__"},
        )

    assert raised.value.code == 7
