"""Scoped orchestration of the existing continuous DataCore collector.

No scheduler, service, alternate archive, or trading eligibility is created.
"""

import errno
import json
import os
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from ai4binance.core.errors import ExchangeError, ExchangeRateLimitError
from ai4binance.data.acquisition_profile import (
    PROFILE_ID,
    PROFILE_TIMEFRAMES,
    SAFE_STATE,
    acquisition_window,
    content_digest,
    native_schedule,
    previous_calendar_month,
    stream_health,
    validate_native_rows,
)
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_continuous import ContinuousMarketHistory
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.data.weekly_volume import (
    ScopedRetryPolicy,
    active_shared_circuit,
    load_evidence,
    record_shared_cooldown,
    save_evidence,
)
from ai4binance.exchange.client import JsonTransport
from ai4binance.ops.runtime import SingleInstanceLease


def verified_selection(payload: Mapping[str, object]) -> list[dict[str, object]]:
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"selection_version", "observed_at"}
    }
    selected = payload.get("selected")
    if (
        payload.get("status") != "VERIFIED"
        or payload.get("selection_version") != content_digest(body)
        or not isinstance(selected, list)
        or len(selected) != 5
    ):
        raise ValueError("a genuine verified frozen TOP5 selection is required")
    if (
        payload.get("execution_allowed") is not False
        or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("selection cannot confer execution authority")
    items = cast(list[dict[str, object]], selected)
    if len({str(item["asset_id"]) for item in items}) != 5:
        raise ValueError("selected asset identities must be unique")
    return items


def profile_root(collector: ContinuousMarketHistory) -> Path:
    return collector.history.source_cache.root / "profiles" / "top5-1000-month"


def profile_health(
    collector: ContinuousMarketHistory, *, cutoff: datetime
) -> dict[str, object]:
    selection = collector.scoped_selection
    if selection is None:
        raise ValueError("frozen selection is missing")
    assets = verified_selection(selection)
    rows: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    for asset in assets:
        for market in ("spot", "usd_m_futures"):
            symbol = str(asset["spot_symbol" if market == "spot" else "futures_symbol"])
            scoped_rows = [
                _stream_health(collector, market, symbol, timeframe, cutoff)
                for timeframe in PROFILE_TIMEFRAMES
            ]
            rows.extend(
                [
                    {key: value for key, value in row.items() if key != "candles"}
                    for row in scoped_rows
                ]
            )
            snapshot = {
                "profile_id": PROFILE_ID,
                "selection_version": selection["selection_version"],
                "asset_id": asset["asset_id"],
                "market": market,
                "symbol": symbol,
                "causal_cutoff": cutoff.isoformat(),
                "streams": scoped_rows,
                **SAFE_STATE,
            }
            digest = content_digest(snapshot)
            path = profile_root(collector) / "snapshots" / f"{digest}.json"
            if not path.exists():
                save_evidence(path, snapshot)
            elif content_digest(load_evidence(path)) != digest:
                raise ValueError("immutable profile snapshot integrity failed")
            snapshots.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "semantic_sha256": digest,
                    "artifact_path": str(path),
                }
            )
    report: dict[str, object] = {
        "profile_id": PROFILE_ID,
        "target_closed_bars": 1000,
        "timeframes": list(PROFILE_TIMEFRAMES),
        "futures_window_interpretation": "ROLLING_ONE_CALENDAR_MONTH_MONTH_END_CLAMPED",
        "selection_version": selection["selection_version"],
        "ranking_start_utc": selection["ranking_start_utc"],
        "ranking_end_utc": selection["ranking_end_utc"],
        "causal_cutoff": cutoff.isoformat(),
        "blockers": ["TOP5_NATIVE_GRID_INCOMPLETE"]
        if any(not str(row["status"]).startswith("DATA_READY") for row in rows)
        else [],
        "status": "DATA_READY"
        if all(str(row["status"]).startswith("DATA_READY") for row in rows)
        else "PARTIAL",
        "streams": rows,
        "snapshots": snapshots,
        "loaded_service_revision": "NOT_VERIFIED",
        "futures_enrichment_status": "NOT_VERIFIED",
        **SAFE_STATE,
    }
    save_evidence(profile_root(collector) / "health-latest.json", report)
    return report


def _stream_health(
    collector: ContinuousMarketHistory,
    market: str,
    symbol: str,
    timeframe: str,
    cutoff: datetime,
) -> dict[str, object]:
    window = acquisition_window(market, timeframe, cutoff)
    archive = ParquetOHLCVArchive(collector.history.archive_root / market)
    required = (collector.required_candles_by_timeframe or {}).get(
        timeframe, collector.minimum_candles or 200
    )
    try:
        manifest = archive.manifest(symbol, timeframe)
        duration = timeframe_duration(timeframe)
        combined = archive.read_window(
            symbol,
            timeframe,
            start_at=min(window.start, window.end - required * duration),
            end_at=window.end - duration,
        )
        candles = tuple(item for item in combined if item.timestamp >= window.start)
        warmup = tuple(
            item
            for item in combined
            if item.timestamp >= window.end - required * duration
        )
        warmup_verified = [item.timestamp for item in warmup] == [
            window.end - (required - index) * duration for index in range(required)
        ]
        if archive.manifest(
            symbol, timeframe
        ) != manifest or not manifest.source.startswith(
            ("BINANCE_PUBLIC_REST_", "BINANCE_VISION_")
        ):
            raise ValueError("profile archive lineage changed or is unapproved")
        result = stream_health(
            window,
            [candle.timestamp for candle in candles],
            strategy_required_bars=required,
            verified_archive_count=manifest.row_count,
            lineage={
                "dataset_sha256": manifest.sha256,
                "source": manifest.source,
                "generated_at": manifest.generated_at,
                "checksum_status": "LOCAL_PARQUET_HASH_VERIFIED",
            },
            warmup_verified=warmup_verified,
        )
        result["candles"] = [
            {
                "timestamp": candle.timestamp.isoformat(),
                "open": str(candle.open),
                "high": str(candle.high),
                "low": str(candle.low),
                "close": str(candle.close),
                "base_volume": str(candle.volume),
            }
            for candle in candles
        ]
    except (OSError, ValueError) as error:
        result = stream_health(
            window,
            [],
            strategy_required_bars=required,
            verified_archive_count=0,
            lineage={
                "status": "UNAVAILABLE_OR_INVALID",
                "reason": type(error).__name__,
            },
        )
    retry = load_evidence(
        profile_root(collector) / "retry" / f"{market}-{symbol}-klines-{timeframe}.json"
    )
    return {
        "symbol": symbol,
        **result,
        "last_useful_update": retry.get("last_useful_update", "NOT_VERIFIED"),
        "failure_reason": retry.get("last_failure_reason")
        or ("NATIVE_GRID_INCOMPLETE" if result["missing_count"] else None),
        "next_retry_at": retry.get("next_retry_at"),
        "job_state": retry.get("status", "NOT_STARTED_BY_SCOPED_WRITER"),
        "shared_source_circuit": load_evidence(
            profile_root(collector) / "retry" / f"{market}-circuit.json"
        ),
    }


def sync_scoped_history(
    collector: ContinuousMarketHistory, *, cutoff: datetime
) -> dict[str, object]:
    """Use the existing canonical lease; never remove an existing foreign lease."""
    lock = collector.history.state_path.with_suffix(".lock")
    if lock.exists():
        if not _owns_lease(lock):
            return {
                "status": "BLOCKED",
                "reason": "CANONICAL_WRITER_BUSY",
                **SAFE_STATE,
            }
        return _sync_owned(collector, cutoff=cutoff)
    with SingleInstanceLease(lock):
        return _sync_owned(collector, cutoff=cutoff)


def _owns_lease(path: Path) -> bool:
    try:
        pid, _ = SingleInstanceLease._read_lock_owner(path)
        return pid == os.getpid() and SingleInstanceLease.lock_owner_is_active(path)
    except RuntimeError:
        return False


def _sync_owned(
    collector: ContinuousMarketHistory, *, cutoff: datetime
) -> dict[str, object]:
    """Give every due asset/TF a bounded turn, with tails before backfill."""
    if collector.pages_per_stream != 1 or collector.archives_per_stream != 1:
        raise ValueError("scoped profile requires one bounded recovery chunk per turn")
    if collector.scoped_clock_resolver is not None:
        cutoff = collector.scoped_clock_resolver(cutoff)
    health = profile_health(collector, cutoff=cutoff)
    rows = cast(list[dict[str, object]], health["streams"])
    collector.scoped_window_starts = {
        (market, tf): acquisition_window(market, tf, cutoff).start
        for market in ("spot", "usd_m_futures")
        for tf in PROFILE_TIMEFRAMES
    }
    # Each timeframe visits all assets/markets before the next timeframe.
    rows.sort(
        key=lambda row: (
            PROFILE_TIMEFRAMES.index(str(row["timeframe"])),
            str(row["symbol"]),
            str(row["market"]),
        )
    )
    policy = ScopedRetryPolicy(**dict(collector.scoped_retry_settings or {}))
    results: list[dict[str, object]] = []
    for row in rows:
        results.append(_scheduled_turn(collector, row, cutoff, policy))
    enrichment = _enrichment_turns(collector, cutoff, policy)
    report = profile_health(collector, cutoff=cutoff)
    jobs = [_job(collector, row) for row in rows]
    wake = min(datetime.fromisoformat(str(job["next_due_at"])) for job in jobs)
    report.update(
        results=results,
        collector_liveness="PASS_FINISHED",
        useful_progress_count=sum(item["status"] == "PROGRESS" for item in results),
        bounded_backlog=len(rows) + len(enrichment),
        native_stream_count=len(rows),
        enrichment_stream_count=len(enrichment),
        futures_enrichment_results=enrichment,
        futures_enrichment_status="PARTIAL_REQUIRED_CONSUMERS_MUST_VERIFY_INPUTS",
        stream_jobs=jobs,
        clock_status="OFFICIAL_CLOCK_VERIFIED"
        if collector.scoped_clock_verified
        else "CALLER_CUTOFF_NOT_RUNTIME_CLOCK_EVIDENCE",
        local_next_wakeup_at=(
            wake - timedelta(seconds=collector.scoped_clock_offset_seconds)
        ).isoformat(),
    )
    save_evidence(profile_root(collector) / "health-latest.json", report)
    save_evidence(
        collector.history.state_path,
        {
            **report,
            "schema_version": "2.0",
            "observed_at": cutoff.isoformat(),
            "profile_data_status": report["status"],
            "status": "DEGRADED" if report["blockers"] else "READY",
            "spot_universe_count": 5,
            "futures_universe_count": 5,
            "coin_m_universe_count": 0,
        },
    )
    return report


def _scheduled_turn(
    collector: ContinuousMarketHistory,
    row: dict[str, object],
    cutoff: datetime,
    policy: ScopedRetryPolicy,
) -> dict[str, object]:
    state_path = _job_path(collector, row)
    _settle_effect(collector, row, cutoff)
    _settle_archive_effect(collector, row)
    state = _job(collector, row)
    schedule = native_schedule(
        cutoff,
        str(row["timeframe"]),
        arrival_grace_seconds=collector.scoped_arrival_grace_seconds,
    )
    due = datetime.fromisoformat(
        str(state.get("next_due_at", schedule["arrival_deadline"]))
    )
    actual_run = collector.clock()
    lag_clock = (
        actual_run + timedelta(seconds=collector.scoped_clock_offset_seconds)
        if collector.scoped_clock_verified
        else cutoff
    )
    state.update(
        schedule, scheduling_lag_seconds=max(0.0, (lag_clock - due).total_seconds())
    )
    if str(row["status"]).startswith("DATA_READY"):
        state.update(next_due_at=schedule["next_native_due_at"], job_status="CURRENT")
        save_evidence(state_path, state)
        return {
            "market": row["market"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "status": "CURRENT",
        }
    save_evidence(state_path, state)
    retained = _collect_turn(collector, row, cutoff, policy, allow_fetch=False)
    if retained["status"] == "PROGRESS":
        state = _job(collector, row)
        state.update(
            last_actual_run_at=actual_run.isoformat(),
            next_due_at=(cutoff + timedelta(seconds=30)).isoformat(),
            job_status="PROGRESS",
        )
        save_evidence(state_path, state)
        return retained
    eligible = datetime.fromisoformat(str(schedule["acquisition_closed_boundary"]))
    missing = cast(list[str], row.get("missing_open_times", []))
    older_gap = any(datetime.fromisoformat(stamp) < eligible for stamp in missing)
    if cutoff < due or (
        cutoff < datetime.fromisoformat(str(schedule["arrival_deadline"]))
        and not older_gap
    ):
        waiting_status = (
            "DEFERRED"
            if state.get("job_status") in {"BLOCKED", "DEFERRED", "DEGRADED_WAIT"}
            else "WAITING_DUE"
        )
        state.update(
            next_due_at=schedule["arrival_deadline"]
            if not older_gap
            else due.isoformat(),
            job_status=waiting_status,
        )
        save_evidence(state_path, state)
        return {
            "market": row["market"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "status": waiting_status,
        }
    state.update(
        last_actual_run_at=actual_run.isoformat(),
        last_scheduled_cutoff_at=cutoff.isoformat(),
        job_status="RUNNING",
    )
    save_evidence(state_path, state)
    result = _collect_turn(collector, row, eligible, policy)
    state = _job(collector, row)
    retry = load_evidence(
        profile_root(collector)
        / "retry"
        / f"{row['market']}-{row['symbol']}-klines-{row['timeframe']}.json"
    )
    circuit = active_shared_circuit(profile_root(collector), str(row["market"]), cutoff)
    wake = cutoff + timedelta(seconds=30)
    for deferred in (retry, circuit):
        if deferred.get("next_retry_at"):
            wake = max(wake, datetime.fromisoformat(str(deferred["next_retry_at"])))
    state.update(
        next_due_at=wake.isoformat(),
        job_status=result["status"],
        retry_state=retry,
        shared_source_circuit=circuit,
    )
    save_evidence(state_path, state)
    return result


def _collect_turn(
    collector: ContinuousMarketHistory,
    row: dict[str, object],
    cutoff: datetime,
    policy: ScopedRetryPolicy,
    *,
    allow_fetch: bool = True,
) -> dict[str, object]:
    lock = collector.history.state_path.with_suffix(".lock")
    if lock.exists() and not _owns_lease(lock):
        return {"status": "BLOCKED", "reason": "CANONICAL_WRITER_BUSY", **SAFE_STATE}
    if not lock.exists():
        with SingleInstanceLease(lock):
            return _collect_turn(
                collector, row, cutoff, policy, allow_fetch=allow_fetch
            )
    kind = str(row.get("kind", "klines"))
    if kind == "klines":
        stream_lock = _job_path(collector, row).with_suffix(".lock")
        if stream_lock.exists():
            return {"status": "DEFERRED", "reason": "STREAM_OWNER_BUSY", **SAFE_STATE}
        with SingleInstanceLease(stream_lock):
            return _collect_owned_turn(
                collector, row, cutoff, policy, allow_fetch=allow_fetch
            )
    return _collect_owned_turn(collector, row, cutoff, policy, allow_fetch=allow_fetch)


def _collect_owned_turn(
    collector: ContinuousMarketHistory,
    row: dict[str, object],
    cutoff: datetime,
    policy: ScopedRetryPolicy,
    *,
    allow_fetch: bool = True,
) -> dict[str, object]:
    market, symbol, timeframe = (
        str(row[key]) for key in ("market", "symbol", "timeframe")
    )
    now = collector.clock()
    kind = str(row.get("kind", "klines"))
    retry_path = (
        profile_root(collector) / "retry" / f"{market}-{symbol}-{kind}-{timeframe}.json"
    )
    if (
        kind == "klines"
        and (replayed_result := _replay_turn(collector, row, cutoff, retry_path))
        is not None
    ):
        return replayed_result
    if not allow_fetch:
        return {"status": "NO_RETAINED_PROGRESS"}
    circuit = active_shared_circuit(profile_root(collector), market, now)
    if circuit:
        return {
            **load_evidence(retry_path),
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "DEGRADED_WAIT",
            **circuit,
        }
    if not policy.reserve(retry_path, now):
        return {
            **load_evidence(retry_path),
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "DEFERRED",
        }
    transport: JsonTransport = collector.spot if market == "spot" else collector.futures
    if kind == "klines":
        transport = _ReceiptTransport(collector, row, transport)
    collector.scoped_tail_priority = not bool(row.get("tail_ready"))
    if kind == "klines":
        _begin_archive_effect(collector, row)
    try:
        before_sha = _turn_revision(collector, market, symbol, kind, timeframe)
    except ValueError:
        return {
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "BLOCKED",
            "reason": "DATASET_INTEGRITY_FAILURE",
        }
    result = _bounded_acquisition(
        collector, market, symbol, kind, timeframe, transport, cutoff
    )
    after_sha = _turn_revision(collector, market, symbol, kind, timeframe)
    if kind == "klines":
        _settle_effect(collector, row, cutoff)
        _settle_archive_effect(collector, row)
    progress = (
        result.get("status") != "BLOCKED"
        and after_sha is not None
        and after_sha != before_sha
    )
    result = _complete_retry_turn(policy, retry_path, now, result, progress)
    return {
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "kind": kind,
        **result,
        "retry_state": load_evidence(retry_path),
    }


def _bounded_acquisition(
    collector: ContinuousMarketHistory,
    market: str,
    symbol: str,
    kind: str,
    timeframe: str,
    transport: JsonTransport,
    cutoff: datetime,
) -> dict[str, object]:
    try:
        replayed = _merge_retained_pages(
            collector, market, symbol, kind, timeframe, cutoff
        )
        result = (
            {"status": "BACKFILLING", "source": "RETAINED_VERIFIED_PAGE"}
            if replayed
            else (
                collector._details(symbol, kind, cutoff, market=market)
                if kind in {"funding", "open_interest"}
                else collector._candles(
                    market, symbol, kind, transport, cutoff, timeframe=timeframe
                )
            )
        )
    except ExchangeRateLimitError as error:
        record_shared_cooldown(profile_root(collector), market, error)
        result = {"status": "BLOCKED", "reason": "SHARED_SOURCE_RATE_LIMIT"}
    except OSError as error:
        if error.errno in {errno.ENOSPC, errno.EROFS, errno.EACCES}:
            raise
        result = {"status": "BLOCKED", "reason": "SOURCE_IO_UNAVAILABLE"}
    except (ExchangeError, ValueError, ArithmeticError) as error:
        result = {
            "status": "BLOCKED",
            "reason": collector._safe_stream_failure_reason(error),
        }
    return dict(result)


def _replay_turn(
    collector: ContinuousMarketHistory,
    row: dict[str, object],
    cutoff: datetime,
    retry_path: Path,
) -> dict[str, object] | None:
    market, symbol, timeframe = (
        str(row[key]) for key in ("market", "symbol", "timeframe")
    )
    try:
        _settle_archive_effect(collector, row)
        before = _turn_revision(collector, market, symbol, "klines", timeframe)
        if _merge_retained_pages(
            collector, market, symbol, "klines", timeframe, cutoff
        ):
            after = _turn_revision(collector, market, symbol, "klines", timeframe)
            return {
                "market": market,
                "symbol": symbol,
                "timeframe": timeframe,
                "kind": "klines",
                "status": "PROGRESS" if before != after else "CURRENT",
                "source": "RETAINED_VERIFIED_PAGE",
                "retry_state": load_evidence(retry_path),
            }
    except ValueError:
        return {
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "BLOCKED",
            "reason": "RETAINED_PAGE_INTEGRITY_FAILURE",
        }
    return None


def _complete_retry_turn(
    policy: ScopedRetryPolicy,
    retry_path: Path,
    now: datetime,
    result: Mapping[str, object],
    progress: bool,
) -> dict[str, object]:
    if progress:
        policy.succeed(retry_path, now)
        result = {**result, "status": "PROGRESS"}
    elif (
        result.get("status") in {"CURRENT", "TAIL_CURRENT"}
        or result.get("reason") == "INSUFFICIENT_CANDLES"
    ):
        policy.succeed(retry_path, now, useful_progress=False)
    else:
        save_evidence(
            retry_path,
            {
                **load_evidence(retry_path),
                "status": str(result.get("status", "BLOCKED")),
                "last_failure_reason": result.get("reason", "NO_VERIFIED_DATA_ADVANCE"),
                **SAFE_STATE,
            },
        )
    return dict(result)


def _turn_revision(
    collector: ContinuousMarketHistory,
    market: str,
    symbol: str,
    kind: str,
    timeframe: str,
) -> str | None:
    if kind in {"funding", "open_interest"}:
        path = (
            collector.history.archive_root
            / market
            / symbol
            / "details"
            / kind
            / "profiles"
            / "top5-1000-month"
            / "collection-progress.json"
        )
        state = load_evidence(path)
        verified_cursor = state.get("verified_source_next_at")
        return str(verified_cursor) if verified_cursor is not None else None
    suffix = {"klines": "", "markPriceKlines": "_mark", "indexPriceKlines": "_index"}[
        kind
    ]
    archive = ParquetOHLCVArchive(collector.history.archive_root / (market + suffix))
    try:
        return archive.manifest(symbol, timeframe).sha256
    except FileNotFoundError:
        return None


_COUNTERS = (
    "get_attempts",
    "completed_responses",
    "failed_requests",
    "unknown_request_outcomes",
    "requested_missing_bars",
    "retained_page_reuses",
    "response_rows",
    "duplicate_overlap_rows",
    "canonical_inserts",
    "late_responses",
)


def _job_path(collector: ContinuousMarketHistory, row: Mapping[str, object]) -> Path:
    market, symbol, timeframe = (
        str(row[key]) for key in ("market", "symbol", "timeframe")
    )
    if market not in {"spot", "usd_m_futures"} or timeframe not in PROFILE_TIMEFRAMES:
        raise ValueError("stream job identity is outside the profile")
    ParquetOHLCVArchive._validate_identity(symbol, timeframe, "BINANCE_PUBLIC_REST")
    return (
        profile_root(collector) / "jobs" / f"{market}-{symbol}-klines-{timeframe}.json"
    )


def _job(
    collector: ContinuousMarketHistory, row: Mapping[str, object]
) -> dict[str, object]:
    state = load_evidence(_job_path(collector, row))
    identity = {key: row[key] for key in ("market", "symbol", "timeframe")}
    if state and any(state.get(key) != value for key, value in identity.items()):
        raise ValueError("persisted stream job binding mismatch")
    if state and state.get("selection_version") != (
        collector.scoped_selection or {}
    ).get("selection_version"):
        raise ValueError("persisted stream job selection mismatch")
    return state or {
        **identity,
        "selection_version": (collector.scoped_selection or {}).get(
            "selection_version"
        ),
        "counters": dict.fromkeys(_COUNTERS, 0),
        **SAFE_STATE,
    }


def _increment(state: dict[str, object], key: str, amount: int = 1) -> None:
    counters = cast(dict[str, int], state["counters"])
    counters[key] = counters.get(key, 0) + amount


def _archive_count(
    collector: ContinuousMarketHistory, row: Mapping[str, object]
) -> int:
    archive = ParquetOHLCVArchive(collector.history.archive_root / str(row["market"]))
    try:
        manifest = archive.manifest(str(row["symbol"]), str(row["timeframe"]))
        if not manifest.source.startswith(("BINANCE_PUBLIC_REST_", "BINANCE_VISION_")):
            raise ValueError("canonical telemetry source is unapproved")
        return manifest.row_count
    except FileNotFoundError:
        return 0


def _begin_archive_effect(
    collector: ContinuousMarketHistory, row: Mapping[str, object]
) -> None:
    state = _job(collector, row)
    state["canonical_effect_checkpoint"] = {
        "row_count_before": _archive_count(collector, row),
        "inserts_before": cast(dict[str, int], state["counters"])["canonical_inserts"],
    }
    save_evidence(_job_path(collector, row), state)


def _settle_archive_effect(
    collector: ContinuousMarketHistory, row: Mapping[str, object]
) -> None:
    state = _job(collector, row)
    checkpoint = cast(dict[str, int], state.get("canonical_effect_checkpoint", {}))
    if not checkpoint:
        return
    if state.get("active_request"):
        return  # Its precise receipt must settle before aggregate archive effects.
    delta = _archive_count(collector, row) - checkpoint["row_count_before"]
    counted = (
        cast(dict[str, int], state["counters"])["canonical_inserts"]
        - checkpoint["inserts_before"]
    )
    if delta < counted:
        raise ValueError("canonical archive effect contradicts durable receipt inserts")
    _increment(state, "canonical_inserts", delta - counted)
    if delta:
        state["last_useful_commit_at"] = collector.clock().isoformat()
    state.pop("canonical_effect_checkpoint", None)
    save_evidence(_job_path(collector, row), state)


def _canonical_page(
    collector: ContinuousMarketHistory,
    row: Mapping[str, object],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    archive = ParquetOHLCVArchive(collector.history.archive_root / str(row["market"]))
    try:
        manifest = archive.manifest(str(row["symbol"]), str(row["timeframe"]))
    except FileNotFoundError:
        return {}
    if not manifest.source.startswith(("BINANCE_PUBLIC_REST_", "BINANCE_VISION_")):
        raise ValueError("canonical source is unapproved")
    candles = archive.read_window(
        str(row["symbol"]),
        str(row["timeframe"]),
        start_at=start,
        end_at=end - timeframe_duration(str(row["timeframe"])),
    )
    if archive.manifest(str(row["symbol"]), str(row["timeframe"])) != manifest:
        raise ValueError("canonical revision changed during receipt verification")
    return {item.timestamp.isoformat(): item for item in candles}


class _ReceiptTransport:
    """Durably stage a bounded decoded GET before the canonical adapter publishes it."""

    def __init__(
        self,
        collector: ContinuousMarketHistory,
        row: Mapping[str, object],
        transport: JsonTransport,
    ) -> None:
        self.collector, self.row, self.transport = collector, row, transport
        self.deadline = time.monotonic() + collector.scoped_turn_deadline_seconds
        self.started = self.deadline - collector.scoped_turn_deadline_seconds
        self.called = False

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        collector, row = self.collector, self.row
        query = dict(params or {})
        expected_path = (
            "/api/v3/klines" if row["market"] == "spot" else "/fapi/v1/klines"
        )
        if (
            self.called
            or path != expected_path
            or query.get("symbol") != row["symbol"]
            or query.get("interval") != row["timeframe"]
        ):
            raise ValueError("native turn permits one correctly bound GET")
        self.called = True
        start = datetime.fromtimestamp(int(query["startTime"]) / 1000, UTC)
        end = datetime.fromtimestamp((int(query["endTime"]) + 1) / 1000, UTC)
        limit = int(query["limit"])
        duration = timeframe_duration(str(row["timeframe"]))
        if not 1 <= limit <= 499 or end - start != limit * duration:
            raise ValueError("native GET must request exactly its bounded missing grid")
        before = _canonical_page(collector, row, start, end)
        if before:
            raise ValueError("native GET plan overlaps verified canonical bars")
        state = _job(collector, row)
        if state.get("active_request"):
            raise ValueError("durable response must be reconciled before another GET")
        request_id = uuid4().hex
        state["active_request"] = {
            "request_id": request_id,
            "phase": "ATTEMPT_RESERVED",
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        _increment(state, "get_attempts")
        _increment(state, "requested_missing_bars", limit)
        save_evidence(_job_path(collector, row), state)
        transport_started = time.monotonic()
        try:
            payload = self.transport.get_json(path, query)
        except ExchangeError, OSError, ValueError, ArithmeticError:
            _increment(state, "failed_requests")
            state.pop("active_request", None)
            save_evidence(_job_path(collector, row), state)
            raise
        return self._stage_response(
            payload,
            path,
            query,
            state,
            request_id,
            start,
            end,
            before,
            transport_started,
        )

    def _stage_response(
        self,
        payload: object,
        path: str,
        query: dict[str, str | int],
        state: dict[str, object],
        request_id: str,
        start: datetime,
        end: datetime,
        before: dict[str, object],
        transport_started: float,
    ) -> object:
        collector, row = self.collector, self.row
        # Persist completion before parsing; a malformed response still completed.
        _increment(state, "completed_responses")
        finished = time.monotonic()
        state["last_request_latency_seconds"] = max(0.0, finished - transport_started)
        state["last_turn_elapsed_seconds"] = max(0.0, finished - self.started)
        state["latency_scope"] = "TRANSPORT_CALL_INCLUDES_RATE_BUDGET_WAIT"
        cast(dict[str, object], state["active_request"])["phase"] = "RESPONSE_RECEIVED"
        save_evidence(_job_path(collector, row), state)
        try:
            rows = validate_native_rows(
                payload, start=start, end=end, timeframe=str(row["timeframe"])
            )
        except ValueError, ArithmeticError:
            state.pop("active_request", None)
            save_evidence(_job_path(collector, row), state)
            raise
        packet: dict[str, object] = {
            "source": path,
            **{key: row[key] for key in ("market", "symbol", "timeframe")},
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": rows,
            "request_params": query,
            "selection_version": (collector.scoped_selection or {})[
                "selection_version"
            ],
            "request_id": request_id,
            "observed_at": collector.clock().isoformat(),
            "hash_scope": "LOCAL_DECODED_JSON_NOT_EXCHANGE_CHECKSUM",
            **SAFE_STATE,
        }
        host = (
            "https://api.binance.com"
            if row["market"] == "spot"
            else "https://fapi.binance.com"
        )
        url = host + path + "?" + urlencode(sorted(query.items()))
        wire = load_evidence(
            profile_root(collector)
            / "responses"
            / f"{sha256(url.encode()).hexdigest()}.json"
        )
        if wire.get("source_url") == url:
            packet["wire_receipt"] = wire
        elif collector.scoped_clock_verified:
            raise ValueError("activated collection requires an actual source receipt")
        packet["content_sha256"] = content_digest(packet)
        pending = (
            profile_root(collector)
            / "pending"
            / f"{row['market']}-{row['symbol']}-{row['timeframe']}"
            / f"{request_id}.json"
        )
        save_evidence(pending, packet)
        _increment(state, "response_rows", len(rows))
        state["active_request"] = {
            "request_id": request_id,
            "phase": "PUBLISH_PENDING",
            "packet_path": str(pending),
            "before_open_times": list(before),
        }
        state["deferred_publish_rows"] = len(rows)
        save_evidence(_job_path(collector, row), state)
        if (
            float(cast(float, state["last_turn_elapsed_seconds"]))
            > collector.scoped_turn_deadline_seconds
        ):
            _increment(state, "late_responses")
            save_evidence(_job_path(collector, row), state)
            raise ValueError(
                "bounded GET completed after the turn deadline; response retained"
            )
        return payload


def _settle_effect(
    collector: ContinuousMarketHistory, row: Mapping[str, object], cutoff: datetime
) -> None:
    state = _job(collector, row)
    active = cast(dict[str, object], state.get("active_request", {}))
    if not active:
        return
    if active.get("phase") != "PUBLISH_PENDING":
        if re.fullmatch(r"[0-9a-f]{32}", str(active.get("request_id", ""))) is None:
            raise ValueError("pending request identity is invalid")
        pending = (
            profile_root(collector)
            / "pending"
            / f"{row['market']}-{row['symbol']}-{row['timeframe']}"
            / f"{active['request_id']}.json"
        )
        if pending.exists():
            packet = load_evidence(pending)
            rows = _validate_packet(collector, row, packet, cutoff)
            _increment(state, "response_rows", len(rows))
            state["active_request"] = {
                "phase": "PUBLISH_PENDING",
                "packet_path": str(pending),
                "before_open_times": [],
            }
            state["deferred_publish_rows"] = len(rows)
            save_evidence(_job_path(collector, row), state)
            _settle_effect(collector, row, cutoff)
            return
        # A crash before a durable packet has an unknown network outcome.
        if active.get("phase") == "ATTEMPT_RESERVED":
            _increment(state, "unknown_request_outcomes")
        state.pop("active_request", None)
        save_evidence(_job_path(collector, row), state)
        return
    packet_path = Path(str(active["packet_path"]))
    directory = (
        profile_root(collector)
        / "pending"
        / f"{row['market']}-{row['symbol']}-{row['timeframe']}"
    )
    if (
        packet_path.resolve().parent != directory.resolve()
        or packet_path.suffix != ".json"
    ):
        raise ValueError("pending receipt path escapes its stream boundary")
    packet = load_evidence(packet_path)
    rows = _validate_packet(collector, row, packet, cutoff)
    start, end = (datetime.fromisoformat(str(packet[key])) for key in ("start", "end"))
    candles = collector._parse_rows(
        cast(list[object], rows),
        start,
        end,
        interval=timeframe_duration(str(row["timeframe"])),
    )
    actual = _canonical_page(collector, row, start, end)
    if any(actual.get(item.timestamp.isoformat()) != item for item in candles):
        return
    previous = cast(list[str], active.get("before_open_times", []))
    inserts = sum(item.timestamp.isoformat() not in previous for item in candles)
    _increment(state, "canonical_inserts", inserts)
    _increment(state, "duplicate_overlap_rows", len(candles) - inserts)
    if inserts:
        state["last_useful_commit_at"] = collector.clock().isoformat()
    state.update(last_applied_receipt=packet["content_sha256"], deferred_publish_rows=0)
    state.pop("active_request", None)
    save_evidence(_job_path(collector, row), state)


def _validate_packet(
    collector: ContinuousMarketHistory,
    row: Mapping[str, object],
    packet: Mapping[str, object],
    cutoff: datetime,
) -> list[list[str]]:
    binding = {key: value for key, value in packet.items() if key != "content_sha256"}
    if (
        packet.get("content_sha256") != content_digest(binding)
        or any(packet.get(key) != row[key] for key in ("market", "symbol", "timeframe"))
        or packet.get("selection_version")
        != (collector.scoped_selection or {}).get("selection_version")
    ):
        raise ValueError("retained native page binding mismatch")
    start, end = (datetime.fromisoformat(str(packet[key])) for key in ("start", "end"))
    source = "/api/v3/klines" if row["market"] == "spot" else "/fapi/v1/klines"
    if (
        start.utcoffset() is None
        or end.utcoffset() is None
        or end > cutoff
        or not start < end
        or packet.get("source") != source
    ):
        raise ValueError("retained native page exceeds its causal or source scope")
    rows = validate_native_rows(
        packet["rows"], start=start, end=end, timeframe=str(row["timeframe"])
    )
    if packet.get("hash_scope") == "LOCAL_DECODED_JSON_NOT_EXCHANGE_CHECKSUM":
        if collector.scoped_clock_verified and not packet.get("wire_receipt"):
            raise ValueError("activated replay requires an actual source receipt")
        query = cast(dict[str, str | int], packet.get("request_params", {}))
        if query != {
            "symbol": str(row["symbol"]),
            "interval": str(row["timeframe"]),
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000) - 1,
            "limit": int((end - start) / timeframe_duration(str(row["timeframe"]))),
        }:
            raise ValueError("retained decoded request binding mismatch")
        if packet.get("wire_receipt"):
            _validate_wire_receipt(collector, row, packet, start, end, query, rows)
        return rows
    digest = str(packet.get("raw_response_sha256"))
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("retained response hash is invalid")
    host = (
        "https://api.binance.com"
        if row["market"] == "spot"
        else "https://fapi.binance.com"
    )
    params: dict[str, str | int] = {
        "symbol": str(row["symbol"]),
        "interval": str(row["timeframe"]),
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000) - 1,
        "limit": int(cast(int, packet.get("retained_request_limit", 499))),
    }
    if not 1 <= int(params["limit"]) <= 499 or len(rows) > int(params["limit"]):
        raise ValueError("retained native response exceeds its bounded source limit")
    url = host + source + "?" + urlencode(sorted(params.items()))
    receipt = cast(Mapping[str, object], packet.get("wire_receipt")) or load_evidence(
        profile_root(collector)
        / "responses"
        / f"{sha256(url.encode()).hexdigest()}.json"
    )
    raw = (profile_root(collector) / "raw" / f"{digest}.json").read_bytes()
    if (
        receipt.get("source_url") != url
        or receipt.get("raw_response_sha256") != digest
        or sha256(raw).hexdigest() != digest
        or [[str(value) for value in item] for item in json.loads(raw)] != rows
    ):
        raise ValueError("retained native raw response integrity failed")
    return rows


def _validate_wire_receipt(
    collector: ContinuousMarketHistory,
    row: Mapping[str, object],
    packet: Mapping[str, object],
    start: datetime,
    end: datetime,
    query: Mapping[str, str | int],
    rows: list[list[str]],
) -> None:
    source = str(packet["source"])
    wire = cast(Mapping[str, object], packet["wire_receipt"])
    digest = str(wire.get("raw_response_sha256", ""))
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("retained wire hash is invalid")
    host = (
        "https://api.binance.com"
        if row["market"] == "spot"
        else "https://fapi.binance.com"
    )
    raw = (profile_root(collector) / "raw" / f"{digest}.json").read_bytes()
    if (
        wire.get("source_url") != host + source + "?" + urlencode(sorted(query.items()))
        or sha256(raw).hexdigest() != digest
        or validate_native_rows(
            json.loads(raw),
            start=start,
            end=end,
            timeframe=str(row["timeframe"]),
        )
        != rows
    ):
        raise ValueError("retained wire receipt integrity failed")


def _merge_retained_pages(
    collector: ContinuousMarketHistory,
    market: str,
    symbol: str,
    kind: str,
    timeframe: str,
    cutoff: datetime,
) -> bool:
    """Replay verified staged GET pages only inside the canonical writer lease."""
    if kind != "klines":
        return False
    directory = profile_root(collector) / "pending" / f"{market}-{symbol}-{timeframe}"
    archive = ParquetOHLCVArchive(collector.history.archive_root / market)
    row: dict[str, object] = {
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
    }
    _settle_effect(collector, row, cutoff)
    for path in sorted(directory.glob("*.json")):
        packet = load_evidence(path)
        receipt_path = profile_root(collector) / "replayed" / f"{path.stem}.json"
        rows = _validate_packet(collector, row, packet, cutoff)
        start, end = (
            datetime.fromisoformat(str(packet[key])) for key in ("start", "end")
        )
        candles = collector._parse_rows(
            cast(list[object], rows), start, end, interval=timeframe_duration(timeframe)
        )
        actual = _canonical_page(collector, row, start, end)
        if any(
            stamp in actual and actual[stamp] != item
            for item in candles
            if (stamp := item.timestamp.isoformat())
        ):
            raise ValueError("retained page conflicts with the canonical archive")
        covered = all(
            actual.get(item.timestamp.isoformat()) == item for item in candles
        )
        marker = load_evidence(receipt_path)
        if marker and marker.get("content_sha256") != packet["content_sha256"]:
            raise ValueError("retained replay marker binding mismatch")
        state = _job(collector, row)
        if covered and (
            marker or state.get("last_applied_receipt") == packet["content_sha256"]
        ):
            if not marker:
                save_evidence(
                    receipt_path,
                    {
                        "content_sha256": packet["content_sha256"],
                        "replayed_at": cutoff.isoformat(),
                        **SAFE_STATE,
                    },
                )
            continue
        if not state.get("active_request"):
            state["active_request"] = {
                "phase": "PUBLISH_PENDING",
                "packet_path": str(path),
                "before_open_times": list(actual),
            }
        _increment(state, "retained_page_reuses")
        save_evidence(_job_path(collector, row), state)
        if candles and not covered:
            archive.update(
                symbol,
                timeframe,
                candles,
                source=f"BINANCE_PUBLIC_REST_{timeframe.upper()}",
                generated_at=cutoff,
            )
        _settle_effect(collector, row, cutoff)
        save_evidence(
            receipt_path,
            {
                "content_sha256": packet["content_sha256"],
                "replayed_at": cutoff.isoformat(),
                **SAFE_STATE,
            },
        )
        return True
    if _stage_retained_wire_page(collector, row, cutoff):
        return _merge_retained_pages(collector, market, symbol, kind, timeframe, cutoff)
    return False


def _receipt_query(
    receipt: Mapping[str, object], row: Mapping[str, object]
) -> dict[str, str | int] | None:
    parsed = urlsplit(str(receipt.get("source_url", "")))
    host, source = (
        ("api.binance.com", "/api/v3/klines")
        if row["market"] == "spot"
        else ("fapi.binance.com", "/fapi/v1/klines")
    )
    if parsed.scheme != "https" or parsed.netloc != host or parsed.path != source:
        return None
    query = parse_qs(parsed.query, strict_parsing=True)
    if set(query) != {"symbol", "interval", "startTime", "endTime", "limit"} or any(
        len(values) != 1 for values in query.values()
    ):
        raise ValueError("retained source query is invalid")
    if query["symbol"] != [row["symbol"]] or query["interval"] != [row["timeframe"]]:
        return None
    return {
        "symbol": str(row["symbol"]),
        "interval": str(row["timeframe"]),
        **{key: int(query[key][0]) for key in ("startTime", "endTime", "limit")},
    }


def _wire_page_packet(
    collector: ContinuousMarketHistory,
    row: Mapping[str, object],
    receipt: Mapping[str, object],
    query: Mapping[str, str | int],
    cutoff: datetime,
) -> dict[str, object] | None:
    start = datetime.fromtimestamp(int(query["startTime"]) / 1000, UTC)
    end = datetime.fromtimestamp((int(query["endTime"]) + 1) / 1000, UTC)
    window = acquisition_window(str(row["market"]), str(row["timeframe"]), cutoff)
    if end > cutoff or end <= window.start or start >= window.end:
        return None
    digest = str(receipt.get("raw_response_sha256", ""))
    if (
        re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or not 1 <= int(query["limit"]) <= 499
    ):
        raise ValueError("retained source digest or request limit is invalid")
    raw_path = profile_root(collector) / "raw" / f"{digest}.json"
    if not raw_path.exists():
        return None  # A receipt without its raw bytes cannot supply a candle.
    raw = raw_path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError("retained source raw integrity failed")
    rows = validate_native_rows(
        json.loads(raw), start=start, end=end, timeframe=str(row["timeframe"])
    )
    candles = collector._parse_rows(
        cast(list[object], rows),
        start,
        end,
        interval=timeframe_duration(str(row["timeframe"])),
    )
    actual = _canonical_page(collector, row, start, end)
    if not any(
        window.start <= item.timestamp < window.end
        and item.timestamp.isoformat() not in actual
        for item in candles
    ):
        return None
    packet: dict[str, object] = {
        **{key: row[key] for key in ("market", "symbol", "timeframe")},
        "source": "/api/v3/klines" if row["market"] == "spot" else "/fapi/v1/klines",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rows": rows,
        "raw_response_sha256": digest,
        "retained_request_limit": query["limit"],
        "selection_version": (collector.scoped_selection or {})["selection_version"],
        "wire_receipt": dict(receipt),
        **SAFE_STATE,
    }
    packet["content_sha256"] = content_digest(packet)
    return packet


def _stage_retained_wire_page(
    collector: ContinuousMarketHistory, row: Mapping[str, object], cutoff: datetime
) -> bool:
    """Recover existing source bytes, including a crash before pending staging."""
    root = profile_root(collector)
    receipt_paths = (
        *sorted((root / "responses").glob("*.json")),
        *sorted((root / "responses" / "history").glob("*.json")),
    )
    for path in receipt_paths:
        receipt = load_evidence(path)
        query = _receipt_query(receipt, row)
        if query is None:
            continue
        packet = _wire_page_packet(collector, row, receipt, query, cutoff)
        if packet is not None:
            pending = (
                root
                / "pending"
                / f"{row['market']}-{row['symbol']}-{row['timeframe']}"
                / f"wire-{packet['content_sha256']}.json"
            )
            if not pending.exists():
                save_evidence(pending, packet)
            return True
    return False


def _enrichment_turns(
    collector: ContinuousMarketHistory, cutoff: datetime, policy: ScopedRetryPolicy
) -> list[dict[str, object]]:
    """Retain supported enrichment through the same bounded canonical adapters."""
    selected = verified_selection(collector.scoped_selection or {})
    collector.scoped_details_start = previous_calendar_month(cutoff)
    jobs: list[dict[str, object]] = []
    for kind, timeframe in collector._collection_kinds("usd_m_futures"):
        if kind == "klines":
            continue
        for asset in selected:
            jobs.append(
                {
                    "market": "usd_m_futures",
                    "symbol": asset["futures_symbol"],
                    "kind": kind,
                    "timeframe": timeframe or "1d",
                    "tail_ready": False,
                }
            )
    return [_collect_turn(collector, job, cutoff, policy) for job in jobs]
