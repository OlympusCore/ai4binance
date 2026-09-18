from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity
from ai4binance.enterprise.dashboard import (
    DashboardMetric,
    ExecutiveDashboardSnapshot,
    build_minimum_dashboard_snapshot,
    build_system_report_dashboard_snapshot,
    dashboard_snapshot_summary_payload,
    system_report_dashboard_cards_payload,
)
from ai4binance.enterprise.pilots import (
    PilotReadinessReport,
    PilotStage,
    build_paper_soak_readiness,
    build_shadow_readiness,
)
from ai4binance.enterprise.reviews import (
    PeriodicReviewRecord,
    ReviewCadence,
    ReviewOutcome,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity(
        "wo-1",
        "run-1",
        "trace-1",
        NOW,
        snapshot_id="snapshot-1",
    )


def test_periodic_reviews_enforce_cadence_outputs_without_mutation() -> None:
    monthly = PeriodicReviewRecord(
        identity(),
        "review-1",
        ReviewCadence.MONTHLY,
        DepartmentId.QUALITY_AUDIT,
        "monthly-signal-review",
        ReviewOutcome.CAPA_REQUIRED,
        ("artifact:monthly-review",),
    )

    assert monthly.production_mutation_allowed is False
    assert monthly.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="outside cadence"):
        replace(monthly, outcome=ReviewOutcome.PAPER_SOAK_CANDIDATE)
    with pytest.raises(ValueError, match="mutate production"):
        replace(monthly, production_mutation_allowed=True)
    with pytest.raises(ValueError, match="user approval"):
        replace(monthly, user_approval_required=False)
    with pytest.raises(ValueError, match="identity is required"):
        replace(monthly, review_id=" ")
    with pytest.raises(ValueError, match="evidence refs must be unique"):
        replace(
            monthly,
            evidence_refs=("artifact:monthly-review", "artifact:monthly-review"),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(monthly, execution_allowed=True)


def test_dashboard_snapshot_exposes_status_without_authority() -> None:
    snapshot = build_minimum_dashboard_snapshot(
        identity(),
        quality_gate_status="PASSED",
    )

    assert snapshot.snapshot_ref == "snapshot-1"
    assert snapshot.metrics[0].metric_id == "quality_gate"
    assert snapshot.metrics[1].blockers == ("LIVE_ORDER_BLOCKED",)
    with pytest.raises(ValueError, match="requires metrics"):
        replace(snapshot, metrics=())
    with pytest.raises(ValueError, match="promote"):
        replace(snapshot, promotion_status="PAPER_APPROVED")
    with pytest.raises(ValueError, match="requires blockers"):
        DashboardMetric("metric-1", "Metric", "unknown", "UNKNOWN")
    with pytest.raises(ValueError, match="metric IDs"):
        ExecutiveDashboardSnapshot(
            identity(),
            "snapshot-1",
            (snapshot.metrics[0], snapshot.metrics[0]),
            (),
        )


def test_system_report_dashboard_snapshot_maps_contract_cards() -> None:
    report_summary = {
        "report_id": "system-report:123",
        "status": "RUNNING_WITH_BLOCKERS",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": ("runtime:RUNTIME_DEGRADED",),
        "advanced_agent_operating_contract": {
            "status": "READY",
            "guardrails": (
                "EXPLICIT_POLICY_BOUNDARIES",
                "FAIL_CLOSED_DEFAULTS",
                "BOUNDED_ACTIONS",
                "TOOL_POLICY_ENFORCEMENT",
            ),
            "human_approval_controls": {
                "mode": "HUMAN_IN_THE_LOOP",
                "required_at": "CRITICAL_DECISION_POINTS",
                "gates": (
                    "TRADING_SCOPE",
                    "MONEY_MOVEMENT_SCOPE",
                    "SECRET_ACCESS_SCOPE",
                    "CONNECTOR_SCOPE",
                    "RISK_OR_POLICY_ESCALATION",
                ),
            },
            "blockers": (),
        },
    }

    snapshot = build_system_report_dashboard_snapshot(
        identity(), report_summary=report_summary
    )
    metrics = {metric.metric_id: metric for metric in snapshot.metrics}

    assert snapshot.snapshot_ref == "system-report:123"
    assert metrics["system_report"].status == "WATCH"
    assert metrics["advanced_agent_contract"].status == "OK"
    assert metrics["contract_guardrails"].status == "OK"
    assert metrics["human_approval_controls"].status == "OK"
    assert metrics["live_gate"].status == "BLOCKED"
    assert snapshot.open_action_refs == (
        "resolve:runtime:RUNTIME_DEGRADED",
        "resolve:LIVE_ORDER_BLOCKED",
    )


def test_dashboard_snapshot_summary_payload_marks_missing_controls() -> None:
    report_summary = {
        "report_id": "system-report:456",
        "status": "DEGRADED",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": ("startup:RUNTIME_STATE_MISSING",),
        "advanced_agent_operating_contract": {
            "status": "DEGRADED",
            "guardrails": ("FAIL_CLOSED_DEFAULTS",),
            "human_approval_controls": {
                "mode": "AUTO",
                "required_at": "NEVER",
                "gates": ("TRADING_SCOPE",),
            },
            "blockers": ("ADVANCED_AGENT_CONTRACT_UNAVAILABLE",),
        },
    }

    snapshot = build_system_report_dashboard_snapshot(
        identity(), report_summary=report_summary
    )
    summary = dashboard_snapshot_summary_payload(snapshot)
    blocked_metric_count = cast(int, summary["blocked_metric_count"])
    blocked_metric_ids = cast(tuple[str, ...], summary["blocked_metric_ids"])
    metrics_raw = cast(tuple[object, ...], summary["metrics"])
    metrics = {
        str(item["metric_id"]): item
        for item in metrics_raw
        if isinstance(item, Mapping)
    }

    assert blocked_metric_count >= 4
    assert "contract_guardrails" in blocked_metric_ids
    assert "human_approval_controls" in blocked_metric_ids
    assert "MISSING_GUARDRAIL:EXPLICIT_POLICY_BOUNDARIES" in cast(
        tuple[str, ...], metrics["contract_guardrails"]["blockers"]
    )
    assert "HUMAN_APPROVAL_MODE_INVALID" in cast(
        tuple[str, ...], metrics["human_approval_controls"]["blockers"]
    )


def test_system_report_dashboard_cards_payload_exposes_metric_cards() -> None:
    cards = system_report_dashboard_cards_payload(
        {
            "report_id": "system-report:789",
            "status": "READY",
            "blockers": (),
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "advanced_agent_operating_contract": {
                "status": "READY",
                "guardrails": (
                    "EXPLICIT_POLICY_BOUNDARIES",
                    "FAIL_CLOSED_DEFAULTS",
                    "BOUNDED_ACTIONS",
                    "TOOL_POLICY_ENFORCEMENT",
                ),
                "human_approval_controls": {
                    "mode": "HUMAN_IN_THE_LOOP",
                    "required_at": "CRITICAL_DECISION_POINTS",
                    "gates": (
                        "TRADING_SCOPE",
                        "MONEY_MOVEMENT_SCOPE",
                        "SECRET_ACCESS_SCOPE",
                        "CONNECTOR_SCOPE",
                        "RISK_OR_POLICY_ESCALATION",
                    ),
                },
                "blockers": (),
            },
        }
    )

    assert cast(str, cards["source"]) == "system-report"
    assert cast(int, cards["metric_count"]) == 5
    assert cast(int, cards["blocked_metric_count"]) == 1
    assert cast(tuple[str, ...], cards["open_action_refs"]) == (
        "resolve:LIVE_ORDER_BLOCKED",
    )


def test_shadow_and_paper_pilot_readiness_do_not_create_orders() -> None:
    shadow = build_shadow_readiness(
        identity(),
        pilot_id="pilot-1",
        candidate_ref="candidate-1",
        evidence_refs=("artifact:oos-report",),
    )
    paper = build_paper_soak_readiness(
        identity(),
        pilot_id="pilot-2",
        candidate_ref="candidate-1",
        evidence_refs=("artifact:oos-report", "artifact:user-review"),
    )

    assert shadow.stage is PilotStage.SHADOW
    assert shadow.order_intent == "NONE"
    assert paper.blockers == ("USER_APPROVAL_REQUIRED", "LIVE_ORDER_BLOCKED")
    with pytest.raises(ValueError, match="order intent"):
        replace(shadow, order_intent="BUY")
    with pytest.raises(ValueError, match="mutate portfolio"):
        replace(shadow, portfolio_mutation=True)
    with pytest.raises(ValueError, match="user approval blocker"):
        PilotReadinessReport(
            identity(),
            "pilot-3",
            PilotStage.PAPER_SOAK,
            "candidate-1",
            ("artifact:oos-report",),
            ("LIVE_ORDER_BLOCKED",),
        )


def test_pilot_readiness_rejects_missing_evidence_duplicates_and_authority() -> None:
    shadow = build_shadow_readiness(
        identity(),
        pilot_id="pilot-1",
        candidate_ref="candidate-1",
        evidence_refs=("artifact:oos-report",),
    )

    with pytest.raises(ValueError, match="identity"):
        replace(shadow, pilot_id="")
    with pytest.raises(ValueError, match="requires evidence"):
        replace(shadow, required_evidence_refs=())
    with pytest.raises(ValueError, match="production state"):
        replace(shadow, promotion_status="PAPER_APPROVED")
    with pytest.raises(ValueError, match="authorize execution"):
        replace(shadow, execution_allowed=True)
    with pytest.raises(ValueError, match="cannot contain blanks"):
        replace(shadow, blockers=("LIVE_ORDER_BLOCKED", " "))
    with pytest.raises(ValueError, match="must be unique"):
        replace(shadow, required_evidence_refs=("artifact:oos-report",) * 2)
