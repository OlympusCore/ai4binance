from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from ai4binance.enterprise import GpuTelemetryAssessment
from ai4binance.ops.continuous_assurance import (
    AuditTriggerType,
    build_continuous_assurance_plan,
    events_from_performance_evidence_snapshot,
)
from ai4binance.ops.decision_telemetry import (
    AcceptanceGateStatus,
    AttributionMethod,
    BlockerEffectivenessRecord,
    BlockerOutcome,
    CanonicalTelemetrySnapshot,
    CounterfactualOutcome,
    CounterfactualType,
    DecisionEffectivenessClass,
    DecisionEffectivenessRecord,
    DecisionInputRecord,
    DecisionOutcomeRecord,
    DecisionProcessRecord,
    DecisionTelemetryFabricRecord,
    DecisionTelemetryLedger,
    DecisionTelemetryStatus,
    DgeEffectivenessMetrics,
    EvidenceQuality,
    ImprovementCandidate,
    LineageStatus,
    MarketType,
    MetricEvidence,
    OpportunityCostType,
    OutcomeAttribution,
    PerformanceAcceptanceResult,
    PerformanceEvidenceSnapshot,
    TelemetryDomain,
    build_performance_evidence_snapshot,
)

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def test_performance_evidence_snapshot_measures_no_trade_and_dge_effectiveness() -> (
    None
):
    snapshot = _snapshot()
    payload = snapshot.to_payload()

    assert snapshot.status is DecisionTelemetryStatus.READY
    assert snapshot.lineage.status is LineageStatus.COMPLETE
    assert payload["execution_allowed"] is False
    assert payload["promotion_status"] == "RESEARCH_ONLY"
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"

    outcome = payload["decision_outcome"]
    assert isinstance(outcome, dict)
    assert outcome["measurable_no_trade"] is True
    assert outcome["max_favorable_move_usdt"] == "42.50"
    assert outcome["max_adverse_move_usdt"] == "8.25"

    dge = payload["dge_effectiveness"]
    assert isinstance(dge, dict)
    assert dge["block_rate"] == "0.4000"
    assert dge["protective_block_rate"] == "0.3000"
    assert dge["false_block_rate"] == "0.1000"
    assert dge["net_protection_value_usdt"] == "85.00"


def test_snapshot_links_canonical_outcome_graph_for_audit_and_learning() -> None:
    snapshot = _rich_snapshot()
    payload = snapshot.to_payload()

    assert snapshot.status is DecisionTelemetryStatus.READY
    assert payload["lifecycle_state"] == "TELEMETRY_COMMITTED"
    assert len(cast(list[object], payload["counterfactuals"])) == 1
    assert len(cast(list[object], payload["outcome_attributions"])) == 1
    assert len(cast(list[object], payload["blocker_effectiveness"])) == 1
    assert len(cast(list[object], payload["decision_effectiveness"])) == 1
    acceptance_results = cast(
        list[dict[str, object]],
        payload["performance_acceptance"],
    )
    improvement_candidates = cast(
        list[dict[str, object]],
        payload["improvement_candidates"],
    )
    assert len(acceptance_results) == 1
    assert len(improvement_candidates) == 1

    telemetry = payload["canonical_telemetry"]
    assert isinstance(telemetry, dict)
    assert telemetry["market_type"] == "SPOT"
    assert set(telemetry["domains"]) >= {
        "DECISION_EFFECTIVENESS",
        "OPPORTUNITY_COST",
        "DGE_EFFECTIVENESS",
    }
    assert telemetry["gate_eligible"] is True

    acceptance = acceptance_results[0]
    assert acceptance["status"] == "PASS"
    assert acceptance["execution_allowed"] is False

    candidate = improvement_candidates[0]
    assert candidate["implementation_status"] == "NOT_AUTHORIZED"
    assert candidate["promotion_status"] == "RESEARCH_ONLY"
    assert candidate["risk_change_allowed"] is False


def test_snapshot_includes_gpu_telemetry_assessment_in_payload_and_report(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(gpu_telemetry_assessment=_gpu_assessment())
    payload = snapshot.to_payload()

    assessment = cast(dict[str, object], payload["gpu_telemetry_assessment"])
    assert assessment["source_label"] == "nvidia-smi"
    assert assessment["healthy"] is True
    assert assessment["blockers"] == []
    assert assessment["headroom_percent"] == 30

    ledger = DecisionTelemetryLedger(tmp_path, durable=False)
    ledger.append(snapshot)
    markdown = ledger.latest_markdown_path.read_text(encoding="utf-8")

    assert "## GPU Resource Governance" in markdown
    assert "nvidia-smi" in markdown
    assert "GPU assessment healthy" in markdown


def test_performance_snapshot_feeds_auto_audit_without_metric_recalculation() -> None:
    snapshot = _snapshot(
        counterfactuals=(_counterfactual(),),
        blocker_effectiveness=(
            replace(
                _blocker_effectiveness(),
                outcome_class=BlockerOutcome.FALSE_BLOCK,
                avoided_loss_usdt=Decimal("0"),
                foregone_profit_usdt=Decimal("12.50"),
            ),
        ),
        telemetry_snapshot=replace(
            _telemetry(),
            blockers=("OPPORTUNITY_COST_SPIKE",),
            gate_eligible=False,
        ),
        acceptance_results=(
            PerformanceAcceptanceResult(
                result_id="acceptance-spot-fail",
                market_type=MarketType.SPOT,
                gate_results={
                    "DATA_ACCEPTANCE": AcceptanceGateStatus.PASS,
                    "SYSTEM_ACCEPTANCE": AcceptanceGateStatus.PASS,
                    "LINEAGE_ACCEPTANCE": AcceptanceGateStatus.PASS,
                    "DECISION_ACCEPTANCE": AcceptanceGateStatus.FAIL,
                    "GOVERNANCE_ACCEPTANCE": AcceptanceGateStatus.PASS,
                    "RISK_ACCEPTANCE": AcceptanceGateStatus.PASS,
                    "ECONOMIC_ACCEPTANCE": AcceptanceGateStatus.FAIL,
                    "EVIDENCE_ACCEPTANCE": AcceptanceGateStatus.PASS,
                },
                evidence_refs=("telemetry:snapshot-1",),
            ),
        ),
        improvement_candidates=(_improvement_candidate(),),
    )

    events = events_from_performance_evidence_snapshot(snapshot)
    plan = build_continuous_assurance_plan(events)
    trigger_types = {event.trigger_type for event in events}
    domains = {
        domain
        for decision in plan.route_decisions
        for domain in cast(list[str], decision.to_payload()["domains"])
    }

    assert AuditTriggerType.DECISION_AUDIT in trigger_types
    assert AuditTriggerType.PERFORMANCE_DRIFT in trigger_types
    assert AuditTriggerType.FALSE_POSITIVE in trigger_types
    assert AuditTriggerType.AUTO_LEARN_OUTCOME in trigger_types
    assert "PERFORMANCE_ENGINEERING" in domains
    assert "AUTO_LEARN_GOVERNANCE" in domains
    assert "DGE_ASSURANCE" in domains
    assert plan.execution_allowed is False
    assert plan.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_lineage_gate_blocks_unmeasured_no_trade_outcomes() -> None:
    snapshot = _snapshot(
        outcome=replace(
            _outcome(),
            observation_window_minutes=None,
            max_favorable_move_usdt=None,
            max_adverse_move_usdt=None,
            counterfactual_return_usdt=None,
        )
    )

    assert snapshot.status is DecisionTelemetryStatus.BLOCKED
    assert snapshot.lineage.status is LineageStatus.BLOCKED
    assert "NO_TRADE_OUTCOME_WINDOW_MISSING" in snapshot.lineage.blockers
    assert "LINEAGE_INCOMPLETE" in snapshot.lineage.blockers
    assert "no_trade_outcome_measurement" in snapshot.lineage.missing_refs


def test_lineage_gate_requires_no_trade_rationale_blockers() -> None:
    snapshot = _snapshot(process=replace(_process(), blockers=()))

    assert snapshot.status is DecisionTelemetryStatus.BLOCKED
    assert "NO_TRADE_RATIONALE_MISSING" in snapshot.lineage.blockers
    assert "blockers" in snapshot.lineage.missing_refs


def test_telemetry_record_hashes_are_deterministic_and_payload_sensitive() -> None:
    first = DecisionTelemetryFabricRecord.seal(
        _snapshot(),
        previous_record_hash="GENESIS",
    )
    repeated = DecisionTelemetryFabricRecord.seal(
        _snapshot(),
        previous_record_hash="GENESIS",
    )
    changed = DecisionTelemetryFabricRecord.seal(
        _snapshot(
            outcome=replace(_outcome(), max_favorable_move_usdt=Decimal("51.00"))
        ),
        previous_record_hash="GENESIS",
    )

    assert first.payload_hash == repeated.payload_hash
    assert first.record_hash == repeated.record_hash
    assert changed.payload_hash != first.payload_hash
    assert changed.record_hash != first.record_hash


def test_telemetry_ledger_appends_hash_chain_and_latest_user_report(
    tmp_path: Path,
) -> None:
    ledger = DecisionTelemetryLedger(tmp_path, durable=False)
    first = ledger.append(_snapshot())
    second = ledger.append(
        _snapshot(
            decision_input=replace(
                _input(),
                snapshot_id="snapshot-2",
            ),
            outcome=replace(_outcome(), outcome_id="outcome-2"),
        )
    )

    lines = ledger.ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first_event = json.loads(lines[0])
    second_event = json.loads(lines[1])

    assert first.record.previous_record_hash == "GENESIS"
    assert second.record.previous_record_hash == first.record.record_hash
    assert first_event["event_type"] == "DECISION_TELEMETRY_EVIDENCE"
    assert second_event["payload"]["record_hash"] == second.record.record_hash
    assert ledger.ledger_path == (
        tmp_path
        / "runtime"
        / "state"
        / "decision_telemetry"
        / "decision-telemetry.jsonl"
    )
    assert ledger.latest_json_path == (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "audit"
        / "performance_evidence_latest.json"
    )
    assert ledger.latest_markdown_path == (
        tmp_path / "runtime" / "reports" / "audit" / "performance_evidence_latest.md"
    )
    assert ledger.verify_integrity() == second.record.record_hash

    latest = json.loads(ledger.latest_json_path.read_text(encoding="utf-8"))
    assert latest["record_hash"] == second.record.record_hash
    markdown = ledger.latest_markdown_path.read_text(encoding="utf-8")
    assert "## ELI10" in markdown
    assert "## NO_TRADE Outcome Measurement" in markdown
    assert "LIVE_ORDER_BLOCKED" in markdown


def test_telemetry_contracts_reject_hidden_live_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(_process(), execution_allowed=True)

    with pytest.raises(ValueError, match="cannot authorize live trading"):
        replace(_outcome(), execution_status="LIVE_FILLED")

    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(_dge(), promotion_status="LIVE_APPROVED")


def test_counterfactual_attribution_and_learning_contracts_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(_counterfactual(), cannot_execute=False)

    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(_counterfactual(), hypothetical_decision_state="LIVE_BUY")

    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(_attribution(), confidence=Decimal("1.1"))

    with pytest.raises(ValueError, match="cannot authorize trading"):
        replace(_attribution(), promotion_status="LIVE_APPROVED")

    with pytest.raises(ValueError, match="cannot be acceptance eligible"):
        replace(_telemetry(), lineage_complete=False)

    with pytest.raises(ValueError, match="cannot be acceptance gates"):
        PerformanceAcceptanceResult(
            result_id="acceptance-enterprise",
            market_type=MarketType.ENTERPRISE_SUMMARY,
            gate_results={"enterprise": AcceptanceGateStatus.PASS},
            evidence_refs=("telemetry:snapshot-1",),
        )

    with pytest.raises(ValueError, match="cannot authorize changes"):
        replace(_improvement_candidate(), human_review_required=False)

    with pytest.raises(ValueError, match="cannot authorize changes"):
        replace(_improvement_candidate(), risk_change_allowed=True)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(_attribution(), market_type=cast(MarketType, "OPTIONS")),
        lambda: replace(
            _decision_effectiveness(),
            market_type=cast(MarketType, "OPTIONS"),
        ),
        lambda: replace(_telemetry(), market_type=cast(MarketType, "OPTIONS")),
        lambda: replace(_acceptance(), market_type=cast(MarketType, "OPTIONS")),
    ],
)
def test_telemetry_contracts_reject_unsupported_market_type(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(
        ValueError,
        match="market type must be SPOT, FUTURES, or ENTERPRISE_SUMMARY",
    ):
        factory()


def test_snapshot_rejects_inconsistent_outcome_graph_references() -> None:
    with pytest.raises(ValueError, match="counterfactual snapshot id"):
        _snapshot(counterfactuals=(replace(_counterfactual(), snapshot_id="other"),))

    with pytest.raises(ValueError, match="unknown counterfactual"):
        _snapshot(
            counterfactuals=(_counterfactual(),),
            blocker_effectiveness=(
                replace(_blocker_effectiveness(), counterfactual_id="missing"),
            ),
        )

    with pytest.raises(ValueError, match="unknown attribution"):
        _snapshot(
            counterfactuals=(_counterfactual(),),
            decision_effectiveness=(
                replace(
                    _decision_effectiveness(),
                    attribution_refs=("missing-attribution",),
                ),
            ),
        )

    with pytest.raises(ValueError, match="telemetry lineage state"):
        _snapshot(
            telemetry_snapshot=replace(
                _telemetry(),
                blockers=("LINEAGE_INCOMPLETE",),
                gate_eligible=False,
                lineage_complete=False,
            )
        )


def test_input_and_process_contracts_reject_incomplete_references() -> None:
    with pytest.raises(ValueError, match="snapshot id"):
        replace(_input(), snapshot_id="")

    with pytest.raises(ValueError, match="source data ids must be unique"):
        replace(_input(), source_data_ids=("duplicate", "duplicate"))

    with pytest.raises(ValueError, match="feature versions are required"):
        replace(_input(), feature_versions={})

    with pytest.raises(ValueError, match="policy versions cannot contain blank"):
        replace(_input(), policy_versions={"risk": ""})

    with pytest.raises(ValueError, match="advisory signal refs are required"):
        replace(_process(), advisory_signal_refs=())

    with pytest.raises(ValueError, match="blockers cannot contain blank"):
        replace(_process(), blockers=(" ",))


def test_outcome_contract_rejects_invalid_measurement_fields() -> None:
    with pytest.raises(ValueError, match="observation window"):
        replace(_outcome(), observation_window_minutes=0)

    with pytest.raises(ValueError, match="maximum adverse move"):
        replace(_outcome(), max_adverse_move_usdt=Decimal("NaN"))

    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_outcome(), observed_at=datetime(2026, 8, 23, 9, 0))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda metrics: replace(metrics, sample_size=0), "sample size"),
        (lambda metrics: replace(metrics, intervention_count=11), "intervention count"),
        (
            lambda metrics: replace(
                metrics,
                intervention_count=2,
                protective_block_count=2,
                false_block_count=1,
            ),
            "classified blocks",
        ),
        (
            lambda metrics: replace(metrics, loss_avoided_usdt=Decimal("Infinity")),
            "loss avoided",
        ),
        (
            lambda metrics: replace(metrics, computed_at=datetime(2026, 8, 23, 9, 0)),
            "timezone-aware",
        ),
    ],
)
def test_dge_metrics_reject_invalid_bounds(
    mutation: Callable[[DgeEffectivenessMetrics], DgeEffectivenessMetrics],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        mutation(_dge())


def test_performance_snapshot_rejects_identity_mismatch_and_authority() -> None:
    good = _snapshot()

    with pytest.raises(ValueError, match="snapshot id"):
        PerformanceEvidenceSnapshot(
            snapshot_id="different-snapshot",
            observed_at=NOW,
            decision_input=_input(),
            decision_process=_process(),
            decision_outcome=_outcome(),
            dge_metrics=_dge(),
            lineage=good.lineage,
        )

    with pytest.raises(ValueError, match="decision process and outcome ids"):
        build_performance_evidence_snapshot(
            decision_input=_input(),
            decision_process=_process(),
            decision_outcome=replace(_outcome(), decision_id="different-decision"),
            dge_metrics=_dge(),
            observed_at=NOW,
        )

    with pytest.raises(ValueError, match="performance evidence"):
        replace(good, execution_allowed=True)


def test_telemetry_ledger_treats_empty_file_as_genesis(
    tmp_path: Path,
) -> None:
    ledger = DecisionTelemetryLedger(tmp_path, durable=False)
    ledger.ledger_path.parent.mkdir(parents=True)
    ledger.ledger_path.write_text("", encoding="utf-8")

    first = ledger.append(_snapshot())
    assert first.record.previous_record_hash == "GENESIS"


def test_telemetry_ledger_blocks_malformed_or_tampered_history(
    tmp_path: Path,
) -> None:
    ledger = DecisionTelemetryLedger(tmp_path, durable=False)
    ledger.ledger_path.parent.mkdir(parents=True)
    ledger.ledger_path.write_text(
        json.dumps({"event_type": "DECISION_TELEMETRY_EVIDENCE", "payload": []}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="field payload must be an object"):
        ledger.append(_snapshot())

    ledger.ledger_path.unlink()
    ledger.append(_snapshot())
    tampered = json.loads(
        ledger.ledger_path.read_text(encoding="utf-8").splitlines()[0]
    )
    tampered["payload"]["record_hash"] = "tampered"
    ledger.ledger_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="record hash is invalid"):
        ledger.verify_integrity()


def _snapshot(
    *,
    decision_input: DecisionInputRecord | None = None,
    process: DecisionProcessRecord | None = None,
    outcome: DecisionOutcomeRecord | None = None,
    dge: DgeEffectivenessMetrics | None = None,
    counterfactuals: tuple[CounterfactualOutcome, ...] = (),
    attributions: tuple[OutcomeAttribution, ...] = (),
    blocker_effectiveness: tuple[BlockerEffectivenessRecord, ...] = (),
    decision_effectiveness: tuple[DecisionEffectivenessRecord, ...] = (),
    telemetry_snapshot: CanonicalTelemetrySnapshot | None = None,
    gpu_telemetry_assessment: GpuTelemetryAssessment | None = None,
    acceptance_results: tuple[PerformanceAcceptanceResult, ...] = (),
    improvement_candidates: tuple[ImprovementCandidate, ...] = (),
) -> PerformanceEvidenceSnapshot:
    selected_input = decision_input or _input()
    return build_performance_evidence_snapshot(
        decision_input=selected_input,
        decision_process=process or _process(),
        decision_outcome=outcome or _outcome(),
        dge_metrics=dge or _dge(),
        counterfactuals=counterfactuals,
        attributions=attributions,
        blocker_effectiveness=blocker_effectiveness,
        decision_effectiveness=decision_effectiveness,
        telemetry_snapshot=telemetry_snapshot,
        gpu_telemetry_assessment=gpu_telemetry_assessment,
        acceptance_results=acceptance_results,
        improvement_candidates=improvement_candidates,
        observed_at=NOW,
    )


def _rich_snapshot() -> PerformanceEvidenceSnapshot:
    return _snapshot(
        counterfactuals=(_counterfactual(),),
        attributions=(_attribution(),),
        blocker_effectiveness=(_blocker_effectiveness(),),
        decision_effectiveness=(_decision_effectiveness(),),
        telemetry_snapshot=_telemetry(),
        acceptance_results=(_acceptance(),),
        improvement_candidates=(_improvement_candidate(),),
    )


def _input() -> DecisionInputRecord:
    return DecisionInputRecord(
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        observed_at=NOW,
        source_data_ids=("binance:spot:BTCUSDT:1h:20260823",),
        feature_versions={"atr": "1.0.0", "rsi": "1.0.0"},
        evidence_ids=("evidence:market-snapshot:1",),
        policy_versions={"risk": "2026.08", "validation": "2026.08"},
    )


def _process() -> DecisionProcessRecord:
    return DecisionProcessRecord(
        decision_id="decision-1",
        risk_assessment_id="risk-1",
        validation_id="validation-1",
        governance_evidence_ids=("governance:dge:1",),
        advisory_signal_refs=("signal:btc:watch-only:1",),
        blockers=("DGE_PROTECTIVE_BLOCK",),
    )


def _outcome() -> DecisionOutcomeRecord:
    return DecisionOutcomeRecord(
        outcome_id="outcome-1",
        decision_id="decision-1",
        observed_at=NOW,
        observation_window_minutes=240,
        max_favorable_move_usdt=Decimal("42.50"),
        max_adverse_move_usdt=Decimal("8.25"),
        counterfactual_return_usdt=Decimal("34.25"),
        no_trade_reason="DGE protective block held the cycle in research-only mode.",
    )


def _dge() -> DgeEffectivenessMetrics:
    return DgeEffectivenessMetrics(
        sample_size=10,
        intervention_count=4,
        protective_block_count=3,
        false_block_count=1,
        loss_avoided_usdt=Decimal("120.00"),
        profit_missed_usdt=Decimal("35.00"),
        drawdown_without_dge_pct=Decimal("12.5"),
        drawdown_with_dge_pct=Decimal("7.0"),
        counterfactual_expectancy_delta_usdt=Decimal("8.50"),
        computed_at=NOW,
    )


def _counterfactual() -> CounterfactualOutcome:
    return CounterfactualOutcome(
        counterfactual_id="cf-no-dge-1",
        counterfactual_type=CounterfactualType.NO_DGE_INTERVENTION,
        originating_decision_id="decision-1",
        snapshot_id="snapshot-1",
        changed_dimension="DGE_INTERVENTION",
        changed_rule_id="DGE_PROTECTIVE_BLOCK",
        retained_safety_controls=(
            "RISK_LIMITS",
            "VALIDATION_GATES",
            "EXCHANGE_FEASIBILITY",
        ),
        hypothetical_decision_state="PAPER_ONLY",
        hypothetical_economic_outcome_usdt=Decimal("-18.50"),
        methodology="same snapshot and market path with only DGE intervention removed",
        assumptions=("fees and slippage use the governed paper model",),
        evidence_quality=EvidenceQuality.SUFFICIENT,
        confidence=Decimal("0.82"),
    )


def _attribution() -> OutcomeAttribution:
    return OutcomeAttribution(
        attribution_id="attrib-1",
        decision_id="decision-1",
        market_type=MarketType.SPOT,
        attribution_method=AttributionMethod.COUNTERFACTUAL_DELTA,
        opportunity_cost_type=OpportunityCostType.BLOCKER,
        evidence_quality=EvidenceQuality.SUFFICIENT,
        confidence=Decimal("0.80"),
        assumptions=("attribution is counterfactual evidence, not causal fact",),
        governance_effect_usdt=Decimal("18.50"),
        avoided_loss_usdt=Decimal("18.50"),
        foregone_profit_usdt=Decimal("0"),
        opportunity_cost_usdt=Decimal("0"),
    )


def _blocker_effectiveness() -> BlockerEffectivenessRecord:
    return BlockerEffectivenessRecord(
        blocker_id="DGE_PROTECTIVE_BLOCK",
        blocker_type="DGE",
        policy_id="dge.policy.research_only",
        decision_id="decision-1",
        outcome_class=BlockerOutcome.PROTECTIVE_BLOCK,
        evaluation_horizon_minutes=240,
        evidence_quality=EvidenceQuality.SUFFICIENT,
        counterfactual_id="cf-no-dge-1",
        avoided_loss_usdt=Decimal("18.50"),
        foregone_profit_usdt=Decimal("0"),
    )


def _decision_effectiveness() -> DecisionEffectivenessRecord:
    return DecisionEffectivenessRecord(
        decision_id="decision-1",
        market_type=MarketType.SPOT,
        effectiveness_class=DecisionEffectivenessClass.BLOCKED_AVOIDED_LOSS,
        evidence_quality=EvidenceQuality.SUFFICIENT,
        observation_window_minutes=240,
        counterfactual_refs=("cf-no-dge-1",),
        attribution_refs=("attrib-1",),
    )


def _telemetry() -> CanonicalTelemetrySnapshot:
    return CanonicalTelemetrySnapshot(
        telemetry_id="snapshot-1",
        observed_at=NOW,
        market_type=MarketType.SPOT,
        metrics=(
            MetricEvidence(
                metric_id="decision.false_block_rate",
                domain=TelemetryDomain.DECISION_EFFECTIVENESS,
                value=Decimal("0.1000"),
                unit="ratio",
                evidence_refs=("attrib-1",),
            ),
            MetricEvidence(
                metric_id="opportunity.foregone_profit_usdt",
                domain=TelemetryDomain.OPPORTUNITY_COST,
                value=Decimal("0"),
                unit="USDT",
                evidence_refs=("attrib-1",),
            ),
            MetricEvidence(
                metric_id="dge.net_protection_value_usdt",
                domain=TelemetryDomain.DGE_EFFECTIVENESS,
                value=Decimal("85.00"),
                unit="USDT",
                evidence_refs=("cf-no-dge-1",),
            ),
        ),
        lineage_complete=True,
        evidence_quality=EvidenceQuality.SUFFICIENT,
    )


def _gpu_assessment() -> GpuTelemetryAssessment:
    return GpuTelemetryAssessment(
        observed_at=NOW,
        source_label="nvidia-smi",
        cuda_available=True,
        device_name="NVIDIA GeForce RTX 4090",
        driver_version="555.85",
        total_vram_bytes=24_064_000_000,
        free_vram_bytes=18_048_000_000,
        gpu_utilization_pct=23,
        active_gpu_processes=1,
        headroom_percent=30,
        healthy=True,
        blockers=(),
    )


def _acceptance() -> PerformanceAcceptanceResult:
    return PerformanceAcceptanceResult(
        result_id="acceptance-spot-1",
        market_type=MarketType.SPOT,
        gate_results={
            "DATA_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "SYSTEM_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "LINEAGE_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "DECISION_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "GOVERNANCE_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "RISK_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "ECONOMIC_ACCEPTANCE": AcceptanceGateStatus.PASS,
            "EVIDENCE_ACCEPTANCE": AcceptanceGateStatus.PASS,
        },
        evidence_refs=("telemetry:snapshot-1",),
    )


def _improvement_candidate() -> ImprovementCandidate:
    return ImprovementCandidate(
        candidate_id="candidate-dge-low-vol-1",
        originating_findings=("finding:false-block-rate",),
        affected_component="DGE",
        affected_rule="DGE_PROTECTIVE_BLOCK",
        affected_markets=(MarketType.SPOT,),
        affected_regimes=("RANGE_LOW_VOL",),
        baseline_metrics=(
            MetricEvidence(
                metric_id="baseline.false_block_rate",
                domain=TelemetryDomain.BLOCKER_EFFECTIVENESS,
                value=Decimal("0.0800"),
                unit="ratio",
                evidence_refs=("baseline:window-1",),
            ),
        ),
        observed_metrics=(
            MetricEvidence(
                metric_id="observed.false_block_rate",
                domain=TelemetryDomain.BLOCKER_EFFECTIVENESS,
                value=Decimal("0.1000"),
                unit="ratio",
                evidence_refs=("telemetry:snapshot-1",),
            ),
        ),
        sample_size=10,
        evidence_quality=EvidenceQuality.PARTIAL,
        confidence=Decimal("0.62"),
        hypothesis="DGE low-volatility blocker behavior needs a governed experiment.",
        proposed_experiment="Run shadow replay before any parameter proposal.",
        opportunity_cost_delta_usdt=Decimal("0"),
    )
