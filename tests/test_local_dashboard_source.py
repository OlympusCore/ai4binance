from __future__ import annotations

import hashlib
import json
import runpy
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ai4binance" / "local_dashboard"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_dashboard_source_builds_deterministic_offline_assets(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "dashboard"
    shutil.copytree(SOURCE, stage)

    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(stage / "build.py.in"),
            str(stage / "design_source.html"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "DASHBOARD_PACKAGE_BUILT"
    assert _sha256(stage / "app.js") == (
        "56c052e1234a1317bf303ed053792c3ec5cc852c5f1b59d24e48415280a5fe31"
    )
    assert _sha256(stage / "app.css") == (
        "820ea8899490af3d761e507a88d0af4fd4ecbf587cbd7118c8faa665b5569cc5"
    )
    assert _sha256(stage / "index.html") == (
        "b80777bf1ce24f8298453f565193691ac64945cc9e16e7ddc00c20e28fb7f701"
    )


def test_dashboard_deployer_preserves_machine_state_and_private_profile() -> None:
    deployer = (ROOT / "scripts" / "deploy_local_dashboard.ps1").read_text(
        encoding="utf-8"
    )

    assert "runtime/dashboard/config.json" in deployer
    assert "runtime/dashboard/browser-profile" in deployer
    assert "source-manifest.json" in deployer
    assert 'live_eligibility_status = "LIVE_ORDER_BLOCKED"' in deployer


def test_dashboard_exposes_useful_cycle_and_producer_health() -> None:
    server = (SOURCE / "server.py.in").read_text(encoding="utf-8")
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")

    assert '"last_success_at"' in server
    assert '"age_seconds"' in server
    assert '"producer_status"' in server
    assert "source.producer_status" in views
    assert "s.age_seconds" in views
    assert "DISABLED" in views


def test_dashboard_recognizes_completed_futures_research() -> None:
    server = (SOURCE / "server.py.in").read_text(encoding="utf-8")

    assert 'result[name].get("status") == "CURRENT"' in server
    assert 'meta["status"] = "READY"' in server
    assert '"unavailable_symbol_count"' in server


def test_virtual_market_separates_trade_records_from_potential_opportunities() -> None:
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")
    wallet = (ROOT / "src" / "ai4binance" / "virtual_wallet_journal.py").read_text(
        encoding="utf-8"
    )

    assert "if(virtual)return;" in views
    assert "potential all-coin opportunities" in views
    assert "Virtual trade records" in views
    assert "payload.trade_records" in views
    assert "completeOpportunityPlan" in views
    assert "Entry / Stop / TP1 / TP2 / TP3 / R/R" in views
    assert "Opportunity generation health" in views
    assert "rejected_by_reason" in views
    assert "CANDIDATES_AVAILABLE_WITH_DATA_GAPS" in views
    assert "Published research opportunities remain visible" in views
    assert "Rejected attempts are diagnostic evidence, not opportunities" in views
    assert "has_complete_measurable_opportunity" in (
        SOURCE / "market_views.py.in"
    ).read_text(encoding="utf-8")
    assert '"generation_health"' in (SOURCE / "market_views.py.in").read_text(
        encoding="utf-8"
    )
    assert "def _dashboard_trade_records" in wallet
    assert "def _trade_record_dashboard_row" in wallet


def test_dashboard_exposes_virtual_runtime_preconditions_without_calling_them_active(
) -> None:
    server = (SOURCE / "server.py.in").read_text(encoding="utf-8")
    views = (SOURCE / "local_views.js").read_text(encoding="utf-8")

    assert '"virtual_runtime_evaluated"' in server
    assert '"virtual_simulation_outcome"' in server
    assert '"risk_approved"' in server
    assert (
        "daemon.virtual_simulation_outcome||projection.status||daemon.status" in views
    )
    assert "Runtime evaluated" in views
    assert "Risk approved" in views


def test_dashboard_projects_auto_audit_movements_with_method_provenance() -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    project = module["auto_audit_observer_projection"]

    projected = project(
        {
            "status": "RUNNING_WITH_BLOCKERS",
            "loop_id": "auto-audit:42",
            "workflow_pattern": "HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER",
            "cycles": [
                {
                    "cycle_index": 1,
                    "observed_at": "2026-09-21T12:00:00+00:00",
                    "system_status": "DEGRADED",
                    "blocker_count": 1,
                    "new_blockers": ["DATA_STALE"],
                    "persistent_blockers": [],
                    "resolved_blockers": [],
                    "action_refs": ["resolve:DATA_STALE"],
                    "system_report_json_path": "runtime/reports/audit.json",
                    "continuous_assurance": {
                        "status": "RUNNING_WITH_BLOCKERS",
                        "route_decisions": [
                            {
                                "trigger_type": "SYSTEM_BLOCKER",
                                "storm_status": "ACCEPTED",
                                "event_id": "event:42",
                                "action_refs": ["run:lean-governance"],
                            }
                        ],
                    },
                }
            ],
        }
    )

    assert projected["movements"] == [
        {
            "cycle_index": 1,
            "observed_at": "2026-09-21T12:00:00+00:00",
            "system_status": "DEGRADED",
            "blocker_count": 1,
            "privacy_leak_status": None,
            "local_qwen_status": None,
            "new_blockers": ["DATA_STALE"],
            "persistent_blockers": [],
            "resolved_blockers": [],
            "action_refs": ["resolve:DATA_STALE"],
            "evidence_ref": "runtime/reports/audit.json",
        }
    ]
    assert projected["recommendations"] == [
        {
            "recommendation": "resolve:DATA_STALE",
            "method": "AUTO_AUDIT_LOOP",
            "method_result": "DEGRADED",
            "observed_at": "2026-09-21T12:00:00+00:00",
            "evidence_ref": "runtime/reports/audit.json",
        },
        {
            "recommendation": "run:lean-governance",
            "method": "CONTINUOUS_ASSURANCE:SYSTEM_BLOCKER",
            "method_result": "ACCEPTED",
            "observed_at": "2026-09-21T12:00:00+00:00",
            "evidence_ref": "event:42",
        },
    ]


def test_dashboard_rejects_auto_audit_artifact_with_execution_authority(
    tmp_path: Path,
) -> None:
    module = runpy.run_path(str(SOURCE / "server.py.in"))
    artifact = tmp_path / "auto-audit-latest.json"
    artifact.write_text(
        json.dumps(
            {
                "execution_allowed": True,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                "cycles": [{"observed_at": datetime.now(UTC).isoformat()}],
            }
        ),
        encoding="utf-8",
    )

    meta, data = module["read_auto_audit_source"](
        artifact,
        86_400,
        now=datetime.now(UTC),
    )

    assert meta["status"] == "INVALID"
    assert data == {}
