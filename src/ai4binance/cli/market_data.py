"""CLI adapter for low-bandwidth public market-history synchronization."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from threading import BoundedSemaphore
from typing import cast

from ai4binance.application.opportunity_monitor import (
    monitor_directory,
    refresh_monitor,
)
from ai4binance.compatibility.opportunity_monitor import screen_market_opportunities
from ai4binance.config import Settings
from ai4binance.core.errors import ExchangeRateLimitError
from ai4binance.data.acquisition import ArchivedMarketSnapshotAcquisition
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.coin_observations import build_coin_observations
from ai4binance.data.legacy_1m_cleanup import LegacyOneMinuteCleanup
from ai4binance.data.market_depth import MarketDepthCollector
from ai4binance.data.market_history_continuous import (
    VIRTUAL_MARKET_COLLECTION_TIMEFRAMES,
    ContinuousMarketHistory,
    MeteredPublicTransport,
    PublicRequestBudget,
)
from ai4binance.data.market_history_sync import (
    MARKET_HISTORY_TIMEFRAMES,
    BinanceVisionArchiveCache,
    MarketHistorySupervisor,
    MarketHistorySynchronizer,
)
from ai4binance.data.market_universe_retention import MarketUniverseRetention
from ai4binance.data.scoped_history import profile_health, verified_selection
from ai4binance.data.weekly_volume import (
    ScopedRetryPolicy,
    WeeklyVolumeRanking,
    active_shared_circuit,
    load_evidence,
    record_public_response,
    record_shared_cooldown,
)
from ai4binance.domain.opportunity_observation import (
    has_complete_measurable_opportunity,
)
from ai4binance.domain.universe import RESEARCH_MARKET_UNIVERSE_SOURCE
from ai4binance.exchange.rate_limit import RateLimitBands, WeightedRateLimitGovernor
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified
from ai4binance.integrations.binance import (
    BinanceMarketUniverseProvider,
    ReadOnlyBinanceJsonTransport,
)
from ai4binance.integrations.research_market_universe import (
    ReadOnlyCoinGeckoJsonTransport,
    ResearchMarketUniverseProvider,
)
from ai4binance.ops.runtime import SingleInstanceLease
from ai4binance.schemas import DataQuality
from ai4binance.wire_contracts import market_snapshot_to_wire

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

    collector = ContinuousMarketHistory(
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
        follow_wall_clock=True,
        minimum_candles=settings.minimum_closed_candles,
        required_candles_by_timeframe=settings.virtual_market_period_lengths,
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
        on_symbol_screen=(
            None
            if settings.market_history_full_universe
            else _build_opportunity_screen(settings, root)
        ),
        # Historical membership changes must not erase OOS source evidence.
        retention=None
        if settings.market_history_full_universe
        else MarketUniverseRetention(
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
    if getattr(settings, "market_history_acquisition_profile", "canonical") == (
        "top5-1000-month"
    ):
        root = synchronizer.source_cache.root / "profiles" / "top5-1000-month"
        collector.scoped_selection = load_evidence(root / "selection-active.json")
        collector.pages_per_stream = 1
        collector.archives_per_stream = 1
        collector.follow_wall_clock = False
        collector.on_symbol_ready = None
        collector.on_symbol_screen = None
        collector.retention = None
        collector.scoped_retry_settings = _top5_retry_settings(settings)
    return collector


def _build_canonical_opportunity_pipeline(
    settings: Settings, root: Path, *, include_futures: bool = False
) -> Callable[[str, str, datetime], Mapping[str, object]]:
    """Build a bounded local-only stage that overlaps analysis with downloads."""

    limiter = BoundedSemaphore(settings.market_history_opportunity_workers)
    spot_archive = ParquetOHLCVArchive(_absolute(settings.dataset_directory) / "spot")
    analysis_timeframes = (
        MARKET_HISTORY_TIMEFRAMES
        if settings.market_history_full_universe
        else VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
    )

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
                            timeframes=analysis_timeframes,
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
                            timeframes=analysis_timeframes,
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
    if command == "market-history-rank-proposal":
        public_provider = replace(
            cast(ResearchMarketUniverseProvider, synchronizer.universe_provider),
            manual_selection_path=None,
            cache_source=RESEARCH_MARKET_UNIVERSE_SOURCE,
        )
        proposal = public_provider.priority_eligible_market_snapshot()
        assets = proposal.market_cap_assets
        spot_by_asset = public_provider._symbols_by_asset(proposal.spot_symbols)
        futures_by_asset = public_provider._symbols_by_asset(proposal.futures_symbols)
        payload = {
            "command": command,
            "status": "BLOCKED" if proposal.blockers else "REVIEW_ONLY",
            "source": proposal.source,
            "spot_assets": [asset for asset in assets if asset in spot_by_asset],
            "usd_m_futures_assets": [
                asset for asset in assets if asset in futures_by_asset
            ],
            "blockers": proposal.blockers,
            "manual_selection_path": str(settings.market_history_manual_universe_path),
            "manual_selection_modified": False,
            **_SAFE_STATE,
        }
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 2 if proposal.blockers else 0
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
        except OSError, ValueError, KeyError, TypeError:
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
        manual_selection_path=_absolute(settings.market_history_manual_universe_path),
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


def run_archive_snapshot_command(
    settings: Settings,
    *,
    cutoff: datetime,
    symbol: str | None = None,
    require_futures_enrichment: bool = False,
) -> int:
    """Publish research snapshots through the existing collector's archives."""
    if cutoff.utcoffset() is None or cutoff > datetime.now(UTC):
        raise ValueError("snapshot cutoff must be aware and cannot be in the future")
    synchronizer = build_market_history_synchronizer(settings)
    universe = synchronizer._eligible_universe(datetime.now(UTC))
    if universe.blockers:
        print(json.dumps({"status": "BLOCKED", "blockers": universe.blockers}))
        return 2
    selected = symbol.strip().upper() if symbol is not None else None
    if selected is not None and selected not in (
        *universe.spot_symbols,
        *universe.futures_symbols,
    ):
        raise ValueError("snapshot symbol must belong to the canonical universe")
    output_root = Path.cwd() / "runtime/artifacts/data/snapshots"
    required_lengths = {
        timeframe: settings.virtual_market_period_lengths[timeframe]
        for timeframe in ("15m", "1h", "4h", "1d")
    }
    results: list[dict[str, object]] = []
    for market, directory, symbols in (
        ("SPOT", "spot", universe.spot_symbols),
        ("USD_M_FUTURES", "usd_m_futures", universe.futures_symbols),
    ):
        acquisition = ArchivedMarketSnapshotAcquisition(
            ParquetOHLCVArchive(synchronizer.archive_root / directory),
            market,
            history_limit=max(required_lengths.values()),
            minimum_closed_candles=settings.minimum_closed_candles,
            require_futures_enrichment=require_futures_enrichment,
            local_candle_limits=required_lengths,
        )
        for instrument in symbols:
            if selected is not None and instrument != selected:
                continue
            snapshot = acquisition.acquire(
                instrument, ("15m", "1h", "4h", "1d"), cutoff=cutoff
            )
            digest = str(snapshot.market_metadata["semantic_sha256"])
            path = output_root / f"{directory}-{instrument}-{digest}.json"
            wire = market_snapshot_to_wire(snapshot)
            evidence = {
                "snapshot": wire,
                "semantic_sha256": digest,
                "source_lineage": {
                    key: dict(value)
                    for key, value in cast(
                        Mapping[str, Mapping[str, object]],
                        snapshot.market_metadata["source_lineage"],
                    ).items()
                },
                "blocking_reasons": list(
                    cast(Sequence[str], snapshot.market_metadata["blocking_reasons"])
                ),
                "publication_time_status": "NOT_VERIFIED",
                "historical_live_availability_verified": False,
                "requires_futures_enrichment": require_futures_enrichment,
                "optional_enrichment": {
                    name: {"status": "NOT_VERIFIED", "required": False}
                    for name in (
                        "open_interest",
                        "settled_funding",
                        "funding_configuration",
                        "mark_price",
                        "index_price",
                        "premium_index",
                        "long_short",
                        "taker_statistics",
                        "basis",
                    )
                },
                **_SAFE_STATE,
            }
            write_json_object_verified(
                path, evidence, blocker="ARCHIVE_SNAPSHOT_WRITE_FAILED", indent=2
            )
            results.append(
                {
                    "market": market,
                    "symbol": instrument,
                    "snapshot_id": snapshot.snapshot_id,
                    "semantic_sha256": digest,
                    "status": "READY"
                    if snapshot.data_quality is DataQuality.DATA_VALID
                    else "BLOCKED",
                    "blocking_reasons": list(
                        cast(
                            Sequence[str], snapshot.market_metadata["blocking_reasons"]
                        )
                    ),
                    "artifact_path": str(path),
                }
            )
    coin_path = output_root / "coin-observations-latest.json"
    coin_report = build_coin_observations(
        synchronizer.archive_root,
        Path.cwd() / "runtime/artifacts/data/futures-replay",
        results,
        cutoff,
    )
    write_json_object_verified(
        coin_path, coin_report, blocker="COIN_OBSERVATIONS_WRITE_FAILED", indent=2
    )
    report = {
        "command": "market-history-snapshot",
        "cutoff": cutoff.astimezone(UTC).isoformat(),
        "status": "READY"
        if all(r["status"] == "READY" for r in results)
        else "BLOCKED",
        "scope": "PILOT" if selected is not None else "CANONICAL_UNIVERSE",
        "universe_source": universe.source,
        "results": results,
        "required_futures_enrichment_verified": False,
        "requires_futures_enrichment": require_futures_enrichment,
        "coin_observations_path": str(coin_path),
        "coin_observations_status": coin_report["status"],
        **_SAFE_STATE,
    }
    write_json_object_verified(
        output_root / "latest.json",
        report,
        blocker="ARCHIVE_SNAPSHOT_REPORT_WRITE_FAILED",
        indent=2,
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "READY" else 2


def run_top5_profile_command(
    settings: Settings, *, command: str, cutoff: datetime | None
) -> int:
    """Explicit acquisition profile invocation with unchanged canonical defaults."""
    settings = settings.model_copy(update={"request_timeout_seconds": 30.0})
    synchronizer = build_market_history_synchronizer(settings)
    provider = cast(ResearchMarketUniverseProvider, synchronizer.universe_provider)
    evidence_root = synchronizer.source_cache.root / "profiles" / "top5-1000-month"
    for metered in (
        provider.binance.spot_transport,
        provider.binance.futures_transport,
    ):
        adapter = cast(MeteredPublicTransport, metered)
        adapter.transport = replace(
            cast(ReadOnlyBinanceJsonTransport, adapter.transport),
            response_bytes_observer=partial(record_public_response, evidence_root),
        )
    if command == "weekly-rank":
        ranking = WeeklyVolumeRanking(
            provider.binance.spot_transport,
            provider.binance.futures_transport,
            evidence_root,
            retry_policy=ScopedRetryPolicy(**_top5_retry_settings(settings)),
            futures_exclusions=settings.futures_symbol_exclusions,
        )
        verified_cutoff = _top5_verified_cutoff(provider, cutoff, evidence_root)
        ranking_lock = (evidence_root / "ranking.lock").resolve()
        if ranking_lock.exists():
            raise ValueError("ranking writer lock must be preserved for owner review")
        with SingleInstanceLease(ranking_lock):
            report = ranking.run(cutoff=verified_cutoff)
    else:
        selection = load_evidence(evidence_root / "selection-active.json")
        verified_selection(selection)
        continuous = build_continuous_market_history(
            settings, synchronizer, root=Path.cwd(), include_coin_m=False
        )
        continuous.scoped_selection = selection
        continuous.pages_per_stream = 1
        continuous.archives_per_stream = 1
        continuous.follow_wall_clock = False
        continuous.required_candles_by_timeframe = (
            settings.virtual_market_period_lengths
        )
        continuous.on_symbol_ready = None
        continuous.on_symbol_screen = None
        continuous.retention = None
        continuous.scoped_retry_settings = _top5_retry_settings(settings)
        selected_cutoff = cutoff or datetime.now(UTC)
        if selected_cutoff.utcoffset() is None or selected_cutoff > datetime.now(UTC):
            raise ValueError("profile cutoff must be aware and cannot be in the future")
        if command in {"snapshot", "status"}:
            report = profile_health(continuous, cutoff=selected_cutoff)
        elif command == "sync":
            lock = _absolute(settings.market_history_state_path).with_suffix(".lock")
            if lock.exists():
                print(
                    json.dumps(
                        {
                            "status": "BLOCKED",
                            "blockers": [
                                "CANONICAL_MARKET_HISTORY_WRITER_LOCK_PRESENT"
                            ],
                            "lock_path": str(lock),
                            **_SAFE_STATE,
                        }
                    )
                )
                return 2
            with SingleInstanceLease(lock):
                report = continuous.sync_cycle(observed_at=selected_cutoff)
        else:
            raise ValueError(
                "TOP5 supports explicit ranking, sync, status and snapshot only"
            )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"candidates", "streams"}
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if report["status"] in {"VERIFIED", "DATA_READY"} else 2


def _top5_retry_settings(settings: Settings) -> dict[str, int]:
    return {
        "attempts_per_episode": settings.market_history_retry_episode_attempts,
        "attempts_per_hour": settings.market_history_retry_hourly_attempts,
        "cooldown_seconds": settings.market_history_retry_cooldown_seconds,
    }


def _top5_verified_cutoff(
    provider: ResearchMarketUniverseProvider, cutoff: datetime | None, root: Path
) -> datetime:
    times: list[datetime] = []
    for market, transport, path in (
        ("spot", provider.binance.spot_transport, "/api/v3/time"),
        ("usd_m_futures", provider.binance.futures_transport, "/fapi/v1/time"),
    ):
        if active_shared_circuit(root, market, datetime.now(UTC)):
            raise ValueError("SHARED_SOURCE_COOLDOWN")
        try:
            payload = transport.get_json(path)
        except ExchangeRateLimitError as error:
            record_shared_cooldown(root, market, error)
            raise
        if not isinstance(payload, dict) or not isinstance(
            payload.get("serverTime"), int
        ):
            raise ValueError("official server time is not verified")
        times.append(datetime.fromtimestamp(payload["serverTime"] / 1000, UTC))
    if abs((times[0] - times[1]).total_seconds()) > 60:
        raise ValueError("official market clocks are inconsistent")
    value = cutoff or min(times)
    if value.utcoffset() is None or value > min(times):
        raise ValueError("ranking cutoff exceeds a verified official clock")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the standalone, research-only market-history command surface."""

    parser = argparse.ArgumentParser(
        description="AI4BINANCE checksum-verified public market-history collector."
    )
    parser.add_argument(
        "command",
        choices=(
            "sync",
            "status",
            "daemon",
            "cleanup-1m",
            "rank-proposal",
            "snapshot",
            "weekly-rank",
        ),
    )
    parser.add_argument(
        "--profile",
        choices=("canonical", "top5-1000-month"),
        default="canonical",
        help="Public acquisition scope; strategy warmup and live gates stay intact.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Exclusive YYYY-MM-DD date for a one-day closed-history sync.",
    )
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument(
        "--cutoff", help="Explicit UTC decision cutoff for archived snapshots."
    )
    parser.add_argument(
        "--symbol", help="Optional canonical instrument for a snapshot pilot."
    )
    parser.add_argument(
        "--require-futures-enrichment",
        action="store_true",
        help="Fail closed when the consumer requires verified Futures enrichment.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove only legacy 1m files with verified native replacements.",
    )
    parsed = parser.parse_args(arguments)
    if parsed.command == "weekly-rank" or parsed.profile == "top5-1000-month":
        return run_top5_profile_command(
            Settings(),
            command=parsed.command,
            cutoff=datetime.fromisoformat(parsed.cutoff) if parsed.cutoff else None,
        )
    if parsed.command == "snapshot":
        if parsed.cutoff is None:
            parser.error("snapshot requires --cutoff")
        return run_archive_snapshot_command(
            Settings(),
            cutoff=datetime.fromisoformat(parsed.cutoff),
            symbol=parsed.symbol,
            require_futures_enrichment=parsed.require_futures_enrichment,
        )
    command = {
        "sync": "market-history-sync",
        "status": "market-history-status",
        "daemon": "market-history-daemon",
        "cleanup-1m": "market-history-cleanup-legacy-1m",
        "rank-proposal": "market-history-rank-proposal",
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
