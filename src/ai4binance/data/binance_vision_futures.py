"""Checksum-bound Binance Vision USD-M Futures replay ingestion."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, cast

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.schemas import OHLCVCandle
from ai4binance.validation.futures_replay import (
    RUNTIME_FUTURES_REPLAY_TIMEFRAME,
    RUNTIME_FUTURES_REPLAY_TIMEFRAMES,
    RuntimeFuturesReplayDataset,
)
from ai4binance.whale_fusion.derivatives import (
    BinanceUsdMClient,
    UsdMFuturesPublicTransport,
)
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

FetchBytes = Callable[[str], bytes]


_BASE_URL: Final = "https://data.binance.vision"
_ALLOWED_HOSTS: Final = frozenset(
    {"data.binance.vision", "s3-ap-northeast-1.amazonaws.com"}
)
_SOURCE_ID: Final = "BINANCE_VISION_CHECKSUM_VERIFIED"
_MAX_ARCHIVE_BYTES: Final = 128 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES: Final = 256 * 1024 * 1024
_MAX_RECORDS: Final = 1_000_000
_SYMBOL_PATTERN: Final = re.compile(r"^[A-Z0-9]{2,24}$")

_KLINE_FIELDS: Final = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)
_METRICS_FIELDS: Final = (
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
_FUNDING_FIELDS: Final = (
    "calc_time",
    "funding_interval_hours",
    "last_funding_rate",
)


class BinanceVisionFuturesIntegrityError(ValueError):
    """Raised when public Futures history cannot satisfy the replay contract."""


@dataclass(frozen=True, slots=True)
class VerifiedFuturesSourceFile:
    """One upstream archive bound to its published Binance Vision checksum."""

    kind: str
    key: str
    url: str
    sha256: str
    byte_count: int
    record_count: int


@dataclass(frozen=True, slots=True)
class BinanceVisionFuturesSyncResult:
    """One locally materialized, research-only Futures replay artifact."""

    dataset: RuntimeFuturesReplayDataset
    source_files: tuple[VerifiedFuturesSourceFile, ...]
    artifact_path: str
    artifact_sha256: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"


@dataclass(frozen=True, slots=True)
class BinanceVisionFuturesReplayIngestor:
    """Build an exact multi-timeframe USD-M replay from public archive evidence."""

    artifact_root: Path
    fetch: FetchBytes
    timeframe: str = RUNTIME_FUTURES_REPLAY_TIMEFRAME
    source_cache: Any | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    derivatives_client: BinanceUsdMClient | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.timeframe not in RUNTIME_FUTURES_REPLAY_TIMEFRAMES:
            raise ValueError("Futures replay timeframe is unsupported")
        object.__setattr__(self, "artifact_root", self.artifact_root.resolve())

    @classmethod
    def with_network(
        cls,
        artifact_root: Path,
        *,
        timeframe: str = RUNTIME_FUTURES_REPLAY_TIMEFRAME,
        timeout_seconds: float = 30.0,
        maximum_response_bytes: int = _MAX_ARCHIVE_BYTES,
    ) -> BinanceVisionFuturesReplayIngestor:
        """Create an ingestor restricted to Binance Vision HTTPS hosts."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1_024 <= maximum_response_bytes <= _MAX_ARCHIVE_BYTES:
            raise ValueError("maximum_response_bytes is outside the safe range")

        def fetch(url: str) -> bytes:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
                raise ValueError("Binance Vision URL is outside the allowlist")
            request = urllib.request.Request(  # noqa: S310 - allowlisted HTTPS.
                url,
                headers={"User-Agent": "ai4binance-research/0.1"},
            )
            with urllib.request.urlopen(  # noqa: S310  # nosec B310
                request,
                timeout=timeout_seconds,
            ) as response:
                payload = cast(bytes, response.read(maximum_response_bytes + 1))
            if len(payload) > maximum_response_bytes:
                raise BinanceVisionFuturesIntegrityError(
                    "Binance Vision response exceeds the configured size limit"
                )
            return payload

        return cls(
            artifact_root,
            fetch,
            timeframe=timeframe,
            derivatives_client=BinanceUsdMClient(
                UsdMFuturesPublicTransport(timeout_seconds=timeout_seconds)
            ),
        )

    @classmethod
    def with_persistent_cache(
        cls,
        artifact_root: Path,
        source_cache_root: Path,
        *,
        timeframe: str = RUNTIME_FUTURES_REPLAY_TIMEFRAME,
        timeout_seconds: float = 30.0,
    ) -> BinanceVisionFuturesReplayIngestor:
        """Reuse the canonical checksum-verified market-history source cache."""

        from ai4binance.data.market_history_sync import BinanceVisionArchiveCache

        cache = BinanceVisionArchiveCache.with_network(
            source_cache_root,
            timeout_seconds=timeout_seconds,
        )
        return cls(
            artifact_root,
            cache.fetch,
            timeframe=timeframe,
            source_cache=cache,
            derivatives_client=BinanceUsdMClient(
                UsdMFuturesPublicTransport(timeout_seconds=timeout_seconds)
            ),
        )

    def sync_day(
        self,
        symbol: str,
        replay_day: date,
        *,
        observed_at: datetime,
    ) -> BinanceVisionFuturesSyncResult:
        """Verify, align, and persist one complete UTC replay day."""

        normalized, normalized_observation = self._validate_request(
            symbol,
            replay_day,
            observed_at,
        )
        derivatives = self._replay_derivatives(
            normalized,
            replay_day,
            replay_day,
            normalized_observation,
        )
        dataset, source_files = self._load_day(
            normalized,
            replay_day,
            normalized_observation,
            {},
            derivatives,
        )
        artifact_path, artifact_sha256 = self._write_artifact(
            dataset,
            replay_day.isoformat(),
        )
        return BinanceVisionFuturesSyncResult(
            dataset=dataset,
            source_files=source_files,
            artifact_path=str(artifact_path),
            artifact_sha256=artifact_sha256,
        )

    def sync_range(
        self,
        symbol: str,
        start_day: date,
        end_day: date,
        *,
        observed_at: datetime,
    ) -> BinanceVisionFuturesSyncResult:
        """Persist one contiguous multi-day replay with deduplicated sources."""

        if end_day < start_day or (end_day - start_day).days >= 366:
            raise ValueError("Futures replay range must contain 1 to 366 days")
        normalized, normalized_observation = self._validate_request(
            symbol,
            end_day,
            observed_at,
        )
        cache: dict[
            str,
            tuple[VerifiedFuturesSourceFile, tuple[dict[str, str], ...]],
        ] = {}
        derivatives = self._replay_derivatives(
            normalized,
            start_day,
            end_day,
            normalized_observation,
        )
        datasets: list[RuntimeFuturesReplayDataset] = []
        sources: list[VerifiedFuturesSourceFile] = []
        current = start_day
        while current <= end_day:
            dataset, day_sources = self._load_day(
                normalized,
                current,
                normalized_observation,
                cache,
                derivatives,
            )
            datasets.append(dataset)
            sources.extend(day_sources)
            current += timedelta(days=1)
        metrics = tuple(datasets[0].derivatives.series)
        if any(tuple(dataset.derivatives.series) != metrics for dataset in datasets):
            raise BinanceVisionFuturesIntegrityError(
                "Futures replay days have inconsistent metric coverage"
            )
        merged = RuntimeFuturesReplayDataset(
            symbol=normalized,
            candles=tuple(candle for dataset in datasets for candle in dataset.candles),
            derivatives=DerivativesDataset(
                symbol=normalized,
                as_of=normalized_observation,
                source=datasets[0].derivatives.source,
                series={
                    metric: tuple(
                        point
                        for dataset in datasets
                        for point in dataset.derivatives.series[metric]
                    )
                    for metric in metrics
                },
            ),
            timeframe=self.timeframe,
        )
        unique_sources = tuple({source.key: source for source in sources}.values())
        label = f"{start_day.isoformat()}_to_{end_day.isoformat()}"
        artifact_path, artifact_sha256 = self._write_artifact(merged, label)
        return BinanceVisionFuturesSyncResult(
            dataset=merged,
            source_files=unique_sources,
            artifact_path=str(artifact_path),
            artifact_sha256=artifact_sha256,
        )

    @staticmethod
    def _validate_request(
        symbol: str,
        latest_day: date,
        observed_at: datetime,
    ) -> tuple[str, datetime]:
        normalized = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Futures replay symbol must be ASCII alphanumeric")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        normalized_observation = observed_at.astimezone(UTC)
        day_end = datetime.combine(latest_day + timedelta(days=1), time(), tzinfo=UTC)
        if normalized_observation < day_end:
            raise ValueError("Futures replay day must be fully observable")
        return normalized, normalized_observation

    def _load_day(
        self,
        symbol: str,
        replay_day: date,
        observed_at: datetime,
        cache: dict[
            str,
            tuple[VerifiedFuturesSourceFile, tuple[dict[str, str], ...]],
        ],
        derivatives: DerivativesDataset | None,
    ) -> tuple[RuntimeFuturesReplayDataset, tuple[VerifiedFuturesSourceFile, ...]]:
        keys = self._source_keys(symbol, replay_day)
        if derivatives is not None:
            keys = {"ohlcv": keys["ohlcv"]}
        sources: dict[str, VerifiedFuturesSourceFile] = {}
        rows: dict[str, tuple[dict[str, str], ...]] = {}
        expected_fields = {
            "ohlcv": _KLINE_FIELDS,
            "mark_price": _KLINE_FIELDS,
            "open_interest": _METRICS_FIELDS,
            "funding_rate": _FUNDING_FIELDS,
        }
        for kind, key in keys.items():
            verified = cache.get(key)
            if verified is None:
                verified = self._verified_rows(
                    kind,
                    key,
                    expected_fields[kind],
                )
                cache[key] = verified
            source, parsed = verified
            sources[kind] = source
            rows[kind] = parsed

        dataset = self._build_dataset(
            symbol,
            replay_day,
            observed_at,
            sources,
            rows,
            self.timeframe,
            derivatives,
        )
        return dataset, tuple(sources[kind] for kind in keys)

    def _replay_derivatives(
        self,
        symbol: str,
        start_day: date,
        end_day: date,
        observed_at: datetime,
    ) -> DerivativesDataset | None:
        """Get exact official REST derivatives; never synthesize archive gaps."""

        if self.derivatives_client is None:
            return None
        start = datetime.combine(start_day, time(), tzinfo=UTC)
        end = datetime.combine(end_day + timedelta(days=1), time(), tzinfo=UTC)
        return self.derivatives_client.replay_history(
            symbol,
            self.timeframe,
            start,
            end,
            observed_at=observed_at,
        )

    def _source_keys(self, symbol: str, replay_day: date) -> dict[str, str]:
        day = replay_day.isoformat()
        month = replay_day.strftime("%Y-%m")
        return {
            "ohlcv": (
                f"data/futures/um/daily/klines/{symbol}/{self.timeframe}/"
                f"{symbol}-{self.timeframe}-{day}.zip"
            ),
            "mark_price": (
                f"data/futures/um/daily/markPriceKlines/{symbol}/{self.timeframe}/"
                f"{symbol}-{self.timeframe}-{day}.zip"
            ),
            "open_interest": (
                f"data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{day}.zip"
            ),
            "funding_rate": (
                f"data/futures/um/monthly/fundingRate/{symbol}/"
                f"{symbol}-fundingRate-{month}.zip"
            ),
        }

    def _verified_rows(
        self,
        kind: str,
        key: str,
        expected_fields: tuple[str, ...],
    ) -> tuple[VerifiedFuturesSourceFile, tuple[dict[str, str], ...]]:
        encoded_key = urllib.parse.quote(key, safe="/")
        url = f"{_BASE_URL}/{encoded_key}"
        if self.source_cache is not None:
            cached, payload = self.source_cache.verified(key, kind=kind)
            actual = cached.sha256
        else:
            payload = self.fetch(url)
            published = self.fetch(f"{url}.CHECKSUM")
            try:
                expected = published.decode("ascii").strip().split()[0].lower()
            except (UnicodeError, IndexError):
                expected = ""
            actual = sha256(payload).hexdigest()
            if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
                raise BinanceVisionFuturesIntegrityError(f"checksum mismatch: {key}")
        parsed = self._parse_csv_archive(key, payload, expected_fields)
        return (
            VerifiedFuturesSourceFile(
                kind=kind,
                key=key,
                url=url,
                sha256=actual,
                byte_count=len(payload),
                record_count=len(parsed),
            ),
            parsed,
        )

    @staticmethod
    def _parse_csv_archive(
        key: str,
        payload: bytes,
        expected_fields: tuple[str, ...],
    ) -> tuple[dict[str, str], ...]:
        if not payload or len(payload) > _MAX_ARCHIVE_BYTES:
            raise BinanceVisionFuturesIntegrityError(
                f"archive size is outside the safe range: {key}"
            )
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = archive.infolist()
                if len(members) != 1:
                    raise BinanceVisionFuturesIntegrityError(
                        f"archive must contain exactly one CSV: {key}"
                    )
                member = members[0]
                if (
                    not member.filename.endswith(".csv")
                    or "/" in member.filename
                    or "\\" in member.filename
                    or member.file_size > _MAX_UNCOMPRESSED_BYTES
                ):
                    raise BinanceVisionFuturesIntegrityError(
                        f"archive member is unsafe: {key}"
                    )
                with archive.open(member) as stream:
                    text = io.TextIOWrapper(stream, encoding="utf-8", newline="")
                    reader = csv.DictReader(text)
                    if tuple(reader.fieldnames or ()) != expected_fields:
                        raise BinanceVisionFuturesIntegrityError(
                            f"archive CSV schema is invalid: {key}"
                        )
                    rows = tuple(dict(row) for row in reader)
        except (zipfile.BadZipFile, UnicodeError, csv.Error):
            raise BinanceVisionFuturesIntegrityError(
                f"invalid ZIP or CSV archive: {key}"
            ) from None
        if not rows or len(rows) > _MAX_RECORDS:
            raise BinanceVisionFuturesIntegrityError(
                f"archive record count is outside the safe range: {key}"
            )
        return rows

    @classmethod
    def _build_dataset(
        cls,
        symbol: str,
        replay_day: date,
        observed_at: datetime,
        sources: Mapping[str, VerifiedFuturesSourceFile],
        rows: Mapping[str, tuple[dict[str, str], ...]],
        timeframe: str = RUNTIME_FUTURES_REPLAY_TIMEFRAME,
        derivatives: DerivativesDataset | None = None,
    ) -> RuntimeFuturesReplayDataset:
        day_start = datetime.combine(replay_day, time(), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        duration = timeframe_duration(timeframe)
        candles = tuple(cls._candle(row, duration) for row in rows["ohlcv"])
        if (
            candles[0].timestamp != day_start
            or candles[-1].timestamp + duration != day_end
            or any(
                following.timestamp - current.timestamp != duration
                for current, following in pairwise(candles)
            )
        ):
            raise BinanceVisionFuturesIntegrityError(
                "Futures OHLCV does not cover one contiguous UTC day"
            )
        candle_timestamps = tuple(candle.timestamp for candle in candles)
        candle_timestamp_set = set(candle_timestamps)
        common_attributes = {
            f"{kind}_source_sha256": source.sha256
            for kind, source in sorted(sources.items())
        }
        common_attributes["alignment"] = f"CLOSED_{timeframe.upper()}_POINT_IN_TIME"

        if derivatives is not None:
            return cls._build_rest_dataset(
                symbol,
                replay_day,
                observed_at,
                timeframe,
                candles,
                derivatives,
                common_attributes,
            )

        mark_rows = rows["mark_price"]
        cls._require_kline_close_alignment(mark_rows, "mark-price", duration)
        mark_timestamps = tuple(
            cls._milliseconds(row["open_time"]) for row in mark_rows
        )
        if mark_timestamps != candle_timestamps:
            raise BinanceVisionFuturesIntegrityError(
                "Futures mark-price timestamps do not align with OHLCV"
            )
        marks = tuple(
            cls._point(
                DerivativesMetric.MARK_PRICE,
                timestamp,
                row["close"],
                sources["mark_price"],
                observed_at,
                {
                    **common_attributes,
                    "mark_open": row["open"],
                    "mark_high": row["high"],
                    "mark_low": row["low"],
                },
            )
            for timestamp, row in zip(mark_timestamps, mark_rows, strict=True)
        )

        aligned_metrics = tuple(
            row
            for row in rows["open_interest"]
            if cls._metrics_timestamp(row["create_time"]) in candle_timestamp_set
        )
        if any(row["symbol"].strip().upper() != symbol for row in aligned_metrics):
            raise BinanceVisionFuturesIntegrityError(
                "Futures open-interest symbol lineage is inconsistent"
            )
        oi_timestamps = tuple(
            cls._metrics_timestamp(row["create_time"]) for row in aligned_metrics
        )
        if oi_timestamps != candle_timestamps:
            raise BinanceVisionFuturesIntegrityError(
                "Futures open-interest timestamps do not align with OHLCV"
            )
        open_interest = tuple(
            cls._point(
                DerivativesMetric.OPEN_INTEREST,
                timestamp,
                row["sum_open_interest"],
                sources["open_interest"],
                observed_at,
                common_attributes,
            )
            for timestamp, row in zip(oi_timestamps, aligned_metrics, strict=True)
        )
        open_interest_value = tuple(
            cls._point(
                DerivativesMetric.OPEN_INTEREST_VALUE,
                timestamp,
                row["sum_open_interest_value"],
                sources["open_interest"],
                observed_at,
                common_attributes,
            )
            for timestamp, row in zip(oi_timestamps, aligned_metrics, strict=True)
        )

        funding_rows = tuple(
            row
            for row in rows["funding_rate"]
            if day_start <= cls._funding_timestamp(row["calc_time"]) < day_end
        )
        funding = tuple(
            cls._point(
                DerivativesMetric.FUNDING_RATE,
                cls._funding_timestamp(row["calc_time"]),
                row["last_funding_rate"],
                sources["funding_rate"],
                observed_at,
                {
                    **common_attributes,
                    "funding_interval_hours": row["funding_interval_hours"],
                    "raw_calc_time": row["calc_time"],
                },
            )
            for row in funding_rows
        )
        if not funding or funding[0].timestamp != day_start:
            raise BinanceVisionFuturesIntegrityError(
                "Futures funding history is incomplete at replay start"
            )

        return RuntimeFuturesReplayDataset(
            symbol=symbol,
            candles=candles,
            derivatives=DerivativesDataset(
                symbol=symbol,
                as_of=observed_at,
                source=_SOURCE_ID,
                series={
                    DerivativesMetric.MARK_PRICE: marks,
                    DerivativesMetric.OPEN_INTEREST: open_interest,
                    DerivativesMetric.OPEN_INTEREST_VALUE: open_interest_value,
                    DerivativesMetric.FUNDING_RATE: funding,
                },
            ),
            timeframe=timeframe,
        )

    @classmethod
    def _build_rest_dataset(
        cls,
        symbol: str,
        replay_day: date,
        observed_at: datetime,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        derivatives: DerivativesDataset,
        attributes: Mapping[str, str],
    ) -> RuntimeFuturesReplayDataset:
        """Admit only public REST points that exactly match closed candle starts."""

        if (
            derivatives.symbol != symbol
            or derivatives.source != "BINANCE_USD_M_PUBLIC_REST"
        ):
            raise BinanceVisionFuturesIntegrityError(
                "Futures public REST derivatives have inconsistent lineage"
            )
        day_start = datetime.combine(replay_day, time(), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        candle_timestamps = tuple(candle.timestamp for candle in candles)

        def points_for(metric: DerivativesMetric) -> tuple[MetricPoint, ...]:
            return tuple(
                point
                for point in derivatives.series.get(metric, ())
                if day_start <= point.timestamp < day_end
            )

        def exact(metric: DerivativesMetric) -> tuple[MetricPoint, ...]:
            points = points_for(metric)
            if tuple(point.timestamp for point in points) != candle_timestamps:
                raise BinanceVisionFuturesIntegrityError(
                    "Futures public REST "
                    f"{metric.value} does not align exactly with OHLCV"
                )
            if any(point.value <= Decimal("0") for point in points):
                raise BinanceVisionFuturesIntegrityError(
                    f"Futures public REST {metric.value} contains a non-positive value"
                )
            return tuple(
                MetricPoint(
                    metric=point.metric,
                    timestamp=point.timestamp,
                    value=point.value,
                    provenance=point.provenance,
                    attributes={
                        **point.attributes,
                        **attributes,
                        "alignment": f"CLOSED_{timeframe.upper()}_EXACT_PUBLIC_REST",
                    },
                )
                for point in points
            )

        mark_price = exact(DerivativesMetric.MARK_PRICE)
        open_interest = exact(DerivativesMetric.OPEN_INTEREST)
        open_interest_value = exact(DerivativesMetric.OPEN_INTEREST_VALUE)
        funding = points_for(DerivativesMetric.FUNDING_RATE)
        if not funding:
            raise BinanceVisionFuturesIntegrityError(
                "Futures public REST funding history is unavailable for replay day"
            )
        return RuntimeFuturesReplayDataset(
            symbol=symbol,
            candles=candles,
            derivatives=DerivativesDataset(
                symbol=symbol,
                as_of=observed_at,
                source="BINANCE_USD_M_PUBLIC_REST",
                series={
                    DerivativesMetric.MARK_PRICE: mark_price,
                    DerivativesMetric.OPEN_INTEREST: open_interest,
                    DerivativesMetric.OPEN_INTEREST_VALUE: open_interest_value,
                    DerivativesMetric.FUNDING_RATE: funding,
                },
            ),
            timeframe=timeframe,
        )

    @staticmethod
    def _candle(row: Mapping[str, str], duration: timedelta) -> OHLCVCandle:
        try:
            open_timestamp = BinanceVisionFuturesReplayIngestor._milliseconds(
                row["open_time"]
            )
            close_timestamp = BinanceVisionFuturesReplayIngestor._milliseconds(
                row["close_time"]
            )
            if close_timestamp != open_timestamp + duration - timedelta(milliseconds=1):
                raise ValueError
            return OHLCVCandle(
                timestamp=open_timestamp,
                open=BinanceVisionFuturesReplayIngestor._decimal(row["open"]),
                high=BinanceVisionFuturesReplayIngestor._decimal(row["high"]),
                low=BinanceVisionFuturesReplayIngestor._decimal(row["low"]),
                close=BinanceVisionFuturesReplayIngestor._decimal(row["close"]),
                volume=BinanceVisionFuturesReplayIngestor._decimal(row["volume"]),
            )
        except (KeyError, ValueError):
            raise BinanceVisionFuturesIntegrityError(
                "Futures OHLCV row contains invalid values"
            ) from None

    @classmethod
    def _require_kline_close_alignment(
        cls,
        rows: tuple[dict[str, str], ...],
        label: str,
        duration: timedelta = timedelta(hours=1),
    ) -> None:
        try:
            aligned = all(
                cls._milliseconds(row["close_time"])
                == cls._milliseconds(row["open_time"])
                + duration
                - timedelta(milliseconds=1)
                for row in rows
            )
        except KeyError:
            aligned = False
        if not aligned:
            raise BinanceVisionFuturesIntegrityError(
                f"Futures {label} close-time alignment is invalid"
            )

    @staticmethod
    def _point(
        metric: DerivativesMetric,
        timestamp: datetime,
        value: str,
        source: VerifiedFuturesSourceFile,
        observed_at: datetime,
        attributes: Mapping[str, str],
    ) -> MetricPoint:
        parsed = BinanceVisionFuturesReplayIngestor._decimal(value)
        return MetricPoint(
            metric=metric,
            timestamp=timestamp,
            value=parsed,
            provenance=Provenance(
                source_id=_SOURCE_ID,
                source_url=source.url,
                observed_at=observed_at,
            ),
            attributes=attributes,
        )

    @staticmethod
    def _milliseconds(raw: str) -> datetime:
        try:
            value = int(raw)
            divisor = 1_000_000 if value >= 100_000_000_000_000 else 1_000
            return datetime.fromtimestamp(value / divisor, tz=UTC)
        except (ValueError, ArithmeticError, OSError):
            raise BinanceVisionFuturesIntegrityError(
                "Futures timestamp is invalid"
            ) from None

    @staticmethod
    def _metrics_timestamp(raw: str) -> datetime:
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            raise BinanceVisionFuturesIntegrityError(
                "Futures metrics timestamp is invalid"
            ) from None

    @classmethod
    def _funding_timestamp(cls, raw: str) -> datetime:
        """Align documented funding boundaries while preserving raw evidence."""

        timestamp = cls._milliseconds(raw)
        boundary = timestamp.replace(microsecond=0)
        if (
            boundary.minute != 0
            or boundary.second != 0
            or not timedelta(0) <= timestamp - boundary < timedelta(seconds=1)
        ):
            raise BinanceVisionFuturesIntegrityError(
                "Futures funding timestamp is outside the hourly boundary tolerance"
            )
        return boundary

    @staticmethod
    def _decimal(raw: str) -> Decimal:
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise BinanceVisionFuturesIntegrityError(
                "Futures decimal value is invalid"
            ) from None
        if not value.is_finite():
            raise BinanceVisionFuturesIntegrityError(
                "Futures decimal value must be finite"
            )
        return value

    def _write_artifact(
        self,
        dataset: RuntimeFuturesReplayDataset,
        coverage_label: str,
    ) -> tuple[Path, str]:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        path = self.artifact_root / (
            f"{dataset.symbol}-{dataset.timeframe}-{coverage_label}.json"
        )
        encoded = (
            json.dumps(
                dataset.to_artifact_payload(),
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        temporary = path.with_suffix(".json.tmp")
        temporary.write_bytes(encoded)
        temporary.replace(path)
        return path, sha256(encoded).hexdigest()


__all__ = (
    "BinanceVisionFuturesIntegrityError",
    "BinanceVisionFuturesReplayIngestor",
    "BinanceVisionFuturesSyncResult",
    "VerifiedFuturesSourceFile",
)
