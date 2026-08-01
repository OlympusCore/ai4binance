"""Folder structure audit reports generated pytest artifacts without cleanup."""

import json
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.ops.folder_structure_audit import (
    FolderRecommendation,
    FolderStructureAuditConfig,
    FolderStructureAuditWriter,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def test_folder_audit_detects_pytest_artifacts_and_persists_report(
    tmp_path: Path,
) -> None:
    (tmp_path / ".pytest-audit-temp3").mkdir()
    (tmp_path / ".pytest-audit-temp3" / "node.txt").write_text(
        "temporary pytest output",
        encoding="utf-8",
    )
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "src").mkdir()
    output = tmp_path / "Artifacts" / "folder-structure-audit"

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(
            repository_root=tmp_path,
            output_directory=output,
            stale_after_days=1,
        )
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    assert entries[".pytest-audit-temp3"].classification == (
        "PYTEST_GENERATED_ARTIFACT"
    )
    assert entries[".pytest-audit-temp3"].recommendation == (
        FolderRecommendation.CLEAN_AFTER_APPROVAL
    )
    assert entries[".pytest-audit-temp3"].cleanup_probe_status == (
        "ACCESS_PROBE_READABLE"
    )
    assert entries[".pytest-audit-temp3"].delete_probe_status == (
        "NOT_EXECUTED_REPORT_ONLY"
    )
    assert entries[".pytest-audit-temp3"].cleanup_blocker is None
    assert entries[".pytest-audit-temp3"].acl_readable is True
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
    (tmp_path / "Secrets").mkdir()
    (tmp_path / ".venv").mkdir()
    output = tmp_path / "Artifacts" / "folder-structure-audit"

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output)
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    assert entries["Secrets"].recommendation == FolderRecommendation.REVIEW_MANUALLY
    assert entries[".venv"].recommendation == FolderRecommendation.KEEP
    assert entries["Secrets"].cleanup_probe_status == "NOT_APPLICABLE"
    assert all(entry.recommendation != "DELETE" for entry in report.folders)


def test_folder_audit_classifies_skill_staging_as_quarantined_review_area(
    tmp_path: Path,
) -> None:
    (tmp_path / "skill-staging").mkdir()
    output = tmp_path / "Artifacts" / "folder-structure-audit"

    report = FolderStructureAuditWriter(
        FolderStructureAuditConfig(tmp_path, output)
    ).run(clock=lambda: NOW)

    entries = {entry.path: entry for entry in report.folders}
    staging = entries["skill-staging"]
    assert staging.classification == "QUARANTINED_SKILL_STAGING"
    assert staging.recommendation == FolderRecommendation.REVIEW_MANUALLY
    assert staging.gitignore_expected is True
    assert staging.cleanup_probe_status == "NOT_APPLICABLE"
    assert "manual review and PR approval" in staging.rationale
