"""Separate, research-only Futures backtests for every supported timeframe."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ai4binance.learning.engine import ControlledLearningEngine
from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting.models import BacktestResult
from ai4binance.validation.futures_backtest_adapter import (
    RuntimeFuturesBacktestAdapter,
    RuntimeFuturesBacktestConfig,
    runtime_futures_backtest_engine,
)
from ai4binance.validation.futures_replay import (
    RUNTIME_FUTURES_REPLAY_TIMEFRAMES,
    RuntimeFuturesReplayDataset,
)
from ai4binance.whale_fusion.models import PriceOiRegime

# VirtualMarket's bounded TOP50 workflow intentionally omits the daily stream.
# Keep this replay research consumer aligned with the collector and opportunity
# monitor rather than reintroducing a fifth network download per Futures symbol.
FUTURES_MULTITF_TIMEFRAMES = tuple(
    timeframe
    for timeframe in RUNTIME_FUTURES_REPLAY_TIMEFRAMES
    if timeframe in {"5m", "15m", "1h", "4h"}
)
_SETUPS = (
    PriceOiRegime.NEW_LONG_PARTICIPATION,
    PriceOiRegime.SHORT_COVERING,
    PriceOiRegime.NEW_SHORT_PRESSURE,
    PriceOiRegime.DELEVERAGING,
)


@dataclass(frozen=True, slots=True)
class FuturesTimeframeBacktest:
    """Independent setup results for one symbol and timeframe."""

    timeframe: str
    dataset_sha256: str
    results: tuple[BacktestResult, ...]


@dataclass(frozen=True, slots=True)
class FuturesMultiTimeframeBacktestReport:
    """Auditable five-timeframe simulation report without execution authority."""

    symbol: str
    created_at: datetime
    timeframe_results: tuple[FuturesTimeframeBacktest, ...]
    learning_summary: object
    artifact_path: str
    artifact_sha256: str
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)


@dataclass(frozen=True, slots=True)
class FuturesMultiTimeframeBacktestRunner:
    """Run and persist each configured timeframe as a distinct backtest."""

    artifact_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_root", self.artifact_root.resolve())

    def run(
        self,
        datasets: Mapping[str, RuntimeFuturesReplayDataset],
        *,
        created_at: datetime | None = None,
    ) -> FuturesMultiTimeframeBacktestReport:
        """Backtest all directional setups and derive advisory learning evidence."""

        expected = set(FUTURES_MULTITF_TIMEFRAMES)
        if set(datasets) != expected:
            raise ValueError("Futures multi-timeframe datasets must be exact")
        ordered = tuple(datasets[timeframe] for timeframe in FUTURES_MULTITF_TIMEFRAMES)
        if any(not isinstance(item, RuntimeFuturesReplayDataset) for item in ordered):
            raise TypeError("Futures multi-timeframe input requires replay datasets")
        symbols = {item.symbol for item in ordered}
        if len(symbols) != 1 or any(
            item.timeframe != timeframe
            for timeframe, item in zip(FUTURES_MULTITF_TIMEFRAMES, ordered, strict=True)
        ):
            raise ValueError("Futures multi-timeframe dataset identity is inconsistent")
        supplied_timestamp = created_at or datetime.now(UTC)
        if supplied_timestamp.tzinfo is None or supplied_timestamp.utcoffset() is None:
            raise ValueError(
                "Futures multi-timeframe created_at must be timezone-aware"
            )
        timestamp = supplied_timestamp.astimezone(UTC)

        timeframe_results: list[FuturesTimeframeBacktest] = []
        all_backtests: list[BacktestResult] = []
        for dataset in ordered:
            backtest_engine = runtime_futures_backtest_engine(dataset)
            results = tuple(
                backtest_engine.run(
                    dataset=dataset,
                    signal_provider=RuntimeFuturesBacktestAdapter(
                        RuntimeFuturesBacktestConfig(setup=setup)
                    ),
                )
                for setup in _SETUPS
            )
            all_backtests.extend(results)
            timeframe_results.append(
                FuturesTimeframeBacktest(
                    timeframe=dataset.timeframe,
                    dataset_sha256=dataset.dataset_sha256,
                    results=results,
                )
            )

        learning = ControlledLearningEngine().analyze(
            created_at=timestamp,
            backtests=tuple(all_backtests),
        )
        symbol = ordered[0].symbol
        payload = self._payload(symbol, timestamp, tuple(timeframe_results), learning)
        artifact_path, artifact_sha256 = self._write(symbol, timestamp, payload)
        return FuturesMultiTimeframeBacktestReport(
            symbol=symbol,
            created_at=timestamp,
            timeframe_results=tuple(timeframe_results),
            learning_summary=learning,
            artifact_path=str(artifact_path),
            artifact_sha256=artifact_sha256,
        )

    @staticmethod
    def _payload(
        symbol: str,
        created_at: datetime,
        timeframe_results: tuple[FuturesTimeframeBacktest, ...],
        learning: object,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "symbol": symbol,
            "created_at": created_at.isoformat(),
            "timeframes": list(FUTURES_MULTITF_TIMEFRAMES),
            "timeframe_results": [
                {
                    "timeframe": item.timeframe,
                    "dataset_sha256": item.dataset_sha256,
                    "setups": [
                        {
                            "metrics": to_primitive(result.metrics),
                            "trades": to_primitive(result.trades),
                            "rejected_signals": to_primitive(result.rejected_signals),
                            "pre_veto_opportunities": to_primitive(
                                result.pre_veto_opportunity_ledger.records
                            ),
                            "missed_opportunities": to_primitive(
                                result.missed_opportunity_ledger.records
                            ),
                            "funnel_telemetry": to_primitive(result.funnel_telemetry),
                            "no_trade_count": result.no_trade_count,
                        }
                        for result in item.results
                    ],
                }
                for item in timeframe_results
            ],
            "second_brain_learning": to_primitive(learning),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def _write(
        self,
        symbol: str,
        created_at: datetime,
        payload: dict[str, object],
    ) -> tuple[Path, str]:
        directory = self.artifact_root / symbol
        directory.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        path = directory / f"{created_at:%Y%m%dT%H%M%SZ}-{digest[:16]}.json"
        temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
        latest = directory / "latest.json"
        latest_temporary = latest.with_suffix(f".json.{os.getpid()}.tmp")
        latest_temporary.write_bytes(encoded)
        os.replace(latest_temporary, latest)
        return path, digest


__all__ = (
    "FUTURES_MULTITF_TIMEFRAMES",
    "FuturesMultiTimeframeBacktestReport",
    "FuturesMultiTimeframeBacktestRunner",
    "FuturesTimeframeBacktest",
)
