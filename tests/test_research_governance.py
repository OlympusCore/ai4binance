"""Research run-card, hypothesis and decay lifecycle tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.research_governance import (
    DecayPolicy,
    HypothesisRegistry,
    HypothesisStatus,
    ResearchBlockerDashboardWriter,
    ResearchBlockerObservation,
    ResearchHypothesis,
    ResearchRunCard,
    ResearchRunCardWriter,
    StrategyDecayEvaluator,
    StrategyHealthSnapshot,
    build_research_blocker_dashboard,
)
from ai4binance.storage import JsonlAuditStore

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
DIGEST = sha256(b"evidence").hexdigest()


def hypothesis() -> ResearchHypothesis:
    return ResearchHypothesis(
        hypothesis_id="hyp:breakout-retest",
        title="Breakout retest continuation",
        thesis="Validated retests may improve OOS expectancy.",
        symbol="HOTUSDT",
        timeframe="1h",
        invalidation_conditions=(
            "OOS expectancy is non-positive",
            "Edge fails cost stress",
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def test_hypothesis_registry_records_explicit_forward_transitions(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "hypotheses.jsonl"
    registry = HypothesisRegistry(ledger=JsonlAuditStore(ledger_path)).add(hypothesis())
    research = registry.get("hyp:breakout-retest").transition(
        HypothesisStatus.RESEARCH,
        updated_at=NOW + timedelta(minutes=1),
        artifact_ids=("run:1",),
    )
    registry = registry.update(research)

    assert registry.get(research.hypothesis_id).artifact_ids == ("run:1",)
    events = [
        json.loads(line)["event_type"] for line in ledger_path.read_text().splitlines()
    ]
    assert events == ["HYPOTHESIS_CREATED", "HYPOTHESIS_TRANSITIONED"]

    with pytest.raises(ValueError, match="invalid hypothesis transition"):
        research.transition(HypothesisStatus.PAPER_APPROVED, updated_at=NOW)
    with pytest.raises(ValueError, match="already exists"):
        registry.add(research)
    with pytest.raises(KeyError):
        registry.get("missing")


def test_run_card_is_hash_linked_atomic_and_live_blocked(tmp_path: Path) -> None:
    card = ResearchRunCard(
        run_id="run:1",
        created_at=NOW,
        symbol="HOTUSDT",
        timeframe="1h",
        hypothesis_id="hyp:breakout-retest",
        dataset_sha256=DIGEST,
        config_sha256=ResearchRunCard.hash_json({"fee": 0.001}),
        strategy_sha256=DIGEST,
        code_revision="working-tree:2026-07-13",
        random_seed=42,
        fee_rate=0.001,
        slippage_rate=0.0005,
        metrics=(("net_return", 0.02), ("max_drawdown", 0.01)),
        artifact_sha256=(("walk-forward.json", DIGEST),),
        blockers=("MULTI_REGIME_EVIDENCE_INCOMPLETE",),
    )
    path = tmp_path / "run-card.json"
    ledger = JsonlAuditStore(tmp_path / "run-cards.jsonl")
    ResearchRunCardWriter(path, ledger).write(card)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["run_id"] == "run:1"
    assert stored["execution_allowed"] is False
    assert not path.with_suffix(".json.tmp").exists()
    assert "RESEARCH_RUN_CARD_WRITTEN" in ledger.path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="staged run card"):
        replace(card, promotion_status="STAGED_CANDIDATE")
    with pytest.raises(ValueError, match="hashes"):
        replace(card, dataset_sha256="bad")


def test_blocker_dashboard_groups_actions_and_remains_live_blocked(
    tmp_path: Path,
) -> None:
    dashboard = build_research_blocker_dashboard(
        dashboard_id="dashboard:HOTUSDT:validation",
        created_at=NOW,
        symbol="hotusdt",
        observations=(
            ResearchBlockerObservation(
                symbol="HOTUSDT",
                timeframe="1h",
                playbook="breakout_retest",
                blocker="COST_STRESS_RETURN_NOT_POSITIVE",
                count=2,
            ),
            ResearchBlockerObservation(
                symbol="HOTUSDT",
                timeframe="4h",
                playbook="support_reclaim",
                blocker="COST_STRESS_RETURN_NOT_POSITIVE",
            ),
        ),
    )

    path = tmp_path / "blocker-dashboard.json"
    ledger = JsonlAuditStore(tmp_path / "blocker-dashboards.jsonl")
    ResearchBlockerDashboardWriter(path, ledger).write(dashboard)
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert stored["execution_allowed"] is False
    assert stored["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert stored["promotion_status"] == "RESEARCH_ONLY"
    assert stored["actions"][0]["occurrences"] == 3
    assert stored["actions"][0]["affected_timeframes"] == ["1h", "4h"]
    assert "slippage" in stored["actions"][0]["recommended_experiment"].lower()
    assert "RESEARCH_BLOCKER_DASHBOARD_WRITTEN" in ledger.path.read_text(
        encoding="utf-8"
    )


def health(
    index: int,
    *,
    healthy: bool = False,
) -> StrategyHealthSnapshot:
    return StrategyHealthSnapshot(
        strategy_id="breakout-retest:v1",
        observed_at=NOW + timedelta(days=index),
        oos_trade_count=30 if healthy else 4,
        expectancy=0.02 if healthy else -0.01,
        profit_factor=1.4 if healthy else 0.7,
        max_drawdown=0.10 if healthy else 0.35,
        turnover=0.10 if healthy else 0.40,
        regime_count=3 if healthy else 1,
    )


def test_decay_evaluator_only_demotes_after_consecutive_evidence() -> None:
    evaluator = StrategyDecayEvaluator(DecayPolicy())
    missing = evaluator.evaluate(HypothesisStatus.PAPER_APPROVED, ())
    assert missing.recommended_status is HypothesisStatus.PAPER_APPROVED
    assert missing.reason_codes == ("STRATEGY_HEALTH_EVIDENCE_MISSING",)

    one_weak = evaluator.evaluate(HypothesisStatus.PAPER_APPROVED, (health(1),))
    assert one_weak.recommended_status is HypothesisStatus.PAPER_APPROVED

    monitoring = evaluator.evaluate(
        HypothesisStatus.PAPER_APPROVED,
        (health(1), health(2)),
    )
    assert monitoring.recommended_status is HypothesisStatus.MONITORING
    assert monitoring.auto_promotion_allowed is False
    assert "DECAY_EXPECTANCY" in monitoring.reason_codes

    decayed = evaluator.evaluate(
        HypothesisStatus.MONITORING,
        (health(1), health(2)),
    )
    assert decayed.recommended_status is HypothesisStatus.DECAYED

    disabled = evaluator.evaluate(
        HypothesisStatus.DECAYED,
        (health(1), health(2), health(3)),
    )
    assert disabled.recommended_status is HypothesisStatus.DISABLED

    recovered = evaluator.evaluate(
        HypothesisStatus.MONITORING,
        (health(1), health(2, healthy=True)),
    )
    assert recovered.recommended_status is HypothesisStatus.MONITORING
