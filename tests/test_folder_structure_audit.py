"""Folder structure audit reports generated pytest artifacts without cleanup."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.ops.folder_structure_audit import (
    FolderRecommendation,
    FolderStructureAuditConfig,
    FolderStructureAuditWriter,
    main,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def test_folder_audit_detects_pytest_artifacts_and_persists_report(
    tmp_path: Path,
) -> None:
    (tmp_path / ".pytest-basetemp-legacy").mkdir()
    (tmp_path / ".pytest-basetemp-legacy" / "node.txt").write_text(
        "temporary pytest output",
        encoding="utf-8",
    )
    (tmp_path / ".tmp").mkdir()
    (tmp_path / ".tmp-alias-check").mkdir()
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "src").mkdir()
    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "folder_structure_audit"
    )

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(
            repository_root=tmp_path,
            output_directory=output,
            stale_after_days=1,
        )
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    assert entries[".pytest-basetemp-legacy"].classification == (
        "PYTEST_GENERATED_ARTIFACT"
    )
    assert entries[".pytest-basetemp-legacy"].recommendation == (
        FolderRecommendation.CLEAN_AFTER_APPROVAL
    )
    assert entries[".pytest-basetemp-legacy"].cleanup_probe_status == (
        "ACCESS_PROBE_READABLE"
    )
    assert entries[".pytest-basetemp-legacy"].delete_probe_status == (
        "NOT_EXECUTED_REPORT_ONLY"
    )
    assert entries[".pytest-basetemp-legacy"].cleanup_blocker is None
    assert entries[".pytest-basetemp-legacy"].acl_readable is True
    assert entries[".tmp"].classification == "GENERATED_TEST_TEMP"
    assert entries[".tmp-alias-check"].classification == "GENERATED_TEST_TEMP"
    assert entries["src"].recommendation == FolderRecommendation.KEEP
    assert entries["src"].cleanup_probe_status == "NOT_APPLICABLE"
    assert entries["src"].delete_probe_status == "NOT_APPLICABLE"
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert (output / "latest.json").is_file()
    assert (output / "latest.md").is_file()
    latest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert latest["mode"] == "REPORT_ONLY"
    assert "PYTEST_GENERATED_FOLDER_PRESENT" in latest["blockers"]
    recommendation_titles = {item["title"] for item in latest["recommendations"]}
    assert "Diagnose .pytest_cache ACL before cleanup" in recommendation_titles


def test_folder_audit_marks_protected_state_for_manual_review(
    tmp_path: Path,
) -> None:
    (tmp_path / "secrets").mkdir()
    (tmp_path / ".venv").mkdir()
    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "folder_structure_audit"
    )

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output)
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    assert entries["secrets"].recommendation == FolderRecommendation.REVIEW_MANUALLY
    assert entries[".venv"].recommendation == FolderRecommendation.KEEP
    assert entries["secrets"].cleanup_probe_status == "NOT_APPLICABLE"
    assert all(entry.recommendation != "DELETE" for entry in report.folders)


def test_folder_audit_classifies_skill_staging_as_quarantined_review_area(
    tmp_path: Path,
) -> None:
    (tmp_path / "runtime" / "skill_staging").mkdir(parents=True)
    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "folder_structure_audit"
    )

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output)
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    staging = entries["runtime/skill_staging"]
    assert staging.classification == "QUARANTINED_SKILL_STAGING"
    assert staging.recommendation == FolderRecommendation.REVIEW_MANUALLY
    assert staging.gitignore_expected is True
    assert staging.cleanup_probe_status == "NOT_APPLICABLE"
    assert "manual review and PR approval" in staging.rationale


def test_folder_audit_rejects_invalid_config_and_unsafe_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="stale_after_days"):
        FolderStructureAuditConfig(tmp_path, tmp_path / "out", stale_after_days=0)
    with pytest.raises(ValueError, match="measure_file_limit"):
        FolderStructureAuditConfig(tmp_path, tmp_path / "out", measure_file_limit=0)
    with pytest.raises(ValueError, match="existing directory"):
        FolderStructureAuditWriter(
            FolderStructureAuditConfig(tmp_path / "missing", tmp_path / "out")
        ).run(clock=lambda: NOW)
    with pytest.raises(ValueError, match="inside repository"):
        FolderStructureAuditWriter(
            FolderStructureAuditConfig(tmp_path, tmp_path.parent / "outside")
        ).run(clock=lambda: NOW)


def test_folder_audit_classifies_runtime_cache_and_legacy_paths(
    tmp_path: Path,
) -> None:
    for relative in (
        ".tmp",
        ".tmp-alias-check",
        ".test-tmp",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "runtime",
        "runtime/analysis",
        "runtime/data",
        "runtime/state",
        "runtime/cache",
        "runtime/logs",
        "runtime/audit",
        "runtime/audit/repository-validator/runs",
        "runtime/artifacts",
        "runtime/artifacts/maintenance_archive",
        "runtime/artifacts/coverage",
        "runtime/quality",
        "runtime/reports",
        "runtime/test",
        "runtime/test/acl",
        "runtime/test/hypothesis",
        "runtime/test/pytest",
        "runtime/test/repository-validator/runs",
        "runtime/tmp",
        "runtime/tmp/test_temp",
        "runtime/tmp/process",
        "runtime/tmp/process/pytest",
        "runtime/tmp/process/pytest/session-a",
        "runtime/tmp/pytest",
        "runtime/models",
        "runtime/pytest-basetemp-legacy",
        "artifacts/test_temp",
        "artifacts/maintenance-archive",
        "backtest/validation",
        "runtime/artifacts/research/backtest/validation",
        "runtime/artifacts/repository_validation/folder_structure_audit",
        "analysis",
        "custom_project",
    ):
        (tmp_path / relative).mkdir(parents=True)
    (tmp_path / ".mypy_cache" / "cache.bin").write_text("cache", encoding="utf-8")
    (tmp_path / "artifacts" / "test_temp" / "run.log").write_text(
        "log",
        encoding="utf-8",
    )
    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "folder_structure_audit"
    )

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output)
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    assert entries[".test-tmp"].classification == "GENERATED_TEST_TEMP"
    assert entries[".tmp"].classification == "GENERATED_TEST_TEMP"
    assert entries[".tmp-alias-check"].classification == "GENERATED_TEST_TEMP"
    assert entries[".mypy_cache"].classification == "TOOL_CACHE"
    assert entries["htmlcov"].classification == "GENERATED_COVERAGE_REPORT"
    assert entries["runtime"].classification == "CANONICAL_RUNTIME_ROOT"
    assert entries["runtime/analysis"].classification == "CANONICAL_RUNTIME_SUBTREE"
    assert entries["runtime/data"].classification == "CANONICAL_RUNTIME_SUBTREE"
    assert (
        entries["runtime/audit/repository-validator/runs"].classification
        == "CANONICAL_RUNTIME_SUBTREE"
    )
    assert (
        entries["runtime/artifacts/coverage"].classification
        == "CANONICAL_RUNTIME_SUBTREE"
    )
    assert entries["runtime/quality"].classification == "CANONICAL_RUNTIME_SUBTREE"
    assert entries["runtime/artifacts/maintenance_archive"].classification == (
        "GENERATED_RUNTIME_ARTIFACT"
    )
    assert entries["runtime/test"].classification == "CANONICAL_RUNTIME_SUBTREE"
    assert entries["runtime/test/acl"].classification == "CANONICAL_RUNTIME_SUBTREE"
    assert (
        entries["runtime/test/repository-validator/runs"].classification
        == "CANONICAL_RUNTIME_SUBTREE"
    )
    assert entries["runtime/tmp/process"].classification == (
        "CANONICAL_RUNTIME_SUBTREE"
    )
    assert entries["runtime/tmp/process/pytest"].classification == (
        "CANONICAL_RUNTIME_SUBTREE"
    )
    assert entries["runtime/tmp/test_temp"].classification == (
        "ACL_FORCED_GENERATED_ARTIFACT"
    )
    assert entries["runtime/tmp/process/pytest/session-a"].classification == (
        "PYTEST_GENERATED_ARTIFACT"
    )
    assert entries["runtime/tmp/pytest"].classification == ("PYTEST_GENERATED_ARTIFACT")
    assert entries["runtime/models"].classification == "PROTECTED_LOCAL_STATE"
    assert entries["runtime/pytest-basetemp-legacy"].classification == (
        "PYTEST_GENERATED_ARTIFACT"
    )
    assert (
        entries["artifacts/test_temp"].classification == "ACL_FORCED_GENERATED_ARTIFACT"
    )
    assert (
        entries["artifacts/maintenance-archive"].classification == "LEGACY_RUNTIME_ROOT"
    )
    assert (
        entries[
            "runtime/artifacts/repository_validation/folder_structure_audit"
        ].classification
        == "CANONICAL_RUNTIME_SUBTREE"
    )
    assert (
        entries["backtest/validation"].classification
        == "LEGACY_BACKTEST_VALIDATION_ALIAS"
    )
    assert (
        entries["runtime/artifacts/research/backtest/validation"].classification
        == "CANONICAL_RUNTIME_SUBTREE"
    )
    assert entries["analysis"].classification == "LEGACY_DOMAIN_STATE_OR_EVIDENCE_ROOT"
    assert entries["custom_project"].classification == "PROJECT_FOLDER"
    recommendation_titles = {item.title for item in report.recommendations}
    assert "Clean local tool caches after approval" in recommendation_titles
    assert "Review manual-scope folders" in recommendation_titles


def test_folder_audit_aligns_repository_definition_and_registered_roots(
    tmp_path: Path,
) -> None:
    for relative in (
        "config",
        "schemas",
        "policies",
        "workflows",
        "factory",
        "ontology",
        "spot",
        "alerts",
        "futures",
        "intelligence",
        "news",
    ):
        (tmp_path / relative).mkdir()
    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "folder_structure_audit"
    )

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output)
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    for relative in ("config", "schemas", "policies", "workflows"):
        assert entries[relative].classification == "SOURCE_OR_DOCUMENTATION"
        assert entries[relative].recommendation == FolderRecommendation.KEEP
    assert entries["factory"].classification == (
        "REGISTERED_OPERATIONAL_SUPPORT_SURFACE"
    )
    assert entries["factory"].recommendation == FolderRecommendation.REVIEW_MANUALLY
    assert entries["ontology"].classification == "LEGACY_MACHINE_MIRROR"
    assert entries["ontology"].recommendation == FolderRecommendation.REVIEW_MANUALLY
    assert entries["spot"].classification == "REGISTERED_PROJECT_FOLDER"
    assert entries["spot"].recommendation == FolderRecommendation.KEEP
    for relative in ("alerts", "futures", "intelligence", "news"):
        assert entries[relative].classification == (
            "REGISTERED_OPTIONAL_PROJECT_FOLDER"
        )
        assert entries[relative].recommendation == (
            FolderRecommendation.REVIEW_MANUALLY
        )


def test_folder_audit_marks_stale_generated_folder_and_cli_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stale = tmp_path / ".pytest-audit-temp9"
    stale.mkdir()
    old_file = stale / "old.txt"
    old_file.write_text("old", encoding="utf-8")
    old_mtime = (NOW - timedelta(days=2)).timestamp()
    os.utime(old_file, (old_mtime, old_mtime))

    output = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "repository_validation"
        / "folder_structure_audit"
    )
    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output, stale_after_days=1)
    ).run(clock=lambda: NOW)
    stale_entry = {entry.path: entry for entry in report.folders}[".pytest-audit-temp9"]

    assert "STALE_GENERATED_FOLDER_PRESENT" in stale_entry.blockers
    assert "PYTEST_GENERATED_FOLDER_PRESENT" in stale_entry.blockers
    assert (
        main(
            (
                "--repository-root",
                str(tmp_path),
                "--output-directory",
                str(output),
                "--stale-after-days",
                "1",
            )
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_allowed"] is False
