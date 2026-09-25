"""Compatibility implementation for local opportunity monitoring.

This bounded implementation persists observations before measuring subsequent
price paths. It never routes outcomes back into candidate generation.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import cast

from ai4binance.agents.catalog import build_default_registry
from ai4binance.agents.data_quality_gate import DataQualityGate
from ai4binance.core.contracts.risk import RiskConfig
from ai4binance.core.errors import ExchangeError
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_sync import read_cached_market_universe
from ai4binance.domain.opportunity_observation import (
    OpportunityLifecycleState,
    diagnose_opportunity_generation,
    has_complete_measurable_opportunity,
    has_complete_measurable_trade_plan,
)
from ai4binance.opportunity_intelligence import (
    TIMEFRAME_DURATIONS,
    ChartPatternLifecycleState,
    OpportunityEventType,
    OpportunityLifecycleEvent,
    detect_chart_pattern,
    opportunity_event_id,
)
from ai4binance.opportunity_ledger import OpportunityLedgerWriter
from ai4binance.opportunity_outcomes import evaluate_opportunity_outcome
from ai4binance.opportunity_radar import (
    VWAPOpportunityEvaluator,
    build_opportunity_radar_snapshot,
)
from ai4binance.reporting import to_primitive
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified
from ai4binance.storage.jsonl import read_bounded_jsonl_tail

MARKET_TIMEFRAMES = {
    "SPOT": ("5m", "15m", "1h", "4h", "1d"),
    "USD_M_FUTURES": ("5m", "15m", "1h", "4h", "1d"),
}
SAFE_STATE: dict[str, object] = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}
FuturesBuilder = Callable[[MarketSnapshot, str], dict[str, object]]
_MAX_UNIVERSE_OPPORTUNITIES = 100


def monitor_directory(root: Path, market: str, symbol: str) -> Path:
    if market not in MARKET_TIMEFRAMES or not re.fullmatch(r"[A-Z0-9]{4,24}", symbol):
        raise ValueError("monitor market or symbol is invalid")
    return root / "runtime/artifacts/opportunity-radar/monitor" / market / symbol


def market_symbols(cache: Path, market: str, now: datetime) -> tuple[str, ...]:
    """Return only the currently verified Binance market universe for the UI."""
    if market not in MARKET_TIMEFRAMES:
        raise ValueError("monitor market is invalid")
    universe = read_cached_market_universe(cache / "universe-v3.json", now)
    if universe is None:
        return ()
    return universe.spot_symbols if market == "SPOT" else universe.futures_symbols


def read_monitor(root: Path, market: str, symbol: str) -> dict[str, object]:
    path = monitor_directory(root, market, symbol) / "latest.json"
    if not path.exists():
        return {
            "status": "NOT_SCANNED",
            "market": market,
            "symbol": symbol,
            **SAFE_STATE,
        }
    if path.stat().st_size > 8_000_000 or path.is_symlink():
        raise ValueError("monitor artifact exceeds read boundary")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(
        value.get(k) != v for k, v in SAFE_STATE.items()
    ):
        raise ValueError("monitor artifact authority is invalid")
    if value.get("market") != market or value.get("symbol") != symbol:
        raise ValueError("monitor artifact identity is invalid")
    return cast(dict[str, object], value)


def universe_monitor_summary(
    root: Path,
    archive: ParquetOHLCVArchive,
    *,
    market: str,
    symbols: tuple[str, ...],
    now: datetime,
    minimum_candles: int,
) -> dict[str, object]:
    """Summarize the eligible universe, not only the selected symbol.

    The collector owns candle refresh.  This read-only projection verifies each
    dataset manifest, reports the complete universe denominator per timeframe,
    and exposes only persisted monitor observations.  Therefore missing monitor
    coverage is explicit instead of being represented as an empty opportunity set.
    """
    if market not in MARKET_TIMEFRAMES:
        raise ValueError("monitor market is invalid")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("monitor summary timestamp must be timezone-aware")
    status_counts = {
        timeframe: {"CURRENT": 0, "STALE": 0, "INVALID": 0, "UNAVAILABLE": 0}
        for timeframe in MARKET_TIMEFRAMES[market]
    }
    monitored_symbols = 0
    opportunities: list[dict[str, object]] = []
    total_opportunity_count = 0
    for symbol in symbols:
        for timeframe in MARKET_TIMEFRAMES[market]:
            status = "UNAVAILABLE"
            try:
                manifest = archive.manifest(symbol, timeframe)
                last_close = (
                    datetime.fromisoformat(manifest.last_timestamp)
                    + (TIMEFRAME_DURATIONS[timeframe])
                )
                if manifest.row_count < minimum_candles or manifest.gap_count:
                    status = "INVALID"
                elif now.astimezone(UTC) - last_close.astimezone(UTC) > (
                    TIMEFRAME_DURATIONS[timeframe] * 2
                ):
                    status = "STALE"
                else:
                    status = "CURRENT"
            except (FileNotFoundError, OSError, ValueError, TypeError):
                status = "UNAVAILABLE"
            status_counts[timeframe][status] += 1
        try:
            monitor_path = monitor_directory(root, market, symbol) / "latest.json"
        except ValueError:
            continue
        if not monitor_path.exists():
            continue
        try:
            monitor = read_monitor(root, market, symbol)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        monitored_symbols += 1
        rows = monitor.get("candidates")
        if isinstance(rows, list):
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or row.get("execution_allowed") is not False
                    or row.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
                    or not has_complete_measurable_opportunity(row)
                ):
                    continue
                total_opportunity_count += 1
                if len(opportunities) < _MAX_UNIVERSE_OPPORTUNITIES:
                    opportunities.append(cast(dict[str, object], row))
    quality = []
    for timeframe in MARKET_TIMEFRAMES[market]:
        counts = status_counts[timeframe]
        quality.append(
            {
                "timeframe": timeframe,
                "universe_count": len(symbols),
                "current_count": counts["CURRENT"],
                "stale_count": counts["STALE"],
                "invalid_count": counts["INVALID"],
                "unavailable_count": counts["UNAVAILABLE"],
                "refresh_required_count": len(symbols) - counts["CURRENT"],
            }
        )
    return {
        "generated_at": now.astimezone(UTC).isoformat(),
        "market": market,
        "universe_count": len(symbols),
        "quality": quality,
        "opportunity_coverage": {
            "monitored_symbol_count": monitored_symbols,
            "universe_count": len(symbols),
            "unmonitored_symbol_count": len(symbols) - monitored_symbols,
            "published_opportunity_count": len(opportunities),
            "suppressed_opportunity_count": total_opportunity_count
            - len(opportunities),
        },
        "opportunities": opportunities,
        **SAFE_STATE,
    }


def _snapshot(
    market: str,
    symbol: str,
    now: datetime,
    candles: dict[str, tuple[OHLCVCandle, ...]],
    freshness: dict[str, object],
    identity: str,
) -> MarketSnapshot:
    prices = [rows[-1].close for rows in candles.values() if rows]
    return MarketSnapshot(
        snapshot_id=identity,
        created_at=now,
        exchange="Binance",
        market_type=market,
        symbol=symbol,
        timeframes=tuple(candles),
        ohlcv_by_timeframe=candles,
        latest_price=prices[0] if prices else None,
        bid=None,
        ask=None,
        spread=None,
        data_quality=DataQuality.DATA_VALID,
        data_freshness=freshness,
        market_metadata={"source": "CANONICAL_LOCAL_MARKET_ARCHIVE"},
    )


def inspect_market_data(
    archive: ParquetOHLCVArchive,
    *,
    market: str,
    symbol: str,
    now: datetime,
    minimum_candles: int,
    candle_limit: int,
    timeframes: tuple[str, ...] | None = None,
) -> tuple[MarketSnapshot, list[dict[str, object]]]:
    """Verify checksums and expose per-timeframe gate results, including gaps."""
    timeframes = timeframes or MARKET_TIMEFRAMES[market]
    if len(set(timeframes)) != len(timeframes) or any(
        tf not in MARKET_TIMEFRAMES[market] for tf in timeframes
    ):
        raise ValueError("monitor timeframes are invalid")
    candles: dict[str, tuple[OHLCVCandle, ...]] = {}
    freshness: dict[str, object] = {}
    quality: list[dict[str, object]] = []
    identities: list[str] = []
    gate = DataQualityGate(
        build_default_registry().get("data_quality"), minimum_candles
    )
    for tf in timeframes:
        duration = TIMEFRAME_DURATIONS[tf]
        row: dict[str, object] = {
            "market": market,
            "symbol": symbol,
            "timeframe": tf,
            "status": "UNAVAILABLE",
            "required_candles": minimum_candles,
            "candle_count": None,
            "last_close": None,
            "gap_count": None,
            "checksum_verified": False,
            "blockers": ["DATASET_UNAVAILABLE"],
        }
        rows: tuple[OHLCVCandle, ...] = ()
        try:
            manifest = archive.manifest(symbol, tf)
            rows = archive.read_window(
                symbol,
                tf,
                start_at=now - duration * (candle_limit + 2),
                end_at=now,
            )
            if archive.manifest(symbol, tf).sha256 != manifest.sha256:
                raise ValueError("dataset changed during inspection")
            rows = tuple(c for c in rows if c.timestamp + duration <= now)[
                -candle_limit:
            ]
            last_close = rows[-1].timestamp + duration if rows else None
            stale = last_close is None or now - last_close > duration * 2
            gap_count = sum(
                b.timestamp - a.timestamp != duration for a, b in pairwise(rows)
            )
            freshness[tf] = {"stale": stale}
            sample = _snapshot(
                market, symbol, now, {tf: rows}, freshness, manifest.sha256
            )
            result = gate.evaluate(sample)
            blockers = list(result.blockers)
            if gap_count or manifest.gap_count:
                blockers.append("DATASET_GAPS")
            row.update(
                status="STALE" if stale else "INVALID" if blockers else "CURRENT",
                candle_count=len(rows),
                last_close=last_close.isoformat() if last_close else None,
                gap_count=manifest.gap_count,
                window_gap_count=gap_count,
                checksum_verified=True,
                source=manifest.source,
                dataset_sha256=manifest.sha256,
                total_candles=manifest.row_count,
                blockers=blockers,
            )
            identities.append(f"{tf}:{manifest.sha256}:{last_close}")
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            row.update(status="INVALID", blockers=["DATASET_INTEGRITY_FAILED"])
            rows = ()
        candles[tf] = rows
        quality.append(row)
    digest = sha256("|".join(identities).encode()).hexdigest()[:24]
    return _snapshot(
        market, symbol, now, candles, freshness, f"monitor:{market}:{symbol}:{digest}"
    ), quality


def screen_market_opportunities(
    archive: ParquetOHLCVArchive,
    *,
    market: str,
    symbol: str,
    now: datetime,
    minimum_candles: int,
    candle_limit: int,
) -> dict[str, object]:
    """Select research enrichment from canonical 15m/1h observations only.

    A trigger or active chart formation requests more evidence. It does not
    satisfy the full radar's higher-timeframe, risk, or execution gates.
    """
    snapshot, quality = inspect_market_data(
        archive,
        market=market,
        symbol=symbol,
        now=now,
        minimum_candles=minimum_candles,
        candle_limit=candle_limit,
        timeframes=("15m", "1h"),
    )
    blockers = [
        f"SCREEN_DATA_{row['status']}:{row['timeframe']}"
        for row in quality
        if row["status"] != "CURRENT"
    ]
    observations: list[dict[str, object]] = []
    if not blockers:
        for timeframe, candles in snapshot.ohlcv_by_timeframe.items():
            vwap = VWAPOpportunityEvaluator().evaluate(
                snapshot,
                timeframe=timeframe,
                session_start=candles[0].timestamp,
                structure_aligned=False,
                htf_aligned=False,
            )
            pattern = detect_chart_pattern(
                candles,
                timeframe=timeframe,
                snapshot_id=snapshot.snapshot_id,
                decision_time=now,
            )
            active_pattern = pattern is not None and pattern.state not in {
                ChartPatternLifecycleState.EXPIRED,
                ChartPatternLifecycleState.INVALIDATED,
            }
            if vwap.bias.value != "NEUTRAL" or active_pattern:
                observations.append(
                    {
                        "timeframe": timeframe,
                        "setup_name": pattern.pattern_type
                        if active_pattern and pattern
                        else vwap.setup_name,
                        "confirmation_requirements": list(vwap.blockers),
                        **SAFE_STATE,
                    }
                )
    return {
        "status": "DATA_BLOCKED" if blockers else "CURRENT",
        "stage": "SCREENING",
        "market": market,
        "symbol": symbol,
        "observed_at": now.isoformat(),
        "timeframes": ["15m", "1h"],
        "quality": quality,
        "candidate_count": len(observations),
        "observations": observations,
        "enrichment_required": bool(observations) and not blockers,
        "blockers": blockers,
        **SAFE_STATE,
    }


def _history(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    if path.stat().st_size > 16_000_000:
        raise ValueError("monitor ledger requires archival before further refresh")
    JsonlAuditStore(path, tamper_evident=True).verify_chain()
    return [
        cast(dict[str, object], json.loads(line)["payload"])
        for line in read_bounded_jsonl_tail(path, max_lines=100_000)
    ]


def _decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result > 0 else None
    except ArithmeticError:
        return None


def _research_position_estimate(candidate: Mapping[str, object]) -> dict[str, object]:
    """Return a bounded research sizing estimate without execution authority."""

    if not has_complete_measurable_trade_plan(candidate):
        return {}
    entry = _decimal(candidate.get("entry"))
    stop = _decimal(candidate.get("stop_loss"))
    if entry is None or stop is None:
        return {}
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return {}
    policy = RiskConfig()
    risk_budget = policy.max_open_position_size_usdt * policy.max_risk_per_trade
    quantity = min(
        risk_budget / stop_distance,
        policy.max_open_position_size_usdt / entry,
    )
    if not quantity.is_finite() or quantity <= 0:
        return {}
    market = str(candidate.get("market", "")).strip().upper()
    bullish = str(candidate.get("direction", "")).strip().upper().startswith("BULLISH")
    estimate: dict[str, object] = {
        "side": "BUY"
        if market == "SPOT" and bullish
        else "SELL"
        if market == "SPOT"
        else "LONG"
        if market == "USD_M_FUTURES" and bullish
        else "SHORT",
        "quantity": format(quantity.normalize(), "f"),
        "estimated_notional_usdt": format((quantity * entry).normalize(), "f"),
        "position_risk_usdt": format((quantity * stop_distance).normalize(), "f"),
        "quantity_basis": "RESEARCH_RISK_POLICY_ESTIMATE",
    }
    if market == "USD_M_FUTURES":
        estimate.update(
            leverage=1,
            leverage_basis="CONSERVATIVE_RESEARCH_BASELINE",
        )
    return estimate


def _outcome(
    row: dict[str, object], archive: ParquetOHLCVArchive, now: datetime
) -> dict[str, object]:
    tf = str(row["timeframe"])
    price = _decimal(row.get("entry"))
    direction = str(row.get("direction", ""))
    if price is None or not has_complete_measurable_opportunity(row):
        return {
            "status": "NOT_TRACKABLE",
            "outcome_reason_codes": ["COMPLETE_MEASURABLE_TRADE_PLAN_REQUIRED"],
        }
    observed = datetime.fromisoformat(str(row["observed_at"]))
    duration = TIMEFRAME_DURATIONS[tf]
    try:
        manifest = archive.manifest(str(row["symbol"]), tf)
        future = archive.read_window(
            str(row["symbol"]), tf, start_at=observed, end_at=now
        )
        if archive.manifest(str(row["symbol"]), tf).sha256 != manifest.sha256:
            raise ValueError("outcome dataset changed during evaluation")
        future = tuple(c for c in future if c.timestamp + duration <= now)
        if future and (
            future[0].timestamp - observed >= duration
            or any(
                b.timestamp - a.timestamp != duration for a, b in pairwise(future[:3])
            )
        ):
            return {
                "status": "NOT_EVALUABLE",
                "outcome_reason_codes": ["OUTCOME_DATA_GAP"],
            }
        evaluated = evaluate_opportunity_outcome(
            opportunity_id=str(row["opportunity_id"]),
            direction=direction.split("_CAUTION")[0],
            reference_price=price,
            observed_at=observed,
            future_candles=future,
            evaluation_horizon=3,
            dataset_id=manifest.sha256,
            timeframe=tf,
            invalidation_price=_decimal(row.get("stop_loss")),
            target_price=_decimal(row.get("tp1")),
        )
        return cast(dict[str, object], to_primitive(evaluated))
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "status": "NOT_EVALUABLE",
            "outcome_reason_codes": ["OUTCOME_DATA_UNAVAILABLE"],
        }


def refresh_monitor(
    root: Path,
    archive: ParquetOHLCVArchive,
    *,
    market: str,
    symbol: str,
    now: datetime,
    minimum_candles: int = 200,
    candle_limit: int = 250,
    futures_builder: FuturesBuilder | None = None,
    timeframes: tuple[str, ...] | None = None,
) -> dict[str, object]:
    directory = monitor_directory(root, market, symbol)
    selected_timeframes = timeframes or MARKET_TIMEFRAMES[market]
    if (
        not selected_timeframes
        or len(set(selected_timeframes)) != len(selected_timeframes)
        or any(
            timeframe not in MARKET_TIMEFRAMES[market]
            for timeframe in selected_timeframes
        )
    ):
        raise ValueError("monitor timeframes are invalid")
    snapshot, quality = inspect_market_data(
        archive,
        market=market,
        symbol=symbol,
        now=now,
        minimum_candles=minimum_candles,
        candle_limit=candle_limit,
        timeframes=selected_timeframes,
    )
    quality_by_tf = {str(row["timeframe"]): row for row in quality}
    history_path = directory / "observations.jsonl"
    history = [
        row
        for row in _history(history_path)
        if has_complete_measurable_opportunity(row)
    ]
    seen = {str(row["opportunity_id"]) for row in history}
    observations = JsonlAuditStore(history_path, durable=True, tamper_evident=True)
    lifecycle = OpportunityLedgerWriter(directory / "lifecycle.jsonl")
    candidates: list[dict[str, object]] = []
    rejected_attempts: list[dict[str, object]] = []
    rejected_by_stage: Counter[str] = Counter()
    rejected_by_reason: Counter[str] = Counter()
    discarded_unmeasurable_candidate_count = 0
    for tf in selected_timeframes:
        dependencies = (tf, "15m", "1h", "4h") if market == "SPOT" else (tf,)
        invalid = tuple(
            dict.fromkeys(
                f"DATA_NOT_CURRENT:{name}"
                for name in dependencies
                if quality_by_tf.get(name, {}).get("status") != "CURRENT"
            )
        )
        item: dict[str, object] = {
            "symbol": symbol,
            "market": market,
            "timeframe": tf,
            "observed_at": now.isoformat(),
            "direction": "WATCH_ONLY",
            "status": "DATA_BLOCKED",
            "blockers": list(invalid),
            **SAFE_STATE,
        }
        if market == "SPOT":
            radar = build_opportunity_radar_snapshot(
                (
                    replace(
                        snapshot,
                        data_quality=DataQuality.DATA_INVALID
                        if invalid
                        else DataQuality.DATA_VALID,
                    ),
                ),
                cycle_id=snapshot.snapshot_id,
                timeframe=tf,
            )
            candidate = radar.candidates[0]
            item.update(candidate.to_inbox_item())
            item.update(
                opportunity_id=candidate.opportunity_id, observed_at=now.isoformat()
            )
        elif not invalid and futures_builder is not None:
            try:
                item.update(futures_builder(snapshot, tf))
            except (OSError, ValueError, RuntimeError, ExchangeError):
                item.update(
                    status="DATA_BLOCKED", blockers=["DERIVATIVES_DATA_UNAVAILABLE"]
                )
        rows = snapshot.ohlcv_by_timeframe.get(tf, ())
        item.update(reference_price=str(rows[-1].close) if rows else None, **SAFE_STATE)
        candle_time = rows[-1].timestamp.isoformat() if rows else "missing"
        identity_seed = (
            f"{market}:{symbol}:{tf}:{candle_time}:"
            f"{item.get('setup_name')}:{item['direction']}"
        )
        item["opportunity_id"] = (
            "monitor-opportunity:" + sha256(identity_seed.encode()).hexdigest()[:24]
        )
        item["data_status"] = quality_by_tf[tf]["status"]
        item["category"] = (
            "POTENTIAL"
            if item["direction"] in {"WATCH_ONLY", "NEUTRAL"}
            or item.get("confirmation_requirements")
            or invalid
            else "OBSERVED"
        )
        item.update(_research_position_estimate(item))
        diagnostic = diagnose_opportunity_generation(item)
        if not diagnostic.complete:
            discarded_unmeasurable_candidate_count += 1
            rejection_time = (
                rows[-1].timestamp + TIMEFRAME_DURATIONS[tf] if rows else now
            )
            diagnostic_payload: dict[str, object] = {
                "candidate_attempt_id": str(item["opportunity_id"]),
                "market": market,
                "symbol": symbol,
                "timeframe": tf,
                "observed_at": now.isoformat(),
                "candle_close_time": rejection_time.isoformat(),
                **diagnostic.to_payload(),
                **SAFE_STATE,
            }
            rejected_attempts.append(diagnostic_payload)
            rejected_by_stage[diagnostic.failed_stage.value] += 1
            rejected_by_reason.update(diagnostic.reason_codes)
            diagnostic_fingerprint = sha256(
                "|".join(
                    (
                        diagnostic.outcome.value,
                        diagnostic.failed_stage.value,
                        *diagnostic.reason_codes,
                        *diagnostic.missing_fields,
                    )
                ).encode()
            ).hexdigest()[:16]
            lifecycle.append(
                OpportunityLifecycleEvent(
                    event_id=opportunity_event_id(
                        f"{item['opportunity_id']}:{diagnostic_fingerprint}",
                        OpportunityEventType.OPPORTUNITY_REJECTED,
                        rejection_time,
                        snapshot.snapshot_id,
                    ),
                    event_type=OpportunityEventType.OPPORTUNITY_REJECTED,
                    opportunity_id=str(item["opportunity_id"]),
                    lifecycle_state=OpportunityLifecycleState.REJECTED,
                    event_time=rejection_time,
                    cycle_id=snapshot.snapshot_id,
                    snapshot_id=snapshot.snapshot_id,
                    reason_codes=diagnostic.reason_codes,
                    evidence_refs=(
                        snapshot.snapshot_id,
                        f"timeframe:{tf}",
                        f"candle-close:{rejection_time.isoformat()}",
                    ),
                    market=market,
                    symbol=symbol,
                    timeframe=tf,
                    evaluation_stage=diagnostic.failed_stage.value,
                    missing_fields=diagnostic.missing_fields,
                    retryability=diagnostic.retryability,
                )
            )
            continue
        candidates.append(item)
        identity = str(item["opportunity_id"])
        if identity not in seen:
            observations.append_verified_idempotent(
                AuditEvent(
                    event_type="OPPORTUNITY_OBSERVED",
                    timestamp=now,
                    payload=item,
                    snapshot_id=identity,
                )
            )
            lifecycle.append(
                OpportunityLifecycleEvent(
                    event_id=opportunity_event_id(
                        identity,
                        OpportunityEventType.OPPORTUNITY_OBSERVED,
                        now,
                        snapshot.snapshot_id,
                    ),
                    event_type=OpportunityEventType.OPPORTUNITY_OBSERVED,
                    opportunity_id=identity,
                    lifecycle_state=OpportunityLifecycleState.WATCH_ONLY,
                    event_time=now,
                    cycle_id=snapshot.snapshot_id,
                    snapshot_id=snapshot.snapshot_id,
                    reason_codes=("RESEARCH_ONLY_OBSERVATION",),
                    evidence_refs=(snapshot.snapshot_id,),
                )
            )
            history.append(item)
            seen.add(identity)
    performance: list[dict[str, object]] = []
    outcomes = JsonlAuditStore(
        directory / "outcomes.jsonl", durable=True, tamper_evident=True
    )
    completed = {str(row["opportunity_id"]): row for row in _history(outcomes.path)}
    for row in history:
        identity = str(row["opportunity_id"])
        trackable = has_complete_measurable_opportunity(row)
        if trackable:
            outcome = completed.get(identity) or _outcome(row, archive, now)
        else:
            outcome = {
                "status": "NOT_TRACKABLE",
                "outcome_reason_codes": ["COMPLETE_MEASURABLE_TRADE_PLAN_REQUIRED"],
            }
        performance.append({**row, "outcome": outcome})
        if outcome.get("status") == "EVALUATED" and identity not in completed:
            outcomes.append_verified_idempotent(
                AuditEvent(
                    event_type="OPPORTUNITY_OUTCOME_EVALUATED",
                    timestamp=now,
                    payload=outcome,
                    snapshot_id=f"{row['opportunity_id']}:3",
                )
            )
    payload: dict[str, object] = {
        "market": market,
        "symbol": symbol,
        "generated_at": now.isoformat(),
        "status": "CURRENT",
        "quality": quality,
        "candidates": candidates,
        "discarded_unmeasurable_candidate_count": (
            discarded_unmeasurable_candidate_count
        ),
        "generation_health": {
            "evaluated_attempt_count": len(selected_timeframes),
            "published_opportunity_count": len(candidates),
            "rejected_attempt_count": discarded_unmeasurable_candidate_count,
            "rejected_by_stage": dict(sorted(rejected_by_stage.items())),
            "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
            "recent_rejections": rejected_attempts[-20:],
        },
        "history": performance[-500:],
        "history_count": len(performance),
        "history_limit": 500,
        "evaluation_horizon_bars": 3,
        "performance_basis": "ENTRY_ANCHORED_PLAN_PATH_NO_FEES_NO_EXECUTION",
        "timeframes": list(selected_timeframes),
        **SAFE_STATE,
    }
    write_json_object_verified(
        directory / "latest.json",
        cast(dict[str, object], to_primitive(payload)),
        blocker="MONITOR_WRITE_FAILED",
    )
    return payload
