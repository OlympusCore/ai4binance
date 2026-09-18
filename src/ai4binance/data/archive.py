"""Atomic Parquet OHLCV archive with provenance and integrity manifests."""

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.schemas import OHLCVCandle

_SYMBOL_PATTERN = re.compile(r"^[^\W_]{2,24}(?:_(?:PERP|[0-9]{6}))?$")
_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Integrity and provenance record for one symbol/timeframe dataset."""

    schema_version: str
    symbol: str
    timeframe: str
    source: str
    parquet_path: str
    sha256: str
    row_count: int
    first_timestamp: str
    last_timestamp: str
    gap_count: int
    gaps: tuple[str, ...]
    generated_at: str


class DatasetIntegrityError(ValueError):
    """Raised when persisted or incremental market data is inconsistent."""


@dataclass(frozen=True, slots=True)
class ParquetOHLCVArchive:
    """Store market-only candles without wallet or inventory state."""

    root: Path

    def update(
        self,
        symbol: str,
        timeframe: str,
        candles: tuple[OHLCVCandle, ...],
        *,
        source: str,
        generated_at: datetime | None = None,
        replace_conflicts_from_sources: tuple[str, ...] = (),
    ) -> DatasetManifest:
        """Atomically merge closed candles and return a verified manifest."""
        normalized_symbol = self._validate_identity(symbol, timeframe, source)
        if not candles:
            raise ValueError("archive update requires at least one candle")
        paths = self._paths(normalized_symbol, timeframe)
        existing = self.read(normalized_symbol, timeframe) if paths[0].exists() else ()
        try:
            merged = self._merge(existing, candles)
        except DatasetIntegrityError:
            # A replacement allowance never covers conflicting stored rows.
            self._merge((), existing)
            existing_manifest = self._load_manifest(paths[1])
            if not any(
                existing_manifest.source.startswith(prefix)
                for prefix in replace_conflicts_from_sources
            ):
                raise
            by_timestamp = {candle.timestamp: candle for candle in existing}
            by_timestamp.update({candle.timestamp: candle for candle in candles})
            merged = tuple(
                by_timestamp[timestamp] for timestamp in sorted(by_timestamp)
            )
        if merged == existing:
            # A resumed collector commonly replays the last verified closed
            # bucket.  Keep the original immutable dataset and manifest when
            # that replay contributes no new candle instead of rewriting the
            # same Parquet payload with a new generated_at value.
            return self._load_manifest(paths[1])
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        self._write_parquet(paths[0], normalized_symbol, timeframe, source, merged)
        gaps = self._find_gaps(merged, timeframe)
        timestamp = generated_at or datetime.now(UTC)
        self._require_aware(timestamp)
        manifest = DatasetManifest(
            schema_version=_SCHEMA_VERSION,
            symbol=normalized_symbol,
            timeframe=timeframe,
            source=source.strip(),
            parquet_path=paths[0].name,
            sha256=self._file_checksum(paths[0]),
            row_count=len(merged),
            first_timestamp=merged[0].timestamp.isoformat(),
            last_timestamp=merged[-1].timestamp.isoformat(),
            gap_count=len(gaps),
            gaps=gaps,
            generated_at=timestamp.isoformat(),
        )
        self._write_manifest(paths[1], manifest)
        return manifest

    def read(self, symbol: str, timeframe: str) -> tuple[OHLCVCandle, ...]:
        """Read a checksum-verified dataset into market-only candle models."""
        normalized_symbol = self._validate_identity(symbol, timeframe, "read")
        parquet_path, manifest_path = self._paths(normalized_symbol, timeframe)
        if not parquet_path.exists() or not manifest_path.exists():
            identity = f"{normalized_symbol}/{timeframe}"
            raise FileNotFoundError(f"dataset not found: {identity}")
        manifest = self._load_manifest(manifest_path)
        if manifest.sha256 != self._file_checksum(parquet_path):
            raise DatasetIntegrityError("dataset checksum does not match manifest")
        table = pq.read_table(parquet_path)  # type: ignore[no-untyped-call]
        rows = table.to_pylist()
        candles = tuple(self._row_to_candle(row) for row in rows)
        if len(candles) != manifest.row_count:
            raise DatasetIntegrityError("dataset row count does not match manifest")
        return candles

    def read_window(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[OHLCVCandle, ...]:
        """Read a bounded range after verifying the complete dataset checksum."""

        self._require_aware(start_at)
        self._require_aware(end_at)
        window_start = start_at.astimezone(UTC)
        window_end = end_at.astimezone(UTC)
        if window_end < window_start:
            raise ValueError("dataset window end cannot precede start")
        normalized_symbol = self._validate_identity(symbol, timeframe, "read")
        parquet_path, manifest_path = self._paths(normalized_symbol, timeframe)
        if not parquet_path.exists() or not manifest_path.exists():
            identity = f"{normalized_symbol}/{timeframe}"
            raise FileNotFoundError(f"dataset not found: {identity}")
        manifest = self._load_manifest(manifest_path)
        if manifest.sha256 != self._file_checksum(parquet_path):
            raise DatasetIntegrityError("dataset checksum does not match manifest")
        table = pq.read_table(  # type: ignore[no-untyped-call]
            parquet_path,
            filters=[
                ("timestamp", ">=", window_start),
                ("timestamp", "<=", window_end),
            ],
        )
        candles = tuple(self._row_to_candle(row) for row in table.to_pylist())
        if len(candles) > manifest.row_count or any(
            not window_start <= candle.timestamp <= window_end for candle in candles
        ):
            raise DatasetIntegrityError("dataset window exceeds verified bounds")
        return candles

    def truncate_from(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_at: datetime,
        source: str,
        generated_at: datetime | None = None,
    ) -> DatasetManifest:
        """Atomically remove candles at or after a closed-candle boundary."""

        self._require_aware(start_at)
        normalized_symbol = self._validate_identity(symbol, timeframe, source)
        paths = self._paths(normalized_symbol, timeframe)
        existing = self.read(normalized_symbol, timeframe)
        boundary = start_at.astimezone(UTC)
        retained = tuple(candle for candle in existing if candle.timestamp < boundary)
        if not retained:
            raise DatasetIntegrityError("closed-candle repair would empty dataset")
        if retained == existing:
            return self._load_manifest(paths[1])
        self._write_parquet(paths[0], normalized_symbol, timeframe, source, retained)
        timestamp = generated_at or datetime.now(UTC)
        self._require_aware(timestamp)
        gaps = self._find_gaps(retained, timeframe)
        manifest = DatasetManifest(
            schema_version=_SCHEMA_VERSION,
            symbol=normalized_symbol,
            timeframe=timeframe,
            source=source.strip(),
            parquet_path=paths[0].name,
            sha256=self._file_checksum(paths[0]),
            row_count=len(retained),
            first_timestamp=retained[0].timestamp.isoformat(),
            last_timestamp=retained[-1].timestamp.isoformat(),
            gap_count=len(gaps),
            gaps=gaps,
            generated_at=timestamp.isoformat(),
        )
        self._write_manifest(paths[1], manifest)
        return manifest

    def manifest(self, symbol: str, timeframe: str) -> DatasetManifest:
        """Load a manifest after verifying its associated Parquet checksum."""
        normalized_symbol = self._validate_identity(symbol, timeframe, "read")
        parquet_path, manifest_path = self._paths(normalized_symbol, timeframe)
        manifest = self._load_manifest(manifest_path)
        if manifest.sha256 != self._file_checksum(parquet_path):
            raise DatasetIntegrityError("dataset checksum does not match manifest")
        return manifest

    def _paths(self, symbol: str, timeframe: str) -> tuple[Path, Path]:
        dataset_directory = self.root / symbol
        return (
            dataset_directory / f"{timeframe}.parquet",
            dataset_directory / f"{timeframe}.manifest.json",
        )

    @staticmethod
    def _validate_identity(symbol: str, timeframe: str, source: str) -> str:
        normalized_symbol = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized_symbol):
            raise ValueError("symbol must be an uppercase alphanumeric identifier")
        timeframe_duration(timeframe)
        if not source.strip():
            raise ValueError("dataset source cannot be empty")
        return normalized_symbol

    @staticmethod
    def _merge(
        existing: tuple[OHLCVCandle, ...],
        incoming: tuple[OHLCVCandle, ...],
    ) -> tuple[OHLCVCandle, ...]:
        by_timestamp: dict[datetime, OHLCVCandle] = {}
        for candle in (*existing, *incoming):
            current = by_timestamp.get(candle.timestamp)
            if current is not None and current != candle:
                raise DatasetIntegrityError(
                    f"conflicting candle at {candle.timestamp.isoformat()}"
                )
            by_timestamp[candle.timestamp] = candle
        return tuple(by_timestamp[key] for key in sorted(by_timestamp))

    @staticmethod
    def _find_gaps(
        candles: tuple[OHLCVCandle, ...],
        timeframe: str,
    ) -> tuple[str, ...]:
        duration = timeframe_duration(timeframe)
        return tuple(
            f"{current.timestamp.isoformat()}->{following.timestamp.isoformat()}"
            for current, following in pairwise(candles)
            if following.timestamp - current.timestamp != duration
        )

    @staticmethod
    def _write_parquet(
        path: Path,
        symbol: str,
        timeframe: str,
        source: str,
        candles: tuple[OHLCVCandle, ...],
    ) -> None:
        columns: dict[str, list[object]] = {
            "timestamp": [candle.timestamp for candle in candles],
            "open": [str(candle.open) for candle in candles],
            "high": [str(candle.high) for candle in candles],
            "low": [str(candle.low) for candle in candles],
            "close": [str(candle.close) for candle in candles],
            "volume": [str(candle.volume) for candle in candles],
        }
        table = pa.table(columns).replace_schema_metadata(
            {
                b"schema_version": _SCHEMA_VERSION.encode(),
                b"symbol": symbol.encode(),
                b"timeframe": timeframe.encode(),
                b"source": source.strip().encode(),
                b"market_data_only": b"true",
            }
        )
        temporary = path.with_suffix(".parquet.tmp")
        pq.write_table(  # type: ignore[no-untyped-call]
            table,
            temporary,
            compression="zstd",
        )
        os.replace(temporary, path)

    @staticmethod
    def _write_manifest(path: Path, manifest: DatasetManifest) -> None:
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    @staticmethod
    def _load_manifest(path: Path) -> DatasetManifest:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise DatasetIntegrityError("dataset manifest must be an object")
        try:
            raw["gaps"] = tuple(raw["gaps"])
            return DatasetManifest(**raw)
        except (KeyError, TypeError, ValueError):
            raise DatasetIntegrityError("dataset manifest is invalid") from None

    @staticmethod
    def _row_to_candle(row: dict[str, object]) -> OHLCVCandle:
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, datetime):
            raise DatasetIntegrityError("dataset timestamp is invalid")
        return OHLCVCandle(
            timestamp=timestamp,
            open=Decimal(str(row.get("open"))),
            high=Decimal(str(row.get("high"))),
            low=Decimal(str(row.get("low"))),
            close=Decimal(str(row.get("close"))),
            volume=Decimal(str(row.get("volume"))),
        )

    @staticmethod
    def _file_checksum(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _require_aware(timestamp: datetime) -> None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
