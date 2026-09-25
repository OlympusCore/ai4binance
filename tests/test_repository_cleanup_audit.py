from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from ai4binance.cli.commands import available_command_names, canonical_command
from ai4binance.cli.enterprise import repository_cleanup_audit_payload
from ai4binance.cli.output import render_payload
from ai4binance.ops import repository_cleanup_audit as cleanup_audit
from ai4binance.ops.repository_cleanup_audit import (
    CleanupAuditStatus,
    run_repository_cleanup_audit,
)


def test_pyproject_script_entrypoint_preserves_cli_main_contract() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_scripts = pyproject["project"]["scripts"]

    assert project_scripts["ai4binance"] == "ai4binance.cli:main"
    assert project_scripts["ai4binance-mcp"] == "ai4binance.mcp.server:main"


@pytest.fixture
def legacy_root_hygiene(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Exercise legacy-root reporting without depending on mutable runtime files."""
    (tmp_path / "data" / "governance").mkdir(parents=True)
    classify_roots = cleanup_audit._root_hygiene_classifications
    monkeypatch.setattr(
        cleanup_audit,
        "_root_hygiene_classifications",
        lambda root: classify_roots(tmp_path),
    )


@pytest.mark.usefixtures("legacy_root_hygiene")
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
    assert any(
        item.path == "artifacts"
        and item.present is False
        and item.decision == "GENERATED_RUNTIME"
        and item.canonical_target == "runtime/artifacts"
        for item in report.root_hygiene_classifications
    )
    assert any(
        item.path == "data"
        and item.present is True
        and item.decision == "REGISTER"
        and item.canonical_target == "runtime/data"
        and "data/governance" in item.observed_children
        for item in report.root_hygiene_classifications
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
    assert classifications["src/ai4binance/external_intel/__main__.py"] == "ENTRY_POINT"
    assert "src/ai4binance/governance/constitution_sync.py" not in classifications
    assert classifications["src/ai4binance/governance/gate.py"] == "ENTRY_POINT"
    assert "src/ai4binance/governance/repository_validator.py" not in classifications
    assert "src/ai4binance/cli/opportunity_radar_persistence.py" not in classifications
    assert (
        "src/ai4binance/application/opportunity_observation.py" not in classifications
    )
    assert classifications["src/ai4binance/github_radar/__main__.py"] == "ENTRY_POINT"
    assert classifications["src/ai4binance/local_agent/__main__.py"] == "ENTRY_POINT"
    assert (
        classifications["src/ai4binance/ops/quality_gate/__main__.py"] == "ENTRY_POINT"
    )
    assert classifications["src/ai4binance/sandbox.py"] == "KEEP"
    assert classifications["src/ai4binance/application/virtual_runtime.py"] == "KEEP"
    assert classifications["src/ai4binance/markets.py"] == "KEEP"
    assert classifications["src/ai4binance/observability/local.py"] == "KEEP"
    assert classifications["src/ai4binance/ops/python_migration_benchmark.py"] == "KEEP"
    assert classifications["src/ai4binance/ops/python_runtime_removal_gate.py"] == (
        "KEEP"
    )
    assert classifications["src/ai4binance/runtime_artifacts/layout.py"] == "KEEP"
    reviews = {item.site: item.status for item in report.broad_exception_reviews}
    assert reviews["src/ai4binance/market_context.py:281"] == "NARROWED"
    assert (
        reviews["src/ai4binance/infrastructure/subprocess/sandbox.py:230"] == "NARROWED"
    )
    assert (
        reviews["src/ai4binance/infrastructure/security/scanner.py:121"] == "NARROWED"
    )
    assert (
        reviews["src/ai4binance/execution/live_spot.py:331"]
        == "RETAINED_FAIL_CLOSED_BOUNDARY"
    )
    assert (
        reviews["src/ai4binance/events/delivery.py:288"]
        == "RETAINED_FAIL_CLOSED_BOUNDARY"
    )
    assert (
        reviews["src/ai4binance/events/journal.py:456"]
        == "RETAINED_FAIL_CLOSED_BOUNDARY"
    )
    assert not any(
        item.site.startswith("src/ai4binance/events/")
        and item.status == "DEFERRED_FAIL_CLOSED_BOUNDARY"
        for item in report.broad_exception_reviews
    )
    assert any(
        package.package_id == "RF-006" and "accounting/records.py" in package.problem
        for package in report.work_packages
    )


def test_cleanup_audit_registry_shows_governed_evidence_chain() -> None:
    report = run_repository_cleanup_audit(Path.cwd())

    classification = next(
        item
        for item in report.static_unimported_classifications
        if item.path == "src/ai4binance/governance/gate.py"
    )

    assert set(classification.evidence_refs) >= {
        "src/ai4binance/governance/gate.py:__main__",
        "tests/test_governance_gate.py",
        "tests/test_artifact_hygiene_scripts.py",
        "scripts/quality.ps1",
        "docs/standards/standard_repository_validator_governance.md",
    }

    assert all(
        item.path != "src/ai4binance/governance/repository_validator.py"
        for item in report.static_unimported_classifications
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
    assert "root_hygiene_classifications" in report
    assert "static_unimported_classifications" in report
    assert "broad_exception_reviews" in report


@pytest.mark.usefixtures("legacy_root_hygiene")
def test_repository_cleanup_audit_text_summarizes_structure_classifications() -> None:
    payload = repository_cleanup_audit_payload()
    text = render_payload(
        payload,
        output_format="text",
        command="repository-cleanup-audit",
    )

    assert (
        "static_file_decisions: ARCHIVE_CANDIDATE=13, ENTRY_POINT=11, KEEP=25" in text
    )
    report = payload["report"]
    assert isinstance(report, dict)
    static_classifications = report["static_unimported_classifications"]
    assert isinstance(static_classifications, list)
    historical_orchestration = next(
        item
        for item in static_classifications
        if item["path"] == "src/ai4binance/historical_replay_application.py"
    )
    assert historical_orchestration["decision"] == "KEEP"
    assert "folder_decisions:" in text
    assert "GENERATED=3" in text
    assert "root_hygiene_decisions: GENERATED_RUNTIME=1, REGISTER=1" in text
    assert (
        "exception_reviews: DEFERRED_FAIL_CLOSED_BOUNDARY=15, NARROWED=4, "
        "RETAINED_FAIL_CLOSED_BOUNDARY=5"
    ) in text
    assert "RF-006 P3_REFACTOR_PACKAGE risk=Medium" in text


def test_root_hygiene_accepts_canonical_storage_without_legacy_directories(
    tmp_path: Path,
) -> None:
    classifications = cleanup_audit._root_hygiene_classifications(tmp_path)
    assert {item.path for item in classifications} == {"artifacts", "data"}
    assert all(
        not item.present and item.decision == "GENERATED_RUNTIME"
        for item in classifications
    )
    assert {item.canonical_target for item in classifications} == {
        "runtime/artifacts",
        "runtime/data",
    }
    assert not (tmp_path / "data").exists()
