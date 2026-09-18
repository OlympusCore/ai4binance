from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from ai4binance.events.traceability import (
    CanonicalTraceJournal,
    CanonicalTraceRecord,
    ConsequentialTraceKind,
    canonical_trace_journal_path,
    canonical_trace_sha256,
)
from ai4binance.governance.architecture import load_logical_architecture_registry
from ai4binance.governance.enforcement.inventory import (
    EnforcementCoverageState,
    EnforcementInventory,
    EnforcementInventoryEntry,
)
from ai4binance.ops import kaizen_quality
from ai4binance.ops.architecture_migration import (
    ArchitectureMigrationAction,
    ArchitectureMigrationClassification,
)
from ai4binance.ops.architecture_projection import (
    ArchitectureProjectionComponent,
    build_canonical_architecture_projection,
)
from ai4binance.ops.kaizen_quality import (
    build_architecture_baseline,
    build_instruction_baseline,
    build_instruction_context_benchmark,
    build_kaizen_quality_snapshot,
    load_current_gate_evidence,
    required_audit_contract_fields,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
ROOT_INSTRUCTION_TOKEN_BUDGET = 1_000
ROOT_INSTRUCTION_SECTION_BUDGET = 16
ROOT_INSTRUCTION_LINE_BUDGET = 140
SCOPED_INSTRUCTION_PATHS = {
    "src/ai4binance/governance/AGENTS.md",
    "tests/AGENTS.md",
}
SCOPED_INSTRUCTION_TOKEN_BUDGET = 200
SCOPED_INSTRUCTION_TOTAL_TOKEN_BUDGET = 360
SCOPED_INSTRUCTION_SECTION_BUDGET = 4
SCOPED_INSTRUCTION_LINE_BUDGET = 40
PROVIDER_INSTRUCTION_CONTRACTS = {
    "CLAUDE.md": ("claude_provider_adapter", "provider_adapter", 200),
    "GEMINI.md": ("gemini_provider_adapter", "provider_adapter", 200),
    "docs/providers/instruction_claude_provider.md": (
        "claude_provider_adapter",
        "claude_provider_adapter",
        500,
    ),
    "docs/providers/instruction_codex_provider.md": (
        "codex_provider_adapter",
        "codex_provider_adapter",
        800,
    ),
}
PROVIDER_INSTRUCTION_TOTAL_TOKEN_BUDGET = 1_650
PROVIDER_CONTEXT_CHAINS = {
    "CODEX": (
        ("AGENTS.md", "docs/providers/instruction_codex_provider.md"),
        1_750,
    ),
    "CLAUDE": (
        (
            "AGENTS.md",
            "CLAUDE.md",
            "docs/providers/instruction_claude_provider.md",
        ),
        1_675,
    ),
    "GEMINI": (("AGENTS.md", "GEMINI.md"), 1_175),
}
PROVIDER_EXACT_SHARED_BLOCK_BUDGET = 3
CODEX_REPRESENTATIVE_TASK_CONTEXT_TOKEN_BUDGET = 1_950
TOKEN_ESTIMATE_STATUS = "TOKEN_ESTIMATE"  # nosec B105  # noqa: S105
TOKEN_ESTIMATION_METHOD = "WORD_COUNT_X_1_3_CEILING"  # nosec B105  # noqa: S105


def test_kaizen_snapshot_tracks_blocker_aging_traceability_and_gate_commands(
    tmp_path: Path,
) -> None:
    inventory = EnforcementInventory(
        version="test",
        entries=(
            _entry("governance_control_plane_update", "governance_changes"),
            _entry("approval_record_runtime_mutation", "approval_state_changes"),
        ),
    )
    trace_journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))
    architecture_projection = build_canonical_architecture_projection(
        projection_id="AI4B-ARCH-PROJECTION-001",
        components=(
            ArchitectureProjectionComponent(
                component_id="risk-engine",
                canonical_domain="08_RISK",
                logical_plane="DECISION_EXECUTION",
                dependency_layer="domain",
                runtime_class="HOT_PATH_DETERMINISTIC",
                owner="RiskOwner",
                authority_effect="VETO",
                source_paths=("src/ai4binance/domain/risk.py",),
                contract_refs=("docs/contracts/risk.md",),
                test_refs=("tests/test_risk.py",),
                hot_path=True,
                deterministic=True,
                llm_dependency=False,
            ),
        ),
    )
    trace_journal.append(
        CanonicalTraceRecord.create(
            trace_id="trace:kaizen:governance-control-plane",
            trace_kind=ConsequentialTraceKind.GOVERNED_CHANGE,
            subject_ref="governance_control_plane_update",
            subject_type="CONTROL",
            occurred_at=NOW,
            event_name="GOVERNED_CHANGE_RECORDED",
            event_status="REPORT_ONLY",
            evidence_refs=("enforcement_inventory:governance_control_plane_update",),
            governed_paths=("src/ai4binance/governance/gate.py",),
            subject_sha256=canonical_trace_sha256(
                {"entrypoint_id": "governance_control_plane_update"}
            ),
        )
    )

    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW + timedelta(seconds=30),
        blocker_cycles=(
            (NOW, ("runtime:RUNTIME_DEGRADED", "validation:OOS_MISSING")),
            (
                NOW + timedelta(seconds=30),
                ("runtime:RUNTIME_DEGRADED", "privacy:KVKK_PUBLIC_PRIVACY_LEAK"),
            ),
        ),
        repository_root=tmp_path,
        inventory=inventory,
        trace_journal=trace_journal,
        architecture_projection=architecture_projection,
        logical_architecture_registry=load_logical_architecture_registry(
            ROOT / "docs/registries/registry_logical_architecture.yaml"
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
    )

    payload = snapshot.to_payload()
    assert payload["status"] == "RUNNING_WITH_BLOCKERS"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    logical_registry = cast(dict[str, object], payload["logical_architecture_registry"])
    assert logical_registry["status"] == "AVAILABLE"
    assert payload["full_gate_command"] == ".\\scripts\\quality.ps1"
    fast_feedback_commands = cast(list[str], payload["fast_feedback_commands"])
    assert fast_feedback_commands[0].endswith("tests/test_kaizen_quality.py")
    assert payload["closure_entrypoint_order"] == [
        "governance_control_plane_update",
        "approval_record_runtime_mutation",
    ]
    blocker_signals = cast(list[dict[str, object]], payload["blocker_signals"])
    signals = {item["blocker"]: item for item in blocker_signals}
    assert signals["runtime:RUNTIME_DEGRADED"]["state"] == "PERSISTENT"
    assert signals["runtime:RUNTIME_DEGRADED"]["age_seconds"] == 30
    assert signals["runtime:RUNTIME_DEGRADED"]["evidence_ref"] == (
        "system-report:runtime"
    )
    runtime_proof_command = cast(
        str,
        signals["runtime:RUNTIME_DEGRADED"]["proof_command"],
    )
    assert "tests/test_kaizen_quality.py" in runtime_proof_command
    assert signals["privacy:KVKK_PUBLIC_PRIVACY_LEAK"]["evidence_ref"] == (
        "privacy-leak-guard"
    )
    privacy_proof_command = cast(
        str,
        signals["privacy:KVKK_PUBLIC_PRIVACY_LEAK"]["proof_command"],
    )
    assert "tests/test_privacy_leak_guard.py" in privacy_proof_command
    assert signals["validation:OOS_MISSING"]["state"] == "RESOLVED"
    assert signals["validation:OOS_MISSING"]["evidence_ref"] == (
        "continuous-assurance:validation"
    )
    traceability_matrix = cast(
        list[dict[str, object]],
        payload["traceability_matrix"],
    )
    trace_rows = {item["entrypoint_id"]: item for item in traceability_matrix}
    assert (
        trace_rows["governance_control_plane_update"]["traceability_status"]
        == "RECORDED"
    )
    assert (
        trace_rows["approval_record_runtime_mutation"]["traceability_status"]
        == "REQUIRED_NOT_RECORDED"
    )
    assert "KAIZEN_TRACEABILITY_GAP:approval_record_runtime_mutation" in cast(
        list[str], payload["blockers"]
    )
    audit_contract_checks = cast(
        list[dict[str, object]],
        payload["audit_contract_checks"],
    )
    assert audit_contract_checks[0]["status"] == "PASS"
    runtime_inventory = cast(dict[str, object], payload["runtime_inventory"])
    assert runtime_inventory["root"] == "runtime"
    classifications = cast(
        list[dict[str, object]],
        runtime_inventory["classifications"],
    )
    runtime_artifacts = next(
        item for item in classifications if item["path"] == "runtime/artifacts"
    )
    assert runtime_artifacts["retention_class"] == "AUDIT_CRITICAL"
    assert runtime_artifacts["cleanup_candidate"] is False
    assert runtime_artifacts["approval_required_for_cleanup"] is True
    runtime_state = next(
        item for item in classifications if item["path"] == "runtime/state"
    )
    assert runtime_state["retention_class"] == "PROTECTED_PRIVATE"
    assert runtime_state["cleanup_candidate"] is False
    privacy_classification = cast(str, runtime_state["privacy_classification"])
    assert "private" in privacy_classification
    runtime_tmp = next(
        item for item in classifications if item["path"] == "runtime/tmp"
    )
    assert runtime_tmp["retention_class"] == "EPHEMERAL"
    assert runtime_tmp["cleanup_candidate"] is True
    assert runtime_tmp["cleanup_mode"] == (
        "review-only test and process temporary retention"
    )
    assert runtime_tmp["approval_required_for_cleanup"] is True
    assert runtime_tmp["evidence_critical"] is False
    architecture_baseline = cast(dict[str, object], payload["architecture_baseline"])
    assert architecture_baseline["source_root"] == "src/ai4binance"
    assert architecture_baseline["module_count"] == 0
    architecture_projection_payload = cast(
        dict[str, object], payload["architecture_projection"]
    )
    assert architecture_projection_payload["status"] == "AVAILABLE"
    projection_payload = cast(
        dict[str, object], architecture_projection_payload["projection"]
    )
    assert projection_payload["projection_id"] == "AI4B-ARCH-PROJECTION-001"
    instruction_baseline = cast(dict[str, object], payload["instruction_baseline"])
    assert instruction_baseline["instruction_file_count"] == 0
    assert instruction_baseline["status"] == "READY"
    instruction_benchmark = cast(
        dict[str, object], payload["instruction_context_benchmark"]
    )
    assert instruction_benchmark["status"] == "RUNNING_WITH_BLOCKERS"
    assert instruction_benchmark["token_count_status"] == TOKEN_ESTIMATE_STATUS
    assert instruction_benchmark["execution_allowed"] is False
    assert instruction_benchmark["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    closure_gate = cast(dict[str, object], payload["closure_gate"])
    assert closure_gate["status"] == "RUNNING_WITH_BLOCKERS"
    assert closure_gate["technical_quality_status"] == "TECHNICAL_QUALITY_NOT_VERIFIED"
    assert closure_gate["governance_closure_status"] == (
        "GOVERNANCE_CLOSURE_NOT_VERIFIED"
    )
    assert closure_gate["acceptance_status"] == "ACCEPTANCE_BLOCKED"
    assert closure_gate["execution_allowed"] is False
    assert closure_gate["promotion_status"] == "RESEARCH_ONLY"
    assert closure_gate["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert closure_gate["governance_approval_evidence"] == {
        "change_class": "UNKNOWN",
        "status": "NOT_VERIFIED",
        "required_approval_count": 0,
        "observed_approval_count": 0,
        "hard_veto": True,
        "blockers": ["GOVERNANCE_CLOSURE_EVIDENCE_NOT_ATTACHED"],
    }
    closure_blockers = cast(list[str], closure_gate["blockers"])
    assert "FULL_QUALITY_GATE_EVIDENCE_NOT_ATTACHED" in closure_blockers
    assert "GOVERNANCE_CLOSURE_EVIDENCE_NOT_ATTACHED" in closure_blockers


def test_kaizen_snapshot_binds_logical_registry_to_selected_repository_root(
    tmp_path: Path,
) -> None:
    registry_path = (
        tmp_path / "docs" / "registries" / "registry_logical_architecture.yaml"
    )
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        (ROOT / "docs/registries/registry_logical_architecture.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    schema_target = tmp_path / "schemas" / "architecture"
    schema_target.mkdir(parents=True)
    for schema_path in sorted((ROOT / "schemas" / "architecture").glob("*.json")):
        (schema_target / schema_path.name).write_text(
            schema_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("logical_architecture_root_binding", "governance"),),
        ),
        trace_journal=CanonicalTraceJournal(canonical_trace_journal_path(tmp_path)),
        continuous_assurance_payload=_continuous_assurance_payload(),
    )

    assert snapshot.logical_architecture_registry is None
    assert any(
        blocker.startswith(
            "LOGICAL_ARCHITECTURE_REGISTRY_UNAVAILABLE:"
            "logical architecture repository references are unavailable"
        )
        for blocker in snapshot.blockers
    )


def test_kaizen_snapshot_blocks_missing_continuous_assurance_payload(
    tmp_path: Path,
) -> None:
    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(version="test", entries=(_entry("x", "x"),)),
        continuous_assurance_payload=None,
    )

    payload = snapshot.to_payload()
    assert payload["status"] == "RUNNING_WITH_BLOCKERS"
    audit_contract_checks = cast(
        list[dict[str, object]],
        payload["audit_contract_checks"],
    )
    assert audit_contract_checks[0]["missing_fields"] == ["continuous_assurance"]
    assert "KAIZEN_CONTINUOUS_ASSURANCE_PAYLOAD_MISSING" in cast(
        list[str],
        payload["blockers"],
    )
    assert "execution_allowed" in required_audit_contract_fields()


def test_kaizen_closure_gate_distinguishes_technical_quality_and_governance(
    tmp_path: Path,
) -> None:
    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("runtime_kaizen_closure", "runtime"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
        quality_gate_payload=_quality_gate_payload(),
        governance_gate_payload=_governance_gate_payload(
            status="REQUIRES_APPROVAL",
            approval_status="RUNNING_WITH_BLOCKERS",
            resolver_status="PASS",
            blockers=("C3_HUMAN_GOVERNANCE_APPROVAL_REQUIRED",),
        ),
    )

    payload = snapshot.to_payload()
    closure_gate = cast(dict[str, object], payload["closure_gate"])
    assert closure_gate["status"] == "RUNNING_WITH_BLOCKERS"
    assert closure_gate["technical_quality_status"] == "TECHNICAL_QUALITY_PASS"
    assert closure_gate["governance_closure_status"] == "GOVERNANCE_CLOSURE_BLOCKED"
    assert closure_gate["acceptance_status"] == "ACCEPTANCE_BLOCKED"
    assert closure_gate["execution_allowed"] is False
    assert closure_gate["promotion_status"] == "RESEARCH_ONLY"
    assert closure_gate["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    approval_evidence = cast(
        dict[str, object],
        closure_gate["governance_approval_evidence"],
    )
    assert approval_evidence == {
        "change_class": "C3_GOVERNED",
        "status": "RUNNING_WITH_BLOCKERS",
        "required_approval_count": 2,
        "observed_approval_count": 0,
        "hard_veto": True,
        "blockers": ["C3_HUMAN_GOVERNANCE_APPROVAL_REQUIRED"],
    }
    closure_checks = {
        item["check_id"]: item
        for item in cast(list[dict[str, object]], closure_gate["checks"])
    }
    assert closure_checks["canonical_full_quality_gate_executed"]["status"] == "PASS"
    assert closure_checks["governance_closure_verified"]["status"] == (
        "RUNNING_WITH_BLOCKERS"
    )
    assert "C3_HUMAN_GOVERNANCE_APPROVAL_REQUIRED" in cast(
        list[str],
        closure_checks["governance_closure_verified"]["blockers"],
    )
    assert closure_checks["technical_governance_live_separation"]["status"] == "PASS"


def test_kaizen_closure_gate_accepts_canonical_governance_resolver_payload(
    tmp_path: Path,
) -> None:
    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("canonical_governance_resolver", "governance"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
        quality_gate_payload=_quality_gate_payload(),
        governance_gate_payload={
            "status": "PASS",
            "change_class": "C3_GOVERNED",
            "approval_verification": {
                "status": "PASS",
                "required_approval_count": 2,
                "observed_approval_count": 2,
                "hard_veto": False,
                "blockers": [],
            },
            "deterministic_gate_resolver": {"decision": "PASS"},
            "blockers": [],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )

    closure_gate = cast(dict[str, object], snapshot.to_payload()["closure_gate"])

    assert closure_gate["status"] == "READY"
    assert closure_gate["governance_closure_status"] == "GOVERNANCE_CLOSURE_PASS"
    assert closure_gate["acceptance_status"] == "ACCEPTANCE_READY"


def test_kaizen_closure_gate_retains_legacy_governance_resolver_compatibility(
    tmp_path: Path,
) -> None:
    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("legacy_governance_resolver", "governance"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
        quality_gate_payload=_quality_gate_payload(),
        governance_gate_payload=_governance_gate_payload(
            status="PASS",
            approval_status="PASS",
            resolver_status="PASS",
            blockers=(),
            observed_approval_count=2,
            hard_veto=False,
        ),
    )

    closure_gate = cast(dict[str, object], snapshot.to_payload()["closure_gate"])

    assert closure_gate["status"] == "READY"
    assert closure_gate["governance_closure_status"] == "GOVERNANCE_CLOSURE_PASS"


def test_current_gate_evidence_rejects_mismatched_subjects(tmp_path: Path) -> None:
    gate_directory = tmp_path / "runtime" / "artifacts" / "quality" / "gate"
    gate_directory.mkdir(parents=True)
    quality_payload = {
        "subject_digest": {"subject_sha256": "a" * 64},
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    governance_payload = {
        "subject_digest": {"subject_sha256": "b" * 64},
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    (gate_directory / "deterministic_quality_gate_latest.json").write_text(
        json.dumps(quality_payload), encoding="utf-8"
    )
    (gate_directory / "governance_gate_latest.json").write_text(
        json.dumps(governance_payload), encoding="utf-8"
    )

    evidence = load_current_gate_evidence(tmp_path)

    assert evidence.quality_gate_payload is None
    assert evidence.governance_gate_payload is None
    assert evidence.blockers == ("CURRENT_GATE_EVIDENCE_SUBJECT_MISMATCH",)


def test_current_gate_evidence_fails_closed_when_loader_returns_no_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        kaizen_quality,
        "_load_current_gate_json_object",
        lambda *args, **kwargs: (None, None),
    )

    evidence = load_current_gate_evidence(tmp_path)

    assert evidence.quality_gate_payload is None
    assert evidence.governance_gate_payload is None
    assert evidence.blockers == ("CURRENT_GATE_EVIDENCE_UNAVAILABLE",)


def test_kaizen_runtime_inventory_blocks_unknown_top_level_runtime_path(
    tmp_path: Path,
) -> None:
    unknown = tmp_path / "runtime" / "scratchpad"
    unknown.mkdir(parents=True)
    (tmp_path / "runtime" / "artifacts").mkdir(parents=True)
    (unknown / "note.txt").write_text("local runtime noise\n", encoding="utf-8")

    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("runtime_inventory_test", "runtime"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
    )

    payload = snapshot.to_payload()
    assert payload["status"] == "RUNNING_WITH_BLOCKERS"
    runtime_inventory = cast(dict[str, object], payload["runtime_inventory"])
    assert "RUNTIME_UNKNOWN_TOP_LEVEL_PATH:runtime/scratchpad" in cast(
        list[str],
        runtime_inventory["blockers"],
    )
    assert "RUNTIME_UNKNOWN_TOP_LEVEL_PATH:runtime/scratchpad" in cast(
        list[str],
        payload["blockers"],
    )
    classifications = cast(
        list[dict[str, object]],
        runtime_inventory["classifications"],
    )
    scratchpad = next(
        item for item in classifications if item["path"] == "runtime/scratchpad"
    )
    assert scratchpad["validation_status"] == "UNKNOWN"
    assert scratchpad["retention_class"] == "REVIEW_REQUIRED"
    assert scratchpad["cleanup_candidate"] is False
    assert scratchpad["cleanup_mode"] is None
    assert scratchpad["approval_required_for_cleanup"] is True
    assert scratchpad["evidence_critical"] is False
    assert scratchpad["scanned_file_count"] == 1
    assert scratchpad["scanned_total_bytes"] == (unknown / "note.txt").stat().st_size
    assert scratchpad["scan_truncated"] is False
    assert scratchpad["access_errors"] == []
    assert scratchpad["source_like_file_count"] == 0
    privacy_classification = cast(str, scratchpad["privacy_classification"])
    assert privacy_classification.startswith("unknown")
    assert scratchpad["observed_children"] == ["runtime/scratchpad/note.txt"]


def test_runtime_inventory_reports_placement_drift_and_dashboard_provenance(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "runtime" / "reports"
    dashboard = tmp_path / "runtime" / "dashboard"
    reports.mkdir(parents=True)
    dashboard.mkdir(parents=True)
    (reports / "human.md").write_text("# Report\n", encoding="utf-8")
    (reports / "machine.json").write_text("{}", encoding="utf-8")
    (dashboard / "server.py").write_text("pass\n", encoding="utf-8")

    snapshot = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("runtime_inventory_metrics", "runtime"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
    )

    inventory = cast(dict[str, object], snapshot.to_payload()["runtime_inventory"])
    blockers = cast(list[str], inventory["blockers"])
    assert "RUNTIME_REPORT_PLACEMENT_DRIFT:1" in blockers
    assert "RUNTIME_DASHBOARD_PROVENANCE_MISSING" in blockers
    classifications = cast(list[dict[str, object]], inventory["classifications"])
    reports_row = next(
        item for item in classifications if item["path"] == "runtime/reports"
    )
    dashboard_row = next(
        item for item in classifications if item["path"] == "runtime/dashboard"
    )
    assert reports_row["non_markdown_report_count"] == 1
    assert reports_row["scanned_file_count"] == 2
    assert dashboard_row["source_like_file_count"] == 1
    assert dashboard_row["retention_class"] == "PROTECTED_PRIVATE"


def test_runtime_inventory_requires_market_reset_retention_metadata(
    tmp_path: Path,
) -> None:
    reset = tmp_path / "runtime" / "data" / "market-reset-example"
    reset.mkdir(parents=True)
    (reset / "snapshot.bin").write_bytes(b"snapshot")

    blocked = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("runtime_reset_metadata", "runtime"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
    )
    assert (
        "RUNTIME_DATA_RESET_RETENTION_METADATA_MISSING:"
        "runtime/data/market-reset-example"
    ) in blocked.runtime_inventory.blockers

    (reset / ".ai4binance-retention.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "owner": "DataAcquisition",
                "purpose": "Rollback snapshot",
                "created_at_utc": "2026-09-14T10:54:18+00:00",
                "review_after_utc": "2026-09-21T10:54:18+00:00",
                "disposition": "RETAIN_UNTIL_REVIEW",
                "replacement_path": "runtime/data/market",
                "deletion_authorized": False,
            }
        ),
        encoding="utf-8",
    )
    classified = build_kaizen_quality_snapshot(
        observed_at=NOW,
        blocker_cycles=((NOW, ()),),
        repository_root=tmp_path,
        inventory=EnforcementInventory(
            version="test",
            entries=(_entry("runtime_reset_metadata", "runtime"),),
        ),
        continuous_assurance_payload=_continuous_assurance_payload(),
    )
    assert not any(
        blocker.startswith("RUNTIME_DATA_RESET_RETENTION_METADATA_")
        for blocker in classified.runtime_inventory.blockers
    )


def test_architecture_baseline_measures_internal_imports_cycles_and_hotspots(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src" / "ai4binance" / "sample"
    tests_root = tmp_path / "tests"
    source_root.mkdir(parents=True)
    tests_root.mkdir()
    (tmp_path / "src" / "ai4binance" / "__init__.py").write_text("", encoding="utf-8")
    (source_root / "__init__.py").write_text("", encoding="utf-8")
    (source_root / "alpha.py").write_text(
        "from ai4binance.sample import beta\n", encoding="utf-8"
    )
    (source_root / "beta.py").write_text(
        "from ai4binance.sample import alpha\n", encoding="utf-8"
    )
    (tests_root / "test_alpha.py").write_text(
        "from ai4binance.sample import alpha\n", encoding="utf-8"
    )

    baseline = build_architecture_baseline(tmp_path)

    payload = baseline.to_payload()
    assert payload["module_count"] == 4
    assert payload["import_cycles"] == [
        ["ai4binance.sample.alpha", "ai4binance.sample.beta"]
    ]
    alpha = next(
        module
        for module in cast(list[dict[str, object]], payload["modules"])
        if module["path"] == "ai4binance/sample/alpha.py"
    )
    assert alpha["internal_dependencies"] == ["ai4binance.sample.beta"]
    assert alpha["internal_dependents"] == ["ai4binance.sample.beta"]
    assert alpha["test_owners"] == ["tests/test_alpha.py"]
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    assert len(ledger) == payload["module_count"]
    alpha_classification = next(
        item
        for item in ledger
        if item["source_path"] == "src/ai4binance/sample/alpha.py"
    )
    assert alpha_classification["classification"] == "KEEP"
    assert alpha_classification["confidence"] == "LOW"
    assert alpha_classification["imports"] == ["ai4binance.sample.beta"]
    assert alpha_classification["imported_by"] == ["ai4binance.sample.beta"]
    assert alpha_classification["target_paths"] == ["src/ai4binance/sample/alpha.py"]
    assert alpha_classification["execution_allowed"] is False
    assert alpha_classification["promotion_status"] == "RESEARCH_ONLY"
    assert alpha_classification["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert payload["classification_coverage"] == {
        "classified_module_count": 4,
        "unclassified_module_count": 0,
        "coverage_percent": 100.0,
        "allowed_actions": [
            "KEEP",
            "MOVE",
            "SPLIT",
            "MERGE",
            "FACADE",
            "DEPRECATE",
            "REMOVE_CANDIDATE",
        ],
    }


def test_architecture_migration_ledger_classifies_every_repository_module() -> None:
    baseline = build_architecture_baseline(ROOT)

    payload = baseline.to_payload()
    ledger = cast(list[dict[str, object]], payload["migration_ledger"])
    source_paths = [cast(str, item["source_path"]) for item in ledger]
    action_counts = cast(dict[str, int], payload["migration_action_counts"])

    assert len(ledger) == baseline.module_count
    assert len(set(source_paths)) == baseline.module_count
    assert sum(action_counts.values()) == baseline.module_count
    assert action_counts["DEPRECATE"] == 0
    assert action_counts["REMOVE_CANDIDATE"] == 0
    assert all(cast(list[str], item["target_paths"]) for item in ledger)
    assert all(
        "ARCHITECTURE_CLASSIFICATION_RULE_MISSING"
        not in cast(list[str], item["blockers"])
        for item in ledger
    )
    assert all(item["execution_allowed"] is False for item in ledger)
    assert all(item["promotion_status"] == "RESEARCH_ONLY" for item in ledger)
    assert all(
        item["live_eligibility_status"] == "LIVE_ORDER_BLOCKED" for item in ledger
    )

    by_path = {cast(str, item["source_path"]): item for item in ledger}
    assert (
        by_path["src/ai4binance/application/orchestration/whale_fusion.py"][
            "classification"
        ]
        == "KEEP"
    )
    assert (
        by_path["src/ai4binance/application/whale_fusion.py"]["classification"]
        == "FACADE"
    )
    assert (
        by_path["src/ai4binance/core/contracts/memory.py"]["classification"] == "KEEP"
    )
    historical_evaluation = by_path["src/ai4binance/historical_replay_evaluation.py"]
    assert historical_evaluation["classification"] == "SPLIT"
    assert set(cast(list[str], historical_evaluation["target_paths"])) == {
        "src/ai4binance/domain/research",
        "src/ai4binance/domain/portfolio",
        "src/ai4binance/domain/evidence",
        "src/ai4binance/application/orchestration",
        "src/ai4binance/infrastructure/persistence",
    }
    historical_application = by_path["src/ai4binance/historical_replay_application.py"]
    assert historical_application["classification"] == "MOVE"
    assert historical_application["target_paths"] == [
        "src/ai4binance/application/orchestration/historical_replay.py"
    ]
    historical_persistence = by_path["src/ai4binance/historical_replay_persistence.py"]
    assert historical_persistence["classification"] == "MOVE"
    assert historical_persistence["target_paths"] == [
        "src/ai4binance/infrastructure/persistence/historical_replay.py"
    ]
    virtual_attribution = by_path[
        "src/ai4binance/research/virtual_runtime_attribution.py"
    ]
    assert virtual_attribution["classification"] == "FACADE"
    assert virtual_attribution["target_paths"] == [
        "src/ai4binance/domain/research/virtual_runtime_attribution.py"
    ]
    assert virtual_attribution["facade_required"] is True
    canonical_attribution = by_path[
        "src/ai4binance/domain/research/virtual_runtime_attribution.py"
    ]
    assert canonical_attribution["classification"] == "KEEP"
    assert canonical_attribution["confidence"] == "HIGH"
    assert canonical_attribution["blockers"] == []
    historical_state = by_path["src/ai4binance/historical_replay_state.py"]
    assert historical_state["classification"] == "SPLIT"
    assert set(cast(list[str], historical_state["target_paths"])) == {
        "src/ai4binance/domain/portfolio",
        "src/ai4binance/domain/evidence",
        "src/ai4binance/infrastructure/persistence",
    }
    assert by_path["src/ai4binance/cli/bootstrap/parser.py"]["classification"] == "KEEP"
    assert by_path["src/ai4binance/cli/parser.py"]["classification"] == "FACADE"
    assert by_path["src/ai4binance/cli/bootstrap/shared.py"]["classification"] == "KEEP"
    assert by_path["src/ai4binance/cli/shared.py"]["classification"] == "FACADE"
    assert (
        by_path["src/ai4binance/cli/bootstrap/skill_discovery.py"]["classification"]
        == "KEEP"
    )
    assert (
        by_path["src/ai4binance/cli/skill_discovery.py"]["classification"] == "FACADE"
    )
    assert (
        by_path["src/ai4binance/cli/presentation/output.py"]["classification"] == "KEEP"
    )
    assert by_path["src/ai4binance/cli/output.py"]["classification"] == "FACADE"
    assert by_path["src/ai4binance/core/errors/exchange.py"]["classification"] == "KEEP"
    assert (
        by_path["src/ai4binance/core/exchange_errors.py"]["classification"] == "FACADE"
    )
    assert (
        by_path[
            "src/ai4binance/infrastructure/filesystem/opportunity_artifact_loader.py"
        ]["classification"]
        == "KEEP"
    )
    assert (
        by_path["src/ai4binance/infrastructure/opportunity_artifact_loader.py"][
            "classification"
        ]
        == "FACADE"
    )
    canonical_markets = by_path["src/ai4binance/domain/market/markets.py"]
    assert canonical_markets["classification"] == "KEEP"
    assert canonical_markets["confidence"] == "HIGH"
    assert canonical_markets["blockers"] == []
    assert by_path["src/ai4binance/markets.py"]["classification"] == "FACADE"
    assert (
        by_path["src/ai4binance/infrastructure/observability/local.py"][
            "classification"
        ]
        == "KEEP"
    )
    assert (
        by_path["src/ai4binance/observability/local.py"]["classification"] == "FACADE"
    )
    canonical_runtime_artifact_layout = by_path[
        "src/ai4binance/infrastructure/filesystem/runtime_artifacts/layout.py"
    ]
    assert canonical_runtime_artifact_layout["classification"] == "KEEP"
    assert canonical_runtime_artifact_layout["confidence"] == "HIGH"
    assert canonical_runtime_artifact_layout["blockers"] == []
    assert (
        by_path["src/ai4binance/runtime_artifacts/layout.py"]["classification"]
        == "FACADE"
    )
    canonical_security_scanner = by_path[
        "src/ai4binance/infrastructure/security/scanner.py"
    ]
    assert canonical_security_scanner["classification"] == "KEEP"
    assert canonical_security_scanner["canonical_domain"] == "16_SECURITY"
    assert canonical_security_scanner["runtime_class"] == "GOVERNED_CONTROL"
    assert canonical_security_scanner["confidence"] == "HIGH"
    assert canonical_security_scanner["blockers"] == []
    assert by_path["src/ai4binance/security_scan.py"]["classification"] == "FACADE"
    canonical_sandbox = by_path["src/ai4binance/infrastructure/subprocess/sandbox.py"]
    assert canonical_sandbox["classification"] == "KEEP"
    assert canonical_sandbox["confidence"] == "HIGH"
    assert canonical_sandbox["blockers"] == []
    assert by_path["src/ai4binance/sandbox.py"]["classification"] == "FACADE"
    assert by_path["src/ai4binance/risk.py"]["classification"] == "MOVE"
    assert by_path["src/ai4binance/domain.py"]["classification"] == "SPLIT"
    assert by_path["src/ai4binance/reporting.py"]["classification"] == "MERGE"
    assert (
        by_path["src/ai4binance/application/services/virtual_runtime.py"][
            "classification"
        ]
        == "KEEP"
    )
    virtual_runtime = by_path["src/ai4binance/application/virtual_runtime.py"]
    assert virtual_runtime["classification"] == "FACADE"
    assert virtual_runtime["facade_required"] is True
    assert "DYNAMIC_IMPORT" in cast(
        list[str], virtual_runtime["entrypoint_or_dynamic_usage"]
    )
    target_collisions = cast(list[dict[str, object]], payload["target_path_collisions"])
    assert target_collisions == [
        {
            "target_path": ("src/ai4binance/application/orchestration/whale_fusion.py"),
            "source_paths": [
                "src/ai4binance/application/orchestration/whale_fusion.py",
                "src/ai4binance/application/whale_fusion.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/application/services/virtual_runtime.py",
            "source_paths": [
                "src/ai4binance/application/services/virtual_runtime.py",
                "src/ai4binance/application/virtual_runtime.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/cli/bootstrap/parser.py",
            "source_paths": [
                "src/ai4binance/cli/bootstrap/parser.py",
                "src/ai4binance/cli/parser.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/cli/bootstrap/shared.py",
            "source_paths": [
                "src/ai4binance/cli/bootstrap/shared.py",
                "src/ai4binance/cli/shared.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/cli/bootstrap/skill_discovery.py",
            "source_paths": [
                "src/ai4binance/cli/bootstrap/skill_discovery.py",
                "src/ai4binance/cli/skill_discovery.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/cli/presentation/output.py",
            "source_paths": [
                "src/ai4binance/cli/output.py",
                "src/ai4binance/cli/presentation/output.py",
            ],
            "classifications": ["FACADE", "KEEP"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/core/errors/exchange.py",
            "source_paths": [
                "src/ai4binance/core/errors/exchange.py",
                "src/ai4binance/core/exchange_errors.py",
                "src/ai4binance/exchange/errors.py",
            ],
            "classifications": ["KEEP", "FACADE", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/core/serialization/primitives.py",
            "source_paths": [
                "src/ai4binance/opportunity_report.py",
                "src/ai4binance/reporting.py",
            ],
            "classifications": ["MERGE", "MERGE"],
            "status": "EXPECTED_MERGE",
        },
        {
            "target_path": "src/ai4binance/domain/market/markets.py",
            "source_paths": [
                "src/ai4binance/domain/market/markets.py",
                "src/ai4binance/markets.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": (
                "src/ai4binance/domain/research/virtual_runtime_attribution.py"
            ),
            "source_paths": [
                "src/ai4binance/domain/research/virtual_runtime_attribution.py",
                "src/ai4binance/research/virtual_runtime_attribution.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": (
                "src/ai4binance/infrastructure/filesystem/"
                "opportunity_artifact_loader.py"
            ),
            "source_paths": [
                (
                    "src/ai4binance/infrastructure/filesystem/"
                    "opportunity_artifact_loader.py"
                ),
                "src/ai4binance/infrastructure/opportunity_artifact_loader.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": (
                "src/ai4binance/infrastructure/filesystem/runtime_artifacts/__init__.py"
            ),
            "source_paths": [
                (
                    "src/ai4binance/infrastructure/filesystem/"
                    "runtime_artifacts/__init__.py"
                ),
                "src/ai4binance/runtime_artifacts/__init__.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": (
                "src/ai4binance/infrastructure/filesystem/runtime_artifacts/layout.py"
            ),
            "source_paths": [
                (
                    "src/ai4binance/infrastructure/filesystem/"
                    "runtime_artifacts/layout.py"
                ),
                "src/ai4binance/runtime_artifacts/layout.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/infrastructure/observability/__init__.py",
            "source_paths": [
                "src/ai4binance/infrastructure/observability/__init__.py",
                "src/ai4binance/observability/__init__.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/infrastructure/observability/local.py",
            "source_paths": [
                "src/ai4binance/infrastructure/observability/local.py",
                "src/ai4binance/observability/local.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/infrastructure/security/scanner.py",
            "source_paths": [
                "src/ai4binance/infrastructure/security/scanner.py",
                "src/ai4binance/security_scan.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
        {
            "target_path": "src/ai4binance/infrastructure/subprocess/sandbox.py",
            "source_paths": [
                "src/ai4binance/infrastructure/subprocess/sandbox.py",
                "src/ai4binance/sandbox.py",
            ],
            "classifications": ["KEEP", "FACADE"],
            "status": "EXPECTED_FACADE",
        },
    ]
    assert not any(item["status"] == "REVIEW_REQUIRED" for item in target_collisions)


def test_architecture_baseline_has_no_cli_runtime_status_cycle() -> None:
    baseline = build_architecture_baseline(ROOT)

    assert ("ai4binance.cli.runtime", "ai4binance.cli.status") not in (
        baseline.import_cycles
    )


def test_architecture_migration_classification_fails_closed_on_invalid_targets() -> (
    None
):
    classification = ArchitectureMigrationClassification(
        source_path="src/ai4binance/example.py",
        public_symbols=("Example",),
        current_role="EXAMPLE",
        canonical_domain="00_META",
        logical_plane="CONTROL & ASSURANCE PLANE",
        runtime_class="REPORT_ONLY",
        hot_path=False,
        side_effects=(),
        imports=(),
        imported_by=(),
        entrypoint_or_dynamic_usage=(),
        test_owners=("tests/test_example.py",),
        classification=ArchitectureMigrationAction.KEEP,
        target_paths=("src/ai4binance/example.py",),
        facade_required=False,
        confidence="HIGH",
        blockers=(),
        rollback_unit="RESTORE_SOURCE_AND_IMPORTS:src/ai4binance/example.py",
    )

    with pytest.raises(ValueError, match="target paths are required"):
        replace(classification, target_paths=())
    with pytest.raises(ValueError, match="must preserve a facade"):
        replace(
            classification,
            classification=ArchitectureMigrationAction.FACADE,
        )


def test_exchange_error_legacy_imports_are_not_used_by_source_modules() -> None:
    legacy_imports = (
        "from ai4binance.core.exchange_errors import",
        "from ai4binance.exchange.errors import",
    )
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if any(
            legacy_import in path.read_text(encoding="utf-8")
            for legacy_import in legacy_imports
        )
    ]

    assert offenders == []


def test_opportunity_loader_legacy_import_is_not_used_by_source_modules() -> None:
    legacy_import = "from ai4binance.infrastructure.opportunity_artifact_loader import"
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if legacy_import in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_cli_parser_legacy_import_is_not_used_by_source_modules() -> None:
    legacy_imports = (
        "from ai4binance.cli.parser import",
        "from .parser import",
    )
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if any(
            legacy_import in path.read_text(encoding="utf-8")
            for legacy_import in legacy_imports
        )
    ]

    assert offenders == []


def test_cli_output_legacy_import_is_not_used_by_source_modules() -> None:
    legacy_import = "from ai4binance.cli.output import"
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if legacy_import in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_cli_shared_legacy_import_is_not_used_by_source_modules() -> None:
    legacy_imports = (
        "from ai4binance.cli.shared import",
        "from .shared import",
    )
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if any(
            legacy_import in path.read_text(encoding="utf-8")
            for legacy_import in legacy_imports
        )
    ]

    assert offenders == []


def test_cli_skill_discovery_legacy_import_is_not_used_by_source_modules() -> None:
    legacy_import = "from ai4binance.cli.skill_discovery import"
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if legacy_import in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_whale_fusion_legacy_import_is_not_used_by_source_modules() -> None:
    legacy_module = "ai4binance.application.whale_fusion"
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src" / "ai4binance").rglob("*.py"))
        if legacy_module in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_instruction_baseline_measures_scope_metadata_and_exact_overlap(
    tmp_path: Path,
) -> None:
    root_rule = (
        "Shared instruction rule " + "must preserve deterministic evidence. " * 3
    )
    (tmp_path / "AGENTS.md").write_text(
        "\n".join(
            (
                "---",
                "authority_scope: repository_agent_operations",
                "---",
                "# Root",
                "",
                root_rule,
                "",
                "Follow `docs/standards/standard_example.md`.",
            )
        ),
        encoding="utf-8",
    )
    scoped = tmp_path / "src" / "ai4binance" / "governance"
    scoped.mkdir(parents=True)
    (scoped / "AGENTS.md").write_text(
        f"# Governance\n\n{root_rule}\n",
        encoding="utf-8",
    )
    (tmp_path / "runtime" / "generated").mkdir(parents=True)
    (tmp_path / "runtime" / "generated" / "AGENTS.md").write_text(
        "# Generated\n\nThis must not be measured as a repository instruction.\n",
        encoding="utf-8",
    )

    payload = build_instruction_baseline(tmp_path).to_payload()

    assert payload["instruction_file_count"] == 2
    assert payload["scoped_instruction_file_count"] == 1
    assert payload["status"] == "READY"
    documents = cast(list[dict[str, object]], payload["documents"])
    root = next(document for document in documents if document["path"] == "AGENTS.md")
    assert root["scope"] == "ROOT"
    assert root["authority_scope"] == "repository_agent_operations"
    assert root["canonical_references"] == ["docs/standards/standard_example.md"]
    assert root["byte_count"] == (tmp_path / "AGENTS.md").stat().st_size
    assert cast(int, root["estimated_token_count"]) > 0
    overlap = cast(list[dict[str, object]], payload["exact_block_overlaps"])
    assert overlap == [
        {
            "left_path": "AGENTS.md",
            "right_path": "src/ai4binance/governance/AGENTS.md",
            "shared_block_count": 1,
        }
    ]


def test_instruction_context_benchmark_routes_only_nearest_persistent_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("Root instruction.\n", encoding="utf-8")
    provider = tmp_path / "docs" / "providers"
    provider.mkdir(parents=True)
    (provider / "instruction_codex_provider.md").write_text(
        "Codex provider instruction.\n",
        encoding="utf-8",
    )
    governance = tmp_path / "src" / "ai4binance" / "governance"
    governance.mkdir(parents=True)
    (tmp_path / "src" / "AGENTS.md").write_text(
        "Source scope instruction.\n",
        encoding="utf-8",
    )
    (governance / "AGENTS.md").write_text(
        "Governance scope instruction.\n",
        encoding="utf-8",
    )
    tests_scope = tmp_path / "tests"
    tests_scope.mkdir()
    (tests_scope / "AGENTS.md").write_text(
        "Test scope instruction.\n",
        encoding="utf-8",
    )

    payload = build_instruction_context_benchmark(tmp_path).to_payload()
    measurements = {
        cast(str, measurement["task_id"]): measurement
        for measurement in cast(list[dict[str, object]], payload["measurements"])
    }

    assert payload["status"] == "READY"
    assert payload["measurement_type"] == "PERSISTENT_INSTRUCTION_CONTEXT"
    assert payload["token_count_status"] == TOKEN_ESTIMATE_STATUS
    assert payload["token_estimation_method"] == TOKEN_ESTIMATION_METHOD
    assert payload["representative_task_count"] == 8
    assert measurements["T3_GOVERNANCE_CHANGE"]["instruction_paths"] == [
        "AGENTS.md",
        "docs/providers/instruction_codex_provider.md",
        "src/ai4binance/governance/AGENTS.md",
    ]
    assert measurements["T6_TESTS_ONLY_CHANGE"]["instruction_paths"] == [
        "AGENTS.md",
        "docs/providers/instruction_codex_provider.md",
        "tests/AGENTS.md",
    ]
    assert measurements["T4_RISK_CHANGE"]["instruction_paths"] == [
        "AGENTS.md",
        "docs/providers/instruction_codex_provider.md",
        "src/AGENTS.md",
    ]
    assert measurements["T7_QUALITY_GATE_SCRIPT_CHANGE"]["instruction_paths"] == [
        "AGENTS.md",
        "docs/providers/instruction_codex_provider.md",
    ]
    assert all(
        measurement["exact_block_overlap_count"] == 0
        for measurement in measurements.values()
    )
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_instruction_context_benchmark_fails_closed_without_codex_adapter(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("Root instruction.\n", encoding="utf-8")

    payload = build_instruction_context_benchmark(tmp_path).to_payload()

    assert payload["status"] == "RUNNING_WITH_BLOCKERS"
    assert payload["measurements"] == []
    assert payload["blockers"] == [
        "INSTRUCTION_CONTEXT_REQUIRED_DOCUMENT_MISSING:"
        "docs/providers/instruction_codex_provider.md"
    ]
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_repository_instruction_context_benchmark_is_bounded_and_task_routed() -> None:
    payload = build_instruction_context_benchmark(ROOT).to_payload()
    measurements = {
        cast(str, measurement["task_id"]): measurement
        for measurement in cast(list[dict[str, object]], payload["measurements"])
    }

    assert payload["status"] == "READY"
    assert set(measurements) == {
        "T1_ROOT_DOCUMENTATION_EDIT",
        "T2_SRC_PYTHON_IMPLEMENTATION",
        "T3_GOVERNANCE_CHANGE",
        "T4_RISK_CHANGE",
        "T5_EXECUTION_CHANGE",
        "T6_TESTS_ONLY_CHANGE",
        "T7_QUALITY_GATE_SCRIPT_CHANGE",
        "T8_ARCHITECTURE_DOCUMENTATION",
    }
    assert cast(int, payload["max_estimated_instruction_tokens"]) <= (
        CODEX_REPRESENTATIVE_TASK_CONTEXT_TOKEN_BUDGET
    )
    governance_paths = cast(
        list[str], measurements["T3_GOVERNANCE_CHANGE"]["instruction_paths"]
    )
    tests_paths = cast(
        list[str], measurements["T6_TESTS_ONLY_CHANGE"]["instruction_paths"]
    )
    assert governance_paths[-1] == "src/ai4binance/governance/AGENTS.md"
    assert tests_paths[-1] == "tests/AGENTS.md"
    assert all(
        measurement["token_count_status"] == TOKEN_ESTIMATE_STATUS
        for measurement in measurements.values()
    )
    assert all(
        measurement["exact_block_overlap_count"] == 0
        for measurement in measurements.values()
    )


def test_root_instruction_contract_has_bounded_context_and_canonical_references() -> (
    None
):
    payload = build_instruction_baseline(ROOT).to_payload()
    documents = cast(list[dict[str, object]], payload["documents"])
    root = next(document for document in documents if document["path"] == "AGENTS.md")

    assert payload["status"] == "READY"
    assert cast(int, root["estimated_token_count"]) <= ROOT_INSTRUCTION_TOKEN_BUDGET
    assert cast(int, root["section_count"]) <= ROOT_INSTRUCTION_SECTION_BUDGET
    assert cast(int, root["line_count"]) <= ROOT_INSTRUCTION_LINE_BUDGET
    assert set(cast(list[str], root["canonical_references"])) >= {
        "docs/governance/framework_core_vnext_governance.md",
        "docs/governance/policy_organization_constitution_handbook.md",
        "docs/providers/instruction_claude_provider.md",
        "docs/providers/instruction_codex_provider.md",
        "docs/standards/standard_repository_file_governance.md",
    }
    overlaps = cast(list[dict[str, object]], payload["exact_block_overlaps"])
    assert [
        overlap
        for overlap in overlaps
        if overlap["left_path"] == "AGENTS.md" or overlap["right_path"] == "AGENTS.md"
    ] == []


def test_scoped_instruction_contract_has_bounded_unique_context() -> None:
    payload = build_instruction_baseline(ROOT).to_payload()
    documents = cast(list[dict[str, object]], payload["documents"])
    scoped = {
        cast(str, document["path"]): document
        for document in documents
        if document["scope"] == "SCOPED"
    }

    assert payload["status"] == "READY"
    assert set(scoped) == SCOPED_INSTRUCTION_PATHS
    assert payload["scoped_instruction_file_count"] == len(SCOPED_INSTRUCTION_PATHS)
    assert (
        sum(
            cast(int, document["estimated_token_count"]) for document in scoped.values()
        )
        <= SCOPED_INSTRUCTION_TOTAL_TOKEN_BUDGET
    )
    for document in scoped.values():
        assert (
            cast(int, document["estimated_token_count"])
            <= SCOPED_INSTRUCTION_TOKEN_BUDGET
        )
        assert cast(int, document["section_count"]) <= SCOPED_INSTRUCTION_SECTION_BUDGET
        assert cast(int, document["line_count"]) <= SCOPED_INSTRUCTION_LINE_BUDGET

    overlaps = cast(list[dict[str, object]], payload["exact_block_overlaps"])
    assert [
        overlap
        for overlap in overlaps
        if overlap["left_path"] in scoped or overlap["right_path"] in scoped
    ] == []


def test_provider_instruction_contracts_are_subordinate_and_budgeted() -> None:
    payload = build_instruction_baseline(ROOT).to_payload()
    documents = cast(list[dict[str, object]], payload["documents"])
    documents_by_path = {
        cast(str, document["path"]): document for document in documents
    }
    provider_documents = {
        path: document
        for path, document in documents_by_path.items()
        if str(document["authority_scope"]).endswith("_provider_adapter")
    }

    assert payload["status"] == "READY"
    assert set(provider_documents) == set(PROVIDER_INSTRUCTION_CONTRACTS)
    assert (
        sum(
            cast(int, document["estimated_token_count"])
            for document in provider_documents.values()
        )
        <= PROVIDER_INSTRUCTION_TOTAL_TOKEN_BUDGET
    )
    for path, (
        authority_scope,
        source_scope,
        token_budget,
    ) in PROVIDER_INSTRUCTION_CONTRACTS.items():
        document = provider_documents[path]
        text = (ROOT / path).read_text(encoding="utf-8")
        assert document["authority_scope"] == authority_scope
        assert cast(int, document["estimated_token_count"]) <= token_budget
        assert "authority_level: PROVIDER_ADAPTER" in text
        assert "authority_effect: OPERATIONAL_SPECIALIZATION" in text
        assert f"source_of_truth_scope: {source_scope}" in text
        assert "source_of_truth: false" in text
        assert "AGENTS.md" in text
        assert "LIVE_ORDER_BLOCKED" in text

    for paths, token_budget in PROVIDER_CONTEXT_CHAINS.values():
        assert (
            sum(
                cast(int, documents_by_path[path]["estimated_token_count"])
                for path in paths
            )
            <= token_budget
        )

    overlaps = cast(list[dict[str, object]], payload["exact_block_overlaps"])
    provider_overlaps = [
        overlap
        for overlap in overlaps
        if overlap["left_path"] in provider_documents
        and overlap["right_path"] in provider_documents
    ]
    assert (
        sum(cast(int, overlap["shared_block_count"]) for overlap in provider_overlaps)
        <= PROVIDER_EXACT_SHARED_BLOCK_BUDGET
    )
    assert [
        overlap
        for overlap in overlaps
        if "AGENTS.md" in {overlap["left_path"], overlap["right_path"]}
        and (
            overlap["left_path"] in provider_documents
            or overlap["right_path"] in provider_documents
        )
    ] == []


def _entry(entrypoint_id: str, scope_family: str) -> EnforcementInventoryEntry:
    return EnforcementInventoryEntry(
        entrypoint_id=entrypoint_id,
        scope_family=scope_family,
        object_type="CONTROL",
        action="UPDATE",
        integration_surface="kaizen_test",
        current_enforcer="DeterministicEnforcementEngine",
        coverage_state=EnforcementCoverageState.BLOCKED,
        status_rationale="Blocked test surface.",
        authority_source="docs/standards/standard_governed_object_enforcement.md",
        policy_source="src/ai4binance/governance/gate.py",
        blocker_source="config/governance/blocker_registry.yaml",
        tests=("tests/test_kaizen_quality.py",),
        bypass_possible=False,
        consequential=True,
    )


def _continuous_assurance_payload() -> dict[str, object]:
    return {
        "trust_assurance": {
            "provenance": {
                "decision_kind": "CONTINUOUS_ASSURANCE_PLAN",
                "decision_id": "provenance:kaizen-test",
                "provenance_hash": "a" * 64,
                "evidence_refs": ["auto-audit-cycle"],
                "blockers": ["LIVE_ORDER_BLOCKED"],
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        }
    }


def _quality_gate_payload() -> dict[str, object]:
    return {
        "status": "PASS",
        "pytest_pass_count": 3436,
        "quality_evidence_gate": {
            "status": "PASS",
            "quality_gate": {"status": "TECHNICAL_QUALITY_PASS"},
        },
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _governance_gate_payload(
    *,
    status: str,
    approval_status: str,
    resolver_status: str,
    blockers: tuple[str, ...],
    observed_approval_count: int = 0,
    hard_veto: bool = True,
) -> dict[str, object]:
    return {
        "status": status,
        "change_class": "C3_GOVERNED",
        "approval_verification": {
            "status": approval_status,
            "required_approval_count": 2,
            "observed_approval_count": observed_approval_count,
            "hard_veto": hard_veto,
            "blockers": list(blockers),
        },
        "deterministic_resolver": {"status": resolver_status},
        "blockers": list(blockers),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
