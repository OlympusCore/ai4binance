"""Bounded dashboard opportunity refresh using public research inputs only."""

from __future__ import annotations

import argparse
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.application.opportunity_monitor import (
    MARKET_TIMEFRAMES,
    market_symbols,
    monitor_directory,
    refresh_monitor,
)
from ai4binance.cli.futures_multitf import _refresh_futures_monitor
from ai4binance.config import Settings
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.opportunity_intelligence import TIMEFRAME_DURATIONS
from ai4binance.ops.runtime import SingleInstanceLease
from ai4binance.schemas import OHLCVCandle


def refresh_candle_windows(
    settings: Settings,
    market: str,
    symbol: str,
    directory: Path,
    now: datetime,
    _client: object | None = None,
    *,
    allow_network: bool = False,
) -> ParquetOHLCVArchive:
    """Reuse verified canonical windows without independent provider retrieval."""

    del allow_network
    canonical = ParquetOHLCVArchive(
        settings.dataset_directory / ("spot" if market == "SPOT" else "usd_m_futures")
    )
    samples = ParquetOHLCVArchive(directory / "market-evidence")
    for tf in MARKET_TIMEFRAMES[market]:
        duration = TIMEFRAME_DURATIONS[tf]
        rows: tuple[OHLCVCandle, ...] = ()
        source = ""
        try:
            manifest = canonical.manifest(symbol, tf)
            last = datetime.fromisoformat(manifest.last_timestamp) + duration
            if (
                not manifest.gap_count
                and manifest.row_count >= settings.minimum_closed_candles
                and now - last <= duration * 2
            ):
                rows = canonical.read_window(
                    symbol,
                    tf,
                    start_at=now - duration * (settings.candle_limit + 2),
                    end_at=now,
                )
                source = "CANONICAL_ARCHIVE_SHA256:" + manifest.sha256
        except (OSError, ValueError):
            pass
        if rows:
            samples.update(symbol, tf, rows, source=source, generated_at=now)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=tuple(MARKET_TIMEFRAMES), required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--canonical-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    settings = Settings()
    now = datetime.now(UTC)
    if args.symbol not in market_symbols(
        settings.market_history_source_cache_directory, args.market, now
    ):
        raise ValueError("symbol is not in the current eligible market universe")
    root = Path.cwd()
    directory = monitor_directory(root, args.market, args.symbol)
    directory.mkdir(parents=True, exist_ok=True)

    with SingleInstanceLease(directory / "refresh.lock"):
        if args.market == "USD_M_FUTURES":
            _refresh_futures_monitor(settings, root, args.symbol, now)
            return 0
        archive = refresh_candle_windows(
            settings,
            args.market,
            args.symbol,
            directory,
            now,
        )
        refresh_monitor(
            root,
            archive,
            market=args.market,
            symbol=args.symbol,
            now=now,
            minimum_candles=settings.minimum_closed_candles,
            candle_limit=settings.candle_limit,
        )
    return 0


if __name__ == "__main__":
    deadline = threading.Timer(180, lambda: os._exit(124))
    deadline.daemon = True
    deadline.start()
    try:
        raise SystemExit(main())
    finally:
        deadline.cancel()
