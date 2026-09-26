"""Multi-timeframe Futures simulation orchestration tests."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.data.binance_vision_futures import BinanceVisionFuturesReplayIngestor
from ai4binance.data.market_history_sync import MarketHistorySourceUnavailableError
from ai4binance.research.futures_multitf import (
    FUTURES_MULTITF_TIMEFRAMES,
    FuturesMultiTimeframeBacktestReport,
    FuturesMultiTimeframeBacktestRunner,
)
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation import RuntimeFuturesReplayDataset
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

NOW = datetime(2026, 9, 10, tzinfo=UTC)
_DURATIONS = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def test_failed_futures_ingest_is_retried_and_never_becomes_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "_eligible_symbols", lambda _root: ("BTCUSDT",)
    )
    calls: list[str] = []

    def fail_ingest(*_args: object, **_kwargs: object) -> object:
        calls.append("ingest")
        raise ValueError("source integrity failure")

    monkeypatch.setattr(
        BinanceVisionFuturesReplayIngestor,
        "with_persistent_cache",
        fail_ingest,
    )
    settings = Settings()
    first = futures_multitf.run_cycle(settings, observed_at=NOW)
    assert first["status"] == "DEGRADED"
    assert first["completed_symbol_count"] == 0
    assert first["pending_symbol_count"] == 1
    assert first["active_timeframe"] == "5m"
    assert first["failure_code"] == "FUTURES_MULTITF_VALUEERROR"
    persisted = json.loads(
        (tmp_path / "runtime/state/futures-multitf-latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["phase"] == "INGEST"
    assert persisted["cycle_started_at"] == NOW.isoformat()
    assert persisted["progress_at"]
    waiting = futures_multitf.run_cycle(
        settings, observed_at=NOW + timedelta(minutes=1)
    )
    assert waiting["status"] == "WAITING_FOR_RETRY"
    assert waiting["blockers"] == ["FUTURES_MULTITF_RETRY_PENDING"]
    assert len(calls) == 1
    retried = futures_multitf.run_cycle(
        settings, observed_at=NOW + timedelta(minutes=31)
    )
    assert retried["status"] == "DEGRADED"
    assert len(calls) == 2
    assert retried["execution_allowed"] is False


def test_unpublished_futures_archive_is_deferred_until_the_window_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A known immutable-source gap must not retry forever or starve the queue."""
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "_eligible_symbols", lambda _root: ("NEWUSDT",)
    )
    monkeypatch.setattr(
        BinanceVisionFuturesReplayIngestor,
        "with_persistent_cache",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MarketHistorySourceUnavailableError("archive-not-published")
        ),
    )

    deferred = futures_multitf.run_cycle(Settings(), observed_at=NOW)
    assert deferred["status"] == "DEFERRED"
    assert deferred["blockers"] == ["FUTURES_DETAIL_SOURCE_NOT_PUBLISHED"]
    assert deferred["retry_after"] == {}
    unavailable_windows = cast(dict[str, str], deferred["unavailable_windows"])
    assert unavailable_windows["NEWUSDT"] == deferred["window"]

    settled = futures_multitf.run_cycle(
        Settings(), observed_at=NOW + timedelta(minutes=1)
    )
    assert settled["status"] == "CURRENT_WITH_SOURCE_GAPS"
    assert settled["pending_symbol_count"] == 0
    assert settled["unavailable_symbol_count"] == 1


def test_current_cycle_keeps_the_local_futures_opportunity_monitor_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "_eligible_symbols", lambda _root: ("BTCUSDT", "ETHUSDT")
    )
    current_window = "2026-08-12_to_2026-09-08"
    state_path = tmp_path / "runtime/state/futures-multitf-latest.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "eligible_symbols": ["BTCUSDT", "ETHUSDT"],
                "completed_windows": {
                    "BTCUSDT": current_window,
                    "ETHUSDT": current_window,
                },
                "monitor_symbol": "BTCUSDT",
            }
        ),
        encoding="utf-8",
    )
    seen: list[str] = []

    def monitor(
        _settings: Settings,
        _root: Path,
        symbol: str,
        _now: datetime,
    ) -> dict[str, object]:
        seen.append(symbol)
        return {"status": "CURRENT", "symbol": symbol, "candidate_count": 5}

    monkeypatch.setattr(futures_multitf, "_monitor_futures_symbol", monitor)
    result = futures_multitf.run_cycle(Settings(), observed_at=NOW)

    assert result["status"] == "CURRENT"
    assert result["monitor_symbol"] == "ETHUSDT"
    monitoring = result["opportunity_monitor"]
    assert isinstance(monitoring, dict)
    assert monitoring["candidate_count"] == 5
    assert seen == ["ETHUSDT"]
    assert result["execution_allowed"] is False
    assert result["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_monitor_summary_counts_closed_favorable_and_adverse_evidence() -> None:
    from ai4binance.cli.futures_multitf import _monitor_summary

    summary = _monitor_summary(
        {
            "status": "CURRENT",
            "symbol": "BTCUSDT",
            "candidates": [{}, {}, {}],
            "history_count": 3,
            "history": [
                {
                    "outcome": {
                        "status": "EVALUATED",
                        "final_outcome_class": "TARGET_FIRST",
                    }
                },
                {"outcome": {"status": "EVALUATED", "final_outcome_class": "ADVERSE"}},
                {"outcome": {"status": "PENDING_HORIZON"}},
            ],
        }
    )

    assert summary["candidate_count"] == 3
    assert summary["evaluated_outcome_count"] == 2
    assert summary["favorable_outcome_count"] == 1
    assert summary["adverse_outcome_count"] == 1
    assert summary["execution_allowed"] is False


def test_three_consecutive_adverse_outcomes_create_one_tuning_trigger() -> None:
    from ai4binance.cli.futures_multitf import _monitor_summary

    history = [
        {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "setup_name": "NEW_LONG_PARTICIPATION",
            "opportunity_id": f"opportunity-{index}",
            "observed_at": (NOW + timedelta(minutes=index)).isoformat(),
            "outcome": {
                "status": "EVALUATED",
                "final_outcome_class": "ADVERSE",
            },
        }
        for index in range(3)
    ]

    summary = _monitor_summary(
        {
            "status": "CURRENT",
            "symbol": "BTCUSDT",
            "candidates": [],
            "history_count": len(history),
            "history": history,
        }
    )

    trigger = summary["tuning_trigger"]
    assert isinstance(trigger, dict)
    assert trigger["kind"] == "ADVERSE_OUTCOME_STREAK"
    assert trigger["failure_count"] == 3
    assert trigger["timeframe"] == "15m"


def test_backtest_missed_opportunity_streak_creates_tuning_trigger() -> None:
    from ai4binance.cli.futures_multitf import _backtest_tuning_trigger
    from ai4binance.research.backtesting.models import MissedOpportunityCategory

    records = tuple(
        SimpleNamespace(
            counterfactual_result=MissedOpportunityCategory.BAD_BLOCK,
            regime="NEW_LONG_PARTICIPATION",
            pre_veto_observation_id=f"pre-veto-{index}",
            rejected_at=NOW + timedelta(minutes=index),
        )
        for index in range(3)
    )
    report = SimpleNamespace(
        symbol="BTCUSDT",
        timeframe_results=(
            SimpleNamespace(
                timeframe="1h",
                results=(
                    SimpleNamespace(
                        missed_opportunity_ledger=SimpleNamespace(records=records)
                    ),
                ),
            ),
        ),
    )

    trigger = _backtest_tuning_trigger(
        cast(FuturesMultiTimeframeBacktestReport, report)
    )

    assert trigger is not None
    assert trigger["kind"] == "MISSED_OPPORTUNITY_STREAK"
    assert trigger["failure_count"] == 3
    assert trigger["setup"] == "NEW_LONG_PARTICIPATION"


def test_current_cycle_runs_one_new_failure_tuning_trigger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "_eligible_symbols", lambda _root: ("BTCUSDT",)
    )
    current_window = "2026-08-12_to_2026-09-08"
    state_path = tmp_path / "runtime/state/futures-multitf-latest.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"completed_windows": {"BTCUSDT": current_window}}),
        encoding="utf-8",
    )
    trigger = {
        "trigger_id": "futures-tuning:adverse-streak",
        "kind": "ADVERSE_OUTCOME_STREAK",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "setup": "NEW_LONG_PARTICIPATION",
    }
    monkeypatch.setattr(
        futures_multitf,
        "_monitor_futures_symbol",
        lambda *_args: {"status": "CURRENT", "tuning_trigger": trigger},
    )
    calls: list[str] = []

    def run_tuning(**kwargs: object) -> dict[str, object]:
        calls.append(str(kwargs["trigger"]))
        completed = kwargs["completed_trigger_ids"]
        assert isinstance(completed, set)
        completed.add("futures-tuning:adverse-streak")
        return {"status": "RESEARCH_TUNING_COMPLETED", "execution_allowed": False}

    monkeypatch.setattr(futures_multitf, "_run_triggered_tuning", run_tuning)
    result = futures_multitf.run_cycle(Settings(), observed_at=NOW)

    tuning = result["failure_tuning"]
    assert isinstance(tuning, dict)
    assert tuning["status"] == "RESEARCH_TUNING_COMPLETED"
    assert result["completed_tuning_triggers"] == ["futures-tuning:adverse-streak"]
    assert len(calls) == 1


def _dataset(timeframe: str) -> RuntimeFuturesReplayDataset:
    candles = tuple(
        OHLCVCandle(
            timestamp=NOW + _DURATIONS[timeframe] * index,
            open=Decimal(100 + index),
            high=Decimal(102 + index),
            low=Decimal(99 + index),
            close=Decimal(101 + index),
            volume=Decimal("1000"),
        )
        for index in range(30)
    )
    observed_at = candles[-1].timestamp + _DURATIONS[timeframe]

    def point(metric: DerivativesMetric, index: int, value: Decimal) -> MetricPoint:
        return MetricPoint(
            metric=metric,
            timestamp=candles[index].timestamp,
            value=value,
            provenance=Provenance(
                source_id="BINANCE_USD_M_PUBLIC_REST",
                source_url="https://fapi.binance.com/futures/data/openInterestHist",
                observed_at=observed_at,
            ),
        )

    return RuntimeFuturesReplayDataset(
        symbol="BTCUSDT",
        candles=candles,
        derivatives=DerivativesDataset(
            symbol="BTCUSDT",
            as_of=observed_at,
            source="BINANCE_USD_M_PUBLIC_REST",
            series={
                DerivativesMetric.OPEN_INTEREST: tuple(
                    point(
                        DerivativesMetric.OPEN_INTEREST,
                        index,
                        Decimal(1000 + index * 10),
                    )
                    for index in range(len(candles))
                ),
                DerivativesMetric.FUNDING_RATE: (
                    *(
                        point(DerivativesMetric.FUNDING_RATE, index, Decimal("0.0001"))
                        for index in range(len(candles))
                    ),
                ),
            },
        ),
        timeframe=timeframe,
    )


def test_failure_tuning_runs_walk_forward_and_never_applies_parameters(
    tmp_path: Path,
) -> None:
    from ai4binance.cli.futures_multitf import _run_futures_failure_tuning

    result = _run_futures_failure_tuning(
        _dataset("1h"),
        {
            "trigger_id": "futures-tuning:test-trigger",
            "kind": "MISSED_OPPORTUNITY_STREAK",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "setup": "NEW_LONG_PARTICIPATION",
            "failure_count": 3,
            "evidence_ids": ["one", "two", "three"],
        },
        tmp_path,
    )

    assert result["status"] == "RESEARCH_TUNING_COMPLETED"
    assert result["candidate_count"] == 6
    assert result["parameter_application"] == "NOT_APPLIED"
    assert result["execution_allowed"] is False
    assert Path(str(result["artifact_path"])).is_file()


def test_runner_persists_separate_timeframes_and_advisory_learning(
    tmp_path: Path,
) -> None:
    datasets = {
        timeframe: _dataset(timeframe) for timeframe in FUTURES_MULTITF_TIMEFRAMES
    }

    report = FuturesMultiTimeframeBacktestRunner(tmp_path).run(
        datasets,
        created_at=datetime(2026, 9, 11, tzinfo=UTC),
    )

    assert tuple(item.timeframe for item in report.timeframe_results) == (
        FUTURES_MULTITF_TIMEFRAMES
    )
    assert all(len(item.results) == 4 for item in report.timeframe_results)
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    payload = json.loads(Path(report.artifact_path).read_text(encoding="utf-8"))
    assert payload["timeframes"] == list(FUTURES_MULTITF_TIMEFRAMES)
    assert len(payload["timeframe_results"]) == 4
    assert all(
        "pre_veto_opportunities" in setup and "missed_opportunities" in setup
        for timeframe in payload["timeframe_results"]
        for setup in timeframe["setups"]
    )
    assert payload["second_brain_learning"]["risk_change_allowed"] is False
    assert payload["execution_allowed"] is False


def test_runner_rejects_incomplete_timeframe_set(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="datasets must be exact"):
        FuturesMultiTimeframeBacktestRunner(tmp_path).run({"1h": _dataset("1h")})


def test_eligible_symbols_validates_and_normalizes_cached_universe(
    tmp_path: Path,
) -> None:
    from ai4binance.cli.futures_multitf import (
        _eligible_symbols,
        _retain_current_universe_state,
    )
    from ai4binance.integrations.research_market_universe import (
        RESEARCH_MARKET_UNIVERSE_SOURCE,
    )

    base = {
        "observed_at": datetime.now(UTC).isoformat(),
        "source": RESEARCH_MARKET_UNIVERSE_SOURCE,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

    with pytest.raises(ValueError, match="UNIVERSE_UNAVAILABLE"):
        _eligible_symbols(tmp_path)

    path = tmp_path / "universe-v3.json"
    path.write_text(
        json.dumps({**base, "futures_symbols": "BTCUSDT"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="UNIVERSE_INVALID"):
        _eligible_symbols(tmp_path)

    path.write_text(
        json.dumps(
            {
                **base,
                "observed_at": datetime.now().replace(microsecond=0).isoformat(),
                "futures_symbols": ["BTCUSDT"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="UNIVERSE_INVALID"):
        _eligible_symbols(tmp_path)

    path.write_text(
        json.dumps({**base, "futures_symbols": ["../bad", 7]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="UNIVERSE_EMPTY"):
        _eligible_symbols(tmp_path)

    path.write_text(
        json.dumps(
            {
                **base,
                "futures_symbols": [
                    " ethusdt ",
                    "BTCUSDT",
                    "BTCUSDT",
                    "not-valid!",
                    7,
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _eligible_symbols(tmp_path) == ("BTCUSDT", "ETHUSDT")

    retained = _retain_current_universe_state(
        {
            "eligible_symbols": ["OLDUSDT"],
            "attempted_windows": {"OLDUSDT": "old", "BTCUSDT": "current"},
            "completed_windows": {"OLDUSDT": "old"},
            "retry_after": {"OLDUSDT": "old"},
            "unavailable_windows": {"OLDUSDT": "old"},
            "active_symbol": "OLDUSDT",
            "monitor_symbol": "OLDUSDT",
            "completed_tuning_triggers": ["old-trigger"],
        },
        ("BTCUSDT", "ETHUSDT"),
    )
    assert retained["attempted_windows"] == {"BTCUSDT": "current"}
    assert retained["completed_windows"] == {}
    assert retained["retry_after"] == {}
    assert retained["unavailable_windows"] == {}
    assert retained["completed_tuning_triggers"] == []
    assert "active_symbol" not in retained
    assert "monitor_symbol" not in retained


def test_learning_projection_handles_unavailable_and_bounded_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import futures_multitf

    monkeypatch.setattr(futures_multitf, "to_primitive", lambda _value: "invalid")
    assert futures_multitf._learning_projection(object()) == {"status": "UNAVAILABLE"}

    monkeypatch.setattr(
        futures_multitf,
        "to_primitive",
        lambda _value: {
            "summary_id": "learning-1",
            "lessons": [{"code": "KEEP"}, {"code": 7}, "invalid"],
            "experiments": "invalid",
        },
    )
    projection = futures_multitf._learning_projection(object())
    assert projection["lesson_count"] == 3
    assert projection["experiment_count"] == 0
    assert projection["lesson_codes"] == ["KEEP"]


def test_monitor_trigger_ignores_incomplete_and_nonconsecutive_evidence() -> None:
    from ai4binance.cli.futures_multitf import _monitor_tuning_trigger

    adverse = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "setup_name": "NEW_LONG_PARTICIPATION",
        "observed_at": NOW.isoformat(),
        "outcome": {"status": "EVALUATED", "final_outcome_class": "ADVERSE"},
    }
    assert (
        _monitor_tuning_trigger(
            [
                "invalid",
                {"outcome": {"status": "PENDING_HORIZON"}},
                {"outcome": {"status": "EVALUATED"}},
                {**adverse, "opportunity_id": "one"},
                {
                    **adverse,
                    "opportunity_id": "two",
                    "outcome": {
                        "status": "EVALUATED",
                        "final_outcome_class": "FAVORABLE",
                    },
                },
            ]
        )
        is None
    )
    assert (
        _monitor_tuning_trigger(
            [
                {**adverse, "opportunity_id": "one"},
                {**adverse, "opportunity_id": "two"},
                adverse,
            ]
        )
        is None
    )


def test_backtest_trigger_returns_none_without_three_bad_blocks() -> None:
    from ai4binance.cli.futures_multitf import _backtest_tuning_trigger
    from ai4binance.research.backtesting.models import MissedOpportunityCategory

    report = SimpleNamespace(
        symbol="BTCUSDT",
        timeframe_results=(
            SimpleNamespace(
                timeframe="1h",
                results=(
                    SimpleNamespace(
                        missed_opportunity_ledger=SimpleNamespace(
                            records=(
                                SimpleNamespace(
                                    counterfactual_result=MissedOpportunityCategory.GOOD_BLOCK
                                ),
                            )
                        )
                    ),
                ),
            ),
        ),
    )

    assert (
        _backtest_tuning_trigger(cast(FuturesMultiTimeframeBacktestReport, report))
        is None
    )


def test_futures_tuning_rejects_too_short_replay_and_reuses_artifact(
    tmp_path: Path,
) -> None:
    from ai4binance.cli.futures_multitf import (
        _futures_tuning_config,
        _run_futures_failure_tuning,
    )

    with pytest.raises(ValueError, match="REPLAY_INSUFFICIENT"):
        _futures_tuning_config(3)

    dataset = _dataset("1h")
    trigger = {
        "trigger_id": "futures-tuning:existing",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "setup": "NEW_LONG_PARTICIPATION",
    }
    artifact = tmp_path / "BTCUSDT" / "1h" / "existing.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")

    result = _run_futures_failure_tuning(dataset, trigger, tmp_path)
    assert result["status"] == "ALREADY_REVIEWED"


def test_cached_tuning_dataset_requires_path_and_matching_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import futures_multitf

    trigger = {"symbol": "BTCUSDT", "timeframe": "1h"}
    with pytest.raises(ValueError, match="REPLAY_UNAVAILABLE"):
        futures_multitf._load_cached_tuning_dataset(tmp_path, {}, trigger)
    with pytest.raises(ValueError, match="REPLAY_UNAVAILABLE"):
        futures_multitf._load_cached_tuning_dataset(
            tmp_path, {"dataset_artifacts": {"1h": 7}}, trigger
        )

    class Loader:
        def __init__(self, root: Path) -> None:
            assert root == tmp_path

        def load(self, path: str) -> RuntimeFuturesReplayDataset:
            assert path == "dataset.json"
            return _dataset("15m")

    monkeypatch.setattr(futures_multitf, "RuntimeFuturesReplayLoader", Loader)
    with pytest.raises(ValueError, match="REPLAY_IDENTITY_INVALID"):
        futures_multitf._load_cached_tuning_dataset(
            tmp_path,
            {"dataset_artifacts": {"1h": "dataset.json"}},
            trigger,
        )

    matching = _dataset("1h")
    monkeypatch.setattr(Loader, "load", lambda _self, _path: matching)
    assert (
        futures_multitf._load_cached_tuning_dataset(
            tmp_path,
            {"dataset_artifacts": {"1h": "dataset.json"}},
            trigger,
        )
        is matching
    )


def test_triggered_tuning_handles_invalid_completed_and_cached_triggers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import futures_multitf

    def run(
        trigger: Mapping[str, object] | None, completed_trigger_ids: set[str]
    ) -> dict[str, object]:
        return futures_multitf._run_triggered_tuning(
            state={},
            datasets={},
            replay_root=tmp_path,
            artifact_root=tmp_path / "artifacts",
            trigger=trigger,
            completed_trigger_ids=completed_trigger_ids,
        )

    completed: set[str] = set()
    assert run(None, completed)["status"] == "NOT_TRIGGERED"
    assert run({}, completed)["status"] == "BLOCKED"

    trigger = {"trigger_id": "futures-tuning:one", "timeframe": "1h"}
    completed.add("futures-tuning:one")
    assert run(trigger, completed)["status"] == "ALREADY_REVIEWED"

    completed.clear()
    dataset = _dataset("1h")
    monkeypatch.setattr(
        futures_multitf, "_load_cached_tuning_dataset", lambda *_args: dataset
    )
    monkeypatch.setattr(
        futures_multitf,
        "_run_futures_failure_tuning",
        lambda *_args: {"status": "RESEARCH_TUNING_COMPLETED"},
    )
    result = run(trigger, completed)
    assert result["status"] == "RESEARCH_TUNING_COMPLETED"
    assert completed == {"futures-tuning:one"}


def test_monitor_futures_symbol_maps_empty_invalid_and_valid_radar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "FuturesOosEvidenceReader", lambda path: str(path)
    )
    monkeypatch.setattr(futures_multitf, "ParquetOHLCVArchive", lambda path: path)

    class Advisor:
        def __init__(
            self, _collector: object, *, timeframe: str, **_kwargs: object
        ) -> None:
            self.timeframe = timeframe

        def build(self, _snapshot: object) -> SimpleNamespace:
            radar: tuple[object, ...]
            if self.timeframe == "5m":
                radar = ()
            elif self.timeframe == "15m":
                radar = (object(),)
            else:
                radar = ({"status": "VALID", "direction": "BULLISH"},)
            return SimpleNamespace(opportunity_radar=radar)

    monkeypatch.setattr(futures_multitf, "RuntimeFuturesAdvisor", Advisor)
    monkeypatch.setattr(
        futures_multitf,
        "to_primitive",
        lambda value: value if isinstance(value, dict) else "invalid",
    )

    built: list[object] = []

    def refresh(*_args: object, **kwargs: object) -> dict[str, object]:
        builder = cast(Callable[[object, str], object], kwargs["futures_builder"])
        candles = tuple(
            OHLCVCandle(
                timestamp=NOW + _DURATIONS["1h"] * index,
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("10"),
            )
            for index in range(15)
        )
        snapshot = SimpleNamespace(ohlcv_by_timeframe={"1h": candles})
        built.extend(
            (
                builder(snapshot, "5m"),
                builder(snapshot, "15m"),
                builder(snapshot, "1h"),
            )
        )
        return {
            "status": "CURRENT",
            "symbol": "BTCUSDT",
            "candidates": built,
            "history": [],
        }

    monkeypatch.setattr(futures_multitf, "refresh_monitor", refresh)
    result = futures_multitf._monitor_futures_symbol(
        Settings(), tmp_path, "BTCUSDT", NOW
    )

    assert result["candidate_count"] == 3
    assert isinstance(built[2], dict)
    assert {
        "entry",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "target_risk_reward",
    } <= set(built[2])


def test_successful_cycle_persists_datasets_learning_and_safe_tuning_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "_eligible_symbols", lambda _root: ("BTCUSDT",)
    )

    class Ingestor:
        def sync_range(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            timeframe = str(_kwargs.get("timeframe", ""))
            return SimpleNamespace(dataset=_dataset("1h"), artifact_path=timeframe)

    monkeypatch.setattr(
        BinanceVisionFuturesReplayIngestor,
        "with_persistent_cache",
        lambda *_args, **_kwargs: Ingestor(),
    )
    report = SimpleNamespace(
        artifact_path="report.json",
        learning_summary={"summary_id": "learning", "lessons": [], "experiments": []},
        timeframe_results=(),
        symbol="BTCUSDT",
    )
    monkeypatch.setattr(
        futures_multitf,
        "FuturesMultiTimeframeBacktestRunner",
        lambda _root: SimpleNamespace(run=lambda *_args, **_kwargs: report),
    )
    monkeypatch.setattr(
        futures_multitf,
        "_monitor_futures_symbol",
        lambda *_args: (_ for _ in ()).throw(OSError("monitor unavailable")),
    )
    monkeypatch.setattr(
        futures_multitf,
        "_run_triggered_tuning",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("tuning unavailable")),
    )

    result = futures_multitf.run_cycle(Settings(), observed_at=NOW)

    assert result["status"] == "PROCESSED"
    assert result["phase"] == "BACKTEST"
    assert result["failure_code"] is None
    dataset_artifacts = result["dataset_artifacts"]
    learning = result["learning"]
    opportunity_monitor = result["opportunity_monitor"]
    failure_tuning = result["failure_tuning"]
    assert isinstance(dataset_artifacts, dict)
    assert isinstance(learning, dict)
    assert isinstance(opportunity_monitor, dict)
    assert isinstance(failure_tuning, dict)
    assert set(dataset_artifacts) == set(FUTURES_MULTITF_TIMEFRAMES)
    assert learning["status"] == "READY"
    assert opportunity_monitor["status"] == "DEGRADED"
    assert failure_tuning["status"] == "BLOCKED"


def test_waiting_cycle_maps_monitor_and_tuning_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        futures_multitf, "_eligible_symbols", lambda _root: ("BTCUSDT",)
    )
    state_path = tmp_path / "runtime/state/futures-multitf-latest.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "retry_after": {"BTCUSDT": (NOW + timedelta(hours=1)).isoformat()},
                "completed_tuning_triggers": "invalid",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        futures_multitf,
        "_monitor_futures_symbol",
        lambda *_args: (_ for _ in ()).throw(OSError("monitor unavailable")),
    )
    monkeypatch.setattr(
        futures_multitf,
        "_run_triggered_tuning",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("tuning unavailable")),
    )

    result = futures_multitf.run_cycle(Settings(), observed_at=NOW)

    assert result["status"] == "WAITING_FOR_RETRY"
    opportunity_monitor = result["opportunity_monitor"]
    failure_tuning = result["failure_tuning"]
    assert isinstance(opportunity_monitor, dict)
    assert isinstance(failure_tuning, dict)
    assert opportunity_monitor["status"] == "DEGRADED"
    assert failure_tuning["status"] == "BLOCKED"


def test_futures_multitf_main_runs_once_daemon_and_validates_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from contextlib import nullcontext

    from ai4binance.cli import futures_multitf

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(futures_multitf, "Settings", lambda: object())
    monkeypatch.setattr(
        futures_multitf, "SingleInstanceLease", lambda _path: nullcontext()
    )
    calls: list[datetime] = []

    def run_cycle(_settings: object, *, observed_at: datetime) -> dict[str, object]:
        calls.append(observed_at)
        return {"status": "CURRENT"}

    monkeypatch.setattr(futures_multitf, "run_cycle", run_cycle)
    sleeps: list[int] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    assert futures_multitf.main(["once"]) == 0
    assert futures_multitf.main(["daemon", "--max-cycles", "2"]) == 0
    assert len(calls) == 3
    assert sleeps == [300]
    assert capsys.readouterr().out.count('"status": "CURRENT"') == 3
    with pytest.raises(ValueError, match="max-cycles must be positive"):
        futures_multitf.main(["daemon", "--max-cycles", "0"])
    assert futures_multitf.build_parser().prog


def test_futures_multitf_cycle_rejects_naive_timestamp() -> None:
    from ai4binance.cli import futures_multitf
    from ai4binance.config import Settings

    with pytest.raises(ValueError, match="timezone-aware"):
        futures_multitf.run_cycle(Settings(), observed_at=datetime(2026, 9, 10))
