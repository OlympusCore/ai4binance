from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.portfolio.opportunity_recovery import (
    OpportunityRecoveryRadar,
    RecoveryCandidate,
    RecoveryLadderStage,
    RecoveryProposalKind,
)
from ai4binance.validation.recovery_queue import (
    RecoveryValidationWorkItem,
    build_recovery_validation_queue,
)


def test_recovery_validation_queue_maps_ladder_to_research_work_items(
    tmp_path: Path,
) -> None:
    radar = _radar()

    queue = build_recovery_validation_queue(radar, artifact_root=tmp_path)
    payload = queue.to_payload()

    assert queue.queue_id == "recovery-validation:HOTUSDT"
    assert queue.status == "QUEUED_WITH_BLOCKERS"
    assert queue.execution_allowed is False
    assert queue.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "OOS_APPROVAL_MISSING" in queue.blockers
    assert "RISK_APPROVAL_MISSING" in queue.blockers
    assert "LIVE_ORDER_BLOCKED" in queue.blockers

    item = queue.items[0]
    assert item.work_id == "recovery-validation:recovery:HOTUSDT:test"
    assert item.priority == "P0"
    assert item.required_artifacts == (
        "runtime/artifacts/research/backtest/validation/HOTUSDT/1h/support_reclaim.jsonl",
        "runtime/artifacts/research/backtest/walk_forward/HOTUSDT/1h/support_reclaim.json",
        "runtime/artifacts/research/backtest/oos/HOTUSDT/1h/support_reclaim.json",
        "runtime/artifacts/research/backtest/robustness/HOTUSDT/1h/support_reclaim.json",
    )
    assert item.execution_allowed is False
    assert item.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_recovery_validation_queue_rejects_invalid_authority_or_limits() -> None:
    with pytest.raises(ValueError, match="max_items"):
        build_recovery_validation_queue(_radar(), max_items=0)

    kwargs = {
        "work_id": "work-1",
        "candidate_id": "candidate-1",
        "symbol": "HOTUSDT",
        "setup_name": "support_reclaim",
        "timeframe": "1h",
        "required_artifacts": ("a.json",),
        "blockers": ("LIVE_ORDER_BLOCKED",),
        "execution_allowed": True,
    }
    with pytest.raises(ValueError, match="cannot authorize"):
        RecoveryValidationWorkItem(**cast(Any, kwargs))


def _radar() -> OpportunityRecoveryRadar:
    candidate = RecoveryCandidate(
        candidate_id="recovery:HOTUSDT:test",
        symbol="HOTUSDT",
        proposal_kind=RecoveryProposalKind.VALIDATION_OPPORTUNITY_REVIEW,
        ladder_stage=RecoveryLadderStage.TRADE_CANDIDATE,
        review_action="COMPLETE_OOS_BEFORE_ACTION",
        rationale="Visible candidate requires validation before any action.",
        source="unit-test",
        timeframe="1h",
        setup_name="support_reclaim",
        score=Decimal("72"),
        confidence=Decimal("0.61"),
        opportunity_grade="B_REVIEW",
        blockers=("OOS_APPROVAL_MISSING", "LIVE_ORDER_BLOCKED"),
        next_safe_actions=("RUN_VALIDATION_QUEUE",),
        evidence_refs=("market_outlook:test",),
        validation_queue_ref="recovery-validation:recovery:HOTUSDT:test",
        oos_evidence_status="QUEUED_RESEARCH_ONLY",
    )
    return OpportunityRecoveryRadar(
        symbol="HOTUSDT",
        inventory_units=Decimal("18400000"),
        range_low=Decimal("0.000312"),
        range_high=Decimal("0.000390"),
        range_source="OPERATOR_RANGE",
        range_move_ratio=Decimal("0.25"),
        ideal_full_cycle_end_units=Decimal("23000000"),
        ideal_full_cycle_unit_gain=Decimal("4600000"),
        ladder=(candidate,),
        blockers=("OOS_APPROVAL_MISSING", "LIVE_ORDER_BLOCKED"),
        next_safe_actions=("RUN_VALIDATION_QUEUE",),
    )
