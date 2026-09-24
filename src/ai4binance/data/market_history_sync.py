"""Low-bandwidth Binance Spot and USD-M Futures history synchronization."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from threading import Lock
from typing import Final, cast
from urllib.error import HTTPError

from ai4binance.core.errors import ExchangeError
from ai4binance.data.archive import DatasetManifest, ParquetOHLCVArchive
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.integrations.binance import (
    BinanceEligibleMarketSnapshot,
    BinanceMarketUniverseProvider,
)
from ai4binance.ops.runtime import SingleInstanceLease
from ai4binance.schemas import OHLCVCandle

FetchBytes = Callable[[str], bytes]

MARKET_HISTORY_TIMEFRAMES: Final = ("5m", "15m", "1h", "4h", "1d")
_BASE_URL: Final = "https://data.binance.vision"
_ALLOWED_HOSTS: Final = frozenset({"data.binance.vision"})
_KEY_PATTERN: Final = re.compile(r"^data/[\w./-]+\.zip$")
_MAX_ARCHIVE_BYTES: Final = 128 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES: Final = 256 * 1024 * 1024
_UNIVERSE_CACHE_MAX_AGE: Final = timedelta(minutes=5)
_COLLECTION_MAX_SYMBOLS_PER_MARKET: Final = 50
_FAST_RETRY_BLOCKERS: Final = frozenset(
    {
        "PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",
        "PUBLIC_MARKET_UNIVERSE_EMPTY",
        "PUBLIC_MARKET_LIQUIDITY_UNIVERSE_UNAVAILABLE",
        "PUBLIC_MARKET_LIQUIDITY_UNIVERSE_EMPTY",
    }
)


def read_cached_market_universe(
    path: Path,
    observed_at: datetime,
    *,
    max_age: timedelta = _UNIVERSE_CACHE_MAX_AGE,
) -> BinanceEligibleMarketSnapshot | None:
    """Read a bounded, safety-constrained cached market universe.

    The five-minute default is deliberately shared by collection and read-only
    projections. A symbol can be delisted independently of candle freshness,
    so a dashboard must never retain an older market universe past its
    verification window.
    """
    try:
        if max_age <= timedelta(0):
            return None
        if (
            observed_at.utcoffset() is None
            or path.is_symlink()
            or path.stat().st_size > 2_000_000
        ):
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(payload["observed_at"])
        if (
            cached_at.utcoffset() is None
            or not timedelta(0) <= observed_at - cached_at <= max_age
        ):
            return None
        if (
            payload.get("execution_allowed") is not False
            or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            return None
        return BinanceEligibleMarketSnapshot(
            spot_symbols=tuple(payload["spot_symbols"]),
            futures_symbols=tuple(payload["futures_symbols"]),
            coin_m_contracts=tuple(
                tuple(item) for item in payload.get("coin_m_contracts", ())
            ),
            excluded_assets=tuple(
                (str(asset), tuple(reasons))
                for asset, reasons in payload["excluded_assets"]
            ),
        )
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return None


class MarketHistoryIntegrityError(ValueError):
    """Raised when public history cannot satisfy its integrity contract."""


class MarketHistorySourceUnavailableError(FileNotFoundError):
    """Raised when an expected immutable public archive is not published."""


@dataclass(frozen=True, slots=True)
class VerifiedCachedArchive:
    """A checksum-verified Binance Vision archive and bandwidth evidence."""

    kind: str
    key: str
    sha256: str
    byte_count: int
    cache_hit: bool
    network_request_count: int
    downloaded_bytes: int


@dataclass(frozen=True, slots=True)
class MarketHistorySymbolResult:
    """One market-symbol synchronization outcome."""

    market: str
    symbol: str
    status: str
    manifests: tuple[DatasetManifest, ...] = ()
    detail_sources: tuple[VerifiedCachedArchive, ...] = ()
    receipt_path: str | None = None
    blocker: str | None = None


@dataclass(frozen=True, slots=True)
class MarketHistorySyncReport:
    """Auditable result for one closed UTC day and current eligible universe."""

    observed_at: str
    target_day: str
    timeframes: tuple[str, ...]
    spot_universe_count: int
    futures_universe_count: int
    excluded_asset_count: int
    results: tuple[MarketHistorySymbolResult, ...]
    blockers: tuple[str, ...]
    state_path: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def downloaded_bytes(self) -> int:
        return sum(
            source.downloaded_bytes
            for result in self.results
            for source in result.detail_sources
        )

    @property
    def network_request_count(self) -> int:
        return sum(
            source.network_request_count
            for result in self.results
            for source in result.detail_sources
        )


@dataclass(frozen=True, slots=True)
class BinanceVisionArchiveCache:
    """Local immutable-source cache that never redownloads verified archives."""

    root: Path
    fetch: FetchBytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    @classmethod
    def with_network(
        cls,
        root: Path,
        *,
        timeout_seconds: float = 30.0,
        maximum_response_bytes: int = _MAX_ARCHIVE_BYTES,
    ) -> BinanceVisionArchiveCache:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1024 <= maximum_response_bytes <= _MAX_ARCHIVE_BYTES:
            raise ValueError("maximum_response_bytes is outside the safe range")

        unavailable_until = 0.0
        availability_lock = Lock()

        def fetch(url: str) -> bytes:
            nonlocal unavailable_until
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
                raise ValueError("Binance Vision URL is outside the allowlist")
            with availability_lock:
                if time.monotonic() < unavailable_until:
                    raise OSError("Binance Vision transport is cooling down")
            request = urllib.request.Request(  # noqa: S310 - allowlisted HTTPS.
                url,
                headers={"User-Agent": "ai4binance-research/0.1"},
            )
            try:
                with urllib.request.urlopen(  # noqa: S310  # nosec B310
                    request,
                    timeout=timeout_seconds,
                ) as response:
                    payload = cast(bytes, response.read(maximum_response_bytes + 1))
            except HTTPError as error:
                if error.code != 404:
                    delay = {418: 86400, 429: 900}.get(error.code, 30)
                    with availability_lock:
                        unavailable_until = time.monotonic() + delay
                raise
            except OSError:
                with availability_lock:
                    unavailable_until = time.monotonic() + 30
                raise
            if len(payload) > maximum_response_bytes:
                raise MarketHistoryIntegrityError(
                    "Binance Vision response exceeds the configured size limit"
                )
            return payload

        return cls(root=root, fetch=fetch)

    def verified(self, key: str, *, kind: str) -> tuple[VerifiedCachedArchive, bytes]:
        normalized = self._validated_key(key)
        archive_path = (self.root / Path(normalized)).resolve()
        checksum_path = archive_path.with_name(f"{archive_path.name}.CHECKSUM")
        if archive_path.exists() and checksum_path.exists():
            payload = archive_path.read_bytes()
            published = checksum_path.read_bytes()
            digest = self._verify_checksum(normalized, payload, published)
            return (
                VerifiedCachedArchive(
                    kind=kind,
                    key=normalized,
                    sha256=digest,
                    byte_count=len(payload),
                    cache_hit=True,
                    network_request_count=0,
                    downloaded_bytes=0,
                ),
                payload,
            )
        encoded_key = urllib.parse.quote(normalized, safe="/")
        url = f"{_BASE_URL}/{encoded_key}"
        network_request_count = 0
        downloaded_bytes = 0
        try:
            if checksum_path.exists():
                published = checksum_path.read_bytes()
            else:
                published = self.fetch(f"{url}.CHECKSUM")
                network_request_count += 1
                downloaded_bytes += len(published)
            if archive_path.exists():
                payload = archive_path.read_bytes()
            else:
                payload = self.fetch(url)
                network_request_count += 1
                downloaded_bytes += len(payload)
        except HTTPError as error:
            if error.code == 404:
                raise MarketHistorySourceUnavailableError(normalized) from None
            raise
        digest = self._verify_checksum(normalized, payload, published)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if not archive_path.exists():
            self._atomic_write(archive_path, payload)
        if not checksum_path.exists():
            self._atomic_write(checksum_path, published)
        return (
            VerifiedCachedArchive(
                kind=kind,
                key=normalized,
                sha256=digest,
                byte_count=len(payload),
                cache_hit=False,
                network_request_count=network_request_count,
                downloaded_bytes=downloaded_bytes,
            ),
            payload,
        )

    def _validated_key(self, key: str) -> str:
        normalized = key.strip().replace("\\", "/")
        if (
            not _KEY_PATTERN.fullmatch(normalized)
            or ".." in normalized.split("/")
            or normalized.startswith("/")
        ):
            raise ValueError("Binance Vision archive key is unsafe")
        target = (self.root / Path(normalized)).resolve()
        if self.root not in target.parents:
            raise ValueError("Binance Vision archive key escapes the cache root")
        return normalized

    @staticmethod
    def _verify_checksum(key: str, payload: bytes, published: bytes) -> str:
        try:
            expected = published.decode("ascii").strip().split()[0].lower()
        except (UnicodeError, IndexError):
            expected = ""
        actual = sha256(payload).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != actual:
            raise MarketHistoryIntegrityError(f"checksum mismatch: {key}")
        return actual

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)


@dataclass(frozen=True, slots=True)
class MarketHistorySynchronizer:
    """Materialize one closed day for every eligible Spot/Futures symbol."""

    universe_provider: BinanceMarketUniverseProvider
    archive_root: Path
    source_cache: BinanceVisionArchiveCache
    state_path: Path

    def sync_day(
        self,
        target_day: date,
        *,
        observed_at: datetime,
    ) -> MarketHistorySyncReport:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        observed_utc = observed_at.astimezone(UTC)
        day_end = datetime.combine(
            target_day + timedelta(days=1), datetime_time(), tzinfo=UTC
        )
        if observed_utc < day_end:
            raise ValueError("market history target day must be fully observable")

        universe = self._eligible_universe(observed_utc)
        if universe.blockers:
            report = MarketHistorySyncReport(
                observed_at=observed_utc.isoformat(),
                target_day=target_day.isoformat(),
                timeframes=MARKET_HISTORY_TIMEFRAMES,
                spot_universe_count=0,
                futures_universe_count=0,
                excluded_asset_count=len(universe.excluded_assets),
                results=(),
                blockers=universe.blockers,
                state_path=str(self.state_path),
            )
            self._write_report(report)
            return report

        results: list[MarketHistorySymbolResult] = []
        for symbol in universe.spot_symbols:
            results.append(self._sync_spot(symbol, target_day, observed_utc))
        for symbol in universe.futures_symbols:
            results.append(self._sync_futures(symbol, target_day, observed_utc))
        blockers = tuple(
            sorted({result.blocker for result in results if result.blocker is not None})
        )
        report = MarketHistorySyncReport(
            observed_at=observed_utc.isoformat(),
            target_day=target_day.isoformat(),
            timeframes=MARKET_HISTORY_TIMEFRAMES,
            spot_universe_count=len(universe.spot_symbols),
            futures_universe_count=len(universe.futures_symbols),
            excluded_asset_count=len(universe.excluded_assets),
            results=tuple(results),
            blockers=blockers,
            state_path=str(self.state_path),
        )
        self._write_report(report)
        return report

    def _eligible_universe(
        self,
        observed_at: datetime,
        *,
        force_refresh: bool = False,
    ) -> BinanceEligibleMarketSnapshot:
        """Return the current eligible market universe and renew its cache.

        ``force_refresh`` is used by long-running collectors at their metadata
        cadence. It prevents a current cache entry from masking a delisting
        until the next full historical backfill cycle.
        """
        cache_path = self.source_cache.root / (
            "universe-v3.json"
            if getattr(self.universe_provider, "coin_m_transport", None)
            else "universe-v2.json"
        )
        if not force_refresh:
            cached = read_cached_market_universe(cache_path, observed_at)
            if cached is not None:
                return cached
        top_volume_snapshot = getattr(
            self.universe_provider, "top_volume_eligible_market_snapshot", None
        )
        snapshot = (
            top_volume_snapshot(
                max_symbols_per_market=_COLLECTION_MAX_SYMBOLS_PER_MARKET
            )
            if callable(top_volume_snapshot)
            else self.universe_provider.eligible_market_snapshot()
        )
        if snapshot.blockers:
            cached = read_cached_market_universe(cache_path, observed_at)
            if cached is not None:
                return cached
            return snapshot
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "observed_at": observed_at.isoformat(),
                    "spot_symbols": snapshot.spot_symbols,
                    "futures_symbols": snapshot.futures_symbols,
                    "coin_m_contracts": snapshot.coin_m_contracts,
                    "excluded_assets": snapshot.excluded_assets,
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, cache_path)
        return snapshot

    def _sync_spot(
        self,
        symbol: str,
        target_day: date,
        observed_at: datetime,
    ) -> MarketHistorySymbolResult:
        try:
            sources: list[VerifiedCachedArchive] = []
            manifests: list[DatasetManifest] = []
            for timeframe in MARKET_HISTORY_TIMEFRAMES:
                key = _daily_kline_key("spot", symbol, "klines", timeframe, target_day)
                source, payload = self.source_cache.verified(key, kind="ohlcv")
                sources.append(source)
                candles = _parse_kline_archive(key, payload, target_day, timeframe)
                manifests.append(
                    self._materialize_timeframe(
                        "spot", symbol, timeframe, candles, observed_at, source.sha256
                    )
                )
            receipt_path = self._write_symbol_receipt(
                "spot",
                symbol,
                target_day,
                observed_at,
                tuple(manifests),
                tuple(sources),
            )
            return MarketHistorySymbolResult(
                market="SPOT",
                symbol=symbol,
                status="SYNCED",
                manifests=tuple(manifests),
                detail_sources=tuple(sources),
                receipt_path=str(receipt_path),
            )
        except MarketHistorySourceUnavailableError:
            return MarketHistorySymbolResult(
                market="SPOT",
                symbol=symbol,
                status="DEFERRED",
                blocker="SPOT_DAILY_SOURCE_NOT_PUBLISHED",
            )
        except (HTTPError, OSError, ValueError, zipfile.BadZipFile):
            return MarketHistorySymbolResult(
                market="SPOT",
                symbol=symbol,
                status="BLOCKED",
                blocker="SPOT_HISTORY_SYNC_FAILED",
            )

    def _sync_futures(
        self,
        symbol: str,
        target_day: date,
        observed_at: datetime,
    ) -> MarketHistorySymbolResult:
        sources: list[VerifiedCachedArchive] = []
        manifests: list[DatasetManifest] = []
        try:
            for timeframe in MARKET_HISTORY_TIMEFRAMES:
                ohlcv_key = _daily_kline_key(
                    "um", symbol, "klines", timeframe, target_day
                )
                ohlcv_source, ohlcv_payload = self.source_cache.verified(
                    ohlcv_key, kind="ohlcv"
                )
                sources.append(ohlcv_source)
                candles = _parse_kline_archive(
                    ohlcv_key, ohlcv_payload, target_day, timeframe
                )
                manifests.append(
                    self._materialize_timeframe(
                        "usd_m_futures",
                        symbol,
                        timeframe,
                        candles,
                        observed_at,
                        ohlcv_source.sha256,
                    )
                )

            mark_key = _daily_kline_key(
                "um", symbol, "markPriceKlines", "5m", target_day
            )
            mark_source, mark_payload = self.source_cache.verified(
                mark_key, kind="mark_price"
            )
            sources.append(mark_source)
            mark_candles = _parse_kline_archive(
                mark_key, mark_payload, target_day, "5m"
            )
            manifests.append(
                self._materialize_timeframe(
                    "usd_m_futures_mark",
                    symbol,
                    "5m",
                    mark_candles,
                    observed_at,
                    mark_source.sha256,
                )
            )

            metrics_key = (
                f"data/futures/um/daily/metrics/{symbol}/"
                f"{symbol}-metrics-{target_day.isoformat()}.zip"
            )
            metrics_source, metrics_payload = self.source_cache.verified(
                metrics_key, kind="open_interest_and_positioning"
            )
            _validate_csv_archive(metrics_key, metrics_payload)
            sources.append(metrics_source)

            funding_month = (target_day.replace(day=1) - timedelta(days=1)).strftime(
                "%Y-%m"
            )
            funding_key = (
                f"data/futures/um/monthly/fundingRate/{symbol}/"
                f"{symbol}-fundingRate-{funding_month}.zip"
            )
            funding_source, funding_payload = self.source_cache.verified(
                funding_key, kind="funding_rate"
            )
            _validate_csv_archive(funding_key, funding_payload)
            sources.append(funding_source)
            receipt_path = self._write_symbol_receipt(
                "usd_m_futures",
                symbol,
                target_day,
                observed_at,
                tuple(manifests),
                tuple(sources),
            )
            return MarketHistorySymbolResult(
                market="USD_M_FUTURES",
                symbol=symbol,
                status="SYNCED",
                manifests=tuple(manifests),
                detail_sources=tuple(sources),
                receipt_path=str(receipt_path),
            )
        except MarketHistorySourceUnavailableError:
            return MarketHistorySymbolResult(
                market="USD_M_FUTURES",
                symbol=symbol,
                status="DEFERRED",
                manifests=tuple(manifests),
                detail_sources=tuple(sources),
                blocker="FUTURES_DETAIL_SOURCE_NOT_PUBLISHED",
            )
        except (HTTPError, OSError, ValueError, zipfile.BadZipFile):
            return MarketHistorySymbolResult(
                market="USD_M_FUTURES",
                symbol=symbol,
                status="BLOCKED",
                manifests=tuple(manifests),
                detail_sources=tuple(sources),
                blocker="FUTURES_HISTORY_SYNC_FAILED",
            )

    def _materialize_timeframe(
        self,
        market_directory: str,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        observed_at: datetime,
        source_sha256: str,
    ) -> DatasetManifest:
        archive = ParquetOHLCVArchive(self.archive_root / market_directory)
        return archive.update(
            symbol,
            timeframe,
            candles,
            source=f"BINANCE_VISION_{timeframe.upper()}_SHA256:{source_sha256}",
            generated_at=observed_at,
        )

    def _write_symbol_receipt(
        self,
        market_directory: str,
        symbol: str,
        target_day: date,
        observed_at: datetime,
        manifests: tuple[DatasetManifest, ...],
        sources: tuple[VerifiedCachedArchive, ...],
    ) -> Path:
        path = (
            self.archive_root
            / market_directory
            / symbol
            / "sources"
            / f"{target_day.isoformat()}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "market": market_directory.upper(),
            "symbol": symbol,
            "target_day": target_day.isoformat(),
            "observed_at": observed_at.isoformat(),
            "base_cadence": "DIRECT_NATIVE_TIMEFRAMES",
            "timeframes": MARKET_HISTORY_TIMEFRAMES,
            "dataset_manifests": tuple(asdict(manifest) for manifest in manifests),
            "source_files": tuple(asdict(source) for source in sources),
            "wallet_data_included": False,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return path

    def _write_report(self, report: MarketHistorySyncReport) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(report)
        payload["downloaded_bytes"] = report.downloaded_bytes
        payload["network_request_count"] = report.network_request_count
        payload["synced_count"] = sum(
            result.status == "SYNCED" for result in report.results
        )
        payload["deferred_count"] = sum(
            result.status == "DEFERRED" for result in report.results
        )
        payload["blocked_count"] = sum(
            result.status == "BLOCKED" for result in report.results
        )
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)


@dataclass(frozen=True, slots=True)
class MarketHistorySupervisor:
    """Resident bounded loop for the latest closed UTC day."""

    synchronizer: MarketHistorySynchronizer
    interval_seconds: float
    lock_path: Path
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)
    cycle: Callable[[datetime], object] | None = field(default=None, repr=False)
    on_recoverable_error: Callable[[datetime, Exception], None] | None = field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not 60 <= self.interval_seconds <= 86_400:
            raise ValueError("market history interval must be between 60 and 86400")
        if not self.lock_path.is_absolute():
            raise ValueError("market history lock path must be absolute")

    def run(self, *, max_cycles: int | None = None) -> int:
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        attempts = 0
        completed = 0
        with SingleInstanceLease(self.lock_path):
            while max_cycles is None or attempts < max_cycles:
                started = time.monotonic()
                now = self.clock()
                attempts += 1
                fast_retry = False
                try:
                    if self.cycle is None:
                        result = self.synchronizer.sync_day(
                            now.date() - timedelta(days=1), observed_at=now
                        )
                    else:
                        result = self.cycle(now)
                except (OSError, ValueError, ArithmeticError, ExchangeError) as error:
                    fast_retry = True
                    if self.on_recoverable_error is not None:
                        self.on_recoverable_error(now, error)
                else:
                    completed += 1
                    fast_retry = _requires_fast_retry(result)
                if max_cycles is None or attempts < max_cycles:
                    delay = self.interval_seconds
                    if self.cycle is not None:
                        delay = max(1, delay - (time.monotonic() - started))
                    if fast_retry:
                        delay = min(delay, 30)
                    self.sleeper(delay)
        return completed


def _requires_fast_retry(result: object) -> bool:
    blockers = (
        result.get("blockers", ())
        if isinstance(result, Mapping)
        else getattr(result, "blockers", ())
    )
    return isinstance(blockers, (list, tuple)) and bool(
        _FAST_RETRY_BLOCKERS.intersection(
            item for item in blockers if isinstance(item, str)
        )
    )


def _daily_kline_key(
    market: str,
    symbol: str,
    kind: str,
    timeframe: str,
    target_day: date,
) -> str:
    market_root = {"spot": "spot", "um": "futures/um", "cm": "futures/cm"}[market]
    return (
        f"data/{market_root}/daily/{kind}/{symbol}/{timeframe}/"
        f"{symbol}-{timeframe}-{target_day.isoformat()}.zip"
    )


def _parse_kline_archive(
    key: str,
    payload: bytes,
    target_day: date,
    timeframe: str,
) -> tuple[OHLCVCandle, ...]:
    rows = _csv_rows(key, payload)
    if rows and not rows[0][0].strip().isdigit():
        rows = rows[1:]
    candles: list[OHLCVCandle] = []
    for row in rows:
        if len(row) < 6:
            raise MarketHistoryIntegrityError(f"kline row is incomplete: {key}")
        try:
            raw_timestamp = int(row[0])
            divisor = 1_000_000 if raw_timestamp >= 100_000_000_000_000 else 1_000
            candle = OHLCVCandle(
                timestamp=datetime.fromtimestamp(raw_timestamp / divisor, tz=UTC),
                open=Decimal(row[1]),
                high=Decimal(row[2]),
                low=Decimal(row[3]),
                close=Decimal(row[4]),
                volume=Decimal(row[5]),
            )
        except (ArithmeticError, OSError, ValueError):
            raise MarketHistoryIntegrityError(
                f"kline row contains invalid values: {key}"
            ) from None
        candles.append(candle)
    cadence = timeframe_duration(timeframe)
    maximum_rows = int(timedelta(days=1) / cadence)
    if not candles or len(candles) > maximum_rows:
        raise MarketHistoryIntegrityError(f"kline row count is invalid: {key}")
    day_start = datetime.combine(target_day, datetime_time(), tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    if any(
        candle.timestamp.second != 0
        or candle.timestamp.microsecond != 0
        or not day_start <= candle.timestamp < day_end
        for candle in candles
    ):
        raise MarketHistoryIntegrityError(f"kline timestamp is invalid: {key}")
    if any(
        following.timestamp - current.timestamp != cadence
        for current, following in pairwise(candles)
    ):
        raise MarketHistoryIntegrityError(f"kline cadence is not contiguous: {key}")
    return tuple(candles)


def _validate_csv_archive(key: str, payload: bytes) -> None:
    if not _csv_rows(key, payload):
        raise MarketHistoryIntegrityError(f"CSV archive is empty: {key}")


def _csv_rows(key: str, payload: bytes) -> list[list[str]]:
    if not payload or len(payload) > _MAX_ARCHIVE_BYTES:
        raise MarketHistoryIntegrityError(f"archive size is invalid: {key}")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise MarketHistoryIntegrityError(
                    f"archive must contain exactly one CSV: {key}"
                )
            member = members[0]
            if (
                not member.filename.endswith(".csv")
                or "/" in member.filename
                or "\\" in member.filename
                or member.file_size > _MAX_UNCOMPRESSED_BYTES
            ):
                raise MarketHistoryIntegrityError(f"archive member is unsafe: {key}")
            with archive.open(member) as stream:
                text = io.TextIOWrapper(stream, encoding="utf-8", newline="")
                return list(csv.reader(text))
    except (UnicodeError, csv.Error, zipfile.BadZipFile):
        raise MarketHistoryIntegrityError(
            f"invalid ZIP or CSV archive: {key}"
        ) from None


__all__ = (
    "MARKET_HISTORY_TIMEFRAMES",
    "BinanceVisionArchiveCache",
    "MarketHistoryIntegrityError",
    "MarketHistorySourceUnavailableError",
    "MarketHistorySupervisor",
    "MarketHistorySymbolResult",
    "MarketHistorySyncReport",
    "MarketHistorySynchronizer",
    "VerifiedCachedArchive",
)
