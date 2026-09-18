"""Canonical cycle completion receipt contract tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from ai4binance.application.orchestration import (
    CanonicalCycleEnvelope as ApplicationCanonicalCycleEnvelope,
)
from ai4binance.application.orchestration.canonical_cycle import (
    MAX_BOUNDED_OBSERVATIONS,
    CanonicalCycleEnvelope,
    CanonicalCycleStep,
    CycleArtifactKind,
    CycleArtifactRef,
    CycleExecutionSurface,
    CycleGovernanceStatus,
)
from ai4binance.domain.research.canonical_cycle import (
    CanonicalCycleEnvelope as DomainCanonicalCycleEnvelope,
)

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def test_application_facade_preserves_canonical_cycle_identity() -> None:
    assert ApplicationCanonicalCycleEnvelope is DomainCanonicalCycleEnvelope
    assert CanonicalCycleEnvelope is DomainCanonicalCycleEnvelope


def artifact(
    artifact_id: str,
    artifact_kind: CycleArtifactKind,
    *,
    cycle_id: str = "cycle-1",
    snapshot_id: str = "snapshot-1",
) -> CycleArtifactRef:
    return CycleArtifactRef(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        cycle_id=cycle_id,
        snapshot_id=snapshot_id,
        payload_sha256=hashlib.sha256(artifact_id.encode()).hexdigest(),
    )


def envelope(**overrides: object) -> CanonicalCycleEnvelope:
    values: dict[str, object] = {
        "cycle_id": "cycle-1",
        "snapshot_id": "snapshot-1",
        "created_at": NOW,
        "execution_surface": CycleExecutionSurface.VIRTUAL_MARKET,
        "governance_status": CycleGovernanceStatus.NO_TRADE,
        "canonical_snapshot": artifact(
            "snapshot-artifact-1",
            CycleArtifactKind.CANONICAL_SNAPSHOT,
        ),
        "shared_state": artifact("state-1", CycleArtifactKind.SHARED_STATE),
        "observations": (
            artifact("observation-1", CycleArtifactKind.OBSERVATION),
            artifact("observation-2", CycleArtifactKind.OBSERVATION),
        ),
        "decision": artifact("decision-1", CycleArtifactKind.DECISION),
        "risk_assessment": artifact("risk-1", CycleArtifactKind.RISK_ASSESSMENT),
        "governance_result": artifact(
            "governance-1", CycleArtifactKind.GOVERNANCE_RESULT
        ),
        "execution_plan": None,
        "audit_trail": artifact("audit-1", CycleArtifactKind.AUDIT_TRAIL),
        "blockers": ("NO_TRADE",),
    }
    values.update(overrides)
    return CanonicalCycleEnvelope(**values)  # type: ignore[arg-type]


def test_no_trade_cycle_binds_all_steps_and_hashes_deterministically() -> None:
    result = envelope()

    assert result.completed_steps == tuple(CanonicalCycleStep)
    assert result.execution_plan is None
    assert result.semantic_sha256 == envelope().semantic_sha256
    assert result.to_payload()["semantic_sha256"] == result.semantic_sha256
    assert result.to_payload()["execution_allowed"] is False
    assert result.to_payload()["promotion_status"] == "RESEARCH_ONLY"
    assert result.to_payload()["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("surface", "kind"),
    [
        (
            CycleExecutionSurface.VIRTUAL_MARKET,
            CycleArtifactKind.VIRTUAL_SIMULATION_PLAN,
        ),
        (CycleExecutionSurface.BINANCE_MARKET, CycleArtifactKind.BINANCE_MANUAL_PLAN),
    ],
)
def test_paper_approved_cycle_accepts_only_surface_bounded_plan(
    surface: CycleExecutionSurface,
    kind: CycleArtifactKind,
) -> None:
    result = envelope(
        execution_surface=surface,
        governance_status=CycleGovernanceStatus.APPROVED_PAPER_ONLY,
        execution_plan=artifact("plan-1", kind),
        blockers=(),
    )

    assert result.execution_plan is not None
    assert result.execution_plan.artifact_kind is kind
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "bad_ref",
    [
        artifact(
            "observation-wrong-cycle",
            CycleArtifactKind.OBSERVATION,
            cycle_id="cycle-2",
        ),
        artifact(
            "observation-wrong-snapshot",
            CycleArtifactKind.OBSERVATION,
            snapshot_id="snapshot-2",
        ),
    ],
)
def test_cycle_rejects_cross_cycle_observation_lineage(
    bad_ref: CycleArtifactRef,
) -> None:
    with pytest.raises(ValueError, match="must match"):
        envelope(observations=(bad_ref,))


def test_cycle_rejects_duplicate_or_unbounded_observations() -> None:
    duplicate = artifact("observation-1", CycleArtifactKind.OBSERVATION)
    with pytest.raises(ValueError, match="identities must be unique"):
        envelope(observations=(duplicate, duplicate))
    with pytest.raises(ValueError, match="non-empty and bounded"):
        envelope(observations=())
    with pytest.raises(ValueError, match="non-empty and bounded"):
        envelope(
            observations=tuple(
                artifact(f"observation-{index}", CycleArtifactKind.OBSERVATION)
                for index in range(MAX_BOUNDED_OBSERVATIONS + 1)
            )
        )


def test_cycle_rejects_role_kind_and_global_identity_collisions() -> None:
    with pytest.raises(ValueError, match="kind must match"):
        envelope(
            canonical_snapshot=artifact(
                "snapshot-artifact-1",
                CycleArtifactKind.SHARED_STATE,
            )
        )
    with pytest.raises(ValueError, match="kind must match"):
        envelope(decision=artifact("decision-1", CycleArtifactKind.SHARED_STATE))
    with pytest.raises(ValueError, match="artifact identities must be unique"):
        envelope(decision=artifact("state-1", CycleArtifactKind.DECISION))


def test_cycle_rejects_plan_without_paper_approval_or_wrong_surface_kind() -> None:
    with pytest.raises(ValueError, match="requires paper-only"):
        envelope(
            execution_plan=artifact("plan-1", CycleArtifactKind.VIRTUAL_SIMULATION_PLAN)
        )
    with pytest.raises(ValueError, match="bounded simulation"):
        envelope(
            governance_status=CycleGovernanceStatus.APPROVED_PAPER_ONLY,
            execution_plan=artifact("plan-1", CycleArtifactKind.BINANCE_MANUAL_PLAN),
            blockers=(),
        )
    with pytest.raises(ValueError, match="manual-only"):
        envelope(
            execution_surface=CycleExecutionSurface.BINANCE_MARKET,
            governance_status=CycleGovernanceStatus.APPROVED_PAPER_ONLY,
            execution_plan=artifact(
                "plan-1", CycleArtifactKind.VIRTUAL_SIMULATION_PLAN
            ),
            blockers=(),
        )


def test_cycle_rejects_unsafe_status_step_and_safety_drift() -> None:
    with pytest.raises(ValueError, match="cannot coexist with governance blockers"):
        envelope(
            governance_status=CycleGovernanceStatus.APPROVED_PAPER_ONLY,
            execution_plan=artifact(
                "plan-1", CycleArtifactKind.VIRTUAL_SIMULATION_PLAN
            ),
        )
    with pytest.raises(ValueError, match="step order is immutable"):
        envelope(completed_steps=tuple(reversed(tuple(CanonicalCycleStep))))
    with pytest.raises(ValueError, match="cannot grant live authority"):
        envelope(execution_allowed=True)


def test_cycle_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        envelope(created_at=datetime(2026, 9, 11))
    with pytest.raises(ValueError, match="cannot grant live authority"):
        envelope(promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="cannot grant live authority"):
        envelope(live_eligibility_status="LIVE_ORDER_ALLOWED")


def test_cycle_artifact_rejects_invalid_identity_hash_and_timestamp() -> None:
    with pytest.raises(ValueError, match="artifact_id is required"):
        replace(artifact("valid", CycleArtifactKind.OBSERVATION), artifact_id=" ")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(artifact("valid", CycleArtifactKind.OBSERVATION), payload_sha256="bad")
    with pytest.raises(ValueError, match="artifact kind is invalid"):
        cast(Any, replace)(
            artifact("valid", CycleArtifactKind.OBSERVATION),
            artifact_kind="INVALID",
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        envelope(created_at=datetime(2026, 9, 11))
    with pytest.raises(ValueError, match="must be UTC"):
        envelope(created_at=NOW.astimezone(timezone(timedelta(hours=3))))


def test_cycle_rejects_blank_or_duplicate_blockers() -> None:
    with pytest.raises(ValueError, match="cannot contain blanks"):
        envelope(blockers=("NO_TRADE", " "))
    with pytest.raises(ValueError, match="must be unique"):
        envelope(blockers=("NO_TRADE", "NO_TRADE"))


def test_cycle_rejects_invalid_surface_status_and_reference_type() -> None:
    with pytest.raises(ValueError, match="execution surface is invalid"):
        envelope(execution_surface="INVALID")
    with pytest.raises(ValueError, match="governance status is invalid"):
        envelope(governance_status="INVALID")
    with pytest.raises(ValueError, match="artifact reference is invalid"):
        envelope(decision=cast(Any, object()))
