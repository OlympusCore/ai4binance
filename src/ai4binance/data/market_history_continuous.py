"""Resumable, public-only collection into the canonical market archive."""

from __future__ import annotations

import json
import re
import time
from collections import Counter, deque
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Final, cast

from ai4binance.core.errors import (
    ExchangeError,
    ExchangeHttpError,
    ExchangeRateLimitError,
    ExchangeTransportError,
)
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.market_history_sync import (
    MARKET_HISTORY_TIMEFRAMES,
    MarketHistorySourceUnavailableError,
    MarketHistorySynchronizer,
    _csv_rows,
)
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.exchange.client import JsonTransport
from ai4binance.exchange.rate_limit import (
    RequestPriority,
    WeightedRateLimitGovernor,
    public_request_weight,
)
from ai4binance.infrastructure.persistence.safe_json import (
    DestinationVerificationError,
    write_json_object_verified,
)
from ai4binance.schemas import OHLCVCandle

_DEFAULT_KLINE_INTERVAL = timedelta(minutes=5)
_TIMEFRAME_REFRESH_SECONDS: dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "1h": 3_600,
    "4h": 14_400,
    "1d": 86_400,
}
_SAFE_STATE: dict[str, object] = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}
VIRTUAL_MARKET_COLLECTION_TIMEFRAMES: Final = ("15m", "1h", "4h")
_DASHBOARD_REFRESH_TIMEFRAMES = MARKET_HISTORY_TIMEFRAMES
_SCREEN_TIMEFRAMES = VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
_ENRICHMENT_TIMEFRAMES: Final[tuple[str, ...]] = ()
# The canonical live path persists native decision timeframes directly. REST
# remains bounded to bootstrap and gap recovery.
_PROGRESS_HEARTBEAT_SECONDS = 5
_SUPPLEMENTAL_STREAM_WORKERS = 1
_COMPATIBLE_DERIVED_SOURCE_PREFIXES = (
    "COMPATIBLE_DIRECT_PLUS_DERIVED_FROM_CANONICAL_1M:",
    "DERIVED_FROM_CANONICAL_1M:",
)
_REFRESH_REQUEST_MAX_BYTES = 16_384
_REFRESH_REQUEST_MAX_AGE = timedelta(minutes=10)
_STATE_RESULT_SAMPLE_LIMIT = 128
_DASHBOARD_OPPORTUNITY_LIMIT = 100
_DASHBOARD_REJECTION_LIMIT = 100
_REFRESH_REQUESTERS = frozenset({"DASHBOARD", "VIRTUAL_MARKET"})
_REFRESH_REQUEST_SAFE_FIELDS = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}
_REFRESH_REQUEST_PENDING_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "requested_at",
        "requester",
        "market",
        "symbol",
        "status",
        "blockers",
        *_REFRESH_REQUEST_SAFE_FIELDS,
    }
)
_REFRESH_REQUEST_SYMBOL = re.compile(r"[A-Z0-9]{4,24}")
_ANALYSIS_READY_STREAM_STATES = frozenset({"CURRENT", "SHARED", "NOT_APPLICABLE"})

SymbolReadyHandler = Callable[[str, str, datetime], Mapping[str, object]]


def _refresh_request_path(path: Path) -> Path:
    """Return the single-writer market-history request state next to state."""

    return path.with_name("market-history-refresh-request.json")


def _read_refresh_request(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > _REFRESH_REQUEST_MAX_BYTES:
        raise ValueError("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
    value = _load(path)
    if value.get("status") != "PENDING":
        if (
            value.get("status") not in {"DATA_READY", "DATA_BLOCKED"}
            or set(value) != (_REFRESH_REQUEST_PENDING_FIELDS | {"completed_at"})
            or not isinstance(value.get("completed_at"), str)
            or any(
                value.get(key) != expected
                for key, expected in _REFRESH_REQUEST_SAFE_FIELDS.items()
            )
            or not isinstance(value.get("blockers"), list)
        ):
            raise ValueError("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
        return value
    if set(value) != _REFRESH_REQUEST_PENDING_FIELDS:
        raise ValueError("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
    requested_at = datetime.fromisoformat(str(value.get("requested_at", "")))
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
    if (
        value.get("schema_version") != "MarketHistoryRefreshRequest/v1"
        or not isinstance(value.get("request_id"), str)
        or not isinstance(value.get("requester"), str)
        or value.get("requester") not in _REFRESH_REQUESTERS
        or value.get("market") not in {"SPOT", "USD_M_FUTURES"}
        or not isinstance(value.get("symbol"), str)
        or _REFRESH_REQUEST_SYMBOL.fullmatch(str(value["symbol"])) is None
        or value.get("blockers") != []
        or any(
            value.get(key) != expected
            for key, expected in _REFRESH_REQUEST_SAFE_FIELDS.items()
        )
    ):
        raise ValueError("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
    return value


def market_history_refresh_status(path: Path) -> dict[str, object]:
    """Read the bounded dashboard request state without mutating collection."""

    try:
        value = _read_refresh_request(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {
            "state": "DATA_BLOCKED",
            "blockers": ["MARKET_HISTORY_REFRESH_REQUEST_INVALID"],
            **_REFRESH_REQUEST_SAFE_FIELDS,
        }
    if value is None:
        return {"state": "NOT_RUN", "blockers": [], **_REFRESH_REQUEST_SAFE_FIELDS}
    return {**value, "state": value.get("status", "DATA_BLOCKED")}


def enqueue_market_history_refresh_request(
    path: Path,
    *,
    market: str,
    symbol: str,
    eligible_symbols: tuple[str, ...],
    requested_at: datetime,
    requester: str = "DASHBOARD",
) -> dict[str, object]:
    """Persist one bounded freshness request; never replace a pending job."""

    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("refresh request timestamp must be timezone-aware")
    normalized_requester = requester.strip().upper()
    if normalized_requester not in _REFRESH_REQUESTERS:
        raise ValueError("market history refresh requester is invalid")
    normalized_symbol = symbol.strip().upper()
    if (
        market not in {"SPOT", "USD_M_FUTURES"}
        or _REFRESH_REQUEST_SYMBOL.fullmatch(normalized_symbol) is None
        or normalized_symbol not in eligible_symbols
    ):
        return {
            "state": "DATA_BLOCKED",
            "blockers": ["MARKET_HISTORY_REFRESH_REQUEST_INELIGIBLE"],
            **_REFRESH_REQUEST_SAFE_FIELDS,
        }
    existing = _read_refresh_request(path)
    if existing is not None and existing.get("status") == "PENDING":
        existing_at = datetime.fromisoformat(str(existing["requested_at"]))
        age = requested_at.astimezone(UTC) - existing_at.astimezone(UTC)
        if age <= _REFRESH_REQUEST_MAX_AGE and age >= timedelta(minutes=-1):
            if (
                existing.get("market") == market
                and existing.get("symbol") == normalized_symbol
            ):
                return {**existing, "state": "PENDING"}
            return {
                "state": "BUSY",
                "request_id": existing.get("request_id"),
                "blockers": ["MARKET_HISTORY_REFRESH_REQUEST_ALREADY_PENDING"],
                **_REFRESH_REQUEST_SAFE_FIELDS,
            }
    request_id = (
        "market-history:"
        + sha256(
            f"{normalized_requester}:{market}:{normalized_symbol}:{requested_at.isoformat()}".encode()
        ).hexdigest()[:24]
    )
    request: dict[str, object] = {
        "schema_version": "MarketHistoryRefreshRequest/v1",
        "request_id": request_id,
        "requested_at": requested_at.astimezone(UTC).isoformat(),
        "requester": normalized_requester,
        "market": market,
        "symbol": normalized_symbol,
        "status": "PENDING",
        "blockers": [],
        **_REFRESH_REQUEST_SAFE_FIELDS,
    }
    write_json_object_verified(
        path,
        request,
        blocker="MARKET_HISTORY_REFRESH_REQUEST_WRITE_FAILED",
        subject_id=request_id,
        indent=2,
        durable=True,
    )
    return {**request, "state": "PENDING"}


def timeframe_refresh_schedule() -> list[dict[str, object]]:
    """Describe direct native-timeframe collection sources."""

    return [
        {
            "timeframe": timeframe,
            "interval_seconds": _TIMEFRAME_REFRESH_SECONDS[timeframe],
            "closed_history_source": f"BINANCE_VISION_{timeframe.upper()}_DIRECT",
            "live_tail_source": f"BINANCE_WEBSOCKET_{timeframe.upper()}_DIRECT",
            "gap_recovery_source": f"BINANCE_PUBLIC_REST_{timeframe.upper()}_ONLY",
            "network_download": True,
        }
        for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
    ]


def _save(path: Path, payload: Mapping[str, object]) -> None:
    write_json_object_verified(
        path, payload, blocker="MARKET_HISTORY_WRITE_FAILED", durable=True
    )


def _recoverable_error_code(error: Exception) -> str:
    """Expose only repository-owned verification codes, never exception detail."""

    if isinstance(error, DestinationVerificationError):
        code = str(error).strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", code):
            return code
    return "MARKET_HISTORY_RECOVERABLE_ERROR"


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("market history state must be an object")
    return cast(dict[str, object], payload)


@dataclass
class PublicRequestBudget:
    """Compatibility facade over the central weighted request governor."""

    seconds_per_weight: float = 0.05
    lock: Lock = field(default_factory=Lock, repr=False)
    next_at: float = 0
    cooldown_until: float = 0
    governor: WeightedRateLimitGovernor = field(
        default_factory=WeightedRateLimitGovernor, repr=False
    )

    def configure_from_exchange_info(self, payload: object) -> None:
        """Use Binance's declared request-weight limits with a safety margin.

        The collector never exceeds the observed exchange limit. Its legacy
        bootstrap pacing uses the configured soft-limit fraction until the
        central governor has parsed the advertised REQUEST_WEIGHT windows.
        """

        if not isinstance(payload, Mapping):
            return
        raw_limits = payload.get("rateLimits")
        if not isinstance(raw_limits, list):
            return
        interval_seconds = {
            "SECOND": 1,
            "MINUTE": 60,
            "HOUR": 3_600,
            "DAY": 86_400,
        }
        candidates: list[float] = []
        for raw_limit in raw_limits:
            if not isinstance(raw_limit, Mapping):
                continue
            if raw_limit.get("rateLimitType") != "REQUEST_WEIGHT":
                continue
            interval = raw_limit.get("interval")
            interval_count = raw_limit.get("intervalNum")
            limit = raw_limit.get("limit")
            if (
                not isinstance(interval, str)
                or not isinstance(interval_count, (int, str))
                or not isinstance(limit, (int, str))
                or isinstance(interval_count, bool)
                or isinstance(limit, bool)
            ):
                continue
            try:
                window_seconds = interval_seconds[interval] * int(interval_count)
                request_weight_limit = int(limit)
            except (KeyError, TypeError, ValueError):
                continue
            if window_seconds <= 0 or request_weight_limit <= 0:
                continue
            candidates.append(
                window_seconds / (request_weight_limit * self.governor.bands.soft_limit)
            )
        if not candidates:
            return
        with self.lock:
            self.seconds_per_weight = max(candidates)
        self.governor.configure_from_exchange_info(payload)

    def acquire(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        *,
        priority: RequestPriority = RequestPriority.SUPPLEMENTAL,
    ) -> None:
        weight = public_request_weight(path, params)
        with self.lock:
            if time.monotonic() < self.cooldown_until:
                raise ExchangeHttpError("shared public request budget cooldown")
        if self.governor.status()["windows"]:
            self.governor.reserve(weight, priority=priority)
            return
        with self.lock:
            time.sleep(max(0, self.next_at - time.monotonic()))
            self.next_at = time.monotonic() + max(
                weight * self.seconds_per_weight,
                0.7 if path.endswith("fundingRate") else 0,
            )

    def observe_headers(self, headers: Mapping[str, str]) -> None:
        """Forward provider usage headers to the central governor."""

        self.governor.observe_headers(headers)

    def apply_retry_after(self, seconds: float, *, banned: bool) -> None:
        """Synchronize legacy and central cooldown state."""

        duration = max(120.0 if banned else 1.0, seconds)
        until = time.monotonic() + duration
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, until)
        self.governor.apply_retry_after(seconds, banned=banned)


@dataclass
class MeteredPublicTransport:
    """Pace public requests and persist shared exchange metadata snapshots."""

    transport: JsonTransport
    snapshot_directory: Path
    minimum_interval_seconds: float = 0.1
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    request_count: int = 0
    decoded_json_bytes: int = 0
    cooldown_until: float = 0
    _pace_lock: Lock = field(default_factory=Lock, repr=False)
    _last_request: float = 0
    _last_funding_request: float = 0
    budget: PublicRequestBudget | None = None

    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> object:
        if self.budget is not None:
            priority = (
                RequestPriority.METADATA
                if path.endswith("exchangeInfo")
                else RequestPriority.GAP_RECOVERY
                if "startTime" in (params or {})
                else RequestPriority.SUPPLEMENTAL
            )
            self.budget.acquire(path, params, priority=priority)
        with self._pace_lock:
            if time.monotonic() < self.cooldown_until:
                raise ExchangeHttpError("public collection rate-limit cooldown")
            due = self._last_request + self.minimum_interval_seconds
            if path.endswith("fundingRate"):
                due = max(due, self._last_funding_request + 0.7)
            self.sleeper(max(0, due - time.monotonic()))
            self._last_request = time.monotonic()
            if path.endswith("fundingRate"):
                self._last_funding_request = self._last_request
            self.request_count += 1
        try:
            payload = self.transport.get_json(path, params)
        except ExchangeRateLimitError as error:
            banned = error.status_code == 418
            duration = error.retry_after_seconds or (86_400 if banned else 900)
            self.cooldown_until = time.monotonic() + duration
            if self.budget is not None:
                self.budget.apply_retry_after(duration, banned=banned)
            raise
        except ExchangeHttpError as error:
            if "429" in str(error) or "418" in str(error):
                banned = "418" in str(error)
                duration = 86_400 if banned else 900
                self.cooldown_until = time.monotonic() + duration
                if self.budget is not None:
                    self.budget.apply_retry_after(duration, banned=banned)
            raise
        except ExchangeTransportError:
            self.cooldown_until = time.monotonic() + 30
            raise
        with self._pace_lock:
            self.decoded_json_bytes += len(json.dumps(payload).encode("utf-8"))
        if path.endswith("exchangeInfo"):
            if self.budget is not None:
                self.budget.configure_from_exchange_info(payload)
            _save(
                self.snapshot_directory / "exchange-info.json",
                {
                    "observed_at": datetime.now(UTC).isoformat(),
                    "payload": payload,
                    **_SAFE_STATE,
                },
            )
        return payload


@dataclass
class ContinuousMarketHistory:
    """One writer, bounded pages per stream, durable progress across shutdowns.

    Historical days use compressed, checksum-verified Vision sources. REST only
    fills unpublished days and the current tail. The bootstrap boundary is saved
    once, so an extended shutdown never moves the missing-data boundary forward.
    """

    history: MarketHistorySynchronizer
    spot: JsonTransport
    futures: JsonTransport
    initial_days: int = 201
    pages_per_stream: int = 2
    archive_downloaded_bytes: int = 0
    archive_request_count: int = 0
    max_workers: int = 4
    minimum_candles: int | None = None
    _metrics_lock: Lock = field(default_factory=Lock, repr=False)
    coin_m: JsonTransport | None = None
    coin_m_contracts: dict[str, tuple[str, str]] = field(default_factory=dict)
    priority_symbols: tuple[str, ...] = ()
    refresh_request_path: Path | None = None
    vision_history_enabled: bool = True
    on_symbol_ready: SymbolReadyHandler | None = field(default=None, repr=False)
    on_symbol_screen: SymbolReadyHandler | None = field(default=None, repr=False)
    clock: Callable[[], datetime] = field(
        default=lambda: datetime.now(UTC), repr=False
    )

    def __post_init__(self) -> None:
        if not 1 <= self.initial_days <= 3650 or not 1 <= self.pages_per_stream <= 32:
            raise ValueError("continuous collection bounds are invalid")
        if not 1 <= self.max_workers <= 8:
            raise ValueError("collection workers must be between 1 and 8")
        if (
            self.minimum_candles is not None
            and not 1 <= self.minimum_candles <= 200_000
        ):
            raise ValueError("minimum_candles must be between 1 and 200000")
        self.priority_symbols = tuple(
            dict.fromkeys(
                symbol.strip().upper()
                for symbol in self.priority_symbols
                if symbol.strip()
            )
        )
        if (
            self.refresh_request_path is not None
            and not self.refresh_request_path.is_absolute()
        ):
            raise ValueError("market refresh request path must be absolute")

    def sync_cycle(self, *, observed_at: datetime) -> dict[str, object]:
        if observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        now = observed_at.astimezone(UTC)
        before = self._network_totals()
        universe = self.history._eligible_universe(now, force_refresh=True)
        self.coin_m_contracts = {
            symbol: (pair, contract)
            for symbol, pair, contract in universe.coin_m_contracts
        }
        results: list[dict[str, object]] = []
        blockers = list(universe.blockers)
        market_work = (
            # Interleaving below prevents the much larger futures stream set
            # from starving the Spot universe shown by the dashboard.
            ("spot", self._prioritized_symbols(universe.spot_symbols), self.spot),
            (
                "usd_m_futures",
                self._prioritized_symbols(universe.futures_symbols),
                self.futures,
            ),
            (
                "coin_m_futures",
                self._prioritized_symbols(universe.coin_m_symbols),
                self.coin_m,
            ),
        )
        # VirtualMarket depends on these bounded bulk snapshots. Refresh once
        # at cycle start so a service restart cannot leave an already-old
        # ticker cache to expire during a long candle collection cycle.
        snapshot_refresh_due = time.monotonic()

        def refresh_snapshots(snapshot_time: datetime) -> None:
            nonlocal snapshot_refresh_due
            if time.monotonic() < snapshot_refresh_due or universe.blockers:
                return
            if snapshot_refresh_due:
                try:
                    refreshed_universe = self.history._eligible_universe(
                        snapshot_time, force_refresh=True
                    )
                except (OSError, ValueError, ExchangeError):
                    refreshed_universe = None
                if (
                    refreshed_universe is None or refreshed_universe.blockers
                ) and "MARKET_UNIVERSE_METADATA_UNAVAILABLE" not in blockers:
                    blockers.append("MARKET_UNIVERSE_METADATA_UNAVAILABLE")
                elif refreshed_universe is not None and not refreshed_universe.blockers:
                    while "MARKET_UNIVERSE_METADATA_UNAVAILABLE" in blockers:
                        blockers.remove("MARKET_UNIVERSE_METADATA_UNAVAILABLE")
            snapshot_failed = False
            for snapshot_market, snapshot_symbols, snapshot_transport in market_work:
                if snapshot_transport is None or not snapshot_symbols:
                    continue
                try:
                    self._snapshots(
                        snapshot_market,
                        snapshot_symbols,
                        snapshot_transport,
                        snapshot_time,
                    )
                except (OSError, ValueError, ExchangeError):
                    snapshot_failed = True
                    if "MARKET_SNAPSHOT_UNAVAILABLE" not in blockers:
                        blockers.append("MARKET_SNAPSHOT_UNAVAILABLE")
            if not snapshot_failed:
                while "MARKET_SNAPSHOT_UNAVAILABLE" in blockers:
                    blockers.remove("MARKET_SNAPSHOT_UNAVAILABLE")
            snapshot_refresh_due = time.monotonic() + 300

        refresh_snapshots(now)

        work_items = self._interleaved_market_work(market_work)
        requested_identity: tuple[str, str] | None = None
        refresh_request: dict[str, object] | None = None
        if self.refresh_request_path is not None:
            try:
                candidate = _read_refresh_request(self.refresh_request_path)
                if candidate is not None and candidate.get("status") == "PENDING":
                    requested_at = datetime.fromisoformat(
                        str(candidate["requested_at"])
                    )
                    age = now - requested_at.astimezone(UTC)
                    if age < timedelta(minutes=-1) or age > _REFRESH_REQUEST_MAX_AGE:
                        self._complete_refresh_request(
                            candidate,
                            now,
                            status="DATA_BLOCKED",
                            blockers=("MARKET_HISTORY_REFRESH_REQUEST_EXPIRED",),
                        )
                    elif universe.blockers:
                        self._complete_refresh_request(
                            candidate,
                            now,
                            status="DATA_BLOCKED",
                            blockers=("MARKET_HISTORY_UNIVERSE_UNAVAILABLE",),
                        )
                    else:
                        requested_market = (
                            "spot" if candidate["market"] == "SPOT" else "usd_m_futures"
                        )
                        eligible = next(
                            (
                                symbols
                                for name, symbols, _ in market_work
                                if name == requested_market
                            ),
                            (),
                        )
                        if candidate["symbol"] not in eligible:
                            self._complete_refresh_request(
                                candidate,
                                now,
                                status="DATA_BLOCKED",
                                blockers=("MARKET_HISTORY_REFRESH_REQUEST_INELIGIBLE",),
                            )
                        else:
                            refresh_request = candidate
                            requested_identity = (
                                requested_market,
                                str(candidate["symbol"]),
                            )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                blockers.append("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
        stream_items = self._interleaved_stream_work(work_items)
        staged = self.on_symbol_screen is not None
        active_collection_timeframes = VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
        staged_markets = {"spot", "usd_m_futures"} if staged else set()
        if staged:
            stream_items = tuple(
                item
                for item in stream_items
                if item[0] in staged_markets
                and item[3] == "klines"
                and item[4] in active_collection_timeframes
            )
        total_symbols = sum(
            len(symbols)
            for _, symbols, transport in market_work
            if transport is not None
        )
        total_streams = len(stream_items)
        if staged:
            total_symbols = sum(
                1 for market, _, _ in work_items if market in staged_markets
            )
        market_labels = {
            "spot": "SPOT",
            "usd_m_futures": "USD_M_FUTURES",
            "coin_m_futures": "COIN_M_FUTURES",
        }
        coverage: dict[str, dict[str, Counter[str]]] = {
            market_labels[market]: {
                timeframe: Counter()
                for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
            }
            for market, _, transport in market_work
            if transport is not None
        }
        completed_symbols = 0
        completed_streams = 0
        required_streams = {
            (market, symbol): len(active_collection_timeframes)
            if market in staged_markets
            else len(self._collection_kinds(market))
            for market, symbol, _ in work_items
        }
        completed_by_symbol: dict[tuple[str, str], int] = {}
        dashboard_statuses_by_symbol: dict[tuple[str, str], dict[str, str]] = {}
        analysis_started: set[tuple[str, str]] = set()
        screening_started: set[tuple[str, str]] = set()
        opportunity_analysis_summary: Counter[str] = Counter()
        opportunity_projection: dict[str, dict[str, object]] = {
            label: {
                "eligible_symbol_count": len(symbols),
                "analyzed_symbol_count": 0,
                "data_blocked_symbol_count": 0,
                "analysis_blocked_symbol_count": 0,
                "delegated_symbol_count": 0,
                "no_opportunity_symbol_count": 0,
                "published_opportunity_count": 0,
                "suppressed_opportunity_count": 0,
                "evaluated_attempt_count": 0,
                "rejected_attempt_count": 0,
                "rejected_by_stage": {},
                "rejected_by_reason": {},
                "recent_rejections": [],
                "opportunities": [],
            }
            for label, symbols in (
                ("SPOT", universe.spot_symbols),
                ("USD_M_FUTURES", universe.futures_symbols),
            )
        }
        stream_failure_summary: Counter[str] = Counter()
        progress_lock = Lock()
        coverage_lock = Lock()
        last_progress_write = 0.0

        def coverage_projection() -> dict[str, list[dict[str, object]]]:
            """Return bounded, collector-owned coverage for dashboard readers."""

            with coverage_lock:
                projection: dict[str, list[dict[str, object]]] = {}
                universe_counts = {
                    "SPOT": len(universe.spot_symbols),
                    "USD_M_FUTURES": len(universe.futures_symbols),
                    "COIN_M_FUTURES": len(universe.coin_m_symbols),
                }
                for market, rows in coverage.items():
                    entries: list[dict[str, object]] = []
                    for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES:
                        counts = rows[timeframe]
                        resolved = sum(counts.values())
                        entries.append(
                            {
                                "timeframe": timeframe,
                                "universe_count": universe_counts[market],
                                "current_count": counts["CURRENT"],
                                "stale_count": 0,
                                "invalid_count": counts["BLOCKED"],
                                "unavailable_count": counts["UNAVAILABLE"],
                                "refresh_required_count": counts["BACKFILLING"],
                                "pending_count": max(
                                    0, universe_counts[market] - resolved
                                ),
                            }
                        )
                    projection[market] = entries
                return projection

        def opportunity_projection_payload() -> dict[str, dict[str, object]]:
            """Return the collector-owned dashboard read model without archive scans."""

            projection: dict[str, dict[str, object]] = {}
            for market, value in opportunity_projection.items():
                analyzed = cast(int, value["analyzed_symbol_count"])
                eligible = cast(int, value["eligible_symbol_count"])
                data_blocked = cast(int, value["data_blocked_symbol_count"])
                analysis_blocked = cast(int, value["analysis_blocked_symbol_count"])
                opportunities = list(
                    cast(list[dict[str, object]], value["opportunities"])
                )
                if opportunities:
                    status = (
                        "CANDIDATES_AVAILABLE_WITH_DATA_GAPS"
                        if data_blocked
                        else "CANDIDATES_AVAILABLE"
                    )
                elif data_blocked:
                    status = "DATA_UNAVAILABLE"
                elif analysis_blocked:
                    status = "ANALYSIS_BLOCKED"
                elif analyzed < eligible:
                    status = (
                        "ANALYSIS_UNAVAILABLE"
                        if cast(int, value["delegated_symbol_count"]) == eligible
                        else "ANALYSIS_PENDING"
                    )
                else:
                    status = "NO_TRADE"
                projection[market] = {
                    **value,
                    "status": status,
                    "opportunities": opportunities,
                    **_SAFE_STATE,
                }
            return projection

        def record_generation_health(
            projection: dict[str, object],
            market: str,
            symbol: str,
            health: object,
        ) -> None:
            """Merge bounded diagnostics independently of analysis success."""

            if not isinstance(health, Mapping):
                return
            for name in ("evaluated_attempt_count", "rejected_attempt_count"):
                count = health.get(name)
                if (
                    isinstance(count, int)
                    and not isinstance(count, bool)
                    and count >= 0
                ):
                    projection[name] = cast(int, projection[name]) + count
            for name in ("rejected_by_stage", "rejected_by_reason"):
                raw_counts = health.get(name)
                target = cast(dict[str, int], projection[name])
                if isinstance(raw_counts, Mapping):
                    for key, count in raw_counts.items():
                        if (
                            isinstance(key, str)
                            and 0 < len(key) <= 180
                            and isinstance(count, int)
                            and not isinstance(count, bool)
                            and count >= 0
                        ):
                            target[key] = target.get(key, 0) + count
            recent = health.get("recent_rejections")
            target_recent = cast(
                list[dict[str, object]], projection["recent_rejections"]
            )
            if isinstance(recent, list):
                for row in recent:
                    if (
                        not isinstance(row, Mapping)
                        or row.get("market") != market
                        or row.get("symbol") != symbol
                        or row.get("execution_allowed") is not False
                        or row.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
                    ):
                        continue
                    projected = {
                        name: row.get(name)
                        for name in (
                            "candidate_attempt_id",
                            "market",
                            "symbol",
                            "timeframe",
                            "observed_at",
                            "candle_close_time",
                            "outcome",
                            "failed_stage",
                            "retryability",
                            "execution_allowed",
                            "promotion_status",
                            "live_eligibility_status",
                        )
                        if isinstance(row.get(name), (str, bool))
                    }
                    for name in ("reason_codes", "missing_fields"):
                        values = row.get(name)
                        projected[name] = (
                            [
                                value
                                for value in values[:20]
                                if isinstance(value, str) and 0 < len(value) <= 180
                            ]
                            if isinstance(values, (list, tuple))
                            else []
                        )
                    target_recent.append(projected)
            if len(target_recent) > _DASHBOARD_REJECTION_LIMIT:
                del target_recent[:-_DASHBOARD_REJECTION_LIMIT]

        def record_opportunity_analysis(
            market: str, symbol: str, analysis: Mapping[str, object]
        ) -> None:
            """Merge a completed canonical analysis into its bounded read model."""

            projection = opportunity_projection.get(market)
            if projection is None:
                return
            record_generation_health(
                projection, market, symbol, analysis.get("generation_health")
            )
            status = str(analysis.get("status", "UNKNOWN"))
            if status == "CURRENT":
                projection["analyzed_symbol_count"] = (
                    cast(int, projection["analyzed_symbol_count"]) + 1
                )
                candidate_count = analysis.get("candidate_count", 0)
                if (
                    isinstance(candidate_count, int)
                    and not isinstance(candidate_count, bool)
                    and candidate_count == 0
                ):
                    projection["no_opportunity_symbol_count"] = (
                        cast(int, projection["no_opportunity_symbol_count"]) + 1
                    )
            elif status == "DATA_BLOCKED":
                projection["data_blocked_symbol_count"] = (
                    cast(int, projection["data_blocked_symbol_count"]) + 1
                )
            elif status == "DELEGATED":
                projection["delegated_symbol_count"] = (
                    cast(int, projection["delegated_symbol_count"]) + 1
                )
            else:
                projection["analysis_blocked_symbol_count"] = (
                    cast(int, projection["analysis_blocked_symbol_count"]) + 1
                )

            if status not in {"CURRENT", "DATA_BLOCKED"}:
                return
            candidates = analysis.get("dashboard_candidates")
            if not isinstance(candidates, list):
                return
            valid_candidates = [
                candidate
                for candidate in candidates
                if isinstance(candidate, dict)
                and candidate.get("market") == market
                and candidate.get("symbol") == symbol
                and candidate.get("execution_allowed") is False
                and candidate.get("live_eligibility_status") == "LIVE_ORDER_BLOCKED"
            ]
            available = _DASHBOARD_OPPORTUNITY_LIMIT - len(
                cast(list[dict[str, object]], projection["opportunities"])
            )
            cast(list[dict[str, object]], projection["opportunities"]).extend(
                valid_candidates[:available]
            )
            projection["suppressed_opportunity_count"] = cast(
                int, projection["suppressed_opportunity_count"]
            ) + max(0, len(valid_candidates) - max(0, available))
            projection["published_opportunity_count"] = len(
                cast(list[dict[str, object]], projection["opportunities"])
            )

        def record_coverage(
            result: Mapping[str, object],
            *,
            market: str,
            kind: str,
            timeframe: str | None,
        ) -> None:
            """Count only a completed direct candle stream; unknown stays pending."""

            status = result.get("status")
            if (
                not isinstance(timeframe, str)
                or kind != "klines"
                or market_labels.get(market) not in coverage
                or timeframe not in coverage[market_labels[market]]
                or status not in {"CURRENT", "BACKFILLING", "BLOCKED", "UNAVAILABLE"}
            ):
                return
            with coverage_lock:
                coverage[market_labels[market]][timeframe][status] += 1

        def publish_progress(
            market: str | None,
            symbol: str | None = None,
            *,
            streams: int = 0,
            stream_status: str | None = None,
            stream_reason: str | None = None,
            kind: str | None = None,
            timeframe: str | None = None,
            force: bool = False,
        ) -> bool:
            """Publish bounded, truthful progress while workers are still busy."""

            nonlocal completed_symbols, completed_streams, last_progress_write
            analysis_ready = False
            with progress_lock:
                completed_streams += streams
                if streams and market is not None and symbol is not None:
                    identity = (market, symbol)
                    completed_by_symbol[identity] = (
                        completed_by_symbol.get(identity, 0) + streams
                    )
                    if stream_status in {"BLOCKED", "UNAVAILABLE"}:
                        failure_key = ":".join(
                            (
                                market,
                                kind or "unknown",
                                timeframe or "none",
                                stream_reason or "UNKNOWN",
                            )
                        )
                        stream_failure_summary[failure_key] += 1
                    if (
                        kind == "klines"
                        and isinstance(timeframe, str)
                        and timeframe in active_collection_timeframes
                    ):
                        dashboard_statuses_by_symbol.setdefault(identity, {})[
                            timeframe
                        ] = stream_status or "UNKNOWN"
                        dashboard_statuses = dashboard_statuses_by_symbol[identity]
                        if identity not in analysis_started and len(
                            dashboard_statuses
                        ) == len(active_collection_timeframes):
                            analysis_started.add(identity)
                            analysis_ready = all(
                                dashboard_statuses.get(required)
                                in _ANALYSIS_READY_STREAM_STATES
                                for required in active_collection_timeframes
                            )
                    if completed_by_symbol[identity] == required_streams[identity]:
                        completed_symbols += 1
                monotonic_now = time.monotonic()
                if (
                    not force
                    and completed_streams > 1
                    and (
                        completed_streams % 10
                        and monotonic_now - last_progress_write < 5
                    )
                ):
                    return analysis_ready
                self._write_collection_progress(
                    cycle_started_at=now,
                    active_market=market,
                    completed_symbols=completed_symbols,
                    total_symbols=total_symbols,
                    completed_streams=completed_streams,
                    total_streams=total_streams,
                    blockers=blockers,
                    collector_coverage=coverage_projection(),
                    opportunity_analysis_summary=dict(
                        sorted(opportunity_analysis_summary.items())
                    ),
                    dashboard_opportunity_projection=opportunity_projection_payload(),
                    stream_failure_summary=dict(sorted(stream_failure_summary.items())),
                )
                last_progress_write = monotonic_now
            return analysis_ready

        publish_progress(None, force=True)
        if not universe.blockers:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:

                def collect_stream(
                    market: str,
                    symbol: str,
                    transport: JsonTransport,
                    kind: str,
                    timeframe: str | None,
                ) -> dict[str, object]:
                    result = self._collect_stream(
                        market,
                        symbol,
                        transport,
                        now,
                        kind=kind,
                        timeframe=timeframe,
                    )
                    record_coverage(
                        result,
                        market=market,
                        kind=kind,
                        timeframe=timeframe,
                    )
                    analysis_ready = publish_progress(
                        market,
                        symbol,
                        streams=1,
                        stream_status=str(result.get("status", "UNKNOWN")),
                        stream_reason=str(result.get("reason", "UNKNOWN")),
                        kind=kind,
                        timeframe=timeframe,
                    )
                    screen_ready = False
                    if market in staged_markets and kind == "klines":
                        with progress_lock:
                            identity = (market, symbol)
                            statuses = dashboard_statuses_by_symbol.get(identity, {})
                            if identity not in screening_started and all(
                                tf in statuses for tf in active_collection_timeframes
                            ):
                                screening_started.add(identity)
                                screen_ready = True
                    if screen_ready and self.on_symbol_screen is not None:
                        try:
                            screening = dict(
                                self.on_symbol_screen(
                                    market_labels[market], symbol, datetime.now(UTC)
                                )
                            )
                        except Exception as error:
                            screening = {
                                "status": "DATA_BLOCKED",
                                "enrichment_required": False,
                                "blockers": ["OPPORTUNITY_SCREEN_FAILED"],
                                "error_category": type(error).__name__[:100],
                                **_SAFE_STATE,
                            }
                        result["opportunity_screening"] = screening
                        with progress_lock:
                            opportunity_analysis_summary[
                                "SCREEN_" + str(screening.get("status", "UNKNOWN"))
                            ] += 1
                            if screening.get("enrichment_required") is not True:
                                record_opportunity_analysis(
                                    market_labels[market], symbol, screening
                                )
                    if analysis_ready and self.on_symbol_ready is not None:
                        try:
                            analysis = dict(
                                self.on_symbol_ready(
                                    market_labels[market], symbol, datetime.now(UTC)
                                )
                            )
                        except Exception as error:
                            analysis = {
                                "status": "BLOCKED",
                                "blockers": ["OPPORTUNITY_ANALYSIS_FAILED"],
                                "error_category": type(error).__name__[:100],
                                **_SAFE_STATE,
                            }
                        result["opportunity_analysis"] = analysis
                        with progress_lock:
                            opportunity_analysis_summary[
                                str(analysis.get("status", "UNKNOWN"))
                            ] += 1
                            record_opportunity_analysis(
                                market_labels[market], symbol, analysis
                            )
                        publish_progress(market, force=True)
                    return result

                # Do not submit the whole universe at once. A 1,300-symbol
                # universe has more than 10,000 streams; an unbounded future
                # set makes a new dashboard request wait behind an hours-long
                # batch and holds avoidable memory. This bounded, deterministic
                # queue keeps all direct Binance work moving while reserving the
                # next available worker for a valid dashboard request.
                background = deque(stream_items)
                priority: deque[tuple[str, str, JsonTransport, str, str | None]] = (
                    deque()
                )
                pending: dict[
                    Future[dict[str, object]],
                    tuple[str, str, JsonTransport, str, str | None],
                ] = {}
                completed_stream_keys: set[tuple[str, str, str, str | None]] = set()
                active_request = refresh_request
                active_identity = requested_identity
                request_remaining: set[tuple[str, str | None]] = set()

                def enqueue_enrichment(identity: tuple[str, str]) -> None:
                    nonlocal total_streams, completed_symbols
                    if identity[0] not in staged_markets:
                        return
                    transport = next(t for m, s, t in work_items if (m, s) == identity)
                    queued_keys = {
                        (m, s, k, tf)
                        for m, s, _, k, tf in (
                            *background,
                            *priority,
                            *pending.values(),
                        )
                    } | completed_stream_keys
                    added = 0
                    for tf in _ENRICHMENT_TIMEFRAMES:
                        if (*identity, "klines", tf) not in queued_keys:
                            background.append((*identity, transport, "klines", tf))
                            added += 1
                    if added:
                        with progress_lock:
                            if (
                                completed_by_symbol.get(identity, 0)
                                == required_streams[identity]
                            ):
                                completed_symbols -= 1
                            required_streams[identity] += added
                            total_streams += added

                def activate_pending_request() -> None:
                    nonlocal active_request, active_identity, request_remaining
                    if active_request is not None or self.refresh_request_path is None:
                        return
                    try:
                        candidate = _read_refresh_request(self.refresh_request_path)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        if "MARKET_HISTORY_REFRESH_REQUEST_INVALID" not in blockers:
                            blockers.append("MARKET_HISTORY_REFRESH_REQUEST_INVALID")
                        return
                    if candidate is None or candidate.get("status") != "PENDING":
                        return
                    requested_market = (
                        "spot" if candidate["market"] == "SPOT" else "usd_m_futures"
                    )
                    identity = (requested_market, str(candidate["symbol"]))
                    if identity not in required_streams:
                        self._complete_refresh_request(
                            candidate,
                            now,
                            status="DATA_BLOCKED",
                            blockers=("MARKET_HISTORY_REFRESH_REQUEST_INELIGIBLE",),
                        )
                        return
                    active_request = candidate
                    active_identity = identity
                    enqueue_enrichment(identity)
                    request_remaining = {
                        ("klines", timeframe)
                        for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
                    }
                    request_remaining.difference_update(
                        (kind, timeframe)
                        for market, symbol, kind, timeframe in completed_stream_keys
                        if (market, symbol) == identity
                    )
                    queued = tuple(background)
                    background.clear()
                    for item in queued:
                        if item[:2] == identity:
                            priority.append(item)
                        else:
                            background.append(item)

                def submit_available() -> None:
                    activate_pending_request()

                    def take_runnable(
                        queue: deque[
                            tuple[
                                str,
                                str,
                                JsonTransport,
                                str,
                                str | None,
                            ]
                        ],
                    ) -> tuple[str, str, JsonTransport, str, str | None] | None:
                        supplemental_inflight = sum(
                            1
                            for (
                                _,
                                _,
                                _,
                                pending_kind,
                                pending_timeframe,
                            ) in pending.values()
                            if self._is_supplemental_stream(
                                pending_kind, pending_timeframe
                            )
                        )
                        for _ in range(len(queue)):
                            candidate = queue.popleft()
                            market, symbol, _, kind, timeframe = candidate
                            # Finish the whole baseline universe before optional
                            # enrichment or legacy COIN-M work consumes a worker.
                            if (
                                staged
                                and queue is background
                                and not (
                                    market in staged_markets
                                    and kind == "klines"
                                    and timeframe in active_collection_timeframes
                                )
                                and any(
                                    m in staged_markets
                                    and k == "klines"
                                    and tf in active_collection_timeframes
                                    for m, _, _, k, tf in (*queue, *pending.values())
                                )
                            ):
                                queue.append(candidate)
                                continue
                            if not self._is_supplemental_stream(kind, timeframe):
                                return candidate
                            identity = (market, symbol)
                            with progress_lock:
                                dashboard_finished = len(
                                    dashboard_statuses_by_symbol.get(identity, {})
                                ) == len(active_collection_timeframes)
                            if (
                                dashboard_finished
                                and supplemental_inflight < _SUPPLEMENTAL_STREAM_WORKERS
                            ):
                                return candidate
                            queue.append(candidate)
                        return None

                    while len(pending) < self.max_workers and (priority or background):
                        item = take_runnable(priority) or take_runnable(background)
                        if item is None:
                            break
                        pending[executor.submit(collect_stream, *item)] = item

                def complete_active_request() -> None:
                    nonlocal active_request, active_identity, request_remaining
                    if (
                        active_request is None
                        or active_identity is None
                        or request_remaining
                    ):
                        return
                    request_results = [
                        result
                        for result in results
                        if (result.get("market"), result.get("symbol"))
                        == active_identity
                    ]
                    request_blockers = self._refresh_request_data_blockers(
                        active_identity[0], active_identity[1], now, request_results
                    )
                    self._complete_refresh_request(
                        active_request,
                        now,
                        status="DATA_READY" if not request_blockers else "DATA_BLOCKED",
                        blockers=request_blockers,
                    )
                    active_request = None
                    active_identity = None

                # A request already present at cycle start is promoted before
                # the first background stream. Requests arriving later are
                # promoted at the next completion boundary, never after the
                # complete-universe batch drains.
                if refresh_request is not None and requested_identity is not None:
                    active_request = None
                    active_identity = None
                    activate_pending_request()
                submit_available()
                while pending:
                    completed, _ = wait(
                        pending,
                        timeout=_PROGRESS_HEARTBEAT_SECONDS,
                        return_when=FIRST_COMPLETED,
                    )
                    if not completed:
                        publish_progress(
                            active_identity[0] if active_identity else None,
                            force=True,
                        )
                    refresh_snapshots(datetime.now(UTC))
                    for future in completed:
                        item = pending.pop(future)
                        result = future.result()
                        results.append(result)
                        market, symbol, _, kind, timeframe = item
                        completed_stream_keys.add((market, symbol, kind, timeframe))
                        screening = result.get("opportunity_screening")
                        if isinstance(screening, Mapping) and (
                            screening.get("status") == "CURRENT"
                            and screening.get("enrichment_required") is True
                            and screening.get("execution_allowed") is False
                            and screening.get("live_eligibility_status")
                            == "LIVE_ORDER_BLOCKED"
                        ):
                            enqueue_enrichment((market, symbol))
                        if active_identity == (market, symbol):
                            request_remaining.discard((kind, timeframe))
                    complete_active_request()
                    submit_available()
        if any(item["status"] == "BLOCKED" for item in results):
            blockers.append("MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE")
        if any(item["status"] == "BACKFILLING" for item in results):
            blockers.append("MARKET_DATA_BACKFILL_PENDING")
        if any(item["status"] == "UNAVAILABLE" for item in results):
            blockers.append("MARKET_DATA_RANGE_UNAVAILABLE")
        if any(
            isinstance(analysis := item.get("opportunity_analysis"), Mapping)
            and analysis.get("status") == "BLOCKED"
            for item in results
        ):
            blockers.append("OPPORTUNITY_ANALYSIS_FAILURE")
        if any(
            isinstance(analysis := item.get("opportunity_analysis"), Mapping)
            and analysis.get("status") == "DATA_BLOCKED"
            for item in results
        ):
            blockers.append("OPPORTUNITY_ANALYSIS_DATA_BLOCKED")
        if any(
            isinstance(screen := item.get("opportunity_screening"), Mapping)
            and screen.get("status") != "CURRENT"
            for item in results
        ):
            blockers.append("OPPORTUNITY_SCREENING_DATA_BLOCKED")
        payload: dict[str, object] = {
            "schema_version": "2.0",
            "observed_at": now.isoformat(),
            "status": "DEGRADED" if blockers else "READY",
            "timeframes": list(VIRTUAL_MARKET_COLLECTION_TIMEFRAMES),
            "timeframe_refresh_schedule": timeframe_refresh_schedule(),
            "collection_plan": self._collection_plan(),
            "initial_history_days": self.initial_days,
            "spot_universe_count": len(universe.spot_symbols),
            "futures_universe_count": len(universe.futures_symbols),
            "coin_m_universe_count": len(universe.coin_m_symbols),
            "excluded_asset_count": len(universe.excluded_assets),
            "archive_root": str(self.history.archive_root),
            "completed_symbols": completed_symbols,
            "total_symbols": total_symbols,
            "completed_streams": completed_streams,
            "total_streams": total_streams,
            "completion_ratio": self._completion_ratio(
                completed_streams, total_streams
            ),
            "collector_coverage": coverage_projection(),
            "opportunity_analysis_summary": dict(
                sorted(opportunity_analysis_summary.items())
            ),
            "dashboard_opportunity_projection": opportunity_projection_payload(),
            "stream_failure_summary": dict(sorted(stream_failure_summary.items())),
            # The state is a dashboard-facing projection, not an unbounded
            # event dump. Dataset manifests and collection-progress files keep
            # stream-level evidence; this bounded sample prevents the state
            # itself from becoming unreadable by the loopback dashboard.
            "result_count": len(results),
            "result_summary": dict(
                sorted(Counter(str(item["status"]) for item in results).items())
            ),
            "results": results[:_STATE_RESULT_SAMPLE_LIMIT],
            "results_truncated": len(results) > _STATE_RESULT_SAMPLE_LIMIT,
            "blockers": sorted(set(blockers)),
            **_SAFE_STATE,
        }
        payload["network"] = {
            key: value - before[key] for key, value in self._network_totals().items()
        }
        _save(self.history.state_path, payload)
        return payload

    def _complete_refresh_request(
        self,
        request: dict[str, object],
        observed_at: datetime,
        *,
        status: str,
        blockers: tuple[str, ...],
    ) -> None:
        if self.refresh_request_path is None:
            return
        completed_at = self.clock()
        if completed_at.utcoffset() is None:
            raise ValueError("market refresh completion clock must be timezone-aware")
        requested_at = datetime.fromisoformat(str(request["requested_at"]))
        if requested_at.utcoffset() is None:
            raise ValueError("market refresh request timestamp must be timezone-aware")
        completion_utc = completed_at.astimezone(UTC)
        requested_utc = requested_at.astimezone(UTC)
        result = {
            **request,
            "status": status,
            "completed_at": max(completion_utc, requested_utc).isoformat(),
            "blockers": list(blockers),
        }
        write_json_object_verified(
            self.refresh_request_path,
            result,
            blocker="MARKET_HISTORY_REFRESH_REQUEST_COMPLETE_WRITE_FAILED",
            subject_id=str(request["request_id"]),
            indent=2,
            durable=True,
        )

    def _refresh_request_data_blockers(
        self,
        market: str,
        symbol: str,
        now: datetime,
        results: list[dict[str, object]],
    ) -> tuple[str, ...]:
        archive = ParquetOHLCVArchive(self.history.archive_root / market)
        blockers: list[str] = []
        for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES:
            try:
                manifest = archive.manifest(symbol, timeframe)
                last_close = datetime.fromisoformat(
                    manifest.last_timestamp
                ) + timeframe_duration(timeframe)
                if manifest.row_count < (self.minimum_candles or 1):
                    blockers.append(
                        f"MARKET_HISTORY_REFRESH_INSUFFICIENT_CANDLES:{timeframe}"
                    )
                elif manifest.gap_count:
                    blockers.append(f"MARKET_HISTORY_REFRESH_DATASET_GAPS:{timeframe}")
                elif now - last_close > timeframe_duration(timeframe) * 2:
                    blockers.append(f"MARKET_HISTORY_REFRESH_DATA_STALE:{timeframe}")
            except (OSError, ValueError, TypeError):
                blockers.append(
                    f"MARKET_HISTORY_REFRESH_DATASET_UNAVAILABLE:{timeframe}"
                )
        if market == "usd_m_futures" and any(
            item.get("kind")
            in {
                "markPriceKlines",
                "indexPriceKlines",
                "funding",
                "open_interest",
            }
            and item.get("status") in {"BLOCKED", "UNAVAILABLE"}
            for item in results
        ):
            blockers.append("FUTURES_DERIVATIVES_CONTEXT_UNAVAILABLE")
        return tuple(sorted(set(blockers)))

    @staticmethod
    def _interleaved_market_work(
        market_work: tuple[tuple[str, tuple[str, ...], JsonTransport | None], ...],
    ) -> tuple[tuple[str, str, JsonTransport], ...]:
        """Return market-symbol work in fair, deterministic rounds."""

        maximum = max(
            (len(symbols) for _, symbols, transport in market_work if transport),
            default=0,
        )
        work: list[tuple[str, str, JsonTransport]] = []
        for index in range(maximum):
            for market, symbols, transport in market_work:
                if transport is not None and index < len(symbols):
                    work.append((market, symbols[index], transport))
        return tuple(work)

    @staticmethod
    def _collection_kinds(market: str) -> tuple[tuple[str, str | None], ...]:
        if market == "spot":
            return tuple(
                ("klines", timeframe)
                for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
            )
        if market in {"usd_m_futures", "coin_m_futures"}:
            return (
                *(
                    ("klines", timeframe)
                    for timeframe in VIRTUAL_MARKET_COLLECTION_TIMEFRAMES
                ),
                ("markPriceKlines", "5m"),
                ("indexPriceKlines", "5m"),
                ("funding", None),
                ("open_interest", None),
            )
        raise ValueError("collection market is invalid")

    @staticmethod
    def _is_supplemental_stream(kind: str, timeframe: str | None) -> bool:
        """Keep large/non-dashboard streams off the fast dashboard lane."""

        return kind != "klines" or timeframe not in _SCREEN_TIMEFRAMES

    def _interleaved_stream_work(
        self,
        market_work: tuple[tuple[str, str, JsonTransport], ...],
    ) -> tuple[tuple[str, str, JsonTransport, str, str | None], ...]:
        """Finish watched symbols first, then schedule fair universe backfill."""

        streams: list[tuple[str, str, JsonTransport, str, str | None]] = []
        priority_set = frozenset(self.priority_symbols)
        priority_work = tuple(item for item in market_work if item[1] in priority_set)
        background_work = tuple(
            item for item in market_work if item[1] not in priority_set
        )
        # A configured watch symbol should become dashboard-usable without
        # waiting behind the complete eligible universe. This changes only
        # deterministic ordering; it neither skips a stream nor relaxes gates.
        for market, symbol, transport in priority_work:
            for kind, timeframe in self._collection_kinds(market):
                streams.append((market, symbol, transport, kind, timeframe))
        # Keep each background symbol's direct streams contiguous. Workers may
        # fetch later symbols concurrently, while the first fully current
        # symbol can immediately enter the bounded opportunity-analysis stage.
        for market, symbol, transport in background_work:
            for kind, timeframe in self._collection_kinds(market):
                streams.append((market, symbol, transport, kind, timeframe))
        return tuple(streams)

    def _prioritized_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        """Place configured watched symbols ahead of bounded backfill work."""

        eligible = frozenset(symbols)
        priority = tuple(
            symbol for symbol in self.priority_symbols if symbol in eligible
        )
        priority_set = frozenset(priority)
        return priority + tuple(
            symbol for symbol in symbols if symbol not in priority_set
        )

    def _collection_plan(self) -> dict[str, object]:
        staged = self.on_symbol_screen is not None
        return {
            "mode": "TOP_VOLUME_FULL_MULTITF" if staged else "FULL_HISTORY",
            "screen_timeframes": list(_SCREEN_TIMEFRAMES) if staged else [],
            "enrichment_timeframes": list(_ENRICHMENT_TIMEFRAMES) if staged else [],
            "enrichment_scope": "ALL_SELECTED_SYMBOLS" if staged else "ALL",
            "deferred_streams": [
                "markPriceKlines",
                "indexPriceKlines",
                "funding",
                "open_interest",
                "coin_m_futures",
            ]
            if staged
            else [],
        }

    def _write_collection_progress(
        self,
        *,
        cycle_started_at: datetime,
        active_market: str | None,
        completed_symbols: int,
        total_symbols: int,
        completed_streams: int,
        total_streams: int,
        blockers: list[str],
        collector_coverage: Mapping[str, object],
        opportunity_analysis_summary: Mapping[str, int],
        dashboard_opportunity_projection: Mapping[str, object],
        stream_failure_summary: Mapping[str, int],
    ) -> None:
        _save(
            self.history.state_path,
            {
                "schema_version": "2.0",
                "status": "COLLECTING",
                "collection_plan": self._collection_plan(),
                "cycle_started_at": cycle_started_at.isoformat(),
                "observed_at": datetime.now(UTC).isoformat(),
                "active_market": active_market,
                "completed_symbols": completed_symbols,
                "total_symbols": total_symbols,
                "completed_streams": completed_streams,
                "total_streams": total_streams,
                "completion_ratio": self._completion_ratio(
                    completed_streams, total_streams
                ),
                "blockers": sorted({"MARKET_DATA_CYCLE_IN_PROGRESS", *blockers}),
                "collector_coverage": collector_coverage,
                "opportunity_analysis_summary": dict(opportunity_analysis_summary),
                "dashboard_opportunity_projection": dict(
                    dashboard_opportunity_projection
                ),
                "stream_failure_summary": dict(stream_failure_summary),
                **_SAFE_STATE,
            },
        )

    def record_recoverable_cycle_failure(
        self,
        observed_at: datetime,
        error: Exception,
    ) -> None:
        """Persist a fail-closed retry state without exposing exception text."""

        if observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        try:
            previous = _load(self.history.state_path)
        except (OSError, ValueError, TypeError):
            previous = {}
        previous_blockers = previous.get("blockers", ())
        if not isinstance(previous_blockers, (list, tuple)):
            previous_blockers = ()
        blockers = {
            str(item)
            for item in previous_blockers
            if isinstance(item, str) and item != "MARKET_DATA_CYCLE_IN_PROGRESS"
        }
        blockers.add("MARKET_HISTORY_CYCLE_RETRY_PENDING")
        payload: dict[str, object] = {
            "schema_version": "2.0",
            "status": "DEGRADED",
            "observed_at": observed_at.astimezone(UTC).isoformat(),
            "last_error_type": type(error).__name__,
            "last_error_code": _recoverable_error_code(error),
            "recovery_action": "RETRY_NEXT_CYCLE",
            "blockers": sorted(blockers),
            **_SAFE_STATE,
        }
        for key in (
            "cycle_started_at",
            "active_market",
            "completed_symbols",
            "total_symbols",
            "completed_streams",
            "total_streams",
            "completion_ratio",
        ):
            if key in previous:
                payload[key] = previous[key]
        _save(self.history.state_path, payload)

    @staticmethod
    def _completion_ratio(completed: int, total: int) -> str:
        if total <= 0:
            return "1.000000"
        return f"{Decimal(completed) / Decimal(total):.6f}"

    def _collect_symbol(
        self,
        market: str,
        symbol: str,
        transport: JsonTransport,
        now: datetime,
        *,
        on_stream_complete: Callable[[], None] | None = None,
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for kind, timeframe in self._collection_kinds(market):
            results.append(
                self._collect_stream(
                    market,
                    symbol,
                    transport,
                    now,
                    kind=kind,
                    timeframe=timeframe,
                )
            )
            if on_stream_complete is not None:
                on_stream_complete()
        return results

    def _collect_stream(
        self,
        market: str,
        symbol: str,
        transport: JsonTransport,
        now: datetime,
        *,
        kind: str,
        timeframe: str | None,
    ) -> dict[str, object]:
        """Collect exactly one market-data stream with fail-closed evidence."""

        try:
            if market == "coin_m_futures" and kind == "indexPriceKlines":
                pair = self.coin_m_contracts[symbol][0]
                owner = min(
                    name
                    for name, metadata in self.coin_m_contracts.items()
                    if metadata[0] == pair
                )
                if symbol != owner:
                    result: dict[str, object] = {
                        "status": "SHARED",
                        "dataset_symbol": pair,
                    }
                else:
                    result = self._candles(
                        market, symbol, kind, transport, now, timeframe="5m"
                    )
            elif kind in {"funding", "open_interest"}:
                result = self._details(symbol, kind, now, market=market)
            else:
                if timeframe is None:
                    raise ValueError("candle timeframe is required")
                result = self._candles(
                    market, symbol, kind, transport, now, timeframe=timeframe
                )
        except (OSError, ValueError, ArithmeticError, ExchangeError) as error:
            result = {
                "status": "BLOCKED",
                "reason": self._safe_stream_failure_reason(error),
            }
        return {
            "market": market,
            "symbol": symbol,
            "kind": kind,
            **({"timeframe": timeframe} if timeframe else {}),
            **result,
        }

    @staticmethod
    def _safe_stream_failure_reason(error: Exception) -> str:
        """Map internal exceptions to bounded codes without leaking details."""

        message = str(error).casefold()
        if "progress exceeds" in message:
            return "PROGRESS_AHEAD_OF_VERIFIED_DATASET"
        if "progress" in message and "invalid" in message:
            return "COLLECTION_PROGRESS_INVALID"
        if "dataset is missing" in message:
            return "VERIFIED_DATASET_MISSING"
        if "checksum" in message or "integrity" in message:
            return "DATASET_INTEGRITY_FAILURE"
        if "conflicting candle" in message:
            return "CONFLICTING_CANDLE"
        if "gap" in message:
            return "DATASET_GAP"
        if "time boundary" in message:
            return "CANDLE_TIME_BOUNDARY_INVALID"
        if "response" in message:
            return "BINANCE_RESPONSE_INVALID"
        if isinstance(error, ExchangeError):
            return "BINANCE_PUBLIC_SOURCE_FAILURE"
        if isinstance(error, OSError):
            return "MARKET_HISTORY_IO_FAILURE"
        if isinstance(error, ArithmeticError):
            return "MARKET_HISTORY_NUMERIC_FAILURE"
        return "MARKET_HISTORY_STREAM_INVALID"

    def _network_totals(self) -> dict[str, int]:
        transports = [
            item
            for item in (self.spot, self.futures, self.coin_m)
            if isinstance(item, MeteredPublicTransport)
        ]
        return {
            "rest_request_count": sum(item.request_count for item in transports),
            "rest_decoded_json_bytes": sum(
                item.decoded_json_bytes for item in transports
            ),
            "archive_downloaded_bytes": self.archive_downloaded_bytes,
            "archive_request_count": self.archive_request_count,
        }

    def _snapshots(
        self,
        market: str,
        symbols: tuple[str, ...],
        transport: JsonTransport,
        now: datetime,
    ) -> None:
        if not symbols:
            return
        prefix = _prefix(market)
        kinds: tuple[str, ...] = ("ticker/bookTicker", "ticker/24hr")
        if market != "spot":
            kinds += ("premiumIndex",)
        for kind in kinds:
            raw = transport.get_json(prefix + kind)
            if not isinstance(raw, list) or any(
                not isinstance(item, dict) for item in raw
            ):
                raise ValueError("public bulk snapshot must be an object array")
            selected = [item for item in raw if item.get("symbol") in symbols]
            if {item.get("symbol") for item in selected} != set(symbols):
                raise ValueError("public bulk snapshot coverage is incomplete")
            _save(
                self.history.archive_root
                / market
                / "metadata"
                / (kind.replace("/", "-") + ".json"),
                {
                    "observed_at": now.isoformat(),
                    "source": prefix + kind,
                    "rows": selected,
                    **_SAFE_STATE,
                },
            )
            if kind == "ticker/24hr":
                _save(
                    self.history.archive_root
                    / market
                    / "metadata"
                    / "wallet-price-coverage.json",
                    {
                        "observed_at": now.isoformat(),
                        "source": prefix + kind,
                        "rows": raw,
                        **_SAFE_STATE,
                    },
                )

    def _progress(
        self,
        directory: Path,
        now: datetime,
        *,
        extend_history: bool = False,
        initial_start: datetime | None = None,
        maximum_cursor: datetime | None = None,
        cursor_tolerance: timedelta = timedelta(0),
    ) -> tuple[Path, dict[str, object], datetime]:
        path = directory / "collection-progress.json"
        if path.exists():
            state = _load(path)
            if not {"next_at", "requested_start"} <= state.keys():
                raise ValueError("collection progress fields are missing")
            start = datetime.fromisoformat(str(state["next_at"]))
            origin = datetime.fromisoformat(str(state["requested_start"]))
            if start.utcoffset() is None or origin.utcoffset() is None:
                raise ValueError("collection progress is invalid or in the future")
            if (
                maximum_cursor is not None
                and cursor_tolerance > timedelta(0)
                and maximum_cursor < start <= maximum_cursor + cursor_tolerance
            ):
                start = maximum_cursor
                state["next_at"] = start.isoformat()
                state["closed_boundary_repaired_at"] = now.isoformat()
                _save(path, state)
            if not origin <= start <= now:
                raise ValueError("collection progress is invalid or in the future")
            required_start = initial_start or (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                - timedelta(days=self.initial_days)
            )
            if extend_history and origin > required_start:
                # Older collectors used a shorter bootstrap window.  Extend it
                # backwards without dropping verified parquet data, so the
                # closed 1d quality requirement can eventually be met.
                state["requested_start"] = required_start.isoformat()
                state["next_at"] = required_start.isoformat()
                state["coverage_extended_at"] = now.isoformat()
                _save(path, state)
                start = required_start
        else:
            start = initial_start or (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                - timedelta(days=self.initial_days)
            )
            state = {
                "requested_start": start.isoformat(),
                "next_at": start.isoformat(),
                **_SAFE_STATE,
            }
            _save(path, state)
        return path, state, start

    @staticmethod
    def _vision_kline_key(
        market: str,
        symbol: str,
        kind: str,
        timeframe: str,
        start: datetime,
        closed_history_end: datetime,
    ) -> tuple[str, datetime]:
        """Return one exact-interval Vision archive and its covered end.

        Monthly archives sharply reduce bootstrap requests. Daily archives fill
        partial months, without substituting a different source interval.
        """

        market_root = {
            "spot": "spot",
            "usd_m_futures": "futures/um",
            "coin_m_futures": "futures/cm",
        }[market]
        month_start = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        following_month = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        # A complete published monthly archive can satisfy a partial first
        # month too; the parser selects only rows at or after ``start``. This
        # replaces up to 30 daily ZIP plus checksum pairs with one verified
        # monthly pair without widening the requested history boundary.
        if following_month <= closed_history_end:
            month = month_start.strftime("%Y-%m")
            return (
                f"data/{market_root}/monthly/{kind}/{symbol}/{timeframe}/"
                f"{symbol}-{timeframe}-{month}.zip",
                following_month,
            )
        day_end = min(start + timedelta(days=1), closed_history_end)
        return (
            f"data/{market_root}/daily/{kind}/{symbol}/{timeframe}/"
            f"{symbol}-{timeframe}-{start.date().isoformat()}.zip",
            day_end,
        )

    @staticmethod
    def _parse_vision_candles(
        key: str,
        payload: bytes,
        start: datetime,
        end: datetime,
        *,
        interval: timedelta,
    ) -> tuple[OHLCVCandle, ...]:
        """Parse the requested exact interval from a verified Vision archive."""

        rows = _csv_rows(key, payload)
        if rows and (not rows[0] or not rows[0][0].strip().isdigit()):
            rows = rows[1:]
        selected: list[object] = []
        for row in rows:
            if not row:
                continue
            try:
                epoch = int(row[0])
                divisor = 1_000_000 if epoch >= 100_000_000_000_000 else 1_000
                timestamp = datetime.fromtimestamp(epoch / divisor, tz=UTC)
            except (IndexError, OSError, ValueError):
                raise ValueError("Vision kline timestamp is invalid") from None
            if start <= timestamp < end:
                selected.append(row)
        if not selected:
            raise MarketHistorySourceUnavailableError(key)
        return ContinuousMarketHistory._parse_rows(
            selected, start, end, interval=interval
        )

    def _record_archive_source(self, source: object) -> None:
        """Accumulate cache evidence safely while workers fetch distinct archives."""

        with self._metrics_lock:
            self.archive_request_count += int(
                getattr(source, "network_request_count", 0)
            )
            self.archive_downloaded_bytes += int(getattr(source, "downloaded_bytes", 0))

    def _candle_initial_start(
        self, now: datetime, interval: timedelta
    ) -> datetime | None:
        """Keep the configured history horizon and deterministic candle floor."""

        interval_seconds = int(interval.total_seconds())
        anchor = now.replace(second=0, microsecond=0)
        configured_anchor = anchor.replace(hour=0, minute=0)
        start = configured_anchor - timedelta(days=self.initial_days)
        if self.minimum_candles is not None:
            # Never narrow a requested historical horizon to the minimum
            # analysis window. Conversely, daily data retains the existing
            # 200-closed-candle hard gate even when the requested horizon is
            # three months.
            start = min(start, anchor - interval * (self.minimum_candles + 1))
        aligned_epoch = int(start.timestamp()) // interval_seconds * interval_seconds
        return datetime.fromtimestamp(aligned_epoch, tz=UTC)

    def _vision_history(
        self,
        *,
        market: str,
        symbol: str,
        kind: str,
        timeframe: str,
        archive: ParquetOHLCVArchive,
        dataset_symbol: str,
        state: dict[str, object],
        progress_path: Path,
        cursor: datetime,
        closed_history_end: datetime,
        interval: timedelta,
        now: datetime,
        replace_conflicts_from_sources: tuple[
            str, ...
        ] = _COMPATIBLE_DERIVED_SOURCE_PREFIXES,
    ) -> tuple[datetime, dict[str, object] | None]:
        """Materialize all published closed history without public REST calls."""

        while cursor < closed_history_end:
            month_start = cursor.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            following_month = (
                month_start.replace(year=month_start.year + 1, month=1)
                if month_start.month == 12
                else month_start.replace(month=month_start.month + 1)
            )
            # Dashboard intervals fit within the bounded REST page budget for
            # one partial month. Avoiding one ZIP plus checksum per day removes
            # the dominant bootstrap request overhead. Native interval archives
            # remain background work when a bounded REST tail is sufficient.
            if (
                timeframe in _DASHBOARD_REFRESH_TIMEFRAMES
                and following_month > closed_history_end
            ):
                break
            key, archive_end = self._vision_kline_key(
                market,
                symbol,
                kind,
                timeframe,
                cursor,
                closed_history_end,
            )
            try:
                source, payload = self.history.source_cache.verified(key, kind=kind)
                self._record_archive_source(source)
                candles = self._parse_vision_candles(
                    key, payload, cursor, archive_end, interval=interval
                )
            except MarketHistorySourceUnavailableError:
                # An archive may legitimately predate a new symbol's listing.
                # Search forward through closed history without replacing that
                # missing period with high-volume REST backfill requests.
                if not state.get("first_available_at"):
                    cursor = archive_end
                    state["next_at"] = cursor.isoformat()
                    _save(progress_path, state)
                    continue
                return cursor, {
                    "status": "UNAVAILABLE",
                    "next_at": cursor.isoformat(),
                    "reason": "BINANCE_VISION_ARCHIVE_UNAVAILABLE",
                }
            except ValueError as error:
                if (
                    timeframe in _DASHBOARD_REFRESH_TIMEFRAMES
                    and "kline page contains a gap" in str(error).casefold()
                ):
                    break
                raise
            if candles[0].timestamp > cursor and state.get("first_available_at"):
                return cursor, {
                    "status": "UNAVAILABLE",
                    "next_at": cursor.isoformat(),
                    "reason": "KLINE_GAP",
                }
            state.setdefault("first_available_at", candles[0].timestamp.isoformat())
            updated = archive.update(
                dataset_symbol,
                timeframe,
                candles,
                source=(
                    f"BINANCE_VISION_DIRECT_{timeframe.upper()}_SHA256:{source.sha256}"
                ),
                generated_at=now,
                replace_conflicts_from_sources=replace_conflicts_from_sources,
            )
            last = datetime.fromisoformat(updated.last_timestamp)
            cursor = max(candles[-1].timestamp + interval, last + interval)
            if cursor < archive_end:
                return cursor, {
                    "status": "UNAVAILABLE",
                    "next_at": cursor.isoformat(),
                    "reason": "KLINE_GAP",
                }
            state["next_at"] = cursor.isoformat()
            _save(progress_path, state)
        return cursor, None

    def _candles(
        self,
        market: str,
        symbol: str,
        kind: str,
        transport: JsonTransport,
        now: datetime,
        *,
        timeframe: str = "5m",
    ) -> dict[str, object]:
        if timeframe not in MARKET_HISTORY_TIMEFRAMES:
            raise ValueError("candle timeframe is invalid")
        interval = timeframe_duration(timeframe)
        suffix = {
            "klines": "",
            "markPriceKlines": "_mark",
            "indexPriceKlines": "_index",
        }[kind]
        archive = ParquetOHLCVArchive(self.history.archive_root / f"{market}{suffix}")
        dataset_symbol = (
            self.coin_m_contracts[symbol][0]
            if market == "coin_m_futures" and kind == "indexPriceKlines"
            else symbol
        )
        directory = archive.root / dataset_symbol
        progress_directory = directory / timeframe
        interval_seconds = int(interval.total_seconds())
        end = datetime.fromtimestamp(
            int(now.timestamp()) // interval_seconds * interval_seconds,
            tz=UTC,
        )
        progress_path, state, cursor = self._progress(
            progress_directory,
            now,
            extend_history=True,
            initial_start=self._candle_initial_start(now, interval),
            maximum_cursor=end,
            cursor_tolerance=interval,
        )
        # Check the durable dataset before trusting progress; never silently reset
        # corrupt/missing storage and thereby skip an offline interval.
        parquet = directory / f"{timeframe}.parquet"
        replace_conflicts_from_sources: tuple[str, ...] = (
            _COMPATIBLE_DERIVED_SOURCE_PREFIXES
        )
        verified_ranges: list[tuple[datetime, datetime]] = []
        if parquet.exists():
            manifest = archive.manifest(dataset_symbol, timeframe)
            if manifest.gaps:
                # Collapse identical legacy rows through the canonical merge;
                # conflicting values remain an integrity failure.
                manifest = archive.update(
                    dataset_symbol,
                    timeframe,
                    archive.read(dataset_symbol, timeframe),
                    source=manifest.source,
                    generated_at=now,
                )
            manifest_last = datetime.fromisoformat(manifest.last_timestamp)
            manifest_generated = datetime.fromisoformat(manifest.generated_at)
            if manifest_generated < manifest_last + interval:
                # Compatibility repair for collectors that persisted the last
                # still-open candle. Its generation timestamp is durable proof
                # that the provider value was sampled before the candle closed.
                # Never broaden this to an arbitrary direct-source conflict:
                # genuinely closed conflicting candles must remain fail-closed.
                archive.truncate_from(
                    dataset_symbol,
                    timeframe,
                    start_at=manifest_last,
                    source="UNCLOSED_CANDLE_COMPATIBILITY_REPAIR",
                    generated_at=now,
                )
                cursor = min(cursor, manifest_last)
                state["next_at"] = cursor.isoformat()
                state["unclosed_candle_repaired_at"] = now.isoformat()
                _save(progress_path, state)
                manifest = archive.manifest(dataset_symbol, timeframe)
            if datetime.fromisoformat(manifest.last_timestamp) >= end:
                manifest = archive.truncate_from(
                    dataset_symbol,
                    timeframe,
                    start_at=end,
                    source="CLOSED_CANDLE_BOUNDARY_REPAIR",
                    generated_at=now,
                )
            last = datetime.fromisoformat(manifest.last_timestamp) + interval
            if cursor > last:
                raise ValueError("collection progress exceeds the verified dataset")
            if manifest.gaps:
                gap_start = (
                    datetime.fromisoformat(manifest.gaps[0].split("->")[0]) + interval
                )
                cursor = min(cursor, gap_start)
            range_start = datetime.fromisoformat(manifest.first_timestamp)
            for gap in manifest.gaps:
                left, right = (
                    datetime.fromisoformat(value) for value in gap.split("->")
                )
                if right <= left:
                    raise ValueError("dataset sequence is invalid")
                verified_ranges.append((range_start, left + interval))
                range_start = right
            verified_ranges.append((range_start, last))
        elif state.get("first_available_at"):
            raise ValueError("collection dataset is missing")

        def missing_window(start: datetime) -> tuple[datetime, datetime]:
            for stored_start, stored_end in verified_ranges:
                if start < stored_start:
                    return start, min(end, stored_start)
                if start < stored_end:
                    start = stored_end
            return start, end

        cursor, request_end = missing_window(cursor)
        # Existing datasets need only their exact holes or tail. A monthly ZIP
        # would replay verified rows; retain bulk archives for initial bootstrap.
        if self.vision_history_enabled and not verified_ranges:
            closed_history_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            cursor, unavailable = self._vision_history(
                market=market,
                symbol=symbol,
                kind=kind,
                timeframe=timeframe,
                archive=archive,
                dataset_symbol=dataset_symbol,
                state=state,
                progress_path=progress_path,
                cursor=cursor,
                closed_history_end=min(closed_history_end, end),
                interval=interval,
                now=now,
                replace_conflicts_from_sources=replace_conflicts_from_sources,
            )
            if unavailable is not None:
                return unavailable
        source = f"BINANCE_PUBLIC_REST_{timeframe.upper()}"
        pending_candles: list[OHLCVCandle] = []

        def flush_rest_batch() -> None:
            nonlocal cursor
            if not pending_candles:
                return
            closed_batch = tuple(pending_candles)
            updated = archive.update(
                dataset_symbol,
                timeframe,
                closed_batch,
                source=source,
                generated_at=now,
                replace_conflicts_from_sources=replace_conflicts_from_sources,
            )
            last_stored = datetime.fromisoformat(updated.last_timestamp)
            state.setdefault(
                "first_available_at", pending_candles[0].timestamp.isoformat()
            )
            if not updated.gaps:
                cursor = max(cursor, last_stored + interval)
            state["next_at"] = cursor.isoformat()
            _save(progress_path, state)
            pending_candles.clear()

        for _ in range(self.pages_per_stream):
            cursor, request_end = missing_window(cursor)
            if cursor >= end:
                break
            rows: list[object]
            prefix = _prefix(market)
            remaining_intervals = max(
                1,
                int(
                    (
                        (request_end - cursor).total_seconds()
                        + interval.total_seconds()
                        - 1
                    )
                    // interval.total_seconds()
                ),
            )
            params: dict[str, str | int] = {
                "pair" if kind == "indexPriceKlines" else "symbol": symbol,
                "interval": timeframe,
                "startTime": int(cursor.timestamp() * 1000),
                "endTime": int(request_end.timestamp() * 1000) - 1,
                "limit": min(
                    499,
                    remaining_intervals,
                ),
            }
            if market == "coin_m_futures" and kind == "indexPriceKlines":
                params["pair"] = self.coin_m_contracts[symbol][0]
            raw = transport.get_json(prefix + kind, params)
            if not isinstance(raw, list):
                raise ValueError("kline response must be an array")
            rows = raw
            if not rows:
                flush_rest_batch()
                return {"status": "UNAVAILABLE", "next_at": cursor.isoformat()}
            if len(rows) > 499:
                raise ValueError("kline response exceeds its page limit")
            candles = self._parse_rows(rows, cursor, request_end, interval=interval)
            if candles[0].timestamp > cursor and state.get("first_available_at"):
                flush_rest_batch()
                return {
                    "status": "UNAVAILABLE",
                    "next_at": cursor.isoformat(),
                    "reason": "KLINE_GAP",
                }
            # Keep all twelve source fields, including quote/taker volume and
            # trade count, alongside the existing OHLCV compatibility projection.
            raw_payload: dict[str, object] = {
                "source": source,
                "volume_unit": "CONTRACTS"
                if market == "coin_m_futures" and kind == "klines"
                else "PROVIDER_NATIVE",
                "rows": rows,
                **_SAFE_STATE,
            }
            digest = sha256(
                json.dumps(raw_payload, sort_keys=True).encode()
            ).hexdigest()
            _save(directory / "sources" / f"{digest}.json", raw_payload)
            pending_candles.extend(candles)
            cursor = candles[-1].timestamp + interval
        flush_rest_batch()
        cursor, _ = missing_window(cursor)
        if state.get("next_at") != cursor.isoformat():
            state["next_at"] = cursor.isoformat()
            _save(progress_path, state)
        return {
            "status": "CURRENT" if cursor >= end else "BACKFILLING",
            "next_at": cursor.isoformat(),
            "requested_start": state["requested_start"],
            "first_available_at": state.get("first_available_at"),
        }

    @staticmethod
    def _parse_rows(
        rows: list[object],
        start: datetime,
        end: datetime,
        *,
        interval: timedelta = _DEFAULT_KLINE_INTERVAL,
    ) -> tuple[OHLCVCandle, ...]:
        candles: list[OHLCVCandle] = []
        for raw in rows:
            if not isinstance(raw, (list, tuple)) or len(raw) != 12:
                raise ValueError("kline must have twelve fields")
            values = [str(value) for value in raw]
            epoch = int(values[0])
            divisor = 1_000_000 if epoch >= 100_000_000_000_000 else 1000
            timestamp = datetime.fromtimestamp(epoch / divisor, tz=UTC)
            close_at = datetime.fromtimestamp(int(values[6]) / divisor, tz=UTC)
            if (
                not start <= timestamp < end
                or timestamp.second
                or timestamp.microsecond
                or not timestamp <= close_at < timestamp + interval
            ):
                raise ValueError("kline time boundary is invalid")
            if candles and timestamp != candles[-1].timestamp + interval:
                raise ValueError(
                    "kline page contains a gap, duplicate, or reversed cursor"
                )
            for index in (5, 7, 9, 10):
                number = Decimal(values[index])
                if not number.is_finite() or number < 0:
                    raise ValueError("kline volume is invalid")
            if int(values[8]) < 0:
                raise ValueError("kline trade count is invalid")
            candles.append(
                OHLCVCandle(
                    timestamp=timestamp,
                    open=Decimal(values[1]),
                    high=Decimal(values[2]),
                    low=Decimal(values[3]),
                    close=Decimal(values[4]),
                    volume=Decimal(values[5]),
                )
            )
        return tuple(candles)

    def _details(
        self, symbol: str, kind: str, now: datetime, *, market: str = "usd_m_futures"
    ) -> dict[str, object]:
        directory = self.history.archive_root / market / symbol / "details" / kind
        path, state, cursor = self._progress(directory, now)
        funding = kind == "funding"
        coin = market == "coin_m_futures"
        if coin and funding and self.coin_m_contracts[symbol][1] != "PERPETUAL":
            return {
                "status": "NOT_APPLICABLE",
                "reason": "DELIVERY_CONTRACT_HAS_NO_FUNDING",
            }
        end = now.replace(second=0, microsecond=0)
        if cursor >= end:
            return {"status": "CURRENT", "next_at": cursor.isoformat()}
        # Recover older OI from immutable daily metrics before requesting the
        # bounded REST tail. Missing archives retain their cursor for retry.
        if not funding and cursor < now - timedelta(days=29):
            return self._historical_metrics(
                symbol, directory, path, state, cursor, market=market
            )
        endpoint = (
            _prefix(market) + "fundingRate"
            if funding
            else "/futures/data/openInterestHist"
        )
        params: dict[str, str | int] = {
            "symbol": symbol,
            "startTime": int(cursor.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000) - 1,
            "limit": 500,
        }
        if not funding:
            params["period"] = "5m"
            if coin:
                params.pop("symbol")
                params["pair"], params["contractType"] = self.coin_m_contracts[symbol]
        transport = self.coin_m if coin else self.futures
        if transport is None:
            raise ValueError("COIN-M transport is unavailable")
        raw = transport.get_json(endpoint, params)
        if not isinstance(raw, list):
            raise ValueError("futures detail response must be an array")
        if len(raw) > 500:
            raise ValueError("futures detail response exceeds its page limit")
        timestamps: list[int] = []
        for item in raw:
            identity = (
                self.coin_m_contracts[symbol][0] if coin and not funding else symbol
            )
            if (
                not isinstance(item, dict)
                or item.get("pair" if coin and not funding else "symbol") != identity
            ):
                raise ValueError("futures detail symbol is invalid")
            if (
                coin
                and not funding
                and item.get("contractType") != self.coin_m_contracts[symbol][1]
            ):
                raise ValueError("COIN-M open-interest contract type is invalid")
            stamp = int(str(item.get("fundingTime" if funding else "timestamp")))
            if not int(cursor.timestamp() * 1000) <= stamp < int(
                end.timestamp() * 1000
            ) or (timestamps and stamp <= timestamps[-1]):
                raise ValueError("futures detail pagination is invalid")
            for field_name in (
                ("fundingRate",)
                if funding
                else ("sumOpenInterest", "sumOpenInterestValue")
            ):
                value = Decimal(str(item.get(field_name)))
                if not value.is_finite() or (not funding and value < 0):
                    raise ValueError("futures detail value is invalid")
            timestamps.append(stamp)
        if not raw and not funding:
            return {"status": "UNAVAILABLE", "next_at": cursor.isoformat()}
        next_at = (
            datetime.fromtimestamp((timestamps[-1] + 1) / 1000, tz=UTC)
            if len(raw) == 500
            else end
        )
        if not funding:
            next_at = min(
                end, datetime.fromtimestamp((timestamps[-1] + 300000) / 1000, tz=UTC)
            )
        _save(
            directory / f"{int(cursor.timestamp() * 1000)}.json",
            {
                "source": endpoint,
                "start_at": cursor.isoformat(),
                "end_at": next_at.isoformat(),
                "rows": raw,
                **_SAFE_STATE,
            },
        )
        state["next_at"] = next_at.isoformat()
        _save(path, state)
        return {
            "status": "CURRENT" if next_at >= end else "BACKFILLING",
            "next_at": next_at.isoformat(),
        }

    def _historical_metrics(
        self,
        symbol: str,
        directory: Path,
        progress_path: Path,
        state: dict[str, object],
        cursor: datetime,
        *,
        market: str = "usd_m_futures",
    ) -> dict[str, object]:
        target = cursor.date().isoformat()
        segment = "cm" if market == "coin_m_futures" else "um"
        key = (
            f"data/futures/{segment}/daily/metrics/{symbol}/"
            f"{symbol}-metrics-{target}.zip"
        )
        try:
            evidence, zipped = self.history.source_cache.verified(
                key, kind="open_interest_and_positioning"
            )
        except MarketHistorySourceUnavailableError:
            return {
                "status": "UNAVAILABLE",
                "next_at": cursor.isoformat(),
                "reason": "METRICS_ARCHIVE_NOT_PUBLISHED",
            }
        rows = _csv_rows(key, zipped)
        with self._metrics_lock:
            self.archive_downloaded_bytes += evidence.downloaded_bytes
            self.archive_request_count += evidence.network_request_count
        if not rows or len(rows) > 289:
            raise ValueError("metrics archive has invalid row count")
        header, *values = rows
        required = {
            "create_time",
            "symbol",
            "sum_open_interest",
            "sum_open_interest_value",
        }
        if not required <= set(header):
            raise ValueError("metrics archive schema is incomplete")
        records: list[dict[str, str]] = []
        previous: datetime | None = None
        for values_row in values:
            if len(values_row) != len(header):
                raise ValueError("metrics archive row is incomplete")
            item = dict(zip(header, values_row, strict=True))
            timestamp = datetime.fromisoformat(item["create_time"]).replace(tzinfo=UTC)
            if item["symbol"] != symbol or timestamp.date() != cursor.date():
                raise ValueError("metrics archive identity is invalid")
            if previous is not None and timestamp - previous != timedelta(minutes=5):
                raise ValueError("metrics archive contains a gap")
            previous = timestamp
            for name in ("sum_open_interest", "sum_open_interest_value"):
                number = Decimal(item[name])
                if not number.is_finite() or number < 0:
                    raise ValueError("metrics archive value is invalid")
            if timestamp >= cursor:
                records.append(item)
        if not records:
            return {"status": "UNAVAILABLE", "next_at": cursor.isoformat()}
        last = datetime.fromisoformat(records[-1]["create_time"]).replace(tzinfo=UTC)
        next_at = last + timedelta(minutes=5)
        _save(
            directory / f"{target}.json",
            {
                "source_key": key,
                "source_sha256": evidence.sha256,
                "rows": records,
                **_SAFE_STATE,
            },
        )
        state["next_at"] = next_at.isoformat()
        _save(progress_path, state)
        return {"status": "BACKFILLING", "next_at": next_at.isoformat()}


def _prefix(market: str) -> str:
    return {
        "spot": "/api/v3/",
        "usd_m_futures": "/fapi/v1/",
        "coin_m_futures": "/dapi/v1/",
    }[market]
