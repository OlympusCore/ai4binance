"""Archived-data Phase C validation pipeline tests."""

import json
from collections.abc import Sized
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.application import ResearchValidationService
from ai4binance.application.validation_pipeline import (
    HistoricalPlaybookAdapter,
    PlaybookValidationResult,
    ValidationBatchResult,
)
from ai4binance.data import ParquetOHLCVArchive
from ai4binance.domain import ValidationStatus
from ai4binance.indicators import atr
from ai4binance.research.backtesting import BacktestConfig, BacktestEngine
from ai4binance.schemas import OHLCVCandle
from ai4binance.storage import JsonlAuditStore
from ai4binance.strategies.registry import StrategyRiskProfileRegistry
from ai4binance.strategies.rules import historical_playbook_decision
from ai4binance.validation import ParameterSet
from ai4binance.validation_pipeline_runtime import (
    SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO,
    HistoricalValidationRuntime,
    _build_historical_decision_resolver,
    runtime_spot_backtest_engine,
)


def validation_candles(count: int) -> tuple[OHLCVCandle, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles: list[OHLCVCandle] = []
    for index in range(count):
        base = Decimal("1") + Decimal(index) / Decimal("1000")
        close = base + (Decimal("0.01") if index % 3 else Decimal("-0.005"))
        candles.append(
            OHLCVCandle(
                timestamp=start + timedelta(hours=index),
                open=base,
                high=max(base, close) + Decimal("0.01"),
                low=min(base, close) - Decimal("0.01"),
                close=close,
                volume=Decimal("1000") + index,
            )
        )
    return tuple(candles)


def test_validation_binds_simulation_config_to_wf_stress_and_checkpoint(
    tmp_path: Path,
) -> None:
    config = BacktestConfig(quantity=Decimal("0.01"), minimum_notional=Decimal("0.001"))
    runtime = HistoricalValidationRuntime(backtest_engine=BacktestEngine(config))
    assert runtime.config_sha256(120) != HistoricalValidationRuntime().config_sha256(
        120
    )
    result = runtime.validate_one(
        "HOTUSDT",
        "1h",
        "trend_continuation",
        validation_candles(120),
        artifact_directory=tmp_path,
    )
    assert cast(Any, result.backtest).assumptions == config
    for evaluation in cast(Any, result.tuning).evaluations:
        assert (
            evaluation.walk_forward_report.statistical_evidence.hypothesis_count
            == len(cast(Any, result.tuning).evaluations)
        )
        for fold in evaluation.walk_forward_report.folds:
            assert fold.training_result.assumptions == config
            assert fold.oos_result.assumptions == config
    assert cast(
        Any, result.run_card
    ).config_sha256 != HistoricalValidationRuntime().config_sha256(120)


def build_intent(**kwargs: object) -> dict[str, object]:
    return dict(kwargs)


def test_preflight_checkpoint_identity_includes_simulation_assumptions() -> None:
    baseline = HistoricalValidationRuntime()
    changed = HistoricalValidationRuntime(
        backtest_engine=BacktestEngine(BacktestConfig(quantity=Decimal("0.001")))
    )
    assert baseline.config_sha256(10) != changed.config_sha256(10)


def test_validation_walk_forward_uses_nonzero_purge_and_embargo() -> None:
    config = HistoricalValidationRuntime._tuning_config(605).walk_forward

    assert config.purge_size == 1
    assert config.embargo_size == 1
    assert config.train_size + (config.test_size * 5) + 5 == 605


def test_runtime_spot_backtest_sizing_is_price_normalized_and_cash_bounded() -> None:
    candles = tuple(
        OHLCVCandle(
            timestamp=datetime(2026, 1, 1, hour=index, tzinfo=UTC),
            open=Decimal("80000") + Decimal(index * 1000),
            high=Decimal("81500") + Decimal(index * 1000),
            low=Decimal("79000") + Decimal(index * 1000),
            close=Decimal("80500") + Decimal(index * 1000),
            volume=Decimal("100"),
        )
        for index in range(3)
    )

    engine = runtime_spot_backtest_engine(
        candles,
        base_engine=BacktestEngine(),
        notional_to_equity_ratio=SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO,
    )

    maximum_open = max(candle.open for candle in candles)
    maximum_notional = maximum_open * engine.config.quantity
    assert engine.config.quantity < Decimal("1")
    assert maximum_notional <= (
        engine.config.initial_cash_usdt * SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO
    )
    assert maximum_notional >= engine.config.minimum_notional


@pytest.mark.parametrize("ratio", [Decimal("0"), Decimal("1.01")])
def test_runtime_spot_backtest_sizing_rejects_unsafe_ratios(
    ratio: Decimal,
) -> None:
    with pytest.raises(ValueError, match="within"):
        HistoricalValidationRuntime(position_notional_to_equity_ratio=ratio)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"execution_allowed": True}, "cannot grant execution authority"),
        ({"promotion_status": ValidationStatus.PAPER_APPROVED}, "research or staged"),
        (
            {"stage_timings_ms": (("preflight", 1.0), ("preflight", 2.0))},
            "names must be unique",
        ),
        ({"stage_timings_ms": ((" ", 1.0),)}, "named and non-negative"),
        ({"stage_timings_ms": (("preflight", -1.0),)}, "named and non-negative"),
    ],
)
def test_playbook_validation_result_rejects_authority_and_invalid_telemetry(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "playbook": "trend_continuation",
        "timeframe": "1h",
        "candle_count": 60,
        "promotion_status": ValidationStatus.RESEARCH_ONLY,
        "blockers": (),
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        cast(Any, PlaybookValidationResult)(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"execution_allowed": True},
        {"live_eligibility_status": "LIVE_ORDER_ELIGIBLE"},
    ],
)
def test_validation_batch_rejects_live_authority(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {"symbol": "BTCUSDT", "results": ()}
    values.update(overrides)
    with pytest.raises(ValueError, match="must remain execution blocked"):
        cast(Any, ValidationBatchResult)(**values)


def test_validation_decision_resolver_reuses_one_playbook_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.validation_pipeline_runtime as runtime_module
    from ai4binance.strategies.registry import build_playbook_registry

    registry = build_playbook_registry()
    build_calls = 0

    def counted_registry_builder() -> object:
        nonlocal build_calls
        build_calls += 1
        return registry

    monkeypatch.setattr(
        runtime_module,
        "build_playbook_registry",
        counted_registry_builder,
    )
    resolver = _build_historical_decision_resolver()
    history = validation_candles(60)

    first = resolver("trend_continuation", history)
    second = resolver("trend_continuation", history)

    assert first == second
    assert build_calls == 1


def test_validation_decision_resolver_reuses_exact_immutable_history_decision() -> None:
    history = validation_candles(80)
    resolver = _build_historical_decision_resolver(history)

    first = resolver("trend_continuation", history)
    second = resolver("trend_continuation", history)
    direct = historical_playbook_decision("trend_continuation", history)

    assert second is first
    assert first == direct


def test_validation_decision_cache_allocates_dataset_slots_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.validation_pipeline_runtime as runtime_module

    history = validation_candles(80)
    dataset_size_requests = 0

    def counted_len(value: Sized) -> int:
        nonlocal dataset_size_requests
        if value is history:
            dataset_size_requests += 1
        return len(value)

    monkeypatch.setattr(runtime_module, "len", counted_len, raising=False)
    resolver = _build_historical_decision_resolver(history)
    first = resolver("trend_continuation", history)
    for _ in range(10):
        assert resolver("trend_continuation", history) is first
    assert dataset_size_requests == 1


def test_validation_pipeline_runs_six_playbooks_and_persists_evidence(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "market")
    archive.update(
        "BTCUSDT",
        "1h",
        validation_candles(60),
        source="TEST_MARKET_DATA",
    )
    artifact_directory = (
        tmp_path / "runtime" / "artifacts" / "research" / "backtest" / "validation"
    )
    report_directory = tmp_path / "runtime" / "reports" / "backtest"

    batch = ResearchValidationService(
        archive,
        artifact_directory,
        HistoricalValidationRuntime(report_directory=report_directory),
    ).run("BTCUSDT", ("1h",))

    assert len(batch.results) == 6
    assert batch.execution_allowed is False
    assert batch.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    resistance = next(
        result for result in batch.results if result.playbook == "resistance_rejection"
    )
    assert resistance.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert resistance.blockers == ("HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED",)
    trend = next(
        result for result in batch.results if result.playbook == "trend_continuation"
    )
    assert trend.backtest is not None
    assert trend.tuning is not None
    assert trend.robustness is not None
    assert trend.run_card is not None
    assert cast(Any, trend.run_card).execution_allowed is False
    lines = (
        (artifact_directory / "BTCUSDT" / "1h" / "trend_continuation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert [json.loads(line)["event_type"] for line in lines] == [
        "BACKTEST_RESULT",
        "WALK_FORWARD_REPORT",
        "TUNING_REPORT",
        "BACKTEST_ROBUSTNESS_REPORT",
    ]
    run_card = json.loads(
        (
            artifact_directory / "BTCUSDT" / "1h" / "trend_continuation.run-card.json"
        ).read_text(encoding="utf-8")
    )
    dashboard = json.loads(
        (artifact_directory / "BTCUSDT" / "blocker-dashboard.json").read_text(
            encoding="utf-8"
        )
    )
    run_card_events = (
        (artifact_directory / "research_run_cards.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    dashboard_events = (
        (artifact_directory / "blocker_dashboards.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    report_payload = json.loads(
        (
            artifact_directory.parent
            / "reports"
            / "validation"
            / "BTCUSDT"
            / "1h"
            / "trend_continuation.summary.json"
        ).read_text(encoding="utf-8")
    )
    report_markdown = (
        report_directory
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "trend_continuation.summary.md"
    ).read_text(encoding="utf-8")
    assert run_card["execution_allowed"] is False
    assert run_card["promotion_status"] in {"RESEARCH_ONLY", "STAGED_CANDIDATE"}
    assert len(run_card["dataset_sha256"]) == 64
    assert run_card["artifact_sha256"][0][0] == (
        "runtime/artifacts/research/backtest/validation/BTCUSDT/1h/"
        "trend_continuation.jsonl"
    )
    assert json.loads(run_card_events[0])["event_type"] == "RESEARCH_RUN_CARD_WRITTEN"
    assert dashboard["execution_allowed"] is False
    assert dashboard["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert dashboard["promotion_status"] == "RESEARCH_ONLY"
    assert report_payload["artifact_path"].startswith(
        "runtime/artifacts/research/backtest/validation/BTCUSDT/1h/"
    )
    assert "Backtest Summary" in report_markdown
    assert any(
        action["blocker"] == "HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED"
        for action in dashboard["actions"]
    )
    assert (
        json.loads(dashboard_events[0])["event_type"]
        == "RESEARCH_BLOCKER_DASHBOARD_WRITTEN"
    )
    run_manifests = sorted(
        (artifact_directory / "BTCUSDT" / "runs").glob("*.manifest.json")
    )
    assert len(run_manifests) == 1
    run_manifest = json.loads(run_manifests[0].read_text(encoding="utf-8"))
    assert run_manifest["status"] == "COMPLETED"
    assert len(run_manifest["playbook_terminals"]) == 6
    assert {
        terminal["checkpoint_status"] for terminal in run_manifest["playbook_terminals"]
    } == {"MISS"}
    assert all(
        terminal["execution_allowed"] is False
        for terminal in run_manifest["playbook_terminals"]
    )
    assert (
        run_manifest["timeframe_evidence"][0]["dataset_sha256"]
        == (run_card["dataset_sha256"])
    )
    event_path = artifact_directory / "BTCUSDT" / "validation-run-events.jsonl"
    event_lines = event_path.read_bytes().splitlines()
    event_types = [json.loads(line)["event_type"] for line in event_lines]
    assert event_types == [
        "VALIDATION_RUN_STARTED",
        "VALIDATION_TIMEFRAME_READY",
        *("VALIDATION_PLAYBOOK_TERMINAL" for _ in range(6)),
        "VALIDATION_RUN_TERMINAL",
    ]
    assert all(
        len(line) + 1 <= JsonlAuditStore(event_path).max_event_bytes
        for line in event_lines
    )

    resumed = ResearchValidationService(
        archive,
        artifact_directory,
        HistoricalValidationRuntime(report_directory=report_directory),
    ).run("BTCUSDT", ("1h",))
    resumed_trend = next(
        result for result in resumed.results if result.playbook == "trend_continuation"
    )
    assert resumed_trend.resumed_from_checkpoint is True
    assert resumed_trend.backtest is None
    assert resumed_trend.run_card is not None
    resumed_run_card = cast(dict[str, object], resumed_trend.run_card)
    assert resumed_run_card["symbol"] == "BTCUSDT"
    assert resumed_run_card["timeframe"] == "1h"
    assert resumed_trend.checkpoint_path is not None
    assert Path(resumed_trend.checkpoint_path).is_file()
    checkpoint = json.loads(
        Path(resumed_trend.checkpoint_path).read_text(encoding="utf-8")
    )
    assert len(checkpoint["run_card_sha256"]) == 64
    assert dict(resumed_trend.stage_timings_ms)["checkpoint_lookup"] >= 0
    resumed_manifest = json.loads(
        sorted((artifact_directory / "BTCUSDT" / "runs").glob("*.manifest.json"))[
            -1
        ].read_text(encoding="utf-8")
    )
    assert {
        terminal["checkpoint_status"]
        for terminal in resumed_manifest["playbook_terminals"]
    } == {"HIT", "MISS"}
    assert len(lines) == len(
        (artifact_directory / "BTCUSDT" / "1h" / "trend_continuation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )


def test_validation_pipeline_blocks_insufficient_history_without_artifacts(
    tmp_path: Path,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "market")
    archive.update(
        "HOTUSDT",
        "1h",
        validation_candles(20),
        source="TEST_MARKET_DATA",
    )
    artifact_directory = tmp_path / "runtime" / "artifacts" / "backtest" / "validation"

    batch = ResearchValidationService(
        archive,
        artifact_directory,
        HistoricalValidationRuntime(
            report_directory=tmp_path / "runtime" / "reports" / "backtest"
        ),
    ).run("HOTUSDT", ("1h",))

    assert all(
        "INSUFFICIENT_VALIDATION_CANDLES" in result.blockers for result in batch.results
    )
    assert not tuple((artifact_directory / "HOTUSDT" / "1h").glob("*.jsonl"))
    manifest_path = next(
        (artifact_directory / "HOTUSDT" / "runs").glob("*.manifest.json")
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETED"
    assert len(manifest["playbook_terminals"]) == 6
    assert all(
        terminal["stage_timings_ms"]["preflight"] >= 0
        for terminal in manifest["playbook_terminals"]
    )


def test_validation_manifest_exists_before_archive_read(tmp_path: Path) -> None:
    artifact_directory = tmp_path / "runtime" / "artifacts" / "validation"

    class ManifestAwareArchive:
        def read(self, symbol: str, timeframe: str) -> tuple[OHLCVCandle, ...]:
            manifests = tuple(
                (artifact_directory / symbol / "runs").glob("*.manifest.json")
            )
            assert len(manifests) == 1
            payload = json.loads(manifests[0].read_text(encoding="utf-8"))
            assert payload["status"] == "RUNNING"
            assert payload["playbook_terminals"] == []
            return validation_candles(20)

    ResearchValidationService(
        ManifestAwareArchive(),
        artifact_directory,
        HistoricalValidationRuntime(),
    ).run("BTCUSDT", ("1d",))


def test_validation_failure_persists_playbook_and_run_terminal_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "market")
    archive.update(
        "BTCUSDT",
        "1h",
        validation_candles(60),
        source="TEST_MARKET_DATA",
    )
    artifact_directory = tmp_path / "runtime" / "artifacts" / "validation"

    def fail_validation(*args: object, **kwargs: object) -> PlaybookValidationResult:
        del args, kwargs
        raise RuntimeError("measured validation failure")

    monkeypatch.setattr(
        HistoricalValidationRuntime,
        "validate_one",
        fail_validation,
    )

    with pytest.raises(RuntimeError, match="measured validation failure"):
        ResearchValidationService(
            archive,
            artifact_directory,
            HistoricalValidationRuntime(),
        ).run("BTCUSDT", ("1h",))

    manifest_path = next(
        (artifact_directory / "BTCUSDT" / "runs").glob("*.manifest.json")
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["playbook_terminals"] == [
        {
            "blockers": [],
            "checkpoint_status": "MISS",
            "execution_allowed": False,
            "failure_code": "RuntimeError",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "playbook": "trend_continuation",
            "promotion_status": "RESEARCH_ONLY",
            "stage_timings_ms": {
                "checkpoint_lookup": pytest.approx(0, abs=1000),
            },
            "status": "FAILED",
            "timeframe": "1h",
        }
    ]
    event_path = artifact_directory / "BTCUSDT" / "validation-run-events.jsonl"
    event_types = [
        json.loads(line)["event_type"]
        for line in event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert event_types[-2:] == [
        "VALIDATION_PLAYBOOK_TERMINAL",
        "VALIDATION_RUN_TERMINAL",
    ]


def test_validation_interrupt_persists_playbook_and_run_terminal_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = ParquetOHLCVArchive(tmp_path / "market")
    archive.update(
        "BTCUSDT",
        "1h",
        validation_candles(60),
        source="TEST_MARKET_DATA",
    )
    artifact_directory = tmp_path / "runtime" / "artifacts" / "validation"

    def interrupt_validation(
        *args: object, **kwargs: object
    ) -> PlaybookValidationResult:
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(
        HistoricalValidationRuntime,
        "validate_one",
        interrupt_validation,
    )

    with pytest.raises(KeyboardInterrupt):
        ResearchValidationService(
            archive,
            artifact_directory,
            HistoricalValidationRuntime(),
        ).run("BTCUSDT", ("1h",))

    manifest_path = next(
        (artifact_directory / "BTCUSDT" / "runs").glob("*.manifest.json")
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["playbook_terminals"][0]["status"] == "FAILED"
    assert manifest["playbook_terminals"][0]["failure_code"] == "KeyboardInterrupt"


def test_historical_adapter_incremental_atr_matches_batch_wilder_atr() -> None:
    candles = validation_candles(80)
    adapter = HistoricalPlaybookAdapter(
        playbook="trend_continuation",
        parameters=ParameterSet(
            "baseline",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        ),
        decision_resolver=historical_playbook_decision,
        atr_calculator=atr,
        intent_builder=build_intent,
    )

    for length in range(1, len(candles) + 1):
        adapter(candles[:length])
        if length >= 15:
            assert adapter._current_atr == atr(candles[:length], 14)


def test_historical_adapter_records_blockers_and_emits_quality_intent() -> None:
    from tests.test_strategy_rules import candles as regime_candles

    history = regime_candles(trending=True)
    adapter = HistoricalPlaybookAdapter(
        playbook="trend_continuation",
        parameters=ParameterSet(
            "quality",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        ),
        decision_resolver=historical_playbook_decision,
        atr_calculator=atr,
        intent_builder=build_intent,
    )

    intents = tuple(adapter(history[:length]) for length in range(1, len(history) + 1))
    emitted = next(intent for intent in intents if intent is not None)

    assert any(intent is not None for intent in intents)
    assert dict(adapter.blocker_counts)["INSUFFICIENT_PLAYBOOK_HISTORY"] == 21
    assert dict(adapter.blocker_counts)["REGIME_STRATEGY_CONDITIONS_REQUIRED"] == 49
    assert emitted["strategy_id"] == "trend_continuation"
    assert emitted["strategy_version"] == "1"
    assert emitted["strategy_config_version"] == "1"
    assert len(emitted["strategy_config_hash"]) == 64
    assert emitted["market"] == "SPOT"
    assert emitted["symbol"] == "UNKNOWN_SYMBOL"
    assert emitted["timeframe"] == "UNKNOWN"
    assert emitted["decision_id"].startswith("decision:")
    assert emitted["snapshot_id"].startswith("snapshot:")
    assert "REGIME_STRATEGY_ELIGIBLE" in emitted["reason_codes"]
    assert emitted["funnel_stages"] == ("DISCOVERED", "READY_FOR_RISK")


def test_historical_adapter_fails_closed_when_strategy_risk_profile_missing() -> None:
    from tests.test_strategy_rules import candles as regime_candles

    history = regime_candles(trending=True)
    adapter = HistoricalPlaybookAdapter(
        playbook="trend_continuation",
        parameters=ParameterSet(
            "baseline",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        ),
        decision_resolver=historical_playbook_decision,
        atr_calculator=atr,
        intent_builder=build_intent,
        risk_profile_registry=StrategyRiskProfileRegistry(()),
    )

    intents = tuple(adapter(history[:length]) for length in range(1, len(history) + 1))
    emitted = next((item for item in intents if item is not None), None)

    assert emitted is None
    assert dict(adapter.blocker_counts)["STRATEGY_RISK_PROFILE_UNCONFIGURED"] >= 1
