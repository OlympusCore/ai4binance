import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4binance.governance import (
    DecisionGovernanceEngine,
    DgeGovernanceContext,
    DgeMarketAction,
    DgeTradeCandidate,
    evaluate_recovery_radar_with_dge,
    evaluate_shadow_without_blocker,
    persist_dge_evaluation_record,
    replay_dge_decision,
)
from ai4binance.governance import replay as replay_module
from ai4binance.governance.audit import dge_decision_log_path, dge_event_log_path
from ai4binance.portfolio.opportunity_recovery import (
    OpportunityRecoveryRadar,
    RecoveryCandidate,
    RecoveryLadderStage,
    RecoveryProposalKind,
)
from ai4binance.storage.destination_verification import DestinationVerificationError

NOW = datetime(2026, 8, 8, 15, 30, tzinfo=UTC)


@pytest.mark.parametrize("stale", [False, True])
def test_virtual_context_routes_only_current_bound_regime_and_mtf(stale: bool) -> None:
    from ai4binance.governance.adapters import _default_virtual_dge_context
    from tests.test_strategy_risk import (
        agent_result,
        approved_candidate,
        market_regime_result,
        snapshot,
    )

    current = snapshot()
    candidate = replace(
        approved_candidate(), evidence=("VIRTUAL_STRATEGY_ID:TREND_PULLBACK",)
    )
    regime = market_regime_result("STRONG_UPTREND", vote=1.0)
    mtf = replace(
        agent_result("multi_timeframe", 1.0),
        calculation_metadata={"alignment_status": "ALIGNED"},
    )
    if stale:
        regime = replace(regime, snapshot_id="previous-cycle")
        mtf = replace(mtf, snapshot_id="previous-cycle")
    context = _default_virtual_dge_context(
        current,
        SimpleNamespace(
            snapshot_id=current.snapshot_id,
            blockers=("OOS_DEPLOYMENT_MISSING",),
            agent_results={"market_regime": regime, "multi_timeframe": mtf},
        ),
        candidate,
        object(),
        risk_approved=True,
        portfolio_verified=True,
        quantity=Decimal("1"),
    )
    assert context.regime_compatible is (not stale)
    assert context.mtf_aligned is (not stale)
    assert context.oos_approved is False
    assert context.validation_approved is False
    assert context.negative_evidence_clear is True


def test_recovery_radar_candidates_are_governed_without_live_authority() -> None:
    records = evaluate_recovery_radar_with_dge(_radar())

    assert len(records) == 1
    record = records[0]
    assert record.source == "opportunity_recovery_radar"
    assert record.candidate.requested_action is DgeMarketAction.SELL
    assert record.decision.governed_action is DgeMarketAction.NO_TRADE
    assert "VAL.OOS_NOT_VALIDATED" in record.decision.hard_blockers
    assert record.decision.execution_allowed is False
    assert record.decision.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_dge_replay_matches_persisted_recovery_record(tmp_path: Path) -> None:
    record = evaluate_recovery_radar_with_dge(_radar())[0]

    persist_result = persist_dge_evaluation_record(tmp_path, record)
    replay = replay_dge_decision(tmp_path, record.decision.decision_id)
    event_log = dge_event_log_path(tmp_path)
    event_rows = [
        json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()
    ]
    decision_log = dge_decision_log_path(tmp_path)
    replay_rows = [
        json.loads(line)
        for line in decision_log.read_text(encoding="utf-8").splitlines()
    ]
    event_payload = event_rows[-1]
    replay_payload = replay_rows[-1]

    assert persist_result.decision_id == record.decision.decision_id
    assert event_payload["tamper_evident"] is True
    assert replay_payload["tamper_evident"] is True
    assert event_rows[0]["event_type"] == "LEGACY_AUDIT_ANCHOR"
    assert replay_rows[0]["event_type"] == "LEGACY_AUDIT_ANCHOR"
    assert event_payload["previous_record_sha256"] == event_rows[0]["record_sha256"]
    assert replay_payload["previous_record_sha256"] == replay_rows[0]["record_sha256"]
    assert replay.status == "MATCH"
    assert replay.mismatches == ()
    assert replay.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_dge_replay_reports_missing_record_as_non_reproducible(
    tmp_path: Path,
) -> None:
    replay = replay_dge_decision(tmp_path, "dge:missing")

    assert replay.status == "NON_REPRODUCIBLE"
    assert replay.blocker == "DGE_REPLAY_RECORD_NOT_FOUND"
    assert replay.execution_allowed is False


def test_dge_replay_rejects_tampered_persisted_record(tmp_path: Path) -> None:
    record = evaluate_recovery_radar_with_dge(_radar())[0]
    persist_dge_evaluation_record(tmp_path, record)

    replay_path = dge_decision_log_path(tmp_path)
    lines = replay_path.read_text(encoding="utf-8-sig").splitlines()
    payload = json.loads(lines[-1])
    payload["payload"]["decision"]["governance_status"] = "MANUAL_REVIEW"
    replay_path.write_text(
        "\n".join([*lines[:-1], json.dumps(payload, ensure_ascii=False)]) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        DestinationVerificationError,
        match="JSONL_AUDIT_TAMPER_EVIDENT_CHAIN_INVALID",
    ):
        replay_dge_decision(tmp_path, record.decision.decision_id)


def test_dge_replay_helpers_and_result_contracts_fail_closed() -> None:
    assert replay_module._mapping(object()) == {}
    assert replay_module._sequence("not-a-sequence") == ()
    assert replay_module._optional_decimal(None) is None

    with pytest.raises(ValueError, match="decision_id is required"):
        replay_dge_decision(Path("."), " ")
    with pytest.raises(ValueError, match="identity is required"):
        replay_module.DgeReplayResult("", "MATCH", ())
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replay_module.DgeReplayResult(
            "decision:1",
            "MATCH",
            (),
            execution_allowed=True,
        )


def test_shadow_without_blocker_records_counterfactual_safely() -> None:
    candidate = DgeTradeCandidate(
        candidate_id="candidate:shadow",
        symbol="HOTUSDT",
        market="SPOT",
        requested_action=DgeMarketAction.BUY,
        setup_name="support_reclaim",
        score=Decimal("80"),
        confidence=Decimal("0.80"),
        risk_reward=Decimal("2.4"),
        capital_source="CURRENT_CAPITAL_REVIEW",
    )
    context = DgeGovernanceContext(
        context_id="context:shadow",
        data_snapshot_id="snapshot:shadow",
        semantic_graph_id="graph:shadow",
        position_context_ref="position:shadow",
        wallet_verified=True,
        oos_approved=False,
        risk_approved=True,
        validation_approved=True,
        execution_feasible=True,
        human_approval_recorded=True,
        config_hash="test",
    )

    diff = evaluate_shadow_without_blocker(
        candidate,
        context,
        blocker="OOS_APPROVAL_MISSING",
        dge=DecisionGovernanceEngine(),
    )

    assert diff.would_change_decision is True
    assert "hard_blockers" in diff.changed_fields
    assert "VAL.OOS_NOT_VALIDATED" in diff.baseline_decision.hard_blockers
    assert "VAL.OOS_NOT_VALIDATED" not in diff.shadow_decision.hard_blockers
    assert diff.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def _radar() -> OpportunityRecoveryRadar:
    candidate = RecoveryCandidate(
        candidate_id="hot-inventory-rotation",
        symbol="HOTUSDT",
        proposal_kind=RecoveryProposalKind.INVENTORY_SELL_REBUY_REVIEW,
        ladder_stage=RecoveryLadderStage.TRADE_CANDIDATE,
        review_action="SELL_HIGH_REBUY_LOW_REVIEW",
        rationale="Range recovery review only.",
        source="test",
        timeframe="1h",
        setup_name="inventory_rotation_recovery",
        score=Decimal("72"),
        confidence=Decimal("0.62"),
        estimated_sell_price=Decimal("0.000390"),
        estimated_rebuy_price=Decimal("0.000312"),
        estimated_cycle_gain_ratio=Decimal("0.20"),
        blockers=(
            "OOS_APPROVAL_MISSING",
            "RISK_APPROVAL_MISSING",
            "LIVE_ORDER_BLOCKED",
        ),
        evidence_refs=("recovery:test",),
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
        blockers=("LIVE_ORDER_BLOCKED",),
        next_safe_actions=("RUN_VALIDATION_QUEUE",),
    )
