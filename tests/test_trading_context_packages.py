"""D3-D9 dependency, timing, economics and historical-definition safety contracts."""

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from ai4binance.agents.advanced import build_advanced_agent
from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.evidence_fusion import EvidenceFusionEngine
from ai4binance.domain import Action, CandidateStatus, PriceZone
from ai4binance.domain.research.virtual_runtime_attribution import TradeDecisionEvidence
from ai4binance.intelligence.contracts import ScenarioType
from ai4binance.intelligence.event_context import (
    EVENT_ADAPTER,
    EventObservation,
    bind_event_context,
    context_payload,
)
from ai4binance.intelligence.inventory import render_reference_manual
from ai4binance.intelligence.method_registry import (
    current_method_registry,
    restore_registry_snapshot,
)
from ai4binance.intelligence.plan import RiskRewardEngine, TradePlanEngine
from ai4binance.intelligence.trading import ScenarioEngine
from ai4binance.runtime_research_context import RuntimeResearchContextLoader
from ai4binance.schemas import AgentStatus
from ai4binance.validation.overfit import assess_method_ablations, paired_ablation_delta
from tests.test_agents import agent_result, eligibility_results, snapshot
from tests.test_structural_entries import structural_context
from tests.test_technical_agents import technical_snapshot
from tests.test_trading_intelligence import (
    _candidate,
    _costed_snapshot,
    _evidence_results,
)
from tests.test_trading_intelligence_diffplan import observation


def event() -> EventObservation:
    base = technical_snapshot()
    return EventObservation(
        observation_id="source:revision1",
        symbol=base.symbol,
        market_type="SPOT",
        source_refs=("https://example.test/original",),
        root_ids=("original:1",),
        published_at=base.created_at - timedelta(hours=2),
        first_seen_at=base.created_at - timedelta(hours=1),
        available_at=base.created_at,
        window_start=base.created_at - timedelta(hours=2),
        window_end=base.created_at,
        verification="VERIFIED",
        source_quality=0.8,
    )


def test_source_review_and_manual_are_deterministic_not_implementation_claims() -> None:
    registry = current_method_registry()
    assert len(registry.source_reviews) == 9
    assert all(
        rule.applicability and rule.tolerance_policy and rule.ambiguity
        for rule in registry.rules
    )
    manual = render_reference_manual(registry)
    assert manual == render_reference_manual(registry)
    assert "source_of_truth: false" in manual
    assert "CATALOG_ONLY" in manual
    assert "METHOD_LEVEL_OOS_NOT_VERIFIED" in manual
    assert all(method.method_id in manual for method in registry.methods)


def test_rejected_opposition_and_blockers_are_retained() -> None:
    registry = build_default_registry()
    results = eligibility_results(snapshot())
    results.update(
        trend=agent_result("trend", 90, 0.9),
        volume=replace(
            agent_result("volume", 20, 0.2),
            directional_vote=-0.8,
            counter_evidence=("SELLING_VOLUME",),
        ),
    )
    result = EvidenceFusionEngine(registry.get("confluence"), registry).fuse(
        snapshot(), results
    )
    assert result.evidence == ("trend",)
    assert "DIRECTIONAL_CONFLICT" in result.warnings
    assert result.calculation_metadata["opposing_agents"] == ("volume",)
    observations = result.calculation_metadata["observations"]
    assert isinstance(observations, tuple)
    discarded = observations[1]
    assert isinstance(discarded, Mapping)
    assert discarded["counter_evidence"] == ("SELLING_VOLUME",)
    assert result.calculation_metadata["independent_confluence_count"] == 0
    reversed_result = EvidenceFusionEngine(registry.get("confluence"), registry).fuse(
        snapshot(), dict(reversed(tuple(results.items())))
    )
    assert result == reversed_result


def test_fusion_foreign_snapshot_fails_closed() -> None:
    registry = build_default_registry()
    results = eligibility_results(snapshot())
    results["trend"] = replace(agent_result("trend", 90, 0.9), snapshot_id="foreign")
    result = EvidenceFusionEngine(registry.get("confluence"), registry).fuse(
        snapshot(), results
    )
    assert result.status is AgentStatus.BLOCKED
    assert result.blockers == ("EVIDENCE_IDENTITY_MISMATCH",)


@pytest.mark.parametrize(
    "change",
    [
        {"available_at": technical_snapshot().created_at + timedelta(seconds=1)},
        {"symbol": "FOREIGNUSDT"},
        {"market_type": "USD_M_FUTURES"},
        {
            "window_end": technical_snapshot().created_at - timedelta(days=2),
            "window_start": technical_snapshot().created_at - timedelta(days=3),
        },
    ],
)
def test_context_rejects_future_stale_and_foreign_rows(
    change: dict[str, object],
) -> None:
    raw = dict(context_payload((event(),))["observations"][0])
    raw.update(change)
    base = replace(technical_snapshot(), sentiment_snapshot={"observations": (raw,)})
    context = bind_event_context(base, "sentiment", required=True)
    assert context.status == "DATA_INVALID"
    assert context.blockers
    assert not context.observations


def test_missing_measurements_are_not_neutral_or_volume_estimates() -> None:
    base = replace(technical_snapshot(), sentiment_snapshot=context_payload((event(),)))
    context = bind_event_context(base, "sentiment")
    assert set(dict(context.measurement_status).values()) == {"NOT_MEASURED"}
    assert context.observations[0].polarity is None
    agent = build_advanced_agent(build_default_registry().get("sentiment"))
    assert agent is not None
    result = agent.analyze(base, {})
    assert result.status is AgentStatus.PARTIAL
    assert result.directional_vote == result.confidence == result.score == 0
    assert result.calculation_metadata["evidence_root_ids"] == ("original:1",)
    assert not result.hard_gate_eligible


def test_critical_event_veto_cannot_be_scored_away() -> None:
    base = _costed_snapshot()
    ordinary = ScenarioEngine().build(base, _evidence_results())
    assert ordinary.selected_scenario is not None
    base = replace(
        base,
        news_snapshot=context_payload((replace(event(), event_severity="CRITICAL"),)),
    )
    state = ScenarioEngine().build(base, _evidence_results())
    assert state.selected_scenario is None
    assert "NEWS_CRITICAL_EVENT_REVIEW_REQUIRED" in state.blockers
    bound = ScenarioEngine().bind_candidates((_candidate(),), state)
    assert bound[0].status is CandidateStatus.RESEARCH_ONLY
    assert not state.execution_allowed
    assert state.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_context_requirement_is_explicit_and_optional_absence_is_visible() -> None:
    base = _costed_snapshot()
    optional = ScenarioEngine().build(base, _evidence_results())
    assert optional.selected_scenario is not None
    assert "SENTIMENT_CONTEXT_UNAVAILABLE" in optional.warnings
    required = ScenarioEngine(required_event_channels=("sentiment",)).build(
        base, _evidence_results()
    )
    assert required.selected_scenario is None
    assert "SENTIMENT_CONTEXT_UNAVAILABLE" in required.blockers


@pytest.mark.parametrize("short", [False, True])
def test_target_ladder_and_partial_exit_use_signed_funding(short: bool) -> None:
    candidate = replace(
        _candidate(),
        market_type="USD_M_FUTURES",
        action=Action.SELL if short else Action.BUY,
        entry_zone=PriceZone(Decimal(100), Decimal(100)),
        stop_loss=Decimal(110 if short else 90),
        invalidation_level=Decimal(110 if short else 90),
        take_profit_levels=(
            Decimal(80 if short else 120),
            Decimal(70 if short else 130),
        ),
    )
    engine = RiskRewardEngine()
    funding = Decimal("-.002" if short else ".002")
    ladder = engine.target_ladder(candidate, Decimal(".001"), funding)
    assert ladder[0][0] == Decimal("20.1" if short else "19.7")
    assert ladder[1][1] > ladder[0][1]
    pnl = engine.conditional_partial_exit(
        candidate,
        fractions=(Decimal(".5"), Decimal(".5")),
        reached_targets=1,
        cost_ratio=Decimal(".001"),
        signed_funding_ratio=funding,
    )
    assert pnl == Decimal("5.1" if short else "4.7")
    with pytest.raises(ValueError, match="weights"):
        engine.conditional_partial_exit(
            candidate,
            fractions=(Decimal(".8"), Decimal(".8")),
            reached_targets=1,
            cost_ratio=Decimal(0),
        )


def test_structural_plan_records_economics_and_replay_definitions() -> None:
    base, results = structural_context()
    state = ScenarioEngine().build(base, results)
    proposals = TradePlanEngine().propose(base, state)
    assert proposals
    candidate = proposals[0]
    assert len(candidate.target_net_risk_rewards) == len(candidate.take_profit_levels)
    assert candidate.stop_alternatives[0][1] == candidate.stop_loss
    factors = json.loads(candidate.decision_evidence.factors_json)
    archived = restore_registry_snapshot(factors["method_registry"])
    assert archived == current_method_registry()
    assert candidate.expected_r is None
    damaged = deepcopy(factors)
    damaged["method_registry"]["definition"]["version"] = "99.0.0"
    with pytest.raises(ValueError, match="digest"):
        replace(candidate.decision_evidence, factors_json=json.dumps(damaged))
    changed_current = archived.model_copy(update={"version": "99.0.0"})
    assert (
        restore_registry_snapshot(factors["method_registry"]).version
        != changed_current.version
    )
    assert TradeDecisionEvidence.from_payload(None).status == "NOT_RECORDED"


def test_rebinding_does_not_backfill_an_existing_decision_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _costed_snapshot()
    state = ScenarioEngine().build(base, _evidence_results())
    assert state.selected_scenario is not None
    archived = TradeDecisionEvidence(
        status="RECONSTRUCTED_FROM_ARCHIVE",
        as_of=base.created_at,
        direction_method="ARCHIVED_METHOD",
        entry_method="ARCHIVED_ENTRY",
        factors_json='{"legacy_factor": 1}',
    )
    candidate = replace(_candidate(), decision_evidence=archived)

    def current_registry_unavailable() -> None:
        raise AssertionError("historical records cannot require the current registry")

    monkeypatch.setattr(
        "ai4binance.intelligence.plan.current_method_registry",
        current_registry_unavailable,
    )
    rebound = TradePlanEngine().bind(candidate, state.selected_scenario, state)
    assert rebound.decision_evidence == archived
    assert "method_registry" not in json.loads(rebound.decision_evidence.factors_json)


@pytest.mark.parametrize("invalid", [True, 0.5, float("nan"), "1"])
def test_plan_counts_reject_noninteger_inputs(invalid: object) -> None:
    candidate = _candidate()
    with pytest.raises(ValueError, match="prefix"):
        RiskRewardEngine().conditional_partial_exit(
            candidate,
            fractions=tuple(
                Decimal(1) / len(candidate.take_profit_levels)
                for _ in candidate.take_profit_levels
            ),
            reached_targets=cast(int, invalid),
            cost_ratio=Decimal(0),
        )
    state = ScenarioEngine().build(_costed_snapshot(), _evidence_results())
    with pytest.raises(ValueError, match="period count"):
        replace(state, funding_periods=cast(int, invalid))


def test_ablation_requires_equal_costs_and_real_provenance() -> None:
    rows = tuple(observation(str(i), 0.7, True) for i in range(20))
    challenger = tuple(replace(row, model_id="sentiment") for row in rows)
    report = assess_method_ablations(
        rows,
        {"sentiment": challenger},
        minimum_observations=20,
        block_length=2,
        bootstrap_samples=99,
    )
    assert "ABLATION_DECISION_TIME_PROVENANCE_MISSING" in report.blockers
    assert report.multiple_comparison is None
    with pytest.raises(ValueError, match="costs"):
        paired_ablation_delta(
            rows, tuple(replace(row, cost_model_id="different") for row in challenger)
        )
    recorded = tuple(
        replace(
            row,
            cost_model_id="fixed-cost-v1",
            dataset_sha256="a" * 64,
            method_registry_sha256="b" * 64,
        )
        for row in rows
    )
    variants = {
        "sentiment": tuple(
            replace(row, model_id="sentiment", net_r=row.net_r + 0.1)
            for row in recorded
        ),
        "dependency": tuple(
            replace(row, model_id="dependency", net_r=row.net_r - 0.1)
            for row in recorded
        ),
    }
    report = assess_method_ablations(
        recorded,
        variants,
        minimum_observations=20,
        block_length=2,
        bootstrap_samples=99,
    )
    assert report.multiple_comparison is not None
    assert report.multiple_comparison.candidate_count == 2
    assert not report.multiple_comparison.promotion_allowed
    assert report == assess_method_ablations(
        recorded,
        variants,
        minimum_observations=20,
        block_length=2,
        bootstrap_samples=99,
    )


def test_event_schema_matches_typed_contract() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "schemas/evidence/event_context.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema.pop("$schema")
    schema.pop("$id")
    assert schema == EVENT_ADAPTER.json_schema()


@pytest.mark.parametrize("invalid", [{"observation_id": "invalid"}, "invalid-shape"])
def test_malformed_optional_context_cannot_hide_critical_risk(invalid: object) -> None:
    critical = context_payload((replace(event(), event_severity="CRITICAL"),))[
        "observations"
    ][0]
    base = replace(
        _costed_snapshot(), news_snapshot={"observations": (critical, invalid)}
    )
    state = ScenarioEngine().build(base, _evidence_results())
    assert state.selected_scenario is None
    assert "NEWS_CONTEXT_INVALID_OR_UNAVAILABLE_AT_DECISION" in state.blockers


def test_context_veto_cannot_be_removed_from_shared_state() -> None:
    base = replace(
        _costed_snapshot(),
        news_snapshot=context_payload((replace(event(), event_severity="CRITICAL"),)),
    )
    state = ScenarioEngine().build(base, _evidence_results())
    with pytest.raises(ValueError, match="vetoes"):
        replace(state, blockers=())


def test_context_requirements_are_scenario_specific() -> None:
    base = _costed_snapshot()
    required = ScenarioEngine(
        required_event_context_by_scenario=(
            (ScenarioType.LONG_CONTINUATION, ("news",)),
        )
    )
    assert required.build(base, _evidence_results()).selected_scenario is None
    unrelated = ScenarioEngine(
        required_event_context_by_scenario=(
            (ScenarioType.SHORT_CONTINUATION, ("news",)),
        )
    )
    assert unrelated.build(base, _evidence_results()).selected_scenario is not None


def test_local_feed_preserves_typed_decision_time_observations(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    row = context_payload((event(),))["observations"][0]
    path.write_text(json.dumps({"event_observation": row}) + "\n", encoding="utf-8")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    loader = RuntimeResearchContextLoader(path, path, empty)
    enriched = loader.attach(technical_snapshot())
    for channel in ("news", "sentiment"):
        bound = bind_event_context(enriched, channel, required=True)
        assert bound.status == "AVAILABLE"
        assert bound.observations[0] == event()
        assert not bound.blockers


def test_eief_adapter_retains_critical_impact_and_demands_complete_evidence() -> None:
    from ai4binance.external_intel.core.enums import DecisionImpact, RadarName
    from ai4binance.external_intel.integration.decision_governance_adapter import (
        to_event_observation,
    )
    from tests.test_external_intel_evidence import _evidence
    from tests.test_external_intel_fusion import _finding

    evidence = _evidence(
        "ev1",
        "https://example.test/original",
        "original",
        0.8,
        technical_snapshot().created_at,
    )
    finding = _finding(
        RadarName.SECURITY_RADAR,
        DecisionImpact.CRITICAL_RISK,
        symbol="HOTUSDT",
        observed_at=evidence.observed_at,
    )
    row = to_event_observation(
        finding,
        (evidence,),
        published_at=evidence.observed_at,
        first_seen_at=evidence.observed_at,
        root_ids=("origin:1",),
        market_type="SPOT",
    )
    assert row.event_severity == "CRITICAL"
    assert row.risk_review_required
    assert row.polarity is None
    assert row.root_ids == ("origin:1",)
    with pytest.raises(ValueError, match="every referenced"):
        to_event_observation(
            finding,
            (),
            published_at=evidence.observed_at,
            first_seen_at=evidence.observed_at,
            root_ids=("origin:1",),
            market_type="SPOT",
        )


def test_social_account_confidence_does_not_verify_content() -> None:
    from ai4binance.whale_fusion.social.context_adapter import to_event_observation
    from ai4binance.whale_fusion.social.engine import SocialIntelligenceEngine
    from tests.test_whale_fusion_social import NOW, post, registry

    classified = SocialIntelligenceEngine(registry()).evaluate(post(), as_of=NOW)
    assert classified.events
    social = classified.events[0]
    row = to_event_observation(
        social,
        symbol="HOTUSDT",
        asset=social.assets[0],
        market_type="SPOT",
        root_ids=(social.post_id,),
    )
    assert row.verification == "UNVERIFIED"
    assert row.volume is None
    assert row.source_refs


def test_dependency_roots_merge_transitively_across_different_clusters() -> None:
    registry = build_default_registry()
    results = eligibility_results(snapshot())
    results.update(
        {
            "order_flow": replace(
                agent_result("order_flow", 90, 0.9),
                calculation_metadata={"evidence_root_ids": ("a",)},
            ),
            "whale": replace(
                agent_result("whale", 80, 0.8),
                calculation_metadata={"evidence_root_ids": ("a", "b")},
            ),
            "trend": replace(
                agent_result("trend", 70, 0.7),
                calculation_metadata={"evidence_root_ids": ("b",)},
            ),
        }
    )
    result = EvidenceFusionEngine(registry.get("confluence"), registry).fuse(
        snapshot(), results
    )
    assert result.calculation_metadata["effective_dependency_group_count"] == 1
    assert result.evidence == ("order_flow",)
