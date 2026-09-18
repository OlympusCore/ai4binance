from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.governance.architecture import load_logical_architecture_registry
from ai4binance.ops.coverage_policy import (
    CoverageFamilyConfig,
    CoverageFamilyResult,
    CoveragePolicyConfig,
    FileCoverage,
    evaluate_coverage_policy,
    load_coverage_policy_config,
    load_file_coverage,
    load_total_coverage_percent,
    main,
)
from ai4binance.ops.coverage_policy import (
    render_markdown as render_coverage_policy_markdown,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)


def test_coverage_policy_ranks_lowest_governed_family_first(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "src\\ai4binance\\opportunity_scanner.py": {
                        "summary": _summary(
                            statements=100,
                            missing=22,
                            branches=40,
                            missing_branches=10,
                        )
                    },
                    "src/ai4binance/governance/blockers.py": {
                        "summary": _summary(
                            statements=100,
                            missing=10,
                            branches=40,
                            missing_branches=15,
                        )
                    },
                    "src/ai4binance/core/contracts/handoffs/models.py": {
                        "summary": _summary(
                            statements=100,
                            missing=5,
                            branches=20,
                            missing_branches=0,
                        )
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    summary = evaluate_coverage_policy(
        _config(enforcement_mode="baseline_migration"),
        load_file_coverage(coverage_json),
        generated_at=NOW,
    )

    assert summary.policy_result == "BASELINE_DEBT"
    assert summary.policy_failures == ("opportunity", "policy")
    assert [result.coverage_family for result in summary.target_results] == [
        "opportunity",
        "policy",
        "handoff",
    ]
    assert summary.target_results[0].statement_coverage == 78.0
    assert summary.target_results[0].coverage_gap == 20.0
    assert summary.target_results[0].policy_state == "BELOW_POLICY"
    assert summary.execution_allowed is False
    assert summary.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_coverage_policy_reports_not_measured_without_fake_zero() -> None:
    summary = evaluate_coverage_policy(_config(), (), generated_at=NOW)

    assert summary.policy_result == "BASELINE_DEBT"
    assert summary.not_measured == ("handoff", "opportunity", "policy")
    assert summary.target_results[0].statement_coverage is None
    assert summary.target_results[0].policy_state == "NOT_MEASURED"


def test_coverage_policy_treats_branch_debt_as_governed_debt(
    tmp_path: Path,
) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "src/ai4binance/governance/blockers.py": {
                        "summary": _summary(
                            statements=100,
                            missing=4,
                            branches=100,
                            missing_branches=6,
                        )
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    summary = evaluate_coverage_policy(
        _config(enforcement_mode="baseline_migration"),
        load_file_coverage(coverage_json),
        generated_at=NOW,
    )

    policy_result = next(
        result
        for result in summary.target_results
        if result.coverage_family == "policy"
    )
    assert policy_result.statement_coverage == 96.0
    assert policy_result.branch_coverage == 94.0
    assert policy_result.coverage_gap == 1.0
    assert policy_result.policy_state == "IMPROVEMENT_REQUIRED"
    assert "policy" in summary.policy_failures


def test_coverage_policy_enforced_mode_fails_on_governed_debt(
    tmp_path: Path,
) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "src/ai4binance/governance/blockers.py": {
                        "summary": _summary(
                            statements=100,
                            missing=10,
                            branches=10,
                            missing_branches=1,
                        )
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    summary = evaluate_coverage_policy(
        _config(enforcement_mode="enforced"),
        load_file_coverage(coverage_json),
        generated_at=NOW,
    )

    assert summary.policy_result == "FAIL"
    assert "policy" in summary.policy_failures
    assert "opportunity" in summary.not_measured


def test_coverage_policy_detects_duplicate_source_ownership(tmp_path: Path) -> None:
    config = CoveragePolicyConfig(
        policy_id="AI4B-POL-QUALITY-COVERAGE-001",
        governed_minimum=95.0,
        remediation_trigger=93.0,
        enforcement_mode="baseline_migration",
        branch_minimum=95.0,
        families=(
            CoverageFamilyConfig(
                name="policy",
                description="Policy",
                include=("src/ai4binance/governance/**",),
            ),
            CoverageFamilyConfig(
                name="repository_validator",
                description="Repository validator",
                include=("src/ai4binance/governance/repository_validator.py",),
            ),
        ),
    )

    summary = evaluate_coverage_policy(
        config,
        (
            load_file_coverage(
                _coverage_file(
                    tmp_path,
                    {
                        "src/ai4binance/governance/repository_validator.py": _summary(
                            statements=100,
                            missing=1,
                            branches=20,
                            missing_branches=1,
                        )
                    },
                )
            )[0],
        ),
        generated_at=NOW,
    )

    assert summary.policy_result == "COVERAGE_SCOPE_CONFLICT"
    assert summary.coverage_scope_conflicts == (
        "src/ai4binance/governance/repository_validator.py:policy,repository_validator",
    )
    assert all(
        result.policy_state == "COVERAGE_SCOPE_CONFLICT"
        for result in summary.target_results
    )


def test_repository_coverage_targets_config_loads_without_scope_conflicts(
    tmp_path: Path,
) -> None:
    config = load_coverage_policy_config(Path("config/quality/coverage-targets.json"))
    rows = tuple(
        load_file_coverage(
            _coverage_file(
                tmp_path,
                {
                    pattern.replace("**", "__sample__").replace(
                        "*", "sample"
                    ): _summary(
                        statements=1,
                        missing=0,
                        branches=0,
                        missing_branches=0,
                    )
                    for family in config.families
                    for pattern in family.include
                },
            )
        )
    )

    summary = evaluate_coverage_policy(config, rows, generated_at=NOW)

    assert summary.coverage_scope_conflicts == ()
    assert summary.enforcement_mode == "baseline_migration"
    assert summary.governed_minimum == 95.0
    assert summary.remediation_trigger == 93.0
    assert summary.branch_minimum == 95.0
    assert config.architecture_assurance is not None
    assert config.architecture_assurance.targets[0].name == "governance"
    payload = json.loads(
        Path("config/quality/coverage-targets.json").read_text(encoding="utf-8")
    )
    assert "audit_policy" in payload
    assert "classification_rules" in payload["audit_policy"]
    assert "decision_governance" in payload["audit_policy"]["classification_rules"]


def test_coverage_policy_includes_architecture_debt_in_unified_result(
    tmp_path: Path,
) -> None:
    config = load_coverage_policy_config(Path("config/quality/coverage-targets.json"))
    coverage_path = _coverage_file(
        tmp_path,
        {
            "src/ai4binance/governance/dge_engine.py": _summary(
                statements=100,
                missing=0,
                branches=20,
                missing_branches=0,
            )
        },
    )
    registry = load_logical_architecture_registry(
        Path("docs/registries/registry_logical_architecture.yaml"),
        schema_root=Path("schemas"),
    )

    with pytest.raises(ValueError, match="repository_root is required"):
        evaluate_coverage_policy(
            config,
            load_file_coverage(coverage_path),
            architecture_registry=registry,
            generated_at=NOW,
        )

    summary = evaluate_coverage_policy(
        config,
        load_file_coverage(coverage_path),
        architecture_registry=registry,
        repository_root=Path("."),
        generated_at=NOW,
    )

    assert summary.policy_result == "BASELINE_DEBT"
    assert summary.architecture_assurance is not None
    assert any(
        failure.startswith("security_controls:security-controls:NOT_MEASURED")
        for failure in summary.architecture_failures
    )
    assert not any(
        failure.startswith("security_controls:NOT_DECLARED:")
        for failure in summary.architecture_failures
    )
    assert summary.critical_behavior_failures
    assert summary.execution_allowed is False
    markdown = render_coverage_policy_markdown(summary)
    assert "## Architecture Assurance" in markdown
    assert "## Critical Behavior Assurance" in markdown
    assert (
        "| security_controls | T0 | security-controls | NOT_MEASURED | N/A |"
        in markdown
    )


def test_coverage_policy_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    coverage_path = tmp_path / "coverage.json"
    config_path = tmp_path / "coverage-targets.json"
    output_json = tmp_path / "coverage_summary.json"
    output_markdown = tmp_path / "coverage_summary.md"
    coverage_path.write_text(
        json.dumps(
            {
                "totals": {"percent_covered": 100.0},
                "files": {
                    "src/ai4binance/governance/blockers.py": {
                        "summary": _summary(
                            statements=100,
                            missing=0,
                            branches=10,
                            missing_branches=0,
                        )
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "coverage_policy": {
                    "policy_id": "AI4B-POL-QUALITY-COVERAGE-001",
                    "governed_minimum": 95.0,
                    "remediation_trigger": 93.0,
                    "enforcement_mode": "baseline_migration",
                    "branch_minimum": 95.0,
                },
                "families": {
                    "policy": {
                        "description": "Policy",
                        "include": ["src/ai4binance/governance/**"],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--coverage-json",
            str(coverage_path),
            "--config",
            str(config_path),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["policy_result"] == "PASS"
    assert payload["total_coverage_percent"] == 100.0
    assert payload["coverage_source"] == "coverage.py json totals.percent_covered"
    assert payload["execution_allowed"] is False
    markdown = output_markdown.read_text(encoding="utf-8")
    assert "document_id: AI4B-QUALITY-EVID-COVERAGE-REALISM-001" in markdown
    assert "Total coverage: `100.00%`" in markdown
    assert "## Realism Proof" in markdown


def test_total_coverage_percent_loads_from_coverage_json(tmp_path: Path) -> None:
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps({"totals": {"percent_covered": 90.015}, "files": {}}),
        encoding="utf-8",
    )

    assert load_total_coverage_percent(coverage_path) == 90.02


def test_coverage_policy_rejects_invalid_enforcement_mode() -> None:
    with pytest.raises(ValueError, match="enforcement_mode"):
        CoveragePolicyConfig(
            policy_id="AI4B-POL-QUALITY-COVERAGE-001",
            governed_minimum=95.0,
            remediation_trigger=93.0,
            enforcement_mode="silent",
            branch_minimum=95.0,
            families=(
                CoverageFamilyConfig(
                    name="policy",
                    description="Policy",
                    include=("src/ai4binance/governance/**",),
                ),
            ),
        )


def test_coverage_policy_models_reject_invalid_debt_and_authority_states() -> None:
    config = _config()
    with pytest.raises(ValueError, match="cannot exceed governed_minimum"):
        replace(config, remediation_trigger=96.0)
    with pytest.raises(ValueError, match="at least one family"):
        replace(config, families=())
    with pytest.raises(ValueError, match="families must be unique"):
        replace(config, families=(config.families[0], config.families[0]))
    with pytest.raises(ValueError, match="cannot be negative"):
        FileCoverage(
            path="src/example.py",
            statements=-1,
            covered_lines=0,
            missing_lines=0,
            branches=0,
            covered_branches=0,
            missing_branches=0,
            percent_covered=0.0,
        )

    result = CoverageFamilyResult(
        target="policy",
        coverage_family="policy",
        source_paths=("src/example.py",),
        statement_coverage=100.0,
        branch_coverage=100.0,
        covered_lines=1,
        missing_lines=0,
        covered_branches=0,
        missing_branches=0,
        policy_threshold=95.0,
        coverage_gap=0.0,
        policy_state="PASS",
    )
    with pytest.raises(ValueError, match="policy_state is invalid"):
        replace(result, policy_state="UNKNOWN")

    summary = evaluate_coverage_policy(config, (), generated_at=NOW)
    assert summary.to_payload()["promotion_status"] == "RESEARCH_ONLY"
    with pytest.raises(ValueError, match="policy_result is invalid"):
        replace(summary, policy_result="UNKNOWN")
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(summary, execution_allowed=True)


def test_coverage_policy_config_rejects_non_mapping_and_invalid_patterns(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "coverage-targets.json"
    config_path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_coverage_policy_config(config_path)

    config_path.write_text(
        json.dumps(
            {
                "coverage_policy": {
                    "policy_id": "policy",
                    "governed_minimum": 95.0,
                    "remediation_trigger": 93.0,
                    "enforcement_mode": "baseline_migration",
                    "branch_minimum": 95.0,
                },
                "families": {
                    "policy": {
                        "description": "Policy",
                        "include": "src/**",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be a list"):
        load_coverage_policy_config(config_path)


def _config(enforcement_mode: str = "baseline_migration") -> CoveragePolicyConfig:
    return CoveragePolicyConfig(
        policy_id="AI4B-POL-QUALITY-COVERAGE-001",
        governed_minimum=95.0,
        remediation_trigger=93.0,
        enforcement_mode=enforcement_mode,
        branch_minimum=95.0,
        families=(
            CoverageFamilyConfig(
                name="policy",
                description="Policy",
                include=("src/ai4binance/governance/**",),
            ),
            CoverageFamilyConfig(
                name="opportunity",
                description="Opportunity",
                include=("src/ai4binance/opportunity_scanner.py",),
            ),
            CoverageFamilyConfig(
                name="handoff",
                description="Handoff",
                include=("src/ai4binance/core/contracts/handoffs/**",),
            ),
        ),
    )


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


def _coverage_file(tmp_path: Path, files: dict[str, dict[str, float | int]]) -> Path:
    path = tmp_path / "unit-coverage-policy.json"
    path.write_text(
        json.dumps(
            {
                "files": {
                    filename: {"summary": summary}
                    for filename, summary in files.items()
                }
            }
        ),
        encoding="utf-8",
    )
    return path
