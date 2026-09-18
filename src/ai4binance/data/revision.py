"""Cross-timeframe dataset revision manifests for reproducible research."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from ai4binance.data.archive import ParquetOHLCVArchive

_REVISION_SCHEMA_VERSION = "1.0"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,24}$")


@dataclass(frozen=True, slots=True)
class DatasetRevisionEntry:
    """One checksum-verified timeframe inside a dataset revision."""

    timeframe: str
    dataset_sha256: str
    row_count: int
    first_timestamp: str
    last_timestamp: str
    gap_count: int
    source: str
    source_manifest_sha256: str
    source_file_count: int


@dataclass(frozen=True, slots=True)
class DatasetRevisionManifest:
    """Immutable identity for a complete multi-timeframe research dataset."""

    schema_version: str
    revision_id: str
    symbol: str
    generated_at: str
    coverage_start: str
    coverage_end: str
    total_rows: int
    entries: tuple[DatasetRevisionEntry, ...]
    warnings: tuple[str, ...]
    research_ready: bool
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.revision_id.startswith("dataset:") or not self.entries:
            raise ValueError("dataset revision identity and entries are required")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("dataset revision cannot grant promotion or execution")


@dataclass(frozen=True, slots=True)
class DatasetRevisionBuilder:
    """Verify persisted Parquet/source manifests and seal one revision."""

    archive_root: Path
    minimum_history: timedelta = timedelta(days=365 * 5)

    def build(
        self,
        *,
        symbol: str,
        timeframes: tuple[str, ...] = ("5m", "15m", "1h", "4h", "1d"),
        generated_at: datetime | None = None,
    ) -> DatasetRevisionManifest:
        normalized = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("dataset revision symbol is invalid")
        if not timeframes or len(set(timeframes)) != len(timeframes):
            raise ValueError("dataset revision timeframes must be unique and non-empty")
        timestamp = generated_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("dataset revision timestamp must be timezone-aware")

        archive = ParquetOHLCVArchive(self.archive_root)
        entries = tuple(
            self._entry(archive, normalized, timeframe) for timeframe in timeframes
        )
        starts = tuple(datetime.fromisoformat(item.first_timestamp) for item in entries)
        ends = tuple(datetime.fromisoformat(item.last_timestamp) for item in entries)
        coverage_start = min(starts)
        coverage_end = max(ends)
        warnings = tuple(
            f"DATASET_GAPS_PRESENT:{item.timeframe}:{item.gap_count}"
            for item in entries
            if item.gap_count
        )
        research_ready = coverage_end - coverage_start >= self.minimum_history
        if not research_ready:
            warnings = (*warnings, "LONG_TERM_HISTORY_INSUFFICIENT")
        revision_id = self._revision_id(normalized, entries)
        return DatasetRevisionManifest(
            schema_version=_REVISION_SCHEMA_VERSION,
            revision_id=revision_id,
            symbol=normalized,
            generated_at=timestamp.isoformat(),
            coverage_start=coverage_start.isoformat(),
            coverage_end=coverage_end.isoformat(),
            total_rows=sum(item.row_count for item in entries),
            entries=entries,
            warnings=warnings,
            research_ready=research_ready,
        )

    def write(self, manifest: DatasetRevisionManifest) -> Path:
        """Atomically persist a deterministic revision manifest."""
        path = self.archive_root / manifest.symbol / "dataset-revision.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return path

    def _entry(
        self,
        archive: ParquetOHLCVArchive,
        symbol: str,
        timeframe: str,
    ) -> DatasetRevisionEntry:
        manifest = archive.manifest(symbol, timeframe)
        source_path = self.archive_root / symbol / f"{timeframe}.source-manifest.json"
        raw_bytes = source_path.read_bytes()
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict):
            raise ValueError("source manifest must be an object")
        if raw.get("dataset_sha256") != manifest.sha256:
            raise ValueError("source manifest dataset checksum mismatch")
        if raw.get("dataset_row_count") != manifest.row_count:
            raise ValueError("source manifest dataset row count mismatch")
        source_file_count = raw.get("source_file_count")
        if not isinstance(source_file_count, int) or source_file_count < 1:
            raise ValueError("source manifest file count is invalid")
        return DatasetRevisionEntry(
            timeframe=timeframe,
            dataset_sha256=manifest.sha256,
            row_count=manifest.row_count,
            first_timestamp=manifest.first_timestamp,
            last_timestamp=manifest.last_timestamp,
            gap_count=manifest.gap_count,
            source=manifest.source,
            source_manifest_sha256=sha256(raw_bytes).hexdigest(),
            source_file_count=source_file_count,
        )

    @staticmethod
    def _revision_id(
        symbol: str,
        entries: tuple[DatasetRevisionEntry, ...],
    ) -> str:
        payload = json.dumps(
            {
                "schema_version": _REVISION_SCHEMA_VERSION,
                "symbol": symbol,
                "entries": [asdict(item) for item in entries],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"dataset:{sha256(payload.encode('utf-8')).hexdigest()[:24]}"
