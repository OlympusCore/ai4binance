"""Read-only runtime command handlers."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import ReadOnlyRuntimeCycle
from ai4binance.application.context.memory import GovernedMemoryCycleBridge
from ai4binance.application.learning_loop import (
    ControlledLearningLoop,
    PaperLedgerLearningEvidenceProvider,
)
from ai4binance.application.runtime import (
    DualMarketAdvisoryReport,
    MarketAdvisory,
    RuntimeOpportunityReviewItem,
)
from ai4binance.cli.bootstrap.shared import virtual_market_gate_payload
from ai4binance.config import Settings
from ai4binance.core.errors import ExchangeError
from ai4binance.enterprise import GpuResourceGovernor
from ai4binance.exchange import (
    BinancePrivateAccountReader,
    BinanceUsdMPrivateAccountReader,
    PrivateCredentials,
    SignedReadOnlyRequestFactory,
    SignedUsdMReadOnlyRequestFactory,
    UrllibPrivateJsonTransport,
)
from ai4binance.execution import PaperLedger
from ai4binance.external_intel.retrieval.feeds import FeedEntry, parse_feed
from ai4binance.infrastructure.persistence.memory import JsonlMemoryStore
from ai4binance.learning.engine import ControlledLearningEngine
from ai4binance.learning.lifecycle import (
    GovernedLessonLifecycleStore,
    GovernedLessonLifecycleWorker,
)
from ai4binance.learning.storage import LearningStore
from ai4binance.ops import (
    PrivateRuntimeStatusStore,
    RuntimeManagementLedger,
    RuntimeStatusStore,
    RuntimeSupervisor,
    SingleInstanceLease,
)
from ai4binance.ops.startup_replay import startup_replay_payload
from ai4binance.ops.user_reports import (
    UserReportPaths,
    canonical_system_root,
    render_professional_summary,
    user_report_paths,
    write_user_report_files,
)
from ai4binance.outlook import MarketOutlookArtifactStore
from ai4binance.portfolio import (
    CostBasisService,
    FallbackSpotPriceReader,
    FuturesAccountSnapshotService,
    InvestmentManagementAssistant,
    MarketManagementContext,
    OpportunityReviewItem,
    PortfolioAnalyticsService,
    WalletSnapshotService,
)
from ai4binance.portfolio.risk_budget import PortfolioRiskPolicy
from ai4binance.reporting import to_primitive
from ai4binance.research_runtime import build_research_application_service
from ai4binance.runtime_research_context import (
    RuntimeContextAcquirer,
    RuntimeResearchContextLoader,
)
from ai4binance.schemas import MarketSnapshot
from ai4binance.storage import JsonlAuditStore, write_json_object_verified
from ai4binance.validation.futures_oos import (
    FuturesOosEvidenceQuery,
    FuturesOosEvidenceReader,
    FuturesOosEvidenceResolver,
    runtime_futures_strategy_sha256,
)
from ai4binance.virtual_wallet_journal import VirtualWalletJournal
from ai4binance.whale_fusion.derivatives import BinanceUsdMClient
from ai4binance.whale_fusion.features import DerivativesFeatureEngine
from ai4binance.whale_fusion.models import DerivativesMetric, PriceOiRegime

from .bootstrap import SnapshotAcquirer
from .bootstrap.shared import build_public_acquisition

_NEWS_FEED_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"
_SOCIAL_FEED_URL = "https://www.reddit.com/r/CryptoCurrency/new/.rss"
_TECHNOLOGY_FEED_URL = "https://github.blog/changelog/feed/"
_ALLOWED_REFRESH_FEED_URLS = (
    _NEWS_FEED_URL,
    _SOCIAL_FEED_URL,
    _TECHNOLOGY_FEED_URL,
)
_FEED_USER_AGENT = "ai4binance-runtime-research/1.0"
_RUNTIME_REFRESH_MAX_ITEMS = 3
_RESIDENT_RESEARCH_REFRESH_INTERVAL = timedelta(minutes=15)
_RUNTIME_TRACE_REPORT_NAME = "trace-validation-latest.json"
_VIRTUAL_MARKET_STATE_NAME = "virtual-market.json"
_VIRTUAL_MARKET_LOCK_NAME = "virtual-market.lock"
_VIRTUAL_MARKET_REFRESH_REQUEST_NAME = "virtual-market-refresh-request.json"
_MARKET_HISTORY_REFRESH_REQUEST_NAME = "market-history-refresh-request.json"
_DASHBOARD_SIMULATION_MAX_SYMBOLS = 1_000
_DASHBOARD_SIMULATION_MAX_BLOCKERS = 12
_VIRTUAL_MARKET_UNIVERSE_LIMIT = 50
_NEWS_ASSET_ALIASES = {
    "BTC": ("bitcoin",),
    "ETH": ("ethereum", "ether"),
    "BNB": ("bnb",),
    "SOL": ("solana",),
    "XRP": ("xrp", "ripple"),
    "DOGE": ("dogecoin",),
    "ADA": ("cardano",),
    "AVAX": ("avalanche",),
    "DOT": ("polkadot",),
    "LINK": ("chainlink",),
}
_POSITIVE_SENTIMENT_TOKENS = (
    "approval",
    "partnership",
    "launch",
    "listing",
    "upgrade",
    "inflow",
    "record",
    "growth",
    "adoption",
    "support",
)
_NEGATIVE_SENTIMENT_TOKENS = (
    "hack",
    "exploit",
    "outage",
    "delay",
    "lawsuit",
    "ban",
    "delist",
    "breach",
    "liquidation",
    "attack",
)


@dataclass(frozen=True, slots=True)
class _LocalFirstPublicAcquisition:
    """Read the shared canonical archive and fail closed when it is unavailable."""

    primary: SnapshotAcquirer

    def acquire(self, symbol: str, timeframes: tuple[str, ...]) -> MarketSnapshot:
        return self.primary.acquire(symbol, timeframes)


_WebFeedItem = FeedEntry


class RuntimeFuturesAdvisor:
    def __init__(
        self,
        collector: BinanceUsdMClient | None,
        feature_engine: DerivativesFeatureEngine | None = None,
        oos_evidence: FuturesOosEvidenceResolver | None = None,
        timeframe: str = "1h",
    ) -> None:
        if timeframe not in {"5m", "15m", "1h", "4h", "1d"}:
            raise ValueError("runtime futures timeframe is unsupported")
        self.timeframe = timeframe
        self.collector = collector
        self.feature_engine = feature_engine or DerivativesFeatureEngine()
        self.oos_evidence = oos_evidence
        self.strategy_sha256 = runtime_futures_strategy_sha256(
            short_lookback=self.feature_engine.short_lookback,
            medium_lookback=self.feature_engine.medium_lookback,
        )

    def build(self, snapshot: object) -> MarketAdvisory:
        snapshot_obj = cast(Any, snapshot)
        if self.collector is None:
            return MarketAdvisory(
                market="USD_M_FUTURES",
                action="NO_TRADE",
                bias="NEUTRAL",
                setup_radar=(),
                blockers=("CANONICAL_FUTURES_DERIVATIVES_UNAVAILABLE",),
                wallet_status="READY",
            )
        symbol = snapshot_obj.symbol
        timeframe_map = snapshot_obj.ohlcv_by_timeframe
        dataset = self.collector.collect(symbol, self.timeframe, 100)
        oi_count = len(dataset.values(DerivativesMetric.OPEN_INTEREST))
        candles = timeframe_map.get(self.timeframe, ())
        prices = tuple(Decimal(str(candle.close)) for candle in candles[-oi_count:])
        features = self.feature_engine.compute(dataset, prices)
        bias = {
            PriceOiRegime.NEW_LONG_PARTICIPATION: "BULLISH",
            PriceOiRegime.SHORT_COVERING: "BULLISH_CAUTION",
            PriceOiRegime.NEW_SHORT_PRESSURE: "BEARISH",
            PriceOiRegime.DELEVERAGING: "BEARISH_CAUTION",
            PriceOiRegime.FLAT_OR_MIXED: "NEUTRAL",
        }[features.price_oi_regime]
        oos_validated = (
            self.oos_evidence is not None
            and self.oos_evidence.is_validated(
                FuturesOosEvidenceQuery(
                    symbol=features.symbol,
                    timeframe=self.timeframe,
                    setup_name=features.price_oi_regime.value,
                    strategy_sha256=self.strategy_sha256,
                    as_of=features.as_of,
                )
            )
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *features.blockers,
                    *(() if oos_validated else ("FUTURES_OOS_NOT_APPROVED",)),
                )
            )
        )
        return MarketAdvisory(
            market="USD_M_FUTURES",
            action="NO_TRADE",
            bias=bias,
            setup_radar=(features.price_oi_regime.value,),
            blockers=blockers,
            wallet_status="READY",
            opportunity_radar=(
                RuntimeOpportunityReviewItem(
                    setup_name=features.price_oi_regime.value,
                    timeframe=self.timeframe,
                    direction=bias,
                    status="FUTURES_RESEARCH_RADAR",
                    promotion_status="RESEARCH_ONLY",
                    setup_tier="C",
                    score=50.0,
                    confidence=0.35,
                    blockers=blockers,
                ),
            ),
        )


class RuntimeInvestmentManager:
    def __init__(
        self,
        assistant: InvestmentManagementAssistant | None = None,
    ) -> None:
        self.assistant = assistant or InvestmentManagementAssistant()

    def review(
        self,
        *,
        symbol: str,
        spot_wallet: object | None,
        futures_account: object | None,
        spot: MarketAdvisory,
        futures: MarketAdvisory,
        portfolio_analytics: object | None = None,
    ) -> object:
        return self.assistant.review(
            symbol=symbol,
            spot_wallet=cast(Any, spot_wallet),
            futures_account=cast(Any, futures_account),
            spot=self._context(spot),
            futures=self._context(futures),
            portfolio_analytics=cast(Any, portfolio_analytics),
        )

    @staticmethod
    def _context(advisory: MarketAdvisory) -> MarketManagementContext:
        return MarketManagementContext(
            advisory.market,
            advisory.action,
            advisory.bias,
            advisory.setup_radar,
            advisory.blockers,
            tuple(
                RuntimeInvestmentManager._item(item)
                for item in advisory.opportunity_radar
            ),
        )

    @staticmethod
    def _item(item: object) -> OpportunityReviewItem:
        item_obj = cast(Any, item)
        return OpportunityReviewItem(
            setup_name=str(item_obj.setup_name),
            timeframe=str(item_obj.timeframe),
            direction=str(item_obj.direction),
            status=str(item_obj.status),
            promotion_status=str(item_obj.promotion_status),
            setup_tier=str(item_obj.setup_tier),
            score=float(item_obj.score),
            confidence=float(item_obj.confidence),
            blockers=tuple(cast(tuple[str, ...], getattr(item_obj, "blockers", ()))),
        )


def build_read_only_runtime(settings: Settings) -> ReadOnlyRuntimeCycle:
    """Build the resident wallet-first runtime without any write endpoint."""
    public_acquisition = build_public_acquisition(settings)
    runtime_symbol = _canonical_resident_runtime_symbol(
        settings,
        datetime.now(UTC),
    )
    context_loader = RuntimeResearchContextLoader(
        news_feed_path=settings.runtime_news_feed_path,
        social_feed_path=settings.runtime_social_feed_path,
        content_feed_path=settings.runtime_content_feed_path,
        technology_feed_path=settings.runtime_technology_feed_path,
        context_ledger_path=settings.runtime_context_ledger_path,
        opportunity_report_path=settings.runtime_opportunity_report_path,
        max_file_bytes=settings.runtime_context_max_file_bytes,
        max_event_age=timedelta(hours=settings.runtime_context_max_event_age_hours),
        max_tracking_entries=settings.runtime_context_max_tracking_entries,
    )
    spot_wallet_service: WalletSnapshotService | None = None
    futures_account_service: FuturesAccountSnapshotService | None = None
    cost_basis_service: CostBasisService | None = None
    try:
        credentials = PrivateCredentials.from_environment_or_file(
            settings.private_credentials_file
        )
    except ValueError:
        credentials = None
    if credentials is not None:
        private_transport = UrllibPrivateJsonTransport(
            timeout_seconds=settings.request_timeout_seconds,
            max_attempts=settings.request_max_attempts,
            backoff_seconds=settings.request_backoff_seconds,
        )
        spot_reader = BinancePrivateAccountReader(
            SignedReadOnlyRequestFactory(credentials), private_transport
        )
        spot_wallet_service = WalletSnapshotService(spot_reader)
        cost_basis_service = CostBasisService(spot_reader)
        futures_account_service = FuturesAccountSnapshotService(
            BinanceUsdMPrivateAccountReader(
                SignedUsdMReadOnlyRequestFactory(credentials), private_transport
            )
        )
    from ai4binance.data.acquisition import (
        LocalMarketPublicClient,
        LocalMarketSnapshotTransport,
    )

    price_snapshot_directory = settings.dataset_directory / "spot" / "metadata"
    price_snapshot_maximum_age = max(
        900, settings.market_history_live_interval_seconds * 3
    )
    analytics_prices = FallbackSpotPriceReader(
        primary=LocalMarketPublicClient(
            LocalMarketSnapshotTransport(
                price_snapshot_directory,
                maximum_age_seconds=price_snapshot_maximum_age,
                ticker_snapshot_filename="wallet-price-coverage.json",
            )
        ),
        fallback=LocalMarketPublicClient(
            LocalMarketSnapshotTransport(
                price_snapshot_directory,
                maximum_age_seconds=price_snapshot_maximum_age,
            )
        ),
    )
    return ReadOnlyRuntimeCycle(
        symbol=runtime_symbol,
        timeframes=settings.timeframes,
        spot_acquirer=RuntimeContextAcquirer(public_acquisition, context_loader),
        spot_wallet_service=spot_wallet_service,
        futures_account_service=futures_account_service,
        futures_advisor=RuntimeFuturesAdvisor(
            None,
            oos_evidence=FuturesOosEvidenceReader(
                settings.futures_oos_artifact_directory
            ),
        ),
        investment_manager=RuntimeInvestmentManager(),
        analytics_service=PortfolioAnalyticsService(
            analytics_prices,
            concentration_limit=settings.portfolio_concentration_limit,
            risk_policy=PortfolioRiskPolicy(
                maximum_gross_usdt=settings.portfolio_maximum_gross_usdt,
                maximum_symbol_usdt=settings.portfolio_maximum_symbol_usdt,
                maximum_correlation_group_usdt=(
                    settings.portfolio_maximum_correlation_group_usdt
                ),
                maximum_strategy_usdt=settings.portfolio_maximum_strategy_usdt,
            ),
        ),
        cost_basis_service=cost_basis_service,
        research_service=build_research_application_service(
            orchestrator=EnterpriseOrchestrator(
                minimum_candles=settings.minimum_closed_candles
            ),
            audit_store=JsonlAuditStore.chained_successor(
                settings.audit_directory / "runtime_research_events.jsonl"
            ),
            memory_bridge=GovernedMemoryCycleBridge(
                JsonlMemoryStore(settings.governed_memory_path)
            ),
            learning_loop=ControlledLearningLoop(
                LearningStore(
                    settings.learning_summary_path,
                    settings.learning_audit_path,
                ),
                ControlledLearningEngine(),
                lifecycle_worker=GovernedLessonLifecycleWorker(
                    GovernedLessonLifecycleStore(
                        settings.governed_lessons_path,
                        settings.governed_lessons_audit_path,
                    )
                ),
            ),
            learning_evidence_provider=PaperLedgerLearningEvidenceProvider(
                PaperLedger(settings.paper_ledger_path)
            ),
            outlook_store=MarketOutlookArtifactStore(
                settings.evidence_artifact_directory
                / "market-outlook"
                / "runtime-state.json"
            ),
        ),
        account_wide_monitoring=True,
    )


def _canonical_resident_runtime_symbol(
    settings: Settings,
    observed_at: datetime,
) -> str:
    """Select one deterministic resident symbol from the shared Spot universe."""

    configured = tuple(
        dict.fromkeys(
            (
                settings.symbol,
                *settings.fixed_symbols,
                *settings.priority_watchlist,
            )
        )
    )
    ranked = _virtual_market_ranked_symbols(settings, configured, observed_at)
    if settings.symbol in ranked:
        return settings.symbol
    return ranked[0] if ranked else settings.symbol


def run_runtime_command(
    command: str,
    settings: Settings,
    *,
    max_cycles: int | None,
    public_acquisition: SnapshotAcquirer | None = None,
) -> int:
    if command in {"virtual-market-once", "virtual-runtime-once", "virtual-runtime"}:
        payload = virtual_runtime_payload(command=command)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if command in {"virtual-market-soak", "virtual-runtime-soak"}:
        payload = virtual_market_soak_payload()
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if command == "virtual-market-daemon":
        return run_virtual_market_daemon(
            settings,
            max_cycles=max_cycles,
            public_acquisition=public_acquisition,
        )
    if command == "runtime-research-refresh-once":
        payload, exit_code = run_runtime_research_refresh_once(settings)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return exit_code
    if command == "runtime-once":
        payload, exit_code = _run_runtime_once(settings)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return exit_code
    runtime = build_read_only_runtime(settings)
    last_feed_refresh: datetime | None = None

    def resident_cycle() -> DualMarketAdvisoryReport:
        nonlocal last_feed_refresh
        now = datetime.now(UTC)
        if (
            last_feed_refresh is None
            or now - last_feed_refresh >= _RESIDENT_RESEARCH_REFRESH_INTERVAL
        ):
            last_feed_refresh = now
            try:
                refresh = _refresh_runtime_research_feeds(settings)
                write_json_object_verified(
                    _resolve_path(
                        Path("runtime/state/runtime_research/feed-refresh-health.json")
                    ),
                    refresh,
                    blocker="RUNTIME_RESEARCH_REFRESH_HEALTH_WRITE_FAILED",
                    subject_id="resident-research-feed-refresh",
                    indent=2,
                )
            except (OSError, TypeError, ValueError):
                # Feed availability must not stop the read-only runtime. The feed
                # remains stale and downstream freshness checks fail closed.
                pass
        return runtime.run()

    lease = SingleInstanceLease(settings.runtime_state_path.with_suffix(".lock"))
    try:
        with lease:
            RuntimeSupervisor(
                cycle=resident_cycle,
                store=RuntimeStatusStore(settings.runtime_state_path),
                interval_seconds=settings.runtime_cycle_interval_seconds,
                private_store=PrivateRuntimeStatusStore(
                    settings.private_runtime_state_path,
                    settings.private_runtime_ledger_path,
                    settings.binance_accounting_directory,
                ),
                management_ledger=RuntimeManagementLedger(
                    settings.management_ledger_path
                ),
            ).run(max_cycles=max_cycles)
        return 0
    except (KeyboardInterrupt, RuntimeError):
        return 2


def run_virtual_market_daemon(
    settings: Settings,
    *,
    max_cycles: int | None,
    public_acquisition: SnapshotAcquirer | None = None,
    cycle_runner: Callable[[Settings, SnapshotAcquirer], int] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Run bounded public-research cycles continuously with live orders blocked."""

    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    acquisition = public_acquisition or _build_virtual_market_acquisition(settings)
    state_path = settings.runtime_state_path.with_name(_VIRTUAL_MARKET_STATE_NAME)
    lock_path = settings.runtime_state_path.with_name(_VIRTUAL_MARKET_LOCK_NAME)
    refresh_request_path = settings.runtime_state_path.with_name(
        _VIRTUAL_MARKET_REFRESH_REQUEST_NAME
    )
    last_success_at = _previous_virtual_market_success(state_path)
    previous = _load_json_mapping(state_path) or {}
    last_symbol = str(previous.get("symbol", ""))
    discovery_symbol = str(previous.get("discovery_symbol", last_symbol))
    priority_symbol = str(previous.get("priority_symbol", ""))
    scan_sequence = previous.get("scan_sequence", 0)
    if (
        not isinstance(scan_sequence, int)
        or isinstance(scan_sequence, bool)
        or scan_sequence < 0
    ):
        scan_sequence = 0
    last_order_ready_at = previous.get("last_order_ready_at")
    dashboard_simulation_projection = previous.get(
        "dashboard_simulation_projection", {}
    )
    consecutive_failures = 0
    cycle_count = 0
    with SingleInstanceLease(lock_path):
        while max_cycles is None or cycle_count < max_cycles:
            cycle_count += 1
            cycle_report: dict[str, object] = {}
            manual_request: dict[str, object] | None = None
            eligible_symbols: tuple[str, ...] = ()
            try:
                if cycle_runner is not None:
                    exit_code = cycle_runner(settings, acquisition)
                else:
                    from ai4binance.data.market_history_sync import (
                        read_cached_market_universe,
                    )
                    from ai4binance.integrations.research_market_universe import (
                        RESEARCH_MARKET_UNIVERSE_SOURCE,
                    )

                    universe = read_cached_market_universe(
                        settings.market_history_source_cache_directory
                        / "universe-v3.json",
                        clock(),
                        expected_source=RESEARCH_MARKET_UNIVERSE_SOURCE,
                    )
                    configured = tuple(
                        dict.fromkeys(
                            (
                                settings.symbol,
                                *settings.fixed_symbols,
                                *settings.priority_watchlist,
                            )
                        )
                    )
                    symbols = (
                        tuple(
                            name for name in configured if name in universe.spot_symbols
                        )
                        + tuple(
                            name
                            for name in universe.spot_symbols
                            if name not in configured
                        )
                        if universe is not None
                        else (
                            _virtual_market_ranked_symbols(
                                settings,
                                configured,
                                clock(),
                            )
                            or configured
                        )
                    )
                    from ai4binance.exchange.client import BinancePublicClient

                    supported_symbols: list[str] = []
                    unsupported_symbols: list[str] = []
                    for name in symbols:
                        try:
                            BinancePublicClient._symbol(name)
                        except ValueError:
                            unsupported_symbols.append(name)
                        else:
                            supported_symbols.append(name)
                    cycle_report.update(
                        universe_symbol_count=len(symbols),
                        supported_symbol_count=len(supported_symbols),
                        unsupported_symbols=tuple(unsupported_symbols),
                        unsupported_symbol_reason=(
                            "PUBLIC_DATA_CLIENT_SYMBOL_UNSUPPORTED"
                            if unsupported_symbols
                            else None
                        ),
                    )
                    symbols = tuple(supported_symbols)
                    eligible_symbols = symbols
                    if not symbols:
                        raise ValueError("VIRTUAL_MARKET_UNIVERSE_EMPTY")
                    manual_request = _pending_virtual_market_refresh_request(
                        refresh_request_path, symbols, clock()
                    )
                    if manual_request is not None:
                        last_symbol = str(manual_request["symbol"])
                        scan_lane = "MANUAL_REFRESH"
                        priority_symbols: tuple[str, ...] = ()
                    else:
                        priority_symbols = (
                            _virtual_market_priority_symbols(
                                settings, configured, symbols, clock()
                            )
                            if universe is not None
                            else ()
                        )
                        held_symbols = _virtual_wallet_journal(
                            settings
                        ).open_position_symbols()
                        priority_symbols = tuple(
                            dict.fromkeys((*held_symbols, *priority_symbols))
                        )[: settings.virtual_market_priority_symbol_count]
                        scan_sequence += 1
                        use_priority = bool(priority_symbols) and scan_sequence % 5 == 0
                        active_symbols = priority_symbols if use_priority else symbols
                        cursor = priority_symbol if use_priority else discovery_symbol
                        index = (
                            (active_symbols.index(cursor) + 1) % len(active_symbols)
                            if cursor in active_symbols
                            else 0
                        )
                        last_symbol = active_symbols[index]
                        scan_lane = "PRIORITY" if use_priority else "DISCOVERY"
                        if use_priority:
                            priority_symbol = last_symbol
                        else:
                            discovery_symbol = last_symbol
                    cycle_settings = settings.model_copy(update={"symbol": last_symbol})
                    from ai4binance.data.market_history_continuous import (
                        VIRTUAL_MARKET_COLLECTION_TIMEFRAMES,
                    )

                    cycle_settings = cycle_settings.model_copy(
                        update={"timeframes": VIRTUAL_MARKET_COLLECTION_TIMEFRAMES}
                    )
                    cycle_report.update(
                        {
                            "symbol": last_symbol,
                            "scan_sequence": scan_sequence,
                            "scan_lane": scan_lane,
                            "priority_symbol": priority_symbol,
                            "discovery_symbol": discovery_symbol,
                            "priority_symbol_count": len(priority_symbols),
                            "universe_source": (
                                "CANONICAL_CACHE"
                                if universe is not None
                                else "LOCAL_SNAPSHOT"
                                if symbols != configured
                                else "CONFIGURED_FALLBACK"
                            ),
                        }
                    )
                    cycle_observed_at = clock()
                    exit_code = _run_virtual_market_research_cycle(
                        cycle_settings,
                        acquisition,
                        observed_at=cycle_observed_at,
                        cycle_report=cycle_report,
                    )
                    _request_market_history_refresh_if_stale(
                        state_path.with_name(_MARKET_HISTORY_REFRESH_REQUEST_NAME),
                        symbol=last_symbol,
                        eligible_symbols=eligible_symbols,
                        observed_at=cycle_observed_at,
                        cycle_report=cycle_report,
                    )
            except (ExchangeError, OSError, RuntimeError, TypeError, ValueError):
                exit_code = 2
            observed_at = clock()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("virtual market daemon clock must be timezone-aware")
            observed_at = observed_at.astimezone(UTC)
            if exit_code == 0:
                last_success_at = observed_at
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            if cycle_report.get("virtual_order_ready") is True and exit_code == 0:
                last_order_ready_at = observed_at.isoformat()
            if eligible_symbols:
                dashboard_simulation_projection = _dashboard_simulation_projection(
                    dashboard_simulation_projection,
                    symbols=eligible_symbols,
                    observed_at=observed_at,
                    exit_code=exit_code,
                    cycle_report=cycle_report,
                )
            payload = _virtual_market_daemon_state(
                observed_at=observed_at,
                cycle_count=cycle_count,
                exit_code=exit_code,
                last_success_at=last_success_at,
            )
            payload.update(cast(dict[str, object], to_primitive(cycle_report)))
            if isinstance(dashboard_simulation_projection, dict):
                payload["dashboard_simulation_projection"] = (
                    dashboard_simulation_projection
                )
            payload["consecutive_failures"] = consecutive_failures
            payload["last_order_ready_at"] = last_order_ready_at
            payload["research_status"] = (
                "CYCLE_FAILED"
                if exit_code != 0
                else "RUNNING_WITH_BLOCKERS"
                if cycle_report.get("research_blockers")
                else "ORDER_READY"
                if cycle_report.get("virtual_order_ready") is True
                else "OBSERVING"
                if "snapshot_id" in cycle_report
                else "NOT_VERIFIED"
            )
            write_json_object_verified(
                state_path,
                payload,
                blocker="VIRTUAL_MARKET_STATE_WRITE_FAILED",
                subject_id="virtual-market-daemon",
                indent=2,
            )
            if manual_request is not None:
                _complete_virtual_market_refresh_request(
                    refresh_request_path,
                    manual_request,
                    observed_at,
                    exit_code,
                    cycle_report,
                )
            print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            sys.stdout.flush()
            if max_cycles is not None and cycle_count >= max_cycles:
                break
            sleeper(
                settings.virtual_market_cycle_interval_seconds
                if cycle_runner is None
                else settings.runtime_cycle_interval_seconds
            )
    return exit_code


def _pending_virtual_market_refresh_request(
    path: Path,
    eligible_symbols: tuple[str, ...],
    observed_at: datetime,
) -> dict[str, object] | None:
    """Read one bounded dashboard request without widening simulation authority."""

    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 16_384:
        raise ValueError("VIRTUAL_MARKET_REFRESH_REQUEST_INVALID")
    value = _load_json_mapping(path)
    if value is None or value.get("status") != "PENDING":
        return None
    if set(value) != {
        "schema_version",
        "request_id",
        "requested_at",
        "market",
        "symbol",
        "status",
        "execution_allowed",
        "promotion_status",
        "live_eligibility_status",
    }:
        raise ValueError("VIRTUAL_MARKET_REFRESH_REQUEST_INVALID")
    requested_at = datetime.fromisoformat(str(value["requested_at"]))
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("VIRTUAL_MARKET_REFRESH_REQUEST_TIMESTAMP_INVALID")
    age = observed_at.astimezone(UTC) - requested_at.astimezone(UTC)
    if age < timedelta(minutes=-1) or age > timedelta(minutes=10):
        return None
    if (
        value.get("schema_version") != "VirtualMarketRefreshRequest/v1"
        or value.get("market") != "SPOT"
        or value.get("symbol") not in eligible_symbols
        or value.get("execution_allowed") is not False
        or value.get("promotion_status") != "RESEARCH_ONLY"
        or value.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("VIRTUAL_MARKET_REFRESH_REQUEST_INVALID")
    return dict(value)


def _complete_virtual_market_refresh_request(
    path: Path,
    request: dict[str, object],
    observed_at: datetime,
    exit_code: int,
    cycle_report: dict[str, object],
) -> None:
    raw_blockers = cycle_report.get("research_blockers", ())
    blockers = tuple(raw_blockers) if isinstance(raw_blockers, (list, tuple)) else ()
    result = {
        **request,
        "status": "COMPLETED" if exit_code == 0 else "FAILED",
        "completed_at": observed_at.isoformat(),
        "exit_code": exit_code,
        "snapshot_id": cycle_report.get("snapshot_id"),
        "virtual_decision_status": cycle_report.get(
            "virtual_decision_status", "NOT_EVALUATED"
        ),
        "virtual_order_ready": cycle_report.get("virtual_order_ready") is True,
        "candidate_count": cycle_report.get("candidate_count", 0),
        "blockers": blockers,
    }
    write_json_object_verified(
        path,
        cast(dict[str, object], to_primitive(result)),
        blocker="VIRTUAL_MARKET_REFRESH_REQUEST_WRITE_FAILED",
        subject_id=str(request["request_id"]),
        indent=2,
    )


def _virtual_market_priority_symbols(
    settings: Settings,
    configured: tuple[str, ...],
    eligible: tuple[str, ...],
    observed_at: datetime,
) -> tuple[str, ...]:
    """Schedule canonical liquidity priorities using shared public files only."""

    return tuple(
        symbol
        for symbol in _virtual_market_ranked_symbols(
            settings,
            configured,
            observed_at,
        )
        if symbol in eligible
    )[: settings.virtual_market_priority_symbol_count]


def _virtual_market_ranked_symbols(
    settings: Settings,
    configured: tuple[str, ...],
    observed_at: datetime,
) -> tuple[str, ...]:
    """Read the bounded Spot universe from the current canonical snapshots."""

    from ai4binance.data.acquisition import LocalMarketSnapshotTransport
    from ai4binance.integrations.binance.market_universe_provider import (
        BinanceMarketUniverseProvider,
    )

    local = LocalMarketSnapshotTransport(
        settings.dataset_directory / "spot" / "metadata",
        maximum_age_seconds=900,
        clock=lambda: observed_at,
    )
    try:
        ranked = BinanceMarketUniverseProvider(
            local,
            local,
            max_symbols_per_market=_VIRTUAL_MARKET_UNIVERSE_LIMIT,
        ).spot_symbols(configured)
    except (ExchangeError, OSError, TypeError, ValueError):
        return ()
    return tuple(
        item.symbol
        for item in ranked
        if item.data_quality_ok and item.status == "TRADING"
    )


def _build_virtual_market_acquisition(settings: Settings) -> SnapshotAcquirer:
    primary = build_public_acquisition(settings)
    return _LocalFirstPublicAcquisition(primary=primary)


def _run_virtual_market_research_cycle(
    settings: Settings,
    public_acquisition: SnapshotAcquirer,
    *,
    observed_at: datetime,
    cycle_report: dict[str, object] | None = None,
) -> int:
    from ai4binance.cli.research import run_public_research_command

    journal = _virtual_wallet_journal(settings)
    exit_code = run_public_research_command(
        "research-public",
        settings,
        public_acquisition=public_acquisition,
        whale_fusion_cycle=None,
        cycle_report=cycle_report,
        virtual_wallet_journal=journal,
    )
    if cycle_report is not None:
        cycle_report["daily_loss_tuning"] = _run_virtual_loss_tuning(
            settings,
            journal,
            observed_at,
        )
    return exit_code


def _request_market_history_refresh_if_stale(
    path: Path,
    *,
    symbol: str,
    eligible_symbols: tuple[str, ...],
    observed_at: datetime,
    cycle_report: dict[str, object],
) -> None:
    """Request one bounded canonical refresh after a stale virtual snapshot."""

    raw_blockers = cycle_report.get("research_blockers", ())
    blockers = (
        tuple(item for item in raw_blockers if isinstance(item, str))
        if isinstance(raw_blockers, (list, tuple))
        else ()
    )
    if not any(item.startswith("STALE_CANDLES:") for item in blockers):
        return
    from ai4binance.data.market_history_continuous import (
        enqueue_market_history_refresh_request,
    )

    try:
        refresh = enqueue_market_history_refresh_request(
            path,
            market="SPOT",
            symbol=symbol,
            eligible_symbols=eligible_symbols,
            requested_at=observed_at,
            requester="VIRTUAL_MARKET",
        )
    except (OSError, ValueError):
        cycle_report["market_history_refresh"] = {
            "state": "DATA_BLOCKED",
            "blockers": ["VIRTUAL_MARKET_REFRESH_REQUEST_FAILED"],
        }
        return
    cycle_report["market_history_refresh"] = refresh


def _virtual_wallet_journal(settings: Settings) -> VirtualWalletJournal:
    return VirtualWalletJournal(
        ledger_path=settings.virtual_wallet_ledger_path,
        state_path=settings.virtual_wallet_state_path,
        report_root=_virtual_wallet_report_root(settings.virtual_wallet_state_path),
    )


def _run_virtual_loss_tuning(
    settings: Settings,
    journal: VirtualWalletJournal,
    observed_at: datetime,
) -> dict[str, object]:
    """Run canonical Spot backtest/tuning after three same-day virtual losses."""

    safe_state = {
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    try:
        trigger = journal.daily_loss_tuning_trigger(observed_at)
    except (OSError, RuntimeError, TypeError, ValueError):
        return {
            "status": "BLOCKED",
            "blockers": ["VIRTUAL_LOSS_TUNING_TRIGGER_UNAVAILABLE"],
            "parameter_application": "NOT_APPLIED",
            **safe_state,
        }
    if trigger.get("status") != "TRIGGERED":
        return {**trigger, "parameter_application": "NOT_APPLIED"}
    trigger_id = str(trigger.get("trigger_id", ""))
    if not re.fullmatch(r"virtual-loss-tuning:[0-9a-f]{24}", trigger_id):
        return {
            "status": "BLOCKED",
            "blockers": ["VIRTUAL_LOSS_TUNING_TRIGGER_INVALID"],
            "parameter_application": "NOT_APPLIED",
            **safe_state,
        }
    tuning_root = settings.validation_artifact_directory / "virtual_loss_tuning"
    artifact_path = tuning_root / f"{trigger_id.rsplit(':', maxsplit=1)[-1]}.json"
    existing = _load_json_mapping(artifact_path)
    if existing:
        if (
            existing.get("trigger_id") != trigger_id
            or existing.get("execution_allowed") is not False
            or existing.get("promotion_status") != "RESEARCH_ONLY"
            or existing.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            return {
                "status": "BLOCKED",
                "blockers": ["VIRTUAL_LOSS_TUNING_ARTIFACT_INVALID"],
                "parameter_application": "NOT_APPLIED",
                **safe_state,
            }
        if existing.get("status") == "RESEARCH_TUNING_COMPLETED":
            return {
                "status": "ALREADY_REVIEWED",
                "trigger_id": trigger_id,
                "artifact_path": str(artifact_path),
                "parameter_application": "NOT_APPLIED",
                **safe_state,
            }
        attempted_at = existing.get("attempted_at")
        try:
            previous_attempt = datetime.fromisoformat(str(attempted_at)).astimezone(UTC)
        except (TypeError, ValueError):
            previous_attempt = observed_at.astimezone(UTC) - timedelta(hours=1)
        if observed_at.astimezone(UTC) - previous_attempt < timedelta(minutes=15):
            return {
                "status": "RETRY_PENDING",
                "trigger_id": trigger_id,
                "artifact_path": str(artifact_path),
                "blockers": existing.get("blockers", []),
                "parameter_application": "NOT_APPLIED",
                **safe_state,
            }

    from ai4binance.application.validation_pipeline import VALIDATED_PLAYBOOKS
    from ai4binance.data import DatasetIntegrityError, ParquetOHLCVArchive
    from ai4binance.validation_pipeline_runtime import (
        SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO,
        HistoricalValidationRuntime,
    )

    raw_subjects = trigger.get("subjects")
    subjects = raw_subjects if isinstance(raw_subjects, list) else []
    archive = ParquetOHLCVArchive(
        settings.dataset_directory / "spot"
        if settings.market_history_local_candles
        else settings.dataset_directory
    )
    runtime = HistoricalValidationRuntime(
        report_directory=settings.backtest_report_directory / "virtual_loss_tuning",
        position_notional_to_equity_ratio=(SPOT_VALIDATION_NOTIONAL_TO_EQUITY_RATIO),
    )
    results: list[dict[str, object]] = []
    aggregate_blockers: list[str] = []
    for raw_subject in subjects[:3]:
        if not isinstance(raw_subject, Mapping):
            aggregate_blockers.append("VIRTUAL_LOSS_TUNING_SUBJECT_INVALID")
            continue
        market = str(raw_subject.get("market", "")).upper()
        symbol = str(raw_subject.get("symbol", "")).upper()
        timeframe = str(raw_subject.get("timeframe", ""))
        playbook = str(raw_subject.get("strategy_id", ""))
        subject = {
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy_id": playbook,
        }
        if market != "SPOT" or playbook not in VALIDATED_PLAYBOOKS:
            blocker = "VIRTUAL_LOSS_TUNING_SUBJECT_UNSUPPORTED"
            aggregate_blockers.append(blocker)
            results.append(
                {"subject": subject, "status": "BLOCKED", "blockers": [blocker]}
            )
            continue
        try:
            candles = archive.read(symbol, timeframe)
            result = runtime.validate_one(
                symbol,
                timeframe,
                playbook,
                candles,
                artifact_directory=tuning_root / "evidence",
            )
            tuning = cast(Any, result.tuning)
            backtest = cast(Any, result.backtest)
            if tuning is None or backtest is None:
                raise ValueError("VIRTUAL_LOSS_TUNING_RESULT_INCOMPLETE")
            results.append(
                {
                    "subject": subject,
                    "status": "RESEARCH_TUNING_COMPLETED",
                    "dataset_sha256": runtime.dataset_sha256(candles),
                    "backtest_metrics": to_primitive(backtest.metrics),
                    "tuning_report_id": tuning.report_id,
                    "candidate_count": tuning.search_space.candidate_count,
                    "selected_parameters": to_primitive(tuning.selected_parameters),
                    "tuning_blockers": list(tuning.blockers),
                    "validation_blockers": list(result.blockers),
                    "parameter_application": "NOT_APPLIED",
                }
            )
        except (
            DatasetIntegrityError,
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ):
            blocker = "VIRTUAL_LOSS_TUNING_DATA_OR_VALIDATION_UNAVAILABLE"
            aggregate_blockers.append(blocker)
            results.append(
                {"subject": subject, "status": "BLOCKED", "blockers": [blocker]}
            )
    if not subjects:
        aggregate_blockers.append("VIRTUAL_LOSS_TUNING_SUBJECTS_MISSING")
    status = (
        "RESEARCH_TUNING_COMPLETED"
        if results
        and all(item.get("status") == "RESEARCH_TUNING_COMPLETED" for item in results)
        else "RETRY_PENDING"
    )
    payload = {
        "schema_version": "VirtualLossTuningResult/v1",
        "status": status,
        "trigger_id": trigger_id,
        "trigger": trigger,
        "attempted_at": observed_at.astimezone(UTC).isoformat(),
        "results": results,
        "blockers": list(dict.fromkeys(aggregate_blockers)),
        "parameter_application": "NOT_APPLIED",
        **safe_state,
    }
    write_json_object_verified(
        artifact_path,
        payload,
        blocker="VIRTUAL_LOSS_TUNING_WRITE_FAILED",
        subject_id=trigger_id,
        indent=2,
        durable=True,
    )
    return {**payload, "artifact_path": str(artifact_path)}


def _virtual_wallet_report_root(state_path: Path) -> Path:
    resolved = state_path.resolve()
    for parent in resolved.parents:
        if parent.name == "runtime":
            return parent.parent
    return Path.cwd().resolve()


def _previous_virtual_market_success(path: Path) -> datetime | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        value = payload.get("last_success_at")
        if not isinstance(value, str) or not value.strip():
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)
    except (AttributeError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def _dashboard_simulation_projection(
    previous: object,
    *,
    symbols: tuple[str, ...],
    observed_at: datetime,
    exit_code: int,
    cycle_report: Mapping[str, object],
) -> dict[str, object]:
    """Persist bounded all-symbol virtual-simulation coverage for the dashboard."""

    eligible_symbols = tuple(sorted(set(symbols)))[:_DASHBOARD_SIMULATION_MAX_SYMBOLS]
    eligible_set = set(eligible_symbols)
    previous_records = (
        previous.get("symbol_observations") if isinstance(previous, Mapping) else []
    )
    records_by_symbol: dict[str, dict[str, object]] = {}
    if isinstance(previous_records, list):
        for row in previous_records:
            if not isinstance(row, Mapping):
                continue
            symbol = row.get("symbol")
            if not isinstance(symbol, str) or symbol not in eligible_set:
                continue
            records_by_symbol[symbol] = {
                "symbol": symbol,
                "observed_at": row.get("observed_at"),
                "scan_lane": row.get("scan_lane"),
                "state": row.get("state"),
                "virtual_decision_status": row.get("virtual_decision_status"),
                "virtual_order_ready": row.get("virtual_order_ready") is True,
                "candidate_count": row.get("candidate_count"),
                "blockers": (
                    [
                        value
                        for value in row.get("blockers", [])
                        if isinstance(value, str)
                    ]
                    if isinstance(row.get("blockers"), (list, tuple))
                    else []
                )[:_DASHBOARD_SIMULATION_MAX_BLOCKERS],
            }
    symbol = cycle_report.get("symbol")
    if isinstance(symbol, str) and symbol in eligible_set:
        raw_blockers = cycle_report.get("research_blockers", ())
        blockers = (
            [value for value in raw_blockers if isinstance(value, str)]
            if isinstance(raw_blockers, (list, tuple))
            else []
        )
        candidate_count = cycle_report.get("candidate_count", 0)
        records_by_symbol[symbol] = {
            "symbol": symbol,
            "observed_at": observed_at.isoformat(),
            "scan_lane": cycle_report.get("scan_lane", "UNAVAILABLE"),
            "state": "COMPLETED" if exit_code == 0 else "FAILED",
            "virtual_decision_status": cycle_report.get(
                "virtual_decision_status", "NOT_EVALUATED"
            ),
            "virtual_order_ready": cycle_report.get("virtual_order_ready") is True,
            "candidate_count": (
                candidate_count
                if isinstance(candidate_count, int)
                and not isinstance(candidate_count, bool)
                and candidate_count >= 0
                else 0
            ),
            "blockers": blockers[:_DASHBOARD_SIMULATION_MAX_BLOCKERS],
        }
    records = [records_by_symbol[symbol] for symbol in sorted(records_by_symbol)]
    scanned = len(records)
    complete = bool(eligible_symbols) and scanned == len(eligible_symbols)
    previous_completed_at = (
        previous.get("last_full_coverage_at") if isinstance(previous, Mapping) else None
    )
    return {
        "status": "COMPLETE" if complete else "IN_PROGRESS",
        "eligible_symbol_count": len(eligible_symbols),
        "scanned_symbol_count": scanned,
        "pending_symbol_count": len(eligible_symbols) - scanned,
        "candidate_symbol_count": sum(
            1
            for record in records
            if isinstance(value := record.get("candidate_count"), int)
            and not isinstance(value, bool)
            and value > 0
        ),
        "order_ready_symbol_count": sum(
            record["virtual_order_ready"] is True for record in records
        ),
        "last_full_coverage_at": (
            observed_at.isoformat() if complete else previous_completed_at
        ),
        "symbol_observations": records,
    }


def _virtual_market_daemon_state(
    *,
    observed_at: datetime,
    cycle_count: int,
    exit_code: int,
    last_success_at: datetime | None,
) -> dict[str, object]:
    gate = virtual_market_gate_payload()
    return {
        "command": "virtual-market-daemon",
        "status": "RUNNING" if exit_code == 0 else "DEGRADED",
        "pid": os.getpid(),
        "updated_at": observed_at.isoformat(),
        "last_success_at": (
            last_success_at.isoformat() if last_success_at is not None else None
        ),
        "cycle_count": cycle_count,
        "cycle_exit_code": exit_code,
        "cycle_blockers": [] if exit_code == 0 else ["VIRTUAL_MARKET_CYCLE_FAILED"],
        "execution_surface": gate["execution_surface"],
        "authority_profile_id": gate["authority_profile_id"],
        "automation_mode": gate["automation_mode"],
        "bounded_simulation_only": gate["bounded_simulation_only"],
        "virtual_simulation_allowed": gate["virtual_simulation_allowed"],
        "paper_execution_allowed": gate["paper_execution_allowed"],
        "external_order_allowed": False,
        "live_order_allowed": False,
        "safety_constraints": list(cast(tuple[str, ...], gate["blockers"])),
        "promotion_status": "RESEARCH_ONLY",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def virtual_runtime_payload(
    *, command: str = "virtual-market-once"
) -> dict[str, object]:
    return {
        "command": command,
        "status": "READY",
        **virtual_market_gate_payload(),
    }


def virtual_market_soak_payload(sample_count: int = 3) -> dict[str, object]:
    if sample_count < 2:
        raise ValueError("virtual-market soak requires at least two samples")
    observed_at = datetime.now(UTC)
    gate_payload = virtual_market_gate_payload()
    gate_serialized = json.dumps(gate_payload, ensure_ascii=False, sort_keys=True)
    gate_sha256 = hashlib.sha256(gate_serialized.encode("utf-8")).hexdigest()
    samples = []
    sample_hashes = []
    for index in range(sample_count):
        sample_observed_at = observed_at + timedelta(milliseconds=index)
        sample = {
            "sample_index": index,
            "observed_at": sample_observed_at.isoformat(),
            "gate_sha256": gate_sha256,
            "execution_allowed": gate_payload["execution_allowed"],
            "live_eligibility_status": gate_payload["live_eligibility_status"],
            "blockers": gate_payload["blockers"],
        }
        samples.append(sample)
        sample_hashes.append(gate_sha256)
    artifact_path = (
        Path.cwd()
        / "runtime"
        / "artifacts"
        / "virtual-market"
        / "runtime-soak"
        / "latest.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "command": "virtual-market-soak",
        "status": "READY",
        "sample_count": sample_count,
        "samples": samples,
        "gate_payload": gate_payload,
        "gate_sha256": gate_sha256,
        "stable_gate_hashes": len(set(sample_hashes)) == 1,
        "artifact_path": str(artifact_path),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": gate_payload["blockers"],
    }
    artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def run_runtime_research_refresh_once(
    settings: Settings,
) -> tuple[dict[str, object], int]:
    refresh_payload = _refresh_runtime_research_feeds(settings)
    refresh_blockers = _text_sequence(refresh_payload.get("blockers"))
    if refresh_blockers:
        payload: dict[str, object] = {
            "command": "runtime-research-refresh-once",
            "status": "BLOCKED",
            "feed_refresh": refresh_payload,
            "runtime_cycle": None,
            "trace_validation": None,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "blockers": refresh_blockers,
        }
        return payload, 2

    runtime_cycle_payload, runtime_exit_code = _run_runtime_once(settings)
    trace_payload, trace_exit_code = _validate_runtime_research_traceability(settings)

    runtime_blockers = _text_sequence(runtime_cycle_payload.get("blockers"))
    blockers: list[str] = []
    if trace_exit_code != 0:
        blockers.extend(_text_sequence(trace_payload.get("blockers")))
        if not blockers:
            blockers.append("RUNTIME_RESEARCH_TRACE_VALIDATION_FAILED")
    elif runtime_exit_code != 0:
        blockers.append("RUNTIME_ONCE_DEGRADED")

    status = "PASS"
    if trace_exit_code != 0:
        status = "BLOCKED"
    elif runtime_exit_code != 0:
        status = "PASS_WITH_RUNTIME_DEGRADED"

    payload = {
        "command": "runtime-research-refresh-once",
        "status": status,
        "feed_refresh": refresh_payload,
        "runtime_cycle": {
            "cycle_id": runtime_cycle_payload.get("cycle_id"),
            "created_at": runtime_cycle_payload.get("created_at"),
            "state": runtime_cycle_payload.get("state"),
            "exit_code": runtime_exit_code,
            "blocker_count": len(runtime_blockers),
        },
        "trace_validation": {
            "status": trace_payload.get("status"),
            "report_path": trace_payload.get("report_path"),
            "opportunity_count": trace_payload.get("opportunity_count"),
            "validated_count": trace_payload.get("validated_count"),
            "all_opportunities_traceable": trace_payload.get(
                "all_opportunities_traceable"
            ),
            "mismatch_count": trace_payload.get("mismatch_count"),
        },
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": tuple(dict.fromkeys(blockers)),
    }
    return payload, 0 if status != "BLOCKED" else 2


def _run_runtime_once(settings: Settings) -> tuple[dict[str, object], int]:
    startup_replay = startup_replay_payload(settings)
    runtime = build_read_only_runtime(settings)
    report = runtime.run()
    RuntimeStatusStore(settings.runtime_state_path).save(report)
    PrivateRuntimeStatusStore(
        settings.private_runtime_state_path,
        settings.private_runtime_ledger_path,
        settings.binance_accounting_directory,
    ).save(report)
    RuntimeManagementLedger(settings.management_ledger_path).append(report)
    payload = runtime_payload(report)
    payload["startup_replay"] = startup_replay
    startup_replay_blockers = _text_sequence(startup_replay.get("blockers"))
    if startup_replay_blockers:
        payload["blockers"] = tuple(
            dict.fromkeys(
                (
                    *_text_sequence(payload.get("blockers")),
                    *startup_replay_blockers,
                )
            )
        )
        if payload.get("state") == "READY":
            payload["state"] = "DEGRADED"
    user_report_paths_payload, user_report_blockers = (
        _write_virtual_portfolio_user_report(settings, payload)
    )
    if user_report_paths_payload:
        payload["user_report_paths"] = user_report_paths_payload
    if user_report_blockers:
        payload["blockers"] = tuple(
            dict.fromkeys(
                (
                    *_text_sequence(payload.get("blockers")),
                    *user_report_blockers,
                )
            )
        )
    return payload, 0 if payload.get("state") == "READY" else 2


def _refresh_runtime_research_feeds(settings: Settings) -> dict[str, object]:
    fetched_at = datetime.now(UTC)
    max_file_bytes = settings.runtime_context_max_file_bytes
    blockers: list[str] = []

    news_items, news_blocker = _fetch_feed_items_with_blocker(
        _NEWS_FEED_URL,
        max_items=_RUNTIME_REFRESH_MAX_ITEMS,
        max_file_bytes=max_file_bytes,
        blocker="RUNTIME_NEWS_FEED_REFRESH_FAILED",
    )
    social_items, social_blocker = _fetch_feed_items_with_blocker(
        _SOCIAL_FEED_URL,
        max_items=_RUNTIME_REFRESH_MAX_ITEMS,
        max_file_bytes=max_file_bytes,
        blocker="RUNTIME_SOCIAL_FEED_REFRESH_FAILED",
    )
    technology_items, technology_blocker = _fetch_feed_items_with_blocker(
        _TECHNOLOGY_FEED_URL,
        max_items=_RUNTIME_REFRESH_MAX_ITEMS,
        max_file_bytes=max_file_bytes,
        blocker="RUNTIME_TECHNOLOGY_FEED_REFRESH_FAILED",
    )
    for blocker in (news_blocker, social_blocker, technology_blocker):
        if blocker is not None:
            blockers.append(blocker)

    if blockers:
        return {
            "status": "BLOCKED",
            "fetched_at": fetched_at.isoformat(),
            "counts": {
                "news": len(news_items),
                "social": len(social_items),
                "content": len(news_items),
                "technology": len(technology_items),
            },
            "domains": {
                "news": _domain_list(news_items),
                "social": _domain_list(social_items),
                "content": _domain_list(news_items),
                "technology": _domain_list(technology_items),
            },
            "blockers": tuple(dict.fromkeys(blockers)),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    eligible_symbols = _eligible_news_symbols(settings)
    news_rows = [
        _news_row(item, fetched_at, eligible_symbols=eligible_symbols)
        for item in news_items
    ]
    social_rows = [_social_row(item) for item in social_items]
    content_rows = [_content_row(item) for item in news_items]
    technology_rows = [_technology_row(item, fetched_at) for item in technology_items]

    _write_jsonl_rows(_resolve_path(settings.runtime_news_feed_path), news_rows)
    _write_jsonl_rows(_resolve_path(settings.runtime_social_feed_path), social_rows)
    _write_jsonl_rows(_resolve_path(settings.runtime_content_feed_path), content_rows)
    _write_jsonl_rows(
        _resolve_path(settings.runtime_technology_feed_path),
        technology_rows,
    )
    user_reports, user_report_blockers = _write_runtime_research_user_reports(
        settings,
        fetched_at=fetched_at,
        news_rows=news_rows,
        social_rows=social_rows,
        content_rows=content_rows,
        technology_rows=technology_rows,
    )

    return {
        "status": "READY",
        "fetched_at": fetched_at.isoformat(),
        "counts": {
            "news": len(news_rows),
            "social": len(social_rows),
            "content": len(content_rows),
            "technology": len(technology_rows),
        },
        "domains": {
            "news": _domain_list(news_items),
            "social": _domain_list(social_items),
            "content": _domain_list(news_items),
            "technology": _domain_list(technology_items),
        },
        "feed_paths": {
            "news": str(_resolve_path(settings.runtime_news_feed_path)),
            "social": str(_resolve_path(settings.runtime_social_feed_path)),
            "content": str(_resolve_path(settings.runtime_content_feed_path)),
            "technology": str(_resolve_path(settings.runtime_technology_feed_path)),
        },
        "user_report_paths": user_reports,
        "blockers": user_report_blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _fetch_feed_items_with_blocker(
    source_url: str,
    *,
    max_items: int,
    max_file_bytes: int,
    blocker: str,
) -> tuple[tuple[_WebFeedItem, ...], str | None]:
    try:
        items = _fetch_feed_items(
            source_url,
            max_items=max_items,
            max_file_bytes=max_file_bytes,
        )
    except (OSError, ValueError):
        return (), blocker
    if not items:
        return (), blocker
    return items, None


def _write_runtime_research_user_reports(
    settings: Settings,
    *,
    fetched_at: datetime,
    news_rows: list[dict[str, object]],
    social_rows: list[dict[str, object]],
    content_rows: list[dict[str, object]],
    technology_rows: list[dict[str, object]],
) -> tuple[dict[str, dict[str, str]], tuple[str, ...]]:
    root = _user_report_root(settings.runtime_context_ledger_path)
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    blockers: list[str] = []
    report_paths: dict[str, dict[str, str]] = {}

    try:
        news_paths = user_report_paths(
            root,
            "news",
            stamp,
            file_stem="news_report",
            latest_stem="latest",
        )
        news_payload = {
            "command": "runtime-research-refresh-once",
            "report_type": "news",
            "observed_at": fetched_at.isoformat(),
            "status": "READY",
            "counts": {
                "news": len(news_rows),
                "social": len(social_rows),
                "content": len(content_rows),
            },
            "news": news_rows,
            "social": social_rows,
            "content": content_rows,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_user_report_files(
            news_paths,
            news_payload,
            _render_runtime_research_markdown(
                title="AI4Binance News and Content Report",
                observed_at=fetched_at.isoformat(),
                status="READY",
                summary=(
                    "The latest local research refresh collected bounded news, "
                    "social, and content context for decision support."
                ),
                sections=(
                    ("News", _feed_report_lines(news_rows, title_field="title")),
                    (
                        "Social Context",
                        _feed_report_lines(social_rows, title_field="source"),
                    ),
                    (
                        "Content Context",
                        _feed_report_lines(content_rows, title_field="source"),
                    ),
                ),
            ),
        )
        report_paths["news"] = _user_report_path_payload(news_paths)
    except (OSError, TypeError, ValueError):
        blockers.append("NEWS_USER_REPORT_WRITE_FAILED")

    try:
        technology_paths = user_report_paths(
            root,
            "technology",
            stamp,
            file_stem="technology_report",
            latest_stem="latest",
        )
        technology_payload = {
            "command": "runtime-research-refresh-once",
            "report_type": "technology",
            "observed_at": fetched_at.isoformat(),
            "status": "READY",
            "counts": {"technology": len(technology_rows)},
            "technology": technology_rows,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_user_report_files(
            technology_paths,
            technology_payload,
            _render_runtime_research_markdown(
                title="AI4Binance Technology Report",
                observed_at=fetched_at.isoformat(),
                status="READY",
                summary=(
                    "The latest local research refresh collected technology "
                    "developments that may influence reliability, security, "
                    "or research workflow priorities."
                ),
                sections=(
                    (
                        "Technology Developments",
                        _feed_report_lines(technology_rows, title_field="title"),
                    ),
                ),
            ),
        )
        report_paths["technology"] = _user_report_path_payload(technology_paths)
    except (OSError, TypeError, ValueError):
        blockers.append("TECHNOLOGY_USER_REPORT_WRITE_FAILED")

    return report_paths, tuple(dict.fromkeys(blockers))


def _write_virtual_portfolio_user_report(
    settings: Settings,
    payload: Mapping[str, object],
) -> tuple[dict[str, str], tuple[str, ...]]:
    root = _user_report_root(settings.runtime_state_path)
    observed_at = (
        _required_text(payload.get("created_at")) or datetime.now(UTC).isoformat()
    )
    stamp = _stamp_from_iso(observed_at)
    paths = user_report_paths(
        root,
        "virtual_portfolio",
        stamp,
        file_stem="virtual_portfolio_report",
        latest_stem="latest",
    )
    blockers = _text_sequence(payload.get("blockers"))
    status = _required_text(payload.get("state")) or _required_text(
        payload.get("status")
    )
    report_payload: dict[str, object] = {
        "command": "virtual-portfolio-report",
        "observed_at": observed_at,
        "status": status or "UNKNOWN",
        "runtime": dict(payload),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": blockers,
    }
    try:
        write_user_report_files(
            paths,
            report_payload,
            render_professional_summary(
                title="AI4Binance Virtual Portfolio Report",
                observed_at=observed_at,
                status=status or "UNKNOWN",
                summary=(
                    "This report summarizes the latest read-only runtime and "
                    "paper-context portfolio state without exposing private "
                    "balances or authorizing any order."
                ),
                blockers=blockers,
                sections=(
                    (
                        "Portfolio State",
                        _virtual_portfolio_report_lines(payload),
                    ),
                ),
            ),
        )
    except (OSError, TypeError, ValueError):
        return {}, ("VIRTUAL_PORTFOLIO_USER_REPORT_WRITE_FAILED",)
    return _user_report_path_payload(paths), ()


def _render_runtime_research_markdown(
    *,
    title: str,
    observed_at: str,
    status: str,
    summary: str,
    sections: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    return render_professional_summary(
        title=title,
        observed_at=observed_at,
        status=status,
        summary=summary,
        sections=sections,
    )


def _feed_report_lines(
    rows: list[dict[str, object]],
    *,
    title_field: str,
) -> tuple[str, ...]:
    lines: list[str] = []
    for row in rows[:20]:
        title = _required_text(row.get(title_field)) or "Untitled"
        impact = _required_text(row.get("impact")) or "CONTEXT"
        source = _required_text(row.get("source")) or "unknown-source"
        source_url = _required_text(row.get("source_url")) or "UNAVAILABLE"
        hint = _required_text(row.get("opportunity_hint"))
        suffix = f"; recommendation `{hint}`" if hint is not None else ""
        lines.append(f"- `{impact}` {title} ({source}, {source_url}){suffix}.")
    return tuple(lines)


def _virtual_portfolio_report_lines(payload: Mapping[str, object]) -> tuple[str, ...]:
    virtual_portfolio = payload.get("virtual_portfolio")
    virtual_mapping = (
        virtual_portfolio if isinstance(virtual_portfolio, Mapping) else {}
    )
    telemetry_assessment = payload.get("telemetry_assessment")
    telemetry_mapping = (
        telemetry_assessment if isinstance(telemetry_assessment, Mapping) else {}
    )
    if virtual_mapping:
        account_runtime = payload.get("account_runtime")
        runtime_mapping = (
            account_runtime if isinstance(account_runtime, Mapping) else {}
        )
        return (
            f"- Cycle id: `{_required_text(payload.get('cycle_id')) or 'UNAVAILABLE'}`.",
            f"- Virtual portfolio source: `{_required_text(virtual_mapping.get('source')) or 'UNKNOWN'}`.",
            f"- Virtual position count: `{virtual_mapping.get('position_count', 0)}`.",
            f"- Open virtual positions: `{virtual_mapping.get('open_position_count', 0)}`.",
            f"- Closed virtual positions: `{virtual_mapping.get('closed_position_count', 0)}`.",
            f"- Realized virtual PnL (USDT): `{virtual_mapping.get('realized_pnl_usdt', '0')}`.",
            (
                "- GPU telemetry assessment: "
                f"`{telemetry_mapping.get('healthy', False)}` "
                f"{telemetry_mapping.get('source_label', 'UNKNOWN')}"
            ),
            (
                "- Account runtime availability: "
                f"`{_required_text(runtime_mapping.get('status')) or 'UNAVAILABLE'}`."
            ),
            "- Execution: `NO_TRADE`.",
        )
    analytics = payload.get("portfolio_analytics")
    analytics_mapping = analytics if isinstance(analytics, Mapping) else {}
    valued_assets = analytics_mapping.get("valued_assets", ())
    asset_count = len(valued_assets) if isinstance(valued_assets, (list, tuple)) else 0
    return (
        f"- Cycle id: `{_required_text(payload.get('cycle_id')) or 'UNAVAILABLE'}`.",
        f"- Runtime state: `{_required_text(payload.get('state')) or 'UNKNOWN'}`.",
        f"- Valued asset count: `{asset_count}`.",
        (f"- Portfolio analytics present: `{bool(analytics_mapping)}`."),
        (
            "- GPU telemetry assessment: "
            f"`{telemetry_mapping.get('healthy', False)}` "
            f"{telemetry_mapping.get('source_label', 'UNKNOWN')}"
        ),
        "- Execution: `NO_TRADE`.",
    )


def _user_report_path_payload(paths: UserReportPaths) -> dict[str, str]:
    return {
        "json_path": str(paths.json_path),
        "markdown_path": str(paths.markdown_path),
        "latest_json_path": str(paths.latest_json_path),
        "latest_markdown_path": str(paths.latest_markdown_path),
    }


def _user_report_root(state_path: Path) -> Path:
    if "PYTEST_CURRENT_TEST" not in os.environ:
        return canonical_system_root(Path.cwd()).resolve()
    resolved = _resolve_path(state_path).resolve()
    for parent in resolved.parents:
        if parent.name == "state":
            return parent.parent
    return resolved.parent


def _stamp_from_iso(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.now(UTC)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fetch_feed_items(
    source_url: str,
    *,
    max_items: int,
    max_file_bytes: int,
) -> tuple[_WebFeedItem, ...]:
    if source_url not in _ALLOWED_REFRESH_FEED_URLS:
        raise ValueError("runtime feed URL is not allowlisted")
    if not _is_allowed_url(source_url):
        raise ValueError("runtime feed URL must be HTTPS and credential-free")

    # Source URLs are hard-allowlisted and payload is size-bounded.
    request = Request(  # noqa: S310
        source_url,
        headers={"User-Agent": _FEED_USER_AGENT},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310  # nosec B310
        payload = response.read(max_file_bytes + 1)
    if len(payload) > max_file_bytes:
        raise ValueError("runtime feed payload exceeds configured max file size")

    return parse_feed(payload, maximum=max_items)


def _validate_runtime_research_traceability(
    settings: Settings,
) -> tuple[dict[str, object], int]:
    generated_at = datetime.now(UTC)
    opportunity_path = _resolve_path(settings.runtime_opportunity_report_path)
    report_path = opportunity_path.with_name(_RUNTIME_TRACE_REPORT_NAME)
    blockers: list[str] = []

    opportunity_payload = _load_json_mapping(opportunity_path)
    if opportunity_payload is None:
        blockers.append("RUNTIME_OPPORTUNITY_REPORT_UNAVAILABLE")
        report = {
            "report_id": "runtime-research-trace-validation:unavailable",
            "generated_at": generated_at.isoformat(),
            "status": "BLOCKED",
            "opportunity_report_path": str(opportunity_path),
            "report_path": str(report_path),
            "opportunity_count": 0,
            "validated_count": 0,
            "mismatch_count": 0,
            "all_opportunities_traceable": False,
            "mismatches": (),
            "blockers": tuple(blockers),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        _persist_trace_report(report_path, report)
        return report, 2

    feed_paths = {
        "news": _resolve_path(settings.runtime_news_feed_path),
        "social": _resolve_path(settings.runtime_social_feed_path),
        "content": _resolve_path(settings.runtime_content_feed_path),
        "technology": _resolve_path(settings.runtime_technology_feed_path),
    }
    feed_indices = {
        "news": _jsonl_source_index(feed_paths["news"], ("event_id",)),
        "social": _jsonl_source_index(feed_paths["social"], ("event_id",)),
        "content": _jsonl_source_index(feed_paths["content"], ("event_id",)),
        "technology": _jsonl_source_index(
            feed_paths["technology"],
            ("development_id", "event_id"),
        ),
    }

    opportunities = _mapping_sequence(opportunity_payload.get("opportunities"))
    mismatch_entries: list[dict[str, object]] = []
    validated_count = 0

    for index, opportunity in enumerate(opportunities):
        opportunity_id = _required_text(opportunity.get("opportunity_id"))
        if opportunity_id is None:
            opportunity_id = f"opportunity-{index + 1}"
        errors: list[str] = []

        primary_source_url = _required_text(opportunity.get("primary_source_url"))
        trace_urls = _text_sequence(opportunity.get("trace_urls"))
        trace_evidence = _mapping_sequence(opportunity.get("trace_evidence"))
        if primary_source_url is None or not _is_allowed_url(primary_source_url):
            errors.append("PRIMARY_SOURCE_URL_MISSING_OR_INVALID")
        if not trace_urls:
            errors.append("TRACE_URLS_MISSING")
        if not trace_evidence:
            errors.append("TRACE_EVIDENCE_MISSING")
        if (
            primary_source_url is not None
            and trace_urls
            and primary_source_url not in trace_urls
        ):
            errors.append("PRIMARY_SOURCE_NOT_IN_TRACE_URLS")

        for trace_entry in trace_evidence:
            feed = _required_text(trace_entry.get("feed"))
            evidence_id = _required_text(trace_entry.get("evidence_id"))
            source_url = _required_text(trace_entry.get("source_url"))
            if feed is None or evidence_id is None or source_url is None:
                errors.append("TRACE_EVIDENCE_SHAPE_INVALID")
                continue
            index_payload = feed_indices.get(feed)
            if index_payload is None:
                errors.append(f"TRACE_EVIDENCE_FEED_UNKNOWN:{feed}")
                continue
            expected_url = index_payload.get(evidence_id)
            if expected_url is None:
                errors.append(f"TRACE_EVIDENCE_ID_NOT_FOUND:{feed}:{evidence_id}")
                continue
            if expected_url != source_url:
                errors.append(f"TRACE_EVIDENCE_URL_MISMATCH:{feed}:{evidence_id}")
            if source_url not in trace_urls:
                errors.append(f"TRACE_EVIDENCE_URL_NOT_LISTED:{feed}:{evidence_id}")

        if errors:
            mismatch_entries.append(
                {
                    "opportunity_id": opportunity_id,
                    "errors": tuple(dict.fromkeys(errors)),
                }
            )
        else:
            validated_count += 1

    all_traceable = not mismatch_entries
    report_id_source = _required_text(opportunity_payload.get("snapshot_id"))
    report_id = (
        f"runtime-research-trace-validation:{report_id_source}"
        if report_id_source is not None
        else "runtime-research-trace-validation:unknown"
    )
    report = {
        "report_id": report_id,
        "generated_at": generated_at.isoformat(),
        "status": "PASS" if all_traceable else "BLOCKED",
        "opportunity_report_path": str(opportunity_path),
        "report_path": str(report_path),
        "feed_paths": {name: str(path) for name, path in feed_paths.items()},
        "opportunity_count": len(opportunities),
        "validated_count": validated_count,
        "mismatch_count": len(mismatch_entries),
        "all_opportunities_traceable": all_traceable,
        "mismatches": tuple(mismatch_entries),
        "blockers": tuple(blockers),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

    persist_blocker = _persist_trace_report(report_path, report)
    if persist_blocker is not None:
        blockers.append(persist_blocker)
        report["status"] = "BLOCKED"
        report["blockers"] = tuple(dict.fromkeys(blockers))
    return report, 0 if report["status"] == "PASS" else 2


def _persist_trace_report(path: Path, payload: dict[str, object]) -> str | None:
    try:
        primitive = cast(dict[str, object], to_primitive(payload))
        report_id = _required_text(primitive.get("report_id"))
        write_json_object_verified(
            path,
            primitive,
            blocker="RUNTIME_RESEARCH_TRACE_REPORT_VERIFY_FAILED",
            subject_id=report_id or "runtime-research-trace-validation",
            indent=2,
        )
    except (OSError, TypeError, ValueError):
        return "RUNTIME_RESEARCH_TRACE_REPORT_WRITE_FAILED"
    return None


def _jsonl_source_index(
    path: Path,
    id_fields: tuple[str, ...],
) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        rows = _read_jsonl_rows(path)
    except (OSError, ValueError):
        return {}
    index: dict[str, str] = {}
    for row in rows:
        source_url = _required_text(row.get("source_url"))
        if source_url is None:
            continue
        if not _is_allowed_url(source_url):
            continue
        evidence_id: str | None = None
        for field in id_fields:
            evidence_id = _required_text(row.get(field))
            if evidence_id is not None:
                break
        if evidence_id is None:
            continue
        index[evidence_id] = source_url
    return index


def _load_json_mapping(path: Path) -> Mapping[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    return cast(Mapping[str, object], payload)


def _read_jsonl_rows(path: Path) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        decoded = json.loads(line)
        if isinstance(decoded, Mapping):
            rows.append(cast(Mapping[str, object], decoded))
    return tuple(rows)


def _news_row(
    item: _WebFeedItem,
    fetched_at: datetime,
    *,
    eligible_symbols: tuple[str, ...] = (),
) -> dict[str, object]:
    event_id = f"coindesk-{item.published_at:%Y%m%d-%H%M%S}-{_slug(item.source_url)}"
    related_symbols = _related_news_symbols(item.title, eligible_symbols)
    return {
        "event_id": event_id,
        "symbol": related_symbols[0] if len(related_symbols) == 1 else "ALL",
        "related_symbols": list(related_symbols),
        "title": item.title,
        "impact": _impact_from_title(item.title),
        "scheduled_at": item.published_at.isoformat(),
        "retrieved_at": fetched_at.isoformat(),
        "source": "coindesk-rss",
        "source_url": item.source_url,
    }


def _eligible_news_symbols(settings: Settings) -> tuple[str, ...]:
    path = _resolve_path(settings.market_history_source_cache_directory) / (
        "universe-v3.json"
    )
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            return ()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            return ()
        raw_symbols = payload.get("futures_symbols", ())
        if not isinstance(raw_symbols, list) or len(raw_symbols) > 5_000:
            return ()
        symbols = tuple(
            sorted(
                {
                    item.strip().upper()
                    for item in raw_symbols
                    if isinstance(item, str)
                    and item.strip().isascii()
                    and item.strip().isalnum()
                    and 4 <= len(item.strip()) <= 24
                }
            )
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ()
    return symbols


def _related_news_symbols(
    title: str,
    eligible_symbols: tuple[str, ...],
) -> tuple[str, ...]:
    normalized = title.casefold()
    original = title
    matched: list[str] = []
    for symbol in eligible_symbols:
        base = symbol[:-4] if symbol.endswith(("USDT", "USDC")) else symbol
        if not base:
            continue
        aliases = _NEWS_ASSET_ALIASES.get(base, ())
        alias_match = any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized)
            for alias in aliases
        )
        ticker_match = bool(
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(base)}(?![A-Za-z0-9])",
                original,
            )
        )
        if alias_match or ticker_match:
            matched.append(symbol)
    return tuple(matched)


def _social_row(item: _WebFeedItem) -> dict[str, object]:
    directional_vote = _title_vote(item.title)
    score = 50.0 + abs(directional_vote) * 35.0
    return {
        "event_id": (
            f"reddit-crypto-{item.published_at:%Y%m%d-%H%M%S}-{_slug(item.source_url)}"
        ),
        "symbol": "ALL",
        "source": "reddit-r-cryptocurrency",
        "source_url": item.source_url,
        "as_of": item.published_at.isoformat(),
        "directional_vote": round(directional_vote, 6),
        "score": round(score, 6),
        "weight": 1.0,
    }


def _content_row(item: _WebFeedItem) -> dict[str, object]:
    directional_vote = _title_vote(item.title)
    score = 55.0 + abs(directional_vote) * 30.0
    return {
        "event_id": (
            "coindesk-content-"
            f"{item.published_at:%Y%m%d-%H%M%S}-{_slug(item.source_url)}"
        ),
        "symbol": "ALL",
        "source": _content_source_label(item.source_url),
        "source_url": item.source_url,
        "as_of": item.published_at.isoformat(),
        "directional_vote": round(directional_vote, 6),
        "score": round(score, 6),
        "weight": 1.1,
    }


def _technology_row(item: _WebFeedItem, fetched_at: datetime) -> dict[str, object]:
    normalized = item.title.casefold()
    security_topic = any(
        token in normalized
        for token in ("security", "codeql", "scanning", "vulnerability")
    )
    return {
        "development_id": (
            f"gh-changelog-{item.published_at:%Y%m%d}-{_slug(item.source_url)}"
        ),
        "symbol": "ALL",
        "title": item.title,
        "impact": "HIGH" if security_topic else "MEDIUM",
        "source": "github-changelog",
        "source_url": item.source_url,
        "as_of": item.published_at.isoformat(),
        "retrieved_at": fetched_at.isoformat(),
        "directional_vote": 0.35 if security_topic else 0.2,
        "score": 72.0 if security_topic else 64.0,
        "weight": 1.3 if security_topic else 1.1,
        "category": "application-security" if security_topic else "developer-platform",
        "opportunity_hint": (
            "Harden secure defaults for repository scanning workflows"
            if security_topic
            else "Review developer platform changes for CI reliability"
        ),
    }


def _write_jsonl_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows
    )
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def _impact_from_title(title: str) -> str:
    normalized = title.casefold()
    if any(token in normalized for token in _NEGATIVE_SENTIMENT_TOKENS):
        return "CRITICAL"
    return "HIGH"


def _content_source_label(source_url: str) -> str:
    path = urlparse(source_url).path
    parts = [segment for segment in path.split("/") if segment]
    if not parts:
        return "coindesk-content"
    return f"coindesk-{parts[0]}"


def _title_vote(title: str) -> float:
    normalized = title.casefold()
    positive_hits = sum(token in normalized for token in _POSITIVE_SENTIMENT_TOKENS)
    negative_hits = sum(token in normalized for token in _NEGATIVE_SENTIMENT_TOKENS)
    if positive_hits == negative_hits:
        return 0.0
    return 0.35 if positive_hits > negative_hits else -0.35


def _domain_list(items: tuple[_WebFeedItem, ...]) -> tuple[str, ...]:
    domains = {
        urlparse(item.source_url).netloc.strip().casefold()
        for item in items
        if urlparse(item.source_url).netloc.strip()
    }
    return tuple(sorted(domains))


def _slug(value: str) -> str:
    path = urlparse(value).path
    parts = [segment for segment in path.split("/") if segment]
    candidate = parts[-1] if parts else ""
    normalized = re.sub(r"[^a-z0-9-]+", "-", candidate.casefold()).strip("-")
    if normalized:
        return normalized[:48]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"item-{digest}"


def _is_allowed_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _required_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _text_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, tuple):
        candidates = value
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        return ()
    return tuple(item for item in candidates if isinstance(item, str) and item)


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, tuple):
        candidates = value
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        return ()
    return tuple(item for item in candidates if isinstance(item, Mapping))


def runtime_payload(report: object) -> dict[str, object]:
    """Return a secret-safe summary without wallet balances."""
    primitive = cast(dict[str, object], to_primitive(report))
    governor = GpuResourceGovernor()
    telemetry = governor.collect_telemetry()
    telemetry_assessment = telemetry.assess(governor.policy.vram_headroom_percent)
    for sensitive in ("spot_wallet", "futures_account", "spot_research"):
        primitive.pop(sensitive, None)
    primitive["telemetry_assessment"] = to_primitive(telemetry_assessment)
    return primitive
