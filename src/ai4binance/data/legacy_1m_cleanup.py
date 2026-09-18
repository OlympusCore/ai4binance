"""Controlled cleanup of legacy 1m runtime market datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai4binance.data.archive import DatasetIntegrityError, ParquetOHLCVArchive
from ai4binance.data.market_history_sync import MARKET_HISTORY_TIMEFRAMES
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified


@dataclass(frozen=True, slots=True)
class LegacyOneMinuteCleanup:
    """Inspect or remove only replacement-verified legacy 1m runtime files."""

    dataset_root: Path

    def run(self, *, apply: bool = False) -> dict[str, object]:
        root = self.dataset_root.resolve()
        rows: list[dict[str, object]] = []
        blockers: list[str] = []
        removed_files = 0
        removed_bytes = 0
        for market in ("spot", "usd_m_futures"):
            market_root = (root / market).resolve()
            if market_root.parent != root or not market_root.exists():
                continue
            archive = ParquetOHLCVArchive(market_root)
            symbol_roots = sorted(
                path for path in market_root.iterdir() if path.is_dir()
            )
            for symbol_root in symbol_roots:
                legacy = tuple(
                    path
                    for path in (
                        symbol_root / "1m.parquet",
                        symbol_root / "1m.manifest.json",
                    )
                    if path.exists()
                )
                if not legacy:
                    continue
                try:
                    if len(legacy) != 2:
                        raise DatasetIntegrityError("legacy artifact set is incomplete")
                    legacy_manifest = archive.manifest(symbol_root.name, "1m")
                    if legacy_manifest.gap_count:
                        raise DatasetIntegrityError("legacy timeframe has gaps")
                    for timeframe in MARKET_HISTORY_TIMEFRAMES:
                        manifest = archive.manifest(symbol_root.name, timeframe)
                        if manifest.gap_count or not _is_direct_native_source(
                            manifest.source
                        ):
                            raise DatasetIntegrityError(
                                "replacement timeframe is not direct native data"
                            )
                except (DatasetIntegrityError, FileNotFoundError, ValueError):
                    blockers.append(
                        f"LEGACY_1M_REPLACEMENT_INVALID:{market}:{symbol_root.name}"
                    )
                    rows.append(
                        {
                            "market": market,
                            "symbol": symbol_root.name,
                            "status": "BLOCKED",
                            "paths": [
                                path.relative_to(root).as_posix() for path in legacy
                            ],
                        }
                    )
                    continue
                byte_count = sum(path.stat().st_size for path in legacy)
                status = "REMOVED" if apply else "READY_FOR_APPROVED_REMOVAL"
                if apply:
                    for path in legacy:
                        path.unlink()
                    removed_files += len(legacy)
                    removed_bytes += byte_count
                rows.append(
                    {
                        "market": market,
                        "symbol": symbol_root.name,
                        "status": status,
                        "byte_count": byte_count,
                        "paths": [path.relative_to(root).as_posix() for path in legacy],
                    }
                )
        payload: dict[str, object] = {
            "command": "market-history-cleanup-legacy-1m",
            "status": "BLOCKED" if blockers else "APPLIED" if apply else "DRY_RUN",
            "apply": apply,
            "rows": rows,
            "blockers": sorted(blockers),
            "removed_files": removed_files,
            "removed_bytes": removed_bytes,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_json_object_verified(
            root / "cleanup-receipts" / "legacy-1m-latest.json",
            payload,
            blocker="LEGACY_1M_CLEANUP_RECEIPT_WRITE_FAILED",
            subject_id="market-history:legacy-1m-cleanup",
            durable=True,
        )
        return payload


def _is_direct_native_source(source: str) -> bool:
    """Accept only checksum-verified archive, REST, or direct-WebSocket data."""

    return source.startswith(
        (
            "BINANCE_VISION_",
            "BINANCE_PUBLIC_REST_",
            "BINANCE_SPOT_WEBSOCKET_DIRECT",
            "BINANCE_USD_M_FUTURES_WEBSOCKET_DIRECT",
        )
    )
