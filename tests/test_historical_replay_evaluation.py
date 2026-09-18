"""Full-system historical replay evidence and publication tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.application.learning_loop import ControlledLearningLoop
from ai4binance.core.contracts.virtual_governance import VirtualGovernanceResult
from ai4binance.enterprise.ykb_report import (
    _historical_replay_evidence_context,
    _historical_replay_wallet_epoch_context,
    _virtual_runtime_dge_effectiveness_context,
    _virtual_runtime_market_acceptance_context,
)
from ai4binance.historical_replay_evaluation import (
    HistoricalDgeCounterfactualOutcome,
    HistoricalReplayMetric,
    HistoricalReplaySystemEvaluator,
)
from ai4binance.historical_replay_state import (
    VIRTUAL_WALLET_RESET_CONFIRMATION,
    HistoricalReplayResetCapital,
    HistoricalReplayStateStore,
)
from ai4binance.learning import ControlledLearningEngine, LearningStore
from ai4binance.ops import DgeEffectivenessStatus
from ai4binance.research import VirtualMarket
from ai4binance.research_runtime import HistoricalReplayRunResult
from tests.test_historical_replay_runner import (
    END,
    HASH_1,
    START,
    _dual_market_request,
    _NoCandidateOrchestrator,
    _Orchestrator,
    _request,
    _runner,
    _snapshot,
)


class _DgeBlockedGovernance:
    def evaluate(self, **kwargs: object) -> VirtualGovernanceResult:
        snapshot = cast(Any, kwargs["snapshot"])
        return VirtualGovernanceResult(
            decision_id=f"dge:{snapshot.snapshot_id}",
            status="DGE_DATA_UNAVAILABLE",
            blockers=("DGE_DATA_UNAVAILABLE",),
            simulation_allowed=False,
        )


def _dual_no_trade_result() -> HistoricalReplayRunResult:
    return _runner(orchestrator=_NoCandidateOrchestrator()).run(
        _dual_market_request(),
        (
            _snapshot(
                START,
                snapshot_id="snapshot-evaluation-spot-start",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                START,
                snapshot_id="snapshot-evaluation-futures-start",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
            _snapshot(
                END,
                snapshot_id="snapshot-evaluation-spot-end",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                END,
                snapshot_id="snapshot-evaluation-futures-end",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=True,
            ),
        ),
    )


def _dual_dge_blocked_result(
    *,
    futures_execution_context: bool = True,
) -> HistoricalReplayRunResult:
    return _runner(
        orchestrator=_Orchestrator(),
        virtual_governance_evaluator=_DgeBlockedGovernance(),
    ).run(
        _dual_market_request(),
        (
            _snapshot(
                START,
                snapshot_id="snapshot-dge-shadow-spot",
                market=VirtualMarket.SPOT,
                execution_context=True,
            ),
            _snapshot(
                START,
                snapshot_id="snapshot-dge-shadow-futures",
                market=VirtualMarket.USD_M_FUTURES,
                execution_context=futures_execution_context,
            ),
        ),
    )


def _counterfactuals(
    result: HistoricalReplayRunResult,
) -> tuple[HistoricalDgeCounterfactualOutcome, ...]:
    return (
        HistoricalDgeCounterfactualOutcome(
            decision_id="dge:snapshot-dge-shadow-spot",
            market=VirtualMarket.SPOT,
            rule_id="DGE_DATA_UNAVAILABLE",
            outcome_observed_at=START,
            net_pnl_usdt=Decimal("-12"),
            execution_model_sha256=HASH_1,
            replay_state_sha256=result.semantic_result_sha256,
            evidence_refs=("shadow:spot:loss",),
        ),
        HistoricalDgeCounterfactualOutcome(
            decision_id="dge:snapshot-dge-shadow-futures",
            market=VirtualMarket.USD_M_FUTURES,
            rule_id="DGE_DATA_UNAVAILABLE",
            outcome_observed_at=START,
            net_pnl_usdt=Decimal("8"),
            execution_model_sha256=HASH_1,
            replay_state_sha256=result.semantic_result_sha256,
            evidence_refs=("shadow:futures:profit",),
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"metric_id": " "}, "metric identity is required"),
        ({"value": None}, "support must match value availability"),
        ({"value": None, "supported": False}, ""),
        ({"value": Decimal("NaN")}, "value must be finite"),
        ({"value": -1}, "cannot be negative"),
    ],
)
def test_historical_replay_metric_contract_is_fail_closed(
    overrides: dict[str, object],
    message: str,
) -> None:
    metric = HistoricalReplayMetric("trade_count", 1, "count")
    if message:
        with pytest.raises(ValueError, match=message):
            cast(Any, replace)(metric, **overrides)
    else:
        candidate = cast(Any, replace)(metric, **overrides)
        assert candidate.supported is False
        assert candidate.to_payload()["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"decision_id": " "}, "decision and rule ids are required"),
        ({"rule_id": "DGE_SIMULATION_NOT_APPROVED"}, "not an ablatable rule"),
        ({"outcome_observed_at": datetime(2026, 1, 1)}, "canonical UTC"),
        ({"net_pnl_usdt": Decimal("NaN")}, "PnL must be finite"),
        ({"execution_model_sha256": "BAD"}, "execution model SHA-256 is invalid"),
        ({"replay_state_sha256": "BAD"}, "replay state SHA-256 is invalid"),
        ({"evidence_refs": (" ",)}, "must be non-empty"),
        ({"evidence_refs": ("same", "same")}, "must be unique"),
        ({"higher_authority_vetoes_retained": False}, "stay research only"),
        ({"execution_allowed": True}, "stay research only"),
        ({"promotion_status": "PROMOTED"}, "stay research only"),
    ],
)
def test_historical_dge_counterfactual_rejects_unsafe_states(
    overrides: dict[str, object],
    message: str,
) -> None:
    outcome = HistoricalDgeCounterfactualOutcome(
        decision_id="dge:decision:1",
        market=VirtualMarket.SPOT,
        rule_id="DGE_RULE_1",
        outcome_observed_at=START,
        net_pnl_usdt=Decimal("1"),
        execution_model_sha256=HASH_1,
        replay_state_sha256=HASH_1,
        evidence_refs=("evidence:1",),
    )
    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(outcome, **overrides)


def test_evaluator_keeps_market_performance_and_acceptance_independent() -> None:
    result = _dual_no_trade_result()

    evaluation = HistoricalReplaySystemEvaluator().evaluate(
        result,
        reproducibility_reference_sha256=result.semantic_result_sha256,
    )

    spot = evaluation.market(VirtualMarket.SPOT)
    futures = evaluation.market(VirtualMarket.USD_M_FUTURES)
    assert spot.performance.portfolio_performance.market == "SPOT"
    assert futures.performance.portfolio_performance.market == "USD_M_FUTURES"
    assert spot.performance.attribution_ledger.closed_trades == ()
    assert futures.performance.attribution_ledger.closed_trades == ()
    assert "WALK_FORWARD_EVIDENCE_MISSING" in spot.blockers
    assert "ROBUSTNESS_EVIDENCE_MISSING" in futures.blockers
    assert "EXECUTION_MODEL_EVIDENCE_MISSING" not in spot.blockers
    assert spot.acceptance is spot.adapter.market_acceptance_result
    assert evaluation.system_acceptance is not None
    assert evaluation.system_acceptance.status.value == "DATA_UNAVAILABLE"
    assert evaluation.execution_allowed is False
    assert evaluation.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    common = {metric.metric_id: metric for metric in spot.performance.common_kpis}
    assert common["initial_equity"].value == Decimal("1000")
    assert common["sharpe"].supported is False
    assert common["spread_cost"].to_payload()["status"] == "INSUFFICIENT_DATA"


def test_evaluator_measures_dge_effectiveness_per_market_and_rule(
    tmp_path: Path,
) -> None:
    result = _dual_dge_blocked_result()
    evaluator = HistoricalReplaySystemEvaluator()

    first = evaluator.evaluate(
        result,
        dge_counterfactuals=_counterfactuals(result),
        reproducibility_reference_sha256=result.semantic_result_sha256,
    )
    second = evaluator.evaluate(
        result,
        dge_counterfactuals=_counterfactuals(result),
        reproducibility_reference_sha256=result.semantic_result_sha256,
    )

    assert first.to_payload() == second.to_payload()
    spot = first.market(VirtualMarket.SPOT).dge_metrics
    futures = first.market(VirtualMarket.USD_M_FUTURES).dge_metrics
    assert spot.status is DgeEffectivenessStatus.EFFECTIVE
    assert spot.loss_avoided_usdt == Decimal("12")
    assert spot.net_protection_value_usdt == Decimal("12")
    assert spot.counterfactual_coverage == Decimal("1.0000")
    assert spot.rule_metrics[0].status is DgeEffectivenessStatus.EFFECTIVE
    assert futures.status is DgeEffectivenessStatus.INEFFECTIVE
    assert futures.profit_missed_usdt == Decimal("8")
    assert futures.net_protection_value_usdt == Decimal("-8")
    assert futures.rule_metrics[0].status is DgeEffectivenessStatus.INEFFECTIVE
    assert first.system_acceptance is not None
    assert first.system_acceptance.execution_allowed is False

    evaluator.persist_and_publish(
        first,
        root=tmp_path,
        stamp="20260101T010000Z",
    )
    context = _virtual_runtime_dge_effectiveness_context(tmp_path)
    assert "SPOT:status=`EFFECTIVE`" in context
    assert "top_useful_rules=`DGE_DATA_UNAVAILABLE`" in context
    assert "USD_M_FUTURES:status=`INEFFECTIVE`" in context
    assert "top_harmful_or_review_rules=`DGE_DATA_UNAVAILABLE`" in context


def test_dge_counterfactual_cannot_bypass_validation_or_model_binding() -> None:
    result = _dual_dge_blocked_result(futures_execution_context=False)
    outcomes = _counterfactuals(result)

    with pytest.raises(
        ValueError,
        match="DGE_SHADOW_CANNOT_BYPASS_HIGHER_AUTHORITY_VETO",
    ):
        HistoricalReplaySystemEvaluator().evaluate(
            result,
            dge_counterfactuals=outcomes,
            reproducibility_reference_sha256=result.semantic_result_sha256,
        )
    with pytest.raises(ValueError, match="execution model mismatch"):
        HistoricalReplaySystemEvaluator().evaluate(
            _dual_dge_blocked_result(),
            dge_counterfactuals=(
                HistoricalDgeCounterfactualOutcome(
                    decision_id=outcomes[0].decision_id,
                    market=outcomes[0].market,
                    rule_id=outcomes[0].rule_id,
                    outcome_observed_at=outcomes[0].outcome_observed_at,
                    net_pnl_usdt=outcomes[0].net_pnl_usdt,
                    execution_model_sha256="a" * 64,
                    replay_state_sha256=outcomes[0].replay_state_sha256,
                    evidence_refs=outcomes[0].evidence_refs,
                ),
            ),
            reproducibility_reference_sha256=result.semantic_result_sha256,
        )


def test_evaluator_persists_publishes_and_feeds_controlled_learning(
    tmp_path: Path,
) -> None:
    result = _dual_no_trade_result()
    learning_loop = ControlledLearningLoop(
        LearningStore(
            summary_path=tmp_path / "runtime" / "learning" / "summary.json",
            audit_path=tmp_path / "runtime" / "learning" / "audit.jsonl",
        ),
        ControlledLearningEngine(),
    )
    evaluator = HistoricalReplaySystemEvaluator()
    evaluation = evaluator.evaluate(
        result,
        reproducibility_reference_sha256=result.semantic_result_sha256,
        learning_loop=learning_loop,
    )

    publication = evaluator.persist_and_publish(
        evaluation,
        root=tmp_path,
        stamp="20260101T020000Z",
    )
    repeated = evaluator.persist_and_publish(
        evaluation,
        root=tmp_path,
        stamp="20260101T020001Z",
    )

    assert evaluation.learning_result is not None
    assert evaluation.learning_result.execution_allowed is False
    assert publication.state_persisted is True
    assert repeated.state_persisted is False
    assert publication.state_path.exists()
    report_dir = (
        tmp_path / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    )
    assert (report_dir / "virtual_research_spot_evidence_latest.json").exists()
    assert (report_dir / "virtual_research_usd_m_futures_evidence_latest.json").exists()
    assert publication.system_acceptance_paths is not None
    assert publication.system_acceptance_paths.latest_json_path.exists()
    assert publication.system_evaluation_paths.latest_json_path.exists()
    acceptance_context = _virtual_runtime_market_acceptance_context(tmp_path)
    dge_context = _virtual_runtime_dge_effectiveness_context(tmp_path)
    replay_context = _historical_replay_evidence_context(tmp_path)
    epoch_context = _historical_replay_wallet_epoch_context(tmp_path)
    assert "spot_acceptance_status=`DATA_UNAVAILABLE`" in acceptance_context
    assert "futures_acceptance_status=`DATA_UNAVAILABLE`" in acceptance_context
    assert "SPOT:status=`NOT_EVALUABLE`" in dge_context
    assert "USD_M_FUTURES:status=`NOT_EVALUABLE`" in dge_context
    assert "HISTORICAL_REPLAY=`AVAILABLE`" in replay_context
    assert "SPOT:initial=`1000`" in replay_context
    assert "USD_M_FUTURES:initial=`1000`" in replay_context
    assert "FORWARD_VIRTUAL=`UNAVAILABLE`" in replay_context
    assert "CURRENT_WALLET_EPOCH=SPOT:epoch_id=" in epoch_context
    assert "PREVIOUS_EPOCH_SUMMARY=`UNAVAILABLE:NO_RESET`" in epoch_context
    assert publication.execution_allowed is False
    assert publication.live_eligibility_status == "LIVE_ORDER_BLOCKED"

    reset = HistoricalReplayStateStore.for_run(
        tmp_path,
        result.request.run_id,
    ).reset_wallet_epochs(
        result,
        reset_at=END + timedelta(minutes=1),
        capitals=(
            HistoricalReplayResetCapital(VirtualMarket.SPOT, Decimal("500")),
            HistoricalReplayResetCapital(
                VirtualMarket.USD_M_FUTURES,
                Decimal("250"),
            ),
        ),
        confirmation=VIRTUAL_WALLET_RESET_CONFIRMATION,
    )
    reset_context = _historical_replay_wallet_epoch_context(tmp_path)
    assert reset.status == "RESET_COMPLETED"
    assert reset.new_epochs[0].epoch_id in reset_context
    assert reset.new_epochs[1].epoch_id in reset_context
    assert "PREVIOUS_EPOCH_SUMMARY=SPOT:ending_equity=`1000`" in reset_context
    assert "LIFETIME_VIRTUAL_HISTORY=`2 epochs per market`" in reset_context


def test_evaluator_requires_reproducibility_and_preserves_requested_market_scope() -> (
    None
):
    result = _dual_no_trade_result()

    evaluation = HistoricalReplaySystemEvaluator().evaluate(result)

    assert all(
        "DECISION_REPRODUCIBILITY_EVIDENCE_MISSING" in item.blockers
        for item in evaluation.markets
    )
    single_market = _runner(orchestrator=_NoCandidateOrchestrator()).run(
        _request(run_id="historical-single-market-evaluation"),
        (
            _snapshot(
                START,
                snapshot_id="snapshot-single-market-evaluation",
                execution_context=True,
            ),
        ),
    )
    single_evaluation = HistoricalReplaySystemEvaluator().evaluate(single_market)
    assert tuple(item.market for item in single_evaluation.markets) == (
        VirtualMarket.SPOT,
    )
    assert single_evaluation.system_acceptance is None
    assert single_evaluation.to_payload()["system_acceptance"] is None


def test_single_market_publication_does_not_fabricate_system_acceptance(
    tmp_path: Path,
) -> None:
    result = _runner(orchestrator=_NoCandidateOrchestrator()).run(
        _request(run_id="historical-single-market-publication"),
        (
            _snapshot(
                START,
                snapshot_id="snapshot-single-market-publication",
                execution_context=True,
            ),
        ),
    )
    evaluator = HistoricalReplaySystemEvaluator()
    evaluation = evaluator.evaluate(
        result,
        reproducibility_reference_sha256=result.semantic_result_sha256,
    )

    publication = evaluator.persist_and_publish(
        evaluation,
        root=tmp_path,
        stamp="20260101T030000Z",
    )

    assert publication.system_acceptance_paths is None
    assert publication.system_evaluation_paths.latest_json_path.exists()
    assert not (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_system_acceptance"
        / "virtual_system_acceptance_latest.json"
    ).exists()


def test_counterfactual_timestamp_must_stay_within_replay() -> None:
    result = _dual_dge_blocked_result()
    late = _counterfactuals(result)[0]
    late = HistoricalDgeCounterfactualOutcome(
        decision_id=late.decision_id,
        market=late.market,
        rule_id=late.rule_id,
        outcome_observed_at=END + timedelta(seconds=1),
        net_pnl_usdt=late.net_pnl_usdt,
        execution_model_sha256=late.execution_model_sha256,
        replay_state_sha256=late.replay_state_sha256,
        evidence_refs=late.evidence_refs,
    )

    with pytest.raises(ValueError, match="outside replay time"):
        HistoricalReplaySystemEvaluator().evaluate(
            result,
            dge_counterfactuals=(late,),
            reproducibility_reference_sha256=result.semantic_result_sha256,
        )
