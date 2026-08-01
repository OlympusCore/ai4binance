from __future__ import annotations

from pathlib import Path

from ai4binance.cli.commands import available_command_names, canonical_command
from ai4binance.cli.enterprise import repository_cleanup_audit_payload
from ai4binance.cli.output import render_payload
from ai4binance.ops.repository_cleanup_audit import (
    CleanupAuditStatus,
    run_repository_cleanup_audit,
)


def test_repository_cleanup_audit_is_report_only_and_fail_closed() -> None:
    report = run_repository_cleanup_audit(Path.cwd())

    assert report.command == "repository-cleanup-audit"
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert report.files_deleted == 0
    assert report.files_moved == 0
    assert report.files_changed_by_audit == 0
    assert report.packages_installed == 0
    assert report.live_actions == 0
    assert report.inventory.python_modules > 0
    assert report.entry_points.project_scripts["ai4binance"] == "ai4binance.cli:main"
    assert any(
        folder.path == ".pytest_cache"
        and folder.decision == "GENERATED"
        and folder.cleanup_mode == "Caches"
        for folder in report.folder_classifications
    )


def test_repository_cleanup_audit_keeps_dynamic_usage_out_of_delete_claims() -> None:
    report = run_repository_cleanup_audit(Path.cwd())

    assert report.status in {
        CleanupAuditStatus.PASSED,
        CleanupAuditStatus.REVIEW_REQUIRED,
    }
    assert report.exact_import_cycle_count == 0
    assert report.dynamic_usage_files
    assert any("registry" in path for path in report.dynamic_usage_files)
    assert report.static_unimported_files
    assert all(package.approval_required for package in report.work_packages)
    assert {package.package_id for package in report.work_packages} == {
        "RF-001",
        "RF-002",
        "RF-003",
        "RF-004",
        "RF-005",
        "RF-006",
    }
    classifications = {
        item.path: item.decision for item in report.static_unimported_classifications
    }
    assert len(classifications) == len(report.static_unimported_files)
    assert classifications["src/ai4binance/cli.py"] == "ENTRY_POINT"
    assert classifications["src/ai4binance/sandbox.py"] == "KEEP"
    assert not any(
        item.decision == "ARCHIVE_CANDIDATE"
        for item in report.static_unimported_classifications
    )
    reviews = {item.site: item.status for item in report.broad_exception_reviews}
    assert reviews["src/ai4binance/market_context.py:281"] == "NARROWED"
    assert reviews["src/ai4binance/security_scan.py:119"] == "NARROWED"
    assert any(
        package.package_id == "RF-006" and "accounting/records.py" in package.problem
        for package in report.work_packages
    )


def test_repository_cleanup_audit_cli_payload_and_alias() -> None:
    payload = repository_cleanup_audit_payload()

    assert canonical_command("cleanup-audit") == "repository-cleanup-audit"
    assert "repository-cleanup-audit" in available_command_names()
    assert payload["command"] == "repository-cleanup-audit"
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["blockers"] == ()
    report = payload["report"]
    assert isinstance(report, dict)
    assert "folder_classifications" in report
    assert "static_unimported_classifications" in report
    assert "broad_exception_reviews" in report


def test_repository_cleanup_audit_text_summarizes_structure_classifications() -> None:
    text = render_payload(
        repository_cleanup_audit_payload(),
        output_format="text",
        command="repository-cleanup-audit",
    )

    assert "static_file_decisions: ENTRY_POINT=4, KEEP=11" in text
    assert "folder_decisions:" in text
    assert "GENERATED=3" in text
    assert "exception_reviews: DEFERRED_FAIL_CLOSED_BOUNDARY=6, NARROWED=4" in text
    assert "RF-006 P3_REFACTOR_PACKAGE risk=Medium" in text
