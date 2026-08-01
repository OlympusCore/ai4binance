from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity
from ai4binance.enterprise.dashboard import (
    DashboardMetric,
    ExecutiveDashboardSnapshot,
    build_minimum_dashboard_snapshot,
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
