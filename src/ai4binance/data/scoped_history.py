"""Scoped orchestration of the existing continuous DataCore collector.

No scheduler, service, alternate archive, or trading eligibility is created.
"""

import errno
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

from ai4binance.core.errors import ExchangeError, ExchangeRateLimitError
from ai4binance.data.acquisition_profile import (
    PROFILE_ID,
    PROFILE_TIMEFRAMES,
    SAFE_STATE,
    acquisition_window,
    content_digest,
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
    """Give every due asset/TF a bounded turn, with tails before backfill."""
    if collector.pages_per_stream != 1 or collector.archives_per_stream != 1:
        raise ValueError("scoped profile requires one bounded recovery chunk per turn")
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
        if str(row["status"]).startswith("DATA_READY"):
            results.append(
                {
                    "market": row["market"],
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "status": "CURRENT",
                }
            )
            continue
        results.append(_collect_turn(collector, row, cutoff, policy))
    enrichment = _enrichment_turns(collector, cutoff, policy)
    report = profile_health(collector, cutoff=cutoff)
    report.update(
        results=results,
        collector_liveness="PASS_FINISHED",
        useful_progress_count=sum(item["status"] == "PROGRESS" for item in results),
        bounded_backlog=len(rows) + len(enrichment),
        native_stream_count=len(rows),
        enrichment_stream_count=len(enrichment),
        futures_enrichment_results=enrichment,
        futures_enrichment_status="PARTIAL_REQUIRED_CONSUMERS_MUST_VERIFY_INPUTS",
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


def _collect_turn(
    collector: ContinuousMarketHistory,
    row: dict[str, object],
    cutoff: datetime,
    policy: ScopedRetryPolicy,
) -> dict[str, object]:
    market, symbol, timeframe = (
        str(row[key]) for key in ("market", "symbol", "timeframe")
    )
    now = datetime.now(UTC)
    kind = str(row.get("kind", "klines"))
    retry_path = (
        profile_root(collector) / "retry" / f"{market}-{symbol}-{kind}-{timeframe}.json"
    )
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
    transport = collector.spot if market == "spot" else collector.futures
    collector.scoped_tail_priority = not bool(row.get("tail_ready"))
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
    after_sha = _turn_revision(collector, market, symbol, kind, timeframe)
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
    elif result.get("status") in {"CURRENT", "TAIL_CURRENT"}:
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
    for path in sorted(directory.glob("*.json"))[:32]:
        packet = load_evidence(path)
        receipt_path = profile_root(collector) / "replayed" / f"{path.stem}.json"
        if receipt_path.exists():
            continue
        binding = {
            key: value for key, value in packet.items() if key != "content_sha256"
        }
        if (
            packet.get("content_sha256") != content_digest(binding)
            or packet.get("market") != market
            or packet.get("symbol") != symbol
            or packet.get("timeframe") != timeframe
            or packet.get("selection_version")
            != (collector.scoped_selection or {}).get("selection_version")
        ):
            raise ValueError("retained native page binding mismatch")
        start, end = (
            datetime.fromisoformat(str(packet[key])) for key in ("start", "end")
        )
        if (
            end > cutoff
            or not start < end
            or packet.get("source")
            != ("/api/v3/klines" if market == "spot" else "/fapi/v1/klines")
        ):
            raise ValueError("retained native page exceeds its causal or source scope")
        rows = validate_native_rows(
            packet["rows"], start=start, end=end, timeframe=timeframe
        )
        digest = str(packet["raw_response_sha256"])
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("retained response hash is invalid")
        raw_path = profile_root(collector) / "raw" / (digest + ".json")
        host = (
            "https://api.binance.com"
            if market == "spot"
            else "https://fapi.binance.com"
        )
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000) - 1,
            "limit": 499,
        }
        url = host + str(packet["source"]) + "?" + urlencode(sorted(params.items()))
        receipt = load_evidence(
            profile_root(collector)
            / "responses"
            / f"{sha256(url.encode()).hexdigest()}.json"
        )
        if (
            receipt.get("source_url") != url
            or receipt.get("raw_response_sha256") != digest
        ):
            raise ValueError("retained response source receipt mismatch")
        raw = raw_path.read_bytes()
        if (
            sha256(raw).hexdigest() != packet["raw_response_sha256"]
            or [[str(value) for value in row] for row in json.loads(raw)] != rows
        ):
            raise ValueError("retained native raw response integrity failed")
        candles = collector._parse_rows(
            cast(list[object], rows), start, end, interval=timeframe_duration(timeframe)
        )
        if candles:
            manifest = archive.update(
                symbol,
                timeframe,
                candles,
                source=f"BINANCE_PUBLIC_REST_{timeframe.upper()}",
                generated_at=cutoff,
            )
            save_evidence(
                receipt_path,
                {
                    "content_sha256": packet["content_sha256"],
                    "dataset_sha256": manifest.sha256,
                    "replayed_at": cutoff.isoformat(),
                    **SAFE_STATE,
                },
            )
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
