"""Tuning sensitivity and human-only parameter promotion tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.events import (
    CanonicalTraceJournal,
    ConsequentialTraceKind,
    TraceabilityRequirement,
    TraceabilityStatus,
    canonical_trace_journal_path,
)
from ai4binance.research.backtesting import BacktestIntent, SignalProvider
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage.jsonl import JsonlAuditStore
from ai4binance.strategies.registry import (
    GovernedStrategyRegistry,
    build_governed_strategy_registry,
    build_playbook_registry,
)
from ai4binance.tuning import (
    GovernedParameterStore,
    HumanApproval,
    ParameterDomain,
    PromotionBoard,
    SearchSpace,
    TuningConfig,
    TuningEngine,
    TuningReport,
)
from ai4binance.tuning.promotion import StrategyPromotionTarget
from ai4binance.tuning.storage import TuningAuditWriter
from ai4binance.validation import (
    MarketRegime,
    ParameterSet,
    PromotionEvidenceLedger,
    PromotionEvidenceSourceKind,
    WalkForwardConfig,
)

NOW = datetime(2026, 2, 1, tzinfo=UTC)


def _write_validation_run_card(
    root: Path,
    *,
    symbol: str,
    timeframe: str,
    playbook: str,
) -> None:
    path = root / symbol / timeframe / f"{playbook}.run-card.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        f"runtime/artifacts/research/backtest/validation/{symbol}/{timeframe}/{playbook}.jsonl",
                        "abc",
                    ]
                ],
                "blockers": [],
                "created_at": NOW.isoformat(),
                "execution_allowed": False,
                "hypothesis_id": f"hyp:{playbook}:{timeframe}",
                "metrics": [("net_return", 0.01), ("trade_count", 12.0)],
                "promotion_status": "PAPER_APPROVED",
                "run_id": f"run:{playbook}:{timeframe}",
                "symbol": symbol,
                "timeframe": timeframe,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def complete_governed_strategy_registry(tmp_path: Path) -> GovernedStrategyRegistry:
    validation_root = tmp_path / "validation"
    _write_validation_run_card(
        validation_root,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="trend_continuation",
    )
    _write_validation_run_card(
        validation_root,
        symbol="HOTUSDT",
        timeframe="1h",
        playbook="volatility_expansion",
    )
    base = build_governed_strategy_registry()
    family = base.resolve_playbook("trend_continuation")
    promoted = replace(
        family,
        parameter_set_ref=(
            validation_root / "HOTUSDT" / "1h" / "trend_continuation.run-card.json"
        ).as_posix(),
        dataset_revision=validation_root.as_posix(),
        backtest_ref=(
            validation_root / "HOTUSDT" / "1h" / "trend_continuation.run-card.json"
        ).as_posix(),
        walk_forward_ref=validation_root.as_posix(),
        oos_ref=validation_root.as_posix(),
        robustness_ref=validation_root.as_posix(),
        paper_ref=validation_root.as_posix(),
    )
    return GovernedStrategyRegistry(
        tuple(
            promoted if item.strategy_id == promoted.strategy_id else item
            for item in base.strategies
        )
    )


def candles(count: int = 12) -> tuple[OHLCVCandle, ...]:
    return tuple(
        OHLCVCandle(
            timestamp=NOW + timedelta(hours=index),
            open=Decimal("100"),
            high=Decimal("104"),
            low=Decimal("98"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for index in range(count)
    )


def strategy_factory(parameters: ParameterSet) -> SignalProvider:
    values = dict(parameters.values)
    target = Decimal("100") + Decimal(str(values["take_profit_multiplier"]))

    def provider(history: tuple[OHLCVCandle, ...]) -> BacktestIntent | None:
        if len(history) % 2 == 0:
            return None
        return BacktestIntent(
            signal_id=f"{parameters.name}:{history[-1].timestamp.isoformat()}",
            timestamp=history[-1].timestamp,
            stop_loss=Decimal("95"),
            take_profit=target,
            atr=Decimal("2"),
        )

    return provider


def regime_classifier(candle: OHLCVCandle) -> MarketRegime:
    return MarketRegime.TREND if candle.timestamp.hour % 4 < 2 else MarketRegime.RANGE


def walk_forward_config() -> WalkForwardConfig:
    return WalkForwardConfig(
        train_size=4,
        test_size=2,
        step_size=2,
        min_oos_trades=4,
        max_turnover=0.6,
        max_edge_concentration=0.3,
    )


def search_space() -> SearchSpace:
    return SearchSpace(
        (
            ParameterDomain("take_profit_multiplier", (1.0, 2.0, 3.0)),
            ParameterDomain("trailing_multiplier", (1.0, 1.5)),
        )
    )


def tuning_report(*, min_neighbors: int = 2) -> TuningReport:
    return TuningEngine().tune(
        symbol="hotusdt",
        timeframe="1h",
        candles=candles(),
        search_space=search_space(),
        strategy_factory=strategy_factory,
        regime_classifier=regime_classifier,
        config=TuningConfig(
            walk_forward=walk_forward_config(),
            min_neighbor_count=min_neighbors,
            min_neighbor_pass_ratio=0.5,
            min_neighbor_return_ratio=0.5,
        ),
    )


def test_tuning_selects_stable_oos_candidate_deterministically() -> None:
    first = tuning_report()
    second = tuning_report()

    assert len(first.evaluations) == 6
    assert dict(first.selected_parameters.values)["take_profit_multiplier"] == 3.0
    assert first.sensitivity.neighbor_count == 3
    assert first.sensitivity.passing_neighbor_count == 2
    assert first.sensitivity.pass_ratio == pytest.approx(2 / 3)
    assert first.promotion_status is ValidationStatus.STAGED_CANDIDATE
    assert first.blockers == ()
    assert first.report_id == second.report_id


def test_isolated_optimum_remains_research_only() -> None:
    report = tuning_report(min_neighbors=10)

    assert report.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert "INSUFFICIENT_SENSITIVITY_NEIGHBORS" in report.blockers


def test_search_space_rejects_unapproved_duplicate_and_unbounded_domains() -> None:
    with pytest.raises(ValueError, match="not approved"):
        ParameterDomain("secret_edge", (1.0,))
    with pytest.raises(ValueError, match="unique"):
        ParameterDomain("ema_fast", (10.0, 10.0))
    with pytest.raises(ValueError, match="outside approved bounds"):
        ParameterDomain("atr_stop_multiplier", (-1.0,))
    with pytest.raises(ValueError, match="must be integers"):
        ParameterDomain("rsi_period", (14.5,))
    with pytest.raises(ValueError, match="unique"):
        SearchSpace(
            (
                ParameterDomain("ema_fast", (10.0,)),
                ParameterDomain("ema_fast", (20.0,)),
            )
        )
    with pytest.raises(ValueError, match="exceeds"):
        SearchSpace(
            (ParameterDomain("ema_fast", (10.0, 20.0, 30.0)),),
            max_candidates=2,
        )


def test_tuning_rejects_invalid_fast_slow_relationships() -> None:
    invalid = SearchSpace(
        (
            ParameterDomain("ema_fast", (20.0,)),
            ParameterDomain("ema_slow", (10.0,)),
        )
    )
    with pytest.raises(ValueError, match="no governance-valid"):
        TuningEngine().tune(
            symbol="HOTUSDT",
            timeframe="1h",
            candles=candles(),
            search_space=invalid,
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=TuningConfig(walk_forward_config()),
        )


def test_tuning_report_is_persisted_as_append_only_audit(tmp_path: Path) -> None:
    report = tuning_report()
    output = tmp_path / "tuning.jsonl"
    TuningAuditWriter(JsonlAuditStore(output)).append(report)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["event_type"] == "TUNING_REPORT"
    assert payload["payload"]["report"]["report_id"] == report.report_id
    assert payload["payload"]["report"]["detail_level"] == "BOUNDED_SUMMARY"
    persisted_fold = payload["payload"]["report"]["evaluations"][0]["walk_forward"][
        "folds"
    ][0]
    assert "training_result" not in persisted_fold
    assert "oos_result" not in persisted_fold
    assert "training_metrics" in persisted_fold
    assert "oos_metrics" in persisted_fold


def approval_for(report_id: str, parameters: ParameterSet) -> HumanApproval:
    return HumanApproval(
        approval_id="approval-1",
        approver="human-reviewer",
        approved_at=NOW + timedelta(days=1),
        tuning_report_id=report_id,
        parameters=parameters,
    )


def test_human_board_and_revision_store_activates_parameters(
    tmp_path: Path,
) -> None:
    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    board_path = tmp_path / "promotion-board.jsonl"
    board = PromotionBoard(JsonlAuditStore(board_path))
    parameter_store = GovernedParameterStore(tmp_path / "production-parameters.json")

    board.record(report, approval)
    revision = parameter_store.activate(report, approval, expected_revision=0)

    persisted = json.loads(parameter_store.path.read_text(encoding="utf-8"))
    assert revision == 1
    assert persisted["revision"] == 1
    assert persisted["status"] == "PAPER_APPROVED"
    assert persisted["approval_id"] == "approval-1"
    assert json.loads(board_path.read_text(encoding="utf-8"))["event_type"] == (
        "PARAMETER_PROMOTION_APPROVED"
    )
    with pytest.raises(ValueError, match="revision conflict"):
        parameter_store.activate(report, approval, expected_revision=0)
    journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))
    assert {record.trace_kind for record in journal.records()} == {
        ConsequentialTraceKind.APPROVAL,
        ConsequentialTraceKind.CONFIG_CHANGE,
    }


def test_parameter_promotion_and_activation_emit_canonical_trace_records(
    tmp_path: Path,
) -> None:
    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    trace_journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))
    board = PromotionBoard(
        JsonlAuditStore(tmp_path / "promotion-board.jsonl"),
        trace_journal=trace_journal,
    )
    parameter_store = GovernedParameterStore(
        tmp_path / "production-parameters.json",
        trace_journal=trace_journal,
    )

    board.record(report, approval)
    board.apply_to_strategy_registry(
        report,
        approval,
        StrategyPromotionTarget("trend_continuation", "1", "default"),
        build_playbook_registry(),
        governed_registry=complete_governed_strategy_registry(tmp_path),
    )
    parameter_store.activate(report, approval, expected_revision=0)
    audit = trace_journal.audit(
        (
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.APPROVAL,
                subject_ref=approval.approval_id,
                event_name="PARAMETER_PROMOTION_APPROVED",
                subject_type="PARAMETER_PROMOTION_APPROVAL",
                approval_ref=approval.approval_id,
            ),
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.PROMOTION_CANDIDATE,
                subject_ref="trend_continuation:1:default",
                event_name="STRATEGY_PROMOTION_APPROVED",
                subject_type="STRATEGY_PROMOTION_ARTIFACT",
                approval_ref=approval.approval_id,
            ),
            TraceabilityRequirement(
                trace_kind=ConsequentialTraceKind.CONFIG_CHANGE,
                subject_ref=str(parameter_store.path.resolve()),
                event_name="GOVERNED_PARAMETER_ACTIVATED",
                subject_type="GOVERNED_PARAMETER_STORE",
                approval_ref=approval.approval_id,
            ),
        )
    )

    assert audit.status is TraceabilityStatus.PASS
    assert {record.trace_kind for record in trace_journal.records()} == {
        ConsequentialTraceKind.APPROVAL,
        ConsequentialTraceKind.PROMOTION_CANDIDATE,
        ConsequentialTraceKind.CONFIG_CHANGE,
    }
    config_record = next(
        record
        for record in trace_journal.records()
        if record.trace_kind is ConsequentialTraceKind.CONFIG_CHANGE
    )
    assert config_record.governed_paths == (str(parameter_store.path.resolve()),)


def test_promotion_board_applies_paper_approval_to_strategy_registry(
    tmp_path: Path,
) -> None:
    from ai4binance.strategies.engine import StrategyEngine
    from tests.test_strategy_risk import evidence, snapshot

    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    result = PromotionBoard(
        JsonlAuditStore(tmp_path / "strategy-board.jsonl")
    ).apply_to_strategy_registry(
        report,
        approval,
        StrategyPromotionTarget("trend_continuation", "1", "default"),
        build_playbook_registry(),
        governed_registry=complete_governed_strategy_registry(tmp_path),
    )
    engine = StrategyEngine(
        registry=result.registry,
        approval_registry=result.approval_registry,
        governed_registry=result.governed_registry,
    )

    candidate = engine.generate(snapshot(), evidence(0.8))[0]

    assert result.registry.get("trend_continuation").promotion_status is (
        ValidationStatus.PAPER_APPROVED
    )
    assert result.governed_registry.resolve_playbook(
        "trend_continuation"
    ).promotion_status is (ValidationStatus.PAPER_APPROVED)
    assert candidate.promotion_status is ValidationStatus.PAPER_APPROVED
    assert result.artifact.approval_id == approval.approval_id
    journal = CanonicalTraceJournal(canonical_trace_journal_path(tmp_path))
    assert {record.trace_kind for record in journal.records()} == {
        ConsequentialTraceKind.PROMOTION_CANDIDATE,
    }


def test_promotion_board_appends_promotion_evidence_ledger(
    tmp_path: Path,
) -> None:
    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    ledger = PromotionEvidenceLedger(tmp_path / "promotion-evidence.jsonl")
    board = PromotionBoard(
        JsonlAuditStore(tmp_path / "strategy-board.jsonl"),
        evidence_ledger=ledger,
    )

    board.record(report, approval)
    board.apply_to_strategy_registry(
        report,
        approval,
        StrategyPromotionTarget("trend_continuation", "1", "default"),
        build_playbook_registry(),
        governed_registry=complete_governed_strategy_registry(tmp_path),
    )

    records = ledger.records()
    assert len(records) == 2
    assert {item.source_kind for item in records} == {
        PromotionEvidenceSourceKind.MANUAL_REVIEW,
        PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
    }
    assert all(not item.is_exact_bound for item in records)


def test_promotion_rejects_mismatch_research_and_live_authority(tmp_path: Path) -> None:
    staged = tuning_report()
    mismatch = approval_for("wrong-report", staged.selected_parameters)
    board = PromotionBoard(JsonlAuditStore(tmp_path / "board.jsonl"))

    with pytest.raises(ValueError, match="approval identity"):
        replace(mismatch, approval_id=" ")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(mismatch, approved_at=datetime(2026, 2, 1))
    with pytest.raises(ValueError, match="target identity"):
        StrategyPromotionTarget(" ", "1", "default")
    with pytest.raises(ValueError, match="IDs must match"):
        board.record(staged, mismatch)
    with pytest.raises(ValueError, match="cannot approve live"):
        replace(
            approval_for(staged.report_id, staged.selected_parameters),
            target_status=ValidationStatus.LIVE_ELIGIBLE,
        )
    research = tuning_report(min_neighbors=10)
    with pytest.raises(ValueError, match="only staged"):
        board.record(
            research,
            approval_for(research.report_id, research.selected_parameters),
        )


def test_promotion_board_rejects_unimplemented_and_duplicate_strategy_artifacts(
    tmp_path: Path,
) -> None:
    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    board = PromotionBoard(
        JsonlAuditStore(tmp_path / "board.jsonl"),
        trace_journal=None,
    )
    registry = build_playbook_registry()
    unimplemented = next(
        item.name for item in registry.playbooks if not item.implemented
    )
    governed_registry = complete_governed_strategy_registry(tmp_path)

    with pytest.raises(ValueError, match="implemented"):
        board.apply_to_strategy_registry(
            report,
            approval,
            StrategyPromotionTarget(unimplemented, "1", "default"),
            registry,
            governed_registry=governed_registry,
        )

    first = board.apply_to_strategy_registry(
        report,
        approval,
        StrategyPromotionTarget("trend_continuation", "1", "default"),
        registry,
        governed_registry=governed_registry,
    )
    with pytest.raises(ValueError, match="already exists"):
        board.apply_to_strategy_registry(
            report,
            approval,
            StrategyPromotionTarget("trend_continuation", "1", "default"),
            registry,
            approval_registry=first.approval_registry,
            governed_registry=governed_registry,
        )


def test_promotion_board_allows_trace_journal_to_be_disabled(tmp_path: Path) -> None:
    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    board = PromotionBoard(
        JsonlAuditStore(tmp_path / "board.jsonl"),
        trace_journal=None,
    )
    object.__setattr__(board, "trace_journal", None)
    store = GovernedParameterStore(
        tmp_path / "production.json",
        trace_journal=None,
    )
    object.__setattr__(store, "trace_journal", None)

    board.record(report, approval)
    store.activate(report, approval, expected_revision=0)

    assert not canonical_trace_journal_path(tmp_path).exists()


def test_promotion_board_rejects_strategy_family_without_complete_real_evidence(
    tmp_path: Path,
) -> None:
    report = tuning_report()
    approval = approval_for(report.report_id, report.selected_parameters)
    board = PromotionBoard(JsonlAuditStore(tmp_path / "board.jsonl"))

    with pytest.raises(ValueError, match="paper approval requires complete"):
        board.apply_to_strategy_registry(
            report,
            approval,
            StrategyPromotionTarget("trend_continuation", "1", "default"),
            build_playbook_registry(),
        )


def test_governed_store_rejects_corrupt_revision(tmp_path: Path) -> None:
    path = tmp_path / "production.json"
    path.write_text('{"revision": 0}', encoding="utf-8")

    with pytest.raises(ValueError, match="revision is invalid"):
        GovernedParameterStore(path).current_revision()


def test_tuning_config_rejects_unsafe_sensitivity_thresholds() -> None:
    with pytest.raises(ValueError, match="neighbor count"):
        TuningConfig(walk_forward_config(), min_neighbor_count=0)
    with pytest.raises(ValueError, match="sensitivity ratios"):
        TuningConfig(walk_forward_config(), min_neighbor_pass_ratio=1.1)
