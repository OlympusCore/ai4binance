"""Archived-data Phase C validation pipeline tests."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from ai4binance.application import ResearchValidationService
from ai4binance.application.validation_pipeline import HistoricalPlaybookAdapter
from ai4binance.data import ParquetOHLCVArchive
from ai4binance.domain import ValidationStatus
from ai4binance.indicators import atr
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation import ParameterSet


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
    artifact_directory = tmp_path / "validation"

    batch = ResearchValidationService(archive, artifact_directory).run(
        "BTCUSDT", ("1h",)
    )

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
    assert trend.run_card.execution_allowed is False
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
    assert run_card["execution_allowed"] is False
    assert run_card["promotion_status"] in {"RESEARCH_ONLY", "STAGED_CANDIDATE"}
    assert len(run_card["dataset_sha256"]) == 64
    assert json.loads(run_card_events[0])["event_type"] == "RESEARCH_RUN_CARD_WRITTEN"
    assert dashboard["execution_allowed"] is False
    assert dashboard["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert dashboard["promotion_status"] == "RESEARCH_ONLY"
    assert any(
        action["blocker"] == "HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED"
        for action in dashboard["actions"]
    )
    assert (
        json.loads(dashboard_events[0])["event_type"]
        == "RESEARCH_BLOCKER_DASHBOARD_WRITTEN"
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
    artifact_directory = tmp_path / "validation"

    batch = ResearchValidationService(archive, artifact_directory).run(
        "HOTUSDT", ("1h",)
    )

    assert all(
        "INSUFFICIENT_VALIDATION_CANDLES" in result.blockers for result in batch.results
    )
    assert not artifact_directory.exists()


def test_historical_adapter_incremental_atr_matches_batch_wilder_atr() -> None:
    candles = validation_candles(80)
    adapter = HistoricalPlaybookAdapter(
        "trend_continuation",
        ParameterSet(
            "baseline",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        ),
    )

    for length in range(1, len(candles) + 1):
        adapter(candles[:length])
        if length >= 15:
            assert adapter._current_atr == atr(candles[:length], 14)


def test_historical_adapter_records_blockers_and_emits_quality_intent() -> None:
    from test_strategy_rules import candles as regime_candles

    history = regime_candles(trending=True)
    adapter = HistoricalPlaybookAdapter(
        "trend_continuation",
        ParameterSet(
            "quality",
            (("atr_stop_multiplier", 1.5), ("take_profit_multiplier", 3.0)),
        ),
    )

    intents = tuple(adapter(history[:length]) for length in range(1, len(history) + 1))

    assert any(intent is not None for intent in intents)
    assert dict(adapter.blocker_counts)["INSUFFICIENT_PLAYBOOK_HISTORY"] == 21
