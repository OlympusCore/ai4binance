"""Resumable all-eligible-coin multi-timeframe Futures research service."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from ai4binance.application.opportunity_monitor import (
    monitor_directory,
    refresh_monitor,
)
from ai4binance.application.opportunity_observation import (
    analyze_futures_snapshot,
    project_futures_opportunity,
)
from ai4binance.config import Settings
from ai4binance.data.acquisition import LocalMarketSnapshotTransport
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.binance_vision_futures import (
    BinanceVisionFuturesReplayIngestor,
)
from ai4binance.data.market_history_sync import MarketHistorySourceUnavailableError
from ai4binance.integrations.research_market_universe import (
    RESEARCH_MARKET_UNIVERSE_SOURCE,
)
from ai4binance.ops import SingleInstanceLease
from ai4binance.reporting import to_primitive
from ai4binance.research.futures_multitf import (
    FUTURES_MULTITF_TIMEFRAMES,
    FuturesMultiTimeframeBacktestReport,
    FuturesMultiTimeframeBacktestRunner,
)
from ai4binance.schemas import AnalysisState, MarketSnapshot
from ai4binance.storage import write_json_object_verified
from ai4binance.validation import (
    FuturesWalkForwardValidator,
    ParameterSet,
    RuntimeFuturesBacktestAdapter,
    RuntimeFuturesBacktestConfig,
    RuntimeFuturesReplayDataset,
    RuntimeFuturesReplayLoader,
    WalkForwardConfig,
    classify_validation_regime,
)
from ai4binance.whale_fusion.models import PriceOiRegime

_SAFE_STATE = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}
_ADVERSE_OUTCOMES = frozenset({"INVALIDATED_FIRST", "ADVERSE"})
_TUNING_TRIGGER_STREAK = 3
_MAX_COMPLETED_TUNING_TRIGGERS = 200
_UNIVERSE_MAX_AGE = timedelta(minutes=5)


def _absolute(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()


def _load_mapping(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _save(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _failure_code(error: Exception) -> str:
    message = str(error).strip()
    safe_message = (
        bool(message)
        and len(message) <= 120
        and message.isascii()
        and message == message.upper()
        and all(character.isalnum() or character == "_" for character in message)
    )
    if safe_message and message.startswith("FUTURES_"):
        return message
    return f"FUTURES_MULTITF_{type(error).__name__.upper()}"


def _save_progress(
    path: Path,
    previous: Mapping[str, object],
    *,
    cycle_started_at: datetime,
    symbol: str,
    phase: str,
    active_timeframe: str | None,
    artifacts: Mapping[str, str],
) -> None:
    payload = {
        **previous,
        "schema_version": "1.0",
        "status": "RUNNING",
        "cycle_started_at": cycle_started_at.isoformat(),
        "progress_at": datetime.now(UTC).isoformat(),
        "active_symbol": symbol,
        "active_timeframe": active_timeframe,
        "phase": phase,
        "dataset_artifacts": dict(artifacts),
        "blockers": [],
        "failure_code": None,
        **_SAFE_STATE,
    }
    _save(path, payload)


def _eligible_symbols(cache_root: Path) -> tuple[str, ...]:
    path = cache_root / "universe-v3.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("FUTURES_MULTITF_UNIVERSE_UNAVAILABLE")
    payload = _load_mapping(path)
    try:
        observed_at = datetime.fromisoformat(str(payload["observed_at"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("FUTURES_MULTITF_UNIVERSE_INVALID") from None
    if observed_at.utcoffset() is None:
        raise ValueError("FUTURES_MULTITF_UNIVERSE_INVALID")
    age = datetime.now(UTC) - observed_at
    if (
        not timedelta(0) <= age <= _UNIVERSE_MAX_AGE
        or payload.get("source") != RESEARCH_MARKET_UNIVERSE_SOURCE
        or payload.get("execution_allowed") is not False
        or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("FUTURES_MULTITF_UNIVERSE_INVALID")
    raw = payload.get("futures_symbols")
    if not isinstance(raw, list) or not raw or len(raw) > 5_000:
        raise ValueError("FUTURES_MULTITF_UNIVERSE_INVALID")
    symbols = tuple(
        sorted(
            {
                item.strip().upper()
                for item in raw
                if isinstance(item, str)
                and item.strip().isascii()
                and item.strip().isalnum()
                and 4 <= len(item.strip()) <= 24
            }
        )
    )
    if not symbols:
        raise ValueError("FUTURES_MULTITF_UNIVERSE_EMPTY")
    return symbols


def _retain_current_universe_state(
    state: Mapping[str, object], symbols: tuple[str, ...]
) -> dict[str, object]:
    """Drop state projections and cursors that refer to an older universe."""
    allowed = frozenset(symbols)
    previous = state.get("eligible_symbols")
    same_universe = isinstance(previous, list) and tuple(previous) == symbols
    retained = dict(state) if same_universe else {}
    for field in (
        "attempted_windows",
        "completed_windows",
        "retry_after",
        "unavailable_windows",
    ):
        raw = state.get(field)
        retained[field] = (
            {
                str(symbol): value
                for symbol, value in raw.items()
                if isinstance(symbol, str) and symbol in allowed
            }
            if isinstance(raw, Mapping)
            else {}
        )
    for field in ("active_symbol", "monitor_symbol"):
        if retained.get(field) not in allowed:
            retained.pop(field, None)
    retained["eligible_symbols"] = list(symbols)
    retained["universe_source"] = RESEARCH_MARKET_UNIVERSE_SOURCE
    if not same_universe:
        retained["completed_tuning_triggers"] = []
    retained.update(_SAFE_STATE)
    return retained


def _next_symbol(symbols: tuple[str, ...], cursor: object) -> str:
    """Return a stable round-robin Futures monitor target."""

    previous = str(cursor)
    if previous not in symbols:
        return symbols[0]
    return symbols[(symbols.index(previous) + 1) % len(symbols)]


def _learning_projection(summary: object) -> dict[str, object]:
    """Keep bounded recommendation-only learning evidence in service state."""

    payload = to_primitive(summary)
    if not isinstance(payload, Mapping):
        return {"status": "UNAVAILABLE"}
    lessons = payload.get("lessons")
    experiments = payload.get("experiments")
    return {
        "status": "READY",
        "summary_id": payload.get("summary_id"),
        "lesson_count": len(lessons) if isinstance(lessons, list) else 0,
        "experiment_count": len(experiments) if isinstance(experiments, list) else 0,
        "lesson_codes": [
            str(item.get("code"))
            for item in lessons[:12]
            if isinstance(item, Mapping) and isinstance(item.get("code"), str)
        ]
        if isinstance(lessons, list)
        else [],
        "risk_change_allowed": False,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _trigger_id(
    kind: str,
    symbol: str,
    timeframe: str,
    setup: str,
    evidence_ids: Sequence[str],
) -> str:
    seed = "|".join((kind, symbol, timeframe, setup, *evidence_ids))
    return f"futures-tuning:{sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def _monitor_tuning_trigger(rows: Sequence[object]) -> dict[str, object] | None:
    """Require exactly three consecutive closed adverse outcomes per setup."""

    grouped: dict[tuple[str, str, str], list[Mapping[str, object]]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        outcome = item.get("outcome")
        if not isinstance(outcome, Mapping) or outcome.get("status") != "EVALUATED":
            continue
        symbol = item.get("symbol")
        timeframe = item.get("timeframe")
        setup = item.get("setup_name")
        if not (
            isinstance(symbol, str)
            and symbol
            and isinstance(timeframe, str)
            and timeframe
            and isinstance(setup, str)
            and setup
        ):
            continue
        grouped.setdefault((symbol, timeframe, setup), []).append(item)

    triggers: list[dict[str, object]] = []
    for (symbol, timeframe, setup), history in grouped.items():
        tail: list[Mapping[str, object]] = []
        for item in reversed(history):
            outcome = item["outcome"]
            if not isinstance(outcome, Mapping):
                break
            if outcome.get("final_outcome_class") not in _ADVERSE_OUTCOMES:
                break
            tail.append(item)
        if len(tail) != _TUNING_TRIGGER_STREAK:
            continue
        evidence_ids = tuple(
            str(item.get("opportunity_id", "")) for item in reversed(tail)
        )
        if any(not value for value in evidence_ids):
            continue
        triggers.append(
            {
                "trigger_id": _trigger_id(
                    "ADVERSE_OUTCOME_STREAK", symbol, timeframe, setup, evidence_ids
                ),
                "kind": "ADVERSE_OUTCOME_STREAK",
                "symbol": symbol,
                "timeframe": timeframe,
                "setup": setup,
                "failure_count": _TUNING_TRIGGER_STREAK,
                "evidence_ids": list(evidence_ids),
                "observed_at": str(tail[0].get("observed_at", "")),
            }
        )
    return max(triggers, key=lambda item: str(item["observed_at"]), default=None)


def _backtest_tuning_trigger(
    report: FuturesMultiTimeframeBacktestReport,
) -> dict[str, object] | None:
    """Find a three-event missed-opportunity streak in fresh replay evidence."""

    for timeframe_result in report.timeframe_results:
        for result in timeframe_result.results:
            records = result.missed_opportunity_ledger.records
            tail = records[-_TUNING_TRIGGER_STREAK:]
            if len(tail) != _TUNING_TRIGGER_STREAK or any(
                record.counterfactual_result.value != "BAD_BLOCK" for record in tail
            ):
                continue
            setup = tail[-1].regime
            evidence_ids = tuple(record.pre_veto_observation_id for record in tail)
            return {
                "trigger_id": _trigger_id(
                    "MISSED_OPPORTUNITY_STREAK",
                    report.symbol,
                    timeframe_result.timeframe,
                    setup,
                    evidence_ids,
                ),
                "kind": "MISSED_OPPORTUNITY_STREAK",
                "symbol": report.symbol,
                "timeframe": timeframe_result.timeframe,
                "setup": setup,
                "failure_count": _TUNING_TRIGGER_STREAK,
                "evidence_ids": list(evidence_ids),
                "observed_at": tail[-1].rejected_at.isoformat(),
            }
    return None


def _futures_tuning_parameters() -> tuple[ParameterSet, ...]:
    """Return the finite, research-only parameter grid for Futures replay."""

    candidates = (
        (Decimal("0.015"), Decimal("0.035")),
        (Decimal("0.015"), Decimal("0.04")),
        (Decimal("0.015"), Decimal("0.05")),
        (Decimal("0.02"), Decimal("0.04")),
        (Decimal("0.02"), Decimal("0.05")),
        (Decimal("0.025"), Decimal("0.05")),
    )
    return tuple(
        ParameterSet(
            f"futures-failure-streak-{index}",
            (
                ("stop_loss_ratio", float(stop_loss)),
                ("take_profit_ratio", float(take_profit)),
            ),
        )
        for index, (stop_loss, take_profit) in enumerate(candidates, start=1)
    )


def _futures_tuning_config(candle_count: int) -> WalkForwardConfig:
    """Build two chronological OOS folds without relaxing validation thresholds."""

    test_size = max(2, candle_count // 5)
    train_size = candle_count - (2 * test_size)
    if train_size < 2:
        raise ValueError("FUTURES_TUNING_REPLAY_INSUFFICIENT")
    return WalkForwardConfig(
        train_size=train_size,
        test_size=test_size,
        step_size=test_size,
        min_folds=2,
        min_oos_trades=5,
        min_regime_count=2,
    )


def _run_futures_failure_tuning(
    dataset: RuntimeFuturesReplayDataset,
    trigger: Mapping[str, object],
    artifact_root: Path,
) -> dict[str, object]:
    """Run bounded OOS tuning and persist a recommendation-only result."""

    setup = PriceOiRegime(str(trigger["setup"]))
    parameters = _futures_tuning_parameters()
    trigger_id = str(trigger["trigger_id"])
    artifact_path = (
        artifact_root
        / dataset.symbol
        / dataset.timeframe
        / f"{trigger_id.rsplit(':', maxsplit=1)[-1]}.json"
    )
    if artifact_path.exists():
        return {
            "status": "ALREADY_REVIEWED",
            "trigger_id": trigger_id,
            "artifact_path": str(artifact_path),
            **_SAFE_STATE,
        }

    def strategy_factory(candidate: ParameterSet) -> RuntimeFuturesBacktestAdapter:
        values = dict(candidate.values)
        return RuntimeFuturesBacktestAdapter(
            RuntimeFuturesBacktestConfig(
                setup=setup,
                stop_loss_ratio=Decimal(str(values["stop_loss_ratio"])),
                take_profit_ratio=Decimal(str(values["take_profit_ratio"])),
            )
        )

    report = FuturesWalkForwardValidator().validate(
        dataset=dataset,
        setup=setup,
        parameters=parameters,
        strategy_factory=strategy_factory,
        regime_classifier=classify_validation_regime,
        config=_futures_tuning_config(len(dataset.candles)),
    )
    payload = {
        "schema_version": "1.0",
        "status": "RESEARCH_TUNING_COMPLETED",
        "trigger": dict(trigger),
        "dataset_sha256": dataset.dataset_sha256,
        "backtest_report_id": report.report_id,
        "candidate_count": len(parameters),
        "selected_parameters": [
            to_primitive(fold.selected_parameters) for fold in report.folds
        ],
        "validation_status": report.oos_validation_status.value,
        "validation_blockers": list(report.blockers),
        "recommendation_status": "RESEARCH_ONLY",
        "parameter_application": "NOT_APPLIED",
        **_SAFE_STATE,
    }
    write_json_object_verified(
        artifact_path,
        payload,
        blocker="FUTURES_FAILURE_TUNING_WRITE_FAILED",
        durable=True,
    )
    return {**payload, "artifact_path": str(artifact_path)}


def _load_cached_tuning_dataset(
    replay_root: Path,
    state: Mapping[str, object],
    trigger: Mapping[str, object],
) -> RuntimeFuturesReplayDataset:
    """Load only a prior checksum-bound replay matching the exact trigger."""

    artifacts = state.get("dataset_artifacts")
    timeframe = str(trigger["timeframe"])
    path = artifacts.get(timeframe) if isinstance(artifacts, Mapping) else None
    if not isinstance(path, str) or not path:
        raise ValueError("FUTURES_TUNING_REPLAY_UNAVAILABLE")
    dataset = RuntimeFuturesReplayLoader(replay_root).load(path)
    if dataset.symbol != trigger["symbol"] or dataset.timeframe != timeframe:
        raise ValueError("FUTURES_TUNING_REPLAY_IDENTITY_INVALID")
    return dataset


def _run_triggered_tuning(
    *,
    state: Mapping[str, object],
    datasets: Mapping[str, RuntimeFuturesReplayDataset],
    replay_root: Path,
    artifact_root: Path,
    trigger: Mapping[str, object] | None,
    completed_trigger_ids: set[str],
) -> dict[str, object]:
    """Run at most one new local tuning experiment per service cycle."""

    if trigger is None:
        return {"status": "NOT_TRIGGERED", **_SAFE_STATE}
    trigger_id = str(trigger.get("trigger_id", ""))
    if not trigger_id:
        return {
            "status": "BLOCKED",
            "blockers": ["FUTURES_TUNING_TRIGGER_INVALID"],
            **_SAFE_STATE,
        }
    if trigger_id in completed_trigger_ids:
        return {"status": "ALREADY_REVIEWED", "trigger_id": trigger_id, **_SAFE_STATE}
    timeframe = str(trigger.get("timeframe", ""))
    dataset = datasets.get(timeframe)
    if dataset is None:
        dataset = _load_cached_tuning_dataset(replay_root, state, trigger)
    result = _run_futures_failure_tuning(dataset, trigger, artifact_root)
    if result["status"] in {"RESEARCH_TUNING_COMPLETED", "ALREADY_REVIEWED"}:
        completed_trigger_ids.add(trigger_id)
    return result


def _tuning_trigger_from_monitor(
    monitoring: Mapping[str, object],
) -> Mapping[str, object] | None:
    """Return one schema-shaped monitor trigger, if the monitor emitted one."""

    trigger = monitoring.get("tuning_trigger")
    return trigger if isinstance(trigger, Mapping) else None


def _monitor_summary(payload: Mapping[str, object]) -> dict[str, object]:
    """Project deterministic post-observation evidence without trading claims."""

    history = payload.get("history")
    rows = history if isinstance(history, list) else []
    evaluated = [
        item
        for item in rows
        if isinstance(item, Mapping)
        and isinstance(item.get("outcome"), Mapping)
        and item["outcome"].get("status") == "EVALUATED"
    ]
    favorable = sum(
        item["outcome"].get("final_outcome_class") in {"TARGET_FIRST", "FAVORABLE"}
        for item in evaluated
    )
    adverse = sum(
        item["outcome"].get("final_outcome_class") in {"INVALIDATED_FIRST", "ADVERSE"}
        for item in evaluated
    )
    candidates = payload.get("candidates")
    return {
        "status": payload.get("status", "INVALID"),
        "symbol": payload.get("symbol"),
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
        "history_count": payload.get("history_count", 0),
        "evaluated_outcome_count": len(evaluated),
        "favorable_outcome_count": favorable,
        "adverse_outcome_count": adverse,
        "tuning_trigger": _monitor_tuning_trigger(rows),
        **_SAFE_STATE,
    }


def _monitor_futures_symbol(
    settings: Settings, root: Path, symbol: str, observed_at: datetime
) -> dict[str, object]:
    """Refresh one local-first Futures observation and evaluate closed outcomes."""

    try:
        with SingleInstanceLease(
            monitor_directory(root, "USD_M_FUTURES", symbol) / "refresh.lock"
        ):
            return _monitor_summary(
                _refresh_futures_monitor(settings, root, symbol, observed_at)
            )
    except RuntimeError as error:
        if str(error) != "runtime instance is already active":
            raise
        return {"status": "COALESCED", "symbol": symbol, "blockers": [], **_SAFE_STATE}


def _refresh_futures_monitor(
    settings: Settings,
    root: Path,
    symbol: str,
    observed_at: datetime,
    *,
    timeframes: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Share the canonical Futures monitor between background consumers."""

    analysis: AnalysisState | None = None
    transport = LocalMarketSnapshotTransport(
        _absolute(settings.dataset_directory) / "usd_m_futures" / "metadata",
        clock=lambda: observed_at,
    )

    def build(snapshot: MarketSnapshot, timeframe: str) -> dict[str, object]:
        nonlocal analysis
        if analysis is None:
            analysis = analyze_futures_snapshot(
                transport.attach_futures_context(snapshot)
            )
        return project_futures_opportunity(analysis, timeframe)

    payload = refresh_monitor(
        root,
        ParquetOHLCVArchive(_absolute(settings.dataset_directory) / "usd_m_futures"),
        market="USD_M_FUTURES",
        symbol=symbol,
        now=observed_at,
        minimum_candles=settings.minimum_closed_candles,
        candle_limit=settings.candle_limit,
        futures_builder=build,
        timeframes=timeframes,
    )
    return payload


def run_cycle(settings: Settings, *, observed_at: datetime) -> dict[str, object]:
    """Process one eligible symbol so the daemon remains bounded and resumable."""

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    now = observed_at.astimezone(UTC)
    cache_root = _absolute(settings.market_history_source_cache_directory)
    state_path = _absolute(Path("runtime/state/futures-multitf-latest.json"))
    replay_root = _absolute(Path("runtime/data/datasets/futures/multitf"))
    report_root = _absolute(Path("runtime/artifacts/validation/futures_multitf"))
    tuning_root = _absolute(Path("runtime/artifacts/validation/futures_failure_tuning"))
    end_day = now.date() - timedelta(days=2)
    # Binance publishes the exact public OI history only for a rolling month.
    # Keep a two-day retention margin so the whole replay remains retrievable
    # without fabricating the oldest partial day.
    start_day = end_day - timedelta(days=27)
    window = f"{start_day.isoformat()}_to_{end_day.isoformat()}"
    state = _load_mapping(state_path)
    symbols = _eligible_symbols(cache_root)
    state = _retain_current_universe_state(state, symbols)
    raw_attempted = state.get("attempted_windows", {})
    attempted = (
        {str(key): str(value) for key, value in raw_attempted.items()}
        if isinstance(raw_attempted, Mapping)
        else {}
    )
    raw_completed = state.get("completed_windows", {})
    completed = dict(raw_completed) if isinstance(raw_completed, Mapping) else {}
    raw_retry = state.get("retry_after", {})
    retry_after = dict(raw_retry) if isinstance(raw_retry, Mapping) else {}
    raw_unavailable = state.get("unavailable_windows", {})
    unavailable = (
        {
            str(symbol): str(unavailable_window)
            for symbol, unavailable_window in raw_unavailable.items()
            if isinstance(symbol, str) and isinstance(unavailable_window, str)
        }
        if isinstance(raw_unavailable, Mapping)
        else {}
    )
    raw_tuning_triggers = state.get("completed_tuning_triggers", [])
    completed_tuning_triggers = (
        {
            item
            for item in raw_tuning_triggers
            if isinstance(item, str) and item.startswith("futures-tuning:")
        }
        if isinstance(raw_tuning_triggers, list)
        else set()
    )
    # A 404 from Binance Vision means the immutable archive has not been
    # published for this symbol/window (commonly a newly listed contract).
    # It is not a transient transport failure.  Do not retry it every cycle or
    # let it starve other symbols; reconsider it only when the rolling window
    # advances.
    pending = tuple(
        item
        for item in symbols
        if completed.get(item) != window and unavailable.get(item) != window
    )
    monitor_symbol = _next_symbol(symbols, state.get("monitor_symbol", ""))

    def retry_due(item: str) -> bool:
        try:
            return datetime.fromisoformat(str(retry_after[item])) <= now
        except (KeyError, TypeError, ValueError):
            return True

    symbol = next((item for item in pending if retry_due(item)), None)
    if symbol is None:
        try:
            monitoring = _monitor_futures_symbol(
                settings, Path.cwd(), monitor_symbol, now
            )
        except (OSError, TypeError, ValueError):
            monitoring = {
                "status": "DEGRADED",
                "symbol": monitor_symbol,
                "blockers": ["FUTURES_MONITOR_DATA_OR_DERIVATIVES_UNAVAILABLE"],
                **_SAFE_STATE,
            }
        trigger = (
            _tuning_trigger_from_monitor(monitoring)
            if isinstance(monitoring, Mapping)
            else None
        )
        try:
            tuning = _run_triggered_tuning(
                state=state,
                datasets={},
                replay_root=replay_root,
                artifact_root=tuning_root,
                trigger=trigger,
                completed_trigger_ids=completed_tuning_triggers,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            tuning = {
                "status": "BLOCKED",
                "blockers": ["FUTURES_FAILURE_TUNING_UNAVAILABLE"],
                **_SAFE_STATE,
            }
        payload = {
            "schema_version": "1.0",
            "status": (
                "WAITING_FOR_RETRY"
                if pending
                else (
                    "CURRENT_WITH_SOURCE_GAPS"
                    if any(unavailable.get(item) == window for item in symbols)
                    else "CURRENT"
                )
            ),
            "observed_at": now.isoformat(),
            "window": window,
            "eligible_symbol_count": len(symbols),
            "eligible_symbols": list(symbols),
            "universe_source": RESEARCH_MARKET_UNIVERSE_SOURCE,
            "attempted_symbol_count": sum(
                attempted.get(item) == window for item in symbols
            ),
            "completed_symbol_count": len(symbols) - len(pending),
            "pending_symbol_count": len(pending),
            "blockers": (
                ["FUTURES_MULTITF_RETRY_PENDING"]
                if pending
                else (
                    ["FUTURES_DETAIL_SOURCE_NOT_PUBLISHED"]
                    if any(unavailable.get(item) == window for item in symbols)
                    else []
                )
            ),
            "timeframes": list(FUTURES_MULTITF_TIMEFRAMES),
            "attempted_windows": attempted,
            "completed_windows": completed,
            "retry_after": retry_after,
            "unavailable_windows": unavailable,
            "unavailable_symbol_count": sum(
                unavailable.get(item) == window for item in symbols
            ),
            "monitor_symbol": monitor_symbol,
            "opportunity_monitor": monitoring,
            "failure_tuning": tuning,
            "completed_tuning_triggers": sorted(completed_tuning_triggers)[
                -_MAX_COMPLETED_TUNING_TRIGGERS:
            ],
            **_SAFE_STATE,
        }
        _save(state_path, payload)
        return payload

    datasets: dict[str, RuntimeFuturesReplayDataset] = {}
    artifacts: dict[str, str] = {}
    active_timeframe: str | None = None
    phase = "INGEST"
    learning: dict[str, object] = {"status": "UNAVAILABLE"}
    backtest_trigger: dict[str, object] | None = None
    failure_code: str | None = None
    _save_progress(
        state_path,
        state,
        cycle_started_at=now,
        symbol=symbol,
        phase=phase,
        active_timeframe=active_timeframe,
        artifacts=artifacts,
    )
    try:
        for timeframe in FUTURES_MULTITF_TIMEFRAMES:
            active_timeframe = timeframe
            _save_progress(
                state_path,
                state,
                cycle_started_at=now,
                symbol=symbol,
                phase=phase,
                active_timeframe=active_timeframe,
                artifacts=artifacts,
            )
            synced = BinanceVisionFuturesReplayIngestor.with_persistent_cache(
                replay_root,
                cache_root,
                timeframe=timeframe,
                timeout_seconds=settings.request_timeout_seconds,
            ).sync_range(
                symbol,
                start_day,
                end_day,
                observed_at=now,
            )
            datasets[timeframe] = synced.dataset
            artifacts[timeframe] = synced.artifact_path
        phase = "BACKTEST"
        _save_progress(
            state_path,
            state,
            cycle_started_at=now,
            symbol=symbol,
            phase=phase,
            active_timeframe=active_timeframe,
            artifacts=artifacts,
        )
        report = FuturesMultiTimeframeBacktestRunner(report_root).run(
            datasets,
            created_at=now,
        )
        status = "PROCESSED"
        blocker = None
        report_path: str | None = report.artifact_path
        learning = _learning_projection(report.learning_summary)
        backtest_trigger = _backtest_tuning_trigger(report)
        completed[symbol] = window
        retry_after.pop(symbol, None)
    except MarketHistorySourceUnavailableError:
        status = "DEFERRED"
        blocker = "FUTURES_DETAIL_SOURCE_NOT_PUBLISHED"
        failure_code = blocker
        report_path = None
        unavailable[symbol] = window
        retry_after.pop(symbol, None)
    except (OSError, TypeError, ValueError) as error:
        status = "DEGRADED"
        blocker = _failure_code(error)
        failure_code = blocker
        report_path = None
        retry_after[symbol] = (now + timedelta(minutes=30)).isoformat()
    try:
        monitoring = _monitor_futures_symbol(settings, Path.cwd(), monitor_symbol, now)
    except (OSError, TypeError, ValueError):
        monitoring = {
            "status": "DEGRADED",
            "symbol": monitor_symbol,
            "blockers": ["FUTURES_MONITOR_DATA_OR_DERIVATIVES_UNAVAILABLE"],
            **_SAFE_STATE,
        }
    monitor_trigger = (
        _tuning_trigger_from_monitor(monitoring)
        if isinstance(monitoring, Mapping)
        else None
    )
    try:
        tuning = _run_triggered_tuning(
            state=state,
            datasets=datasets,
            replay_root=replay_root,
            artifact_root=tuning_root,
            trigger=monitor_trigger or backtest_trigger,
            completed_trigger_ids=completed_tuning_triggers,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        tuning = {
            "status": "BLOCKED",
            "blockers": ["FUTURES_FAILURE_TUNING_UNAVAILABLE"],
            **_SAFE_STATE,
        }
    attempted[symbol] = window
    payload = {
        "schema_version": "1.0",
        "status": status,
        "observed_at": now.isoformat(),
        "cycle_started_at": now.isoformat(),
        "progress_at": datetime.now(UTC).isoformat(),
        "window": window,
        "active_symbol": symbol,
        "active_timeframe": active_timeframe,
        "phase": phase,
        "eligible_symbol_count": len(symbols),
        "eligible_symbols": list(symbols),
        "universe_source": RESEARCH_MARKET_UNIVERSE_SOURCE,
        "attempted_symbol_count": sum(
            attempted.get(item) == window for item in symbols
        ),
        "timeframes": list(FUTURES_MULTITF_TIMEFRAMES),
        "completed_symbol_count": sum(
            completed.get(item) == window for item in symbols
        ),
        "pending_symbol_count": sum(
            completed.get(item) != window and unavailable.get(item) != window
            for item in symbols
        ),
        "dataset_artifacts": artifacts,
        "backtest_report_path": report_path,
        "learning": learning,
        "monitor_symbol": monitor_symbol,
        "opportunity_monitor": monitoring,
        "failure_tuning": tuning,
        "completed_tuning_triggers": sorted(completed_tuning_triggers)[
            -_MAX_COMPLETED_TUNING_TRIGGERS:
        ],
        "blockers": [] if blocker is None else [blocker],
        "failure_code": failure_code,
        "attempted_windows": attempted,
        "completed_windows": completed,
        "retry_after": retry_after,
        "unavailable_windows": unavailable,
        "unavailable_symbol_count": sum(
            unavailable.get(item) == window for item in symbols
        ),
        **_SAFE_STATE,
    }
    _save(state_path, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("once", "daemon"))
    parser.add_argument("--max-cycles", type=int)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.max_cycles is not None and parsed.max_cycles < 1:
        raise ValueError("max-cycles must be positive")
    settings = Settings()
    lock_path = _absolute(Path("runtime/state/futures-multitf.lock"))
    cycles = 1 if parsed.command == "once" else parsed.max_cycles
    completed = 0
    with SingleInstanceLease(lock_path):
        while cycles is None or completed < cycles:
            payload = run_cycle(settings, observed_at=datetime.now(UTC))
            print(json.dumps(to_primitive(payload), sort_keys=True))
            completed += 1
            if cycles is None or completed < cycles:
                time.sleep(300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
