"""CLI adapter for low-bandwidth public market-history synchronization."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import BoundedSemaphore

from ai4binance.application.opportunity_monitor import (
    monitor_directory,
    refresh_monitor,
)
from ai4binance.compatibility.opportunity_monitor import screen_market_opportunities
from ai4binance.config import Settings
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.legacy_1m_cleanup import LegacyOneMinuteCleanup
from ai4binance.data.market_depth import MarketDepthCollector
from ai4binance.data.market_history_continuous import (
    VIRTUAL_MARKET_COLLECTION_TIMEFRAMES,
    ContinuousMarketHistory,
    MeteredPublicTransport,
    PublicRequestBudget,
)
from ai4binance.data.market_history_sync import (
    BinanceVisionArchiveCache,
    MarketHistorySupervisor,
    MarketHistorySynchronizer,
)
from ai4binance.data.market_universe_retention import MarketUniverseRetention
from ai4binance.domain.opportunity_observation import (
    has_complete_measurable_opportunity,
)
from ai4binance.exchange.rate_limit import RateLimitBands, WeightedRateLimitGovernor
from ai4binance.integrations.binance import (
    BinanceMarketUniverseProvider,
    ReadOnlyBinanceJsonTransport,
)
from ai4binance.integrations.research_market_universe import (
    ReadOnlyCoinGeckoJsonTransport,
    ResearchMarketUniverseProvider,
)
from ai4binance.ops.runtime import SingleInstanceLease

_SAFE_STATE: dict[str, object] = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}
_DEPTH_SYMBOLS_PER_CONNECTION = 10
_DASHBOARD_CANDIDATE_FIELDS = (
    "opportunity_id",
    "observed_at",
    "timeframe",
    "direction",
    "status",
    "reference_price",
    "entry",
    "stop_loss",
    "tp1",
    "tp2",
    "tp3",
    "target_risk_reward",
    "side",
    "quantity",
    "leverage",
    "estimated_notional_usdt",
    "position_risk_usdt",
    "quantity_basis",
    "leverage_basis",
    "setup_name",
)


def _dashboard_candidate_projection(
    candidates: Sequence[object], *, market: str, symbol: str
) -> list[dict[str, object]]:
    """Return the bounded, authority-preserving candidate projection for readers."""

    projected: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        if (
            candidate.get("market") != market
            or candidate.get("symbol") != symbol
            or candidate.get("execution_allowed") is not False
            or candidate.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
            or not has_complete_measurable_opportunity(candidate)
        ):
            continue
        row: dict[str, object] = {}
        for name in _DASHBOARD_CANDIDATE_FIELDS:
            value = candidate.get(name)
            if isinstance(value, str) and len(value) <= 240:
                row[name] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                row[name] = value
        blockers = candidate.get("blockers")
        if (
            isinstance(blockers, Sequence)
            and not isinstance(blockers, str)
            and all(
                isinstance(blocker, str) and len(blocker) <= 180
                for blocker in blockers[:40]
            )
        ):
            row["blockers"] = list(blockers[:40])
        else:
            row["blockers"] = ["CANDIDATE_BLOCKERS_UNAVAILABLE"]
        row.update(market=market, symbol=symbol, **_SAFE_STATE)
        projected.append(row)
    return projected


def _priority_depth_markets(
    universe: object,
    priority_symbols: Sequence[str],
    *,
    include_coin_m: bool,
) -> dict[str, tuple[str, ...]]:
    """Cover each active top-volume market universe with bounded public L2."""

    priority = tuple(dict.fromkeys(priority_symbols))
    spot_symbols = tuple(dict.fromkeys(getattr(universe, "spot_symbols", ())))
    futures_symbols = tuple(dict.fromkeys(getattr(universe, "futures_symbols", ())))

    def selected(symbols: tuple[str, ...]) -> tuple[str, ...]:
        eligible = frozenset(symbols)
        watched = tuple(symbol for symbol in priority if symbol in eligible)
        return tuple(dict.fromkeys((*watched, *symbols)))[:50]

    markets = {
        "spot": selected(spot_symbols),
        "usd_m_futures": selected(futures_symbols),
    }
    if include_coin_m:
        coin_m_symbols = frozenset(getattr(universe, "coin_m_symbols", ()))
        markets["coin_m_futures"] = tuple(
            symbol for symbol in priority if symbol in coin_m_symbols
        )
    return markets


def build_market_depth_collector(
    synchronizer: MarketHistorySynchronizer,
    continuous: ContinuousMarketHistory,
) -> MarketDepthCollector:
    """Build bounded shards so one reconnect cannot invalidate a full universe."""

    transports = {"spot": continuous.spot, "usd_m_futures": continuous.futures}
    if continuous.coin_m is not None:
        transports["coin_m_futures"] = continuous.coin_m
    return MarketDepthCollector(
        synchronizer.archive_root / "depth",
        transports,
        symbols_per_connection=_DEPTH_SYMBOLS_PER_CONNECTION,
    )


def build_continuous_market_history(
    settings: Settings,
    synchronizer: MarketHistorySynchronizer,
    *,
    root: Path,
    include_coin_m: bool,
) -> ContinuousMarketHistory:
    """Build the one canonical continuous collector used by every runtime."""

    return ContinuousMarketHistory(
        history=synchronizer,
        spot=synchronizer.universe_provider.spot_transport,
        futures=synchronizer.universe_provider.futures_transport,
        initial_days=settings.market_history_initial_days,
        enrichment_days=getattr(
            settings,
            "market_history_enrichment_days",
            settings.market_history_initial_days,
        ),
        pages_per_stream=settings.market_history_pages_per_stream,
        max_workers=settings.market_history_max_workers,
        minimum_candles=settings.minimum_closed_candles,
        coin_m=(
            synchronizer.universe_provider.coin_m_transport if include_coin_m else None
        ),
        priority_symbols=tuple(
            dict.fromkeys(
                (settings.symbol, *settings.fixed_symbols, *settings.priority_watchlist)
            )
        ),
        refresh_request_path=_absolute(settings.market_history_state_path).with_name(
            "market-history-refresh-request.json"
        ),
        on_symbol_ready=_build_canonical_opportunity_pipeline(
            settings, root, include_futures=True
        ),
        on_symbol_screen=_build_opportunity_screen(settings, root),
        retention=MarketUniverseRetention(
            archive_root=_absolute(settings.dataset_directory),
            source_cache_root=_absolute(
                getattr(
                    settings,
                    "market_history_source_cache_directory",
                    settings.dataset_directory.parent / "market_sources",
                )
            ),
            opportunity_monitor_root=(
                root / "runtime/artifacts/opportunity-radar/monitor"
            ).resolve(),
            futures_replay_root=(
                root / "runtime/data/datasets/futures/multitf"
            ).resolve(),
            futures_artifact_roots=(
                (root / "runtime/artifacts/validation/futures_multitf").resolve(),
                (
                    root / "runtime/artifacts/validation/futures_failure_tuning"
                ).resolve(),
            ),
        ),
    )


def _build_canonical_opportunity_pipeline(
    settings: Settings, root: Path, *, include_futures: bool = False
) -> Callable[[str, str, datetime], Mapping[str, object]]:
    """Build a bounded local-only stage that overlaps analysis with downloads."""

    limiter = BoundedSemaphore(settings.market_history_opportunity_workers)
    spot_archive = ParquetOHLCVArchive(_absolute(settings.dataset_directory) / "spot")

    def analyze(
        market: str, symbol: str, observed_at: datetime
    ) -> Mapping[str, object]:
        if market != "SPOT" and (market != "USD_M_FUTURES" or not include_futures):
            return {
                "status": "DELEGATED",
                "owner": "futures-multitf",
                "blockers": [],
                **_SAFE_STATE,
            }
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("opportunity analysis timestamp must be timezone-aware")
        directory = monitor_directory(root, market, symbol)
        with limiter:
            try:
                with SingleInstanceLease(directory / "refresh.lock"):
                    if market == "USD_M_FUTURES":
                        from ai4binance.cli.futures_multitf import (
                            _refresh_futures_monitor,
                        )

                        payload = _refresh_futures_monitor(
                            settings,
                            root,
                            symbol,
                            observed_at,
                            timeframes=VIRTUAL_MARKET_COLLECTION_TIMEFRAMES,
                        )
                    else:
                        payload = refresh_monitor(
                            root,
                            spot_archive,
                            market=market,
                            symbol=symbol,
                            now=observed_at.astimezone(UTC),
                            minimum_candles=settings.minimum_closed_candles,
                            candle_limit=settings.candle_limit,
                            timeframes=VIRTUAL_MARKET_COLLECTION_TIMEFRAMES,
                        )
            except RuntimeError as error:
                if str(error) != "runtime instance is already active":
                    raise
                return {
                    "status": "COALESCED",
                    "blockers": [],
                    "compute_profile": "CPU_REFERENCE",
                    "pipeline_mode": "OVERLAPPED_WITH_MARKET_DOWNLOAD",
                    **_SAFE_STATE,
                }
        raw_candidates = payload.get("candidates", ())
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
        decision_blockers = sorted(
            {
                str(blocker)
                for candidate in candidates
                if isinstance(candidate, Mapping)
                for blocker in candidate.get("blockers", ())
                if isinstance(blocker, str)
            }
        )
        raw_quality = payload.get("quality", ())
        quality = raw_quality if isinstance(raw_quality, list) else []
        raw_generation_health = payload.get("generation_health")
        generation_health = (
            dict(raw_generation_health)
            if isinstance(raw_generation_health, Mapping)
            else {
                "evaluated_attempt_count": 0,
                "published_opportunity_count": len(candidates),
                "rejected_attempt_count": 0,
                "rejected_by_stage": {},
                "rejected_by_reason": {},
                "recent_rejections": [],
            }
        )
        quality_by_timeframe = {
            str(row.get("timeframe")): row
            for row in quality
            if isinstance(row, Mapping)
        }
        data_blockers: list[str] = []
        for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES:
            quality_status = quality_by_timeframe.get(timeframe, {}).get(
                "status", "UNAVAILABLE"
            )
            if quality_status != "CURRENT":
                data_blockers.append(f"OPPORTUNITY_DATA_{quality_status}:{timeframe}")
        return {
            "status": "DATA_BLOCKED" if data_blockers else "CURRENT",
            "blockers": data_blockers,
            "decision_blockers": decision_blockers,
            "candidate_count": len(candidates),
            "generation_health": generation_health,
            "dashboard_candidates": _dashboard_candidate_projection(
                candidates, market=market, symbol=symbol
            ),
            "compute_profile": "CPU_REFERENCE",
            "pipeline_mode": "OVERLAPPED_WITH_MARKET_DOWNLOAD",
            **_SAFE_STATE,
        }

    return analyze


def _build_opportunity_screen(
    settings: Settings, root: Path
) -> Callable[[str, str, datetime], Mapping[str, object]]:
    limiter = BoundedSemaphore(settings.market_history_opportunity_workers)

    def screen(market: str, symbol: str, now: datetime) -> Mapping[str, object]:
        with limiter:
            result = screen_market_opportunities(
                ParquetOHLCVArchive(
                    _absolute(settings.dataset_directory) / market.lower()
                ),
                market=market,
                symbol=symbol,
                now=now,
                minimum_candles=settings.minimum_closed_candles,
                candle_limit=settings.candle_limit,
            )
            from ai4binance.infrastructure.persistence.safe_json import (
                write_json_object_verified,
            )

            write_json_object_verified(
                monitor_directory(root, market, symbol) / "screening.json",
                result,
                blocker="MARKET_SCREENING_DESTINATION_VERIFY_FAILED",
                subject_id=f"market-screening:{market}:{symbol}",
            )
            return result

    return screen


def run_market_history_command(
    command: str,
    settings: Settings,
    *,
    as_of: str | None,
    max_cycles: int | None,
    cleanup_apply: bool = False,
) -> int:
    """Run or inspect the research-only historical market-data collector."""

    synchronizer = build_market_history_synchronizer(settings)
    if command == "market-history-cleanup-legacy-1m":
        payload = LegacyOneMinuteCleanup(synchronizer.archive_root).run(
            apply=cleanup_apply
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not payload["blockers"] else 2
    if command == "market-history-status":
        try:
            payload = json.loads(synchronizer.state_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("market history status must be an object")
            if payload.get("schema_version") == "2.0":
                observed = datetime.fromisoformat(str(payload["observed_at"]))
                age = (datetime.now(UTC) - observed).total_seconds()
                if (
                    not 0
                    <= age
                    <= max(900, settings.market_history_live_interval_seconds * 3)
                ):
                    payload["status"] = "STALE"
                    existing_blockers = payload.get("blockers")
                    payload["blockers"] = [
                        *(
                            existing_blockers
                            if isinstance(existing_blockers, list)
                            else []
                        ),
                        "MARKET_HISTORY_STATE_STALE",
                    ]
        except (OSError, ValueError, KeyError, TypeError):
            payload = {
                "command": command,
                "status": "BLOCKED",
                "blockers": ("MARKET_HISTORY_STATE_UNAVAILABLE",),
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 2
        payload["command"] = command
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not payload.get("blockers") else 2

    continuous = build_continuous_market_history(
        settings,
        synchronizer,
        root=Path.cwd(),
        include_coin_m=getattr(settings, "market_history_coin_m_enabled", False),
    )
    if command == "market-history-sync" and as_of is None:
        with SingleInstanceLease(synchronizer.state_path.with_suffix(".lock")):
            payload = continuous.sync_cycle(observed_at=datetime.now(UTC))
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0 if not payload["blockers"] else 2

    if command == "market-history-sync":
        now = datetime.now(UTC)
        target_day = (
            _exclusive_as_of(as_of) - timedelta(days=1)
            if as_of
            else now.date() - timedelta(days=1)
        )
        with SingleInstanceLease(synchronizer.state_path.with_suffix(".lock")):
            report = synchronizer.sync_day(target_day, observed_at=now)
        payload = asdict(report)
        payload.update(
            {
                "command": command,
                "status": "DEGRADED" if report.blockers else "READY",
                "downloaded_bytes": report.downloaded_bytes,
                "network_request_count": report.network_request_count,
            }
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not report.blockers else 2

    if command == "market-history-daemon":
        depth = build_market_depth_collector(synchronizer, continuous)

        def cycle(now: datetime) -> object:
            if settings.market_depth_enabled:
                universe = synchronizer._eligible_universe(now)
                if not universe.blockers:
                    priority = tuple(
                        dict.fromkeys(
                            (
                                settings.symbol,
                                *settings.fixed_symbols,
                                *settings.priority_watchlist,
                            )
                        )
                    )
                    markets = _priority_depth_markets(
                        universe,
                        priority,
                        include_coin_m=continuous.coin_m is not None,
                    )
                    depth.start(markets)
            return continuous.sync_cycle(observed_at=now)

        supervisor = MarketHistorySupervisor(
            synchronizer=synchronizer,
            interval_seconds=settings.market_history_live_interval_seconds,
            lock_path=_absolute(settings.market_history_state_path).with_suffix(
                ".lock"
            ),
            cycle=cycle,
            on_recoverable_error=continuous.record_recoverable_cycle_failure,
        )
        try:
            completed = supervisor.run(max_cycles=max_cycles)
        except RuntimeError as error:
            payload = {
                "command": command,
                "status": "BLOCKED",
                "blockers": (
                    "MARKET_HISTORY_ALREADY_RUNNING"
                    if str(error) == "runtime instance is already active"
                    else "MARKET_HISTORY_RUNTIME_FAILURE",
                ),
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 2
        finally:
            depth.close()
        last_state = json.loads(synchronizer.state_path.read_text(encoding="utf-8"))
        payload = {
            "command": command,
            "status": "STOPPED",
            "completed_cycles": completed,
            "blockers": last_state.get(
                "blockers", ["MARKET_HISTORY_STATE_UNAVAILABLE"]
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not payload["blockers"] else 2
    raise ValueError(f"unsupported market history command: {command}")


def build_market_history_synchronizer(settings: Settings) -> MarketHistorySynchronizer:
    bands = RateLimitBands(
        soft_limit=settings.public_rate_limit_soft,
        warning=settings.public_rate_limit_warning,
        throttle=settings.public_rate_limit_throttle,
        hard_stop=settings.public_rate_limit_hard_stop,
    )
    spot_budget = PublicRequestBudget(governor=WeightedRateLimitGovernor(bands=bands))
    futures_budget = PublicRequestBudget(
        governor=WeightedRateLimitGovernor(bands=bands)
    )
    binance_provider = BinanceMarketUniverseProvider(
        spot_transport=MeteredPublicTransport(
            ReadOnlyBinanceJsonTransport(
                base_url="https://api.binance.com",
                allowed_prefixes=("/api/v3/",),
                timeout_seconds=settings.request_timeout_seconds,
                max_attempts=1,
                backoff_seconds=settings.request_backoff_seconds,
                response_headers_observer=spot_budget.observe_headers,
            ),
            _absolute(settings.dataset_directory) / "spot" / "metadata",
            budget=spot_budget,
        ),
        futures_transport=MeteredPublicTransport(
            ReadOnlyBinanceJsonTransport(
                base_url="https://fapi.binance.com",
                allowed_prefixes=("/fapi/v1/", "/futures/data/"),
                timeout_seconds=settings.request_timeout_seconds,
                max_attempts=1,
                backoff_seconds=settings.request_backoff_seconds,
                response_headers_observer=futures_budget.observe_headers,
            ),
            _absolute(settings.dataset_directory) / "usd_m_futures" / "metadata",
            budget=futures_budget,
        ),
        coin_m_transport=MeteredPublicTransport(
            ReadOnlyBinanceJsonTransport(
                base_url="https://dapi.binance.com",
                allowed_prefixes=("/dapi/v1/", "/futures/data/"),
                timeout_seconds=settings.request_timeout_seconds,
                max_attempts=1,
                response_headers_observer=futures_budget.observe_headers,
            ),
            _absolute(settings.dataset_directory) / "coin_m_futures" / "metadata",
            budget=futures_budget,
        )
        if settings.market_history_coin_m_enabled
        else None,
        quote_assets=settings.preferred_quote_assets,
        futures_symbol_exclusions=settings.futures_symbol_exclusions,
    )
    universe_provider = ResearchMarketUniverseProvider(
        binance=binance_provider,
        market_cap_transport=ReadOnlyCoinGeckoJsonTransport(
            timeout_seconds=settings.request_timeout_seconds,
            max_attempts=min(settings.request_max_attempts, 3),
        ),
        wallet_balance_path=(
            _absolute(settings.binance_accounting_directory)
            / "spot"
            / "balance_snapshots.jsonl"
        ),
        wallet_minimum_value_usdt=(settings.market_history_wallet_minimum_value_usdt),
        wallet_maximum_age=timedelta(minutes=settings.accounting_freshness_minutes),
        market_cap_asset_limit=settings.market_history_market_cap_asset_limit,
    )
    return MarketHistorySynchronizer(
        universe_provider=universe_provider,  # type: ignore[arg-type]
        archive_root=_absolute(settings.dataset_directory),
        source_cache=BinanceVisionArchiveCache.with_network(
            _absolute(settings.market_history_source_cache_directory),
            timeout_seconds=settings.request_timeout_seconds,
        ),
        state_path=_absolute(settings.market_history_state_path),
    )


def _exclusive_as_of(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("as_of must use YYYY-MM-DD") from None


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the standalone, research-only market-history command surface."""

    parser = argparse.ArgumentParser(
        description="AI4BINANCE checksum-verified public market-history collector."
    )
    parser.add_argument("command", choices=("sync", "status", "daemon", "cleanup-1m"))
    parser.add_argument(
        "--as-of",
        default=None,
        help="Exclusive YYYY-MM-DD date for a one-day closed-history sync.",
    )
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove only legacy 1m files with verified native replacements.",
    )
    parsed = parser.parse_args(arguments)
    command = {
        "sync": "market-history-sync",
        "status": "market-history-status",
        "daemon": "market-history-daemon",
        "cleanup-1m": "market-history-cleanup-legacy-1m",
    }[parsed.command]
    return run_market_history_command(
        command,
        Settings(),
        as_of=parsed.as_of,
        max_cycles=parsed.max_cycles,
        cleanup_apply=parsed.apply,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "build_continuous_market_history",
    "build_market_depth_collector",
    "build_market_history_synchronizer",
    "main",
    "run_market_history_command",
)
