"""Checksum-verified Binance Vision Spot kline ingestion."""

import csv
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast

from ai4binance.data.archive import DatasetManifest, ParquetOHLCVArchive
from ai4binance.schemas import OHLCVCandle

FetchBytes = Callable[[str], bytes]
_BASE_URL = "https://data.binance.vision"
_LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
_ALLOWED_HOSTS = frozenset({"data.binance.vision", "s3-ap-northeast-1.amazonaws.com"})
_ALLOWED_SYMBOLS = frozenset({"HOTUSDT", "BTCUSDT"})
_ARCHIVE_PATTERN = re.compile(
    r"(?P<symbol>HOTUSDT|BTCUSDT)-(?P<timeframe>15m|1h|4h|1d)-"
    r"(?P<date>\d{4}-\d{2}(?:-\d{2})?)\.zip$"
)


class BinanceVisionIntegrityError(ValueError):
    """Raised when an upstream archive fails identity or checksum validation."""


@dataclass(frozen=True, slots=True)
class VerifiedSourceFile:
    """One verified upstream ZIP and its published checksum."""

    key: str
    sha256: str
    byte_count: int
    candle_count: int


@dataclass(frozen=True, slots=True)
class BinanceVisionSyncResult:
    """One timeframe sync result with source and final dataset evidence."""

    symbol: str
    timeframe: str
    source_files: tuple[VerifiedSourceFile, ...]
    dataset_manifest: DatasetManifest
    source_manifest_path: str
    execution_allowed: bool = False


@dataclass(frozen=True, slots=True)
class BinanceVisionIngestor:
    """Build reproducible market-only datasets from Binance Vision archives."""

    archive: ParquetOHLCVArchive
    fetch: FetchBytes

    @classmethod
    def with_network(
        cls,
        archive: ParquetOHLCVArchive,
        *,
        timeout_seconds: float = 30.0,
        maximum_response_bytes: int = 128 * 1024 * 1024,
    ) -> "BinanceVisionIngestor":
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if maximum_response_bytes < 1024:
            raise ValueError("maximum_response_bytes must be at least 1024")

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
                raise BinanceVisionIntegrityError(
                    "Binance Vision response exceeds the configured size limit"
                )
            return payload

        return cls(archive=archive, fetch=fetch)

    def sync(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        *,
        as_of: date,
    ) -> tuple[BinanceVisionSyncResult, ...]:
        """Sync complete monthly archives plus closed daily archives."""
        normalized = symbol.strip().upper()
        if normalized not in _ALLOWED_SYMBOLS:
            raise ValueError(
                "Binance Vision sync is currently governed for HOTUSDT and BTCUSDT"
            )
        if not timeframes or len(set(timeframes)) != len(timeframes):
            raise ValueError("timeframes must be non-empty and unique")
        return tuple(
            self._sync_timeframe(normalized, timeframe, as_of)
            for timeframe in timeframes
        )

    def _sync_timeframe(
        self,
        symbol: str,
        timeframe: str,
        as_of: date,
    ) -> BinanceVisionSyncResult:
        monthly_prefix = f"data/spot/monthly/klines/{symbol}/{timeframe}/"
        monthly = self._archive_keys(monthly_prefix, symbol, timeframe, as_of)
        if not monthly:
            raise FileNotFoundError(f"no monthly Binance Vision files: {timeframe}")
        latest_month = max(self._archive_date(key) for key in monthly)
        daily_prefix = (
            f"data/spot/daily/klines/{symbol}/{timeframe}/"
            f"{symbol}-{timeframe}-{as_of:%Y-%m}"
        )
        daily = tuple(
            key
            for key in self._archive_keys(daily_prefix, symbol, timeframe, as_of)
            if self._archive_date(key) > latest_month
        )
        keys = (*monthly, *daily)
        verified: list[VerifiedSourceFile] = []
        candles: list[OHLCVCandle] = []
        for key in keys:
            source, parsed = self._verified_candles(key)
            verified.append(source)
            candles.extend(parsed)
        dataset = self.archive.update(
            symbol,
            timeframe,
            tuple(candles),
            source="BINANCE_VISION_CHECKSUM_VERIFIED",
        )
        source_path = self._write_source_manifest(
            symbol,
            timeframe,
            as_of,
            tuple(verified),
            dataset,
        )
        return BinanceVisionSyncResult(
            symbol,
            timeframe,
            tuple(verified),
            dataset,
            str(source_path),
        )

    def _archive_keys(
        self,
        prefix: str,
        symbol: str,
        timeframe: str,
        as_of: date,
    ) -> tuple[str, ...]:
        query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix})
        listing = self.fetch(f"{_LIST_URL}/?{query}")
        if len(listing) > 10 * 1024 * 1024:
            raise BinanceVisionIntegrityError("Binance Vision listing is too large")
        keys = tuple(
            value.decode("utf-8")
            for value in re.findall(rb"<Key>([^<]+)</Key>", listing)
        )
        archives = tuple(
            key
            for key in keys
            if key.endswith(".zip")
            and self._matches_archive(key, symbol, timeframe)
            and self._archive_date(key) < as_of
        )
        return tuple(sorted(archives, key=self._archive_date))

    @staticmethod
    def _matches_archive(key: str, symbol: str, timeframe: str) -> bool:
        match = _ARCHIVE_PATTERN.search(key)
        return (
            match is not None
            and match.group("symbol") == symbol
            and match.group("timeframe") == timeframe
        )

    @staticmethod
    def _archive_date(key: str) -> date:
        match = _ARCHIVE_PATTERN.search(key)
        if match is None:
            raise BinanceVisionIntegrityError("unexpected Binance Vision archive name")
        value = match.group("date")
        date_format = "%Y-%m-%d" if len(value) == 10 else "%Y-%m"
        return datetime.strptime(value, date_format).date()

    def _verified_candles(
        self,
        key: str,
    ) -> tuple[VerifiedSourceFile, tuple[OHLCVCandle, ...]]:
        encoded_key = urllib.parse.quote(key, safe="/")
        payload = self.fetch(f"{_BASE_URL}/{encoded_key}")
        published = self.fetch(f"{_BASE_URL}/{encoded_key}.CHECKSUM")
        expected = published.decode("ascii").strip().split()[0].lower()
        actual = sha256(payload).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
            raise BinanceVisionIntegrityError(f"checksum mismatch: {key}")
        candles = self._parse_zip(key, payload)
        return VerifiedSourceFile(key, actual, len(payload), len(candles)), candles

    @classmethod
    def _parse_zip(
        cls,
        key: str,
        payload: bytes,
    ) -> tuple[OHLCVCandle, ...]:
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                if len(names) != 1 or not names[0].endswith(".csv"):
                    raise BinanceVisionIntegrityError(
                        f"archive must contain exactly one CSV: {key}"
                    )
                text = io.TextIOWrapper(archive.open(names[0]), encoding="utf-8")
                return tuple(cls._row_to_candle(row) for row in csv.reader(text))
        except zipfile.BadZipFile:
            raise BinanceVisionIntegrityError(f"invalid ZIP archive: {key}") from None

    @staticmethod
    def _row_to_candle(row: list[str]) -> OHLCVCandle:
        if len(row) < 6:
            raise BinanceVisionIntegrityError("Binance Vision kline row is incomplete")
        try:
            raw_timestamp = int(row[0])
            divisor = 1_000_000 if raw_timestamp >= 100_000_000_000_000 else 1_000
            timestamp = datetime.fromtimestamp(raw_timestamp / divisor, tz=UTC)
            return OHLCVCandle(
                timestamp=timestamp,
                open=Decimal(row[1]),
                high=Decimal(row[2]),
                low=Decimal(row[3]),
                close=Decimal(row[4]),
                volume=Decimal(row[5]),
            )
        except (ValueError, ArithmeticError):
            raise BinanceVisionIntegrityError(
                "Binance Vision kline row contains invalid values"
            ) from None

    def _write_source_manifest(
        self,
        symbol: str,
        timeframe: str,
        as_of: date,
        source_files: tuple[VerifiedSourceFile, ...],
        dataset: DatasetManifest,
    ) -> Path:
        path = self.archive.root / symbol / f"{timeframe}.source-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        payload = {
            "schema_version": "1.0",
            "symbol": symbol,
            "timeframe": timeframe,
            "as_of_exclusive": as_of.isoformat(),
            "source": "BINANCE_VISION",
            "source_files": [asdict(item) for item in source_files],
            "source_file_count": len(source_files),
            "dataset_sha256": dataset.sha256,
            "dataset_row_count": dataset.row_count,
            "wallet_data_included": False,
            "execution_allowed": False,
        }
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path
