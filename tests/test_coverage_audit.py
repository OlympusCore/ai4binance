from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.governance.architecture import load_logical_architecture_registry
from ai4binance.ops.coverage_audit import (
    CoverageAuditSort,
    build_coverage_audit_report,
    load_coverage_audit_config,
    load_coverage_audit_files,
    main,
    render_markdown,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)


def test_coverage_audit_builds_risk_and_remediation_views(tmp_path: Path) -> None:
    coverage_path = _coverage_file(
        tmp_path,
        {
            "src/ai4binance/ops/folder_structure_audit.py": {
                "summary": _summary(
                    statements=233,
                    missing=49,
                    branches=80,
                    missing_branches=28,
                ),
                "missing_lines": [3, 4],
            },
            "src/ai4binance/governance/dge_engine.py": {
                "summary": _summary(
                    statements=100,
                    missing=11,
                    branches=50,
                    missing_branches=10,
                ),
                "missing_lines": [10, 11],
            },
        },
    )
    config = load_coverage_audit_config(Path("config/quality/coverage-targets.json"))

    report = build_coverage_audit_report(
        load_coverage_audit_files(coverage_path),
        config,
        policy_document="docs/policies/quality/coverage_improvement_strategy_policy.md",
        coverage_config="config/quality/coverage-targets.json",
        coverage_json="coverage.json",
        sort_by=CoverageAuditSort.RISK,
        source_root=Path("."),
        generated_at=NOW,
    )

    assert report.report_id == "AI4B-COVERAGE-AUDIT-DECISION-READY"
    assert report.below_threshold_count == 2
    assert report.coverage_view[0].path.endswith("folder_structure_audit.py")
    assert report.risk_view[0].path.endswith("governance/dge_engine.py")
    assert report.files[0].path == report.risk_view[0].path
    assert report.risk_view[0].priority == "P0"
    assert report.risk_view[0].tier == "T0"
    assert report.risk_view[0].target_coverage == 97.0
    assert "LIVE_ORDER_BLOCK_PATH" in report.risk_view[0].test_gap_types
    assert report.risk_view[0].recommended_test_types
    assert report.risk_view[0].manual_instruction.startswith("Raise ")
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_coverage_audit_adds_registry_derived_assurance_views(
    tmp_path: Path,
) -> None:
    coverage_path = _coverage_file(
        tmp_path,
        {
            "src/ai4binance/governance/dge_engine.py": {
                "summary": _summary(
                    statements=100,
                    missing=0,
                    branches=20,
                    missing_branches=0,
                )
            }
        },
    )
    config = load_coverage_audit_config(Path("config/quality/coverage-targets.json"))
    registry = load_logical_architecture_registry(
        Path("docs/registries/registry_logical_architecture.yaml"),
        schema_root=Path("schemas"),
    )

    report = build_coverage_audit_report(
        load_coverage_audit_files(coverage_path),
        config,
        policy_document="docs/policies/quality/coverage_improvement_strategy_policy.md",
        coverage_config="config/quality/coverage-targets.json",
        coverage_json="coverage.json",
        source_root=Path("."),
        architecture_registry=registry,
        generated_at=NOW,
    )

    decision_governance = next(
        row
        for row in report.architecture_view
        if row.component_id == "decision-governance"
    )
    assert decision_governance.statement_coverage == 100.0
    assert decision_governance.relation_status == "PROVEN"
    assert any(row.state == "NOT_MEASURED" for row in report.architecture_view)
    assert report.critical_behavior_view
    assert all(not row.runtime_proven for row in report.critical_behavior_view)


def test_coverage_audit_filters_priority_and_target_only(tmp_path: Path) -> None:
    coverage_path = _coverage_file(
        tmp_path,
        {
            "src/ai4binance/ops/folder_structure_audit.py": {
                "summary": _summary(
                    statements=100,
                    missing=8,
                    branches=10,
                    missing_branches=1,
                )
            },
            "src/ai4binance/governance/blockers.py": {
                "summary": _summary(
                    statements=100,
                    missing=4,
                    branches=100,
                    missing_branches=4,
                )
            },
        },
    )
    config = load_coverage_audit_config(Path("config/quality/coverage-targets.json"))

    report = build_coverage_audit_report(
        load_coverage_audit_files(coverage_path),
        config,
        policy_document="docs/policies/quality/coverage_improvement_strategy_policy.md",
        coverage_config="config/quality/coverage-targets.json",
        coverage_json="coverage.json",
        priority="P0",
        target_only=True,
        generated_at=NOW,
    )

    assert [row.path for row in report.files] == [
        "src/ai4binance/governance/blockers.py"
    ]
    assert report.files[0].coverage_gap_to_target == 1.0
    assert report.files[0].classification_rule == "blocker_governance"


def test_coverage_audit_detects_fail_closed_branch_semantics_and_sorting(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "ai4binance" / "execution" / "replay_recovery.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def recover(payload: str) -> str:\n"
        "    if not payload:\n"
        "        raise ValueError('missing payload')\n"
        "    return json.dumps(payload)\n",
        encoding="utf-8",
    )
    coverage_path = _coverage_file(
        tmp_path,
        {
            "src/ai4binance/execution/replay_recovery.py": {
                "summary": _summary(
                    statements=50,
                    missing=20,
                    branches=40,
                    missing_branches=30,
                ),
                "missing_lines": [3, 4],
            },
            "src/unclassified.py": {
                "summary": _summary(
                    statements=10,
                    missing=2,
                    branches=2,
                    missing_branches=1,
                ),
                "missing_lines": [1],
            },
        },
    )
    config = load_coverage_audit_config(Path("config/quality/coverage-targets.json"))

    report = build_coverage_audit_report(
        load_coverage_audit_files(coverage_path),
        config,
        policy_document="docs/policy.md",
        coverage_config="config/quality/coverage-targets.json",
        coverage_json="coverage.json",
        sort_by=CoverageAuditSort.BRANCH_PRESSURE,
        source_root=tmp_path,
        generated_at=NOW,
    )

    row = report.files[0]
    assert row.path.endswith("execution/replay_recovery.py")
    assert {
        "ERROR_PATHS",
        "RETURN_PATHS",
        "SERIALIZATION_PATH",
        "LIVE_ORDER_BLOCK_PATH",
        "REPLAY_PATH",
        "RECOVERY_PATH",
    }.issubset(row.test_gap_types)
    assert {
        "failure_path",
        "fail_closed",
        "serialization",
        "replay",
        "recovery",
    }.issubset(row.recommended_test_types)
    fallback = next(item for item in report.files if item.path == "src/unclassified.py")
    assert fallback.classification_rule == "default_source"
    assert report.to_payload()["execution_allowed"] is False
    markdown = render_markdown(report)
    assert "BranchPressure" in markdown


def test_coverage_audit_models_reject_invalid_config_and_authority() -> None:
    config = load_coverage_audit_config(Path("config/quality/coverage-targets.json"))
    rule = config.classification_rules[0]

    with pytest.raises(ValueError, match="criticality_score"):
        replace(rule, criticality_score=101)
    with pytest.raises(ValueError, match="cannot exceed"):
        replace(config, default_threshold=99.0, default_target_coverage=95.0)
    with pytest.raises(ValueError, match="requires classification rules"):
        replace(config, classification_rules=())

    report = build_coverage_audit_report(
        (),
        config,
        policy_document="docs/policy.md",
        coverage_config="config/quality/coverage-targets.json",
        coverage_json="coverage.json",
        generated_at=NOW,
    )
    assert "No files matched this view." in render_markdown(report)
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(report, execution_allowed=True)


def test_coverage_audit_requires_source_root_for_architecture_view(
    tmp_path: Path,
) -> None:
    config = load_coverage_audit_config(Path("config/quality/coverage-targets.json"))
    registry = load_logical_architecture_registry(
        Path("docs/registries/registry_logical_architecture.yaml"),
        schema_root=Path("schemas"),
    )
    with pytest.raises(ValueError, match="source_root is required"):
        build_coverage_audit_report(
            load_coverage_audit_files(_coverage_file(tmp_path, {})),
            config,
            policy_document="docs/policy.md",
            coverage_config="config/quality/coverage-targets.json",
            coverage_json="coverage.json",
            architecture_registry=registry,
            generated_at=NOW,
        )


def test_coverage_audit_cli_writes_decision_ready_outputs(tmp_path: Path) -> None:
    coverage_path = _coverage_file(
        tmp_path,
        {
            "src/ai4binance/governance/blockers.py": {
                "summary": _summary(
                    statements=100,
                    missing=10,
                    branches=10,
                    missing_branches=2,
                )
            }
        },
    )

    exit_code = main(
        [
            "--coverage-json",
            str(coverage_path),
            "--config",
            "config/quality/coverage-targets.json",
            "--output-directory",
            str(tmp_path),
            "--policy-document",
            "docs/policies/quality/coverage_improvement_strategy_policy.md",
            "--coverage-json-display",
            "coverage.json",
            "--sort-by",
            "Risk",
        ]
    )

    assert exit_code == 0
    payload = json.loads((tmp_path / "coverage_audit_below_93.json").read_text())
    assert payload["report_id"] == "AI4B-COVERAGE-AUDIT-DECISION-READY"
    assert payload["files"][0]["priority"] == "P0"
    assert payload["files"][0]["target_coverage"] == 97.0
    markdown = (tmp_path / "coverage_audit_below_93.md").read_text()
    assert "## Coverage View" in markdown
    assert "## Risk View" in markdown
    assert "## Remediation View" in markdown
    assert "## Architecture View" in markdown
    assert "## Critical Behavior View" in markdown


def _summary(
    *,
    statements: int,
    missing: int,
    branches: int,
    missing_branches: int,
) -> dict[str, float | int]:
    return {
        "covered_lines": statements - missing,
        "num_statements": statements,
        "missing_lines": missing,
        "num_branches": branches,
        "covered_branches": branches - missing_branches,
        "missing_branches": missing_branches,
        "percent_covered": round((statements - missing) / statements * 100, 2),
    }


def _coverage_file(
    tmp_path: Path,
    files: dict[str, dict[str, object]],
) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps({"files": files}),
        encoding="utf-8",
    )
    return path
